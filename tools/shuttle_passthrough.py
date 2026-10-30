#!/usr/bin/env python3
"""TETHER shuttle: dumb bidirectional PX4-UDP <-> serial passthrough (stdlib + pyserial).

    uv run python tools/shuttle_passthrough.py --dev /dev/serial/by-path/<...> [--port 14601]

PX4 -> serial: every datagram from PX4 goes into a bounded queue (--queue-max bytes). When full,
the OLDEST WHOLE datagrams are dropped (counted), so stale telemetry never piles up. Writes are paced
at baud/10 B/s (8N1) and only while the kernel tty out-queue is under --kernel-max bytes, so latency
lives in our queue (visible, bounded), not in the kernel buffer.
serial -> PX4: bytes read from serial are sent, unparsed, to the address PX4's packets came from,
from the SAME socket (so PX4's per-instance commands such as cmd 511 hit the right instance).
--hold-reset (default ON): DTR=False/RTS=True are set BEFORE open() so an ESP32 DevKit's auto-reset
circuit holds EN low and the board acts as a plain USB-UART. Use --no-hold-reset for other adapters.
"""
import argparse
import collections
import errno
import os
import select
import socket
import time

import serial

ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
ap.add_argument("--bind", default="localhost", help="UDP bind host (PX4 sends to this)")
ap.add_argument("--port", type=int, default=14601, help="UDP bind port (PX4 -o remote port)")
ap.add_argument("--dev", required=True, help="serial device path")
ap.add_argument("--baud", type=int, default=115200)
ap.add_argument("--queue-max", type=int, default=2048, help="max queued bytes PX4->serial (K)")
ap.add_argument("--kernel-max", type=int, default=256, help="max bytes allowed in kernel tty out-queue")
ap.add_argument("--hold-reset", action=argparse.BooleanOptionalAction, default=True)
ap.add_argument("--quiet", action="store_true", help="no 1 Hz status line")
a = ap.parse_args()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((a.bind, a.port))
sock.setblocking(False)
ser = serial.Serial()  # unopened: set lines first so EN is held low from the moment we open
ser.port, ser.baudrate, ser.timeout = a.dev, a.baud, 0
if a.hold_reset:
    ser.dtr, ser.rts = False, True
ser.open()
fd = ser.fileno()  # pyserial opens O_NONBLOCK on POSIX; we os.write() it ourselves

px4 = None
q, qbytes, inflight = collections.deque(), 0, b""
st = dict(up_rx=0, up_tx=0, down=0, drop_dg=0, drop_b=0, down_nopeer=0)
rate = a.baud / 10.0  # 8N1 bytes/s
tokens, t_last, t_stat = 0.0, time.monotonic(), time.monotonic() + 1.0


def out_waiting():
    try:
        return ser.out_waiting
    except (OSError, serial.SerialException):
        return 0


print(f"shuttle: udp {a.bind}:{a.port} <-> {a.dev} @{a.baud} hold_reset={a.hold_reset} K={a.queue_max}B", flush=True)
while True:
    busy = bool(inflight or q)
    r, _, _ = select.select([sock, fd], [], [], 0.002 if busy else 0.1)
    if sock in r:  # PX4 -> queue (drain all pending datagrams)
        while True:
            try:
                d, src = sock.recvfrom(65535)
            except BlockingIOError:
                break
            if px4 != src:
                print(f"shuttle: PX4 peer = {src}", flush=True)
                px4 = src
            st["up_rx"] += len(d)
            q.append(d)
            qbytes += len(d)
            while qbytes > a.queue_max and q:  # drop oldest whole datagrams; inflight is never cut
                old = q.popleft()
                qbytes -= len(old)
                st["drop_dg"] += 1
                st["drop_b"] += len(old)
    if fd in r:  # serial -> PX4, unparsed
        data = ser.read(4096)
        if data:
            if px4:
                sock.sendto(data, px4)
                st["down"] += len(data)
            else:
                st["down_nopeer"] += len(data)
    now = time.monotonic()
    tokens = min(tokens + (now - t_last) * rate, a.kernel_max)
    t_last = now
    budget = int(min(tokens, a.kernel_max - out_waiting()))
    if budget > 0 and (inflight or q):
        if not inflight:
            inflight = q.popleft()
            qbytes -= len(inflight)
        try:
            n = os.write(fd, inflight[:budget])
        except OSError as e:
            if e.errno not in (errno.EAGAIN, errno.EWOULDBLOCK, errno.EINTR):
                raise
            n = 0
        inflight = inflight[n:]
        tokens -= n
        st["up_tx"] += n
    if now >= t_stat and not a.quiet:
        t_stat = now + 1.0
        print(f"px4->ser rx {st['up_rx']} tx {st['up_tx']} B | ser->px4 {st['down']} B "
              f"(nopeer {st['down_nopeer']}) | q {qbytes} B/{len(q)} dg | drops {st['drop_dg']} dg "
              f"{st['drop_b']} B | kq {out_waiting()} B", flush=True)

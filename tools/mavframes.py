#!/usr/bin/env python3
"""Stdlib-only MAVLink frame splitter (v1 + v2) used by census/probe tools.

Runs anywhere python3 exists (host venv or the bare guest):
    python3 mavframes.py [port] [seconds]     # listen on 0.0.0.0:port, print msgid census
A UDP datagram from PX4 may hold several MAVLink packets, so we split on frame
boundaries using the length byte; wire length = header + payload + CRC (+13 B v2 signature).
"""
import socket
import sys
import time

NAMES = {0: "HEARTBEAT", 1: "SYS_STATUS", 2: "SYSTEM_TIME", 30: "ATTITUDE", 31: "ATTITUDE_QUATERNION",
         32: "LOCAL_POSITION_NED", 33: "GLOBAL_POSITION_INT", 77: "COMMAND_ACK", 147: "BATTERY_STATUS",
         245: "EXTENDED_SYS_STATE", 109: "RADIO_STATUS"}


def split_frames(buf):
    """Yield (msgid, wire_len, sysid, compid, payload, version) for each frame in buf."""
    i, n = 0, len(buf)
    while i < n:
        b = buf[i]
        if b == 0xFD and i + 10 <= n:  # MAVLink 2: 10 B header + payload + 2 B CRC (+13 sig)
            plen, incompat = buf[i + 1], buf[i + 2]
            flen = 12 + plen + (13 if incompat & 0x01 else 0)
            if i + flen > n:
                return
            msgid = buf[i + 7] | (buf[i + 8] << 8) | (buf[i + 9] << 16)
            yield msgid, flen, buf[i + 5], buf[i + 6], buf[i + 10:i + 10 + plen], 2
            i += flen
        elif b == 0xFE and i + 6 <= n:  # MAVLink 1: 6 B header + payload + 2 B CRC
            plen = buf[i + 1]
            flen = 8 + plen
            if i + flen > n:
                return
            yield buf[i + 5], flen, buf[i + 3], buf[i + 4], buf[i + 6:i + 6 + plen], 1
            i += flen
        else:
            i += 1  # resync on garbage


if __name__ == "__main__":
    port = int(sys.argv[1]) if len(sys.argv) > 1 else 14550
    secs = float(sys.argv[2]) if len(sys.argv) > 2 else 10
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    s.bind(("0.0.0.0", port))
    s.settimeout(0.5)
    counts, srcs, t_end = {}, set(), time.monotonic() + secs
    while time.monotonic() < t_end:
        try:
            data, addr = s.recvfrom(65535)
        except socket.timeout:
            continue
        srcs.add(addr)
        for msgid, flen, *_ in split_frames(data):
            c = counts.setdefault(msgid, [0, 0])
            c[0] += 1
            c[1] += flen
    print(f"listened {secs:.0f}s on :{port}, sources={sorted(srcs)}")
    for msgid, (c, b) in sorted(counts.items(), key=lambda kv: -kv[1][1]):
        print(f"{msgid:6d} {NAMES.get(msgid, ''):22s} n={c:6d} {c / secs:7.1f} Hz {b / secs:8.0f} B/s")

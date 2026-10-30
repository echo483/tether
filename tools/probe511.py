#!/usr/bin/env python3
"""cmd 511 probe: MAV_CMD_SET_MESSAGE_INTERVAL through the SAME UDP socket that receives PX4's stream.

    uv run python tools/probe511.py [--bind localhost] [--port 14560] [--window 12]

Steps: learn PX4's source addr from first datagram -> PARAM_REQUEST_READ (return-path proof +
failsafe params) -> baseline ATTITUDE rate -> 511(msg 30, 1e6 us) + ACK -> measure -> 511(msg 30, 0 =
default) + ACK -> measure. Rates counted on raw frames (msgid 30, sysid 1) over --window s host time.
"""
import argparse
import json
import socket
import struct
import time

from pymavlink.dialects.v20 import common as m2

from mavframes import split_frames

ap = argparse.ArgumentParser()
ap.add_argument("--bind", default="localhost")
ap.add_argument("--port", type=int, default=14560)
ap.add_argument("--window", type=float, default=12.0)
ap.add_argument("--settle", type=float, default=2.0)
ap.add_argument("--msgid", type=int, default=30)
ap.add_argument("--params", default="NAV_DLL_ACT,COM_DL_LOSS_T,COM_DLL_EXCEPT")
a = ap.parse_args()

sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
sock.bind((a.bind, a.port))
sock.settimeout(0.2)
mav = m2.MAVLink(None, srcSystem=255, srcComponent=190)
mav.robust_parsing = True
data, px4 = sock.recvfrom(65535)
print(f"PX4 stream source = {px4!r} (reply target), host socket = {sock.getsockname()!r}")
out = {"px4_src": list(px4), "bind": [a.bind, a.port]}


def pump(seconds, want=None):
    """Receive for `seconds`; return (count of msgid a.msgid, decoded msgs matching `want` predicate)."""
    n, got, t_end = 0, [], time.monotonic() + seconds
    while time.monotonic() < t_end:
        try:
            d, src = sock.recvfrom(65535)
        except socket.timeout:
            continue
        for msgid, _flen, sysid, _c, _p, _v in split_frames(d):
            n += (msgid == a.msgid and sysid == 1)
        if want:
            got += [m for m in (mav.parse_buffer(d) or []) if want(m)]
    return n, got


def send(msg):
    sock.sendto(msg.pack(mav), px4)  # same socket, reply to the address the stream came from


params = {}
for pid in a.params.split(","):
    send(m2.MAVLink_param_request_read_message(1, 1, pid.encode(), -1))
    _, pv = pump(1.5, lambda m: m.get_type() == "PARAM_VALUE" and m.param_id == pid)
    if pv:
        v = pv[0]
        val = struct.unpack("<i", struct.pack("<f", v.param_value))[0] if v.param_type in (5, 6) else v.param_value
        params[pid] = {"value": val, "type": v.param_type}
    else:
        params[pid] = None
print("params:", params)
out["params"] = params


def set_interval(us):
    for attempt in range(3):
        send(m2.MAVLink_command_long_message(1, 1, 511, attempt, a.msgid, us, 0, 0, 0, 0, 0))
        _, acks = pump(1.0, lambda m: m.get_type() == "COMMAND_ACK" and m.command == 511)
        if acks:
            return acks[0].result
    return None


res = {}
n0, _ = pump(a.window)
res["baseline"] = {"n": n0, "window_s": a.window, "hz": n0 / a.window}
ack1 = set_interval(1_000_000)
pump(a.settle)
n1, _ = pump(a.window)
res["after_1hz"] = {"ack": ack1, "n": n1, "window_s": a.window, "hz": n1 / a.window}
ack2 = set_interval(0)
pump(a.settle)
n2, _ = pump(a.window)
res["after_restore"] = {"ack": ack2, "n": n2, "window_s": a.window, "hz": n2 / a.window}
out["rates"] = res
ok = ack1 == 0 and abs(n1 / a.window - 1) < 0.35 and ack2 == 0 and n2 > 0.8 * n0
out["verdict"] = "PASS" if ok else "FAIL"
print(json.dumps(out, indent=1))

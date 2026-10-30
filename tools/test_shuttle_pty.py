#!/usr/bin/env python3
"""Loopback test of shuttle_passthrough.py against an os.openpty() pair (no hardware).

    uv run python tools/test_shuttle_pty.py [--port 14561] [--secs 10] [--baud 115200]

Shuttle opens the pty SLAVE as its "serial port"; this script plays the radio on the MASTER:
it parses everything PX4 sends (pymavlink, CRC-checked) and injects PARAM_REQUEST_READ(NAV_DLL_ACT)
into the master to prove the serial->PX4 direction (expects PARAM_VALUE back through the pty).
"""
import argparse
import os
import select
import subprocess
import sys
import time
import tty

from pymavlink.dialects.v20 import common as m2

ap = argparse.ArgumentParser()
ap.add_argument("--port", type=int, default=14561)
ap.add_argument("--secs", type=float, default=10)
ap.add_argument("--baud", type=int, default=115200)
ap.add_argument("--queue-max", type=int, default=2048)
a = ap.parse_args()

master, slave = os.openpty()
tty.setraw(master)
path = os.ttyname(slave)
here = os.path.dirname(os.path.abspath(__file__))
sh = subprocess.Popen([sys.executable, "-u", os.path.join(here, "shuttle_passthrough.py"), "--dev", path,
                       "--port", str(a.port), "--baud", str(a.baud), "--queue-max", str(a.queue_max)],
                      stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True)
mav = m2.MAVLink(None, srcSystem=255, srcComponent=191)
mav.robust_parsing = True
counts, nbytes, bad, pv, sent_req = {}, 0, 0, None, False
t0 = time.monotonic()
while time.monotonic() - t0 < a.secs:
    r, _, _ = select.select([master], [], [], 0.1)
    if master in r:
        d = os.read(master, 4096)
        nbytes += len(d)
        for m in mav.parse_buffer(d) or []:
            t = m.get_type()
            if t == "BAD_DATA":
                bad += 1
                continue
            counts[t] = counts.get(t, 0) + 1
            if t == "PARAM_VALUE" and m.param_id == "NAV_DLL_ACT":
                pv = (m.param_id, m.param_value, m.param_type, round(time.monotonic() - t0, 2))
    if not sent_req and counts.get("HEARTBEAT") and time.monotonic() - t0 > 3:
        os.write(master, m2.MAVLink_param_request_read_message(1, 1, b"NAV_DLL_ACT", -1).pack(mav))
        sent_req = True
sh.terminate()
out = sh.communicate(timeout=5)[0].strip().splitlines()
el = time.monotonic() - t0
print("shuttle output (first 3 / last 2):", *out[:3], "...", *out[-2:], sep="\n  ")
print(f"pty master received {nbytes} B in {el:.1f}s ({nbytes / el:.0f} B/s); BAD_DATA={bad}")
for k in ("HEARTBEAT", "ATTITUDE", "SYS_STATUS", "GLOBAL_POSITION_INT"):
    print(f"  {k}: n={counts.get(k, 0)}")
print(f"  distinct msg types={len(counts)}; PARAM_VALUE(NAV_DLL_ACT) via serial->PX4->serial: {pv}")
ok = counts.get("HEARTBEAT", 0) > 0 and counts.get("ATTITUDE", 0) > 0 and pv is not None
print("VERDICT:", "PASS" if ok else "FAIL")

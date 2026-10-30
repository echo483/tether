"""T1a probe: talk to a DroneBridge ESP32 AP with no autopilot attached.

DroneBridge only sends to UDP clients it has heard from, so we send a GCS heartbeat first,
then print what comes back once per second (msg counts by type, sysid/compid, RADIO_STATUS).

    uv run python tools/rf_probe.py              # default: DroneBridge AP gateway (tnet.DB_IP):14550
    uv run python tools/rf_probe.py --secs 30
"""
import argparse
import time
from collections import Counter

from pymavlink import mavutil
from tnet import DB_IP

ap = argparse.ArgumentParser()
ap.add_argument("--host", default=DB_IP)
ap.add_argument("--port", type=int, default=14550)
ap.add_argument("--secs", type=float, default=20.0)
a = ap.parse_args()

m = mavutil.mavlink_connection(f"udpout:{a.host}:{a.port}", source_system=255, source_component=190)
t0 = last_hb = last_print = time.monotonic()
first_rx = None
window, total, ids = Counter(), Counter(), set()
while time.monotonic() - t0 < a.secs:
    now = time.monotonic()
    if now - last_hb >= 1.0:
        m.mav.heartbeat_send(mavutil.mavlink.MAV_TYPE_GCS, mavutil.mavlink.MAV_AUTOPILOT_INVALID, 0, 0, 0)
        last_hb = now
    msg = m.recv_match(blocking=True, timeout=0.2)
    if msg is not None and msg.get_type() != "BAD_DATA":
        if first_rx is None:
            first_rx = now - t0
            print(f"first frame after {first_rx:.2f} s")
        window[msg.get_type()] += 1
        total[msg.get_type()] += 1
        ids.add((msg.get_srcSystem(), msg.get_srcComponent()))
        if msg.get_type() == "RADIO_STATUS":
            print(f"  RADIO_STATUS rssi={msg.rssi} remrssi={msg.remrssi} txbuf={msg.txbuf} "
                  f"noise={msg.noise} rxerrors={msg.rxerrors}")
    if now - last_print >= 1.0:
        print(f"t={now - t0:5.1f}s  {dict(window) or 'NOTHING'}")
        window.clear()
        last_print = now

print("\nTOTAL", dict(total), "\nsysid/compid seen:", sorted(ids))
print("PASS" if total.get("HEARTBEAT") else "FAIL: no heartbeat received")

"""t1_diag.py — decide, from counters alone, why board 1 isn't decoding MAVLink from board 3.

Needs: laptop on the TETHER AP (t1_diag.sh handles it), board 3 the only USB serial device.
Three 5-second tests, each read off board 1's own counters (/api/system/stats):
  A  board 3 held in reset, laptop sends nothing     -> board 1 should receive ~0 B
  B  board 3 RUNNING (its ROM spams "invalid header" on TX0) -> if board 1 receives that, its RX
     is wired to board 3's TX0: the jumpers are SWAPPED
  C  board 3 held, laptop sends 50 HEARTBEAT/s       -> board 1 should receive ~1 kB/s and decode ~50 msg/s
"""
import glob
import json
import time
import urllib.request

import socket

import serial
from pymavlink.dialects.v20 import common as mav

DB = "http://" + ".".join(map(str, (192, 168, 2, 1)))


def api(path):
    try:
        return json.load(urllib.request.urlopen(f"{DB}/api/{path}", timeout=3))
    except Exception as e:  # noqa: BLE001
        return {"ERR": str(e)}


def stats():
    d = api("system/stats")
    return d.get("read_bytes"), d.get("serial_dec_mav_msgs")


def delta(a, b):
    return None if None in (a[0], b[0]) else (b[0] - a[0], b[1] - a[1])


s = api("settings")
print("BOARD 1 SETTINGS:", {k: s.get(k) for k in ("ssid", "wifi_chan", "esp32_mode", "proto", "baud", "gpio_tx", "gpio_rx", "gpio_rts", "gpio_cts")} if "ERR" not in s else s)
if "ERR" not in s and (s.get("baud"), s.get("gpio_tx"), s.get("gpio_rx"), s.get("proto")) != (115200, 19, 18, 4):
    print("!! CONFIG DRIFT: expected baud 115200, tx 19, rx 18, proto 4")

dev = sorted(set(glob.glob("/dev/serial/by-path/*port0")))[0]
ser = serial.Serial()
ser.port, ser.baudrate, ser.timeout = dev, 115200, 0.05
ser.dtr, ser.rts = False, True
ser.open()
ser.rts = False; time.sleep(0.1); ser.rts = True          # explicit reset pulse, then hold
time.sleep(0.5); ser.reset_input_buffer()
res = {}


def window(name, secs=5.0, send=None):
    a = stats(); got = 0; t0 = time.time(); nxt = t0
    while time.time() - t0 < secs:
        got += len(ser.read(4096))
        if send and time.time() >= nxt:
            ser.write(send); nxt += 0.02                  # 50 frames/s
    b = stats(); d = delta(a, b)
    res[name] = d
    print(f"{name}: board1 rx bytes / mav msgs in {secs:.0f}s = {d}   (laptop heard from board 3: {got} B)")


window("A held+silent")
ser.rts = False                                            # release: board 3 boots and spams its TX0
window("B board3 running")
ser.rts = True; time.sleep(0.3); ser.reset_input_buffer()
hb = mav.MAVLink_heartbeat_message(2, 12, 0, 0, 4, 3).pack(mav.MAVLink(None, srcSystem=1, srcComponent=1))
window("C held+heartbeats", send=hb)

# D: the other direction. Send UDP to board 1; DroneBridge writes it out its TX (D19) -> wire 2 -> board 3 TX0
# -> CP2102 -> laptop. Board 3 held. Tests wire 2 + GND without needing wire 1.
u = socket.socket(socket.AF_INET, socket.SOCK_DGRAM); u.bind(("", 0)); u.setblocking(False)
gcs = mav.MAVLink_heartbeat_message(6, 8, 0, 0, 4, 3).pack(mav.MAVLink(None, srcSystem=255, srcComponent=190))
heard = b""; t0 = time.time(); nxt = t0
while time.time() - t0 < 5.0:
    heard += ser.read(4096)
    if time.time() >= nxt:
        try: u.sendto(gcs, (DB.split("//")[1], 14550))
        except OSError: pass
        nxt += 0.02
parser = mav.MAVLink(None); parser.robust_parsing = True
n_hb = sum(1 for m in (parser.parse_buffer(heard) or []) if m.get_type() == "HEARTBEAT")
res["D uplink"] = (len(heard), n_hb)
print(f"D uplink: laptop heard {len(heard)} B from board 1 via wire 2, {n_hb} heartbeats decoded (sent ~250)")
ser.close()

A, B, C, D = res["A held+silent"], res["B board3 running"], res["C held+heartbeats"], res["D uplink"]
print("\nVERDICT:")
up_ok = D[1] > 50
print(f"  wire 2 + GND (board1 D19 -> board3 TX0): {'OK' if up_ok else 'NOT WORKING'}")
if None in (A, B, C):
    print("  could not read board 1 counters — laptop not on the AP?")
elif C[1] > 100:
    print(f"  WIRING OK: board 1 decoded {C[1]} heartbeats. Rerun tools/t1b.sh.")
elif B[0] > 2000 and C[0] < 1000:
    print("  JUMPERS SWAPPED: board 1's RX hears board 3's TX0. Swap the two jumper ends AT BOARD 1 (D18<->D19), rerun.")
elif C[0] > 2000 and C[1] == 0:
    print(f"  BYTES ARRIVE BUT DON'T DECODE ({C[0]} B): baud mismatch or a bad contact. Check baud above; re-seat jumpers + GND.")
elif up_ok:
    print("  GND and wire 2 are GOOD, so WIRE 1 is the problem: it must run board 3 RX0 -> board 1 D18.")
    print("  Check its board-3 end is in RX0's row (not TX0 just above it) and its board-1 end in D18's row (not D19 / D5 beside it).")
elif C[0] < 1000 and B[0] < 1000:
    print("  NOTHING CROSSES IN EITHER DIRECTION: most likely the GND jumper (board 3 GND -> board 1 GND) is missing or in the wrong row.")
    print("  Fix GND first, then re-seat wires 1 and 2. Send Hermes a photo if unsure.")
else:
    print("  unclear — send this report to Hermes.")

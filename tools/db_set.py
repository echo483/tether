"""db_set.py — change a few DroneBridge settings without touching the password, then read back.

    uv run python tools/db_set.py --read
    uv run python tools/db_set.py wifi_chan=6            # e.g. move channel at the venue
    uv run python tools/db_set.py baud=115200 gpio_tx=19 gpio_rx=18

POST /api/settings only changes the keys you send; the board saves and reboots ~2 s later, and it
silently drops values it rejects, so we always read back and compare.
"""
import json
import subprocess
import sys
import time
import urllib.request

from tnet import DB_IP

BASE = f"http://{DB_IP}/api"
SECRET = ("wifi_pass", "espnow_secret")


def get():
    d = json.load(urllib.request.urlopen(f"{BASE}/settings", timeout=4))
    return {k: ("<hidden>" if k in SECRET else v) for k, v in d.items()}


if len(sys.argv) < 2 or sys.argv[1] == "--read":
    print(json.dumps(get(), indent=1))
    sys.exit(0)

want = {}
for kv in sys.argv[1:]:
    k, v = kv.split("=", 1)
    if k in SECRET:
        sys.exit("refusing to set secrets here — use the web UI or tools/db_apply.sh")
    want[k] = int(v) if v.lstrip("-").isdigit() else v
req = urllib.request.Request(f"{BASE}/settings", data=json.dumps(want).encode(),
                             headers={"Content-Type": "application/json"}, method="POST")
print("POST", want, "->", json.load(urllib.request.urlopen(req, timeout=5)).get("msg"))
print("board rebooting; reconnecting wifi …")
time.sleep(9)
subprocess.run(["nmcli", "con", "up", "tether-ap"], capture_output=True)
for _ in range(10):
    try:
        got = get()
        break
    except OSError:
        time.sleep(2)
else:
    sys.exit("FAIL: board not reachable after reboot")
bad = {k: (got.get(k), v) for k, v in want.items() if got.get(k) != v}
print("VERIFY", "OK" if not bad else f"MISMATCH (got, want): {bad}")
sys.exit(1 if bad else 0)

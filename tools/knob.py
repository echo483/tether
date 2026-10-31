"""knob.py — the demo hot keys. One command per beat; same doors the sweep uses.

    uv run python tools/knob.py squeeze 1600     # capacity squeeze to 1600 B/s (synthetic, disclosed)
    uv run python tools/knob.py clear            # capacity back to unlimited
    uv run python tools/knob.py blackout 3       # drop all downlink for 3 s
    uv run python tools/knob.py on | off         # TETHER manager on / off (live)
    uv run python tools/knob.py boundary         # squeeze below the critical set (700 B/s): TETHER must fail
    uv run python tools/knob.py                  # interactive: s=squeeze c=clear b=blackout 1=on 0=off x=boundary q=quit
"""
import json
import socket
import sys

from tnet import AIR_CTRL_PORT, GROUND_CTRL_PORT, LOCAL

S = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)


def air(msg):
    S.sendto(json.dumps(msg).encode(), (LOCAL, AIR_CTRL_PORT)); print("air   <-", msg)


def ground(msg):
    S.sendto(json.dumps(msg).encode(), (LOCAL, GROUND_CTRL_PORT)); print("ground<-", msg)


def do(cmd, arg=None):
    if cmd in ("squeeze", "s"):
        air({"C_Bps": float(arg or 1600)})
    elif cmd in ("clear", "c"):
        air({"C_Bps": None})
    elif cmd in ("blackout", "b"):
        air({"blackout_s": float(arg or 3)})
    elif cmd in ("boundary", "x"):
        air({"C_Bps": 700.0})
    elif cmd in ("on", "1"):
        ground({"manager": True})
    elif cmd in ("off", "0"):
        ground({"manager": False})
    else:
        print(__doc__)


if len(sys.argv) > 1:
    do(sys.argv[1], sys.argv[2] if len(sys.argv) > 2 else None)
else:
    print("keys: s=squeeze 1600  c=clear  b=blackout 3 s  1=TETHER on  0=TETHER off  x=boundary 700  q=quit")
    for line in sys.stdin:
        k = line.strip()
        if k == "q":
            break
        if k:
            do(k.split()[0], k.split()[1] if len(k.split()) > 1 else None)

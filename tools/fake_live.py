"""fake_live.py — SYNTHETIC ground/air JSONL writer for testing dash.py and copilot.py (not data).

    uv run python tools/fake_live.py                    # logs/fake/{ground,air}.jsonl, loops forever
    uv run python tools/fake_live.py --dir logs/live    # only when no real air.py/ground.py is running!
    uv run python tools/fake_live.py --secs 45 --manager off

Per cycle (--period 45 s): squeeze C = 1600 B/s at t = 10-30 s, blackout at 35-38 s. With the manager
on it sheds to T0 at ~12 s, restores T1 at 22 s and T2 at 33 s. Fluid queue K = 3200 B (same as PREREG).
"""
import argparse
import json
import random
import time
from pathlib import Path

ap = argparse.ArgumentParser()
ap.add_argument("--dir", default="logs/fake")
ap.add_argument("--secs", type=float, default=0.0, help="stop after N s (0 = forever)")
ap.add_argument("--period", type=float, default=45.0)
ap.add_argument("--manager", choices=["on", "off"], default="on")
ap.add_argument("--emulated", type=int, default=1)
ap.add_argument("--seed", type=int, default=7)
a = ap.parse_args()

ROOT = Path(__file__).resolve().parent.parent
D = Path(a.dir) if Path(a.dir).is_absolute() else ROOT / a.dir
D.mkdir(parents=True, exist_ok=True)
G = open(D / "ground.jsonl", "w", buffering=1)
A = open(D / "air.jsonl", "w", buffering=1)
rng = random.Random(a.seed)
T0, T1, T2 = 889.0, 519.0, 893.0
LOAD = [T0 + T1 + T2, T0 + T1, T0]          # offered B/s by number of tiers shed
HZ = {"T0": 24.0, "T1": 10.0, "T2": 30.0}
K, DT, MGR = 3200.0, 0.2, a.manager == "on"
SHED = {1: ["ATTITUDE_QUATERNION", "ATTITUDE_TARGET", "POSITION_TARGET_LOCAL_NED"],
        2: ["VFR_HUD", "LOCAL_POSITION_NED", "ALTITUDE", "GPS_RAW_INT"]}


def w(f, **kv):
    f.write(json.dumps(kv) + "\n")


t0 = time.time()
q, drops, tier, last_rx, k, prev_tier = 0.0, 0, 0, t0, 0, 0
print(f"fake_live: SYNTHETIC logs -> {D} (manager {a.manager})")
while not a.secs or time.time() - t0 < a.secs:
    now = time.time()
    tr = (now - t0) % a.period
    squeeze, blackout = 10 <= tr < 30, 35 <= tr < 38
    C = 1600.0 if squeeze else None
    if MGR:
        tier = 2 if 12 <= tr < 22 else 1 if 22 <= tr < 33 else 0
    L = LOAD[tier]
    cap = C if C else 11520.0
    q = min(K, max(0.0, q + (L - cap) * DT))
    full = q >= K - 1
    if full:
        drops += 1
    if blackout:
        q = 0.0
    else:
        last_rx = now - rng.uniform(0.0, 0.06)
    qdelay = q / cap
    age = (now - last_rx) + qdelay + 0.02
    link = "blackout" if blackout and tr - 35 > 0.3 else "stale" if age > 1.0 else "ok"
    share = 0.0 if blackout else (min(1.0, cap / L) if full else 1.0)
    rx = {n: (0.0 if (i > 0 and tier >= 3 - i) else round(HZ[n] * share * rng.uniform(0.9, 1.1), 1))
          for i, n in enumerate(("T0", "T1", "T2"))}
    good = 0 if blackout else round(min(L, cap) * rng.uniform(0.95, 1.03))
    w(G, t=now, kind="tick", picture_age_s=round(age, 3), aoi_s={"ATTITUDE": round(age, 3)},
      qdelay_s=round(qdelay, 3), loss=round(1 - cap / L, 3) if full else 0.0, goodput_Bps=good,
      rx_hz=rx, link=link, tier=tier, manager=MGR)
    if tier != prev_tier:
        what = "shed" if tier > prev_tier else "restore"
        why = "qdelay>q_hi for 0.6s" if what == "shed" else "qdelay<q_lo for 3.0s"
        w(G, t=now, kind="event", what=what, tier=tier, reason=why)
        for lvl in range(min(tier, prev_tier) + 1, max(tier, prev_tier) + 1):
            for m in SHED[lvl]:
                w(G, t=now, kind="event", what="cmd511", msg=m, interval_us=-1 if what == "shed" else 0)
        prev_tier = tier
    if k % 5 == 0:
        w(A, t=now, kind="air", C_Bps=0 if blackout else C, K_bytes=int(K), offered_Bps=round(L), sent_Bps=0
          if blackout else round(min(L, cap)), q_bytes=round(q), drops=drops, seed=a.seed, emulated=bool(a.emulated),
          blackout=blackout, C_set=C)
    k += 1
    time.sleep(max(0.0, t0 + k * DT - time.time()))

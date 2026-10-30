"""qsim.py — pre-registration simulator for TETHER (prep tool, not the product).

Feeds the measured offered-load census through the same model the demo stages:
a drop-tail byte queue of K bytes drained at capacity C(t), with C stepping down then back up.
Arms: U0 = no manager; M = TETHER policy (shed a tier when queueing delay stays high,
restore one tier after it stays low — hysteresis + probe-up). Output = predicted picture age.

    uv run python tools/qsim.py                       # default census + policy, n=10 seeds/arm
    uv run python tools/qsim.py --c-lo 1200 --k-sec 3 --boundary
"""
import argparse
import json
import random
from collections import deque
from pathlib import Path

import numpy as np

HERE = Path(__file__).resolve().parent
DEFAULT_TIERS = [
    ["HEARTBEAT", "ATTITUDE", "GLOBAL_POSITION_INT", "SYS_STATUS", "BATTERY_STATUS", "EXTENDED_SYS_STATE"],
    ["VFR_HUD", "LOCAL_POSITION_NED", "ALTITUDE", "HOME_POSITION", "MISSION_CURRENT", "GPS_RAW_INT", "PING"],
]  # tier 2 = everything else in the census


def load_streams(census_path, tiers):
    rows = json.load(open(census_path))["rows"]
    out = []
    for r in rows:
        tier = next((i for i, t in enumerate(tiers) if r["name"] in t), len(tiers))
        out.append({"name": r["name"], "hz": r["hz"], "size": r["mean_len"], "tier": tier})
    return out


def run(streams, arm, seed, c_hi, c_lo, k_bytes, t_on=10.0, t_off=40.0, t_end=55.0, dt=0.002,
        q_hi=0.5, q_lo=0.1, t_detect=0.6, t_restore=3.0, uplink=0.05, jump=False):
    rng = random.Random(seed)
    n_tiers = max(s["tier"] for s in streams) + 1
    nxt = [rng.uniform(0, 1 / s["hz"]) for s in streams]
    queue, q_bytes, inflight = deque(), 0, deque()
    link_free, shed, pending = 0.0, 0, []       # shed = number of tiers currently off (from the top)
    hi_since = lo_since = None
    latest_att, last_q = None, 0.0
    samples, drops, sent = [], 0, 0
    t = 0.0
    while t < t_end:
        C = c_lo if t_on <= t < t_off else c_hi
        # PX4 applies a rate command `uplink` seconds after the manager sends it
        while pending and pending[0][0] <= t:
            shed = pending.pop(0)[1]
        for i, s in enumerate(streams):
            while nxt[i] <= t:
                period = 1 / s["hz"]
                nxt[i] += period * rng.uniform(0.95, 1.05)
                if s["tier"] >= n_tiers - shed and s["tier"] > 0:
                    continue                      # stream is shed at the source
                sent += 1
                if q_bytes + s["size"] > k_bytes:
                    drops += 1                    # drop-tail
                    continue
                queue.append((t, s, t)); q_bytes += s["size"]
        while queue and link_free <= t:          # serializer at C bytes/s
            gen, s, _ = queue.popleft(); q_bytes -= s["size"]
            link_free = max(link_free, t) + s["size"] / C
            inflight.append((link_free, gen, s["name"]))
        while inflight and inflight[0][0] <= t:
            fin, gen, name = inflight.popleft()
            if name == "ATTITUDE":
                latest_att, last_q = gen, fin - gen
        if arm == "M" and not pending:           # the manager sees only what arrived
            hi_since = (hi_since or t) if last_q > q_hi else None
            lo_since = (lo_since or t) if last_q < q_lo else None
            if hi_since and t - hi_since >= t_detect and shed < n_tiers - 1:
                pending.append((t + uplink, n_tiers - 1 if jump else shed + 1)); hi_since = None
            elif lo_since and t - lo_since >= t_restore and shed > 0:
                pending.append((t + uplink, shed - 1)); lo_since = None
        if round(t / dt) % 100 == 0:             # 5 Hz picture-age samples
            samples.append((t, t - latest_att if latest_att is not None else np.nan))
        t += dt
    s = np.array(samples)
    win = s[(s[:, 0] >= t_on) & (s[:, 0] < t_off), 1]
    stale = s[(s[:, 0] >= t_on) & (s[:, 1] > 1.0)]
    return {"p50": float(np.nanpercentile(win, 50)), "p99": float(np.nanpercentile(win, 99)),
            "max": float(np.nanmax(win)), "t_stale": float(stale[0, 0] - t_on) if len(stale) else None,
            "drop_frac": drops / max(sent, 1), "frac_stale": float(np.mean(win > 1.0))}


def ci(xs):
    xs = np.array(xs, float); n = len(xs)
    t95 = {5: 2.776, 10: 2.262, 20: 2.093, 30: 2.045}.get(n, 1.96)
    return xs.mean(), t95 * xs.std(ddof=1) / np.sqrt(n) if n > 1 else 0.0


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--census", default=str(HERE.parent / "notes/evidence/census-14561.json"))
    ap.add_argument("--c-hi", type=float, default=11520.0, help="B/s, 115200 8N1 UART")
    ap.add_argument("--c-lo", type=float, default=1200.0)
    ap.add_argument("--k-sec", type=float, default=3.0, help="queue K = k_sec * c_lo bytes")
    ap.add_argument("--n", type=int, default=10)
    ap.add_argument("--boundary", action="store_true")
    ap.add_argument("--jump", action="store_true", help="shed straight to tier 0, then probe up one tier at a time")
    a = ap.parse_args()
    st = load_streams(a.census, DEFAULT_TIERS)
    L = sum(s["hz"] * s["size"] for s in st)
    by_tier = [sum(s["hz"] * s["size"] for s in st if s["tier"] == k) for k in range(3)]
    K = a.k_sec * a.c_lo
    print(f"L={L:.0f} B/s  tiers T0/T1/T2 = {by_tier[0]:.0f}/{by_tier[1]:.0f}/{by_tier[2]:.0f} B/s"
          f"  C_lo={a.c_lo:.0f}  K={K:.0f} B  arithmetic: fill≈{K / max(L - a.c_lo, 1):.1f}s  stale≈{K / a.c_lo:.1f}s")
    out = {"L": L, "tiers_Bps": by_tier, "c_lo": a.c_lo, "K": K, "arms": {}}
    for arm in ("U0", "M"):
        rs = [run(st, arm, seed, a.c_hi, a.c_lo, K, jump=a.jump) for seed in range(a.n)]
        p50, p50c = ci([r["p50"] for r in rs]); p99, p99c = ci([r["p99"] for r in rs])
        ts = [r["t_stale"] for r in rs if r["t_stale"] is not None]
        fs, fsc = ci([r["frac_stale"] for r in rs])
        out["arms"][arm] = rs
        print(f"{arm:>2}: picture age p50 {p50:.2f}±{p50c:.2f}s  p99 {p99:.2f}±{p99c:.2f}s  (n={a.n} seeds)"
              f"  >1s {100*fs:.0f}±{100*fsc:.0f}% of squeeze  first >1s at +{np.mean(ts):.1f}s" if ts else
              f"{arm:>2}: picture age p50 {p50:.2f}±{p50c:.2f}s  p99 {p99:.2f}±{p99c:.2f}s  (n={a.n} seeds)  never >1s")
    if a.boundary:
        print("boundary sweep, arm M (fails = picture >1 s old for more than half the squeeze):")
        out["boundary"] = []
        for c in range(500, 1700, 100):
            r = run(st, "M", 0, a.c_hi, c, a.k_sec * c, jump=a.jump)
            out["boundary"].append({"c_lo": c, **r})
            print(f"  C_lo={c:5d} B/s  p50={r['p50']:.2f}s  stale {100*r['frac_stale']:3.0f}%  "
                  f"{'FAILS' if r['frac_stale'] > 0.5 else 'holds'}")
    Path(HERE.parent / "notes/evidence/qsim-last.json").write_text(json.dumps(out, indent=1))

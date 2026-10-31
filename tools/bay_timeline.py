#!/usr/bin/env python3
"""bay_timeline.py DIR — the measured timeline of one bay mission run (air.jsonl truth + ground.jsonl events).

    uv run python tools/bay_timeline.py logs/bay-on-<ts>
t = 0 at takeoff (first air record with alt_m > 1). Range at an event is interpolated from the 1 Hz air records.
"""
import json
import sys
from pathlib import Path

D = Path(sys.argv[1])
rd = lambda p: [json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []  # noqa: E731
air = [r for r in rd(D / "air.jsonl") if r.get("kind") == "air"]
g = rd(D / "ground.jsonl") + rd(D / "manual.jsonl")
ticks, ev = [r for r in g if r.get("kind") == "tick"], sorted([r for r in g if r.get("kind") == "event"],
                                                               key=lambda r: r["t"])
fly = [r for r in air if (r.get("alt_m") or 0) > 1.0]
if not fly:
    sys.exit("no flight in air.jsonl")
t0 = fly[0]["t"]


def rng_at(t):
    pts = [(r["t"], r["range_m"]) for r in air if r.get("range_m") is not None]
    for (ta, ra), (tb, rb) in zip(pts, pts[1:]):
        if ta <= t <= tb:
            return ra + (rb - ra) * (t - ta) / max(tb - ta, 1e-9)
    return pts[-1][1] if pts else None


def line(t, what):
    r = rng_at(t)
    print(f"  T+{t - t0:6.1f} s  range {'—' if r is None else f'{r:5.0f}'} m  {what}")


print(f"run {D}")
prev = "x"
for r in air:                                            # capacity regime changes (truth)
    c = "BLACKOUT" if r.get("blackout") else "unlimited" if r.get("C_set") is None else f"{r['C_set']} B/s"
    if c != prev and r["t"] >= t0 - 5:
        line(r["t"], f"air: capacity -> {c}")
    prev = c
for e in ev:
    w = e.get("what")
    if w in ("shed", "restore"):
        line(e["t"], f"TETHER {w} -> tier {e['tier']} ({e.get('reason')})")
    elif w == "failsafe":
        line(e["t"], f"TETHER FAILSAFE {e['action']}: {e['reason']} (picture_age {e.get('picture_age_s')} s, "
                     f"link {e.get('link')})")
    elif w == "cmd":
        line(e["t"], f"  cmd {e.get('name')} sent")
    elif w == "ack":
        line(e["t"], f"  COMMAND_ACK cmd {e['command']} result {e['result']}")
    elif w in ("manual_rtl", "manager"):
        line(e["t"], f"{w} {e.get('on', '')}")
mx = max(air, key=lambda r: r.get("range_m") or 0)
line(mx["t"], f"MAX RANGE {mx['range_m']:.0f} m (alt {mx.get('alt_m')} m)")
after = [r for r in air if r["t"] > mx["t"] and (r.get("alt_m") or 0) < 0.5]
if after:
    line(after[0]["t"], f"back on the ground: alt {after[0]['alt_m']} m, range from home {after[0]['range_m']} m")
fl = [k for k in ticks if t0 <= k["t"] <= (after[0]["t"] if after else 1e18)]
pa = [k["picture_age_s"] for k in fl if k.get("picture_age_s") is not None]
bo = sum(1 for k in fl if k.get("link") == "blackout")
if pa:
    stale = sum(1 for x in pa if x > 1.0)
    print(f"  picture_age in flight: max {max(pa):.1f} s · >1 s for {stale / 5:.1f} s of {len(fl) / 5:.0f} s "
          f"({100 * stale / len(pa):.0f}%) · link=blackout for {bo / 5:.1f} s")
bo_air = [r for r in air if r.get("blackout")]
if bo_air:
    print(f"  air blackout: {len(bo_air)} s total (from T+{bo_air[0]['t'] - t0:.1f} s)")

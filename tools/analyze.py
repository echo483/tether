#!/usr/bin/env python3
"""analyze.py — the TETHER results table (DEMO.md 1:42–2:00) from CONTRACT.md §2 logs. Stdlib only.
    ~/.local/bin/uv run python tools/analyze.py [logs/runs.csv | logs/ | logs/<run_id> ...]   # default: logs/
    ~/.local/bin/uv run python tools/analyze.py --selftest   # synthetic runs -> logs/selftest-*/, exit 0 = pass
Window = the squeeze (air.jsonl 0 < C_Bps < L), the window PREREG.md speaks in; no squeeze -> whole run (noted).
Headline = share of ticks stale (picture_age_s > 1.0 s), NOT p99 (p99 is the detection transient).
Arms: mean ± 95% t-CI across runs; U0−M paired by seed, t at df = n−1 (1.96 above df 30).
Boundary (squeeze C < L_crit): predicted level K/C and onset K/(L−C) vs observed — level = median picture age
once the queue is full; onset = air.jsonl q_bytes crossing 0.9 K (interpolated between the 1 Hz samples).
"""
import argparse, csv, json, math, random, re, statistics as st, sys, time  # noqa: E401
from collections import deque
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
L_BPS, L_CRIT, STALE_S = 2300.4, 1359.4, 1.0      # notes/census.md L, L_crit; CONTRACT §2 stale
CSV_COLS = ["run_id", "arm", "seed", "start", "end", "dir"]      # logs/runs.csv, written by tools/sweep.py
RUN_RE = re.compile(r"^\d{8}-\d{6}-(U0|U1|M)-(\d+)$")
T95 = dict(enumerate(map(float, """12.706 4.303 3.182 2.776 2.571 2.447 2.365 2.306 2.262 2.228 2.201 2.179 2.160
    2.145 2.131 2.12 2.11 2.101 2.093 2.086 2.08 2.074 2.069 2.064 2.06 2.056 2.052 2.048 2.045 2.042""".split()), 1))
COLS = [("age mean s", "mean", 1, 2), ("age p50 s", "p50", 1, 2), ("age p99 s", "p99", 1, 2),
        ("stale>1s %", "stale", 100, 0), ("loss %", "loss", 100, 1), ("goodput B/s", "goodput", 1, 0)]
NAN = math.nan

tcrit = lambda df: T95.get(df, 1.96) if df >= 1 else NAN  # noqa: E731  95% two-sided t, df 1..30

def ci(xs):
    xs = [x for x in xs if x is not None and not math.isnan(x)]
    if not xs:
        return NAN, NAN
    return st.fmean(xs), (tcrit(len(xs) - 1) * st.stdev(xs) / math.sqrt(len(xs)) if len(xs) > 1 else NAN)

def pct(xs, p):
    xs, k = sorted(xs), (len(xs) - 1) * p / 100
    i = int(k)
    return xs[i] + (xs[min(i + 1, len(xs) - 1)] - xs[i]) * (k - i) if xs else NAN

def read_jsonl(path, t0=None, t1=None):
    out = []
    for line in path.read_text().splitlines() if path.exists() else []:
        try:
            r = json.loads(line)
        except ValueError:
            continue                                  # torn last line from a killed process
        if isinstance(r, dict) and isinstance(r.get("t"), (int, float)) and (t0 is None or t0 <= r["t"] <= t1):
            out.append(r)
    return out

def discover(paths):
    runs = {}
    for p in map(Path, paths):
        csvp = p if p.suffix == ".csv" else p / "runs.csv"
        if csvp.is_file():
            with open(csvp, newline="") as f:
                found = [dict(r, seed=int(r["seed"]), start=float(r["start"]), end=float(r["end"]),
                              dir=next((d for d in (csvp.parent / Path(r["dir"]).name, Path(r["dir"]), ROOT / r["dir"])
                                        if d.is_dir()), Path(r["dir"]))) for r in csv.DictReader(f)]
        else:                                         # run dirs sit beside runs.csv: survives copying logs/
            ms = [(q, RUN_RE.match(q.name)) for q in ([p] + sorted(p.iterdir()) if p.is_dir() else [])]
            found = [{"run_id": q.name, "arm": m[1], "seed": int(m[2]), "dir": q, "start": None, "end": None}
                     for q, m in ms if m and q.is_dir()]
        runs.update((r["run_id"], r) for r in found)
    return sorted(runs.values(), key=lambda r: r["run_id"])

def measure(run):
    """Per-run statistics over the squeeze window; None if ground.jsonl has no ticks."""
    d, t0, t1 = Path(run["dir"]), run.get("start"), run.get("end")
    air = [a for a in read_jsonl(d / "air.jsonl", t0, t1) if a.get("kind") == "air"]
    ticks = [k for k in read_jsonl(d / "ground.jsonl", t0, t1) if k.get("kind") == "tick"]
    if not ticks:
        return None
    sq = [a for a in air if a.get("C_Bps") and a["C_Bps"] < L_BPS]       # null = unlimited, 0 = blackout
    gaps = [b["t"] - a["t"] for a, b in zip(air, air[1:])]
    half = (st.median(gaps) if gaps else 1.0) / 2
    w0, w1 = (sq[0]["t"] - half, sq[-1]["t"] + half) if sq else (ticks[0]["t"], ticks[-1]["t"] + 1e-6)
    win = [k for k in ticks if w0 <= k["t"] < w1]
    ages = [k["picture_age_s"] for k in win if k.get("picture_age_s") is not None]
    m = dict(run, squeeze=bool(sq), mean=st.fmean(ages) if ages else NAN, p50=pct(ages, 50), p99=pct(ages, 99),
             stale=sum(k.get("picture_age_s") is None or k["picture_age_s"] > STALE_S for k in win) / max(len(win), 1),
             loss=st.fmean(k.get("loss") or 0.0 for k in win) if win else NAN,
             goodput=st.fmean(k.get("goodput_Bps") or 0.0 for k in win) if win else NAN,
             tier_end=ticks[-1].get("tier"), mgr_bad=sum(bool(k.get("manager")) != (run["arm"] == "M") for k in ticks),
             C=None, K=None, onset=None, level=None)
    if sq:
        C, K = st.median(a["C_Bps"] for a in sq), st.median(a.get("K_bytes") or 0 for a in sq)
        m.update(C=C, K=K)
        pts = [(w0, 0.0)] + [(a["t"], a.get("q_bytes") or 0.0) for a in sq]
        for (ta, qa), (tb, qb) in zip(pts, pts[1:]):
            if K and qb >= 0.9 * K:                    # queue full: first crossing of 0.9 K
                m["onset"] = ta + (tb - ta) * (0.9 * K - qa) / max(qb - qa, 1e-9) - w0
                break
        on = m["onset"] if m["onset"] is not None else K / (L_BPS - C)
        plat = [k["picture_age_s"] for k in win if k["t"] >= w0 + on + K / C and k.get("picture_age_s") is not None]
        m["level"] = st.median(plat) if plat else None   # plateau = after the fill plus one full sojourn
    return m

cell = lambda mh, sc, nd: "—" if math.isnan(mh[0]) else f"{mh[0] * sc:.{nd}f}" + (  # noqa: E731
    "" if math.isnan(mh[1]) else f"±{mh[1] * sc:.{nd}f}")
f2 = lambda x: "—" if x is None else f"{x:.2f}"  # noqa: E731

def report(runs):
    ms = [m for m in map(measure, runs) if m]
    for r in [r for r in runs if r["run_id"] not in {m["run_id"] for m in ms}]:
        print(f"skip {r['run_id']}: no ground.jsonl ticks in {r['dir']}")
    is_b = lambda m: m["C"] is not None and m["C"] < L_CRIT  # noqa: E731
    bnd, main, by = [m for m in ms if is_b(m)], [m for m in ms if not is_b(m)], {"U0": {}, "M": {}, "U1": {}}
    for m in main:                                   # runs are in time order: a re-run of (arm, seed) wins
        by[m["arm"]][m["seed"]] = m
    seeds = sorted(set(by["U0"]) & set(by["M"]))
    n, out = len(seeds), {"n": len(seeds), "boundary": []}
    print(f"\nTETHER results — {n} paired runs U0 vs M (joined by seed) · window = squeeze (air C_Bps < L = "
          f"{L_BPS} B/s) · ± = 95% t-CI, df={n - 1}, t={tcrit(n - 1):.3f}")
    print(f"{'arm':<6}{'n':>3}" + "".join(f"{h:>14}" for h, *_ in COLS))
    for arm, rs in [(a, [by[a][s] for s in seeds]) for a in ("U0", "M")] + [("U1", list(by["U1"].values()))]:
        if rs:
            print(f"{arm:<6}{len(rs):>3}" + "".join(f"{cell(ci([r[c[1]] for r in rs]), *c[2:]):>14}" for c in COLS))
    if n:
        diffs = {k: [by["U0"][s][k] - by["M"][s][k] for s in seeds] for _, k, _, _ in COLS}
        print(f"{'U0−M':<6}{n:>3}" + "".join(f"{cell(ci(diffs[c[1]]), *c[2:]):>14}" for c in COLS) + "  paired")
        u, mm, p99u, p99m = [ci([by[a][s][k] for s in seeds])[0] * (100 if k == "stale" else 1)
                             for k in ("stale", "p99") for a in ("U0", "M")]          # stale shares in %
        d, h = (100 * x for x in ci(diffs["stale"]))
        out.update(u0_stale=u, m_stale=mm, d=d, h=h)
        print(f"HEADLINE  picture >1 s old for {u:.0f}% of the squeeze unmanaged vs {mm:.0f}% with TETHER; "
              f"paired U0−M = {d:.0f} pp, 95% CI [{d - h:.0f}, {d + h:.0f}] pp (n={n})")
        print(f"PREREG    falsifier U0 stale < 70%: {'FIRED' if u < 70 else 'no'} ({u:.0f}%) · falsifier M stale > "
              f"20%: {'FIRED' if mm > 20 else 'no'} ({mm:.0f}%) · paired CI excludes 0: {'yes' if d - h > 0 else 'NO'}")
        print(f'SAY       "{n} paired runs tonight: unmanaged, the picture was over a second old {u:.0f}% of the '
              f'squeeze; with TETHER, {mm:.0f}%. Paired difference {d:.0f} points, 95% CI {d - h:.0f} to {d + h:.0f}. '
              f'p99 age {p99u:.2f} s vs {p99m:.2f} s. Raw logs in the repo."')
    else:
        print("no complete U0/M pair (same seed, squeeze C >= L_crit) — no paired difference")
    print(f"\nBOUNDARY  squeeze C < L_crit = {L_CRIT} B/s · predicted level K/C, onset K/(L−C), L = {L_BPS} B/s · "
          f"tolerance: level ±max(25%, 0.3 s), onset ±max(50%, 1.0 s)" + ("" if bnd else "\n  none in these runs"))
    for m in bnd:
        C, K, ol, oo = m["C"], m["K"], m["level"], m["onset"]
        pl, po = (K / C, K / (L_BPS - C)) if K else (NAN, NAN)
        lok = ol is not None and abs(ol - pl) <= max(0.25 * pl, 0.3)
        ook = oo is not None and abs(oo - po) <= max(0.5 * po, 1.0)
        out["boundary"].append(v := "PASS" if lok and ook else "FAIL")
        print(f"  {m['run_id']:<24} {m['arm']:<3} C={C:.0f} K={K:.0f}  level pred {pl:.2f} obs {f2(ol)} s "
              f"{'PASS' if lok else 'FAIL'} · onset pred {po:.2f} obs {f2(oo)} s {'PASS' if ook else 'FAIL'} · "
              f"stale {100 * m['stale']:.0f}% → PREDICTION {v}" + ("  (K_bytes missing)" if not K else ""))
    unp = [m["run_id"] for a in ("U0", "M") for s, m in by[a].items() if s not in seeds]
    for what, ids in (("unpaired, not in the table", unp), ("no squeeze in air.jsonl → whole-run window",
                      [m["run_id"] for m in main if not m["squeeze"]]), ("WARN ground 'manager' flag disagrees with "
                      "the arm", [f"{m['run_id']} ({m['mgr_bad']} ticks)" for m in ms if m["mgr_bad"]])):
        if ids:
            print(f"note: {what}: {', '.join(ids)}")
    return out

# --- self-test: the qsim drop-tail model, emitted as CONTRACT §2 logs (PREREG tiers 889/519/893 B/s) ---
SYN = [("ATTITUDE", 588.0, 40, 0), ("T0_REST", 301.0, 43, 0), ("T1", 519.0, 37, 1), ("T2", 893.0, 52, 2)]

def synth(d, arm, seed, start, c_lo, run_s=28.0, t_on=5.0, t_off=23.0, bo_at=24.0, bo_s=3.0, dt=0.005):
    """One seeded run: C steps 11520 → c_lo → 11520 B/s (time-indexed), K = 2 s × c_lo, a 3 s blackout."""
    rng, K = random.Random(seed), 2.0 * c_lo           # same seed => same frame times in both arms
    nxt = [rng.uniform(0, size / bps) for _, bps, size, _ in SYN]
    t_air, t_tick = random.Random(seed + 1000).uniform(0, 1), 0.0   # air.py's 1 Hz log phase vs the step
    q, queue, inflight, hist, pending, air, gnd, latest = 0.0, deque(), deque(), deque(), [], [], [], {}
    shed, link_free, last_rx, qd, drops, hi, lo = 0, 0.0, 0.0, 0.0, 0, None, None
    for i in range(int(run_s / dt)):
        t = i * dt
        C, blk = (c_lo if t_on <= t < t_off else 11520.0), bo_at <= t < bo_at + bo_s
        shed = pending.pop(0)[1] if pending and pending[0][0] <= t else shed   # PX4 applies cmd 511 50 ms later
        for j, (name, bps, size, tier) in enumerate(SYN):
            while nxt[j] <= t:
                nxt[j] += size / bps * rng.uniform(0.95, 1.05)
                if tier and tier >= 3 - shed:
                    continue                            # shed at the source (cmd 511 interval −1)
                full = q + size > K                     # drop-tail byte queue
                drops += full
                hist.extend([(t, "gen", size, tier)] + [(t, "lost", size, tier)] * full)
                if not full:
                    queue.append((t, name, size, tier))
                    q += size
        while queue and link_free <= t:                 # serializer at C B/s
            gen, name, size, tier = queue.popleft()
            q, link_free = q - size, max(link_free, t) + size / C
            hist.append((t, "sent", size, tier))
            inflight.append((link_free, gen, name, size, tier, blk))
        while inflight and inflight[0][0] <= t:
            fin, gen, name, size, tier, lost = inflight.popleft()
            hist.append((t, "lost" if lost else "rx", size, tier))
            if not lost:
                last_rx, latest[name], qd = t, gen, fin - gen if name == "ATTITUDE" else qd
        while hist and hist[0][0] < t - 1.0:
            hist.popleft()
        if arm == "M" and not pending:                  # the manager sees only what arrived
            hi = (t if hi is None else hi) if qd > 0.5 else None
            lo = (t if lo is None else lo) if qd < 0.1 else None
            new = (2, "qdelay>q_hi for 0.6s") if hi is not None and t - hi >= 0.6 and shed < 2 else \
                  (shed - 1, "qdelay<q_lo for 3.0s, probe up") if lo is not None and t - lo >= 3.0 and shed else None
            if new:
                pending, hi, lo = [(t + 0.05, new[0])], None, None
                a, b = sorted((3 - shed, 3 - new[0]))
                gnd += [{"t": start + t, "kind": "event", "what": "shed", "tier": new[0], "reason": new[1]}] + [
                    {"t": start + t, "kind": "event", "what": "cmd511", "msg": s[0],
                     "interval_us": -1 if new[0] > shed else 0} for s in SYN if a <= s[3] < b]
        if t >= t_tick:
            t_tick += 0.2
            rx, nlost = [h for h in hist if h[1] == "rx"], sum(h[1] == "lost" for h in hist)
            age = t - latest["ATTITUDE"] if "ATTITUDE" in latest else None
            gnd.append({"t": start + t, "kind": "tick", "picture_age_s": None if age is None else round(age, 3),
                        "aoi_s": {k: round(t - g, 3) for k, g in latest.items()}, "qdelay_s": round(qd, 3),
                        "loss": round(nlost / max(nlost + len(rx), 1), 3), "goodput_Bps": sum(h[2] for h in rx),
                        "rx_hz": {f"T{k}": sum(h[3] == k for h in rx) for k in range(3)},
                        "link": "blackout" if t - last_rx > 0.5 else "stale" if age is None or age > 1 else "ok",
                        "tier": shed, "manager": arm == "M"})
        if t >= t_air:
            t_air += 1.0
            air.append({"t": start + t, "kind": "air", "C_Bps": C, "K_bytes": K, "q_bytes": round(q),
                        "offered_Bps": sum(h[2] for h in hist if h[1] == "gen"),
                        "sent_Bps": sum(h[2] for h in hist if h[1] == "sent"), "drops": drops, "seed": seed})
    d.mkdir(parents=True, exist_ok=True)
    for name, rows in (("air", air), ("ground", gnd)):
        (d / f"{name}.jsonl").write_text("".join(json.dumps(r) + "\n" for r in rows))

def selftest():
    root, base, rows = ROOT / "logs" / time.strftime("selftest-%Y%m%d-%H%M%S"), time.time() - 3600, []
    plan = [(arm, s, 1600.0) for s in (1, 2, 3) for arm in ("U0", "M")] + [("U0", 99, 700.0), ("M", 99, 700.0)]
    for i, (arm, seed, c_lo) in enumerate(plan):
        start = base + 30 * i
        rid = f"{time.strftime('%Y%m%d-%H%M%S', time.localtime(start))}-{arm}-{seed}"
        synth(root / rid, arm, seed, start, c_lo)
        rows.append([rid, arm, seed, f"{start:.3f}", f"{start + 28:.3f}", f"logs/{root.name}/{rid}"])
    (root / "runs.csv").write_text("".join(",".join(map(str, r)) + "\n" for r in [CSV_COLS] + rows))
    print(f"selftest: {len(plan)} synthetic runs — C 11520→1600 B/s (pairs) or →700 B/s (boundary) at +5 s, "
          f"back at +23 s, K = 2 s × C, 3 s blackout at +24 s — in {root.relative_to(ROOT)}/")
    res = report(discover([root / "runs.csv"]))
    checks = [("3 pairs joined by seed", res["n"] == 3), ("U0 stale >= 70% (PREREG)", res.get("u0_stale", 0) >= 70),
              ("M stale <= 20% (PREREG)", res.get("m_stale", 100) <= 20),
              ("paired 95% CI on stale share excludes 0", res.get("d", 0) - res.get("h", NAN) > 0),
              ("2 boundary runs, both PREDICTION PASS", res["boundary"] == ["PASS", "PASS"])]
    ok = all(c for _, c in checks)
    print("\n" + "".join(f"  {'ok ' if c else 'BAD'} {x}\n" for x, c in checks) + "SELFTEST " + ("FAIL", "PASS")[ok])
    return 0 if ok else 1

def main():
    ap = argparse.ArgumentParser(description="TETHER results table (see module docstring)")
    ap.add_argument("paths", nargs="*", help="runs.csv, logs/ dir or logs/<run_id>/ dirs (default: logs/)")
    ap.add_argument("--selftest", action="store_true", help="synthetic pairs + boundary runs; exit 0 = pass")
    a = ap.parse_args()
    runs = None if a.selftest else discover(a.paths or [ROOT / "logs"])
    if runs == []:
        print("no runs found (want logs/runs.csv or logs/<YYYYmmdd-HHMMSS-arm-seed>/ dirs)")
    return selftest() if a.selftest else 0 if runs and report(runs) else 2

if __name__ == "__main__":
    sys.exit(main())

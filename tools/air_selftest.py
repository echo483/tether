#!/usr/bin/env python3
"""air_selftest.py — emulated-mode self-test of tools/air.py (no hardware; PX4 SIH must stream to :14601).

    ~/.local/bin/uv run python tools/air_selftest.py            # ~105 s, prints the per-phase table

Starts `air.py --emulated`, plays the ground side itself (binds tnet.LOCAL:tnet.DB_UDP_PORT like ground.py,
parses with pymavlink parse_buffer, compid 68 excluded), drives air.py's control port on a fixed timeline and
sends PARAM_REQUEST_READ uplink to the datagrams' source to prove the uplink. ATTITUDE age = now − gen_time,
gen_time = time_boot_ms/1000 + offset. Reported ages are skew-corrected (PX4 SIH's clock runs ~4 % slow vs the
host, so a plain min-offset drifts); age30 = CONTRACT §2 as written (min over the last 30 s), for comparison.
Logs: logs/air-selftest-<ts>/{air.jsonl,listen.jsonl}.
"""
import json, select, socket, statistics as stt, subprocess, sys, time  # noqa: E401
from pathlib import Path

from pymavlink.dialects.v20 import common as mav

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
import tnet  # noqa: E402

RUN = HERE.parent / "logs" / f"air-selftest-{time.strftime('%Y%m%d-%H%M%S')}"
PLAN = [(15, {"C_Bps": 1600}), (35, {"C_Bps": None}), (45, {"blackout_s": 3}), (55, {"profile": "step", "seed": 1})]
PARAM_AT, END = [3, 12, 30, 50, 100], 105.0

RUN.mkdir(parents=True)
air = subprocess.Popen([sys.executable, str(HERE / "air.py"), "--emulated", "--log", str(RUN / "air.jsonl")],
                       stdout=open(RUN / "air.out", "w"), stderr=subprocess.STDOUT)
time.sleep(1.0)
rx = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
rx.bind((tnet.LOCAL, tnet.DB_UDP_PORT))
ctl = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
ctl.connect((tnet.LOCAL, tnet.AIR_CTRL_PORT))
p = mav.MAVLink(None, srcSystem=255, srcComponent=190)
p.robust_parsing = True
lg = open(RUN / "listen.jsonl", "w", buffering=1)
t0 = time.time()
plan, params, src, offset, tb = list(PLAN), list(PARAM_AT), None, None, None
samples, att, arrivals, preq, preplies, sec = [], [], [], {}, [], dict(n=0, b=0, t=t0 + 1)
while (now := time.time()) < t0 + END:
    if select.select([rx], [], [], 0.02)[0]:
        d, src = rx.recvfrom(65535)
        t_rx = time.time()
        sec["b"] += len(d)
        arrivals.append(t_rx - t0)
        for m in p.parse_buffer(d) or []:
            if m.get_srcComponent() == 68 or m.get_type() == "BAD_DATA":
                continue
            sec["n"] += 1
            if m.get_type() == "ATTITUDE":
                tb = m.time_boot_ms / 1000.0
                offset = t_rx - tb if offset is None else min(offset, t_rx - tb)
                att.append((t_rx - t0, t_rx, tb))
            elif m.get_type() == "PARAM_VALUE":
                pid = m.param_id if isinstance(m.param_id, str) else m.param_id.decode()
                k = max((k for k in preq if k <= t_rx), default=None)
                preplies.append((round(t_rx - t0, 2), pid.strip("\x00"), None if k is None else round(t_rx - k, 3)))
                lg.write(json.dumps({"t": t_rx, "kind": "param_value", "id": pid, "value": m.param_value}) + "\n")
    rel = now - t0
    while plan and rel >= plan[0][0]:
        ctl.send((json.dumps(plan.pop(0)[1]) + "\n").encode())
    if params and rel >= params[0] and src:
        params.pop(0)
        rx.sendto(mav.MAVLink_param_request_read_message(1, 1, b"SYS_AUTOSTART", -1).pack(p), src)
        preq[time.time()] = 1
    if tb is not None and (not samples or rel - samples[-1][0] >= 0.1):
        samples.append((rel, now, tb))
        lg.write(json.dumps({"t": now, "kind": "age", "age_runmin": round(now - tb - offset, 3), "tb": tb}) + "\n")
    if now >= sec["t"]:
        age = now - tb - offset if tb is not None else float("nan")
        print(f"[{rel:5.1f}s] {sec['n']:4d} msg/s {sec['b']:5d} B/s ATTITUDE age(run-min) {age:5.2f} s", flush=True)
        sec.update(n=0, b=0, t=sec["t"] + 1)
air.send_signal(2)
air.wait(5)
A = [json.loads(x) for x in open(RUN / "air.jsonl") if '"kind": "air"' in x]
for r in A:
    r["rel"] = r["t"] - t0
# PX4 SIH's time_boot_ms runs slow vs the host clock (measured ~4 %), so a plain running min of
# (t_rx - tb) drifts. Skew-corrected gen_time: lower envelope a + (1+s)*tb fitted on unqueued phases.
UNQ = [(2, 15), (40, 45), (49, 65), (98, 105)]
bins = {}
for rel, t_rx, tb_ in att:
    if any(lo <= rel < hi for lo, hi in UNQ):
        k = int(rel)
        bins[k] = min(bins.get(k, (9e18, 0)), (t_rx - tb_, tb_))
ys, xs = [v[0] for v in bins.values()], [v[1] for v in bins.values()]
mx, my = stt.fmean(xs), stt.fmean(ys)
skew = sum((x - mx) * (y - my) for x, y in zip(xs, ys)) / sum((x - mx) ** 2 for x in xs)
a0 = min(t_rx - tb_ - skew * tb_ for rel, t_rx, tb_ in att if any(lo <= rel < hi for lo, hi in UNQ))
age_c = [(rel, now - (tb_ + a0 + skew * tb_)) for rel, now, tb_ in samples]
age_r = []
for rel, now, tb_ in samples:              # CONTRACT §2 as written: offset = min over the last 30 s
    o = min((t_rx - x for r2, t_rx, x in att if rel - 30 <= r2 <= rel), default=None)
    o = min(t_rx - x for r2, t_rx, x in att[:1]) if o is None else o
    age_r.append((rel, now - tb_ - o))


def win(lo, hi):
    ag, a30 = [a for r, a in age_c if lo <= r < hi], [a for r, a in age_r if lo <= r < hi]
    ar = [r for r in A if lo <= r["rel"] < hi]
    f = lambda k: round(stt.fmean(r[k] for r in ar)) if ar else None  # noqa: E731
    return dict(n_age=len(ag), age_mean=stt.fmean(ag), age_med=stt.median(ag), age_max=max(ag),
                age30_mean=stt.fmean(a30), n_air=len(ar), sent=f("sent_Bps"), off=f("offered_Bps"),
                q=f("q_bytes"), drops=(ar[-1]["drops"] - ar[0]["drops"]) if ar else None,
                C=sorted({str(r["C_Bps"]) for r in ar}))


def first(lo, hi, pred):
    return next((round(r - lo, 1) for r, a in age_c if lo <= r < hi and pred(a)), None)


gaps = [(b - a, a) for a, b in zip(arrivals, arrivals[1:]) if 44 <= a < 52]
res = {"unlimited 5-15 s": win(5, 15), "C=1600 steady 25-35 s": win(25, 35), "after C=null 40-45 s": win(40, 45),
       "blackout 45-48 s": win(45.5, 48), "post-blackout 49-55 s": win(49, 55),
       "step: unlimited 57-65 s": win(57, 65), "step: squeeze 75-95 s": win(75, 95),
       "step: after 98-105 s": win(98, 105)}
ev = {"skew_px4_slow_vs_host": round(skew / (1 + skew), 4), "n_attitude": len(att), "n_age_samples": len(samples),
      "C1600_rise_to_1.8s_s": first(15, 35, lambda x: x >= 1.8),
      "null_recover_below_0.2s_s": first(35, 45, lambda x: x < 0.2),
      "blackout_max_gap_s": round(max(gaps)[0], 2) if gaps else None,
      "blackout_gap_start_rel_s": round(max(gaps)[1], 2) if gaps else None,
      "blackout_recover_below_0.2s_s": first(48, 55, lambda x: x < 0.2),
      "step_rise_to_1.8s_from_profile_s": first(55, 95, lambda x: x >= 1.8),
      "step_recover_below_0.2s_from_95s_s": first(95, 105, lambda x: x < 0.2),
      "air_C_timeline": [(round(r["rel"], 1), r["C_Bps"], r["blackout"]) for r in A if 44 <= r["rel"] < 105],
      "param_replies(rel,id,latency)": preplies, "param_requests_at": PARAM_AT}
json.dump(dict(phases=res, events=ev), open(RUN / "summary.json", "w"), indent=1)
for k, v in res.items():
    print(f"{k:<24} " + " ".join(f"{a}={(round(b, 2) if isinstance(b, float) else b)}" for a, b in v.items()))
for k, v in ev.items():
    print(f"{k}: {v}")
print(f"logs: {RUN}")

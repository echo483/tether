# ground.py self-test — 2026-10-30 18:55–19:06 PDT (emulated chain)

Chain: PX4 SIH (VM) → `tools/air.py --emulated` (localhost:14601 → UDP localhost:14550) → `tools/ground.py`
→ QGC port 14560 (a test listener sat on 14560; QGC was not running) · uplink ground → localhost:14598 → air.py → PX4.
Harness: `tools/ground_selftest.py basic|manager RUN_DIR [SECS] [schedule-json]` (starts air.py + ground.py, drives the control ports, decodes what
reaches 14560). Real RF (`--serial`) was **not** exercised: the hardware was in use. Code path only.

## Clock finding (measured before writing the code)
PX4 SIH time runs slow vs the host: slope of 1 s ATTITUDE minima of (t_rx − time_boot_ms) = **+3.15 %** (20 s, n = 290
ATTITUDE); ground.py's live estimate read +3.3…+3.7 % across runs. A plain 30 s running-min offset would therefore lag
by ~30 × 0.033 ≈ 1 s and show as permanent qdelay (= constant false sheds). ground.py projects each sample in the 30 s
min forward by a measured skew r (lower-envelope fit of 1 s ATTITUDE minima, calm buckets only, 120 s; persisted in
`logs/live/ground-skew.json` as the next run's prior). Residual: baseline qdelay after a squeeze 0.01–0.06 s.

## 1. Baseline, manager off (`logs/gtest-basic`, n = 84 ticks after a 5 s settle, 5 Hz)
| metric | value |
|---|---|
| picture_age_s | median **0.058 s**, max 0.226 s |
| goodput_Bps | mean **2316 B/s** (census L = 2300) |
| loss | 0.0 · link `ok` 84/84 · qdelay median 0.020 s |
| rx_hz | T0 22 / T1 11 / T2 19 |
| first tick | `picture_age_s: null` (before the first ATTITUDE) |
| QGC port 14560 | 52 137 B in 23.6 s received by the listener; NAMED_VALUE_FLOAT PIC_AGE 42 + TIER 42 (= 2 Hz) |

## 2. Manager (`logs/gtest-mgr`, `--manager`, C_Bps 1600 at +10 s, null at +40 s; one run)
- Shed straight to T0 at **+2.4 s** after the squeeze (air ctl +9.7 → shed +12.1); one resend at +13.1 (T1/T2 rates had
  not fallen yet — the queued tail drains FIFO). picture_age peak 1.05 s, back **< 0.3 s at +16 s (≈ 6 s after the squeeze)**.
- cmd 511 works on PX4: after the shed, rx_hz T1 12 → 1, T2 20 → 0–1; restore T1 → 12–13 Hz within 1 s.
- Probe-up during the squeeze: restore T1 (+18.8), restore T2 (+21.8) → overload (T0+T1+T2 = 2300 > 1600) → re-shed (+23.9);
  ~12 s cycle, each costing ~1–2 s with picture > 1 s. After C → null: T1 +42.7, T2 +45.7, tier 0, goodput back to ~2300.
- QGC saw 9 STATUSTEXT from sysid 1 / compid 191: severity 4 "TETHER: link degraded - shed 2 tiers, 21 streams",
  severity 6 "TETHER: link recovered - restored tier 1" / "... tier 2".
- Live toggle (`logs/gtest-mgr2`): `{"manager": false}` → localhost:14597 at +29.7 → restore-all; picture_age climbed to
  1.95 s (K/C = 2.0 s) with loss 26 %. `{"manager": true}` at +37.7 → shed at +38.3, picture_age 0.53 s at +43, 0.034 s at +44.

## 3. sweep.py --launch + analyze.py (n = 2 pairs, C 1600 over [5, 23) s, 28 s arms)
`tools/sweep.py --launch --pairs 2 --c-lo 1600 --logs logs/ground-selftest2 --air-cmd "{py} {air_py} --emulated --log {dir}/air.jsonl --seed {seed}"`
→ SWEEP PASS 2/2; `tools/analyze.py logs/ground-selftest2` accepts the logs:

| arm | n | age p50 s | age p99 s | stale > 1 s | loss | goodput B/s |
|---|---|---|---|---|---|---|
| U0 | 2 | 1.92 ± 0.18 | 2.01 ± 0.34 | 78 ± 21 % | 15.3 % | 1646 |
| M | 2 | 0.41 ± 0.14 | 1.38 ± 0.56 | 20 ± 20 % | 0.0 % | 1529 |
| U0 − M | 2 | | | 58 ± 2 pp paired | | |

(n = 2, df = 1, t = 12.706: CIs are wide.) PREREG falsifier "M stale > 20 %" sits exactly on the line (20 %; 22 % and 19 %
per run). The second stale episode in each M arm is the probe-up restoring T2 at C = 1600 < L and re-shedding.
Also `logs/ground-selftest` (n = 1 pair): U0 79 % vs M 16 %.

## Known issues
- sweep prints `WARN streams still shed at the end` for M arms: the 28 s arm ends ~5 s after C returns, before probe-up
  finishes. The exit restore is **lost** under `--launch`, because sweep SIGINTs air.py at the same moment, so ground.py
  also resets every stream to the PX4 default (cmd 511 interval 0, twice, 1 s apart) on its first received frame, in both
  arms. Verified: U0-2 straight after M-1 starts with T2 at 22 Hz; `logs/gtest-reset` T2 0 → 17 Hz within 1.6 s.
- `link: blackout` = no frame for > 1.0 s (per brief), not "3 × baseline p99.9 inter-arrival" (CONTRACT §2).
- The exit STATUSTEXT reads "restored tier 2" when only T2 was still shed.

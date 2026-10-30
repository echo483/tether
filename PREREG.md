# PREREG — predictions committed before the sprint (do not edit after `git tag sprint-start`)

Source: `tools/qsim.py --c-lo 1600 --k-sec 2 --jump --boundary` → `notes/evidence/qsim-prereg.txt`.
Inputs: census of PX4 instance #5 (`notes/evidence/census-14561.json`, n = 60 s, 3340 datagrams):
L = 2300 B/s; tiers T0/T1/T2 = 889/519/893 B/s (tiers as in `qsim.DEFAULT_TIERS`).
Model: drop-tail byte queue K = 3200 B (2.0 s × C) drained at C; C steps 11520 → 1600 B/s at
t = 10 s, back at t = 40 s. Manager: shed straight to T0 when ATTITUDE queueing delay > 0.5 s for
0.6 s; restore one tier after < 0.1 s for 3 s. n = 10 seeds per arm; ± is the 95% t-interval.

| Arm | Picture age p50 | p99 | Time >1 s old (of squeeze) |
|---|---|---|---|
| U0 (no manager) | 2.10 ± 0.00 s | 2.24 ± 0.02 s | 90 ± 0 % |
| M (TETHER) | 0.10 ± 0.01 s | 1.10 ± 0.05 s | 4 ± 2 % |

**Arithmetic check:** stale level ≈ K/C = 2.0 s; fill ≈ K/(L−C) = 4.6 s; drain after shedding to T0
≈ K/(C − 889) = 4.5 s. **Boundary:** TETHER fails (picture > 1 s old for > 50 % of the squeeze) when
C < T0 load: predicted between C = 900 and 1000 B/s. The live boundary run uses C = 700 B/s.

**Falsifiers (any one = the prediction failed, and we say so):** U0 stale share < 70 %; M stale share
> 20 %; M holds at C = 700 B/s. Real-chain numbers go in a separate table from emulated ones.

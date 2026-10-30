# TETHER — interface contract (frozen at 17:10, edit only by agreement)

Two people build against this file and do not negotiate after it is frozen.
**A** = air.py + manager.py (systems). **B** = ground.py metrics, dash.py, copilot.py (instrument/AI).
Census-driven tier lists are filled from `notes/census.md`.

## 1. Port map (single host)
| Who | Binds | Talks to | Notes |
|---|---|---|---|
| PX4 SIH, GCS mavlink instance | its own | air.py `[IP_ADDRESS]:14550` | see notes/sitl.md for the exact instance |
| air.py (radio side) | serial `/dev/serial/by-path/…` | board 3 → board 1 UART | baud must equal DroneBridge's |
| air.py control | `[IP_ADDRESS]:14599/udp` | — | JSON lines in, see §4 |
| ground.py radio side | `wlp0s20f3`, ephemeral | DroneBridge `[IP_ADDRESS]:14550` | sends first (DroneBridge only talks to clients it has heard from) |
| ground.py GCS side | `[IP_ADDRESS]` ephemeral | QGC `[IP_ADDRESS]:14560` | QGC uplink comes back on the same socket and is forwarded up the radio |
| QGC | `14560/udp` | — | UDP + serial autoconnect **off** (never grabs 14550 or the tty) |

## 2. Logs — JSONL, one object per line, `logs/<run_id>/<proc>.jsonl`
`run_id` = `YYYYmmdd-HHMMSS-<arm>-<seed>`; arm ∈ `U0` (no manager) · `U1` (static rate) · `M` (TETHER).
All `t` are host `time.time()` seconds (single host → one clock). Every line has `t` and `kind`.

**air.py → `air.jsonl`** (ground truth; the manager must never read it)
```json
{"t":0.0,"kind":"air","C_Bps":4000,"K_bytes":12000,"offered_Bps":9100,"sent_Bps":4000,"q_bytes":11800,"drops":312,"seed":7}
```
1 Hz. `drops` cumulative whole datagrams.

**ground.py → `ground.jsonl`**
```json
{"t":0.0,"kind":"tick","picture_age_s":0.04,"aoi_s":{"ATTITUDE":0.04,"GLOBAL_POSITION_INT":0.11},"qdelay_s":0.01,"loss":0.0,"goodput_Bps":3900,"rx_hz":{"T0":24.0,"T1":10.0,"T2":0.0},"link":"ok","tier":2,"manager":true}
{"t":0.0,"kind":"event","what":"shed","tier":2,"reason":"qdelay>q_hi for 0.6s"}
{"t":0.0,"kind":"event","what":"cmd511","msg":"HIGHRES_IMU","interval_us":-1}
```
`tick` at 5 Hz. Definitions (B owns the code, these are the semantics):
- **picture_age_s** = AoI of ATTITUDE = `now − gen_time(latest ATTITUDE received)`.
- **gen_time** = `time_boot_ms/1000 + offset`, `offset = min over the last 30 s of (t_rx − time_boot_ms/1000)`.
  The clock offset cancels; no sync needed.
- **qdelay_s** = `(t_rx − time_boot_ms/1000) − offset` for the latest critical frame.
- **loss** = seq-gap loss per (sysid, compid) over the last 1 s. Not on raw `seq` alone (wraps).
- **link** = `ok` | `stale` (picture_age > 1.0 s) | `blackout` (no frame for > 3× baseline p99.9 inter-arrival).
- **tier** = how many tiers are currently shed (0 = all streams on).

## 3. Tiers — policy file `policy.json` (manager reloads on mtime change)
```json
{"name":"default","tiers":[["HEARTBEAT","ATTITUDE","GLOBAL_POSITION_INT","SYS_STATUS"],["…T1 from census…"],["…T2 bulk from census…"]],
 "q_hi_s":0.5,"q_lo_s":0.1,"T_detect_s":0.6,"T_restore_s":3.0}
```
Tier 0 is never shed. Shedding tier N = cmd 511 with `interval_us = -1` for each msg in it.
Restoring = `interval_us = 0` (PX4 default) and **verify the measured rate returns**.
Thresholds are derived from the measured baseline, not taste — fill from the census/baseline run.
copilot.py may write `policy.json`; it must pass `validate_policy()` (known msg names only, tier 0
must contain HEARTBEAT and ATTITUDE). If the copilot is offline, `default` stands.

## 4. air.py control port (demo hot keys and the sweep use the same door)
`{"C_Bps": 4000}` · `{"C_Bps": null}` (unlimited) · `{"profile":"step", "seed":7}` · `{"blackout_s": 3}`
The squeeze is synthetic, seeded, **time-indexed** (both arms see the same C(t)) — and disclosed on screen.

## 5. Uplink rule
The squeeze applies to the **downlink only** (PX4 → ground). The uplink is untouched — that is why a
ground-side manager can command PX4 over a degraded link. Never block on COMMAND_ACK; confirm by
the measured rate.

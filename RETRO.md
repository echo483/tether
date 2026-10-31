# TETHER — retro, metrics, and the full-system design

Night Hack (Founders, Inc., Fort Mason SF), Oct 30 2026. Two builders, 5-hour sprint + same-day prep.
Not presented — kept as a working, measured prototype. Everything below cites a log in this repo.

## 1. What exists
| Layer | Built | File |
|---|---|---|
| Vehicle | PX4 SIH quad (simulated), home = Fort Mason (37.8063, −122.4318) | `tools/guest_px4_sih.sh` |
| Link emulator | drop-tail byte queue K, token-bucket capacity C, blackout, seeded step profile, **capacity-vs-range model** | `tools/air.py` |
| Real RF hop | ESP32 DevKit + DroneBridge v2.4.1 AP; laptop WiFi → board 1 → UART TX → board 3 (held in reset) → laptop | `tools/air.py --radio-host`, `ground.py --serial` |
| Estimator | picture age (AoI) from PX4 `time_boot_ms` + running-min offset **with clock-drift correction**; seq-gap loss; goodput | `tools/ground.py` |
| Controller | tiered shedding via `MAV_CMD_SET_MESSAGE_INTERVAL` (cmd 511), hysteresis, probe-up restore | `tools/ground.py` (Manager) |
| Failsafe | **downlink-aware RTL**: all tiers shed + stale 3 s, or blackout 2 s → `MAV_CMD_NAV_RETURN_TO_LAUNCH` ×3 | `tools/ground.py --failsafe` |
| Operator I/O | STATUSTEXT + NAMED_VALUE_FLOAT into QGC; half-screen dashboard | `tools/ground.py`, `tools/dash.py` |
| AI | Claude: operator intent → schema-validated policy; post-flight incident report (never in the loop) | `tools/copilot.py` |
| Method | traffic census, queue-sim pre-registration, paired ABAB sweep + analysis | `tools/census.py`, `qsim.py`, `sweep.py`, `analyze.py` |

## 2. What we measured (method · instrument · n)
| Claim | Number | Source |
|---|---|---|
| Offered load (PX4 instance #5, Normal mode) | L = 2300 B/s; tiers T0/T1/T2 = 889/519/893 B/s | `notes/census.md`, 60 s, 3340 datagrams |
| cmd 511 lever works | ATTITUDE 14.75 → 0.92 → 14.75 Hz (ACK ACCEPTED) | `notes/T0-REPORT.md`, 12 s windows |
| Real 2.4 GHz hop carries PX4 at full rate | ATTITUDE 14.7 Hz, 176 frames / 12 s, laptop WiFi → ESP32 → UART → laptop | `logs/rfflip-185022.txt` |
| Emulated squeeze, single run | picture age 0.01 s → **1.91 s** (C = 1600 B/s, K = 3200 B; predicted K/C = 2.0 s) → **0.05 s** with TETHER → 2.89 s at C = 700 (TETHER fails, as predicted) | integration run 19:09 |
| **Paired sweep, emulated link** (C = 1600 B/s for 18 s of each 28 s arm, K = 3200 B) | picture > 1 s old **77 ± 1 %** of the squeeze unmanaged vs **15 ± 4 %** with TETHER; paired difference **63 pp, 95 % CI [59, 67]**; p50 age 1.92 → 0.39 s; p99 2.05 → 1.35 s | `notes/evidence/sweep-emu-n10-RESULTS.txt`, n = 10 pairs ABAB, t-CI df = 9 |
| Boundary (C = 700 B/s < critical set) | TETHER fails as predicted: level 4.39 s (pred. K/C = 4.57), onset 2.46 s (pred. 2.00), stale 89 % | same, n = 1 |
| Bay mission, TETHER on (emulated link, real PX4 flight) | shed at 275 m; RTL at **587 m**; max excursion **634 m**; landed home T+190 s | `notes/evidence/bay-on/` (n = 1) |
| Bay mission, TETHER off | blackout from 804 m; operator blind **104 s** (picture up to 50 s old); drifted to **995 m** before a blind manual RTL | `notes/evidence/bay-off/` (n = 1) |

### 2a. Pre-registration scorecard (PREREG.md, committed before the sprint)
| Prediction | Predicted | Observed (n = 10) | Verdict |
|---|---|---|---|
| Falsifier: unmanaged stale share < 70 % | not < 70 % (point 90 %) | 77 ± 1 % | **held** — point estimate high: the sweep's 18 s squeeze window makes the ~4.6 s fill a bigger share than the sim's 30 s |
| Falsifier: managed stale share > 20 % | not > 20 % (point 4 ± 2 %) | 15 ± 4 % | **held, but the point prediction missed ~4×** — probe-up restores a tier while C < L and re-sheds every ~12 s; the sim under-modelled detection latency |
| Boundary: TETHER fails below the critical set | fails at C < ~900–1000 B/s | fails at C = 700: level 4.39 vs 4.57 s, onset 2.46 vs 2.00 s | **held** |

Not yet claimed: real-RF sweep numbers (all n = 10 above are emulated link, real PX4 telemetry).

## 3. What broke, and the lesson
1. **Laptop → ESP32 UART direction never worked** (wire 1). Counter-based A/B/C/D tests (`t1_diag.py`) showed board 1's RX
   floating while the reverse direction decoded 100 %. Root cause not isolated in time (adapter RX0 path vs board 1 pin).
   **Lesson:** test each direction with the target's own counters; when one is dead, flip the topology instead of re-seating jumpers.
2. **One WiFi card.** Joining the device AP took the dev laptop — and the AI agents — offline. **Lesson:** the dev machine never
   joins the device network; use the second laptop or USB tethering.
3. **PX4 SIH clock runs ~3 % slow** → phantom queueing delay with a plain running-min offset; fixed with drift estimation.
4. **Probe-up oscillation:** restoring a tier while C < L refills the queue every ~12 s → managed stale share 20 % vs predicted 4 %
   (n = 2). Needs back-off (below).
5. Integration pitfalls: QGC claims every CP2102 as a SiK radio; port collisions (QGC vs SITL on 14560); `pkill -f` killing its
   own shell; a provider redacting IP literals in tool I/O.

## 4. If resources and time weren't the constraint — the full system
**Thesis:** in DDIL comms (denied, disrupted, intermittent, limited), the operator's *picture freshness* is the quantity to
control, and the downlink can die while the uplink survives. Autopilot failsafes watch the uplink. TETHER watches what arrives.

1. **Real radios, real capacity signal.** Replace the synthetic curve with RADIO_STATUS (`txbuf`, `rssi`, `remrssi`) from SiK /
   RFD900x, ELRS MAVLink mode, or IP mesh radios (Doodle Labs Mesh Rider, Silvus). Capacity = estimator fusing radio reports with
   measured goodput and AoI, not a constant.
2. **Shed at the source, latest-value-wins.** Move the queue discipline onboard (PX4 module in C++ over uORB, or a companion
   computer): per-class priority queues, *replace-not-append* for state messages so a full buffer holds fresh data. That attacks
   the drain-time term (Q / (C − L_T0)) that dominates recovery today.
3. **Controller with AIMD probe-up.** Additive increase / multiplicative decrease with exponential back-off after a failed probe;
   per-message rate scaling instead of all-or-nothing tiers.
4. **Failsafe inside the autopilot's state machine.** A "downlink quality" input to PX4 commander with configurable actions
   (loiter → RTL → land), hysteresis and latching; specify it as a state machine and model-check it (TLA+); symmetric
   uplink/downlink monitoring.
5. **Multi-bearer + security.** Bond RF + LTE/5G + SATCOM; route the critical set over the best bearer; MAVLink 2 signing and link
   encryption.
6. **Fleet scale.** Allocate shared capacity across N vehicles by mission priority (who gets the pipe) — the Lattice-shaped problem.
7. **Test like it flies.** HIL on the bench F411 + ELRS; programmable attenuators and walk tests; seeded scenario CI; ≥ 30 paired runs
   per claim with bootstrap CIs; pre-registered falsifiers.

## 5. Next steps (owned, KISS, in order)
| # | Step | Done when |
|---|---|---|
| 1 | AIMD back-off in the manager; re-run the n = 10 sweep | managed stale share ≤ prereg 4 % bound, or the miss explained |
| 2 | n ≥ 30 sweep on the real ESP32 hop | results table with CIs from real RF |
| 3 | Latest-value-wins air-side queue (Python first) | recovery time after shedding measured vs drop-tail |
| 4 | Port the estimator + controller to **C++** (MAVSDK or PX4 module), unit + property tests | same sweep numbers from the C++ build |
| 5 | Real radio: RFD900x/SiK pair or ELRS MAVLink on the bench F411 | RADIO_STATUS-driven capacity, attenuator test |

## 6. Resume (draft — fill numbers only from §2)
**TETHER — link-aware telemetry manager for PX4 drones** (Python, pymavlink, PX4 SITL, ESP32/DroneBridge, QGroundControl, Claude API)
- Measured operator picture staleness (age of information) from received MAVLink timestamps — no clock sync, drift-corrected — and
  shed telemetry by priority with MAVLink's own `SET_MESSAGE_INTERVAL`, zero autopilot changes; under emulated capacity collapse the
  operator's picture was > 1 s stale 15 % of the time vs 77 % unmanaged (10 paired runs, difference 63 pp, 95 % CI 59–67).
- Designed a downlink-aware Return-to-Launch failsafe: in a range-limited Fort Mason → SF Bay mission the vehicle turned home at
  587 m (max 634 m); without it the operator was blind for 104 s and the vehicle drifted to 995 m (simulated vehicle, n = 1 each).
- Brought up a 2.4 GHz ESP32 MAVLink link in a 5-hour hackathon; isolated a dead UART direction with counter-based differential
  tests and re-routed telemetry through the working path.

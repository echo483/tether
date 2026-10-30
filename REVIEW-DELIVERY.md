# TETHER: delivery review (risk, timeline, work blocks)

Reviewer brief: delivery lead. Written 2026-10-29. Based on `SPEC.md` v1.0 and `SETUP-TONIGHT.md`.
The reviewer had no internet access. Anything about DroneBridge, PX4 or QGC internals marked
**[verify]** comes from memory, not from a source.

---

## 0. The verdict in five lines

1. **The headline experiment as written won't show anything.** With i.i.d. loss and delay,
   rate adaptation can't change per-message delivery. A simulation gives managed **0.809** vs
   unmanaged **0.800** critical-set delivery at 20 % loss (§A.1). T3's "≥2×" can't be reached
   with that fault model. Rate adaptation only matters on a **capacity-limited** link. Change
   the headline fault profile to **capacity collapse** with a bounded queue.
2. **The manager can't see the faults you inject.** `RADIO_STATUS` reports real RF. At 1 m on a
   table it will say the link is perfect all night, whatever the injector does. A transport
   layer needs **two endpoints**. Add a TETHER ground agent that sends delivery reports back
   over the degraded uplink.
3. **Cut failover now. Redefine store-and-forward.** Failover needs a two-interface GCS, a
   ground-side merge and a third DroneBridge board, and the third board is already your
   USB-UART adapter. Replaying stale state telemetry into a link that is just recovering
   contradicts your own prioritisation thesis.
4. **Run the measurement on one host with one clock.** The host's WiFi joins the DroneBridge AP
   and runs the ground agent, and QGC runs on the host too. That gives true one-way latency and
   exact delivery (packets joined by hash). Device 2 is optional decoration.
5. **Ask for one wiring exception tonight.** It is a two-jumper, zero-flash loopback test that
   decides whether you need a Micro Center run tomorrow (§B, tonight block T+70).

---

## (a) What fails, ranked, and when

| # | Risk | Mechanism | When it fires | Likelihood | Fix / fallback |
|---|---|---|---|---|---|
| **1 — HIGHEST** | **T3 null result** | i.i.d. loss/delay hits every message the same way whatever the rate, so managed ≈ unmanaged. RADIO_STATUS is blind to software faults. There is no ground endpoint, so nothing tells the manager what was delivered. | **7:30–8:30 pm**, the worst possible moment. Found while tuning, with no time left to redesign. | Near-certain if built as specced | Tonight: capacity-collapse profile, critical-set metric, ground agent with uplink reports. Tomorrow: pre-register the prediction from the sim plus the measured census. |
| 2 | Serial bridge into the DroneBridge FC UART | Adapter (none owned), classic-ESP32 pin map, baud, DroneBridge UART config, TX/RX swap | Tomorrow M+0:30–2:30 | Moderate–high | CP2102-in-reset trick (§B). Pins from the research notes. Store decision by M+0:15. Emulated link is always the fallback. |
| 3 | Guest→host MAVLink, no return path | PX4's GCS instance sends to localhost by default. **[verify]** PX4 may only talk to a UDP peer it has heard from. Under passt the host can't initiate without a forward, so neither side starts. | Tonight T+10–50 | Moderate | Explicit target on the instance (`mavlink start … -t <gateway> -o 14550` or the param equivalent). Fallback: a passt UDP `portForward` and restart. |
| 4 | Manager "does nothing" | `SET_MESSAGE_INTERVAL` only changes the mavlink instance that **received** it. Sent from a separate socket (e.g. 14540 onboard), it throttles the wrong stream. Two other things can also fight the manager. QGC may request its own rates. **[verify]** PX4 also throttles itself from RADIO_STATUS `txbuf` (SiK flow control). | Sprint 5:10–6:10 | Moderate | Tonight's probe: send cmd 511 *through the shuttle's own socket* and measure the rate change. Watch the uplink for QGC's cmd 511 / REQUEST_DATA_STREAM. |
| 5 | Sweep wall-clock | 30 pairs × 2 arms × (30 s run + 5 s reset) = **35 min**. 45 s runs make it 50 min. It is real time because SITL is real time. | 7:40–8:30 pm | High if started late | One headline profile only. Start by 7:50 or drop to n=10. Run it unattended with `systemd-inhibit`. |
| 6 | Venue 2.4 GHz and host networking | 120 teams' worth of RF. NetworkManager leaves the AP because it has no internet and joins a remembered network. The laptop sleeps mid-sweep. Brownout resets on thin cables. | 4:15–9:30 pm | Moderate | Channel scan at 4:15. Pin AP autoconnect priority and disable the other saved networks. `systemd-inhibit`. Interleave arms ABAB. Short, known-good cables. |
| 7 | Environment papercuts | Not in `dialout`, with no passwordless sudo. QGC AppImage needs libfuse2 on Debian 13 (use `--appimage-extract`). Gazebo is heavy (use SIH). Charge-only cables. `/dev/ttyUSB*` renumbers on replug. Cheap CP2102s often share serial `0001`, so `by-id` paths collide; use `/dev/serial/by-path/`. Laptop may only have USB-C ports. ModemManager probes new ttys. | Tonight / M+0:00 | High that at least one bites | Tonight's checks (§B). Bring a hub. |
| 8 | Prep-vs-sprint challenge at judging | "The injector skeleton" in morning prep is part of what you claim as owned work. Judges score sprint work only. | 10 pm | Low–moderate, high cost | Fault models get built in the sprint. Git tag `sprint-start` at 5:00. A disclosure card on the table. |
| 9 | Cold start at the venue | VM boot, AP join, port map, QGC: easily 30+ min unrehearsed | 4:15–5:00 | Moderate | Timed cold-start rehearsal tomorrow, target ≤15 min, from a written RUNBOOK. |
| 10 | Unrehearsed demo / fatigue | Five hours after a four-hour morning | 10 pm | Moderate | Freeze at 8:50. Three rehearsals. Fallback video recorded by 9:15. |
| 0 | Hardware review | Disqualifying if missing | Tonight | Low **if done first** | Minute 0 tonight. Template in §E. |

**Single highest risk: #1.** It is the only failure with no fallback. A dead radio degrades to the
emulated link with the same code and the same numbers. An experiment that can't separate the
arms leaves the project with no headline, however well everything else works. It is also the
cheapest to fix, because it is all design and no code.

---

## (b) Work-block plan

Owners: **A = systems/radio** (hardware, DroneBridge, serial, SITL, PX4-side actuation,
manager). **B = instrument/analysis** (logging, ground agent, injector, sweep, stats,
dashboard). The contract between A and B is the log schema, the report message, the shuttle
hook and the port map (§D).

### Tonight: 90 min. No flashing. One optional jumper.

| T+ | A | B | Deliverable | Done when |
|---|---|---|---|---|
| 0–10 | **Hardware review**: draft it (§E) | Count laptop ports (USB-A/C), hub, cables; send the review | Submission sent; screenshot saved | Confirmation saved on both phones |
| 10–50 | VM up, SITL **SIH** (not Gazebo) running. Point the GCS instance at the host gateway. Host listener sees HEARTBEAT. **Return-path probe**: from the host, through the *same* socket, send cmd 511 to slow ATTITUDE to 1 Hz. | `id` shows `dialout` (if not: `sudo usermod -aG dialout $USER`, re-login, tonight). `esptool chip_id` on **all 3 boards × every cable**. Record MAC, flash size, module marking (WROOM vs WROVER, which decides GPIO16/17). Label boards 1/2/3 and cables "data OK". | `notes/sitl.md` with the exact commands. `notes/boards.md`. | COMMAND_ACK = ACCEPTED **and** the measured ATTITUDE rate drops to ~1 Hz. 3/3 boards answer. |
| 30–60 | — | uv repo + `pymavlink pyserial esptool` | venv | `import pymavlink, serial` OK |
| 50–70 | **Offered-load census**: 60 s capture; per msgid Hz, bytes/s, packet size. Also the critical-set subtotal. | **DroneBridge research** → `notes/dronebridge.md`, each answer with source URL or "unknown": classic-ESP32 binary + version + flash offsets; FC UART GPIOs and whether they are configurable; baud options; UDP addressing in AP mode (broadcast / per-station / multi-client / ports); does it emit RADIO_STATUS in AP mode, and **in which direction**; channel and TX-power settings; AP password change; is AES-GCM ESP-NOW-only **[verify]** | `notes/census.md` + raw log | L and L_crit known with n = 60 s. Every research question answered or marked unknown. |
| 60–75 | — | QGC: `--appimage-extract`, run, connect to SITL without radios. **Cut first if late**; it takes 10 min tomorrow. | — | Vehicle visible in QGC |
| 70–75 | *Optional exception.* Board #3: jumper **EN→GND** and **TX0↔RX0**, open its tty, type, see the echo. No flash. | — | Adapter route proven or disproven | Echo seen, or a store run is booked for tomorrow |
| 75–90 | **Decision block, both.** Write `DECISIONS.md`: topology (single host); headline profile (capacity collapse); metric definitions (§D); baud (≥1.5× the census peak); adapter route / store run; cuts (failover, ESP-NOW). Shut the VM down. **Sleep.** | | `DECISIONS.md` | Every open item in SPEC §7.5 / §11 / §12 is closed or cut |

If tonight overruns, cut in this order: QGC → census (move to M+0) → research. **Never cut**
the review, the dialout/chip_id check, or the return-path + cmd 511 probe.

### Tomorrow morning: 4 h, all substrate. Example times 08:00–12:00.

| M+ | A | B | Deliverable | Done when |
|---|---|---|---|---|
| 0:00–0:15 | Adapter loopback test (if not done tonight) | — | Go/no-go on the store run | Decided by M+0:15. If the store is needed, **B goes**: 2× 3.3 V USB-TTL (CP2102/FT232/CH340), 2 data cables, a hub. Abort the trip if it runs past 75 min. |
| 0:15–1:15 | Flash prebuilt DroneBridge on board #1 (esptool CLI). Configure AP mode, channel, **a new AP password and web password**, FC UART GPIOs, baud, MAVLink mode, low TX power. Host joins the AP. Pin the AP's NM autoconnect priority. | `link.py`: UDP↔serial and UDP↔UDP (emulated) behind one interface. Explicit bounded queues with drop counters. Null `Hook`. `log.py` JSONL schema. `ground.py`: receive, log, forward to QGC. | Flashed, configured board. Plumbing. | Config survives a power-cycle. On the emulated path, SITL→ground→QGC with 0 unaccounted drops over 5 min (report n). |
| 1:15–2:15 | Wire adapter→board #1: **GND, TX, RX only**. Raw byte test (a canned HEARTBEAT in, UDP out), then full chain: SITL → shuttle → RF → ground → QGC. **GATE T1.** | `CONTRACT.md` (§D). `PREREG.md`: headline profile parameters, plus **predicted** delivery/latency per arm from the census fed through the queue sim. Committed before 5 pm. | T1. Pre-registration. | QGC shows the vehicle over RF and a round-trip command (arm or param read) succeeds. |
| 2:15–2:45 | **RF baseline**, both: 5 min unmanaged, no faults. Delivery, one-way latency p50/p99/max, RADIO_STATUS present (y/n). | | `notes/baseline-rf.md` with method, instrument, n, CI, raw log, date | Numbers exist. Confirms the RF path doesn't constrain at the chosen baud. |
| 2:45–3:30 | **Cold-start rehearsal**, both. Power everything off, follow `RUNBOOK.md`, time it. Then go offline (internet off) and re-run the chain. VM snapshot, `git tag prep-end`. | | RUNBOOK + snapshot + tag | Cold start ≤15 min with no internet |
| 3:30–4:00 | Pack from the checklist (§E). Charge everything. **Stop.** | | | Bag packed |

**Morning cut:** if there is no T1 by **M+2:45**, stop radio work. The emulated link becomes
primary. The radio gets one retry at the venue, 4:15–5:00, from the RUNBOOK only.

### Sprint: 5:00–10:00 pm

4:15–5:00 is setup, not build: cold start, `nmcli dev wifi list` channel scan, set the
DroneBridge channel, re-check T1 in venue RF, record a 2-min venue baseline.

| Time | A | B | Gate / done |
|---|---|---|---|
| 5:00–5:10 | Both: `git tag sprint-start`, read the cut table aloud, confirm the contract | | — |
| 5:10–6:10 | **Manager v0.** Actuator: cmd 511 on the shuttle's own SITL socket, with ACK check. FULL / CRITICAL tables from the census. Manual toggle. Offered-load meter. | **`inject.py`**: seeded, time-scheduled profiles (capacity + drop-tail queue, blackout, loss, delay) in the hook. **Ground reports**: 5 Hz `DEBUG_VECT` (rx B/s, rx pkt/s, gap estimate) on the uplink, plus a 1 Hz GCS HEARTBEAT so the sweep runs without QGC. | A: the toggle takes offered load to L_crit ±10 % and restores to L ±10 %. B: same seed gives an identical fault schedule, and unmanaged delivery under the cap matches PREREG ±5 pp. |
| 6:10–6:25 | **GATE T2**, both, emulated link | | Unmanaged degrades as predicted |
| 6:25–7:25 | **Closed loop.** Estimator: delivered/offered over W = 1 s from reports. Hysteresis. **Probe-up recovery** (without probing it stays shed forever). Thresholds derived from the measured W, report period and queue size. | **`analyze.py` + `sweep.py`.** Join by hash. Per-run metrics 1–4 from one run shape. Paired ABAB order. Per-run precondition check (offered load at baseline before the fault). Bootstrap CI over runs. Table with method/instrument/n/CI/log/date. | A: auto detect, shed, recover on emulated, then 1 paired run on RF. B: 3-pair dry run produces the table. |
| 7:25–7:40 | **GATE T3**: one paired run on the RF path. Pick the sweep path. | | Managed ≥ the pre-registered ratio |
| 7:40–8:20 | Sweep runs **unattended** on the rig (`systemd-inhibit`). **Nobody touches laptop 1.** A builds the dashboard on laptop 2, reading copies of the live JSONL. | Predict the boundary run (C < L_crit) from census + sim. Write the RESULTS.md skeleton. | n = 30 pairs done by 8:20 |
| 8:20–8:50 | Boundary run (predicted failure, then confirmed). Stretch: latest-value-wins on blackout recovery. | Final table, one plot | **8:50 HARD FREEZE** |
| 8:50–9:15 | Record the fallback video, both: screen capture plus phone video of the boards | | Video on both laptops |
| 9:15–9:45 | Rehearse ×3, both, including the failure run and a **radio-pull drill** (switch to emulated in <30 s) | | 2:00 ±15 s |
| 9:45–10:00 | Reset the rig to its demo start state. All gear on the table. **Nobody leaves** (no re-entry). | | — |

Run shape: 5 s nominal | 15 s capacity collapse | 10 s recovered, then a 5 s reset. Each run
yields metric 1 (delivery), 2 (latency, thousands of packets), 3 (time to detect) and 4 (time to
recover) at once. 30 pairs take 35 min.

---

## (c) Cut lines and the minimum viable winner

| Clock | Condition | Action | What you still have |
|---|---|---|---|
| **Tonight** | — | **Cut** failover, ESP-NOW mode, backlog store-and-forward | Everything below |
| M+2:45 | No T1 | Emulated link primary. One retry at venue setup. | T0, T2, T3 on emulated |
| 5:00 | T1 doesn't reproduce at the venue | Emulated from minute 0. Boards on the table, labelled honestly. | Same |
| 6:25 | T2 fails | B fixes the injector, 6:45 latest. A carries on with the manual toggle. | — |
| 7:25 | Closed loop not working | Ship an **operator-triggered** managed arm. Drop metric 3 and say so. | Managed vs unmanaged delivery, n=30 |
| 7:40 | RF path flaky | Sweep on emulated, labelled | Full table |
| 7:50 | Sweep not started | n = 10 pairs (12 min); report n = 10 with its wider CI | Honest smaller table |
| 8:20 | Sweep unfinished | Stop it; report the n achieved | — |
| **8:50** | Anything | **Freeze code** | — |
| 9:15 | Live chain unstable | Demo the fallback video plus a live emulated run | — |

**Minimum viable winner:** real PX4 → TETHER air agent → real ESP32/DroneBridge radio →
TETHER ground agent → QGC. One capacity-collapse profile. Managed vs unmanaged **critical-set
delivery and p99 latency**, n = 30 paired runs, 95 % CI, raw logs. The prediction is
pre-registered before 5 pm and confirmed live. One boundary run fails exactly where predicted.
The same thing on the emulated link counts as the floor.

That isn't guaranteed to beat 120 teams. It is the strongest thing this hardware can honestly
show in five hours, and very few tables will show a falsifiable prediction.

---

## (d) Over-scoped / under-scoped

**Over-scoped**
- Five features plus an instrument plus six metrics at mixed n, in 5 h. Collapse it to one
  paired experiment that yields metrics 1–4. Drop 5 (failover). Do 6 only if the blackout
  stretch happens.
- Several fault profiles at n = 30 each. Run one headline profile; anything else gets an n = 5
  smoke run or nothing.
- Failover: two-interface GCS, ground merge, a third radio. **[verify]** QGC already handles
  multiple links to one vehicle, so the novelty is weak.
- A second radio mode (ESP-NOW). The third board is the adapter.
- Store-and-forward of state telemetry. The right policy is latest-value-wins for state, with
  queuing only for events (STATUSTEXT, COMMAND_ACK). QGC's comm-lost indication is driven by
  missing heartbeats at the ground, so air-side buffering can't prevent it during a blackout.
- Pitch claims: "a $7 radio that behaves like a dramatically more expensive link", "1 km",
  "150 m". None of these are measured by you. Say only what the table says.

**Under-scoped (missing from the spec)**
- The **ground endpoint** and the **feedback path**: report format, rate, and the fact that
  feedback travels over the degraded uplink.
- **Metric definitions**: delivery of *what*? Managed deliberately sends less. Use critical-set
  delivery and critical-message latency/age. The unit of analysis is the run, not the packet.
- **The offered-load census.** Without L and L_crit you can't set C, predict anything, or pick
  a baud.
- **Baud choice.** 57600 baud is 5.76 KB/s and 115200 is 11.52 KB/s. If SITL offers more than
  that, the "unmanaged" baseline is broken before any fault. Put the bottleneck in the injector,
  where you can script it, not in the UART.
- **The prediction formula.** The fluid estimate C/L is wrong for small messages under
  byte-limited drop-tail: the sim gives 0.437 against a C/L of 0.18 (§A.2). Predict from the sim
  with census input, never from the formula.
- **Confounds**: PX4's own RADIO_STATUS throttling **[verify]**; QGC rate requests and param
  reloads on reconnect. The sweep runs headless, without QGC. Arms must be interleaved because
  venue RF changes over the evening.
- **Instrument isolation**: the manager must not import or read injector state.
- **Every drop point explicit and counted.** A pyserial write blocks, and then the kernel
  silently drops UDP. Any loss you can't account for is a harness bug.
- Cold-start RUNBOOK, offline operation, laptop sleep, NM autoconnect, USB ports and hub.
- Rehearsal time and the fallback video (absent from the spec timeline).
- The prep/sprint audit trail.

**Premises that are wrong or unverified**
- "≥2× delivery under 20 % loss + 200 ms": false (§A.1).
- "RADIO_STATUS is our link-state input": only real RF; keep it as a logged secondary signal.
  **[verify]** whether DroneBridge emits it in AP mode at all.
- "REAL: packet loss": in the measurements, loss is injected at the serial boundary. Say that.
- "REAL: encryption (AES-GCM-256)": **[verify]**. Likely ESP-NOW-only; WiFi AP mode is WPA2.
- Demo step 2, "QGC stutters and drops" at 20 %/200 ms: QGC will probably stay connected. Under
  capacity collapse it visibly lags. Predict what it will look like, then rehearse it.
- "Third V1 as passthrough, ~20 lines, zero purchases": the 20 lines need an ESP32 toolchain you
  haven't installed. The CP2102-in-reset trick needs no firmware.
- "NAT mapping keeps itself alive": plausible, but only if PX4 sends unsolicited. Tonight's probe
  settles it.
- Novelty: **[verify]** PX4 and ArduPilot already throttle streams from RADIO_STATUS `txbuf`. Your
  new parts are end-to-end feedback, priority-aware shedding, and the seeded, published
  benchmark. Lead with the benchmark.

---

## (e) Safety, legal, venue

- **Hardware review (tonight, first).** Declare: 2–3 ESP32 dev boards, USB-powered from laptops;
  2.4 GHz WiFi AP (one SSID, low TX power, certified modules, unmodified antennas); **no**
  batteries except laptops, **no** LiPo, motors, props, airframe or flight; no soldering, no
  fabrication. Power: 2 laptops plus a declared power strip. **Ask explicitly whether a private
  2.4 GHz AP is permitted.** Some venues ban them; ESP-NOW doesn't fix that, because its ground
  side still needs an AP. Keep the confirmation.
- **RF legality (FCC Part 15).** Unmodified certified modules at default or lower power are fine.
  Check the module can shows an FCC ID; clones exist. **Never** jam, deauth, spoof SSIDs or
  sniff others' traffic. Jamming is illegal outright (47 U.S.C. §333) and is an instant
  ejection. The "contested spectrum" pitch is demonstrated **only** by the software injector. If
  a judge asks you to jam it, the answer is "no, which is why the instrument exists." Passive
  attenuation (a metal tin over the board) is the only physical degradation allowed.
- **Network hygiene.** Never join or bridge the venue network. The host's WiFi sits on your AP,
  so it is offline, which is what you want. Give the SSID an obvious team name.
- **Change the default AP and web passwords.** A room full of hackers, a default-password AP,
  and an unauthenticated MAVLink path into your autopilot is a demo someone else can end for you.
- **Electrical.** USB power only. Connect **GND, TX, RX only** between boards. Never tie VIN/5V
  or 3V3 between two USB-powered boards. Logic is 3.3 V. Boards sit on a non-conductive surface,
  never on an aluminium laptop. Tape the boards and cables down; no loose jumpers near VIN. Route
  cables away from walkways.
- **No airframe, props or LiPo on site**, not even as decoration. It invites a safety re-review.
- **Judged-work integrity.** Tag `sprint-start`. Put a disclosure card on the table: "Built
  before 5 pm: VM, PX4 build, shuttle/logging plumbing, DroneBridge flash, pre-registration.
  Built 5–10 pm: injector, manager, ground reports, sweep, results." Undisclosed prep is the
  realistic way to get disqualified.
- **Attribution.** DroneBridge (Apache-2.0), PX4 (BSD-3), QGC: credit them on screen and in the
  README.
- **Framing.** Civilian-equivalent claims only. No "tactical", "military-grade" or range claims
  you haven't measured.
- **No re-entry after 10 pm.** Chargers, hub, power strip and cables are on the table by 9:45.

---

## (f) Do NOT

1. Build failover, "just a quick version". Not tonight, not at 8:20.
2. Rebuild PX4 anywhere, or upgrade anything (apt, uv, QGC, DroneBridge) after the morning
   cold-start passes.
3. Install an ESP32 toolchain or write ESP32 firmware. Flash prebuilt DroneBridge only.
4. Put USB passthrough or serial into the VM.
5. Let the manager read injector state.
6. Run all unmanaged runs and then all managed runs. Interleave ABAB.
7. Debug the radio during the sprint after 6:30. Switch to emulated and move on.
8. `pip install` anything at the venue, or depend on the internet at all.
9. Call injected loss "real packet loss", or quote DroneBridge's range figures as your own.
10. Change code after 8:50.
11. Touch laptop 1 while the sweep runs.
12. Leave the room after 9:45.
13. Jam, deauth, sniff, or join the venue network.
14. Bring LiPo, props or an airframe.

---

## Appendix A: arithmetic (run 2026-10-29, Python stdlib, discrete-event drop-tail sim)

The stream mix here is **illustrative** (L = 16.6 KB/s, L_crit = 1.26 KB/s). Replace it with
tonight's census before quoting any prediction.

**A.1 Spec profile: 20 % i.i.d. loss, no capacity limit, 60 s:**
unmanaged critical delivery **0.800**, managed **0.809**. No separation.

**A.2 Capacity collapse, drop-tail queue = 0.5 s × C, steady state:**

| C | fluid C/L | sim unmanaged crit | sim managed crit | managed p99 |
|---|---|---|---|---|
| 3.0 KB/s | 0.18 | 0.437 (p99 498 ms) | 1.000 | 15 ms |
| 1.5 KB/s | 0.09 | 0.224 | 1.000 | 59 ms |
| 1.0 KB/s | 0.06 | 0.188 | **0.800** | 479 ms |
| 0.6 KB/s | 0.04 | 0.062 | **0.472** | 457 ms |

The last two rows are the **boundary run**: once C falls below L_crit, managed fails as
predicted. The fluid formula also underestimates unmanaged delivery of small packets by 2–2.5×.
Predict with the sim. Over a 15 s collapse with a ~1.5 s detection transient, the illustrative
ratio is ~2.2× at C = 3 KB/s and ~4× at C = 1.5 KB/s. Choose C for clear separation and
pre-register it.

**A.3 Why heartbeats alone can't be the estimator:** at a true 80 % delivery, the 1 Hz
heartbeat Wilson 95 % CI is [0.49, 0.94] over 10 s and [0.63, 0.90] over 30 s. Detection would
take tens of seconds. Count all packets at the ground and report them back.

**A.4 Serial ceilings (8N1):** 57600 → 5.76 KB/s · 115200 → 11.52 · 230400 → 23.04 ·
460800 → 46.08 · 921600 → 92.16. **[verify]** DroneBridge's baud options.

**A.5 Sweep time:** 30 pairs: 35 min at 30+5 s, 50 min at 45+5 s, 70 min at 60+10 s.

---

## Appendix B: the zero-firmware USB-UART (board #3)

Holding the ESP32 in reset (EN tied to GND) releases its UART0 pins. The on-board CP2102 is then
reachable on the header. **[verify with the loopback]**
- Header **TX0** (GPIO1) goes to the CP2102's RXD. Connect the **foreign TX** here (straight
  through, not crossed).
- Header **RX0** (GPIO3) goes to the CP2102's TXD. Connect the **foreign RX** here.
- Common GND. Nothing else. Never connect VIN/3V3.
- Test: jumper TX0↔RX0 with EN→GND, open the tty, and typed bytes should echo back.

Fallbacks, in order: buy a 3.3 V USB-TTL adapter; MicroPython passthrough (flash one binary
with esptool; needs `kbd_intr(-1)` and raw stdio, fiddly with binary MAVLink); Arduino sketch
(needs a toolchain, last resort).

---

## Appendix C: the interface contract (freeze in the morning, confirm at 5:00)

1. **Packet log (JSONL):** `t_ns` (host CLOCK_MONOTONIC), `node` ∈ {air_in, inj_out, gnd_rx,
   gnd_tx, air_rx}, `dir` ∈ {down, up}, `msgid`, `sysid`, `compid`, `seq`, `len`, `h`
   (8-byte blake2b of the raw frame). Delivery and latency come from joining `air_in` with
   `gnd_rx` on `h`.
2. **Run manifest:** `run_id, arm, profile, seed, t_start, t_fault_on, t_fault_off, t_end,
   precondition_ok, git_sha`. Runs that fail the precondition are reported, never silently
   dropped.
3. **Ground report:** `DEBUG_VECT` (msg 250) at 5 Hz, name `TT_LINK`, x = rx B/s, y = rx pkt/s,
   z = gap estimate, sent on the uplink. The shuttle consumes it and doesn't forward it to SITL.
4. **Hook:** `process(dir, frame, t_ns) -> list[(release_t_ns, frame)]`. Only the injector
   implements it.
5. **Manager inputs allowed:** the pre-injector SITL stream, ground reports from the uplink,
   DroneBridge RADIO_STATUS (logged only). **Forbidden:** injector internals. The manager uses
   its own sysid/compid and filters its own COMMAND_ACKs.
6. **Port map:** SITL GCS instance local/remote, shuttle, ground agent, QGC (manual UDP link,
   autoconnect off to avoid a 14550 clash). Write the actual numbers once tonight's probe works.

---

## Appendix D: revised demo run sheet (~2 min)

| t | Run | What it proves |
|---|---|---|
| 0:00–0:20 | QGC shows PX4 through the ESP32 radio. Dashboard shows L and C. | Real autopilot, real radio, real GCS |
| 0:20–0:50 | Capacity collapses to C; TETHER off. "Prediction: X % critical delivery." QGC attitude lags. | The unmanaged failure, predicted |
| 0:50–1:20 | Same profile and seed; TETHER on. It detects in ~1 s, sheds, and holds Y %. | The mechanism doing visible work |
| 1:20–1:40 | C < L_crit. "Prediction: managed fails at Z %." It does. | The boundary |
| 1:40–2:00 | Table: n = 30 paired runs, CI, raw log path, date. Close: "Your drone's data should degrade, not disappear, and here's the measured curve." | The result |

## Appendix E: pack list

Laptops ×2 with chargers; power strip (declared); USB hub; 3 boards (labelled); ≥4 tested
data cables, including spare USB-C↔micro-USB if the laptop is C-only; jumper wires (F-F) plus
spares; tape; a non-conductive mat; the disclosure card; a printed RUNBOOK; the
hardware-review confirmation; the fallback video on both laptops and a USB stick.

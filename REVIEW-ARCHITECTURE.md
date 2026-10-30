# TETHER: adversarial review of the architecture and comms design

Reviewed 2026-10-29 against `SPEC.md` v1.0 and `SETUP-TONIGHT.md`. No internet was used.

Each claim is tagged:
**[F]** checked on this host tonight · **[A]** arithmetic, script output quoted · **[K]** from memory, confidence stated · **[U]** uncertain, with the check that settles it.

---

## P0: wrong as written. Fix before the sprint.

### 1. T3 cannot pass under the demo's own profile, and the demo's failure will not show
- **Loss that is iid does not depend on load.** At 20% Bernoulli loss the unmanaged delivery ratio is 0.80, so "≥2×" means 1.60, which is impossible. Shedding streams does not change the loss probability of the frames that remain. **[A]**
- **QGC will not "fall apart".** Heartbeats arrive at 1 Hz, and a comm-lost needs 3–4 of them lost in a row. At p=0.2 that predicts 0.15–0.77 comm-lost events in a 2-minute demo **[A]**. The exact QGC timeout is **[U]**, so both k=3 and k=4 are shown. Losing 20% of a 50 Hz attitude stream is invisible, and a fixed 200 ms delay is invisible too.
- **Mechanism:** rate shedding only helps when the damage is caused by *offered load L > capacity C*. So the injector's main impairment has to be a **capacity limit**: a token bucket at C B/s, a drop-tail queue of K bytes, and C varying over time. Bursty Gilbert-Elliott loss and blackouts are secondary impairments. Unmanaged steady state: queue delay = K/C, loss = 1−C/L.
  Illustrative, with L=20 KB/s (the real L is unmeasured): C=5.76 KB/s and K=64 KiB give **11.4 s stale telemetry and 71% loss** **[A]**. That is what "falls apart" actually looks like, and shedding fixes it exactly when L_crit < C.
- **Rewrite T3:** step C from C_hi to C_lo, with L_crit < C_lo < L_total. Pass if TETHER keeps the critical-set AoI p99 < X ms while unmanaged exceeds Y s. n=30 paired runs. Derive X and Y from measured K, C and L.

### 2. The estimator's input cannot see the faults the instrument injects
- RADIO_STATUS reports the radio's own state. At 1 m on a table, RSSI stays pinned high, and software-injected faults never move it. The manager as specified would never detect an injected fault.
- RADIO_STATUS has no timing fields, so "one-way delay, jitter" cannot come from it. `rxerrors`, `fixed` and `noise` have SiK semantics, and DroneBridge may zero-fill them **[U: log it for 60 s tomorrow]**.
- **Replace it with estimation from the telemetry itself, at the receiver:**
  - **Queueing delay** by delay gradient. Use the payload's `time_boot_ms` as the sender's clock: `q(t) = (t_rx − time_boot_ms) − min over window`. The clock offset cancels, so no clock sync and no custom message are needed.
  - **Loss** from per-(sysid, compid) `seq` gaps.
  - **Goodput** in B/s.
  - **Blackout:** no frame for more than 3× the baseline p99.9 inter-arrival time (a measured constant).
- **Calibration:** if sim time ≠ wall time (RTF ≠ 1), the drift shows up as a fake delay slope. Measure the idle slope and subtract it, and use SIH.
- Keep RADIO_STATUS as a logged covariate only.

### 3. A transport with one endpoint is not a transport
The "TETHER is TCP" analogy needs a receiver. The spec puts the manager and the injector on the air side and leaves QGC alone on the ground, so nothing measures what actually arrived.

**Move the brain to the ground side.** A ground agent sits between the radio and QGC. It measures (it is the receiver), decides, and sends `MAV_CMD_SET_MESSAGE_INTERVAL` up the link the same way a GCS does.
- **Why this works:** congestion is asymmetric. The downlink is saturated and the uplink is nearly empty, so the 511 commands get through.
- **Don't block on COMMAND_ACK.** It comes back over the congested downlink. Confirm the change by watching the rate instead.
- **The air side becomes dumb:** shuttle + bounded queue + injector.
- **Better pitch:** a drop-in box in front of any GCS, with zero changes to the airframe.

### 4. Two clocks and no NTP make metric #2 invalid
QGC on device 2, over an AP with no internet, has no clock sync with the host. "Timestamps on both ends" then measures nothing reliable.

**Fix:** put the ground side on the **same host**. Its Intel CNVi WiFi (`wlp0s20f3`) is currently unused **[F]** and can join DroneBridge's AP.
- **Chain:** SITL → host shuttle → UART → ESP32 → RF → host WiFi → ground agent → QGC. It all runs on one monotonic clock.
- **Join air and ground logs on a hash of the frame bytes, not on `seq`.** An 8-bit seq wraps every 2.56 s at 100 msg/s **[A]**, which is shorter than the bloated delays you will be measuring.
- Device 2 can be a display relay at most. No measurement may depend on it.

### 5. Prior art covers §7.2, §7.4 and §7.5. Concede it, then claim the difference.
**[K]** PX4 already scales every stream to the instance data rate (`-r` / `MAV_x_RATE`). I am fairly, not fully, sure PX4's mavlink module also backs off on `RADIO_STATUS.txbuf` (constants named `RADIO_BUFFER_*`). ArduPilot has done txbuf flow control with SiK radios for about a decade.

**Check tonight, 1 minute, in the VM:**
`grep -rn "txbuf\|RADIO_BUFFER" ~/PX4-Autopilot/src/modules/mavlink/`

What follows from it:
- **Confound.** If DroneBridge sends RADIO_STATUS toward the FC and the shuttle forwards it, PX4 throttles itself inside your "unmanaged" baseline. Strip or forward, but decide, and record the choice per run.
- **The baselines must include a competently configured PX4:**
  - U0: no shaping (`-r` set high).
  - U1: PX4's static `-r` = C.

  A judge's first question will be "isn't that just setting the data rate?" The answer has to be a measurement.
- **TETHER's only defensible win** has two parts:
  - C varies over time: U1 tuned for C_hi bloats at C_lo, and U1 tuned for C_lo wastes C_hi.
  - TETHER sheds by priority, where PX4 scales everything uniformly **[K, medium]**.
- **Failover:** QGC already handles several links to one vehicle and switches its priority link **[K, fairly confident]**. MAVProxy already de-duplicates across links.
- **Reliable events:** PX4 and QGC have an events interface (EVENT with a sequence number + REQUEST_EVENT retransmit) **[K, medium]**.

### 6. Store-and-forward of telemetry makes the link worse
State messages are snapshots. Bursting stale ATTITUDE/POSITION after a blackout:
1. makes QGC show the past as the present,
2. loads the link at the exact moment it is re-forming,
3. inflates delivery ratio, which means a metric that rewards bursting is broken.

**Classify messages:**
- **STATE:** latest value wins. Never queue. One last-value slot per msgid.
- **EVENT:** STATUSTEXT, COMMAND_ACK. A bounded queue.
- **BULK:** shed first.

**Headline metric:** critical-set **Age of Information** p50/p99 at the GCS, with delivery ratio as the secondary metric. Delete §7.4 as written.

---

## P1: risky. De-risk tonight or tomorrow morning.

7. **`dialout` [F].** `ops` is not in `dialout`. `/dev/ttyUSB0` is `root:dialout 0660` with no ACL, so tonight's `esptool chip_id` will fail with EACCES.
   Fix first: `sudo usermod -aG dialout ops`, then log in again (or run `newgrp dialout` in the working shell).

8. **Delete the "20-line passthrough firmware".** The host has no ESP32 compile toolchain (arduino-cli / PlatformIO / IDF), which is a 0.5–2 GB download plus a first build.
   **Zero-firmware alternative [K, fairly confident]:** jumper board #3's **EN pin to GND**. The chip is held in reset, so its CP2102 becomes a plain 3.3 V USB-UART on the header:
   - board3 `RX0` (CP2102 TXD) → board1 FC-RX
   - board1 FC-TX → board3 `TX0`
   - GND to GND

   Before connecting to board 1, short RX0 to TX0 and echo-test at 57600, 115200 and 921600. **Confirm you own female-female jumpers.** That is the only part this plan depends on.
   - **Optional 15-minute zero-wiring probe [U]:** set DroneBridge's FC UART to TX=GPIO1 / RX=GPIO3. GPIO-matrix routing should take the pin away from the UART0 console, which would make it effectively noUARTConsole. Risks:
     - The UI may reject those pins.
     - The boot ROM prints garbage for about the first 100 ms.
     - DTR/RTS on port open or close can reset the board. Open the port once and use `stty -hupcl`.
   - **Pins:** on a WROOM-32 (typical for DevKit V1), GPIO16/17 are free; they are PSRAM only on WROVER. Flash uses 6–11. Safe set: 25/26, 32/33, 18/19, 21/22. 34–39 can be RX only. Read the module marking tonight.

9. **Device naming [F].** The CP2102 reports `ID_SERIAL_SHORT=0001`, a generic default. With 2–3 boards plugged in, the `/dev/serial/by-id` names collide, and ttyUSB numbering follows plug order. Use `/dev/serial/by-path/...` and label the physical ports.

10. **Design the bottleneck. Don't inherit it.** A shuttle doing blocking serial writes hands the latency to its own UDP receive buffer: about 208 KiB by default, which is **up to about 18 s** at 115200 **[A]**. That is an artifact of the shuttle. A real FC's UART buffer is a few KB, and PX4 drops at the source when it is full.
    - Use a non-blocking writer with an explicit K-byte drop-tail queue, and log K and C per run.
    - Set the UART baud to ≥460800 so the wire is never the bottleneck during emulated sweeps.
    - Then run **one validation pair**: a real 57600 UART against an emulated 5.76 KB/s bucket. If AoI agrees within the CI, the emulator is validated. That single comparison is your strongest methodology claim.

11. **WiFi-mode physics is not the injector's iid model.** 802.11 unicast retries at the MAC layer, so real degradation shows up as:
    - latency and jitter,
    - an MCS drop, which is a capacity drop,
    - then disassociation, with multi-second assoc/DHCP recovery.

    Whether ESP-NOW has MAC ACKs depends on whether DroneBridge sends broadcast **[U]**. Don't make MAC-level claims on stage that you didn't measure.

12. **The guest→host hop.** The NAT-keepalive reasoning is fine, but it is not the real risk. passt tracks flows, and guest→gateway traffic lands on host loopback **[K, verify tonight]**. The real risks:
    - (a) PX4's default GCS instance sends to the *guest's* localhost. Nothing leaves the VM until you add an instance with an explicit partner, e.g. `mavlink start -u 14580 -o 14560 -t <gateway> -m normal -r 1000000`. The flags are from memory; check `mavlink start` help.
    - (b) Port clash: keep TETHER off 14550.
    - (c) Reply to the observed (addr, port), as pymavlink `udpin:` does.
    - (d) `-p` broadcast doesn't cross passt.

13. **Mullvad [F]:** connected, **Lockdown Mode on**, LAN sharing allowed. Test the exact venue state tomorrow:
    - no venue network,
    - tunnel down,
    - host WiFi on the DroneBridge AP.

    Pin NetworkManager so `wlp0s20f3` can't roam to a phone hotspot mid-demo: `autoconnect-priority` on the DroneBridge connection, autoconnect off on the others.

14. **QGC port and param load.**
    - Turn off QGC's UDP autoconnect, which binds 14550, and add a manual UDP link from the ground agent.
    - Finish QGC's parameter download at C_hi *before* degrading. Otherwise QGC sits in "loading parameters" for the whole demo. Roughly 1k PARAM_VALUE frames is tens of KB, competing with telemetry at 5.76 KB/s.

15. **Board budget.** If board 3 is the adapter, ESP-NOW mode uses all three boards and leaves no spare. The ground board's output path is also another classic-ESP32 UART question **[U]**. Go WiFi AP mode only (1 radio + adapter + 1 spare). ESP-NOW is a stretch with a cut time.

16. **The spec's "Real" list overclaims.**
    - "Real: the packet loss" is false; the impairments are synthetic.
    - AES-GCM-256 is DroneBridge's ESP-NOW layer **[K, medium]**. In WiFi AP mode the path is WPA2.

    **Disclosure line:** real radio in the path. Impairments are synthetic and seeded, and the emulator is validated once against a real bottleneck. One real fault: the radio's power is pulled.

---

## P2: simplify or delete
- **Delete failover (T4)** and the two-interface GCS. QGC already does it, and it costs hardware.
- **Delete store-and-forward as specified** (see #6).
- **Delete Gazebo; use SIH.** It is headless. Gazebo under virgl runs at RTF<1, which changes L from run to run. Log RTF and offered load per run anyway.
- **Delete the dashboard app.** Use a 2 Hz terminal status line plus one matplotlib window with the air-side and ground-side attitude traces. The visible gap between the two traces *is* the AoI. No web stack, no network dependency.
- **Delete "the scale story is free".** N vehicles on one broadcast channel is a multiple-access capacity-allocation problem.
- **Demote RADIO_STATUS** to a logged covariate.

---

## P3: add
- **A channel indexed by time, from the seed.** The seed generates a trajectory over time (C(t), GE state(t), blackout windows), not per-packet draws. With per-packet RNG, managed and unmanaged offer different packet counts and so see *different* channels despite the "same seed".
- **Paired, interleaved runs.** Alternate U0/U1/TETHER (ABAB or randomised), with one seed per triple. Report paired differences with a CI (t at df=29 is 2.045, or bootstrap). The venue's 2.4 GHz band gets worse through the evening, so running conditions in blocks confounds them with time.
- **T5 wall-clock [A].** 30 runs × 3 conditions × 1 profile × (20 s + 10 s reset) = **45 min**. Three profiles take 135 of the 300 sprint minutes. Run one profile over RF and the rest in emulation, sequentially.
- **Predict the knees, then confirm them on stage.**
  - From measured L_total and L_crit: unmanaged AoI blows up at C < L_total, and TETHER holds until C < L_crit (+ overhead).
  - Recovery time after a 511 step ≈ Q/(C − L_after).
  - Sweep C downward live and show TETHER failing where you predicted it would.
- **Controller design.**
  - **Tiers** come from `mavlink status streams`, measured tonight.
  - **Shed** one tier per step after q > q_hi for T_detect.
  - **Restore** one tier after q < q_lo for T_restore, with T_restore > T_detect for hysteresis.
  - **Derive** the thresholds from the measured baseline q distribution.
  - **Filter** TETHER's own COMMAND_ACKs out of the QGC stream.
  - **Log** any 511 or REQUEST_DATA_STREAM that QGC sends itself.
- **One real fault:** pull the air radio's USB power. Measure recovery (including AP re-association) n≥10 tomorrow morning.
- **Freeze the contract before the two of you split.** JSONL per frame:
  `{t_ns, side, h=blake2b(frame)[:8], sysid, compid, msgid, seq, len, run_id, cond, seed}`
  - Builder A: shuttle, queue, injector, air log.
  - Builder B: ground agent, estimator, controller, join and analysis.
- **Make the prep/sprint boundary auditable.** `git tag sprint-start` at 17:00. The morning is plumbing and logs only.
- **Hardware review:** declare **three** ESP32s, not two.

---

## Revised gates
| Gate | Statement | Pass criterion |
|---|---|---|
| T0 | Pieces proven | Spec T0 + dialout fixed + PX4 txbuf grep + `mavlink status streams` rates recorded |
| T1 | Radio in path | Heartbeat over RF reaches the ground agent on the host |
| T2 | Instrument works | Capacity profile reproducibly drives unmanaged AoI to the predicted K/C (n=10) |
| T3 | Manager works | Under a C step, TETHER holds critical AoI p99 < X while U0 and U1 do not. Paired, n=30, one profile, over RF |
| T4 | Result | Knee prediction confirmed; emulator validated against a real 57600 UART |

## Cut lines
| Clock | Check | If missed |
|---|---|---|
| 17:00 | `git tag sprint-start` | — |
| 18:30 | Capacity injector + both-side logs joining | Run on an emulated link (same code, labelled) |
| 19:30 | Controller closed loop on one C step | Demo U0 vs U1 + the measured knee (still a result) |
| 19:30 | ESP-NOW decision | Never after this |
| 20:00–20:45 | RF sweep, one profile | Stop at 21:00 regardless |
| 21:30 | Freeze | Rehearse twice; record the fallback video by 21:45 |

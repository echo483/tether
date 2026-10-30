# TETHER — link-aware telemetry for cheap unmanned systems

**Spec v2.0 — plan of record.** Supersedes v1.0. Incorporates three independent adversarial
reviews (`REVIEW-ARCHITECTURE.md`, `REVIEW-DEMO.md`, `REVIEW-DELIVERY.md`).

Night Hack by Founders, Inc. · Fort Mason SF · Fri Oct 30 2026
Check-in 4:15 · Build 5–10 pm · Exhibition 10 pm · Close 11 pm · Team of 2

> **Hook:** A dropped link tells you. A stale link doesn't.
> **Tagline:** When the link gets bad, send what matters.

---

## 0. The verdict — what changed and why

All three reviewers, working independently, found the **same load-bearing defect**:

> **T3 as written cannot pass.** Under independent random loss at rate *p*, every sent packet
> arrives with probability (1−p) **regardless of how many you send**. Shedding streams reduces
> the numerator and the denominator proportionally, so the delivery ratio cannot move. It is an
> identity, not an empirical question. Simulated: managed 0.809 vs unmanaged 0.800.

Rate adaptation only helps when the damage is **offered load > capacity**. So the headline fault
changes from *loss and delay* to **capacity collapse**, and the headline metric changes from
delivery ratio to **age of information** — how stale the pilot's picture is.

Four more corrections:

| # | Was | Now | Why |
|---|---|---|---|
| 1 | Manager on the air side | **Manager on the ground side** | A transport needs two endpoints. Nothing on the ground was measuring what arrived. |
| 2 | `RADIO_STATUS` as the link input | Estimate **at the receiver from the traffic** | A radio on a table reads perfect all night; it cannot see a software-injected fault. |
| 3 | FIFO store-and-forward | **Latest-value-wins** for state | Bursting stale position shows the past as the present and inflates delivery ratio. 9.9 s stale vs 0.1 s. |
| 4 | Failover as a headline feature | **Cut** | QGC already switches links; it needs a two-interface GCS and the third radio. |

**Keep:** real PX4, real QGC, a real radio in the path, a MAVLink-native lever, and the
measurement discipline. The fault was staging and experiment design — not substance.

---

## 1. What we own

**DroneBridge is our PHY/MAC. We built the transport and policy layer above it.**

| Layer | Who built it | What it is |
|---|---|---|
| **PHY/MAC** | DroneBridge (Apache-2.0, since 2018) | ESP32 RF link: WiFi / ESP-NOW, WPA2 or AES-GCM |
| **Transport + policy** | **US** | Receiver-side estimation, capacity-aware shedding, prioritisation, freshness policy |
| **Application** | MAVLink / PX4 / QGC | Standard telemetry |

**The line to say:** *"DroneBridge moves bytes; it doesn't know what a heartbeat is. TETHER
decides which bytes."*

**Do not** use the "DroneBridge is Ethernet, TETHER is TCP" analogy. TCP's reliable, in-order
delivery is *exactly* the head-of-line blocking we exist to remove. A networking engineer will
use it to end the pitch. For the VC crowd use: *"What a video call does on bad WiFi — drop the
extras, keep the call."*

### The startup thesis (narrowed)

As unmanned systems get cheap and plentiful, the bottleneck moves off the airframe and onto the
link. Everyone optimises hardware. Nobody ships a software layer that keeps an operator's picture
*fresh* on a cheap radio — and nobody publishes how these links actually fail.

**The product is the layer, not the radio.** A drop-in box in front of any GCS, with **zero
changes to the airframe**. That is the retrofit pitch, and it is genuinely better than the
v1 pitch because it is true.

### Prior art — concede it, then claim the difference

**[verify tonight, 1 min]** `grep -rn "txbuf\|RADIO_BUFFER" ~/PX4-Autopilot/src/modules/mavlink/`

PX4 already scales streams to the configured link rate, and probably backs off on
`RADIO_STATUS.txbuf`. ArduPilot has done txbuf flow control on SiK radios for about a decade.
QGC already handles multiple links to one vehicle.

**What is actually ours:** end-to-end feedback (decide from what *arrived*), priority-aware
shedding where PX4 scales uniformly, and a **seeded, published benchmark**. Lead with the
benchmark. Honest framing beats a novelty claim that an engineer can puncture in one question.

---

## 2. The four Ws

**WHO** — a small-unit operator flying a cheap airframe they can afford to lose.
**WHAT** — the link layer between them, plus the instrumentation to measure it.
**WHEN** — the moment the RF environment degrades: congestion, range, interference.
**WHERE** — RF-crowded, indoor, urban, beyond-line-of-sight.

## 3. Mission

> Keep the operator's picture **current** on a cheap radio — and publish the curve where that
> stops working.

## 4. Problem statement

Cheap drones link on $7 radios. When the RF environment degrades, the dangerous failure is not
disconnection — QGC announces that. It is **silent staleness**: the GCS says *connected* while
showing a pilot a picture that is seconds old. There is no standard way to measure how a
low-cost telemetry link behaves under congestion, so teams cannot separate a link problem from a
software problem, and cannot improve what they cannot measure.

---

## 5. Architecture

```
 ┌──────────── VM — simulator appliance ──────────────┐
 │   PX4 SITL (SIH, headless)  real autopilot, sim AC │
 └───────────────────┬────────────────────────────────┘
                     │ MAVLink/UDP  guest → host gateway
                     │ (continuous stream keeps the NAT mapping alive)
 ┌───────────────────▼────────────────────────────────┐
 │ LAPTOP 1 — "DRONE"  (air side, dumb by design)     │
 │   shuttle : UDP ↔ serial, bounded drop-tail queue  │
 │   injector: capacity collapse + loss + blackout    │
 │            ──serial──▶ ESP32 #1 (DroneBridge, AP)  │
 └────────────────────────────────────────────────────┘
                     ╎  2.4 GHz RF  ╎   ← a metal tin covers this
 ┌────────────────────▼───────────────────────────────┐
 │ LAPTOP 2 — "PILOT"  (ground side, the brain)       │
 │   ground agent : measures what ACTUALLY ARRIVED    │
 │   TETHER manager: estimate → decide → cmd 511 up   │
 │   QGroundControl                                   │
 └────────────────────────────────────────────────────┘
```

**Congestion is asymmetric.** The downlink is saturated; the uplink is nearly empty. That is why
a ground-side manager can send `MAV_CMD_SET_MESSAGE_INTERVAL` *up* the degraded link and have it
arrive. This is the architectural insight the whole design rests on.

**Don't block on `COMMAND_ACK`** — it comes back over the congested downlink. Confirm by watching
the measured rate instead.

**Real:** the radio, the autopilot (PX4), the GCS (QGC), the wall-clock timing.
**Synthetic and disclosed:** the impairments. Validate the emulator **once** against a real
57600-baud UART bottleneck — that single comparison is the strongest methodology claim available.

**No video.** DroneBridge carries telemetry and command only. Say it before anyone asks.

---

## 6. The layer we build

### 6.1 Link state — estimation at the receiver

`RADIO_STATUS` is demoted to a **logged covariate**. It reports real RF, has no timing fields,
and on a table it will read perfect forever. Estimate from the traffic itself:

| Quantity | Method |
|---|---|
| **Queueing delay** | delay gradient on the payload's `time_boot_ms`: `q(t) = (t_rx − time_boot_ms) − min over window`. **The clock offset cancels — no clock sync needed.** |
| **Loss** | per-(sysid, compid) `seq` gaps. Not on `seq` alone: it wraps every 2.56 s at 100 msg/s. |
| **Goodput** | bytes/s at the receiver |
| **Blackout** | no frame for > 3× the baseline p99.9 inter-arrival time (a *measured* constant) |

**Calibrate first:** if SITL's real-time factor ≠ 1, drift appears as a fake delay slope. Measure
the idle slope and subtract it. Use SIH, log RTF per run.

### 6.2 Actuation — MAVLink's own lever

**`MAV_CMD_SET_MESSAGE_INTERVAL`** (cmd 511): interval in µs, `-1` disables, `0` restores
default. This is how a GCS controls stream rates, and PX4 honours it.

**Critical:** cmd 511 only affects the mavlink instance that **received** it. Send it through the
shuttle's own SITL socket, or it throttles the wrong stream. Probe this tonight.

**Policy:** shed one tier per step after `q > q_hi` for `T_detect`; restore one tier after
`q < q_lo` for `T_restore`, with `T_restore > T_detect` (hysteresis). Derive thresholds from the
measured baseline, not from taste. **Probe up** — without probing, a shed stream stays shed.

### 6.3 Freshness policy — not FIFO

| Class | Examples | Policy |
|---|---|---|
| **STATE** | ATTITUDE, POSITION, GLOBAL_POSITION_INT | **Latest value wins.** One slot per msgid. Never queue. |
| **EVENT** | STATUSTEXT, COMMAND_ACK | Bounded queue, replayed on recovery |
| **BULK** | raw sensor streams, HIGHRES_IMU | Shed first |

Bursting stale state after a blackout makes QGC show the past as the present *and* loads the link
exactly as it re-forms. Delete v1 §7.4 as written.

### 6.4 The fault injector — the instrument

Seeded **capacity-collapse**: a token bucket at C bytes/s plus a bounded drop-tail queue of K
bytes, with C varying over time. Secondary: Gilbert–Elliott burst loss, blackout windows, delay.

**The channel is indexed by TIME, not per packet.** With per-packet RNG, the two arms send
different packet counts and therefore see *different* channels despite the "same seed". One
trajectory `{C(t), GE(t), blackout(t)}` per seed, replayed by both arms.

**The manager must never read injector state.** If it can see the truth, there is nothing to demo.

---

## 7. Measurements

Format is fixed: method, instrument, `n`, statistic with CI, raw log, date.

| # | Metric | Unit of analysis | n | Gate |
|---|---|---|---|---|
| **1** | **Critical-set age of information** p50/p99 at the GCS, managed vs unmanaged | the run | 30 paired | **T3 headline** |
| 2 | Critical-set delivery ratio | the run | 30 paired | T3 (secondary) |
| 3 | Time to detect | the run | 30 | T3 |
| 4 | Time to recover | the run | 30 | T3 |
| 5 | Emulator validation: emulated vs real 57600 UART | the run | 1 paired | T4 |

**Why AoI is the headline:** managed deliberately sends *less*. Delivery ratio rewards stale
bursts and is trivially gamed. Freshness is the property the operator actually wants.

**Arms must be interleaved** (ABAB or randomised), never blocked — the venue's 2.4 GHz band gets
worse through the evening, so blocked runs confound condition with time. Report **paired
differences** with a CI (t at df=29 is 2.045, or bootstrap).

**Baselines, both of them:**
- **U0** — no shaping (PX4 `-r` set high)
- **U1** — PX4's static rate tuned to C

A judge's first question will be *"isn't that just setting the data rate?"* U1 is the answer, and
it has to be a measurement. **TETHER's defensible win:** C *varies*, so a static rate is wrong in
both directions — U1 tuned for C_hi bloats at C_lo, and U1 tuned for C_lo wastes C_hi.

**Pre-register the prediction before 17:00.** Simulate both arms with tonight's census, write the
expected numbers into `PREREG.md`, commit it. A predicted failure confirmed on stage is the one
thing a room remembers.

---

## 8. Gates

| Gate | Statement | Pass criterion |
|---|---|---|
| **T0** | Pieces proven | SITL runs; `dialout` fixed; cmd-511 probe works; txbuf grep done; stream census recorded |
| **T1** | Radio in the path | A heartbeat over **real RF** reaches the ground agent |
| **T2** | Instrument works | The capacity profile reproducibly drives unmanaged AoI to the predicted value (n=10) |
| **T3** | Manager works | Under a C step, TETHER holds critical AoI p99 < X while U0 and U1 do not. Paired, n=30, over RF |
| **T4** | Result | Knee prediction confirmed; emulator validated against a real UART bottleneck |

**T0–T2 is a complete, honest project. T3 is the result. T4 is the methodology claim.**

---

## 9. The demo — live, no slides, 2 minutes

**Design rule:** the judge performs one physical cause with their own hands; you disclose one
synthetic cause; one giant number; one prediction confirmed, one failure predicted.

**The set.** Two laptops side by side. A radio that is cabled to **laptop 1 only**, standing about
1.5–2 m away with a metal tin next to it.

- **Laptop 1, "DRONE"** — PX4 SITL, shuttle, injector. One huge attitude dial. A strip showing
  commands received over the air.
- **Laptop 2, "PILOT"** — ground agent, manager, QGC. The same dial, driven **only by what came
  over the air**. A giant **PILOT LAG** number, red above 1 s. Plus the load bar.

**Why two devices when the sweep is single-host:** the sweep stays on one host for the single
clock; the *demo* uses two so a passer-by can see that the only link between the two is the air.
AoI on laptop 2 comes from the `time_boot_ms` delay gradient, where the offset cancels — so no
clock sync is needed. Disconnect laptop 1's WiFi from the AP for the demo.

**Run sheet**

| t | Action | What it proves | Line |
|---|---|---|---|
| 0:00–0:08 | Both dials together, lag 0.04 s | — | "A dropped link tells you. A stale link doesn't. Watch." |
| 0:08–0:30 | **The judge closes the tin over the radio** | The only path is RF, and *their hand* broke it. Real PX4, real radio, real GCS. | "That's real PX4 flying a simulated quad. The radio runs DroneBridge — open source, not ours. The only way from that laptop to this one is through the air. Close the lid." |
| 0:30–0:55 | Squeeze capacity, TETHER **off**. Prediction announced first. | The dangerous failure: **alive but showing the past.** QGC still says *connected*. | "We can't stand a kilometre apart, so we squeeze capacity in software — seeded, scripted, disclosed. Prediction: three seconds stale within two. … There it is." |
| 0:55–1:20 | TETHER **on** | The mechanism, and the prediction confirmed | "TETHER sees the backlog at the pilot's end and tells PX4, in MAVLink's own command, what to stop sending. Don't trust our dashboard — that's QGC's own inspector showing those streams at zero." |
| 1:20–1:42 | **Branch by judge type.** Engineer: step C below the critical set → *TETHER fails too*, as predicted. Founder: re-squeeze → *nothing the pilot notices*. | The boundary, measured not hidden | "We don't create bandwidth. We decide who gets it — and here's where that stops working." |
| 1:42–2:00 | One line of receipts | It's a result | "Thirty paired runs through this radio tonight. Raw logs in the repo." |

**Pacing is arithmetic.** With K ≈ **3 s × C**, onset is visible within ~1.2 s and the recovery
drains in ~6.4 s — narratable as a countdown. At 0.5 s × C the failure is invisible; at 20 s × C
recovery is 45 s of dead air. The boundary beat needs C well below the critical set to fail
inside 20 s.

**Demo-killers — check all five before 17:00:**
1. **`NAV_DLL_ACT`** — the lid also cuts QGC's uplink. If the datalink failsafe is armed, the
   first lid closure sends the drone home and the next judge sees a parked vehicle.
2. **The mission must loop and keep turning** — DO_JUMP over a lawnmower pattern. A constant-bank
   orbit makes lag invisible.
3. **Reset stream rates between arms** — cmd 511 persists. Send `param2 = 0` and *verify the
   measured rate* or your "unmanaged" run is already throttled, and the A/B looks rigged.
4. **WiFi re-association after the lid** — static IP, pinned BSSID, and a measured
   lid-open → first-frame time (n ≥ 10).
5. **No WiFi scans on the pilot interface during runs** — off-channel time looks exactly like a
   link fault. One venue scan at 16:15.

**Fallback ladder** (each switch rehearsed as one command, under 30 s):

| Failure | Fallback |
|---|---|
| Board dies | Board 2, pre-flashed with an identical config |
| Serial/ESP32 path dies, WiFi fine | **Phone hotspot as the RF path** — laptop 1 → phone → laptop 2, and the phone goes *in the tin*, which is a cleaner blackout than the ESP32 |
| All RF dead | Single-host **emulated** link, permanent "EMULATED LINK" banner, plus the fallback video recorded by 21:15 |
| Closed loop broken | Demo the instrument: predicted collapse, then operator-triggered shedding to show the lever works by hand |

**Corrected from v1:** not "same code, same numbers." Numbers measured on an emulated link are a
different measurement. **Keep two tables and never mix them.**

---

## 10. Hardware and environment — what we actually have

**3× ESP32 classic DevKit V1** (CP2102). From the DroneBridge docs: supported but *not recommended
for new builds*; the `noUARTConsole` variant is **not published** for classic ESP32, so UART0
stays the console; GPIO0/2/5/12/15 unusable; GPIO6–11 and GPIO16–17 flagged as SPI flash.
**Read the module marking** — 16/17 are free on WROOM, PSRAM on WROVER.

**Serial into the flight-controller UART — the zero-firmware trick.**
Do **not** plan to write passthrough firmware: there is no ESP32 toolchain on the host, which is a
0.5–2 GB download plus a first build. Instead, **tie board #3's EN pin to GND** — the chip is held
in reset and its CP2102 becomes a plain 3.3 V USB-UART on the header. Test by jumpering TX0↔RX0
and echo-testing. **Requires female-female jumpers** — the only part this plan depends on.

### Where things run — decided

| | Runs | Why |
|---|---|---|
| **VM** | PX4 SITL (**SIH**, not Gazebo) only | Already built; Ubuntu-only toolchain; SIH is headless and RTF≈1 |
| **Laptop 1** | shuttle, bounded queue, injector | Owns the air-side ESP32 |
| **Laptop 2** | ground agent, manager, QGC | The brain, and the second physical device |

**Radio mode: WiFi AP (1 radio + 1 adapter + 1 spare).** This **reverses v1's choice of ESP-NOW**:
with board #3 as the adapter, an ESP-NOW pair consumes all three boards and leaves no spare, and
the ground-side board's output path is a second open classic-ESP32 UART question. ESP-NOW becomes
a **stretch with a hard cut at 19:30**, never after.

### Environment facts — verified on the machine

| Fact | Consequence |
|---|---|
| **`ops` is not in `dialout`** | `esptool chip_id` fails with EACCES. Fix: `sudo usermod -aG dialout ops`, then re-login |
| **CP2102s all report serial `0001`** | `/dev/serial/by-id` collides. Use `/dev/serial/by-path/` and label the physical ports |
| **Mullvad connected, Lockdown Mode on** | Test the exact venue state: tunnel down, host on the AP, no venue network |
| **`wlp0s20f3` exists and is unused** | Available if a second radio interface is ever wanted |
| **A blocking serial write hands latency to the kernel's 208 KiB UDP buffer** | ≈18 s at 115200. Use a non-blocking writer with an explicit bounded queue, and log K and C per run |
| **Baud** | Set ≥460800 so the wire is never the bottleneck during emulated sweeps |
| **QGC** | Needs `--appimage-extract` on Debian 13. Disable UDP autoconnect (14550 clash). Finish the parameter download *before* degrading |

---

## 11. Prep vs sprint — the defensible boundary

The judges score **sprint** work. Tag `git tag sprint-start` at 17:00 and put a **disclosure card**
on the table:

> **Built before 17:00:** VM, PX4 build, shuttle and logging plumbing, DroneBridge flash and
> config, the offered-load census, the pre-registration.
> **Built 17:00–22:00:** the injector, the manager, the ground reports, the sweep, the results.

**Prep is component bring-up only.** No estimator, no controller, no metrics. Undisclosed prep is
the realistic way to get disqualified; disclosed prep is just an honest head start.

---

## 12. Cut lines

| Clock | Condition | Action | What you still have |
|---|---|---|---|
| Tonight | — | **Cut** failover, ESP-NOW, FIFO store-and-forward | Everything below |
| M+2:45 | No T1 | Emulated link becomes primary; one retry at the venue | T0, T2, T3 emulated |
| 17:00 | T1 doesn't reproduce | Emulated from minute 0, boards on the table, labelled honestly | Same |
| 18:30 | No injector / no joined logs | Run emulated, labelled | Full table |
| 19:30 | No closed loop on one C step | Ship an **operator-triggered** managed arm | Managed vs unmanaged, n=30 |
| 19:30 | ESP-NOW undecided | **Never** | WiFi AP |
| 19:50 | Sweep not started | n = 10 (12 min), report the wider CI | Honest smaller table |
| 20:20 | Sweep unfinished | Stop it, report the n achieved | — |
| **20:50** | Anything | **FREEZE CODE** | — |
| 21:15 | Live chain unstable | Fallback video plus a live emulated run | Full demo |

**Minimum viable winner:** real PX4 → air agent → real ESP32 radio → ground agent → QGC. One
capacity-collapse profile. Managed vs unmanaged **critical-set AoI and delivery**, n = 30 paired
runs, 95% CI, raw logs. The prediction pre-registered before 17:00 and confirmed live. One
boundary run that fails exactly where predicted. The emulated version is the floor.

Under 21:00 both devices **must** be solid, or demo single-host with a labelled split screen.

---

## 13. Fleet and scale

N vehicles on one channel is a **multiple-access capacity-allocation problem**, not a free
extension. Delete v1's "the scale story is free". If asked, the honest answer is that the
adaptive layer generalises, and that the multi-vehicle case is future work with a known name.

---

## 14. Safety, legality, venue

- **Hardware review tonight, minute 0.** Declare **three** ESP32 boards, USB-powered; a 2.4 GHz
  private AP (one SSID, low TX power, certified modules, unmodified antennas); **no** LiPo, props,
  airframe or flight; no soldering or fabrication. **Ask explicitly whether a private AP is
  permitted** — some venues ban them — and keep the confirmation.
- **FCC Part 15.** Unmodified certified modules at default or lower power. **Never** jam, deauth,
  spoof SSIDs or sniff others' traffic. Jamming is illegal outright (47 U.S.C. §333) and is an
  instant ejection. If a judge asks you to jam it, the answer is *"no — which is why the
  instrument exists."* Passive attenuation (a metal tin) is the only physical degradation allowed.
- **Never join or bridge the venue network.** Give the SSID an obvious team name.
- **Change the default AP and web passwords.** A room full of hackers, a default-password AP, and
  an unauthenticated MAVLink path into your autopilot is a demo someone else can end for you.
- **Electrical.** GND/TX/RX only between boards. **Never** tie VIN/5V or 3V3 between two
  USB-powered boards. 3.3 V logic. Boards on a non-conductive surface, never on an aluminium
  laptop. Tape everything down.
- **No airframe, props or LiPo on site** — not even as decoration. It invites a safety re-review.
- **Attribution.** DroneBridge (Apache-2.0), PX4 (BSD-3), QGC — credited on screen and in the README.
- **Framing.** Civilian-equivalent claims only. No "tactical", no "military-grade", no range figure
  you did not measure.
- **No re-entry after 22:00.** Chargers, hub, power strip and cables on the table by 21:45.

**Strike from anything said out loud:** "a $7 radio that behaves like a tactical link" (tactical
radios buy range, anti-jam and MIMO — software can't); "contested spectrum" (say *crowded
spectrum, like this hall*, and quote the AP count from the 16:15 scan); "1 km" / "150 m" (those
are DroneBridge's numbers, not ours); "AES-GCM" (WiFi AP mode is WPA2).

---

## 15. Do NOT

1. Build failover, "just a quick version". Not tonight, not at 20:20.
2. Rebuild PX4 anywhere, or upgrade anything after the morning cold-start passes.
3. Install an ESP32 toolchain or write ESP32 firmware. Flash prebuilt DroneBridge only.
4. Put USB passthrough or serial into the VM.
5. Let the manager read injector state.
6. Run all unmanaged runs then all managed runs. Interleave ABAB.
7. Debug the radio during the sprint after 18:30. Switch to emulated and move on.
8. `pip install` anything at the venue, or depend on the internet at all.
9. Call injected loss "real packet loss", or quote DroneBridge's range figures as our own.
10. Change code after 20:50.
11. Touch laptop 1 while the sweep runs.
12. Leave the room after 21:45.
13. Jam, deauth, sniff, or join the venue network.
14. Bring LiPo, props or an airframe.

---

## 16. Out of scope

Video, autonomy, BVLOS flight, real airframes, video encoding, payload work, ESP-NOW as a primary
path, failover, and anything requiring a part we do not already own. Each one costs a gate.

# TETHER — tonight's 90 minutes and tomorrow's 4 hours

**Tonight's goal: prove the pieces separately and sleep.** Nothing here is the project. Nothing
here is sprint work. Tonight buys you a calm Friday.

**Do not tonight:** flash DroneBridge, wire the radio, or attempt a radio link.

**Owners:** **A = systems/radio** (hardware, DroneBridge, serial, SITL, PX4-side actuation).
**B = instrument/analysis** (logging, ground agent, injector, sweep, stats, dashboard).
The contract between them is the log schema, the report message, the shuttle hook and the port map.

**Verified on this machine — act on these first:**
- `ops` is **not in `dialout`** → `esptool chip_id` will fail with EACCES.
- Mullvad is **connected with Lockdown Mode on**.
- No ESP32 is currently plugged in (`/dev/serial/` does not exist).
- All CP2102s report serial `0001`, so `/dev/serial/by-id` names collide — use `by-path`.

---

## §0 · Minute 0 — the only disqualifying item

- [ ] **Submit the hardware review.**
      **Three** ESP32 dev boards, USB-powered from laptops; one 2.4 GHz private AP (one SSID, low
      TX power, certified modules, unmodified antennas); **no** LiPo, motors, props, airframe or
      flight; no soldering or fabrication; two laptops plus a declared power strip.
      **Ask explicitly whether a private 2.4 GHz AP is permitted.** Keep the confirmation.

- [ ] Count laptop USB ports (A vs C), check the hub, and confirm ≥4 cables are *data* cables.

---

## §1 · Tonight — 90 minutes

| T+ | A (systems/radio) | B (instrument/analysis) | Done when |
|---|---|---|---|
| **0–10** | Draft the hardware review | Port/cable audit; send the review | Submission sent, screenshot saved |
| **10–50** | Fix `dialout`: `sudo usermod -aG dialout ops`, then re-login or `newgrp dialout`. VM up, PX4 **SIH** (not Gazebo). Point the GCS instance at the host gateway. **Return-path probe**: from the host, through the *same* socket, send cmd 511 to slow ATTITUDE to 1 Hz. | `esptool chip_id` on **all 3 boards × every cable**. Record MAC, flash size, **module marking (WROOM vs WROVER — decides GPIO16/17)**. Label boards 1/2/3; label cables "data OK". | `notes/sitl.md` with the exact commands; `notes/boards.md`. **COMMAND_ACK = ACCEPTED *and* the measured ATTITUDE rate drops to ~1 Hz.** |
| **30–60** | — | `uv` repo + `pymavlink pyserial esptool` | `import pymavlink, serial` succeeds in the venv |
| **50–70** | **Offered-load census**: 60 s capture — per-msgid Hz, bytes/s, packet size, plus the critical-set subtotal. | **DroneBridge research** → `notes/dronebridge.md`: classic-ESP32 binary + version + flash offsets; FC UART GPIOs and whether configurable; baud options; UDP addressing in AP mode; channel + TX power; **do we own female-female jumpers?** | `L` and `L_crit` known with n = 60 s. Every research question answered or marked unknown. |
| **60–75** | — | QGC: `--appimage-extract`, run, connect to SITL with no radios | Vehicle visible. **Cut first if late** — it costs 10 min tomorrow instead |
| **70–75** | *The one wiring exception.* Board #3: jumper **EN→GND** and **TX0↔RX0**, open the tty, type, see the echo. No flash. | — | Echo seen → the adapter route is proven. No echo → **book a store run for the morning.** |
| **75–90** | **Decision block, both.** Write `DECISIONS.md`: headline profile = capacity collapse; metric definitions; baud (≥1.5× the census peak); adapter route or store run; cuts (failover, ESP-NOW). Shut the VM down. **Sleep.** | | Every open item closed or cut |

**Cut order if you overrun:** QGC → census (move to M+0) → research.
**Never cut:** the hardware review, the `dialout`/`chip_id` check, or the return-path + cmd-511
probe. Those three are load-bearing.

**Optional, only if there is time:** the tin test (close a metal tin over a powered board on the
desk and watch the link drop), and `NAV_DLL_ACT` — the datalink failsafe that would send the
simulated drone home the first time a judge closes the lid.

### Why the loopback exception matters

Tying **EN to GND** holds the ESP32 in reset, so its CP2102 becomes a plain 3.3 V USB-UART on the
header. That deletes the planned "20-line passthrough firmware" — there is no ESP32 toolchain on
the host, and installing one is a 0.5–2 GB download plus a first build. The two-jumper echo test
takes five minutes and it decides whether someone drives to a store in the morning.

---

## §2 · Tomorrow morning — 4 hours, all substrate

Prep is component bring-up and environment **only**. No estimator, no controller, no metrics.

| M+ | A | B | Done when |
|---|---|---|---|
| **0:00–0:15** | Adapter loopback (if not done tonight) | — | **Go/no-go on the store run by 0:15.** If needed, B goes: 2× 3.3 V USB-TTL, 2 data cables, a hub. Abort the trip if it runs past 75 min |
| **0:15–1:15** | Flash prebuilt DroneBridge on board #1 (esptool CLI). Configure AP mode, channel, **a new AP password and web password**, FC UART GPIOs, baud, low TX power. Host joins the AP. **Pin NetworkManager autoconnect priority** so the laptop can't roam away. | `link.py` (UDP↔serial *and* UDP↔UDP behind one interface, bounded queues, drop counters), `log.py` JSONL schema, `ground.py` | Config survives a power-cycle. Emulated path: SITL→ground→QGC with **0 unaccounted drops** over 5 min |
| **1:15–2:15** | Wire adapter→board #1: **GND, TX, RX only.** Raw byte test, then the full chain. **GATE T1.** | `CONTRACT.md`. `PREREG.md`: profile parameters + **predicted** delivery/latency per arm from the census fed through the queue sim. **Committed before 17:00.** | QGC shows the vehicle over RF and a round-trip command succeeds |
| **2:15–2:45** | **RF baseline**, both: 5 min unmanaged, no faults — delivery, one-way latency p50/p99/max, RADIO_STATUS present y/n | | `notes/baseline-rf.md` with method, instrument, n, CI, raw log, date |
| **2:45–3:30** | **Cold-start rehearsal**, both. Power everything off, follow `RUNBOOK.md`, time it. Then **go offline and re-run the chain.** VM snapshot; `git tag prep-end`. | | Cold start **≤15 min with no internet** |
| **3:30–4:00** | Pack from §3. Charge everything. **Stop.** | | Bag packed |

**Morning cut:** no T1 by **M+2:45** → stop radio work. The emulated link becomes primary. The
radio gets one retry at the venue, 16:15–17:00, from the RUNBOOK only.

**Demo prep, folded into the morning (~30 min):** measure lid-closed → first-frame recovery
(n ≥ 10) and quote it as the prediction; set a static IP and pin the BSSID on the AP connection;
stand up laptop 2's `uv` env; export or screenshot the DroneBridge config so board 2 can be a
drop-in spare.

---

## §3 · Pack list

Two laptops + chargers · power strip (declared) · USB hub · **3 boards, labelled** · ≥4 tested
data cables including a spare USB-C↔micro-USB · **female-female jumpers + spares** · tape · a
non-conductive mat · the **disclosure card** · a printed **RUNBOOK** · the hardware-review
confirmation · a **metal tin** · the fallback video on both laptops and a USB stick.

---

## §4 · The sprint

See `SPEC.md` §8 (gates), §9 (the demo run sheet) and §12 (cut lines). Order of work:

injector + ground reports → estimator → rate adaptation → closed loop → sweep → boundary run.

**If you only get half of it done:** the instrument, the estimator, and a manual toggle. That is
T0–T2 plus a demonstrated lever — still a complete, honest result.

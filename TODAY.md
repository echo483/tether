# TETHER — TODAY (Fri Oct 30)

Clock: 12:00 now · leave for SF ~15:00 · check-in 16:15 · **build 17:00–22:00** · close 23:00.

**The goal of the next 3 hours: a heartbeat over real RF, at home, with no venue network involved.**
Everything else is secondary. If T1 works before you leave, the venue is a re-run. If it doesn't,
you're debugging radio wiring at 17:00 with 5 hours on the clock.

---

## The project, distilled

Cheap drones lose the link, and the dangerous failure isn't disconnection — QGC announces that.
It's **silent staleness**: the GCS says *connected* while the operator watches a picture that is
seconds old.

TETHER is a small layer that sits **between a drone's autopilot and its radio**, on the ground
side, with **zero changes to the airframe**. It measures what *actually arrived*, decides what
matters, and tells the autopilot — in MAVLink's own command — what to stop sending, so the
operator's picture stays fresh. Then it publishes the curve where that stops working.

DroneBridge (existing open-source firmware) is the PHY/MAC. **We build the transport and policy
layer above it.** One line: *"DroneBridge moves bytes; TETHER decides which bytes."*

---

## Devices needed

| Item | Notes |
|---|---|
| **3× ESP32 DevKit V1** | 1 = radio, 3 = USB-UART adapter, 2 = spare |
| **2 laptops** + chargers | Laptop 1 = drone/shuttle/injector. Laptop 2 = ground agent/manager/QGC |
| **Female-female jumpers** | **The one hard dependency.** No jumpers, no adapter |
| **≥4 data USB cables** | Not charge-only. Include a USB-C↔micro-USB spare |
| USB hub, power strip | Hub not currently attached — bring it |
| **Metal tin with a lid** | The judge-performed fault in the demo |
| Tape, non-conductive mat, printed RUNBOOK, disclosure card | |

No purchased part is required if you own the jumpers.

---

## Wiring schematic

```
  LAPTOP 1 ──USB──▶ [BOARD 3  — held in RESET, = plain USB-UART]
                      EN ── GND
                      TX0 (GPIO1) ────────────▶ FC-RX  (board 1, per DroneBridge config)
                      RX0 (GPIO3) ◀──────────── FC-TX  (board 1)
                      GND ───────────────────── GND
                                                       │
                                    [BOARD 1 — DroneBridge, AP mode, 2.4 GHz]
                                                       │
                                            ~1.5–2 m   ╎  2.4 GHz  ╎  ← tin covers this
                                                       │
  LAPTOP 2 ──WiFi──▶ DroneBridge AP ──▶ ground agent ──▶ QGC
```

**Rules:** GND / TX / RX only. **Never** tie 5V or 3V3 between two USB-powered boards. 3.3 V logic.
Boards on a non-conductive surface, never on an aluminium laptop.

**Before wiring board 1:** jumper board 3's TX0↔RX0 and echo-test. If no echo, the adapter route is
dead — buy a USB-TTL adapter instead of burning sprint time.

---

## Stack

| Layer | Choice | Why |
|---|---|---|
| Autopilot | **PX4 SITL, SIH target** — already built in VM `dronelab` | Headless, RTF≈1. Gazebo is heavier and distorts run-to-run load |
| Radio firmware | **DroneBridge prebuilt binary** (Apache-2.0) | We do not write ESP32 firmware, and there is no toolchain here |
| Ours | **Python + `uv`**, `pymavlink` + `pyserial` only | Every extra package is a venue failure mode |
| GCS | **QGroundControl** (`--appimage-extract`) | Independent witness for the demo; `libfuse2t64` already installed |
| Plots | `matplotlib` | Truth-beside-received traces; no web stack |

---

## Next 3 hours — 12:00–15:00

**A = systems/radio** · **B = instrument/analysis**

| Time | A | B | Done when |
|---|---|---|---|
| **12:00–12:15** | **Submit the hardware review** — 3 ESP32 boards, USB-powered; one 2.4 GHz private AP; no LiPo/props/airframe; no soldering. **Ask if a private AP is permitted.** | Gear audit: 2 laptops, hub, cables, **jumpers**, tin | Submission sent, screenshot saved. Jumper presence confirmed |
| **12:15–12:45** | `sudo usermod -aG dialout ops`, re-login. Boot the VM. Start PX4 **SIH** (not Gazebo). Point the GCS instance at the host gateway | Plug in all 3 boards. `esptool chip_id` × 3 boards × every cable. Record MAC, flash size, **module marking (WROOM vs WROVER — decides GPIO16/17)**. Label boards 1/2/3; label cables "data OK" | `notes/sitl.md` with the exact SITL command. `notes/boards.md`. **3/3 boards answer** |
| **12:45–13:15** | **Return-path probe**: from the host, through the *same* socket, send cmd 511 to slow ATTITUDE to 1 Hz | `uv` repo + `pymavlink pyserial esptool`. Freeze `CONTRACT.md` (log JSONL schema, report message, port map) | **COMMAND_ACK = ACCEPTED *and* the measured ATTITUDE rate drops to ~1 Hz.** `import pymavlink, serial` succeeds |
| **13:15–13:45** | Flash prebuilt DroneBridge on board #1. Configure AP mode, channel, **new AP + web passwords**, FC UART GPIOs, baud, low TX power | **Offered-load census**: 60 s capture — per-msgid Hz, bytes/s, packet size, critical-set subtotal | DocBridge config survives a power-cycle. `DECISIONS.md`: headline profile = capacity collapse; metric defs; baud; adapter route; cuts |
| **13:45–14:30** | **Wire + GATE T1.** Adapter (EN→GND) → board 1: GND/TX/RX only. Laptop 1 joins the AP. Then the full chain: SITL → shuttle → RF → laptop 2 → QGC | Same. Then measure lid-closed → recovery (n≥10) and check `NAV_DLL_ACT` | **A vehicle visible in QGC over real RF.** THIS IS THE GATE |
| **14:30–14:50** | Both: `DECISIONS.md` closed out. Export/screenshot the DroneBridge config so board 2 is a drop-in spare | | Every open item closed or explicitly cut |
| **14:50–15:00** | Both: **offline check** — disable internet, confirm SITL→RF→QGC still runs. Pack from the list | | Chain works with no internet |

**If you overrun, cut in this order:** census → QGC install → research.
**Never cut:** the hardware review, the `dialout` fix, the loopback echo test, or T1.

**If T1 fails by 14:30:** stop. Ship the emulated link as primary, bring the boards labelled
honestly, and spend the venue setup window on the emulated path instead. That is a real project,
not a failure.

---

## The 5-hour sprint — 17:00–22:00

| Time | A | B | Gate |
|---|---|---|---|
| 16:15–17:00 | Venue setup: cold start from the RUNBOOK, channel scan once, re-check T1, 2-min venue baseline | | 17:00 |
| 17:00–17:10 | `git tag sprint-start`. Read the cut table aloud. Confirm the contract | | — |
| 17:10–18:10 | Manager actuator: cmd 511 on the shuttle's own socket, manual toggle | `inject.py`: seeded **time-indexed** capacity collapse + drop-tail queue. Ground reports (TT_LINK on the uplink) | — |
| 18:10–18:25 | **GATE T2** — unmanaged degrades to the pre-registered value | | T2 |
| 18:25–19:25 | Closed loop: estimator + hysteresis + probe-up recovery | `analyze.py` + `sweep.py`, join by hash, paired ABAB, bootstrap CI | — |
| 19:25–19:40 | **GATE T3** — one paired run on RF. Choose the sweep path | | T3 |
| 19:40–20:20 | Sweep unattended, n=30 paired (`systemd-inhibit`). **Nobody touches laptop 1** | Build the dashboard on laptop 2 from copies of the live logs | — |
| 20:20–20:50 | Boundary run — predicted failure, confirmed live | Final table + one plot | **20:50 FREEZE** |
| 20:50–21:15 | Record the fallback video (screen + phone video of the boards) | | — |
| 21:15–21:45 | Rehearse ×3, including the radio-pull drill (<30 s switch) | | 2:00 ±15 s |
| 21:45–22:00 | Reset the rig to demo start state. All gear on the table | | **Nobody leaves** (no re-entry after 22:00) |

---

## Prepped = true (the leave-the-house checklist)

- [ ] Hardware review **submitted** + AP question answered
- [ ] `dialout` fixed; **3/3 boards answer `chip_id`**; module marking recorded
- [ ] Board #3 loopback **echoes** (or a USB-TTL adapter is in the bag)
- [ ] SITL SIH boots from a written command; guest→host return path proven
- [ ] cmd 511 probe works against the shuttle's own socket
- [ ] Offered-load census recorded: `L` and `L_crit`
- [ ] Board #1 flashed + configured; config power-cycles clean; board 2 pre-flashed as spare
- [ ] **T1: a heartbeat over real RF**
- [ ] `DECISIONS.md` written; `CONTRACT.md` frozen
- [ ] QGC installed on laptop 2, connects to SITL
- [ ] Offline check passed (no internet)
- [ ] Packed: 2 laptops + chargers, 3 boards, jumpers, ≥4 data cables, hub, tin, tape, mat, printed RUNBOOK, disclosure card, power strip

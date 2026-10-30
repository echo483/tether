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

## Wiring — decide the adapter route BEFORE you wire anything

**Path 1 (preferred): no jumpers, no soldering, no board 3.**
The DevKit's CP2102 is wired to GPIO1(TX)/GPIO3(RX). If DroneBridge lets you configure its FC
UART, set **TX=GPIO1, RX=GPIO3** — the GPIO matrix takes those pins off the UART0 console, so
**board 1's own USB becomes the serial link.** Nothing else needed. Risks: the web UI may refuse
GPIO1/3; the boot ROM prints garbage for ~100 ms; DTR/RTS can reset the board on open.

**Path 2: solder it.** Normal practice; a pin-to-wire joint on a header is not a hack.

```
BOARD 3  (EN tied low → dedicated adapter)
   EN ───solder─── GND            ← 2 joints, permanent, certain. Do this first.
   TX0 ───wire───▶ board1 FC_RX   ← 3 joints, ONLY after the research names the FC UART GPIOs
   RX0 ───wire───◀ board1 FC_TX
   GND ───wire──── board1 GND
```

Cut a male-to-male jumper in half and use the halves as wire. **Never solder the TX/RX wires
before you know board 1's FC UART GPIOs** — desoldering under a hackathon clock is misery.

**Path 3: the breadboard.** Fine for holding boards and strain relief, but a DevKit V1 is too wide
to reliably straddle a standard breadboard's two banks. Don't bet the harness on it.

**Path 4: one 3.3 V USB-TTL adapter.** A single purchase that deletes the problem.

```
  LAPTOP 1 ──USB──▶ [BOARD 3 — held in RESET = plain USB-UART]   ...OR board 1 direct (Path 1)
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

### T1 decomposes into four independent checks

1. SITL emits MAVLink; the host shuttle can read it — **software only**
2. The host can write down the serial port to board 1 — *the only step the adapter route affects*
3. Board 1 carries it over RF; the ground station joins the AP and receives UDP — **one config, testable alone**
4. QGC renders it — **GCS only**

Do 1, 3 and 4 first: they need no adapter decision at all, and they prove T1 is reachable before
you commit to a harness.

**⭐ T1a comes before all of it, and needs no adapter, no jumpers, no second laptop.**
DroneBridge *injects its own heartbeat and RADIO_STATUS in MAVLink mode* so it can register with a
GCS. So: flash board 1, **power it from a wall charger**, put laptop 1 on the AP via its **free
WiFi radio `wlp0s20f3`**, and run QGC — a vehicle appears with no autopilot in the loop at all.
That proves the radio, the AP, the UDP path and the GCS in about 30 minutes, and it is the bulk of
the risk.

**Do not chase QGC on iOS.** The project states iOS "is no longer supported as a standard build"
and daily builds list "iOS currently unavailable". Android and desktop only — so laptop 1 is the
test GCS, not the iPhone.

**T1b** is the same chain with PX4 feeding the FC UART through the adapter.

**Confirmed from DroneBridge's own docs — do not attempt either of these:**
- Configuring the FC UART onto GPIO1/3 **crashes the device.** The firmware will not re-assign
  UART0. So board 1's own USB can never be the flight-controller link.
- `noUARTConsole` firmware is **not published for the ESP32 (Classic)**, so the onboard USB-UART
  cannot be freed either. An external USB-UART on the air side is mandatory.

**Use the official online flasher — `https://drone-bridge.com/flasher/`** in Chrome. No toolchain,
no esptool, no `dialout`. That deletes two failure modes at once.

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

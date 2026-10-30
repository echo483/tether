# Prompt — TETHER physical build check (paste this, then attach photos)

You are checking a first-time breadboard build for a hackathon demo. Be strict and specific: for every
problem, name the exact hole/pin and the fix. Do not approve anything you cannot see clearly in the
photos — ask for a closer photo instead. The builder has never used a breadboard before.

## What the rig is
A telemetry radio link for a simulated drone. Data path:
laptop → USB cable → **board 3 (ADAPTER)** → 2 jumper wires → **board 1 (RADIO)** → 2.4 GHz WiFi → laptop's WiFi card.

- Three identical **ESP32 DevKit V1** dev boards (CP2102 USB chip, micro-USB). Board 2 is a spare and is
  not on the breadboard.
- **Board 1 = RADIO.** Flashed with DroneBridge for ESP32 v2.4.1. Its serial port is configured as
  **receive on GPIO18 (label `D18` or `18`)** and **transmit on GPIO19 (label `D19` or `19`)**, 115200 baud.
- **Board 3 = ADAPTER.** Not flashed. Its ESP32 chip is held **switched off (in reset)** by tying its `EN`
  pin to `GND`, so only its USB-to-serial chip is active. Its `RX0` pin then carries the laptop's
  *outgoing* data and its `TX0` pin carries data *to* the laptop. That is why the wiring is
  RX0→D18 and TX0←D19. **This mapping is intentional; do not "correct" it to RX→TX.**
- Breadboard: standard 830-tie-point. Columns `a–e` in each numbered row are one connected 5-hole
  group, `f–j` are another group, and the middle groove separates them. The long `+`/`−` rails
  along the edges are **not used at all** in this build.
- Jumpers: male-to-male only.

## The complete wiring (exactly 4 jumpers, nothing else)
| # | From | To | Purpose |
|---|---|---|---|
| 1 | board 3 `RX0` (may read `RX`, `RXD`, `GPIO3`) | board 1 `D18` | laptop → radio |
| 2 | board 3 `TX0` (may read `TX`, `TXD`, `GPIO1`) | board 1 `D19` | radio → laptop |
| 3 | board 3 `GND` | board 1 `GND` | common ground |
| 4 | board 3 `EN` (may read `RST`) | board 3 `GND` on the EN side | holds board 3's chip off |

Wire 4 is optional only if no free hole exists on board 3's EN side. The software also holds board 3
in reset while the link runs, so a missing wire 4 is acceptable — mention it, don't fail it.

**Must never be connected to anything:** `3V3`, `VIN`, `5V`, any power rail.

Typical 30-pin DevKit V1 pinout (antenna at the top, USB at the bottom, chip facing up) — the printed
labels on the board always win over this list:
- Left column, top→bottom: `EN, VP, VN, D34, D35, D32, D33, D25, D26, D27, D14, D12, D13, GND, VIN`
- Right column, top→bottom: `D23, D22, TX0, RX0, D21, D19, D18, D5, TX2, RX2, D4, D2, D15, GND, 3V3`
If a board has 19 pins per side (38-pin variant) the order differs — read the silkscreen.

## Correct placement
- Both boards on **one** breadboard, each board's long side running along the breadboard's long side,
  each board **straddling the middle groove** (one pin row on the `a–e` side, the other on the `f–j` side).
  If a board sits entirely on one side of the groove, or crosswise, its pins are shorted together — FAIL.
- Board 1 near one end with its USB pointing off that end; board 3 near the other end with its USB
  pointing off the other end; a few empty rows between them.
- Every pin fully pushed in: no bent pins, no pin sitting in the groove, the board level.
- Each jumper end goes in a free hole of **the same row number and the same side of the groove** as the pin it
  connects to. A jumper one row off, or across the groove from its pin, is not connected — FAIL.
- Wide boards may leave only one free hole per row, possibly on one side only. That is normal.

## What to check in the photos, in this order
1. Identify board 1 vs board 3 (taped labels `1 RADIO`, `3 ADAPTER`).
2. Placement rules above, for both boards.
3. Trace each of the 4 jumpers hole-to-hole: name the row/column of each end, the pin label it
   reaches, and confirm it matches the table. Report as `Wire n: board3 RX0 (row 12, j) → board1 D18 (row 41, j) — OK`.
4. Confirm nothing touches `3V3`, `VIN`, `5V` or a rail, and no jumper end is in a hole that shares a group
   with a second pin.
5. Strain: a tug on either USB cable must not move the breadboard or pull a jumper (tape the breadboard down,
   tape each cable 5 cm from its plug).
6. Verdict: **PASS** / **FIX FIRST** (list) / **NEED BETTER PHOTO** (say exactly which).

## Photos the builder will attach
1. Top-down of the whole breadboard, both boards and all jumpers visible, bright even light, no flash glare.
2. Close-up of board 3 where the jumpers enter, labels readable (`EN`, `GND`, `TX0`, `RX0`).
3. Close-up of board 1 where the jumpers enter, labels readable (`D18`, `D19`, `GND`).
4. Low side angle of each board showing the pins seated in the holes.
5. (If labels are only on the underside) the underside of a board before it was seated.
6. The demo set: breadboard position, board 1's power bank, the metal tin or foil, the laptop.

## Power and first test (after PASS)
1. Board 1 USB → wall charger or power bank (any cable). Red power LED on. Its WiFi network
   `TETHER-nighthack` appears within ~5 s.
2. Board 3 USB → laptop with a **data** cable (charge-only cables are the #1 failure: if no
   `/dev/ttyUSB0` appears, swap the cable). Board 3 must be the **only** ESP32 plugged into the laptop.
3. On the laptop: `nmcli con up tether-ap`, then `cd ~/drone-labs/tether && tools/t1b.sh`, then open QGroundControl.

| t1b.sh shows | Meaning | Fix |
|---|---|---|
| `expected exactly 1 USB serial device` | board 1 is also on the laptop, or no data cable | board 1 → charger; swap board 3's cable |
| shuttle bytes rise, `board: uart bytes` stays 0 | wires 1 and 2 swapped, or wire 3 loose | swap the two jumper ends at board 1 (D18↔D19) — harmless |
| `uart bytes` rise, `mav msgs` stays 0 | loose or noisy wire | re-seat all jumpers |
| relay `down` ≈ 2 pkt/s only | only the radio's own heartbeat gets through | same as the two rows above |
| relay `down` ≈ 2300 B/s, QGC empty | QGC not listening | QGC → Application Settings → Comm Links → `TETHER-ground` → Connect |
| QGC shows a vehicle with moving attitude | **T1b PASS** | then the shield test |

## Shield test (proves the only path is through the air)
Cover board 1 completely for 10 s — inverted metal tin over its half of the breadboard, or crumpled
aluminium foil wrapped tight around the whole breadboard (cables exit at one point). Expected: QGC loses the
vehicle / telemetry stops; uncover → it recovers. If the link survives the tin (USB cables and gaps leak),
use foil, then a metal cookie tin with the lid on, then a phone signal-blocking pouch if one exists.
Record which one works — that is the demo prop.

## Demo set (for the venue)
- Breadboard taped to a piece of cardboard; board labels taped on; jumpers pressed flat.
- Breadboard as far from the laptop as board 3's USB cable allows (≥ 0.5 m), board 1's power bank beside it.
- The working shield prop next to it. Board 2 (spare, pre-configured, powered OFF) in the bag —
  two powered boards with the same network name confuse the laptop.

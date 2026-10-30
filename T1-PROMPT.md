# T1 handoff prompt — paste this into Claude Code on the host

---

## MISSION

Bring up **T1 only**: a MAVLink link from PX4 SITL, out through a real ESP32 radio, into a ground
station. **Do not build the link manager, the estimator, the controller, the fault injector, or
any metrics.** Those are explicitly sprint work and out of scope. This session is component
bring-up and environment only.

**Definition of done:** a vehicle is visible in QGroundControl, and at least one MAVLink message
originated by PX4 has crossed the radio. Record the evidence in `notes/`.

Read `SPEC.md` and `TODAY.md` in this repo first for context. Then work the phases in order.
**Stop and report at the end of each phase**, with the pass criterion stated as passed/failed.

---

## ENVIRONMENT FACTS (verified — do not re-litigate)

| Fact | Consequence |
|---|---|
| Debian 13 host, username `ops`, **no passwordless sudo** | Ask before any `sudo` |
| `ops` is **NOT in `dialout`** | Serial access will fail with EACCES until fixed |
| VM `dronelab` (Ubuntu 24.04, 8 vCPU/12 GB), currently **shut off** | Start with `LIBVIRT_DEFAULT_URI=qemu:///session virsh start dronelab` |
| SSH: `ssh -p 2222 -i ~/.ssh/drone_lab_ed25519 lab@127.0.0.1` | PX4 is **already built** there |
| **Mullvad VPN is connected with Lockdown Mode ON** | It will fight local interface changes. Note it; do not disable without asking |
| All CP2102 boards report serial number `0001` | `/dev/serial/by-id` names collide. Use `/dev/serial/by-path/` or label by port |
| Host has `uv` at `~/.local/bin/uv` | Use `uv venv` / `uv run`; **do not** `pip install` into the system Python |
| `libfuse2t64` is already installed | QGC's AppImage will run; `--appimage-extract` is the fallback |

**Hardware:** 3× ESP32 classic DevKit V1 (CP2102). Only **male-to-male** jumpers are owned; there
are no female-female jumpers. A soldering iron is available.

**Non-negotiable from DroneBridge's docs:**
- The firmware **will not** re-assign UART0. Configuring its FC UART onto GPIO1/3 **crashes the
  device.** Never try it.
- `noUARTConsole` firmware is **not published for the ESP32 (Classic).**
- Therefore the air-side board **cannot** use its own USB for the flight-controller link. An
  external USB-UART is required. Design around that; do not attempt a workaround.
- Dead pins on classic ESP32: **GPIO0, 2, 5, 12, 15**, and 6–11 / 16–17 (flash).
  Safe: **4, 13, 14, 18, 19, 21, 22, 23, 25, 26, 27, 32, 33.**

---

## PHASE 1 — phone QGC + a board, no laptop, no adapter, no autopilot  ⭐ START HERE

This is the highest-value 30 minutes available. It needs one board, one USB cable, and a phone.

1. Record each board's identity before flashing: `chip_id`, flash size, and the **module marking
   on the can** (WROOM vs WROVER — this decides whether GPIO16/17 are free). Label boards 1/2/3
   physically and write it into `notes/boards.md`.
2. Flash board 1 with the **standard** DroneBridge flavour for `esp32` using the **official online
   flasher at `https://drone-bridge.com/flasher/`** in Chrome. No toolchain, no esptool, no
   `dialout` needed. (If the flasher fails, fall back to `esptool.py` inside the uv venv — and fix
   `dialout` first with `sudo usermod -aG dialout ops`.)
3. Power-cycle the board. Confirm the AP appears.
4. **Create a `notes/dronebridge.md`** recording, verbatim from the docs and the web UI:
   - the default SSID and password (the docs and the GitHub README disagree — record what you
     actually see on the air)
   - the gateway IP, and the UDP/TCP ports
   - the firmware version flashed
5. In the web UI (`http://dronebridge.local` or the gateway IP), change **both** the AP password
   and the web-UI password away from the defaults. Record where the new one is kept — **not in
   this repo.**
6. Set the channel to a clearly unused one. Leave TX power low.
7. **Install QGC on the phone:** `https://d176tv9ibo4jno.cloudfront.net/latest/QGroundControl.apk`
   (Android 9+).
8. Join the phone to the DroneBridge AP. **Turn mobile data OFF first** — the DroneBridge docs
   warn the phone will otherwise route over cellular and you will see nothing.
9. Open QGC and let it auto-connect on UDP 14550.

**PASS CRITERION:** QGC shows a connected vehicle. In MAVLink mode DroneBridge injects its own
heartbeat and RADIO_STATUS, so this proves the radio, the AP, the UDP path and the GCS **without
any autopilot in the loop**. Screenshot it.

**Record:** the measured time from power-on to QGC showing connected, n≥3.

---

## PHASE 2 — SITL runs and emits MAVLink  (no radio)

1. Start the VM and SSH in.
2. Locate the PX4 build. Run **SIH, not Gazebo** — SIH is headless and its real-time factor is
   near 1, which matters because an RTF far from 1 corrupts the timing measurements later.
3. Get PX4 running headless with a MAVLink stream on a known UDP port.
4. Confirm from inside the guest that MAVLink is flowing and that heartbeat and attitude streams
   are present.

**PASS CRITERION:** heartbeats observable, attitude present, and **the exact working command
written into `notes/sitl.md`** — copy-pasteable, with the SIH target named explicitly.

**Also record:** the real-time factor, and whether it is close to 1. If it isn't, say so — it
changes how every later latency number must be interpreted.

---

## PHASE 3 — guest → host MAVLink, and the cmd 511 probe  (no radio)

This is the one nontrivial hop in the whole architecture. Prove it before anything depends on it.

1. Point a PX4 mavlink instance at the **host's gateway address** (under `passt` the host is the
   gateway). The default instance talks to the guest's own localhost and nothing leaves the VM.
2. On the host, listen with a small `pymavlink` script inside the uv venv. Do not install
   mavproxy unless it is already available.
3. Verify the **return path**: send something from the host and confirm it lands in the guest.
   The claim is that SITL's continuous stream keeps the NAT mapping alive so no port forward is
   needed. **Verify that claim — do not assume it.** If it fails, add a UDP `portForward` to the
   VM's passt network and restart, and record which was needed.
4. **The cmd 511 probe.** From the host, **through the same socket the shuttle will use**, send
   `MAV_CMD_SET_MESSAGE_INTERVAL` to slow ATTITUDE to 1 Hz. Then **measure** the observed rate.

**PASS CRITERION:** `COMMAND_ACK` returns ACCEPTED **and** the measured ATTITUDE rate actually
drops to ~1 Hz. A command that is acknowledged but has no measured effect is a failed probe —
record it as such, because cmd 511 only affects the mavlink instance that *received* it, and
sending it from the wrong socket is the exact failure this probe exists to catch.

**Also record:** the port map actually in use, and whether RADIO_STATUS is present.

---

## PHASE 4 — the offered-load census  (no radio)

1. Capture 60 s of SITL's MAVLink on the host.
2. Report per-message-ID: Hz, bytes/s, and average packet size. Sort by bytes/s.
3. Report **L** (total offered bytes/s) and **L_crit** (the critical-set subtotal: heartbeat,
   attitude, position, status).

**PASS CRITERION:** `L` and `L_crit` stated with n = 60 s, and the top five chattiest streams
named. These numbers set the fault profile's capacity and the pre-registered prediction, so the
sprint cannot start without them.

---

## PHASE 5 — the adapter decision, then T1b

Only start this once Phases 1–4 have passed. The adapter is required (see environment facts).

**Option A — preferred, zero soldering.** A 3.3 V USB-TTL adapter (CP2102/CH340/FT232) usually
ships with **female-ended jumper wires**, which slide straight onto the ESP32's male pins. Check
first whether one is already owned — many ESP32 kits include one. If yes, that is the whole
solution.

**Option B — free, needs the iron.** Use board 3 as a USB-UART by holding it in reset: tie its
**EN pin to GND**. Its CP2102 is unaffected and becomes a plain 3.3 V USB-UART on the header.
Then wire, using cut-in-half male-to-male jumpers as the wire:

```
board3 EN ──solder── GND
board3 TX0 (GPIO1) ──▶ board1 FC_RX   (the GPIO configured in the web UI)
board3 RX0 (GPIO3) ◀── board1 FC_TX
board3 GND ───────── board1 GND
```

**Test the adapter before trusting it:** with EN tied low, bridge TX0↔RX0 and echo-test at
115200. If bytes do not return, the adapter is not working — stop and say so.

**Then T1b:**
1. Configure board 1's FC UART pins in the web UI to the pins you actually wired, baud 115200,
   serial protocol **MAVLink**.
2. Run the shuttle: read MAVLink from SITL's UDP and write it to the adapter's serial port.
   Bidirectional.
3. Watch QGC on the phone.

**PASS CRITERION:** QGC shows the **PX4 vehicle** — not DroneBridge's injected heartbeat — with
live attitude responding to the simulation. That is T1.

---

## SAFETY AND HOUSE RULES

- **GND, TX, RX only.** Never tie 5V or 3V3 between two USB-powered boards. 3.3 V logic.
- Boards on a non-conductive surface, never on an aluminium laptop.
- **Do not** jam, deauth, sniff, or join any network that is not ours.
- **Do not** flash anything other than the prebuilt DroneBridge binaries. No firmware authoring.
- **Do not** build the manager, estimator, controller, injector, or dashboard in this session.
- **Do not** install an ESP32 toolchain.
- If a phase fails, **stop and report it** rather than improvising a workaround. A clean failed
  gate is worth more than a hacked pass.

## REPORTING

At the end, produce `notes/T1-REPORT.md` stating, per phase: **passed / failed**, the exact
commands used, the observed result, and any assumption that turned out to be false.

Every number gets: method, instrument, n, and how it was measured.

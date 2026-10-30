# TETHER — link-aware telemetry for cheap unmanned systems

**Spec v1.0 — locked.** Night Hack by Founders, Inc. · Fort Mason SF · Fri Oct 30 2026
Check-in 4:15 · Build 5–10 pm · Exhibition 10 pm · Close 11 pm · Team of 2

> **Your drone's data should degrade, not disappear.**

---

## 1. What we own (read this first)

**DroneBridge is our PHY/MAC. We built the transport and policy layer above it.**

Nobody says you "just used Ethernet" when you build TCP. The radio is a component. The value
is the layer that decides *what to send, at what rate, over which path, and what to do when it
breaks.*

This distinction is the pitch. It is also true.

| Layer | Who built it | What it is |
|---|---|---|
| **PHY/MAC** | DroneBridge (Apache-2.0, since 2018) | ESP32 RF link: WiFi / ESP-NOW / LR, AES-GCM-256 |
| **Transport + policy** | **US** | Link estimation, rate adaptation, prioritization, buffering, failover |
| **Application** | MAVLink / PX4 / QGC | Standard telemetry |

### The startup thesis

As unmanned systems get cheap and plentiful — swarms, attritable mass, $7 radios — the
bottleneck moves off the airframe and onto the link. Everyone optimizes hardware. Nobody ships
a software layer that makes a cheap radio behave like a tactical one, and nobody publishes how
these links actually fail.

**The product is the layer, not the radio.** It is transport-agnostic by construction: the same
manager serves ESP-NOW, WiFi, LoRa, or cellular, and one aircraft or twenty. That's the scale
story, and it's free if the interface is designed right.

### What we own, concretely

1. **The Link Manager** — MAVLink-aware transport
2. **The measurement harness** — scripted fault injection + published degradation profile
3. **The interface** — transport- and node-agnostic

---

## 2. The four Ws

**WHO** — a small-unit operator flying a cheap airframe they can afford to lose.
**WHAT** — the link layer between them, plus the instrumentation to measure it.
**WHEN** — at the exact moment the RF environment degrades: congestion, range, interference.
**WHERE** — RF-crowded, indoor, urban, beyond-line-of-sight. Contested spectrum, cheap aircraft.

## 3. Mission

> Give cheap unmanned systems a comms link that **degrades gracefully instead of dying** — and
> prove it with measured numbers.

## 4. Problem statement

Cheap drones link on $7 radios. When the RF environment degrades, the link saturates or drops,
and the operator loses the aircraft with no explanation and no recovery path. Worse, there is
no standard way to measure how a low-cost telemetry link behaves under loss, delay and
congestion — so teams cannot separate a link problem from a software problem, and cannot
improve what they cannot measure.

## 5. Value proposition

- A $7 radio that behaves like a dramatically more expensive link: rate-adaptive, prioritized,
  buffering, failover-capable.
- **A benchmark, not a demo.** Scripted fault injection and published degradation numbers, so
  link behaviour is a measured property instead of a vibe.
- **Transport-agnostic and node-agnostic.** Same layer, one aircraft or twenty.

---

## 6. Architecture

```
   ┌──────────────────────────── the VM ────────────────────────────┐
   │  PX4 SITL ──MAVLink(UDP)──▶ TETHER link manager ──serial──▶ ... │
   │  (real autopilot,           · link state estimation            │
   │   simulated airframe)       · rate adaptation                  │
   │                             · prioritization                   │
   │                             · store-and-forward                │
   │                             · failover                         │
   │                             · fault injector                   │
   └──────────────────────────────┬─────────────────────────────────┘
                                  │ USB (passthrough)
                            ┌─────▼─────┐   RF    ┌───────────┐
                            │ ESP32 #1  │~~~~~~~~▶│ ESP32 #2  │──▶ QGC
                            │DroneBridge│         │DroneBridge│   (device 2)
                            └───────────┘         └───────────┘
```

**Real:** the radio, the encryption, the packet loss, the autopilot (PX4), the GCS (QGC).
**Simulated:** the airframe. This is hardware-in-the-loop **on the comms path** — a standard
and legitimate test setup. We are testing the link, not the flight.

**Limitation to state out loud:** DroneBridge carries telemetry and command only. No video.

---

## 7. The Link Manager — the thing we build

### 7.1 Link state estimation

DroneBridge injects **`RADIO_STATUS`** (message 109) into the MAVLink stream: `rssi`,
`remrssi`, `noise`, `rxerrors`, `fixed`, `txbuf`. That is our link-state input, over a standard
message, for free. No custom telemetry channel required.

Derive per-window: delivery ratio, one-way delay estimate, jitter, buffer occupancy, RSSI
trend. Report with `n` and a CI, like everything else we build.

### 7.2 Rate adaptation — the correct way

Do **not** invent a throttle. Use MAVLink's own mechanism:

**`MAV_CMD_SET_MESSAGE_INTERVAL`** (command 511) sets the interval for a given message ID —
`-1` to disable, µs otherwise. This is exactly how a GCS controls stream rates, and it works on
PX4. Our manager commands the autopilot in MAVLink's own language.

Policy: as the link degrades, protect the critical set (attitude, position, heartbeat, status)
and shed the chatty set (raw sensor streams, high-rate diagnostics). Restore on recovery.

### 7.3 Prioritization

A ranked table of message IDs. Under constraint, low-priority streams are throttled first, and
only ever by `SET_MESSAGE_INTERVAL` — the autopilot stays in control of its own streams.

### 7.4 Store-and-forward

On blackout: buffer local telemetry, flag the gap, burst on recovery. The GCS sees a
discontinuity, not a session loss.

### 7.5 Failover

Two physical paths, one logical stream. When the primary degrades below threshold, switch and
make the switch invisible by buffering across the gap.

*Open item:* the mechanism depends on what DroneBridge exposes. Two candidates —
(a) **channel agility** (one modem pair, manager re-selects channel), cheapest, one ground board;
(b) **dual-path** (two modems, ground device needs two interfaces). Decide after seeing
DroneBridge's API tonight. **Do not let this block L0–L3.**

### 7.6 Fault injector (the instrument)

Scriptable degradation on the link path: **delay, loss, corrupt, blackout**, with a seed for
reproducibility. This is what makes the project a result instead of a demo, and it is the same
instrument we use to *measure*. **Build it early** — it also unblocks development when the
radio isn't cooperating.

---

## 8. Release gates

Same discipline as `autonomy-lab`. A gate is a decision, not a checkpoint.

| Gate | Statement | Pass criterion |
|---|---|---|
| **T0** | Pieces proven separately | QGC flies SITL over plain UDP; both boards flash; serial shuttle loopback echoes |
| **T1** | Radio in the path | QGC heartbeat arrives over real RF |
| **T2** | Instrument works | Injected loss/delay reproducibly degrades the unmanaged link |
| **T3** | Manager works | Managed link sustains ≥2× the delivery ratio of unmanaged under the same profile |
| **T4** | Failover works | Path switch observed by the GCS as a gap, not a disconnect |
| **T5** | Measured | ≥30 runs per fault profile, tabulated with `n` and CI |

**T0–T2 is a complete, honest project.** T3 is what makes it useful. T4–T5 is what makes it a
result.

---

## 9. Measurements

Format is fixed: method, instrument, `n`, statistic with CI, raw log, date. A number missing any
line is not a result.

| # | Metric | Method | n | Gate |
|---|---|---|---|---|
| 1 | Delivery ratio, managed vs unmanaged | fault injector, same profile & seed | ≥30 each | T3 |
| 2 | End-to-end latency p50/p99/max | software timestamps on both ends | ≥10⁴ | T3 |
| 3 | Time to detect degradation | injector trigger → manager action | ≥30 | T3 |
| 4 | Time to recover | fault cleared → pre-fault delivery ratio | ≥30 | T3 |
| 5 | Failover switch time | injector kills path A → stream restored on B | ≥20 | T4 |
| 6 | Bytes buffered / burst on blackout | counters, blackout of fixed duration | ≥20 | T3 |

**Metric 1 is the headline.** Managed vs unmanaged, same conditions, same seed, 30 runs each.

---

## 10. The demo — live, no slides, ~2 minutes

**Set:** the VM driving PX4 SITL. Two ESP32s on the table with LEDs. A second device running
QGroundControl. A dashboard showing link state and the metric.

1. **Fly it.** QGC flying the simulated vehicle **through two real radios.** Heartbeat on screen.
2. **Degrade it.** Inject 20% loss + 200 ms delay. The unmanaged link falls apart — QGC stutters
   and drops.
3. **Manage it.** Enable TETHER. It estimates the link, sheds the chatty streams, protects the
   critical ones. Link returns and holds. Numbers on screen.
4. **Break it.** Full blackout. Store-and-forward. The GCS sees a gap, then a catch-up burst.
5. **Switch it.** Kill path A. Failover. The GCS never drops the session.
6. **The table.** Delivery ratio and p99 latency, managed vs unmanaged, `n≥30`.

**Fallback (required by the posting):** if the radios fail entirely, run the manager and
injector against an emulated link. Same code, same numbers. Say so, don't hide it.

---

## 11. Hardware — what we actually have

**3× ESP32 classic DevKit V1** (CP2102, `/dev/ttyUSB0`). From the DroneBridge docs:

- Classic ESP32 is supported but **not recommended for new builds**
- **`noUARTConsole` firmware is not available** for classic ESP32 → UART0 stays the console
- Pins that don't work: GPIO0, GPIO2, GPIO5, GPIO12, GPIO15; **GPIO16-17 flagged as SPI flash**

**Implication:** the FC UART must be mapped to free GPIOs on a second UART. Verify against the
flashed build's pin map — don't assume a generic tutorial's numbers.

**Serial into the second UART:** the board's only USB port is the console. Options:
- (a) a USB-TTL adapter (~$10, in person only)
- (b) **a third V1 flashed as a USB↔UART passthrough** — ~20 lines, zero purchases

**Everything runs in the VM.** No host/VM split. That requires **USB passthrough** of the ESP32
into the VM. Note: `passt` user-mode networking means the guest **cannot associate with a WiFi
AP** — so the VM reaches the radio over USB, and the second device (QGC) joins the radio's AP.

---

## 12. Risks

| Risk | Mitigation |
|---|---|
| Classic ESP32 pin/console limits | Verify the build's UART pins tonight. Passthrough-board fallback for serial |
| VM cannot join a WiFi AP (passt) | USB passthrough the ESP32 into the VM; GCS on a second physical device |
| Default streams already saturate the link | Characterize the baseline first — that **is** the control condition |
| Failover mechanism unclear | Don't let it block L0–L3; decide after reading DroneBridge's API |
| "You just flashed someone's firmware" | Lead with the manager + the numbers. §1 is the answer |
| Scope creep into flight/autonomy | Stay on the link. PX4 is a vehicle, not a project |
| Venue RF congestion | Pick a clear channel; never touch the venue network |
| Hardware review not submitted | **Submit tonight.** This is the only disqualifying item |

---

## 13. Explicitly out of scope

Video, autonomy, BVLOS flight, real airframes, video encoding, payload work, and anything that
requires a part we don't already own. Every one of these costs a gate.

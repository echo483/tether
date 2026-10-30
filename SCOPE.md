# TETHER — scope lock v3 (Fri Oct 30, 12:45)

Supersedes the sprint sizing in SPEC.md v2 (SPEC stays the reference for mechanisms).
**Rule: KISS. Something demoable exists at every cut line. Submit at 22:00 no matter what.**

## One line
TETHER keeps a drone operator's picture **fresh** on a $7 radio: it measures staleness from what
actually arrives, and tells PX4 — in MAVLink's own command — what to stop sending.
Claude turns operator intent into the priority policy; the deterministic loop enforces it.

## What we own (the build layer) vs what we use
| Ours (built 17:00–22:00 unless marked prep) | Not ours (credited) |
|---|---|
| `air.py` shuttle: UDP↔serial, bounded queue, seeded capacity squeeze (disclosed) — passthrough core is **prep** | PX4 SITL (SIH) — BSD-3 |
| `ground.py`: picture age (AoI) from `time_boot_ms` delay gradient, seq-gap loss, goodput → JSONL | DroneBridge for ESP32 (PHY/MAC) — Apache-2.0 |
| `manager.py`: tiered shedding via cmd 511, hysteresis, probe-up restore | QGroundControl (independent witness) |
| `dash.py`: giant PICTURE AGE number, 30 s trace, tier strip | Claude API |
| `copilot.py` (stretch): intent → validated policy JSON; incident report from the log | |

## Topology — single host primary
`PX4 SIH ─UDP→ air.py ─serial→ [board 3 in reset = USB-UART] → board 1 (DroneBridge AP) ~~2.4 GHz~~ laptop WiFi (wlp0s20f3) → ground.py → QGC (UDP 14560)`
One laptop, one clock, one env. The RF hop is real: the tin over board 1 breaks it.
Laptop 2 = teammate's dev box (dash/copilot/pitch against recorded JSONL); becomes the pilot
screen only if it runs `ground.py` + QGC cleanly by 19:30.

## Tiers and cut lines
| Tier | Done when | Cut / fallback at |
|---|---|---|
| **T0 floor** | PX4 vehicle in QGC **through our layer** over real RF; live PICTURE AGE number | 18:00 → emulated link (UDP↔UDP in air.py), "EMULATED" banner |
| **T1 feature** | squeeze → stale as predicted; manager on → fresh | 19:15 → operator-triggered shedding (one key) |
| **T2 result** | n=10 per arm, interleaved ABAB, mean ± t-CI; one boundary run (C < L_crit) fails as predicted | 20:15 → report n achieved |
| **T3 stretch** | Claude intent→policy + incident report | 20:15 hard cut → "AI offline, default policy" |
| — | **20:50 code freeze** · 21:15 fallback video done · 21:45 rig reset | |

## Cut tonight (with the mechanism)
- **Failover** — needs a second bearer; 3 boards = radio + adapter + spare, and single-host failover is a loopback. QGC already switches links.
- **ESP-NOW** — consumes all 3 boards, leaves no spare.
- **30 paired runs, U1 as a full arm, bootstrap, emulator-vs-UART validation** — n=10 paired fits in 15 min; U1 = one run.
- **LLM in the control loop** — 1–3 s per call vs a 200 ms loop, and it dies with the internet.

## Port map (confirm against notes/T0-REPORT.md)
| Socket | Bind | Peer |
|---|---|---|
| PX4 GCS instance | PX4 | → air.py 127.0.0.1:14550 |
| air.py serial | /dev/serial/by-path/… (board 3) | 460800 or 115200, set = DroneBridge |
| ground.py radio side | wlp0s20f3 ephemeral | ↔ 192.168.2.1:14550 (registers by sending first) |
| ground.py GCS side | 127.0.0.1 | → QGC 127.0.0.1:14560 |
| QGC | UDP 14560, autoconnect OFF | — |

## Harness (board 3 held in reset = plain USB-UART)
With board 3's ESP32 in reset its header labels are the dead chip's view, so wire **same-to-same**:
```
board3 EN  ── board3 GND          (hold in reset)
board3 RX0 ──▶ board1 GPIO16 (DroneBridge UART RX)   ← laptop data out
board3 TX0 ◀── board1 GPIO17 (DroneBridge UART TX)   ← radio data in
board3 GND ─── board1 GND          (never 5V / 3V3)
```
The TX0↔RX0 loopback test passes regardless of this mapping — it cannot catch a swap.
Can marked WROVER (PSRAM on 16/17)? → set TX=33 / RX=32 and wire to those instead.

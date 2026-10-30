# TETHER — demo run sheet, pitch, disclosure card

Live, no slides, 2:00. Rehearse ×3 at 21:15. Numbers in ⟨brackets⟩ are filled from measurements
(PREREG.md / results), never from memory.

## The set
- Laptop 1: QGC left half, `dash.py` right half — giant **PICTURE AGE** number (green < 0.5 s,
  red > 1 s), 30 s trace, tier strip, an **"impairment: synthetic, seeded"** label whenever the
  squeeze is active.
- The breadboard (board 1 = radio, board 3 = adapter, 4 jumpers) taped to cardboard as far from the
  laptop as board 3's USB cable allows; board 1 on its own power bank; the shield prop that passed the
  shield test (tin / foil) beside it. See PHYSICAL.md.
- A printed disclosure card (below) and a card with the pre-registered prediction.

## Run sheet
| t | Action | What it proves | Line |
|---|---|---|---|
| 0:00–0:10 | Drone flying a loop in QGC; age 0.0x s | baseline | "A dropped link tells you. A stale link doesn't." |
| 0:10–0:30 | **Judge closes the tin.** Dash → BLACKOUT. Open → recovers in ⟨t_rec⟩ s | the only path is RF, and their hand broke it | "Real PX4 flying a simulated quad. The radio is DroneBridge — open source, not ours. The only way from the autopilot to this screen is through the air. Close the lid." |
| 0:30–0:55 | Squeeze capacity, TETHER **off**. Read the prediction card first | the dangerous failure: QGC says *connected* while showing the past | "We can't stand a kilometre apart, so we squeeze capacity in software — seeded, disclosed. Prediction: ⟨K/C⟩ s stale within ⟨t_fill⟩ s. … There it is. Still says connected." |
| 0:55–1:20 | TETHER **on** | the mechanism; prediction confirmed | "TETHER measures staleness from what actually arrives, and tells PX4 in MAVLink's own command what to stop sending. Don't trust our dashboard — that's QGC's own inspector showing those streams at zero." |
| 1:20–1:42 | **Branch by judge.** Founder/VC: type intent into the copilot → policy changes → tier strip moves. Engineer: step C below the critical set → **TETHER fails too, as predicted** | AI sets policy, deterministic loop enforces it / the boundary, measured | VC: "Claude turns what the operator cares about into a priority policy. It never sits in the control loop — the loop runs at 5 Hz, a model call takes seconds." Eng: "We don't create bandwidth. We decide who gets it — and here's where that stops working." |
| 1:42–2:00 | Results table on screen | it's a result, not a vibe | "⟨n⟩ paired runs through this radio tonight: unmanaged p99 age ⟨x⟩ s, TETHER ⟨y⟩ s, 95% CI ⟨…⟩. Raw logs in the repo." |

**Recovery arithmetic for pacing:** onset ≈ K/(L−C) s to fill; stale level ≈ K/C; drain after
shedding ≈ Q/(C − L_after). Narrate the drain as a countdown, don't hide it.

**Fallbacks (each one command, < 30 s):** board 1 dies → board 2 (pre-flashed, `tools/db_apply.sh`)
· radio path dies → `air.py --emulated` + "EMULATED LINK" banner · closed loop broken →
operator-triggered shedding key · everything broken → fallback video (recorded by 21:15).

## Likely questions — answers in one breath
- *"Isn't that just setting the data rate?"* — A static rate is wrong in both directions when
  capacity moves: tuned for good conditions it bloats, tuned for bad it wastes. ⟨U1 run result⟩.
- *"Doesn't PX4/ArduPilot already do this?"* — ArduPilot has done radio-buffer flow control on SiK
  radios for a decade; PX4 scales streams uniformly. Ours decides from what *arrived*, sheds by
  priority, and publishes a benchmark.
- *"Why not just use the AI to control it?"* — Latency and availability. The model proposes, the
  loop enforces; if the API is down the default policy runs.
- *"Is the loss real?"* — The tin is real. The squeeze is synthetic and labelled. No video — telemetry only.

## Disclosure card (print it)
> **Built before 17:00 (prep):** PX4 SIH environment, DroneBridge flash + config (prebuilt, not ours),
> serial harness, a dumb UDP↔serial passthrough, bring-up probes (rate command, traffic census),
> the interface contract, the pre-registered prediction.
> **Built 17:00–22:00 (sprint):** the capacity squeeze, staleness measurement, the TETHER manager,
> the dashboard, the Claude policy copilot, every run and result shown.
> **Not ours:** PX4 (BSD-3), DroneBridge for ESP32 (Apache-2.0), QGroundControl, Claude API.

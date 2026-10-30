# TETHER: demo and pitch review

Reviewed 2026-10-29 against `SPEC.md` v1.0, `SETUP-TONIGHT.md`, and the two sibling reviews.
No internet was used.

This review **assumes the fixes in `REVIEW-ARCHITECTURE.md` / `REVIEW-DELIVERY.md`**: the
capacity-collapse profile, a ground agent, AoI as the headline, a single-host sweep, failover
cut, and latest-value-wins in place of FIFO store-and-forward. It does not argue them again. It
covers only what the judge sees, hears and touches.

Tags: **[A]** arithmetic, with output from `review/demo_pacing_sim.py` (illustrative stream mix,
L = 8.84 kB/s, L_crit = 1.12 kB/s; re-run it with tonight's census) · **[K]** from memory,
confidence stated · **[U]** unverified, with the check that settles it.

---

## (a) Verdict

**Live: yes. Visible: barely. Tangible: no.** As specced, the radio is a USB extension cord
with an LED.

Why it will read as shallow, most damaging first:

1. **The radio has no effect on anything the judge sees.**
   - Every fault is injected in software, upstream of the radio.
   - At 1–3 m the ESP32 link has tens of dB of margin, so it behaves like a wire.
   - Swap the radio for a cable and every beat looks identical. A judge who asks "what changes
     if you replace that with a wire?" has ended the demo, and "nothing" is the honest answer.
   - This is the root of the "laptop doing laptop things" worry. Better visuals don't fix it.
     The fix is to make the radio **causally necessary** to one thing the judge does with their
     own hands.
2. **Beat 2's failure probably won't show up, and TETHER couldn't fix it if it did.**
   - At 20% i.i.d. loss, P(at least one run of 3 lost heartbeats in a 120 s demo) = **0.53**.
     For a run of 4 it is **0.14** **[A]**. QGC's comm-lost flag is a coin flip.
   - 200 ms of delay can't be seen.
   - Shedding can't change either effect.
3. **Every cause is a keypress.** Nothing on the table moves, glows or responds. A judge sees
   the team type and a number change, which is exactly a laptop doing laptop things.
4. **The visible effects are too small to read from 2 m in a loud hall:**
   - QGC's HUD at 20 Hz vs 16 Hz;
   - a 200 ms delay;
   - a table of numbers at the end. Nobody reads a table standing in an aisle.
5. **Six beats in 120 s, and the three weakest come last:**
   - Store-and-forward and failover are the hardest to see.
   - They are also the most exposed to prior art: QGC already does multi-link switching **[K,
     fairly confident]**.
   - A FIFO "catch-up burst" makes QGC show the past as the present. That is a visible bug, not
     a feature: **9.9 s** of stale picture after an 8 s blackout, against **0.1 s** with
     latest-value-wins **[A]**.
6. **The strongest real evidence never reaches the screen:**
   - PX4 acknowledging a MAVLink command from *your* code;
   - a number you predicted before pressing the key.

**Worth keeping.** Real PX4, real QGC, and a real radio in the path. A MAVLink-native lever
(cmd 511). And measurement discipline. A predicted failure confirmed live is something almost no
other team out of 120 will have. The fault is the staging, not the substance.

---

## (b) The redesigned 2-minute demo

**Design rule:** give the judge
- one physical cause they perform with their own hands (**the lid**),
- one synthetic cause you disclose (**the squeeze**),
- one number (**pilot lag**),
- one prediction you confirm, and one failure you predict.

### The set

Two laptops, plus one radio that has a cable to the drone laptop only.

```
                          AISLE  (judge stands here)
 ┌──────────────────────────────────────────────────────────────────────┐
 │ [RADIO]  [TIN]          ~1.5–2 m of air           [LAPTOP 1] [LAPTOP 2]│
 │ board1+3  "close         ──────────────►           "DRONE"    "PILOT"  │
 │ on a box   the lid"                                truth dial  QGC +   │
 │  │                                                            lag dial │
 │  └──── USB, taped along the back edge, to LAPTOP 1 ONLY        [♥ cup] │
 └──────────────────────────────────────────────────────────────────────┘
```

**Laptop 1, "DRONE".** Runs PX4 SITL, the shuttle and the injector. The screen shows:
- one huge heading (or roll) dial: what the drone is doing now;
- a strip below it: `commands received over the air from TETHER` (511s as PX4 receives them).

**Laptop 2, "PILOT".** Its WiFi is on the DroneBridge AP, and it has **no cable to the drone
side**. The only cable it has goes to the ♥ LED board.
It runs the ground agent, TETHER's decision side, and QGC. The screen shows:
- the same dial, driven only by what came over the air, next to laptop 1's dial;
- a giant **PILOT LAG** number;
- the RF strip and the load bar (see (c)).

**Why two devices, when the sibling reviews say one host:**
- **Keep the sweep on one host**, for the single clock.
- **Use two devices for the live demo.** A passer-by can see that the only link between the
  drone and the pilot is the air.
- **Same ground-agent code on either machine.** On laptop 2, AoI comes from the
  `time_boot_ms` delay gradient. The offset cancels, so no clock sync is needed.
- **Disconnect laptop 1's WiFi from the AP in the demo configuration.**
- **Cut line 21:00:** if the two-device setup isn't solid by then, demo single-host with a
  labelled split screen.

### Run sheet

| t | Action | What the judge sees | What it proves | Line (say it, short) |
|---|---|---|---|---|
| 0:00–0:08 | — | Both dials moving together, lag 0.04 s | — | "A dropped link tells you. A stale link doesn't. Watch." |
| 0:08–0:30 | **Judge closes the tin lid** over the radio | Pilot dial freezes and the drone dial keeps turning. RF strip falls off a cliff. QGC shows *Communication lost*, the ♥ LED stops. Open the lid: it comes back in the time you measured that morning | The only path is RF. Our software can't fake this, because your hand did it | "That's real PX4 code flying a simulated quad. The radio runs DroneBridge, open source, not ours. The only way from that laptop to this one is through the air. Close the lid." |
| 0:30–0:55 | Key: **squeeze**, TETHER **off** | Load bar: offered 8.8 kB/s into a 2.0 kB/s pipe. **Within ~1 s** the pilot dial trails the drone dial. PILOT LAG climbs and stalls at ~3 s, in red. QGC still says *connected* | The dangerous failure: alive but showing the past | "We can't stand a kilometre apart in here, so we squeeze capacity in software: seeded, scripted, disclosed. Prediction: three seconds stale, within two seconds. … There it is. QGC still thinks it's fine." |
| 0:55–1:20 | Key: TETHER **on** | Decision log: `shed HIGHRES_IMU, ATTITUDE_TARGET … cmd 511 → ACCEPTED`. The load bar drops under the line. A **predicted drain countdown** runs (≈6 s) and the lag returns to 0.04 s, so the dials lock together | The mechanism, and the prediction confirmed | "TETHER sees the backlog at the pilot's end and tells PX4, in MAVLink's own command, what to stop sending. The backlog drains in six seconds, which we predicted. Don't trust our dashboard. That's QGC's own inspector showing those streams at zero." |
| 1:20–1:42 | **Pick one**, by judge type. **Engineer:** step C to 0.6 kB/s, below what the critical set needs. **Founder:** release the squeeze and squeeze again with TETHER on | **Engineer:** "Prediction: even TETHER goes stale now." Lag passes 1 s in ~2 s, as predicted. **Founder:** the lag blips and recovers, with nothing for the pilot to notice | **Engineer:** the boundary, measured, not hidden. **Founder:** the "nothing happens" moment | **Engineer:** "We don't create bandwidth. We decide who gets it, and here's where that stops working." **Founder:** "That's the product: the pilot never notices." |
| 1:42–2:00 | Point at laptop 2's receipts pane | One line: *pilot lag p99 at 2 kB/s: unmanaged X s · TETHER Y s · n = 30 paired runs through this radio · 95% CI · logs/…* | It's a result, not a demo | "Thirty paired runs through this radio tonight, raw logs in the repo. When the link gets bad, send what matters." |

- **The 30-second version**, for when a judge is moving fast: lid (10 s) → squeeze then TETHER
  on (15 s) → the number (5 s).
- **Walk-by attract loop.** Between judges, script the squeeze/on/off cycle every ~60 s, so a
  passer-by always sees the dials split and rejoin and the big number turn red, then green.
  - Never run the attract loop during the sweep.
  - Tag exhibition runs separately. Never pool them into n.
- **Optional judge interaction**, rehearse it first: the judge clicks *Go to location* in QGC
  during the squeeze. The drone dial moves now; the pilot's view moves ~3 s later.
  - If QGC reports *vehicle did not respond* because the ACK is stuck in the queue, point at it.
    It's a real operator failure **[K, medium: QGC ACK timeout ~3 s with retries, so rehearse]**.

### Pacing: choosing what the failure looks like [A]

The emulated radio buffer K sets what the judge sees. **K is a demo decision, so choose it and
justify it.** Values for C = 2 kB/s:

| K | Unmanaged, as the judge sees it | TETHER on, 511 only | Fresh after "on" |
|---|---|---|---|
| 0.5 s × C | Lag 0.55 s, max heartbeat gap 2.1 s. **Barely visible** | p99 0.07 s | 0.7 s |
| **3 s × C** | **Lag > 1 s after 1.2 s, steady at 3.0 s**, max heartbeat gap 3.6 s | p99 0.07 s | **6.4 s** (fluid K/(C−L_crit) = 6.8 s) |
| 20 s × C | Lag 17–20 s, which is dramatic | Still stale **25 s later** (drain ≈ 45 s) | Dead air |

- **Use K ≈ 3 s × C.** It is visible within a second, and the drain is short enough to narrate
  as a countdown.
- **Name where that buffer size comes from**, or show the K/C line, lag against K, as a
  measured plot.
- **If TETHER owns an air-side queue**, latest-value-wins on that queue brings "fresh after on"
  down from 6.4 s to ~0.7 s.
- **The boundary beat needs C well below L_crit to fail inside 20 s.** At C = 1.0 kB/s managed
  lag takes 8.8 s to pass 1 s. At 0.6 kB/s it takes 2.0 s **[A]**.

### Demo-killers to check before 17:00 (new; not in the sibling reviews)

1. **Datalink-loss failsafe.**
   - The lid also cuts QGC's uplink heartbeats. If `NAV_DLL_ACT` is enabled, the first lid
     closure sends the drone home or lands it. The next judge then sees a parked vehicle.
   - Check `NAV_DLL_ACT` and `COM_DL_LOSS_T` **[K, fairly confident on the names]**.
2. **The mission must loop and keep turning.**
   - Use DO_JUMP with a large repeat count over a lawnmower pattern. The 180° heading steps make
     lag obvious.
   - A constant-bank orbit makes lag *invisible*.
   - Check that the sim battery can't trip a failsafe over 6 h **[U]**.
3. **Reset the stream rates between arms.**
   - cmd 511 intervals persist in PX4. After any managed run, send param2 = 0 (the default rate)
     and *verify the measured rate* before the next unmanaged demo.
   - Otherwise the "unmanaged" run is already throttled and the A/B looks rigged.
4. **WiFi re-association after the lid.**
   - Set a static IP on the AP connection (no DHCP) and pin the BSSID.
   - Measure lid-open → first frame, n ≥ 10, in the morning, and quote it as the prediction.
5. **No WiFi scans on the pilot interface during runs.** Off-channel time looks exactly like a
   link fault. Do the venue channel scan once, at 16:15.

---

## (c) Making the RF legible

Ranked by value per minute. The sprint-minute estimate assumes the core plumbing already exists.

| # | Item | Its job (not decoration) | Cost | Build |
|---|---|---|---|---|
| 1 | **Metal tin with a lid** over the radio, with a "close the lid" card | The only physical, judge-performed, real-RF fault. It proves the path is through the air | $0–5 (a cookie tin) | **Prep:** a 10-min test tonight |
| 2 | **Two side-by-side dials**, drone vs pilot, ≥ ⅓ of each screen | The gap between them *is* the staleness, readable at 3 m with no explanation | $0 | 30 min |
| 3 | **PILOT LAG**, ~200 px, red > 1 s, green < 0.3 s. Subtitle "age of attitude at the GCS" | One number for the aisle | $0 | in #2 |
| 4 | **RF strip** from laptop 2's own NIC: `iw dev <if> link` / `station dump` at 2–5 Hz → signal dBm, tx/rx bitrate, retries | Real RF numbers, independent of DroneBridge's RADIO_STATUS and of your injector. A hand over the PCB antenna produces a visible dip | $0 | 20 min **[K: fields are standard; U: unprivileged on this kernel]** |
| 5 | **Offered-vs-capacity bar** (kB/s) plus the stream table with shed rows struck through | Shows *why*: 8.8 into a 2.0 pipe is arithmetic, not a vibe | $0 | 20 min |
| 6 | **Decision log** with PX4's COMMAND_ACK, mirrored on laptop 1 as "received over the air" | The mechanism is attributable to your code | $0 | 10 min |
| 7 | **♥ heartbeat LED**: spare board2 with MicroPython (esptool only, no toolchain), blue LED on GPIO2, under an inverted white paper cup. The ground agent writes 1 byte per received HEARTBEAT | Physical "the pilot hears the drone" that you can read without looking at a screen. It stops under the lid and stutters under the squeeze | $0. Board2 stops being the spare; re-flashing DroneBridge takes 3 min | **Prep:** flash MicroPython. **Sprint:** 20 min |
| 8 | Labels: "AIRCRAFT RADIO · DroneBridge (not ours) · 2.4 GHz", "DRONE", "PILOT" | Disclosure in the physical world | $0 | 5 min |

- **On screen: items 2–6 and nothing else.**
- **Hide** the VM console, the terminals and the editor.
- **Add one footer:** `radio firmware: DroneBridge (Apache-2.0, not ours) · tether/: N LOC, M
  commits since sprint-start`.
- **Where the time comes from:** the delivery plan's 7:40–8:20 dashboard slot covers #2/#3/#5/#6.
  Add #4 and #7 only after T3 passes.

**Prep: the tin test tonight.** Close the tin over the radio, then read laptop 2's `iw` signal
and frame arrivals.

Ladder:
1. Lid closed over the radio and its cable entry.
2. Foil wrapped over the cable notch.
3. Lowest DroneBridge TX power, if the UI exposes it **[U]**.
4. If none of those gives a clean blackout: the judge **pulls the radio's USB**. It's
   undeniable, but it isn't RF, so say so.

**Considered and rejected:**
- **Coupling real RSSI to the synthetic capacity.** It makes the physical and the synthetic
  impossible to tell apart, which is the opposite of what you're selling.
- **A congestion-generator ESP32 or a "jammer".** Illegal or antisocial in a shared hall
  (sibling review).
- **A cardboard drone carrying the radio.** A prop that invites a safety re-review.
- **A servo with a cardboard plane.** Only if you already own an SG90 *and* can amend the
  hardware review tonight. It also risks brownouts on laptop USB.
- **Sound.** The hall is too loud.
- **The pull-the-cable failover moment.** QGC already does it, and it needs a second path.
- **A results table as a demo beat.** It goes on the receipts pane, as one line.

---

## (d) Pre-empting "you just flashed someone else's firmware"

1. **Say it first, proudly, in the first beat.** A disclosure the judge drags out of you sounds
   like a confession. Volunteered, it is credibility.
2. **The A/B is the proof.** Same radio, same firmware, same seed, one variable. Whatever changes
   on screen is your code, by construction. Say it in exactly those words.
3. **Show artifacts the radio can't produce:**
   - PX4's COMMAND_ACK to your 511s, on both laptops;
   - QGC's MAVLink Inspector, an independent witness, showing the shed streams at 0 Hz;
   - a number you predicted before pressing the key.
4. **Receipts on laptop 2, on request:**
   - `git log --oneline sprint-start..`
   - the LOC of `tether/`
   - the raw log directory
5. **Concede prior art before an engineer raises it**, after verifying it tonight with the
   sibling review's `grep`:
   - "PX4 can scale all its streams down uniformly. ArduPilot has done flow control on SiK
     radios for years."
   - "We shed by priority, decide from what actually arrives at the pilot's end, and publish the
     degradation curve."
6. **The one line to rehearse:** *"DroneBridge moves bytes; it doesn't know what a heartbeat is.
   TETHER decides which bytes."*

---

## (e) Tagline and one-liner

**"Your drone's data should degrade, not disappear."**
- **It describes the wrong failure.** Your own demo shows the dangerous case isn't
  disappearance, which QGC announces. It's silent staleness while QGC says *connected*.
- **"Data"** makes people think of video, which you don't carry. You've handed them the obvious
  objection.
- **"Should"** is an aspiration, not a claim.
- If you keep it, cut it to **"Degrade, don't disappear."**

**"Link-aware telemetry for cheap unmanaged systems"** is jargon. "Link-aware" means nothing to
half the room.

**"DroneBridge is Ethernet, TETHER is TCP"** works against you with any networking engineer:
- TCP's reliable, in-order delivery is exactly wrong for state telemetry. Head-of-line blocking
  *is* the staleness you're fixing.
- Your own FIFO replay result, 9.9 s stale, is the TCP behaviour.
- Replace it with: *"DroneBridge moves bytes; TETHER decides which bytes."* Or, for the VC
  crowd: *"What a video call does on bad WiFi (drop the extras, keep the call), for drone
  telemetry."*

**Use these:**
- **Hook (first line):** *"A dropped link tells you. A stale link doesn't."*
- **Tagline:** *"When the link gets bad, send what matters."*
- **One-liner:** *"TETHER sits between a cheap drone's autopilot and its radio. When the link
  gets squeezed, it measures what's reaching the pilot and tells the autopilot, in MAVLink, what
  to stop sending, so the pilot's picture stays current. Thirty paired runs say it works, and
  where it stops working."*

**Strike from anything you say out loud:**
- "a $7 radio that behaves like a tactical link". Tactical radios buy range, anti-jam and MIMO,
  and software can't. A defence-literate judge will say so.
- "contested spectrum". You don't test it. Say "crowded spectrum, like this hall", and quote the
  number of APs from the 16:15 scan.
- "1 km" and "150 m". Those are DroneBridge's numbers, not yours.
- "AES-GCM", unless you're in ESP-NOW mode.
- "the scale story is free".

---

## (f) Fallback if the radios die

Decide by what died. Rehearse each switch as one command, under 30 s.

| Failure | Fallback | Still tangible? | Label on screen |
|---|---|---|---|
| Board1 dies | Board2, **pre-flashed with an identical DroneBridge config** (screenshot or export the config tonight). If board2 is the ♥ LED, re-flash it (3 min) and lose the LED | Yes, unchanged | none |
| Adapter, serial or ESP32 path dies, WiFi fine | **Phone hotspot as the RF path.** Laptop 1 → phone → laptop 2. The phone goes **in the tin** with no cable, which is a cleaner blackout than the ESP32. The shuttle's sink switches serial → UDP, which proves the "transport-agnostic" claim. **Test tonight:** both laptops on the hotspot, ping both ways (client isolation **[U]**) | Yes | "RF path: phone hotspot (ESP32 down at HH:MM)" |
| All RF dead, or the chain unstable after 21:00 | Single-host **emulated link**, same code. Laptop 2 plays the **phone video recorded 21:00–21:15** of the real radio: lid, hand-over-antenna dip, squeeze, TETHER on. Plus the RF-run raw logs | Partly: the video carries the physical part. The prediction, the boundary and the lag dials all survive live | "EMULATED LINK" banner, permanently on |
| Closed loop broken (T3 missed) | Demo the instrument: the predicted unmanaged collapse confirmed, the K/C line, then **operator-triggered** 511 shedding to show the lever works by hand | Yes | "manual trigger: loop not closed" |

**Two corrections to the spec's fallback (§10):**
- Not "same code, same numbers". Numbers measured on an emulated link are a different
  measurement. Keep two tables and never mix them.
- "Say so, don't hide it" is correct. Put it in a banner, not a sentence you might forget.

---

## Build budget, demo-specific only

| When | What | Who / time |
|---|---|---|
| Tonight | Tin test; phone-hotspot ping test; MicroPython onto board2 (blink only); export the DroneBridge config; check `NAV_DLL_ACT`; plan the looping lawnmower mission | ~40 min, substrate only |
| Morning | Measure lid → recovery (n ≥ 10); static IP and BSSID pin; set up laptop 2's uv env; time the cold start | ~30 min |
| 7:40–8:20 | Dials, PILOT LAG, load bar, decision log (on laptop 2, while the sweep runs) | 1 person, 40 min |
| After T3 | RF strip (20 min), ♥ LED (20 min), attract loop (10 min) | Cut any of them without regret |
| 21:00 | Two-device go/no-go; record the fallback video | Both |
| 21:15–21:45 | Rehearse ×3: the engineer variant, the founder variant, and the radio-death drill | Both |

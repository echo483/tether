# TETHER — tonight's setup

**Goal tonight: prove the pieces separately and go to sleep.** Nothing here is the project.
Nothing here is sprint work. Tonight buys you a calm Friday.

**Do not tonight:** flash DroneBridge, wire anything, or attempt a radio link. Those are tomorrow.

---

## 0. Before anything else — 5 minutes

- [ ] **Submit the hardware review to the organisers.**
      Two USB-powered ESP32s, no LiPo, no props, no soldering. Declare the 2.4 GHz radios.
      *This is the only item on this page that can disqualify you.* Do it first.

---

## 1. The VM boots and PX4 runs

The VM is `dronelab`, currently shut off. 8 vCPU / 12 GB / 120 GB, SSH on
`[IP_ADDRESS]:2222` with `~/.ssh/drone_lab_ed25519`. PX4 is **already built** —
`bin/px4` exists and the build log ends `rc=0`.

```sh
LIBVIRT_DEFAULT_URI=qemu:///session virsh start dronelab
ssh -p 2222 -i ~/.ssh/drone_lab_ed25519 lab@[IP_ADDRESS]
```

- [ ] VM boots; SSH works
- [ ] `~/PX4-Autopilot/build/px4_sitl_default/bin/px4` exists
- [ ] **Pass criterion:** PX4 SITL starts and the console shows a vehicle booting.
      Confirm the actual make target for this build — `px4_sitl` may default to Gazebo, which
      is heavier than we need. **SIH is the lighter target and is enough for a MAVLink source.**
      Write down the exact command that works.

## 2. MAVLink is on the wire

- [ ] Confirm SITL is emitting MAVLink (the console usually reports the UDP port, typically 14550)
- [ ] Watch packets arrive — `mavproxy.py` or `pymavlink` is enough to prove it tonight
- [ ] **Pass criterion:** you can see a heartbeat and an attitude message with your own eyes

*(pymavlink/pyserial are not installed on this host. Install them where you'll work — in the VM.)*

## 3. QGroundControl

- [ ] Install QGC. AppImage is fine — you already use that pattern (`~/Applications/`).
- [ ] Connect it to SITL over plain UDP — **no radios involved**
- [ ] **Pass criterion:** QGC shows the simulated vehicle moving, with telemetry on screen

Decide where QGC lives for the **demo**: ideally a second physical device (phone/tablet). For
tonight, wherever is fastest. Note: `passt` user-mode networking means the VM **cannot join a
WiFi AP** — so at the event the VM reaches the radio over USB and the second device joins the
radio's AP.

## 4. The ESP32 — identify it, don't flash it

A CP2102 DevKit is at `/dev/ttyUSB0`.

```sh
pipx install esptool        # or: pip install --user esptool
esptool.py --port /dev/ttyUSB0 chip_id
```

- [ ] Chip identified (expect classic ESP32)
- [ ] Flash size and MAC recorded
- [ ] **Pass criterion:** esptool talks to the board and reports a chip. That proves USB, driver,
      and cable — the three things that waste an hour tomorrow if broken.

## 5. The one piece of research that de-risks tomorrow

Open the DroneBridge repo/wiki and answer, **in writing**:

- [ ] Which **GPIOs does the classic-ESP32 DroneBridge build use for the flight-controller UART?**
- [ ] Is there a prebuilt classic-ESP32 binary, and which variant (the docs say `noUARTConsole`
      is *not* available for classic ESP32)?
- [ ] Which pins does the build reserve for the console?

**Pass criterion:** you know the exact TX/RX GPIO numbers for the FC link before you pick up a
jumper wire tomorrow. Docs warn that GPIO16-17 are flagged on some modules — don't assume.

---

## Tomorrow morning — 4 hours, the heavier setup

This is prep, not sprint work. The judges score the sprint.

1. Flash DroneBridge on **two** boards. Verify the web UI (`DroneBridge ESP32` /
   `dronebridge.local` / password `dronebridge`).
2. **USB passthrough** the ESP32 into the VM. Verify `/dev/ttyUSB0` inside the guest.
3. Build the **serial shuttle**: SITL's MAVLink UDP ↔ the ESP32's serial, using the **second
   UART on the GPIOs from item 5.** If you have no USB-TTL adapter, flash the third V1 as a
   USB↔UART passthrough.
4. Wire it. Power it. Do not let the magic smoke out — check 3.3 V, not 5 V.
5. **GATE T1: a QGC heartbeat arriving over real RF.** This is the whole morning's objective.
6. Stand up the second device as the GCS.
7. **Build the fault injector skeleton** — even a crude delay/drop injector against a loopback.
   It unblocks everything, and it's the instrument you measure with.

---

## The 5-hour sprint

The manager, the measurements, the demo. See `SPEC.md` §7–§10.

**Order of work:** link state estimation → rate adaptation → prioritization → fault injector →
store-and-forward → failover → the 30-run sweep.

**If you only get half of it done:** estimator + rate adaptation + the sweep. That's T0–T3, which
is a complete result and a real demo.

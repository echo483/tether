# TETHER — tonight's setup

**Goal tonight: prove the pieces separately and go to sleep.** Nothing here is the project.
Nothing here is sprint work. Tonight buys you a calm Friday.

**Do not tonight:** flash DroneBridge, wire anything, or attempt a radio link. Those are tomorrow.

**Where things run** (see `SPEC.md` §11): **VM = PX4 SITL only.** **Host = everything we build**,
including `/dev/ttyUSB0`. **Device 2 = QGC over the radio's AP.** No USB passthrough.

---

## 0. Before anything else — 5 minutes

- [ ] **Submit the hardware review to the organisers.**
      Two USB-powered ESP32s, no LiPo, no props, no soldering. Declare the 2.4 GHz radios.
      *The only item on this page that can disqualify you.* Do it first.

---

## 1. The host repo — proper deps, hit the ground running

New repo on the host. You have `uv`; use it. Deps are deliberately tiny — **pymavlink, pyserial,
esptool** — because every extra package is a tomorrow-morning failure mode.

```
tether/
  pyproject.toml          # or requirements.txt + uv.lock
  tether/
    link.py               # SITL <-> serial shuttle                        (T0/T1)
    inject.py             # fault injector: delay/loss/corrupt/blackout    (T2)
    manager.py            # link estimation, rate adaptation, priority     (T3)
    radio.py              # RADIO_STATUS parsing, SET_MESSAGE_INTERVAL     (T3)
    dash.py               # live numbers, for the demo
  notes/                  # the pin map from item 6 goes here
```

```sh
uv venv && uv pip install pymavlink pyserial esptool
uv run python -c "import pymavlink, serial; print('ok')"
```

- [ ] Repo created, venv up, imports verified
- [ ] **Pass criterion:** `import pymavlink, serial` succeeds inside the venv

## 2. The VM boots and PX4 runs

VM `dronelab`, currently shut off. 8 vCPU / 12 GB / 120 GB, SSH on `[IP_ADDRESS]:2222`, key
`~/.ssh/drone_lab_ed25519`. PX4 is **already built** — the build log ends `rc=0`.

```sh
LIBVIRT_DEFAULT_URI=qemu:///session virsh start dronelab
ssh -p 2222 -i ~/.ssh/drone_lab_ed25519 lab@[IP_ADDRESS]
```

- [ ] VM boots; SSH works; `build/px4_sitl_default/bin/px4` exists
- [ ] **Pass criterion:** SITL starts and the console shows a vehicle booting.
      **Write down the exact command that works** — `px4_sitl` may default to Gazebo, which is
      heavier than we need. SIH is the lighter target and supplies the same MAVLink.

## 3. The one integration point — guest → host MAVLink

The only nontrivial hop in the topology, so prove it tonight.

- [ ] From the guest, point SITL's MAVLink at the **host's gateway address** (under `passt` the
      host is the gateway — same idea as slirp's [IP_ADDRESS])
- [ ] On the host, listen with `mavproxy.py` or a 10-line `pymavlink` script
- [ ] **Pass criterion:** the host sees heartbeats, **and** something sent from the host lands in
      the guest. SITL's continuous stream should keep the NAT mapping alive so the return path
      needs no port forwards — **confirm that, don't assume it**

If the return path fails: add a UDP `portForward` to the VM's passt network and restart. A known
fallback, not a blocker.

## 4. QGroundControl

- [ ] Install QGC — AppImage on the host, or the Android build on the second device
- [ ] Connect it to SITL — **no radios involved**
- [ ] **Pass criterion:** QGC shows the simulated vehicle with live telemetry

For the **demo**, QGC lives on the second device over the radio's AP. Tonight, wherever is
fastest — the goal is just to know the install works.

## 5. The ESP32 — identify it, don't flash it

A CP2102 DevKit sits at `/dev/ttyUSB0`.

```sh
uv run esptool.py --port /dev/ttyUSB0 chip_id
```

- [ ] Chip identified (expect classic ESP32); flash size and MAC recorded
- [ ] **Pass criterion:** esptool talks to the board. That proves USB, driver, and cable — the
      three things that waste an hour tomorrow if broken

## 6. The research that de-risks tomorrow — write it down

Open the DroneBridge repo/wiki and answer **in writing**, into `notes/`:

- [ ] Which **GPIOs does the classic-ESP32 build use for the flight-controller UART?**
- [ ] Is there a prebuilt classic-ESP32 binary — and which variant, given the docs say
      `noUARTConsole` is *not* available for classic ESP32?
- [ ] Which pins does the build reserve for the console?

**Pass criterion:** you know the exact TX/RX GPIO numbers before you pick up a jumper wire
tomorrow. The docs flag GPIO16-17 on some modules — don't assume.

---

## Tomorrow morning — 4 hours, the heavier setup

Prep, not sprint work. The judges score the sprint.

1. Flash DroneBridge on **two** boards. Verify the web UI (`DroneBridge ESP32` /
   `dronebridge.local` / password `dronebridge`).
2. Build the **serial shuttle** (`link.py`): SITL's MAVLink UDP ↔ the ESP32's serial, on the
   GPIOs from item 6. No USB-TTL adapter? Flash the third V1 as a USB↔UART passthrough.
3. Wire it. **3.3 V, not 5 V.**
4. **GATE T1: a QGC heartbeat arriving over real RF.** That's the morning's whole objective.
5. Stand up the second device as the GCS — QGC over the radio's AP.
6. **Build the fault injector skeleton** (`inject.py`) — even crude, against a loopback. It
   unblocks everything, and it's the instrument you measure with.

---

## The 5-hour sprint

The manager, the measurements, the demo. See `SPEC.md` §7–§10.

**Order of work:** link state estimation → rate adaptation → prioritization → fault injector →
store-and-forward → failover → the 30-run sweep.

**If you only get half of it done:** estimator + rate adaptation + the sweep. That's T0–T3 — a
complete result and a real demo.

# TETHER — runbook (one page; every step is copy-paste)

All commands from `~/drone-labs/tether`. Board 1 = RADIO (power bank), board 3 = ADAPTER (only board on
the laptop), board 2 = spare in the bag. Board AP: SSID `TETHER-nighthack`, gateway 192.168.2 dot 1.

## A. Before leaving (today)
| # | Step | Pass |
|---|---|---|
| 1 | Breadboard harness (3–4 jumpers, see SCOPE.md §Harness), photo to Hermes | photo checked |
| 2 | AP password: Chrome → board web UI → Wi-Fi Password → Save & Reboot; then `nmcli con modify tether-ap wifi-sec.psk 'PASS' && nmcli con up tether-ap` | laptop re-joins |
| 3 | `tools/t1b.sh`, open QGC | **PX4 vehicle in QGC over RF** |
| 4 | Tin over board 1 for 10 s, then open | link drops, recovers |
| 5 | Board 2: web flasher → join its default AP → `TETHER_AP_PASS='…' tools/db_apply.sh` (then `--verify`) | all keys ok; power off, bag it |
| 6 | Offline drill (disconnects Hermes): `LIBVIRT_DEFAULT_URI=qemu:///session virsh shutdown dronelab`, unplug Ethernet, `nmcli con up tether-ap`, `tools/t1b.sh` → QGC vehicle; `tools/preflight.sh` → GO; replug | works with zero internet |
| 7 | `git push` / copy repo to a USB stick; pack (list below) | |

## B. Venue cold start (16:15–17:00)
1. Laptop on the power strip. Board 1 on the power bank, on its stand ~1.5 m away, tin beside it. Board 3 → laptop USB.
2. Channel: `nmcli -f SSID,CHAN,SIGNAL dev wifi list | sort -k2 -n` → pick the emptiest of 1/6/11 →
   `uv run python tools/db_set.py wifi_chan=N` (keeps the password, verifies after reboot).
3. `nmcli con up tether-ap` → `tools/t1b.sh` (starts VM + PX4 + shuttle + relay) → QGC: vehicle.
4. `tools/preflight.sh` → **GO**. Stop t1b.sh.
5. 17:00: `git tag sprint-start && git push --tags` (prep/sprint boundary for the judges).

## C. Recovery (each < 1 min)
| Symptom | Do |
|---|---|
| QGC: no vehicle | `ss -ulpn \| grep 1456` (QGC on 14560?) → QGC Comm Links → `TETHER-ground` → Connect |
| Board unreachable | power-cycle board 1, wait 5 s, `nmcli con up tether-ap` |
| Board settings wrong (someone clicked its boot button = SSID/pass reset to defaults) | join "DroneBridge for ESP32" / `dronebridge`, rerun `tools/db_apply.sh` |
| No PX4 stream on 14601 | `tools/vmssh 'bash -s' < tools/guest_px4_sih.sh` |
| VM wedged | `LIBVIRT_DEFAULT_URI=qemu:///session virsh destroy dronelab; tools/t1b.sh` |
| Board 1 dead | move the 3 jumpers to board 2 (pre-configured), same pins |
| RF path dead | `air.py --emulated` + "EMULATED LINK" banner (sprint feature) |
| QGC refuses to die | `pkill -9 -f QGroundControl` |

## D. Judging reset (21:45)
Kill air/ground/manager → restart PX4 (`guest_px4_sih.sh`) so the mission loops from the start → `tools/preflight.sh` GO →
QGC + dash side by side → capacity unlimited, manager OFF → disclosure + prediction cards on the table.

## Pack
Laptop + charger · power strip · board 1 on breadboard with board 3 (taped down) · board 2 in bag ·
power bank + cable for board 1 · 3 data USB cables (1 spare) · USB hub · metal tin · tape · spare jumpers ·
printed disclosure + prediction cards · phone (hotspot / USB tether for the Claude copilot).

# QGroundControl on this host — TETHER setup

QGC **v5.1.5** (`X-AppImage-Version=5.1.5`), extracted to `~/.local/opt/qgc/squashfs-root`.

## Launch command

```
~/.local/opt/qgc/squashfs-root/AppRun            # foreground
~/.local/opt/qgc/squashfs-root/AppRun >/tmp/qgc.log 2>&1 &   # background
```
AppRun forces the xcb platform ("Wayland support incomplete"), which works on this KDE Wayland
session through XWayland (`DISPLAY=:1`). The portal warning "App info not found for
'org.mavlink.qgroundcontrol'" is harmless. Quit from the UI, or use `kill -TERM <pid>`. On this host QGC
**ignored SIGTERM for more than 10 s** and needed SIGKILL. Settings had already been flushed, but quit from
the UI after any setting change you care about.

## Settings file

`~/.config/QGroundControl/QGroundControl.ini`. This is a stable build, so there is no " Daily" suffix: QGC
appends " Daily" only when built with `QGC_DAILY_BUILD` (`src/QGCApplication.cc` L87-93). QGC
created the file on first launch with `SettingsVersion=9`. **Don't remove that key**: if
`SettingsVersion` doesn't match, QGC wipes the whole file (`QGCApplication.cc` L128-137).
The pristine first-run copy is kept outside the repo at
`~/.hermes/profiles/dev/cache/scratch/qgc/QGroundControl.ini.firstrun`.

## What I changed (appended; neither group existed before)

```ini
[AutoConnect]
autoConnectUDP=false        ; no dynamic "UDP Link (AutoConnect)" on 14550
autoConnectPixhawk=false
autoConnectSiKRadio=false   ; IMPORTANT: QGC classes CP2102 10c4:ea60 as "SiK Radio" -> would grab every ESP32 DevKit tty
autoConnectLibrePilot=false
autoConnectRTKGPS=false
autoConnectZeroConf=false

[LinkConfigurations]
count=1
Link0\name=TETHER-ground
Link0\type=1                ; LinkConfiguration::TypeUdp (TypeSerial=0, TypeUdp=1, TypeTcp=2 ...)
Link0\auto=true             ; started by LinkManager::startAutoConnectedLinks() at boot
Link0\high_latency=false
Link0\port=14560            ; local listen port
Link0\hostCount=0           ; no fixed targets; QGC replies to whoever sends to 14560
```
(`;` comments are shown here for explanation only. The real file has no comments.)

Keys come from the QGC **v5.1.5** source, not guesses:
- `src/Settings/AutoConnect.SettingsGroup.json` gives the fact names and defaults (all `autoConnect*` default **true**, `udpListenPort` 14550). `src/Settings/AutoConnectSettings.cc` L6 gives the group name `"AutoConnect"`, which was renamed from `"LinkManager"` in v5.0. Old `[LinkManager]` keys get migrated.
- `src/Comms/LinkManager.cc` `saveLinkConfigurationList`/`loadLinkConfigurationList` (L338-435) gives `LinkConfigurations/count`, `LinkN/name|type|auto|high_latency`. `src/Comms/LinkConfiguration.h` L104-115 has the enum. `src/Comms/UDPLink.cc` `UDPConfiguration::load/saveSettings` (L105-142) gives `port`, `hostCount`, `hostN`/`portN`.
- `src/Comms/USBBoardInfo.json` L68 lists `vendorID 4292 / productID 60000` → "SiK Radio". That is why serial autoconnect must be off.

To move the link to another port: quit QGC, then `sed -i 's/^Link0\\port=14560$/Link0\\port=14570/' ~/.config/QGroundControl/QGroundControl.ini`.

## Verification (relaunch, 2026-10-30 ~12:39:46–12:40:35 PDT)

```
$ ss -ulpn | grep -E '1455|1456'
UNCONN 0 0  INADDR_ANY (0 dot 0 dot 0 dot 0):14560  INADDR_ANY (0 dot 0 dot 0 dot 0):*  users:(("QGroundControl",pid=28531,fd=51))
```
- The `TETHER-ground` link exists and is listening on **INADDR_ANY (0 dot 0 dot 0 dot 0):14560**. **Nothing is bound on 14550.** On the first launch, before the edit, QGC had bound 14550 with the default autoconnect on.
- After QGC exited, the ini still had both groups unchanged, so QGC re-saved our link config without losing it.
- **QGC actually connected to a vehicle on 14560.** Within about 3 s the log showed a
  `COMP_METADATA_TYPE_GENERAL ... mftp://` request (component info over MAVLink FTP), and QGC saved
  `FlightMapPosition` = 47.3977434, 8.5455944 (PX4 SITL's default home). PX4 SITL in the VM is
  currently streaming to **host UDP 14560**, the port `tools/probe511.py` defaults to.

## ⚠ Port conflict on this host

On this single host, **14560 is already the SITL→host MAVLink ingress** (`tools/probe511.py --port 14560`,
which was bound to it at 12:38). While QGC is running it takes that stream and talks back to PX4:
heartbeats, parameter/mission/FTP requests. Two consequences:
- Don't run QGC on this host while the SITL ingress, shuttle or census uses 14560. Any capture
  taken between 12:39:46 and 12:40:35 may include QGC's GCS traffic.
- The SPEC puts QGC on laptop 2 and SITL on laptop 1, which avoids the conflict. If both run on one host, give QGC another port (e.g. 14570, see the sed above) and have the ground agent forward to it.

## Remaining

- The link was checked from sockets and the ini. I did not open the QGC UI to *Application Settings → Comm Links*.
- DroneBridge's own heartbeat (compid 68, `MAV_TYPE_ONBOARD_CONTROLLER`) will **not** create a vehicle in QGC. See `notes/dronebridge.md`.

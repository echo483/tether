# DroneBridge for ESP32 — verified facts for TETHER

Verified 2026-10-30 against the **v2.4.1 source tag**, not the PX4 docs. Line numbers refer to the
v2.4.1 tree. Board-side behaviour has **not** been observed on hardware yet; everything below comes
from reading the source.

## Contradictions with our earlier assumptions (read first)

1. **The REST API changed.** Settings are read with `GET /api/settings` and written with `POST /api/settings`. There is **no** `/api/settings/change` route and **no** `/api/system/reboot` route; the POST handler saves to NVS and reboots on its own after 2 s.[2]
2. **There is no web-UI password.** The REST API has no authentication. `GET /api/settings` returns `wifi_pass` (and `espnow_secret`) **in plaintext** to anyone joined to the AP.[3][2]
3. **There is no TX-power setting in v2.4.1.** None of the 27 parameters controls TX power. "Low TX power" cannot be set over REST or in the UI.[3][4]
4. **On a generic ESP32 the UART defaults are TX=0, RX=0 at 57600 baud.** GPIO17/16 at 115200 is *not* the default, so the pins must be set after flashing.[4]
5. **QGC will not show a vehicle from DroneBridge's own heartbeat.** DroneBridge sends compid 68 with `MAV_TYPE_ONBOARD_CONTROLLER`. QGC 5.1.5 drops any heartbeat whose compid is not 1, so T1 Phase 1's pass criterion ("QGC shows a connected vehicle, no autopilot") cannot pass as written.[10][20] Prove Phase 1 instead with a raw listener on UDP 14550 that sees HEARTBEAT 1/68 and RADIO_STATUS at 1 Hz.
6. **Web Serial on desktop Linux needs rw access to `/dev/ttyUSB*`.** Chrome opens the tty directly, so the user must be in `dialout` (or have a uaccess/ACL rule). The flasher does **not** get around `dialout`.[15][16][17] Details in the table below.
7. **The AP's DHCP hands out a default gateway** (the ESP32's own address).[6][13]
8. **Until the UART pins are configured, the board puts no telemetry on the air at all.** When
   TX==RX (the factory 0/0), `open_serial_socket()` fails and `control_module_udp_tcp()` deletes
   itself *before* it opens UDP 14550 and TCP 5760. The heartbeat timer still logs "Starting to send heartbeats", but
   `db_send_to_all_udp_clients` returns early because the socket is -1. Only the REST/web server keeps running.
   Board 1's boot log shows exactly this sequence. The log line misleadingly says "JTAG serial socket
   not opened". So **set `gpio_tx`≠`gpio_rx` first**, even before anything is wired.[12][7]

## Ground truth — board 1 (`notes/evidence/board1-bootlog.txt`, serial boot log)

App version `2.4.1 (stable)`, chip rev v3.1, 4 MB flash. The NVS defaults printed are `esp32_mode=1`,
`wifi_chan=6`, `baud=57600`, `gpio_tx=0`, `gpio_rx=0`, `proto=4`, `trans_pack_size=576`. The key names match
the v2.4.1 `db_parameters.c` names that the REST JSON uses. Log lines 130-136:
`DB_SERIAL: Init UART socket aborted. TX GPIO == RX GPIO - Configure first!`, then
`DB_CONTROL: ... Aborting start of control module.`, then `DB_TIMERS: Starting to send heartbeats.`, then
`DB_ESP32: Rest Server started`. This agrees with every source-derived default below.

**Chosen pins: `gpio_tx=19`, `gpio_rx=18`, baud 115200** (parent's decision). These pins are safe on both WROOM
and WROVER, which makes the WROOM/WROVER GPIO16/17 question moot.

## Facts (cited)

| Topic | Fact | Src |
|---|---|---|
| Current stable | **v2.4.1** "stable", published 2026-09-12 (GitHub `releases/latest`). Its asset is `DroneBridge_ESP32_v2_4_1_stable.zip`. `db_parameters.h` says 2.4.1 build 23 "stable". | [1][4] |
| Build toolchain | CI image is ESP-IDF **5.4.4** | [14] |
| Read settings | `GET /api/settings` returns a flat JSON object of all 27 params, passwords included | [2] L499-506, [3] L919-943 |
| Change settings | `POST /api/settings` with a flat JSON body. Missing keys stay unchanged. Out-of-range or invalid values are **silently dropped**: the reply is still `success` and only the ESP log shows an error. Then it saves to NVS, replies `{"status":"success","msg":"Settings changed! Rebooting ..."}`, waits 2 s and calls `esp_restart()`. The body must be under 10240 B. | [2] L151-188, [3] L871-913 |
| Other routes | `GET /api/system/info` (version, MAC), `GET /api/system/stats` (UART bytes, decoded MAVLink count, `udp_clients`, `connected_sta` RSSI), `GET /api/system/clients`, `POST /api/settings/clients/udp` `{"udp_client_ip":"a.b.c.d","udp_client_port":N,"save":true}`, `DELETE /api/settings/clients/clear_udp`, `POST /api/settings/espnow-secret/rotate` | [2] |
| JSON keys | `esp32_mode` (1=AP, 2=STA, 3=AP-LR, 4/5=ESP-NOW air/gnd, 6=BLE), `wifi_chan` (1-13, default 6), `ssid`, `wifi_pass`, `ap_ip`, `wifi_hostname`, `wifi_en_gn`, `ant_use_ext`, `baud`, `gpio_tx`, `gpio_rx`, `gpio_rts`, `gpio_cts`, `rts_thresh`, `proto` (1=MSP/LTM, **4=MAVLink**, 5=transparent), `trans_pack_size` (16-1023, def 576), `serial_timeout` (ms, def 20), `ltm_per_packet`, `radio_dis_onarm`, `udp_client_ip`, `udp_client_port`, `rep_rssi_dbm`, `espnow_secret`, `espnow_air2air`, `ip_sta`, `ip_sta_gw`, `ip_sta_netmsk` | [3] L58-550, [4] L109-121 |
| Defaults | SSID `DroneBridge for ESP32`, pass `dronebridge`, `ap_ip` 192.168.2 dot 1, `/24`. Generic board: TX/RX/RTS/CTS = GPIO0, **57600** baud | [3] L504-510, [4] L70-76, [6] |
| Password length | Firmware accepts 7-63 chars. The UI enforces 8-63, and WPA2 needs ≥8, so use **≥8** | [3] L506, [5] L97-98 |
| Baud | Firmware accepts any value in 1200..5,000,000. UI dropdown: 5000000, 3000000, 2000000, 1500000, 1000000, **921600**, 576000, 500800, **460800**, 230400, 115200, 76800, 57600, 38400, 19200, 9600, 4800, 2400, 1200. **460800 and 921600 are both selectable.** | [3] L145-161, [5] L227-248 |
| Flow control | Off when `gpio_rts == gpio_cts`; those pins are then left alone (`UART_PIN_NO_CHANGE`) | [12] L67-98 |
| TX power | **No parameter exists.** The firmware never calls `esp_wifi_set_max_tx_power`, so the ESP-IDF default applies | [3] L522-550 |
| AP radio | AP mode is forced to **802.11b only** (`wifi_en_gn` has no effect in AP mode). WPA2-PSK, max 10 stations, country `US`, channels 1-13 (manual policy) | [6] L292-334 |
| Ports | UDP **14550** (bound on INADDR_ANY, broadcast allowed). TCP **5760**. | [9] L66-67, [7] |
| UDP, AP mode | (a) When the DHCP server leases an IP to a station, `<station-ip>:14550` is **added automatically**, with no packet needed first. (b) **Any** host that sends a UDP packet to `:14550` is added at its source ip:port. (c) Static clients can be added with `POST /api/settings/clients/udp`; one of them can be saved to NVS (`udp_client_ip`/`udp_client_port`) and comes back on boot. Clients are removed when the station disconnects (by MAC), or after 5 consecutive send failures. Maximum **8** clients; data is unicast to every one of them. There is **no broadcast** to the subnet. | [6] L152-174, [7] L171-200 & L749-769, [8] L27, [2] L215-307 |
| Injected MAVLink | Only when `proto`=4. **HEARTBEAT at 1 Hz** with sysid = `DB_MAV_SYS_ID` (default **1**, later copied from the FC's heartbeat on the UART) and compid **68** (`MAV_COMP_ID_TELEMETRY_RADIO`), type `MAV_TYPE_ONBOARD_CONTROLLER`, autopilot `INVALID`. **RADIO_STATUS at 1 Hz** in AP mode once ≥1 station is joined: `rssi` = first station's RSSI (dBm while `rep_rssi_dbm`=1), `remrssi`/`noise`/`remnoise` = 255, `rxerrors`=0. Both are sent to all radio clients. | [10] L45-85 & L314-350, [11] L70-156, [12] L50 |
| QGC vs that heartbeat | QGC 5.1.5 `_vehicleHeartbeatInfo` returns early when `componentId != MAV_COMP_ID_AUTOPILOT1`, and also skips `MAV_TYPE_ONBOARD_CONTROLLER`. A DroneBridge-only link therefore never creates a vehicle. | [20] L66-90 |
| DHCP gateway | The AP sets netif `gw = ap_ip` and then starts DHCPS. ESP-IDF's DHCPS defaults `dhcps_offer=0xFF` and adds **option 3 (router) whenever gw≠0**. DroneBridge never turns that off, so joining laptops get a **default route through the ESP32**. | [6] L336-344, [13] L185 & L468-479 |
| Web Serial perms | Chromium's serial code goes through `permission_broker` only on ChromeOS/Android. On desktop Linux it opens the device path itself (`base::File(port_, READ\|WRITE)`), as the user running Chrome. If the user lacks access, the result is "Failed to open serial port" / `FILE_ERROR_ACCESS_DENIED`, and the fix is the `dialout` group. On **this host**, `ttyUSB*` gets `GROUP="dialout"` (`/usr/lib/udev/rules.d/50-udev-default.rules:42`), `70-uaccess.rules` only tags signal-analyzer `ttyACM`, and `id` shows `ops` is **not** in `dialout`. So the flasher **will fail** until the user fixes access. | [15] L139-148, [16][17] |
| Flasher | drone-bridge.com/flasher supports Chrome, Edge and Firefox ≥151. Firefox needs a site-permission add-on. | [18] |
| Boot button | **Single click** (≤350 ms) sets SSID and password back to the defaults (`DroneBridge for ESP32`/`dronebridge`), forces AP mode, saves and reboots. **Long press** resets *all* settings. Double, triple and quadruple clicks start ESP-NOW binding. Anyone who can touch the board can bring the default-password AP back. | [6] L624-654, [5] L77-82 |
| Classic ESP32 | `noUARTConsole` is not published for ESP32 classic, so UART0 stays the console | [19] |

## Operational consequences

- **Addresses in these notes are written as "192.168.2 dot 1"** because host tooling replaces dotted-quad literals with a placeholder token. `tools/db_apply.sh` finds the board address at runtime: first the DHCP server id that `nmcli` reports on wlp0s20f3, otherwise one built from integers. `db_config.json` stores `ap_ip` as `_ap_ip_octets`.
- **Keep the default route off the ESP32**, and set the connection up before joining:
  ```
  nmcli con add type wifi ifname wlp0s20f3 con-name tether-ap ssid "TETHER-nighthack" \
    wifi-sec.key-mgmt wpa-psk wifi-sec.psk "$TETHER_AP_PASS" \
    ipv4.method auto ipv4.never-default yes ipv4.ignore-auto-dns yes ipv6.method disabled \
    connection.autoconnect no
  nmcli con up tether-ap
  ip route    # expect: only 192.168.2 dot 0/24 dev wlp0s20f3; default still via Ethernet
  ```
  (`$TETHER_AP_PASS` lands in NM's keyfile, which is root-only under `/etc/NetworkManager/system-connections/`. It never goes into the repo.)
- **Ground agent:** the ESP32 sends to `<laptop-ip>:14550` automatically after DHCP. The agent should bind 14550 and forward to QGC's `TETHER-ground` link on 14560, and QGC must **not** bind 14550 (see `notes/qgc.md`). If the laptop uses a static IP, DHCP never runs: send one packet to 192.168.2 dot 1:14550 or POST a static client.
- **Do not include `wifi_pass` in screenshots** of `GET /api/settings`. `tools/db_apply.sh --read` redacts it.
- `radio_dis_onarm` must stay 0, or the radio turns off when PX4 arms.
- After every POST, read the settings back and diff them, because the board silently ignores values it rejects.
- Fixing Web Serial needs `sudo` from the user, since we don't run sudo. Pick one: `sudo usermod -aG dialout ops`, then log out and back in, **or** a one-time udev rule `SUBSYSTEM=="tty", ATTRS{idVendor}=="10c4", ATTRS{idProduct}=="ea60", TAG+="uaccess"` plus `sudo udevadm control --reload && sudo udevadm trigger`, then replug, **or** a per-plug `sudo setfacl -m u:ops:rw /dev/ttyUSB0`.
- **QGC classes every CP2102 (10c4:ea60) as a "SiK Radio"** and auto-connects it by default (QGC `USBBoardInfo.json`). `notes/qgc.md` turns that off.

## Unknowns (need hardware or the UI)

- The real on-air SSID and password after flashing v2.4.1 from the web flasher, and whether the flasher erases NVS. If the board was flashed before, the old NVS values carry over.
- Default TX power on this build, and whether 802.11b-only AP mode limits throughput at our offered load.
- Whether 115200 is enough for SITL's offered load. Compare with the census in `notes/evidence/census-*.md`. 230400, 460800 and 921600 are selectable if it isn't, but check the CP2102 adapter path first.
- Whether QGC's MAVLink Inspector lists sysid 1 / compid 68 traffic without a vehicle (not checked).
- The "PX4 docs vs README" SSID disagreement mentioned in T1-PROMPT. The v2.4.1 source says `DroneBridge for ESP32` / `dronebridge`.

## Sources

[1] https://github.com/DroneBridge/ESP32/releases/tag/v2.4.1 — DroneBridge ESP32 v2.4.1 release (GitHub API releases/latest = v2.4.1, 2026-09-12)
[2] https://github.com/DroneBridge/ESP32/blob/v2.4.1/main/http_server.c — http_server.c v2.4.1 — REST route table
[3] https://github.com/DroneBridge/ESP32/blob/v2.4.1/main/db_parameters.c — db_parameters.c v2.4.1 — parameter names, ranges, defaults
[4] https://github.com/DroneBridge/ESP32/blob/v2.4.1/main/db_parameters.h — db_parameters.h v2.4.1 — version, generic default pins/baud, mode & proto enums
[5] https://github.com/DroneBridge/ESP32/blob/v2.4.1/frontend/index.html — frontend/index.html v2.4.1 — UART baud dropdown
[6] https://github.com/DroneBridge/ESP32/blob/v2.4.1/main/main.c — main.c v2.4.1 — db_init_wifi_apmode (11b, WPA2, US ch1-13, gw=AP IP, DHCPS)
[7] https://github.com/DroneBridge/ESP32/blob/v2.4.1/main/db_esp32_control.c — db_esp32_control.c v2.4.1 — send to all UDP clients, drop after 5 failures
[8] https://github.com/DroneBridge/ESP32/blob/v2.4.1/main/db_esp32_control.h — db_esp32_control.h v2.4.1 — MAX_UDP_CLIENTS 8
[9] https://github.com/DroneBridge/ESP32/blob/v2.4.1/main/db_protocol.h — db_protocol.h v2.4.1 — ports 5760 TCP / 14550 UDP
[10] https://github.com/DroneBridge/ESP32/blob/v2.4.1/main/db_mavlink_msgs.c — db_mavlink_msgs.c v2.4.1 — heartbeat compid/type
[11] https://github.com/DroneBridge/ESP32/blob/v2.4.1/main/db_timers.c — db_timers.c v2.4.1 — 1 Hz heartbeat + RADIO_STATUS injection
[12] https://github.com/DroneBridge/ESP32/blob/v2.4.1/main/db_serial.c — db_serial.c v2.4.1 — DB_MAV_SYS_ID = 1 default
[13] https://github.com/espressif/esp-idf/blob/release/v5.4/components/lwip/apps/dhcpserver/dhcpserver.c — ESP-IDF v5.4 dhcpserver.c — router option offered when netif gw != 0 (dhcps_offer default 0xFF, L185)
[14] https://github.com/DroneBridge/ESP32/tree/v2.4.1/.github/actions/esp-idf-5_4_4-with-node — DroneBridge CI builds with ESP-IDF 5.4.4
[15] https://chromium.googlesource.com/chromium/src/+/main/services/device/serial/serial_io_handler.cc — Chromium serial_io_handler.cc — non-ChromeOS opens the tty path directly with base::File
[16] https://www.gaunt.dev/blog/2022/web-serial-issues-on-chrome — Web serial issues on Chrome (FILE_ERROR_ACCESS_DENIED -> dialout)
[17] https://stackoverflow.com/questions/63112645/webserial-api-device-cannot-open-port-on-ubuntu — SO: WebSerial cannot open port on Ubuntu -> dialout
[18] https://drone-bridge.com/flasher — DroneBridge online flasher (Chrome, Edge, Firefox >=151)
[19] https://dronebridge.gitbook.io/docs/dronebridge-for-esp32/installation — DroneBridge docs — Installation (noUARTConsole not for ESP32 classic)
[20] https://github.com/mavlink/qgroundcontrol/blob/v5.1.5/src/Vehicle/MultiVehicleManager.cc — QGC v5.1.5 MultiVehicleManager — ignores compid!=1 / ONBOARD_CONTROLLER heartbeats

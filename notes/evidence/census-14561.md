| # | msgid | name | n | Hz | bytes/s | mean pkt B | crit |
|---|---|---|---|---|---|---|---|
| 1 | 30 | ATTITUDE | 882 | 14.70 | 588.0 | 40.0 | Y |
| 2 | 31 | ATTITUDE_QUATERNION | 589 | 9.82 | 431.9 | 44.0 | Y |
| 3 | 24 | GPS_RAW_INT | 294 | 4.90 | 274.4 | 56.0 |  |
| 4 | 33 | GLOBAL_POSITION_INT | 294 | 4.90 | 191.1 | 39.0 | Y |
| 5 | 74 | VFR_HUD | 235 | 3.92 | 113.6 | 29.0 |  |
| 6 | 83 | ATTITUDE_TARGET | 117 | 1.95 | 93.6 | 48.0 |  |
| 7 | 85 | POSITION_TARGET_LOCAL_NED | 88 | 1.47 | 92.4 | 63.0 |  |
| 8 | 12901 | OPEN_DRONE_ID_LOCATION | 58 | 0.97 | 67.7 | 70.0 |  |
| 9 | 1 | SYS_STATUS | 58 | 0.97 | 50.3 | 52.0 | Y |
| 10 | 36 | SERVO_OUTPUT_RAW | 58 | 0.97 | 47.4 | 49.0 |  |
| 11 | 141 | ALTITUDE | 58 | 0.97 | 42.5 | 44.0 |  |
| 12 | 32 | LOCAL_POSITION_NED | 58 | 0.97 | 38.7 | 40.0 | Y |
| 13 | 12904 | OPEN_DRONE_ID_SYSTEM | 58 | 0.97 | 35.8 | 37.0 |  |
| 14 | 242 | HOME_POSITION | 29 | 0.48 | 32.4 | 67.0 |  |
| 15 | 8 | MSG_8 | 58 | 0.97 | 28.9 | 29.9 |  |
| 16 | 230 | ESTIMATOR_STATUS | 29 | 0.48 | 26.1 | 54.0 |  |
| 17 | 147 | BATTERY_STATUS | 29 | 0.48 | 25.6 | 53.0 | Y |
| 18 | 29 | SCALED_PRESSURE | 58 | 0.97 | 25.1 | 26.0 |  |
| 19 | 0 | HEARTBEAT | 58 | 0.97 | 20.3 | 21.0 | Y |
| 20 | 42 | MISSION_CURRENT | 58 | 0.97 | 15.5 | 16.0 |  |
| 21 | 380 | MSG_380 | 29 | 0.48 | 15.5 | 32.0 |  |
| 22 | 245 | EXTENDED_SYS_STATE | 58 | 0.97 | 13.5 | 14.0 | Y |
| 23 | 132 | DISTANCE_SENSOR | 29 | 0.48 | 12.1 | 25.0 |  |
| 24 | 436 | MSG_436 | 29 | 0.48 | 9.7 | 20.0 |  |
| 25 | 411 | MSG_411 | 19 | 0.32 | 4.1 | 13.0 |  |
| 26 | 241 | VIBRATION | 5 | 0.08 | 2.7 | 32.0 |  |
| 27 | 4 | PING | 5 | 0.08 | 1.7 | 20.0 |  |

L = 2300.4 B/s; L_crit = 1359.4 B/s (ATTITUDE, ATTITUDE_QUATERNION, GLOBAL_POSITION_INT, SYS_STATUS, LOCAL_POSITION_NED, BATTERY_STATUS, HEARTBEAT, EXTENDED_SYS_STATE); missing crit: []
datagrams = 3340 (55.7/s, mean 41 B); UDP payload 2300.4 B/s; signed pkts = 0; RADIO_STATUS present = False; RTF(ATTITUDE.time_boot_ms) = 0.9806480145860267
L / 11520 B/s (115200 8N1) = 20.0%; L / 46080 B/s (460800) = 5.0%

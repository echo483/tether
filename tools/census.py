#!/usr/bin/env python3
"""Offered-load census of a PX4 MAVLink UDP stream (receive-only; sends nothing).

    uv run python tools/census.py [--bind localhost] [--port 14561] [--secs 60] [--md out.md]

Bytes = full MAVLink wire length per packet (v2: 10 B header + payload + 2 B CRC, +13 B if signed),
split out of each UDP datagram with mavframes.split_frames. Clock = host time.monotonic().
RTF = delta(ATTITUDE.time_boot_ms) / delta(host ms) between first and last ATTITUDE of sysid 1.
"""
import argparse
import json
import socket
import struct
import time

from pymavlink.dialects.v20 import common as m2

from mavframes import split_frames

CRIT = ["HEARTBEAT", "ATTITUDE", "ATTITUDE_QUATERNION", "GLOBAL_POSITION_INT", "LOCAL_POSITION_NED",
        "SYS_STATUS", "EXTENDED_SYS_STATE", "BATTERY_STATUS"]
# PX4 sends these from development.xml; pymavlink's common dialect has no class for them
EXTRA = {8: "LINK_NODE_STATUS", 380: "TIME_ESTIMATE_TO_TARGET", 411: "CURRENT_EVENT_SEQUENCE",
         436: "CURRENT_MODE"}
ap = argparse.ArgumentParser()
ap.add_argument("--bind", default="localhost")
ap.add_argument("--port", type=int, default=14561)
ap.add_argument("--secs", type=float, default=60.0)
ap.add_argument("--md", default=None)
ap.add_argument("--json", default=None)
a = ap.parse_args()

s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
s.bind((a.bind, a.port))
s.settimeout(0.5)
d, src = s.recvfrom(65535)  # wait for stream, then start the clock on the next datagram boundary
stats, n_dgram, dgram_bytes, signed, att = {}, 0, 0, 0, []
t0 = time.monotonic()
t_end = t0 + a.secs
while (now := time.monotonic()) < t_end:
    try:
        d, src = s.recvfrom(65535)
    except socket.timeout:
        continue
    n_dgram += 1
    dgram_bytes += len(d)
    for msgid, flen, sysid, compid, payload, ver in split_frames(d):
        st = stats.setdefault(msgid, [0, 0])
        st[0] += 1
        st[1] += flen
        signed += flen > 12 + len(payload) and ver == 2
        if msgid == 30 and sysid == 1 and len(payload) >= 4:
            att.append((now, struct.unpack_from("<I", payload)[0]))
T = a.secs
rows = []
for msgid, (n, b) in stats.items():
    cls = m2.mavlink_map.get(msgid)
    name = cls.msgname if cls else EXTRA.get(msgid, f"MSG_{msgid}")
    rows.append({"msgid": msgid, "name": name, "n": n, "hz": n / T, "Bps": b / T, "mean_len": b / n})
rows.sort(key=lambda r: -r["Bps"])
L = sum(r["Bps"] for r in rows)
crit = [r for r in rows if r["name"] in CRIT]
L_crit = sum(r["Bps"] for r in crit)
rtf = None
if len(att) > 1:
    rtf = (att[-1][1] - att[0][1]) / ((att[-1][0] - att[0][0]) * 1000.0)
res = {"src": list(src), "secs": T, "datagrams": n_dgram, "udp_payload_Bps": dgram_bytes / T,
       "mean_datagram_B": dgram_bytes / max(n_dgram, 1), "signed_packets": signed, "L_Bps": L,
       "L_crit_Bps": L_crit, "rtf_attitude": rtf, "radio_status_present": 109 in stats,
       "frac_115200": L / 11520, "frac_460800": L / 46080, "rows": rows,
       "date": time.strftime("%Y-%m-%d %H:%M:%S %Z")}
lines = ["| # | msgid | name | n | Hz | bytes/s | mean pkt B | crit |", "|---|---|---|---|---|---|---|---|"]
for i, r in enumerate(rows, 1):
    lines.append(f"| {i} | {r['msgid']} | {r['name']} | {r['n']} | {r['hz']:.2f} | {r['Bps']:.1f} | "
                 f"{r['mean_len']:.1f} | {'Y' if r['name'] in CRIT else ''} |")
lines.append(f"\nL = {L:.1f} B/s; L_crit = {L_crit:.1f} B/s ({', '.join(r['name'] for r in crit)}); "
             f"missing crit: {[c for c in CRIT if c not in {r['name'] for r in crit}]}")
lines.append(f"datagrams = {n_dgram} ({n_dgram / T:.1f}/s, mean {res['mean_datagram_B']:.0f} B); "
             f"UDP payload {res['udp_payload_Bps']:.1f} B/s; signed pkts = {signed}; "
             f"RADIO_STATUS present = {res['radio_status_present']}; RTF(ATTITUDE.time_boot_ms) = {rtf}")
lines.append(f"L / 11520 B/s (115200 8N1) = {res['frac_115200']:.1%}; L / 46080 B/s (460800) = {res['frac_460800']:.1%}")
md = "\n".join(lines)
print(md)
if a.md:
    open(a.md, "w").write(md + "\n")
if a.json:
    json.dump(res, open(a.json, "w"), indent=1)

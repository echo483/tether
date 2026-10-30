"""relay_ground.py — dumb ground-side relay for T1b (prep plumbing; ground.py replaces it in the sprint).

DroneBridge (AP mode) pushes MAVLink to <this laptop's wifi ip>:14550 after DHCP. We bind :14550,
forward every datagram to QGC (localhost:14560), and send QGC's uplink back up the radio to the
board from the SAME :14550 socket, so DroneBridge sees one client, not two.

    uv run python tools/relay_ground.py
"""
import select
import socket
import time

from tnet import DB_IP, DB_UDP_PORT, LOCAL, QGC_PORT

radio = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
radio.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
radio.bind(("", DB_UDP_PORT))
gcs = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
gcs.bind((LOCAL, 0))
qgc = (LOCAL, QGC_PORT)
board = (DB_IP, DB_UDP_PORT)
radio.sendto(b"", board)  # harmless empty datagram: registers us even if DHCP auto-add was missed

down = up = down_b = up_b = 0
last = time.monotonic()
while True:
    r, _, _ = select.select([radio, gcs], [], [], 0.5)
    for s in r:
        data, src = s.recvfrom(65535)
        if s is radio:
            gcs.sendto(data, qgc); down += 1; down_b += len(data)
        else:
            radio.sendto(data, board); up += 1; up_b += len(data)
    if time.monotonic() - last >= 1.0:
        print(f"down {down:4d} pkt {down_b:6d} B/s   up {up:3d} pkt {up_b:5d} B/s", flush=True)
        down = up = down_b = up_b = 0
        last = time.monotonic()

"""tnet.py — the port map from CONTRACT.md as code. Import this; never type IP literals.

(Tooling note: dotted-quad literals typed through the agent get redacted, so addresses are
built from ints here. Humans: the DroneBridge AP gateway is 192.168.2 dot 1.)
"""
LOCAL = "localhost"


def ip(*octets):
    return ".".join(str(o) for o in octets)


DB_IP = ip(192, 168, 2, 1)       # DroneBridge AP gateway (board 1)
DB_UDP_PORT = 14550              # DroneBridge MAVLink UDP; it auto-pushes to <laptop wifi ip>:14550 after DHCP
PX4_PORT = 14601               # PX4 TETHER mavlink instance -> host localhost:14601 (air.py binds it)
QGC_PORT = 14560                 # QGC listens here; ground.py forwards to it
AIR_CTRL_PORT = 14599            # air.py control port (JSON lines)
WIFI_IF = "wlp0s20f3"            # laptop WiFi joined to the DroneBridge AP
AIR_UPLINK_PORT = 14598          # air.py binds: any MAVLink datagram here is forwarded raw to PX4 (the command link)
LIVE_DIR = "logs/live"           # default log dir when not under sweep.py: logs/live/{air,ground}.jsonl

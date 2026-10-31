"""loopback3.py — is board 3's RX0 pin + wire 1 actually carrying the laptop's data? (runs online, no AP)

Setup: pull BOTH jumper ends out of board 1. Push wire 1's free end (the one that went to D18)
into a free hole of board 3's **TX0** row. Now: laptop -> CP2102 TX -> RX0 pin -> wire 1 -> TX0 pin -> CP2102 RX -> laptop.
Board 3 is held in reset, so its ESP32 stays out of the way.

    uv run python tools/loopback3.py
"""
import glob
import os
import time

import serial

dev = sorted(set(glob.glob("/dev/serial/by-path/*port0")))[0]
s = serial.Serial()
s.port, s.baudrate, s.timeout = dev, 115200, 0.05
s.dtr, s.rts = False, True
s.open()
s.rts = False; time.sleep(0.1); s.rts = True; time.sleep(0.4); s.reset_input_buffer()
pattern = os.urandom(64)
sent = got = match = 0
t0 = time.time()
while time.time() - t0 < 3.0:
    s.write(pattern); sent += len(pattern)
    time.sleep(0.01)
    b = s.read(4096); got += len(b); match += b.count(pattern[:8])
s.close()
print(f"sent {sent} B, read back {got} B, pattern hits {match}")
if got > sent * 0.8 and match > 10:
    print("PASS: board 3 RX0 + wire 1 are good -> the fault is at board 1's end (D18 row / pin). Next: move to another RX pin.")
elif got == 0:
    print("FAIL: nothing comes back -> wire 1 is broken, or not in RX0's / TX0's row, or board 3's RX0 pin is dead. Swap the jumper first.")
else:
    print("PARTIAL: bytes come back garbled -> loose contact. Re-seat, or swap the jumper.")

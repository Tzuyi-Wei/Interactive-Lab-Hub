# Read the LSM6DS3 and print how far the cup is tilted.
#
# Run this with the sensor taped to the cup, then tilt the cup the way you would
# to drink from it. The numbers it prints are what the thresholds in the real
# sketch should be set to - note the angle at rest and the angle while drinking,
# and pick something comfortably between the two.
#
#   python tilt_test.py

import math
import time

import board
import busio
from adafruit_lsm6ds.lsm6ds3trc import LSM6DS3TRC

i2c = busio.I2C(board.SCL, board.SDA)
sensor = LSM6DS3TRC(i2c)

print("tilt from upright, in degrees - ctrl-c to stop")
print()

while True:
    x, y, z = sensor.acceleration

    # With the board flat the whole 9.8 m/s^2 of gravity sits on one axis. As
    # the cup tips, gravity spills into the other two, and the angle between
    # "where gravity is now" and "where it was upright" is the tilt.
    horizontal = math.hypot(x, y)
    tilt = math.degrees(math.atan2(horizontal, abs(z)))

    bar = "#" * int(tilt / 3)
    print(f"\r{tilt:5.1f} deg  {bar:<40}", end="", flush=True)
    time.sleep(0.1)

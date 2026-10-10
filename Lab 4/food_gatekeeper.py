import time
from datetime import datetime

import qwiic_proximity
import pi_servo_hat

# Food Gatekeeper
# The jar's lid rests open. After 10pm, a hand reaching for the jar is
# detected by a Qwiic proximity sensor behind a hole in the front of the
# jar, and the servo on the hinge snaps the lid shut. Once the hand is
# gone, the lid slowly opens again.

SERVO_CH = 0
LID_OPEN = 10
LID_CLOSED = 100

# How long the lid stays shut after the hand has gone, and how slowly it
# opens again afterwards.
HOLD_CLOSED = 3.0
REOPEN_STEP = 2
REOPEN_DELAY = 0.03

# Calibrate this value for your own jar and sensor placement.
# Run qwiic_distance.py first to compare the proximity reading with
# your hand at the jar and with nothing in front of it.
# Higher proximity values mean the object is closer.
HAND_THRESHOLD = 60

# The gatekeeper only guards the jar from NIGHT_START until NIGHT_END.
# Set ALWAYS_NIGHT to True to demo it during the day.
NIGHT_START = 22
NIGHT_END = 6
ALWAYS_NIGHT = True


def is_night():
    if ALWAYS_NIGHT:
        return True
    hour = datetime.now().hour
    return hour >= NIGHT_START or hour < NIGHT_END


# --- Set up proximity sensor ---
proximity_sensor = qwiic_proximity.QwiicProximity()

if not proximity_sensor.connected:
    raise RuntimeError(
        "Qwiic proximity sensor not found. Check the Qwiic connection."
    )

proximity_sensor.begin()


# --- Set up servo ---
servo = pi_servo_hat.PiServoHat()
servo.restart()
servo.move_servo_position(SERVO_CH, LID_OPEN)

print("Food Gatekeeper ready!")
print(f"Current proximity threshold: {HAND_THRESHOLD}")


try:
    while True:
        proximity = proximity_sensor.get_proximity()
        print(f"Proximity: {proximity}", end="\r")

        if proximity > HAND_THRESHOLD and is_night():
            print(f"\nHand detected after hours! Proximity = {proximity}")
            # One jump instead of a sweep, so it reads as a bite.
            servo.move_servo_position(SERVO_CH, LID_CLOSED)

            # Keep the lid shut until the hand has been gone for HOLD_CLOSED.
            last_seen = time.time()
            while time.time() - last_seen < HOLD_CLOSED:
                if proximity_sensor.get_proximity() > HAND_THRESHOLD:
                    last_seen = time.time()
                time.sleep(0.05)

            print("Hand gone. Opening the lid again.")
            # Works whichever way round the servo is mounted.
            step = REOPEN_STEP if LID_OPEN > LID_CLOSED else -REOPEN_STEP
            for angle in range(LID_CLOSED, LID_OPEN, step):
                servo.move_servo_position(SERVO_CH, angle)
                time.sleep(REOPEN_DELAY)
            servo.move_servo_position(SERVO_CH, LID_OPEN)

        time.sleep(0.05)

except KeyboardInterrupt:
    print("\nStopping Food Gatekeeper.")
    servo.move_servo_position(SERVO_CH, LID_OPEN)

#!/usr/bin/env python3
"""Show how much the webcam sees moving, so the trigger can be set sensibly.

    python motion_check.py

Sit in front of the camera and watch the number. The value with nobody there is
the noise floor; the value while you are sitting and talking normally is what the
threshold has to be under. Ctrl-C to stop.
"""
import subprocess
import numpy as np

SIZE = 160 * 120
proc = subprocess.Popen(
    ["ffmpeg", "-loglevel", "quiet", "-f", "v4l2", "-video_size", "320x240",
     "-i", "/dev/video0", "-pix_fmt", "gray", "-s", "160x120", "-r", "4",
     "-f", "rawvideo", "-"], stdout=subprocess.PIPE)

previous = None
peak = 0.0
print("motion   peak   (ctrl-C to stop)")
try:
    while True:
        raw = proc.stdout.read(SIZE)
        if len(raw) < SIZE:
            break
        frame = np.frombuffer(raw, dtype=np.uint8).astype(np.int16)
        if previous is not None:
            value = float(np.abs(frame - previous).mean())
            peak = max(peak, value)
            bar = "#" * int(min(value, 50))
            print("%6.2f  %6.2f  %s" % (value, peak, bar), flush=True)
        previous = frame
except KeyboardInterrupt:
    print("\npeak was %.2f" % peak)
finally:
    proc.terminate()

"""
Part H: the Sleep Gatekeeper's night shift. Guard the phone stand all night, headless.

A VCNL4040 proximity sensor (Lab 4) sits under the phone stand. Infrared works in the
dark, so the camera is not needed at night. The math question waits for the morning.

    python overnight.py --bedtime 00:30 --wake 08:00    # a real night
    python overnight.py --bedtime now --wake +2          # fake night: bedtime now, wake in 2 minutes

From bedtime on, the stand nags until the phone is put on it (the hand-off). After that,
taking the phone off makes it nag until the phone is back. At wake time it stops, so
the morning script can run next.

Writes night_log.jsonl (one JSON object per line): "start", "bedtime", "handed_in",
"phone_off", "phone_on" (with how long the phone was away) and "wake" events, plus an
"alive" line every 10 minutes so you can tell a quiet night from a crashed one.
Start it in tmux or with nohup so it survives the ssh disconnect (see the README).
"""
import argparse
import datetime
import json
import subprocess
import time

import qwiic_proximity

parser = argparse.ArgumentParser()
parser.add_argument("--bedtime", default="00:00", help="HH:MM, or 'now'")
parser.add_argument("--wake", default=None, help="HH:MM, or +N for N minutes from now; default: run until Ctrl-C")
parser.add_argument("--threshold", type=int, default=1000,
                    help="proximity above this means the phone is on the stand (measured: ~164 empty, ~2600 with phone)")
parser.add_argument("--confirm", type=int, default=4,
                    help="readings in a row before the phone counts as taken or put back")
parser.add_argument("--interval", type=float, default=0.5, help="seconds between readings")
args = parser.parse_args()


def next_time(hhmm, after):
    """The next HH:MM at or after `after`; a bedtime up to 12 hours ago counts as already started."""
    h, m = map(int, hhmm.split(":"))
    t = after.replace(hour=h, minute=m, second=0, microsecond=0)
    if t < after - datetime.timedelta(hours=12):
        t += datetime.timedelta(days=1)
    return t


start = datetime.datetime.now()
bedtime = start if args.bedtime == "now" else next_time(args.bedtime, start)
if args.wake is None:
    wake = None
elif args.wake.startswith("+"):
    wake = start + datetime.timedelta(minutes=float(args.wake[1:]))
else:
    wake = next_time(args.wake, bedtime)
    if wake <= bedtime:
        wake += datetime.timedelta(days=1)

sensor = qwiic_proximity.QwiicProximity()
if not sensor.connected:
    raise SystemExit("proximity sensor not found: check the Qwiic cable")
sensor.begin()
sensor.get_proximity()          # the first reading after begin() is 0
time.sleep(0.2)

log = open("night_log.jsonl", "a")
speech = None


def write(entry):
    entry = {"t": datetime.datetime.now().isoformat(timespec="seconds"), **entry}
    log.write(json.dumps(entry) + "\n")
    log.flush()
    print(entry, flush=True)


def say(text):
    """Speak without blocking the sensor loop; skip if the last sentence is still playing."""
    global speech
    if speech is None or speech.poll() is not None:
        speech = subprocess.Popen(["espeak-ng", "-s", "150", text],
                                  stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


phone_on = sensor.get_proximity() > args.threshold
disagree = 0                    # readings in a row that disagree with phone_on
handed_in = False               # has the phone been put on the stand since bedtime?
bedtime_logged = False
taken_at = None
last_nag = last_beat = 0.0

write({"event": "start", "bedtime": bedtime.isoformat(timespec="minutes"),
       "wake": wake.isoformat(timespec="minutes") if wake else None, "phone_on": phone_on})
print(f"guarding from {bedtime:%H:%M}" + (f" until {wake:%H:%M}" if wake else ", Ctrl-C to stop"), flush=True)

while True:
    try:
        now = datetime.datetime.now()
        if wake and now >= wake:
            write({"event": "wake"})
            break

        # one debounced reading: a hand passing over or a bump of the desk does not count
        seen_on = sensor.get_proximity() > args.threshold
        disagree = disagree + 1 if seen_on != phone_on else 0
        changed = disagree >= args.confirm
        if changed:
            phone_on, disagree = seen_on, 0

        if now >= bedtime:
            if not bedtime_logged:
                write({"event": "bedtime"})
                bedtime_logged = True
            if not handed_in:
                if phone_on:            # the hand-off
                    handed_in = True
                    write({"event": "handed_in"})
                    say("Good night. I will keep your phone.")
                elif time.time() - last_nag > 20:
                    say("It is time for bed. Put your phone on the stand.")
                    last_nag = time.time()
            elif changed and not phone_on:
                taken_at = now
                write({"event": "phone_off"})
            elif changed and phone_on:
                write({"event": "phone_on", "away_s": int((now - taken_at).total_seconds())})
                say("Thank you. Good night.")
            if handed_in and not phone_on and time.time() - last_nag > 5:
                say("Put the phone back.")
                last_nag = time.time()

        if time.time() - last_beat > 600:
            write({"alive": True, "phone_on": phone_on})
            last_beat = time.time()
        time.sleep(args.interval)
    except KeyboardInterrupt:
        break
    except Exception as e:
        print("hiccup:", e, flush=True)
        time.sleep(args.interval)

print("night shift stopped", flush=True)

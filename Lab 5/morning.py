"""
Part I: the Sleep Gatekeeper's morning. The alarm only stops when you get out of bed,
stand in front of the stand and answer a math question with your fingers.

    python morning.py                      # alarm, question, then the report on last night
    python morning.py --show               # also show the camera with the finger count (VNC)
    python morning.py --log some.jsonl     # use another night's log

Last night's log decides the difficulty: no phone taken is one easy question, taken once
is one harder question, taken twice or more is two hard questions in a row.
Python picks the answer (1 to 10, so it fits on your fingers) and builds the question
around it; Qwen only writes the report, and only from facts Python counted.
"""
import argparse
import datetime
import json
import math
import os
import random
import re
import subprocess
import threading
import time
import wave

import cv2
import mediapipe as mp
import requests

parser = argparse.ArgumentParser()
parser.add_argument("--log", default="night_log.jsonl")
parser.add_argument("--model", default="qwen3.5:0.8b")
parser.add_argument("--show", action="store_true", help="show the camera with the finger count (needs VNC)")
parser.add_argument("--hold", type=float, default=2.0, help="seconds an answer must be held")
parser.add_argument("--away", type=float, default=20.0, help="seconds without a hand before the alarm comes back")
args = parser.parse_args()


# --- last night -----------------------------------------------------------------

def read_night(path):
    """Count what the night shift logged. Everything the morning says comes from here."""
    entries = [json.loads(line) for line in open(path) if line.strip()] if os.path.exists(path) else []
    starts = [i for i, e in enumerate(entries) if e.get("event") == "start"]
    night = entries[starts[-1]:] if starts else entries          # only the last night in the file
    events = [e for e in night if "event" in e]
    handed = next((e["t"][11:16] for e in events if e["event"] == "handed_in"), None)
    bedtime = next((e["t"][11:16] for e in events if e["event"] == "bedtime"), None)
    away = [e["away_s"] for e in events if e["event"] == "phone_on" and "away_s" in e]
    taken = sum(1 for e in events if e["event"] == "phone_off")
    return {"bedtime": bedtime, "handed_in": handed, "taken": taken,
            "away_min": round(sum(away) / 60), "logged": bool(night)}


night = read_night(args.log)
level = "easy" if night["taken"] == 0 else "medium" if night["taken"] == 1 else "hard"
questions_needed = 2 if level == "hard" else 1
print("last night:", night, "->", level, flush=True)


# --- questions --------------------------------------------------------------------

def make_question(level):
    """Pick the answer first (1 to 10), then build a question around it.
    Returns (text to show, text to speak, answer)."""
    answer = random.randint(1, 10)
    if level == "easy":                        # a - b
        b = random.randint(3, 15)
        a = answer + b
        return f"{a} - {b}", f"{a} minus {b}", answer
    if level == "medium":                      # (a + b) / d
        d = random.randint(2, 9)
        total = answer * d
        a = random.randint(1, total - 1) if total > 1 else 1
        b = total - a
        return f"({a} + {b}) / {d}", f"{a} plus {b}, divided by {d}", answer
    d = random.randint(3, 9)                   # (a x b - c) / d
    target = answer * d
    while True:
        a, b = random.randint(3, 12), random.randint(3, 12)
        if a * b > target:
            break
    c = a * b - target
    return f"({a} x {b} - {c}) / {d}", f"{a} times {b}, minus {c}, divided by {d}", answer


# --- report (Qwen, in the background while the alarm rings) ------------------------

def facts_text(n):
    if not n["logged"]:
        return "There is no log from last night."
    parts = [f"Bedtime was set for {n['bedtime']}." if n["bedtime"] else "No bedtime was logged."]
    parts.append(f"The phone was put on the stand at {n['handed_in']}." if n["handed_in"]
                 else "The phone was never put on the stand.")
    if n["taken"]:
        parts.append(f"The phone was taken off the stand {n['taken']} time(s) during the night, "
                     f"for about {n['away_min']} minute(s) in total.")
    else:
        parts.append("The phone stayed on the stand all night.")
    return " ".join(parts)


NUMBER_WORDS = re.compile(r"\d|\b(one|two|three|four|five|six|seven|eight|nine|ten|eleven|twelve|"
                          r"once|twice|hour|hours|minute|minutes|o'clock|midnight)\b", re.I)


VERDICTS = {   # Python judges the night; this is also the line said when Qwen's is rejected
    "easy": ("kept the phone away all night", "Well done, your phone and you both got some rest."),
    "medium": ("took the phone back once", "Your phone missed you, but I did not miss a thing."),
    "hard": ("took the phone back again and again", "I counted every sneak, and so does today's math."),
}


def ask_qwen(facts):
    """The facts are always said word for word by Python: when Qwen restated them it got them
    wrong ("your night ended at 00:30", "about two hours" for 26 minutes), and when it judged
    the night itself it praised a bad one. So Python gives it the verdict and Qwen only writes
    one sentence of reaction, which may not contain any time or number."""
    verdict, fallback = VERDICTS[level]
    examples = "\n".join(f"{v} -> {line}" for v, line in VERDICTS.values())
    prompt = (f"You are a strict but kind sleep gatekeeper talking to the user in the morning.\n"
              f"Write one short sentence to the user that matches what they did last night. Examples:\n"
              f"{examples}\n{verdict} ->")
    try:
        r = requests.post("http://localhost:11434/api/generate", json={
            "model": args.model, "prompt": prompt, "think": False, "stream": False,
            "options": {"temperature": 0.7, "num_predict": 40}}, timeout=120)
        r.raise_for_status()
        # emoji crash print() in the Pi's latin-1 terminal and espeak cannot say them anyway
        text = r.json()["response"].encode("ascii", "ignore").decode().strip().split("\n")[0]
    except Exception as e:
        print("qwen failed:", e, flush=True)
        text = ""
    if (not text or len(text) > 160 or NUMBER_WORDS.search(text)
            or "cannot" in text.lower() or text.lower().startswith("good night")):
        print("qwen's sentence rejected:", repr(text), flush=True)
        text = fallback
    return f"{facts} {text}"


facts = facts_text(night)
report = {"text": facts}                       # replaced by Qwen's version if it comes back in time
threading.Thread(target=lambda: report.update(text=ask_qwen(facts)), daemon=True).start()


# --- sound ----------------------------------------------------------------------------

def make_beep(path="/tmp/gatekeeper_alarm.wav", rate=22050):
    """Two short beeps and a pause, written once so aplay can loop it."""
    frames = bytearray()
    for i in range(int(rate * 1.0)):
        t = i / rate
        on = (t % 0.5) < 0.2 and t < 0.9
        v = int(12000 * math.sin(2 * math.pi * 880 * t)) if on else 0
        frames += v.to_bytes(2, "little", signed=True)
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(bytes(frames))
    return path


class Alarm:
    def __init__(self):
        self.wav, self.proc, self.thread, self.running = make_beep(), None, None, False

    def _loop(self):
        while self.running:
            self.proc = subprocess.Popen(["aplay", "-q", self.wav],
                                         stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            self.proc.wait()

    def start(self):
        self.running = True
        if not (self.thread and self.thread.is_alive()):     # one loop at a time
            self.thread = threading.Thread(target=self._loop, daemon=True)
            self.thread.start()

    def stop(self):
        self.running = False
        if self.proc and self.proc.poll() is None:
            self.proc.terminate()


def say(text):
    print("says:", text, flush=True)
    subprocess.run(["espeak-ng", "-s", "140", text], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


# --- fingers ------------------------------------------------------------------------

def dist(a, b):
    return math.hypot(a.x - b.x, a.y - b.y)


def count_fingers(hand):
    """Fingers up on one hand. A finger is up when its tip is farther from the wrist than
    its middle joint, which works however the hand is turned. The thumb is up when its tip
    is farther from the base of the little finger than its own middle joint."""
    lm = hand.landmark
    up = sum(dist(lm[tip], lm[0]) > dist(lm[tip - 2], lm[0]) for tip in (8, 12, 16, 20))
    up += dist(lm[4], lm[17]) > dist(lm[3], lm[17])
    return up


# --- the morning --------------------------------------------------------------------

hands = mp.solutions.hands.Hands(max_num_hands=2, model_complexity=0,
                                 min_detection_confidence=0.6, min_tracking_confidence=0.5)
draw = mp.solutions.drawing_utils
cap = cv2.VideoCapture(0)
cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)

alarm = Alarm()
alarm.start()
print("alarm ringing; stand in front of the camera and show a hand", flush=True)

question = None                 # (shown, spoken, answer) while one is being asked
asked = 0
correct = 0
last_hand = 0.0
held, held_since = None, 0.0
moved = False                   # an answer only counts after the hand changed since the question
log = open(args.log, "a")


def write(entry):
    log.write(json.dumps({"t": datetime.datetime.now().isoformat(timespec="seconds"), **entry}) + "\n")
    log.flush()


try:
    while correct < questions_needed:
        ok, frame = cap.read()
        if not ok:
            time.sleep(0.5)
            continue
        result = hands.process(cv2.cvtColor(frame, cv2.COLOR_BGR2RGB))
        found = result.multi_hand_landmarks or []
        fingers = sum(count_fingers(h) for h in found) if found else None
        now = time.time()

        if found:
            last_hand = now
            if question is None:                       # someone is at the stand: ask
                alarm.stop()
                time.sleep(0.3)
                question = make_question(level)
                intro = {"easy": "Good morning. You left your phone alone last night.",
                         "medium": "Good morning. You took your phone once last night, so this one is harder.",
                         "hard": f"Good morning. You took your phone {night['taken']} times last night. "
                                 f"Two hard questions."}[level] if asked == 0 else "Next question."
                asked += 1
                say(f"{intro} What is {question[1]}? Answer with your fingers.")
                write({"event": "question", "level": level, "question": question[0], "answer": question[2]})
                held, held_since, moved = fingers, time.time(), False
                continue
        elif question is not None and now - last_hand > args.away:   # walked away: back to bed?
            say("I can't see you. The alarm is back.")
            write({"event": "walked_away"})
            question = None
            alarm.start()

        if fingers != held:
            held, held_since, moved = fingers, now, True
        elif question is not None and moved and fingers and now - held_since >= args.hold:
            write({"event": "answer", "fingers": fingers, "right": fingers == question[2]})
            if fingers == question[2]:
                correct += 1
                say("Correct!")
            else:
                say(f"{fingers} is not right. Here is another one.")
            question = None
            held = None

        if args.show:
            view = frame.copy()
            for h in found:
                draw.draw_landmarks(view, h, mp.solutions.hands.HAND_CONNECTIONS)
            top = f"Q: {question[0]} = ?" if question else "show a hand to stop the alarm"
            cv2.putText(view, top, (10, 35), cv2.FONT_HERSHEY_SIMPLEX, 0.9, (0, 255, 0), 2)
            cv2.putText(view, f"fingers: {fingers if fingers is not None else '-'}", (10, 70),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.8, (255, 255, 0), 2)
            cv2.imshow("Sleep Gatekeeper", view)
            if cv2.waitKey(1) == ord("q"):
                break
except KeyboardInterrupt:
    pass
finally:
    alarm.stop()
    cap.release()
    cv2.destroyAllWindows()

if correct >= questions_needed:
    write({"event": "awake"})
    say("Alarm off. " + report["text"])

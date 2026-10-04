#!/usr/bin/env python3
"""The voice journal. This is the half the participant sees.

The webcam notices someone sitting down and the device asks how their day was.
After that it listens, and it does not try to work out from a short pause that
the turn is over, because Part 1 showed that the pauses people leave while they
are thinking run to five seconds and longer.

The turn ends when the person says so. Saying "that's it" ends it, which is panel
5 of the storyboard. Falling silent for eight seconds ends it too, which is well
past the longest pause measured in Part C.

    python journal.py

    camera    someone sits down, the device asks first
    speech    "that's it", "that's all", "I'm done"
    silence   eight seconds with nothing said
    button B  the same thing, for when none of the above works
    button A  ask again, if the camera did not notice

wizard.py can drive the same states from another terminal, as a fallback if a
button fails during a session.
"""

import json
import math
import subprocess
import sys
import threading
import time
import wave
from pathlib import Path

import numpy as np
import sherpa_onnx
import sounddevice as sd

import board
import digitalio
from PIL import Image, ImageDraw, ImageFont
from adafruit_rgb_display import st7789

LAB = Path(__file__).resolve().parent
CONTROL = Path("/tmp/journal_control.json")
ENTRIES = LAB / "entries"
VOICE = "en_US-lessac-medium"
CAMERA = "/dev/video0"
SAMPLE_RATE = 16000

WIDTH, HEIGHT = 240, 135
OPENING = "How was your day?"
CLOSING = "Saved. Same time tomorrow?"

# How different two webcam frames have to be before we call it a person.
MOTION_THRESHOLD = 6.0

# How long a silence has to run before the turn is treated as finished. The
# longest thinking pause measured in Part C was 5.19s, so this leaves room.
SILENCE_END = 8.0

# Said at the end of a turn. Kept to whole phrases: a bare "done" turns up in
# ordinary sentences like "I got a lot done today".
CLOSING_PHRASES = (
    "that's it", "thats it", "that is it",
    "that's all", "thats all", "that is all",
    "that's everything", "thats everything",
    "i'm done", "im done", "i am done",
    "i'm finished", "im finished", "i am finished",
)


def font(size):
    for path in ("/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
                 "/System/Library/Fonts/Supplemental/Arial.ttf"):
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


FONT_BIG = font(22)
FONT_MID = font(15)
FONT_SMALL = font(11)


class Camera(threading.Thread):
    """Watches the webcam and reports whether anything is moving in front of it."""

    daemon = True

    def __init__(self):
        super().__init__()
        self.motion = 0.0
        self.present = False
        self._stop = threading.Event()

    def run(self):
        proc = subprocess.Popen(
            ["ffmpeg", "-loglevel", "quiet", "-f", "v4l2",
             "-video_size", "320x240", "-i", CAMERA,
             "-pix_fmt", "gray", "-s", "160x120", "-r", "4",
             "-f", "rawvideo", "-"],
            stdout=subprocess.PIPE)
        size = 160 * 120
        previous = None
        try:
            while not self._stop.is_set():
                raw = proc.stdout.read(size)
                if len(raw) < size:
                    break
                frame = np.frombuffer(raw, dtype=np.uint8).astype(np.int16)
                if previous is not None:
                    self.motion = float(np.abs(frame - previous).mean())
                    self.present = self.motion > MOTION_THRESHOLD
                previous = frame
        finally:
            proc.terminate()

    def stop(self):
        self._stop.set()


class Recorder:
    """Collects microphone audio for as long as a turn lasts."""

    def __init__(self):
        self.chunks = []
        self.stream = None

    def start(self):
        self.chunks = []
        self.stream = sd.InputStream(channels=1, dtype="float32",
                                     samplerate=SAMPLE_RATE,
                                     callback=lambda data, *_: self.chunks.append(data.copy()))
        self.stream.start()

    def stop(self):
        if self.stream is None:
            return np.zeros(0, dtype=np.float32)
        self.stream.stop()
        self.stream.close()
        self.stream = None
        if not self.chunks:
            return np.zeros(0, dtype=np.float32)
        return np.concatenate(self.chunks).reshape(-1)

    @property
    def seconds(self):
        return sum(len(c) for c in self.chunks) / SAMPLE_RATE

    def drain(self, taken):
        """Everything recorded since the last call, for the watcher to read."""
        chunks = self.chunks[taken:]
        if not chunks:
            return taken, np.zeros(0, dtype=np.float32)
        return len(self.chunks), np.concatenate(chunks).reshape(-1)


def said_closing(text):
    cleaned = "".join(c for c in text.lower() if c.isalnum() or c in " \'")
    return any(phrase in cleaned for phrase in CLOSING_PHRASES)


class TurnWatcher:
    """Listens alongside the recording for a sign that the turn is over.

    Runs the same Silero VAD as listen.py, but not to endpoint with. It is used
    to tell speech from silence, so the eight second rule has something to count,
    and to hand each finished utterance to whisper to check for a closing phrase.
    """

    def __init__(self, recognizer):
        config = sherpa_onnx.VadModelConfig()
        config.silero_vad.model = str(LAB / "models" / "silero_vad.onnx")
        config.silero_vad.min_silence_duration = 0.6
        config.silero_vad.min_speech_duration = 0.25
        config.sample_rate = SAMPLE_RATE
        self.vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=90)
        self.window = config.silero_vad.window_size
        self.recognizer = recognizer
        self.buffer = np.empty(0, dtype=np.float32)
        self.last_voice = time.monotonic()
        self.heard_closing = False

    def feed(self, samples):
        if len(samples) == 0:
            return
        self.buffer = np.concatenate([self.buffer, samples])
        while len(self.buffer) > self.window:
            self.vad.accept_waveform(self.buffer[:self.window])
            self.buffer = self.buffer[self.window:]

        if self.vad.is_speech_detected():
            self.last_voice = time.monotonic()

        while not self.vad.empty():
            utterance = np.array(self.vad.front.samples, dtype=np.float32)
            self.vad.pop()
            self.last_voice = time.monotonic()
            threading.Thread(target=self._check, args=(utterance,), daemon=True).start()

    def _check(self, utterance):
        segments, _ = self.recognizer.transcribe(utterance, beam_size=1)
        text = " ".join(seg.text.strip() for seg in segments)
        if text and said_closing(text):
            print(f"    heard a closing phrase: {text!r}", flush=True)
            self.heard_closing = True

    @property
    def silence(self):
        return time.monotonic() - self.last_voice

    def finished(self):
        return self.heard_closing or self.silence > SILENCE_END


def speak(text):
    """Say a line through Piper. Blocks until it has finished speaking."""
    piper = subprocess.Popen(
        [sys.executable, "-m", "piper", "--model", VOICE,
         "--data-dir", str(LAB / "voices"), "--output-raw", "--", text],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    subprocess.run(["aplay", "-q", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"],
                   stdin=piper.stdout)
    piper.wait()


def save_entry(samples, transcript):
    ENTRIES.mkdir(exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    with wave.open(str(ENTRIES / f"{stamp}.wav"), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes((samples * 32767).astype(np.int16).tobytes())
    (ENTRIES / f"{stamp}.txt").write_text(transcript + "\n")
    return stamp


class Screen:
    def __init__(self):
        cs = digitalio.DigitalInOut(board.D5)
        dc = digitalio.DigitalInOut(board.D25)
        self.disp = st7789.ST7789(board.SPI(), cs=cs, dc=dc, rst=None,
                                  baudrate=64000000, width=135, height=240,
                                  x_offset=53, y_offset=40)
        backlight = digitalio.DigitalInOut(board.D22)
        backlight.switch_to_output()
        backlight.value = True
        self.image = Image.new("RGB", (WIDTH, HEIGHT))
        self.draw = ImageDraw.Draw(self.image)

    def centre(self, text, fnt, y, fill):
        left, _, right, _ = self.draw.textbbox((0, 0), text, font=fnt)
        self.draw.text(((WIDTH - (right - left)) / 2 - left, y), text, font=fnt, fill=fill)

    def wrap(self, text, fnt, width):
        words, lines, line = text.split(), [], ""
        for word in words:
            trial = f"{line} {word}".strip()
            left, _, right, _ = self.draw.textbbox((0, 0), trial, font=fnt)
            if right - left > width and line:
                lines.append(line)
                line = word
            else:
                line = trial
        if line:
            lines.append(line)
        return lines

    def render(self, state, phase, transcript, seconds):
        d = self.draw
        d.rectangle((0, 0, WIDTH, HEIGHT), fill=(8, 8, 10))

        if state == "idle":
            d.ellipse((WIDTH / 2 - 4, HEIGHT / 2 - 4, WIDTH / 2 + 4, HEIGHT / 2 + 4),
                      fill=(55, 55, 60))

        elif state == "asking":
            for i, line in enumerate(self.wrap(OPENING, FONT_BIG, WIDTH - 24)):
                self.centre(line, FONT_BIG, 44 + i * 26, (235, 235, 235))

        elif state == "listening":
            # A slow breath, so a long silence still looks like attention.
            breath = (math.sin(phase * 0.8) + 1) / 2
            radius = 9 + 5 * breath
            glow = int(90 + 120 * breath)
            d.ellipse((WIDTH / 2 - radius, 46 - radius, WIDTH / 2 + radius, 46 + radius),
                      fill=(glow, int(glow * 0.78), 40))
            self.centre("listening...", FONT_MID, 74, (240, 196, 70))
            self.centre(f"{seconds:.0f}s", FONT_SMALL, 98, (110, 110, 110))

        elif state == "thinking":
            d.ellipse((WIDTH / 2 - 11, 46 - 11, WIDTH / 2 + 11, 46 + 11),
                      fill=(196, 92, 92))
            self.centre("finished", FONT_MID, 74, (236, 140, 140))
            dots = "." * (1 + int(phase * 1.2) % 3)
            self.centre(dots, FONT_SMALL, 98, (120, 120, 120))

        elif state == "saved":
            lines = self.wrap(transcript or "(nothing recorded)", FONT_SMALL, WIDTH - 20)
            for i, line in enumerate(lines[:4]):
                d.text((10, 12 + i * 15), line, font=FONT_SMALL, fill=(150, 150, 150))
            self.centre("Saved", FONT_MID, HEIGHT - 42, (120, 210, 140))
            self.centre("same time tomorrow?", FONT_SMALL, HEIGHT - 22, (110, 110, 110))

        self.disp.image(self.image, 90)


def read_command():
    """Take one command from the wizard, if there is one waiting."""
    try:
        payload = json.loads(CONTROL.read_text())
    except (OSError, ValueError):
        return None
    CONTROL.unlink(missing_ok=True)
    return payload


def main():
    print("Loading whisper...", flush=True)
    from faster_whisper import WhisperModel
    recognizer = WhisperModel("tiny.en", device="cpu", compute_type="int8")

    CONTROL.unlink(missing_ok=True)
    screen = Screen()
    camera = Camera()
    camera.start()
    recorder = Recorder()

    button_a = digitalio.DigitalInOut(board.D23)
    button_b = digitalio.DigitalInOut(board.D24)
    button_a.switch_to_input()
    button_b.switch_to_input()
    was_a = was_b = False

    state = "idle"
    watcher = None
    taken = 0
    phase = 0.0
    transcript = ""
    seen_since = None
    state_entered = time.monotonic()
    pending = None

    def enter(new_state):
        nonlocal state, state_entered
        state = new_state
        state_entered = time.monotonic()
        print(f"[{new_state}]", flush=True)
        Path("/tmp/journal_state").write_text(new_state)

    def do_ask():
        nonlocal state, watcher, taken
        if state == "listening":
            recorder.stop()          # asking again abandons the turn in progress
        enter("asking")
        speak(OPENING)
        time.sleep(2.0)              # the pause from the Part 1 script
        watcher = TurnWatcher(recognizer)
        taken = 0
        recorder.start()
        enter("listening")

    def do_end():
        nonlocal pending
        samples = recorder.stop()
        enter("thinking")

        def transcribe(audio):
            nonlocal pending
            if len(audio) < SAMPLE_RATE // 2:
                pending = ("", audio)
                return
            segments, _ = recognizer.transcribe(audio, beam_size=1)
            pending = (" ".join(s.text.strip() for s in segments), audio)

        threading.Thread(target=transcribe, args=(samples,), daemon=True).start()

    enter("idle")
    print("Ready. Button B ends a turn, button A asks again.", flush=True)

    try:
        while True:
            phase += 0.1
            now = time.monotonic()
            command = read_command()
            action = command.get("action") if command else None

            if action == "quit":
                break
            if action == "reset":
                if state == "listening":
                    recorder.stop()
                transcript = ""
                enter("idle")
            elif action == "say" and command.get("text"):
                speak(command["text"])
            elif action == "ask":
                do_ask()
            elif action == "end" and state == "listening":
                do_end()

            # The person ends their own turn, either by saying so or by going
            # quiet for long enough that they clearly have.
            if state == "listening" and watcher is not None:
                taken, fresh = recorder.drain(taken)
                watcher.feed(fresh)
                if watcher.finished():
                    why = "a closing phrase" if watcher.heard_closing else \
                          f"{watcher.silence:.0f}s of silence"
                    print(f"    turn ended by {why}", flush=True)
                    do_end()

            # Buttons are active low, so False is pressed. Acting on the change
            # stops one press counting as many.
            a, b = not button_a.value, not button_b.value
            if b and not was_b and state == "listening":
                print("    button B: the person ended their turn", flush=True)
                do_end()
            elif a and not was_a and state in ("idle", "saved"):
                print("    button A: asking again", flush=True)
                do_ask()
            was_a, was_b = a, b

            # The camera starts the conversation, the way panel 3 of the
            # storyboard has it: the device notices someone and asks first.
            if state == "idle":
                if camera.present:
                    seen_since = seen_since or now
                    if now - seen_since > 1.5:
                        seen_since = None
                        do_ask()
                else:
                    seen_since = None

            if state == "thinking" and pending is not None:
                transcript, audio = pending
                pending = None
                stamp = save_entry(audio, transcript)
                print(f"    saved {stamp}: {transcript!r}", flush=True)
                enter("saved")
                speak(CLOSING)

            if state == "saved" and now - state_entered > 12:
                enter("idle")

            screen.render(state, phase, transcript,
                          recorder.seconds if state == "listening" else 0)
            time.sleep(0.05)
    except KeyboardInterrupt:
        pass
    finally:
        camera.stop()
        if recorder.stream is not None:
            recorder.stop()
        print("\nStopped.")


if __name__ == "__main__":
    main()

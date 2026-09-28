#!/usr/bin/env python3
"""Ask for a number out loud, wait for the answer, and write it down.

    python ask_number.py
    python ask_number.py --question "What is your zip code?"
    python ask_number.py --min-silence 1.0

Numbers are where transcription goes wrong in a way you can see. Whisper will
sometimes give you digits, sometimes the words, and sometimes a mix, so the
script prints what it heard and what it made of it side by side. The recording
and the transcript are saved next to each other so the errors can be looked at
again later.
"""

import argparse
import datetime as dt
import re
import subprocess
import sys
import wave
from pathlib import Path

import numpy as np
import sherpa_onnx
import sounddevice as sd
from faster_whisper import WhisperModel

LAB = Path(__file__).resolve().parent
VOICE = "en_US-lessac-medium"
SAMPLE_RATE = 16000
ANSWERS = LAB / "answers"

WORDS = {
    "zero": "0", "oh": "0", "o": "0", "one": "1", "two": "2", "three": "3",
    "four": "4", "five": "5", "six": "6", "seven": "7", "eight": "8",
    "nine": "9", "ten": "10", "eleven": "11", "twelve": "12",
}


def speak(text):
    """Say something through Piper, straight to the speaker."""
    piper = subprocess.Popen(
        [sys.executable, "-m", "piper", "--model", VOICE,
         "--data-dir", str(LAB / "voices"), "--output-raw", "--", text],
        stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    subprocess.run(["aplay", "-q", "-r", "22050", "-f", "S16_LE", "-t", "raw", "-"],
                   stdin=piper.stdout)
    piper.wait()


def listen_once(min_silence):
    """Record until the speaker stops, and return the samples."""
    config = sherpa_onnx.VadModelConfig()
    config.silero_vad.model = str(LAB / "models" / "silero_vad.onnx")
    config.silero_vad.min_silence_duration = min_silence
    config.silero_vad.min_speech_duration = 0.25
    config.sample_rate = SAMPLE_RATE
    vad = sherpa_onnx.VoiceActivityDetector(config, buffer_size_in_seconds=60)
    window = config.silero_vad.window_size

    buffer = np.empty(0, dtype=np.float32)
    with sd.InputStream(channels=1, dtype="float32", samplerate=SAMPLE_RATE) as stream:
        while True:
            chunk, _ = stream.read(int(0.1 * SAMPLE_RATE))
            buffer = np.concatenate([buffer, chunk.reshape(-1)])
            while len(buffer) > window:
                vad.accept_waveform(buffer[:window])
                buffer = buffer[window:]
            if not vad.empty():
                samples = np.array(vad.front.samples, dtype=np.float32)
                vad.pop()
                return samples


def digits_in(text):
    """Pull a digit string out of whatever form the answer arrived in."""
    out = []
    for token in re.findall(r"[a-z]+|\d+", text.lower()):
        if token.isdigit():
            out.append(token)
        elif token in WORDS:
            out.append(WORDS[token])
    return "".join(out)


def save(samples, question, heard, digits):
    ANSWERS.mkdir(exist_ok=True)
    stamp = dt.datetime.now().strftime("%Y%m%d_%H%M%S")
    wav_path = ANSWERS / f"{stamp}.wav"
    with wave.open(str(wav_path), "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(SAMPLE_RATE)
        f.writeframes((samples * 32767).astype(np.int16).tobytes())
    (ANSWERS / f"{stamp}.txt").write_text(
        f"question: {question}\nheard:    {heard}\ndigits:   {digits}\n")
    return wav_path


def main():
    parser = argparse.ArgumentParser(description=__doc__,
                                     formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--question", default="How many pets do you have?")
    parser.add_argument("--model", default="tiny.en")
    parser.add_argument("--min-silence", type=float, default=1.0,
                        help="silence before the answer counts as finished")
    args = parser.parse_args()

    print("Loading the model...", flush=True)
    recognizer = WhisperModel(args.model, device="cpu", compute_type="int8")

    speak(args.question)
    print(f"\n{args.question}")
    print("listening...", flush=True)

    samples = listen_once(args.min_silence)
    segments, _ = recognizer.transcribe(samples, beam_size=1)
    heard = " ".join(s.text.strip() for s in segments)
    digits = digits_in(heard)

    print(f"\n  {len(samples) / SAMPLE_RATE:.1f}s of speech")
    print(f"  heard   {heard!r}")
    print(f"  digits  {digits or '(none found)'}")
    print(f"  saved   {save(samples, args.question, heard, digits)}")

    speak(f"I heard {digits}" if digits else "I did not catch a number.")


if __name__ == "__main__":
    main()

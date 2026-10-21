#!/usr/bin/env python3
"""The controller. This is the half the wizard sees, and the participant does not.

The one thing the device cannot decide for itself is when a turn is over, so
that is what this is for. Everything else it does on its own.

    python wizard.py

    a   ask the opening question and start listening
    e   end the turn: the person has finished, go and transcribe
    r   reset to idle
    s   say something off script, typed in
    q   quit the journal
"""

import json
import sys
import termios
import tty
from pathlib import Path

CONTROL = Path("/tmp/journal_control.json")
STATE = Path("/tmp/journal_state")

KEYS = {
    "a": ("ask", "asked, now listening"),
    "e": ("end", "turn ended"),
    "r": ("reset", "back to idle"),
    "q": ("quit", "quitting"),
}


def send(action, **extra):
    CONTROL.write_text(json.dumps({"action": action, **extra}))


def read_key():
    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setraw(fd)
        return sys.stdin.read(1)
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def main():
    print(__doc__.split("\n", 2)[2])
    print("waiting for keys. journal.py should already be running.\n")
    while True:
        key = read_key()
        if key in ("\x03", "\x04"):
            print("controller closed")
            return
        if key == "s":
            print("\nsay: ", end="", flush=True)
            text = sys.stdin.readline().strip()
            if text:
                send("say", text=text)
                print(f"  -> spoke {text!r}")
            continue
        if key not in KEYS:
            continue
        action, note = KEYS[key]
        send(action)
        current = STATE.read_text().strip() if STATE.exists() else "?"
        print(f"  {key}  {note:24} (device was: {current})")
        if action == "quit":
            return


if __name__ == "__main__":
    main()

# Render cup_clock.py without a Raspberry Pi attached.
#
# Draws the clock in a few different states and writes them to one PNG, so the
# layout can be worked on from a laptop and only taken to the Pi once it looks
# right. Needs pillow, nothing else.
#
#   python preview_cup_clock.py [output.png]

import sys

from PIL import Image, ImageDraw

from cup_clock import CupState, draw_frame, HEIGHT, MODES, WIDTH

SCALE = 3

# Each frame is: which cup is on screen, how full each substance is, whether a
# hand is on the door handle, and what the frame is meant to show.
FRAMES = [
    ("ALCOHOL", {"ALCOHOL": 1.00}, False, "just logged a drink"),
    ("ALCOHOL", {"ALCOHOL": 0.55}, False, "halfway there"),
    ("ALCOHOL", {"ALCOHOL": 0.00}, False, "beer is clear"),
    ("CAFFEINE", {"CAFFEINE": 0.80}, False, "caffeine, still wired"),
    ("CAFFEINE", {"CAFFEINE": 0.80, "ALCOHOL": 0.4}, False,
     "coffee on screen, beer still pending - note the dim lamp"),
    ("CAFFEINE", {"CAFFEINE": 0.80, "ALCOHOL": 0.4}, True,
     "reaching for the door: alcohol is what counts, not the cup shown"),
    ("CAFFEINE", {"CAFFEINE": 0.80, "ALCOHOL": 0.4}, True, "the other half of the flash"),
    ("CAFFEINE", {"CAFFEINE": 0.80}, True, "coffee left but no alcohol - fine to drive"),
]


def build_sheet():
    sheet = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE * len(FRAMES)), "black")

    for row, (mode, fills, touching, _) in enumerate(FRAMES):
        state = CupState(mode)
        for name, fill in fills.items():
            state.left[name] = fill * MODES[name]["clear_seconds"]

        # Consecutive warning rows show the two halves of the flash, so step the
        # phase between them rather than letting it follow the row number.
        phase = (0.0 if row % 2 else 1.4) if touching else row * 1.3

        frame = Image.new("RGB", (WIDTH, HEIGHT))
        draw_frame(ImageDraw.Draw(frame), state, phase=phase, touching=touching)
        sheet.paste(frame.resize((WIDTH * SCALE, HEIGHT * SCALE), Image.NEAREST),
                    (0, row * HEIGHT * SCALE))

    return sheet


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "cup_clock_preview.png"
    build_sheet().save(out)
    for mode, fills, touching, caption in FRAMES:
        held = " ".join(f"{n[0]}={v:.0%}" for n, v in fills.items())
        hand = "hand" if touching else "    "
        print(f"  show {mode:<9} {held:<16} {hand}  {caption}")
    print(f"wrote {out}")

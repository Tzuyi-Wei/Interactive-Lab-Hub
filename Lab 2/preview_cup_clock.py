# Render cup_clock.py without a Raspberry Pi attached.
#
# Draws the clock at a few different fill levels and writes them to one PNG, so
# the layout can be worked on from a laptop and only taken to the Pi once it
# looks right. Needs pillow, nothing else.
#
#   python preview_cup_clock.py [output.png]

import sys

from PIL import Image, ImageDraw

from cup_clock import CupState, draw_frame, HEIGHT, MODES, WIDTH

SCALE = 3
FRAMES = [
    ("ALCOHOL", 1.00, "just logged a drink"),
    ("ALCOHOL", 0.55, "halfway there"),
    ("ALCOHOL", 0.00, "clear to drive"),
    ("CAFFEINE", 0.80, "caffeine, still wired"),
]


def build_sheet():
    sheet = Image.new("RGB", (WIDTH * SCALE, HEIGHT * SCALE * len(FRAMES)), "black")

    for row, (mode, fill, _) in enumerate(FRAMES):
        state = CupState(mode)
        state.remaining = fill * MODES[mode]["clear_seconds"]

        frame = Image.new("RGB", (WIDTH, HEIGHT))
        draw_frame(ImageDraw.Draw(frame), state, phase=row * 1.3)
        sheet.paste(frame.resize((WIDTH * SCALE, HEIGHT * SCALE), Image.NEAREST),
                    (0, row * HEIGHT * SCALE))

    return sheet


if __name__ == "__main__":
    out = sys.argv[1] if len(sys.argv) > 1 else "cup_clock_preview.png"
    build_sheet().save(out)
    for mode, fill, caption in FRAMES:
        print(f"  {mode:<9} {fill:>4.0%}  {caption}")
    print(f"wrote {out}")

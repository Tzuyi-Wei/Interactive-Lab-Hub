import math
import random
import time

from PIL import Image, ImageDraw, ImageFont

# --- Tunables ---------------------------------------------------------------

# How long the body takes to clear one serving. The real figures are roughly one
# hour for a standard drink and about five hours for a cup of coffee; DEMO_SPEED
# runs the clock faster so the draining is visible in a short video.
DEMO_SPEED = 60  # 1 = real time, 60 = one hour of metabolism per minute

# Which MPR121 channel the copper tape on the door handle is clipped to.
HANDLE_CHANNEL = 0

# Fallback door handle: SparkFun Qwiic button. Register map is the one used in
# the course's own button_device.py.
QWIIC_BUTTON_ADDRESS = 0x6F
QWIIC_BUTTON_STATUS = 0x03
QWIIC_BUTTON_PRESSED = 0x04

MODES = {
    "ALCOHOL": {
        "clear_seconds": 60 * 60,
        "liquid": (255, 176, 59),
        "background": (46, 6, 6),
        "accent": (231, 76, 60),
        # A beer mug is heavy and almost straight-sided, and it carries a head.
        "taper": 3,
        "foam": True,
        "ribs": True,
        "handle_width": 4,
    },
    "CAFFEINE": {
        "clear_seconds": 5 * 60 * 60,
        "liquid": (138, 84, 44),
        "background": (6, 33, 16),
        "accent": (46, 204, 113),
        "taper": 10,
        "foam": False,
        "ribs": False,
        "handle_width": 3,
    },
}
MODE_ORDER = list(MODES)

WIDTH, HEIGHT = 240, 135

# Left column holds the two mode lamps, the vessel lives to the right of it.
PANEL_W = 60
CUP = {"left": 88, "right": 168, "top": 12, "bottom": 88}
HANDLE = {"left": 152, "right": 188, "top": 30, "bottom": 66}

FOAM_HEIGHT = 13
FOAM_COLOUR = (252, 249, 238)
FOAM_SHADOW = (223, 214, 190)
FOAM_HIGHLIGHT = (255, 255, 252)

# Bubble positions are picked once with a fixed seed, so the foam looks
# irregular but does not flicker into a new arrangement every frame.
_rng = random.Random(7)
FOAM_BUBBLES = [(_rng.uniform(0.04, 0.96), _rng.uniform(0.25, 0.95),
                 _rng.choice((0, 0, 0, 1)), _rng.random() < 0.35)
                for _ in range(44)]
RISING_BUBBLES = [(_rng.uniform(0.12, 0.88), _rng.random(),
                   _rng.choice((1, 1, 2))) for _ in range(10)]


def _cup_edges(y, taper):
    """Left and right edge of the vessel at height y, following its taper."""
    ratio = (y - CUP["top"]) / (CUP["bottom"] - CUP["top"])
    inset = taper * ratio
    return CUP["left"] + inset, CUP["right"] - inset


def _font(size, bold=False):
    """Load DejaVu on the Pi, fall back to a Mac face when previewing."""
    candidates = [
        "/usr/share/fonts/truetype/dejavu/DejaVuSansMono-Bold.ttf" if bold
        else "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
        "/System/Library/Fonts/Menlo.ttc",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
    ]
    for path in candidates:
        try:
            return ImageFont.truetype(path, size)
        except OSError:
            continue
    return ImageFont.load_default()


FONT_TIME = _font(22, bold=True)
FONT_WARN = _font(24, bold=True)
FONT_SMALL = _font(11)
FONT_TINY = _font(9)


class CupState:
    """How much metabolising is still owed, in seconds, for each substance.

    The two are tracked separately and drain at the same time: drinking a beer
    does not clear your coffee, and switching the display does not move either
    of them. Only what is on screen changes.
    """

    def __init__(self, mode="ALCOHOL"):
        self.mode = mode
        self.left = {name: 0.0 for name in MODE_ORDER}

    @property
    def spec(self):
        return MODES[self.mode]

    @property
    def remaining(self):
        """Seconds still owed for the substance currently on screen."""
        return self.left[self.mode]

    @remaining.setter
    def remaining(self, value):
        self.left[self.mode] = max(0.0, value)

    @property
    def alcohol_remaining(self):
        """Driving safety depends on this one only - caffeine does not count."""
        return self.left["ALCOHOL"]

    def add_serving(self):
        self.remaining += self.spec["clear_seconds"]

    def next_mode(self):
        # Purely a change of view. Both substances keep their own countdown.
        self.mode = MODE_ORDER[(MODE_ORDER.index(self.mode) + 1) % len(MODE_ORDER)]

    def reset(self):
        """Empty the cup on screen, leaving the other substance alone."""
        self.remaining = 0.0

    def tick(self, elapsed):
        # Everything in the body metabolises at once, not just what is on screen.
        for name in self.left:
            self.left[name] = max(0.0, self.left[name] - elapsed * DEMO_SPEED)

    @property
    def fill(self):
        """0.0 empty to 1.0 full - one serving fills the vessel exactly."""
        return min(self.remaining / self.spec["clear_seconds"], 1.0)

    @property
    def servings_left(self):
        return math.ceil(self.remaining / self.spec["clear_seconds"])

    def countdown(self, name=None):
        total = int(self.left[name] if name else self.remaining)
        return f"{total // 3600:01d}:{total // 60 % 60:02d}:{total % 60:02d}"


def _wavy_surface(draw, x0, x1, y, colour, phase):
    """A shallow sine wave so the liquid reads as liquid, not as a bar."""
    points = [(x, y + 2.0 * math.sin((x / 9.0) + phase))
              for x in range(int(x0), int(x1) + 1)]
    draw.line(points, fill=colour, width=3)


def _draw_foam(draw, x0, x1, surface_y, phase):
    """A head of fine foam sitting on the beer, bubbles and all."""
    top = surface_y - FOAM_HEIGHT

    # Solid body of the head, then a crown of overlapping circles so the top
    # edge is lumpy instead of a flat line.
    draw.rectangle((x0, top + 4, x1, surface_y), fill=FOAM_COLOUR)
    # Step well under the radius so neighbouring blobs overlap - spaced any
    # wider and the gaps between them show through as notches in the head.
    for index in range(int((x1 - x0) // 4) + 1):
        cx = x0 + 2 + index * 4
        radius = 4.2 + 1.4 * math.sin(index * 1.9 + phase * 0.25)
        draw.ellipse((cx - radius, top + 4 - radius, cx + radius, top + 4 + radius),
                     fill=FOAM_COLOUR)

    # Fine bubbles. Most are a single pixel of shadow; a few are brighter than
    # the foam itself, which is what makes a head look carbonated rather than
    # like a flat white band.
    for rel_x, rel_y, radius, bright in FOAM_BUBBLES:
        bx = x0 + rel_x * (x1 - x0)
        by = top + 4 + rel_y * (FOAM_HEIGHT - 4)
        colour = FOAM_HIGHLIGHT if bright else FOAM_SHADOW
        draw.ellipse((bx - radius, by - radius, bx + radius, by + radius),
                     fill=colour)


def _draw_rising_bubbles(draw, level, base_y, taper, phase):
    """A few bubbles drifting up through the beer towards the head."""
    if base_y - level < 6:
        return
    for rel_x, offset, radius in RISING_BUBBLES:
        progress = (phase * 0.04 + offset) % 1.0
        by = base_y - (base_y - level) * progress
        left, right = _cup_edges(by, taper)
        bx = left + 4 + rel_x * (right - left - 8)
        draw.ellipse((bx - radius, by - radius, bx + radius, by + radius),
                     fill=(255, 231, 178))


def _centre_text(draw, text, font, y, fill):
    left, _, right, _ = draw.textbbox((0, 0), text, font=font)
    draw.text(((WIDTH - (right - left)) / 2 - left, y), text, font=font, fill=fill)


def _draw_reach_response(draw, state, phase):
    """What the screen does while a hand is on the door handle."""
    # Only alcohol decides this. Caffeine can still be counting down behind the
    # scenes and it makes no difference to whether you may drive.
    if state.alcohol_remaining <= 0:
        draw.rectangle((0, 0, WIDTH, HEIGHT), fill=(4, 40, 20))
        draw.rectangle((3, 3, WIDTH - 4, HEIGHT - 4), outline=(46, 204, 113), width=3)
        _centre_text(draw, "SAFE TO DRIVE", FONT_WARN, 42, (46, 204, 113))
        _centre_text(draw, "no alcohol left", FONT_SMALL, 80, (150, 200, 170))
        return

    # Flash roughly three times a second - fast enough to read as an alarm,
    # slow enough that a phone camera catches both states in a video.
    bright = int(phase * 0.85) % 2 == 0
    draw.rectangle((0, 0, WIDTH, HEIGHT),
                   fill=(214, 28, 28) if bright else (56, 2, 2))
    draw.rectangle((3, 3, WIDTH - 4, HEIGHT - 4),
                   outline=(255, 255, 255) if bright else (120, 10, 10), width=4)

    _centre_text(draw, "DON'T DRIVE", FONT_WARN, 34, (255, 255, 255))
    _centre_text(draw, state.countdown("ALCOHOL"), FONT_TIME, 68,
                 (255, 255, 255) if bright else (200, 120, 120))
    _centre_text(draw, "still in your body", FONT_SMALL, 100, (255, 210, 210))


def draw_frame(draw, state, phase=0.0, touching=False):
    """Render one frame of the clock onto a 240x135 drawing surface."""
    if touching:
        _draw_reach_response(draw, state, phase)
        return

    spec = state.spec
    taper = spec["taper"]
    empty = state.remaining <= 0

    draw.rectangle((0, 0, WIDTH, HEIGHT), fill=spec["background"])

    # --- left panel: which substance are we counting down ------------------
    for index, name in enumerate(MODE_ORDER):
        cy = 40 + index * 40
        active = name == state.mode
        pending = state.left[name] > 0
        accent = MODES[name]["accent"]
        colour = accent if active else (70, 70, 70)
        draw.ellipse((14, cy - 10, 34, cy + 10), fill=accent if active else None,
                     outline=colour, width=2)
        if pending and not active:
            # A dim core: not the substance you are looking at, but still in you.
            dim = tuple(c // 3 for c in accent)
            draw.ellipse((19, cy - 5, 29, cy + 5), fill=dim)
        draw.text((40, cy - 6), name[0], font=FONT_SMALL,
                  fill=accent if active else (110, 110, 110))
    draw.line((PANEL_W, 10, PANEL_W, HEIGHT - 10), fill=(70, 70, 70), width=1)

    # --- the vessel --------------------------------------------------------
    outline = (235, 235, 235)
    # Handle first, so the wall is drawn over where the two meet. A half circle
    # puts both ends of the handle flat against that wall.
    draw.arc((HANDLE["left"], HANDLE["top"], HANDLE["right"], HANDLE["bottom"]),
             start=-90, end=90, fill=outline, width=spec["handle_width"])

    if not empty:
        top_y = CUP["top"] + 3
        base_y = CUP["bottom"] - 3
        # When there is a head, a full glass means "liquid plus foam reaches the
        # rim", so the liquid itself stops one head short of the top.
        head = FOAM_HEIGHT if spec["foam"] else 0
        full_y = top_y + head + (3 if spec["foam"] else 0)
        level = max(base_y - (base_y - full_y) * state.fill, full_y)

        left_at_level, right_at_level = _cup_edges(level, taper)
        left_at_base, right_at_base = _cup_edges(base_y, taper)
        draw.polygon(
            [(left_at_level + 3, level), (right_at_level - 3, level),
             (right_at_base - 3, base_y), (left_at_base + 3, base_y)],
            fill=spec["liquid"],
        )

        if spec["ribs"]:
            # Vertical ribs, the way a moulded beer mug catches the light.
            for fraction in (0.22, 0.5, 0.78):
                rib_x = left_at_level + fraction * (right_at_level - left_at_level)
                draw.line((rib_x, level + 3, rib_x, base_y - 2),
                          fill=(255, 196, 104), width=1)

        if spec["foam"]:
            _draw_rising_bubbles(draw, level, base_y, taper, phase)
            _draw_foam(draw, left_at_level + 3, right_at_level - 3, level, phase)
        else:
            _wavy_surface(draw, left_at_level + 3, right_at_level - 3, level,
                          spec["liquid"], phase)

    draw.polygon(
        [(CUP["left"], CUP["top"]), (CUP["right"], CUP["top"]),
         (CUP["right"] - taper, CUP["bottom"]), (CUP["left"] + taper, CUP["bottom"])],
        outline=outline, width=3,
    )

    if state.servings_left > 1:
        draw.text((CUP["left"] + 8, CUP["top"] + 5), f"x{state.servings_left}",
                  font=FONT_SMALL, fill=(25, 25, 25))

    # --- countdown ---------------------------------------------------------
    label = "CLEAR" if empty else state.countdown()
    colour = spec["accent"] if empty else (255, 255, 255)
    left, _, right, _ = draw.textbbox((0, 0), label, font=FONT_TIME)
    centre = PANEL_W + (WIDTH - PANEL_W) / 2
    draw.text((centre - (right - left) / 2 - left, CUP["bottom"] + 8),
              label, font=FONT_TIME, fill=colour)

    draw.text((PANEL_W + 8, HEIGHT - 12), "A mode    B +1 cup", font=FONT_TINY,
              fill=(120, 120, 120))


def _open_door_handle(i2c):
    """Return a callable that reports whether a hand is on the door handle.

    Prefers the MPR121 and its copper tape; falls back to a Qwiic button if no
    MPR121 answers. Returns None when neither is connected, in which case the
    clock still runs and simply never shows the warning.
    """
    try:
        import adafruit_mpr121
        pad = adafruit_mpr121.MPR121(i2c)[HANDLE_CHANNEL]
        print("door handle: MPR121 copper tape")
        return lambda: pad.value
    except (ImportError, ValueError, OSError, RuntimeError):
        pass

    try:
        from adafruit_bus_device.i2c_device import I2CDevice
        button = I2CDevice(i2c, QWIIC_BUTTON_ADDRESS)

        def pressed():
            buf = bytearray(1)
            with button:
                button.write_then_readinto(
                    QWIIC_BUTTON_STATUS.to_bytes(1, "little"), buf)
            return bool(buf[0] & QWIIC_BUTTON_PRESSED)

        pressed()  # fail here rather than mid-loop if the button is not there
        print("door handle: Qwiic button (MPR121 not found)")
        return pressed
    except (ImportError, ValueError, OSError, RuntimeError):
        pass

    print("door handle: none found, warning disabled")
    return None


def main():
    import board
    import digitalio
    from adafruit_rgb_display import st7789

    cs_pin = digitalio.DigitalInOut(board.D5)
    dc_pin = digitalio.DigitalInOut(board.D25)
    disp = st7789.ST7789(
        board.SPI(),
        cs=cs_pin,
        dc=dc_pin,
        rst=None,
        baudrate=64000000,
        width=135,
        height=240,
        x_offset=53,
        y_offset=40,
    )

    backlight = digitalio.DigitalInOut(board.D22)
    backlight.switch_to_output()
    backlight.value = True

    button_a = digitalio.DigitalInOut(board.D23)
    button_b = digitalio.DigitalInOut(board.D24)
    button_a.switch_to_input()
    button_b.switch_to_input()

    handle = _open_door_handle(board.I2C())

    image = Image.new("RGB", (WIDTH, HEIGHT))
    draw = ImageDraw.Draw(image)
    state = CupState()

    was_a = was_b = False
    last = time.monotonic()
    phase = 0.0

    while True:
        now = time.monotonic()
        state.tick(now - last)
        last = now

        # Buttons are active-low, so False means pressed. Acting on the change
        # rather than the level stops one press counting as dozens of cups.
        a, b = not button_a.value, not button_b.value
        if a and b:
            state.reset()
        elif a and not was_a:
            state.next_mode()
        elif b and not was_b:
            state.add_serving()
        was_a, was_b = a, b

        touching = handle() if handle is not None else False

        phase += 0.35
        draw_frame(draw, state, phase, touching=touching)
        disp.image(image, 90)
        time.sleep(0.05)


if __name__ == "__main__":
    main()

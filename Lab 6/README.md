# Distributed Interaction

**TODO: team names (netIDs)**

**Help.** We used Claude (AI) to help write and debug the code (`burger/server.py`, the big
screen page and `burger/pi/pan.py`) and to analyse the motion recordings. The game idea, the
design decisions and the testing are our own.

---

# Part A. MQTT Messaging

\*\*\***Brainstorm 5 ideas for messaging between devices.**\*\*\*

We started from "a two-player game where each player's Pi is a controller", and these are the
ideas we went through before settling on Pan Burger (Part C). Each one is a few sensors talking
to one referee over MQTT.

1. **Finger math duel.** A referee Pi publishes a math question on `IDD/<team>/duel/question`;
   each player answers by holding up fingers to their Pi's camera (MediaPipe hands, reused from
   Lab 5) and publishes `{"fingers": 4, "t": 1.82}`. Each Pi measures its own reaction time from
   when *it* received the question, so network delay does not decide who wins.
2. **Quick draw.** The referee waits a random time and publishes `GO`; the first player to swipe
   over their proximity sensor wins, and moving before `GO` loses. Simple enough to understand from
   across the room, but it shows the fairness problem: whose message arrives first is not the
   same as who moved first.
3. **Colour race.** The referee shows a target colour; players race to find an object of that
   colour and hold it to their APDS-9960 (the sensor from Part B), publishing the RGB they read.
4. **Tug of war.** Each player waves a hand over a proximity sensor as fast as they can; each Pi
   publishes its count every 100 ms and the referee moves a rope on the big screen by the
   difference.
5. **Flip the bacon.** Each player holds a "pan" with a motion sensor and flips a strip of bacon
   on the shared screen at the right moment, not raw and not burnt; a third player turns the heat
   up and down. This grew into Pan Burger: more ingredients, chopping and stacking, and passing
   food between the two pans.

**Inventing our own topics.** MQTT agreed on nothing in advance, which made it quick to start:
we picked topics like `IDD/panburger/burger/p1/gesture` and payloads like `{"type": "flip"}`
and could test them with `mosquitto_pub` before any Pi code existed. The cost is that nothing
else understands them; a "light" in Matter behaves the same everywhere, our "flip" only means
something to our server.

---

# Part B. Collaborative Pixel Grid

\*\*\***Include: screenshot of grid + photo of your Pi setup.**\*\*\*

Each Pi reads its APDS-9960 and publishes `{"mac": ..., "r": ..., "g": ..., "b": ...}` to
`IDD/pixelgrid/colors` ten times a second; the grid server gives every MAC address its own cell
and repaints it live. Our Pi is the left cell:

<img src="imgs/partB_pi.jpg" alt="A laptop showing the pixel grid at localhost:5052 with two cells, light blue on the left and pink on the right; in front, a hand holds a blue sticky note to the APDS-9960 taped on the cardboard pan" width="520" />
<img src="imgs/partB_grid.jpg" alt="Screenshot of the grid with no cards held: both cells are pink" width="300" />

<img src="imgs/partB_screen.jpg" alt="Our Pi taped to the cardboard: the Mini PiTFT shows the JSON it publishes, mac 88:a2:9e:c8:40:86, ip 172.20.10.2, r 255, g 156, b 202 and a timestamp" width="300" />

Our Pi's Mini PiTFT shows the message it is publishing: here RGB(255, 156, 202), the pink of
the room light.

* **Holding the blue sticky note** to the sensor turns our cell light blue.
* **With no card, the cell is pink.** The room light is warm, and the example scales every
  reading so that its largest channel is 255, so "white-ish with a bit more red" becomes pink.
  Our Part C calibration measured the same thing: "no card" read as red 0.48, green 0.28,
  blue 0.24.
* **The cell changes slowly**, about once every 0.7 s. The example sets
  `sensor.integration_time = 10`, but the library's property is called
  `color_integration_time`, so the line only creates an unused attribute and the sensor keeps
  its default of 256 cycles (≈ 0.7 s per reading). We hit the same thing in Part C.
* **How we ran it.** The class grid (`farlab.infosci.cornell.edu:5000`) did not answer from our
  network, so we ran the Lab's `app.py` on the laptop. macOS uses port 5000 for AirPlay, so we
  ran it on port 5052. The examples are written for paho-mqtt 1.x and our Pis have 2.x; a small
  launcher sets the version-1 callback API before running them, so the example files are
  unchanged.

---

# Part C. Pan Burger

## 1. Project description

**Pan Burger** is a two-player cooking game. Each player holds a **pan**: a Raspberry Pi with
a 6-DoF motion sensor, a colour sensor and its Mini PiTFT screen. The laptop shows a burger
shop in first person: customers queue from left to right, each with a speech bubble showing the
burger they want and a patience bar.

<img src="imgs/burger_play.png" alt="The big screen during a two-player round (Level 2, Lunch Rush): two customers in the queue with order bubbles (cheese; lettuce) and patience bars, the first one outlined green because P2's plate matches its order so far. Below, a steel kitchen counter for P1 and P2. P1 is in Grill mode with a patty cooking (side A face down) and one cooked patty in its Ready tray; P2 is in Assembly mode with a bottom bun on a plate, lettuce on the board with 3 of 5 chops, and chopped lettuce in its Ready tray" width="720" />

Every burger is built **bottom to top**: bun → fillings in the customer's order → bun. Fillings
are random (only the buns are required): one customer wants two patties and cheese, the next one
only lettuce. Ingredients are **colour cards** (sticky notes: orange, pink, yellow and blue) held
to the pan's colour sensor, and some of them need work first:

| Ingredient | Card | Work needed |
|---|---|---|
| Patty | pink | Grill it: put the card in the pan, **toss the pan up** to flip it when the side facing down is done. Both sides cooked = ready; wait too long = burnt (−3) |
| Lettuce | blue | Chop it: **chop down** with the pan 5 times |
| Cheese | yellow | Nothing |
| Bun | orange | Nothing |

Each pan can be one of three stations, and the player switches with the two buttons on the
PiTFT (A = previous, B = next): **grill** (screen red, "PAN"), **board** (green, "KNIFE") and
**assembly** (blue, "PLATE"). In assembly mode a plate appears by itself, and the player scans
cards in order. Finishing the top bun serves the burger to the first customer who ordered exactly
that. A customer who waits too long leaves angry (−5).

**Why it is interesting.** The two pans are identical, so the team decides how to split the work:
one player can grill while the other chops and assembles, or both can do everything. Cooked food
sits in a player's own "ready" tray, and a **forward swing** of the pan throws one item to the
partner's tray. That is the point where two devices have to cooperate, and it only works because
the laptop keeps one shared state for both. There is also a single-player mode (fewer, more
patient customers) and three levels.

<img src="imgs/burger_lobby.png" alt="Start screen: choose Single or Two-player co-op, choose Level 1 First Day, 2 Lunch Rush or 3 Peak Hour, and an Open the shop! button; the rules are summarised below" width="520" />

---

## 2. Architecture

```mermaid
flowchart LR
  subgraph P1["Pan P1 (Raspberry Pi)"]
    I1["LSM6DS3TR-C 6-DoF<br/>APDS-9960 colour + proximity<br/>PiTFT buttons A / B"] --> C1["pan.py<br/>100 Hz: flip / toss / chop<br/>card colour → ingredient<br/>buttons → mode"]
    C1 --> O1["PiTFT: mode colour,<br/>flashes on events"]
  end
  subgraph P2["Pan P2 (Raspberry Pi)"]
    I2["same sensors"] --> C2["pan.py"] --> O2["PiTFT"]
  end
  B(("MQTT broker<br/>farlab.infosci.cornell.edu"))
  C1 -- "mode / card / gesture / button" --> B
  C2 -- "mode / card / gesture / button" --> B
  B -- "feedback" --> C1
  B -- "feedback" --> C2
  B <--> S["Laptop: server.py<br/>the only referee<br/>orders, cooking, stacks, score"]
  S -- "Socket.IO" --> W["Big screen (browser)<br/>customers, counter, timer"]
```

| | Where | What |
|---|---|---|
| **Input** | each pan | IMU at 100 Hz, colour/proximity at ~33 Hz, two buttons |
| **Computation** | each pan | raw motion → `flip` / `toss` / `chop`; colour → `bun` / `cheese` / `lettuce` / `meat`; buttons → mode |
| | laptop | the whole game: customers, cooking timers, what is in each tray and on each plate, serving, score |
| **Output** | laptop | the big screen and its sounds |
| | each pan | the PiTFT: full screen in the mode colour, flashes white / yellow / red on events from the server |

---

## 3. Build documentation

The pan is a piece of cardboard held like a paddle. The two sensors are taped to the front,
where the cards are held; the Pi and its screen are taped to the back, facing the player's hand.

<img src="imgs/pan_9910.jpg" alt="Front of the pan: a cardboard board held in one hand, with the APDS-9960 (left) and the LSM6DS3 board (right) taped to it, joined by a Qwiic cable; both boards' green power LEDs are on" width="340" />
<img src="imgs/pan_9911.jpg" alt="Back of the pan: a Raspberry Pi taped to the cardboard with a USB-C power cable, its Mini PiTFT showing a red screen with P1 and PAN (grill mode); on the table behind it, the ingredient cards: orange, pink, yellow and blue sticky notes" width="340" />

### Hardware (each pan)

* Raspberry Pi 5 with the Mini PiTFT (the screen and its two buttons), powered over USB-C
* APDS-9960 colour / proximity sensor, I²C address `0x39`
* LSM6DS3TR-C 6-DoF accelerometer + gyroscope, I²C address `0x6a` (identified from its
  `WHO_AM_I` register, `0x6A`)
* both on the same Qwiic chain; a white light pointed at the cards (see 5. Reflection)
* four sticky notes as ingredient cards

### MQTT topics

Everything lives under `IDD/panburger/burger/`. The pans only report what happened; the laptop
decides what it means.

| Topic | From → to | Payload | Meaning |
|---|---|---|---|
| `p1/mode`, `p2/mode` | pan → laptop | `{"mode": "grill" \| "board" \| "assembly"}` | sent on every switch, and again every 5 s |
| `p1/card` | pan → laptop | `{"card": "meat"}` | a card was recognised |
| `p1/gesture` | pan → laptop | `{"type": "flip" \| "toss" \| "chop"}` | a motion was recognised |
| `p1/button` | pan → laptop | `B` | long press on B: throw away what is on the current station |
| `p1/feedback` | laptop → pan | `{"sound": "ding", "msg": "Patty done!", "mode": "grill"}` | the pan flashes its screen |
| `game` (retained) | laptop → all | phase, level, score, time left | |

The server also accepts a plain word (`mosquitto_pub ... -t IDD/panburger/burger/p1/card -m meat`),
which made it easy to test without the pans, and the big screen has a keyboard simulator for both
players.

### Recognising motion from real data

We first recorded every motion with `burger/pi/record_motion.py` (100 Hz, ten labelled steps such
as "flip 5 times", "hold it like a pan and wander around without flipping") into
[`burger/pi/recordings/motion_20261103_193039.csv`](burger/pi/recordings/motion_20261103_193039.csv),
and picked the thresholds from the peaks of each motion:

| Motion | What gives it away | Measured | Doing nothing / wandering |
|---|---|---|---|
| **flip** | a jolt up and a fast rotation about Y | \|a\| 26–30 m/s², \|gy\| 6.7–10.1 rad/s, forward ≤ 7.4 | \|gy\| ≤ 2.1 |
| **toss** to partner | a jolt up **and** a big forward acceleration | forward \|ax\| 11.7–18.2 | forward ≤ 5 |
| **chop** | a sharp hit | \|a\| 17–70 | ≤ 16.4 (one 19.7 bump) |

The chops were recorded with the pan held like a knife; now that the pan stays flat, the chop
threshold still needs a new recording. Flip and toss both jolt the pan upward; the forward axis separates them (flips ≤ 7.4, tosses ≥
11.7, so the line is at 9.5). The classifier only runs in the matching mode, so a chop can never
be read as a flip:

```python
elif s['a'] > TRIGGER_A and t >= self.lock_until and self.mode in ('grill', 'board'):
    self.capture = list(self.recent)          # 0.1 s before the jolt ...
    self.capture_until = t + WINDOW_AFTER     # ... and 0.35 s after it

def classify(self, w):
    peak = lambda k: max(abs(x[k]) for x in w)
    if self.mode == 'grill':
        if peak('ax') > TOSS_MIN_FORWARD:                              # 9.5
            return 'toss'
        if peak('a') > FLIP_MIN_A and peak('gy') > FLIP_MIN_ROT:       # 20, 5
            return 'flip'
    elif self.mode == 'board' and peak('a') > CHOP_MIN_A:              # 16
        return 'chop'
```

`burger/pi/replay.py` feeds a recording through the same detector on the laptop. On our
recording it finds 5 of 5 flips and 5 of 5 tosses, and nothing at all while the pan is carried
around without flipping.

### Reading the cards

The colour reading is turned into proportions of red, green and blue (so it does not depend on
brightness) plus the log of brightness, and matched to the nearest calibrated card. A card counts
when the proximity rises above a threshold; the reader then waits 0.3 s for a fresh colour
reading, and the next card only counts after the proximity has dropped again, so a card held
still is read once. `pan.py --calibrate` measures "no card" and each card, refuses a card that the
sensor clearly did not see, and prints how far apart the cards are.

### The referee

`server.py` is the only place where the game state lives. A pan saying `card: meat` in assembly
mode is only accepted if that player has a cooked patty in their tray **and** some waiting
customer's order starts with the current stack plus a patty; otherwise the layer is refused and
nothing is used up:

```python
candidate = p['stack'] + [card]
wanted = [c for c in self.customers if c['order'][:len(candidate)] == candidate]
if not wanted:
    return self.event(pid, 'error', 'No customer wants it stacked like that')
if card in ('meat', 'lettuce'):
    if card not in p['tray']:
        return self.event(pid, 'error',
                          'No cooked patty yet!' if card == 'meat' else 'No chopped lettuce yet!')
    p['tray'].remove(card)
```

### Files

| File | Runs on | What |
|---|---|---|
| [`burger/server.py`](burger/server.py) | laptop | game server, MQTT bridge, Socket.IO |
| [`burger/templates/index.html`](burger/templates/index.html) | browser | the big screen and the keyboard simulator |
| [`burger/pi/pan.py`](burger/pi/pan.py) | each Pi | the pan |
| [`burger/pi/record_motion.py`](burger/pi/record_motion.py) | Pi | records labelled motion data |
| [`burger/pi/replay.py`](burger/pi/replay.py) | laptop | replays a recording through the motion detector |
| [`burger/README.md`](burger/README.md) | | how to run everything |

---

## How the design changed

* **Three stations on one device.** We first wanted three Pis (grill, board, assembly). When two
  Pis became enough, we made both pans identical and let each player change station instead.
* **How to change station, three tries.**
  1. *By how the pan is held*: flat = grill, turned 90° like a knife = board, resting on the
     table = assembly. The IMU could tell all three apart (a pan held still in the hand still
     trembles: the standard deviation of |a| was 0.087–0.238, on the table 0.011–0.015), but
     waiting for a pose to be stable made it feel slow.
  2. *Tilt left / right* to step through the modes. Every tilt counted twice: swinging back past
     flat overshot to the other side, so the pan kept jumping between grill and assembly and
     could never reach the board. A 0.8 s pause after each switch fixed the double count, but
     a switch still took a deliberate tilt and a pause.
  3. *The PiTFT buttons* (A = previous, B = next, hold B = throw away). Not as physical, but
     instant and never wrong. Tilt switching is still in the code (`pan.py --tilt`).
* **No plate card.** The white plate card and the red meat card read almost the same (distance
  0.25), so we dropped the plate card: switching to assembly sets out a plate by itself.
* **Restart.** The big screen got a restart and a back-to-lobby button during a round.

---

## 4. User testing

**TODO (Wednesday): test with 2+ people not on our team.**

* Photos / video of use
* What did they think before trying?
* What surprised them?
* What would they change?

---

## 5. Reflection

**What worked well.** Recording the motions first and picking thresholds from the numbers.
Flip, toss and chop are distinct enough that a few rules recognise them, and replaying the
recording on the laptop let us test every change without the hardware. Keeping all the game state
on the laptop also kept the pans simple: they never need to know what the other pan is doing.

**Challenges with distributed interaction.**

* *One referee.* Two pans can act at the same moment (both throw, both serve). If each pan kept
  its own copy of the game they could disagree; with the laptop as the only referee, whatever it
  receives first wins and both screens show the same thing.
* *Who is in charge of the mode.* The pan decides its own mode, but the server resets everyone
  to grill when a round starts. A pan that is in assembly mode then disagrees with the screen.
  The pans now re-send their mode when a round starts and every 5 seconds, which also tells the
  big screen whether a pan is connected (🟢 / ⚪).
* *Debugging over a network.* When the screen "didn't move", the cause was not the network but
  the round having ended, so the server ignored every input. Printing every input on the server
  with "(ignored: game is over)" made that visible.

**How the sensor events worked.** The IMU was the easy part. The **colour sensor was the hard
part**. The APDS-9960 has no light of its own and reads whatever light the card reflects:

* The first calibration read every card as mostly green, even the warm-coloured ones. Holding a
  card close blocks the room light, and whatever light is left is not the light the card was meant
  to be seen in. (We first blamed the PiTFT's light and made the screen flash white while reading a
  card, but the screen is on the back of the pan, so it cannot light the cards.)
* The default colour integration time is 0.7 s per reading, so a card held up briefly was read
  with the colour from *before* it arrived. We changed it to 0.1 s and wait for a fresh reading.
* Re-measuring one card once recorded the empty air ("meat" = the room light), after which
  everything was read as meat. Calibration now measures "no card" first and refuses a card that
  reads like it.
* With our own white light, the cards separated well (all pairs ≥ 0.52), but the same card read
  differently from one calibration to the next (meat red share 0.55, then 0.43). The reading
  depends on distance and angle more than on the card.

**What we would improve.**

* A **card slot**: a short black tube around the colour sensor with a white LED inside, closed
  by the card. Fixed distance, fixed light, no room light, so the reading would be the same every
  time. (Or a TCS34725, a colour sensor with its own LED.)
* **TODO after Wednesday's feedback.**

**Where did computation happen, and why there?** Motion recognition runs **on each pan**, at
100 Hz: 100 samples a second of six numbers are too many to send over a shared broker, and the
latency would make flips feel late. Only the result (`flip`) is sent. The **game runs on the
laptop**, because there has to be exactly one place that decides what happened when both players
act. We did not use a language model: every decision here has to be fast and the same every time.

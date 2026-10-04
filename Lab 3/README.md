# Chatterboxes

**Tzuyi (Monica) Wei (tw628)**

# Part 1

## A. Text to Speech

\*\***Write your own shell file to use your favorite of these TTS engines to have your Pi greet you by name.**\*\*

[`greet.sh`](greet.sh). It says one line, "Good evening, Monica. How was your
day?", and takes the engine as an argument:

```bash
./greet.sh          # Piper, the one I chose
./greet.sh all      # the same line in every engine, back to back
./greet.sh espeak   # or festival, flite, piper
```

I wrote it this way because the demo scripts each say a different sentence, so
you cannot actually compare them. One sentence in four voices is comparable.

\*\***Then answer: Is the same greeting, in these different voices, the same greeting? Describe one concrete way the voice changed what the utterance seemed to mean or who seemed to be speaking.**\*\*

Only Piper sounded natural. espeak-ng, festival and flite were all choppy and
hard to make out, and all three sounded like a machine.

**Is it the same greeting?** Not for this device. "How was your day?" is asking
you to tell it something. When the words come out choppy you spend the whole
sentence working out what was said, and by the end nothing has been asked of
you, you have just been decoding. With Piper you hear the question the first
time.

A journal only works if the person answers it honestly, and that is hard to do
with a voice you have to decode first. So I use Piper, even though it is the
slowest of the four and waits a moment before it starts speaking.

## B. Speech to Text

\*\***Record a few seconds of your own speech (`arecord -d 5 -f cd -c 1 -r 16000 test.wav`) and transcribe it with at least two model sizes. Report the real-time factor for each. At what point does the accuracy improvement stop being worth the delay, for a system that has to answer you?**\*\*

I ran the lab's file through three model sizes, then did the same with a
30 second recording of my own.

`lookdave.wav`, 3.72 seconds of clean studio speech:

| model | transcription | real-time factor |
|---|---|---|
| tiny.en | 1.04s | 0.28x |
| base.en | 2.19s | 0.59x |
| small.en | 5.83s | 1.56x |

All three returned exactly the same words. On this file the bigger models cost
5.6 times more and gave nothing back.

My own recording is a different story. It is 30 seconds of one person talking
quietly in a room with real pauses, which is what my device will actually hear.
The phrase to watch is "record a quick check-in before heading to bed".

| model | transcription | RTF | what it heard |
|---|---|---|---|
| tiny.en | 3.22s | 0.11x | "create a quick check in" |
| base.en | 6.01s | 0.20x | "cook or cook chicken" |
| small.en | 275.80s | 9.19x | correct, every word |

Only `small.en` got it right. On easy audio the model size bought me nothing. On
my own audio it was the only thing that worked.

Then look at the time. 275 seconds to transcribe 30 seconds of speech. Part of
that is the model and part of it is heat. Afterwards `vcgencmd get_throttled`
returned `0xe0000` and the Pi was at 74C, so it had already started slowing
itself down. I have no active cooler fitted. That number is not a clean
measurement of `small.en`, it is a measurement of `small.en` on a Pi that is
throttling. The honest reading is that the cost of a big model is not fixed. It
grows at exactly the moment you are asking the most of the machine.

Real-time factor is not a property of the model either. Every model looks faster
on my recording than on `lookdave.wav` because half of mine is silence and
silence is cheap.

**My answer:** for a device that has to answer you this is not a close call.
`small.en` is accurate and unusable. `tiny.en` answers in 3 seconds and gets
words wrong. I take `tiny.en` and design around the errors instead of paying for
them, which for a journal means putting the transcript on screen so the person
can see what it heard.

\*\***Write your own script that verbally asks for a numerical input (a phone number, zipcode, number of pets) and records the answer the respondent provides.**\*\*

[`ask_number.py`](ask_number.py). It asks the question through Piper, waits for
the answer using the same VAD as `listen.py`, transcribes it, and then says the
number back. Every answer is kept in `answers/` as a wav and a text file, so a
mistake can be looked at again instead of being remembered wrongly.

```bash
python ask_number.py
python ask_number.py --question "What is your phone number?"
```

It prints two things, what it heard and what it made of that. Two answers I
recorded:

```
question: How many pets do you have?
heard:    I have one.
digits:   1

question: What is your zip code?
heard:    1, 0, 0, 4, 4.
digits:   10044
```

Both were heard correctly. The zip code was spoken as five separate digits and
came back as five separate digits, so nothing was misheard. What did need
handling was the shape of it: Whisper wrote "1, 0, 0, 4, 4." with commas and a
full stop, which is not a zip code until the punctuation is taken out.

That is why the two columns are separate. Whisper is not consistent about how it
writes a number down, sometimes words and sometimes digits and sometimes a list,
and all of those have to end up as the same answer. Keeping the raw transcript
beside the parsed number tells you which kind of problem you have. Formatting is
fixable in code, which is all either of my answers needed. A genuinely misheard
digit is not, and has to be handled in the conversation instead, which is why the
script reads the number back before it stops.

I did not manage to make it mishear a digit in these two tries.

## C. Turn-taking: knowing when someone has stopped talking

\*\***Try both extremes, and something in between. Describe what each one feels like to talk to. Note specifically: at 0.2s, what kinds of normal speech get cut off? At 1.5s, what does the delay make the system seem like?**\*\*

Before describing how it feels I measured my own pauses. I recorded 30
seconds of reflective speech and ran it through the same Silero VAD that
`listen.py` uses. Half of the recording turned out to be silence.

Every pause in it, in seconds:

```
0.07  0.23  0.36  0.39  0.49  0.49  0.75  1.00  2.51  5.19
```

Median 0.49. Longest 5.19.

| `--min-silence` | pauses it reads as "you are done" | my 30 seconds becomes |
|---|---|---|
| 0.2s | 9 of 10 | 10 turns |
| 0.4s (default) | 6 of 10 | 7 turns |
| 0.8s | 3 of 10 | 4 turns |
| 1.5s | 2 of 10 | 3 turns |
| 3.0s | 1 of 10 | 2 turns |

There is a 5.19 second pause in there. It is the one where I stopped to think
about what the best part of the day had been. Nobody would ship a device that
waits 5 seconds before answering, so a device like this will always cut in on
that kind of pause.

Cutting costs accuracy as well. The same recording given to `tiny.en` three ways:

| | what came back |
|---|---|
| whole file | "taking a walk outside and you have to turn in" |
| one utterance at a time, the way `listen.py` does it | "The best part of my day was just..." / "taking a walk outside the afternoon." / "They're marrowers." |
| silence removed, kept as one stream | "taking a walk outside, near afternoon" |

The 0.7 second fragment came back as "They're marrowers", which is not anything.
A sentence split across two turns loses the words at the seam. Whisper works from
context and a fragment has none.

Removing the silence did not make it faster here, 3.22s for the whole 30 seconds
against 3.51s for the 16.9 seconds of speech. Whisper pads everything out to 30
second windows, so dropping 13 seconds of silence stayed inside the same single
window and bought nothing. It only pays when it takes you down a whole window.

So ending a turn too early does two kinds of damage at once. It interrupts the
person, and it makes the transcript worse.

**What gets cut off at 0.2s.** I put the recording back through the same VAD at
each setting and transcribed every turn it produced. At 0.2s one sentence, "I
felt a little busy but it's still such a wonderful day", came back as four
separate turns:

```
turn 4 [0.9s]  I felt
turn 5 [1.0s]  a little busy.
turn 6 [0.6s]  but...
turn 7 [2.0s]  do it such a wonderful day.
```

"but" is a turn on its own. So what gets cut is not the end of a sentence. It is
the small pause you make while you are picking the next word. At 0.4s it is the
same sentence and almost the same four pieces, and "a little busy" also comes
back as "a little bit".

At 1.5s the first 13.2 seconds hold together and read as one thought. That is
much better. But my two long pauses, 2.51s and 5.19s, are still longer than the
threshold, so the same reflection still arrives in three pieces.

**What 1.5s feels like to talk to.** Less slow than I expected. Waiting 1.5
seconds after you stop speaking is not the part you notice.

What you notice is what comes after it. One of my turns was 4.9 seconds of
speech and took 5.79 seconds to transcribe, so the real wait was over 7 seconds
and only 1.5 of those came from the threshold. The endpointing value is the
parameter the lab hands you, but it is not the whole delay, and on a Pi that is
already warm it is not even the larger half.

## D. Storyboard

\*\***Post your storyboard and diagram here.**\*\*

A voice journal. It asks how your day was, and then it stays out of the way
while you answer.

<img src="Lab3-1.jpg" alt="Six panel storyboard: end of the day, too tired to write, the device asks first, it listens without interrupting, the user ends their own turn, the entry is saved" width="760" />

The two screen states in panels 4 and 5 are the design. `listening...` means the
turn is still yours no matter how long you stop for. `finished` means the turn
has passed to the device. Nothing about the sound tells you which state you are
in, so the screen has to.

\*\***Please describe and document your process.**\*\*

I measured first and designed afterwards, which turned out to be the right way
round.

The original plan was an ordinary voice assistant for journalling: it asks, you
answer, it endpoints, it replies. Then Part C gave me the pause data from my own
speech and that plan stopped making sense. The median pause is 0.49s but the
longest is 5.19s, and the long one was not the end of anything. It was the pause
where I was working out what the best part of the day had been, which is
exactly the sentence a journal exists to collect. Any threshold short enough to
feel responsive cuts that sentence in half.

So the device does not decide when your turn ends. You do. That is the one real
decision in the design and everything else follows from it:

- If the person ends the turn, the device needs to show that it is still
  listening during a long silence, or the silence just looks like it crashed.
  Hence `listening...` in panel 4.
- If the device is not endpointing, it needs some other way to start. Panel 3 is
  a proximity sensor: it notices someone sitting down and asks first, so the
  person never has to find a button to begin.
- The voice had to be Piper. From Part A, the other three engines make you decode
  the sentence before you can answer it, and a journal only gets honest answers.

The script, with the pauses written in, because they are choices and not
accidents:

| | who | what | pause after |
|---|---|---|---|
| 1 | device | "How was your day?" | 2.0s before it starts recording, so the question is not still hanging in the air while it listens |
| 2 | person | talks, stops, talks again | as long as they want, 5.19s was normal for me |
| 3 | person | "that's it" | - |
| 4 | device | shows the transcript | 1.5s, which is what transcription actually costs |
| 5 | device | "Saved. Same time tomorrow?" | ends |

The 1.5s in row 4 is measured, not guessed. In Part C one of my turns was 4.9
seconds of speech and took 5.79 seconds to transcribe, and a short sentence takes
closer to one or two. That wait has to be shown as thinking, or it reads as the
device having stopped.

One thing I cut. I wanted the device to say something about what you told it.
It says "Saved. Same time tomorrow?" instead. A journal is for putting something
down, not for being answered, and every reply I drafted sounded like it was
grading me.

## E. Acting out the dialogue

\*\***Describe if the dialogue seemed different than what you imagined when it was acted out, and how.**\*\*

[**acting_out.mov**](acting_out.mov)

It went the way I imagined it. The part I was least sure about, the person
having to end their own turn, did not need explaining. They finished what they
were saying, the turn ended, and neither of us had to do anything to make that
happen.

The limit of the test is that a person was playing the device. Ending a turn in
front of someone who is visibly waiting for you is easy. Whether it stays that
easy when the thing across from you is a screen is the part this does not tell
me.

---

# Lab 3 Part 2

## Prep for Part 2

**What needed improving.** Three things came out of Part 1.

There was only one way to end a turn. In Part 1 the person said "that's it" to a
human, who understood it without being told to. A device needs more than one way
in, so a turn now ends three ways: saying so, pressing button B, or going quiet
for eight seconds. Eight is not a guess. The longest thinking pause I measured in
Part C was 5.19s, so it leaves nearly three seconds of room.

The opening came too fast. The camera triggered after a second and a half of
movement, which arrives before someone has finished sitting down. Three seconds
lets them settle before they are spoken to.

The device never showed what it had heard. `tiny.en` turned "record a quick
check-in" into "create a quick check in" in Part 1, and nothing on screen would
have let anyone catch it. Now the transcript appears with "Saved", so the person
can read back what was written down.

**Beyond speech.** The screen carries the states, because the sound cannot. A
yellow dot breathing slowly means listening, and it keeps breathing through a
five second silence so the pause does not read as a crash. A still red dot means
the turn has passed to the device. Then the transcript, which is the fix for the
third problem above.

## Prototype your system

[`journal.py`](journal.py) is the system, and it runs without a wizard.

That is a decision rather than something I skipped. Wizard of Oz is for testing
an interaction before you can build the hard part of it, and this design has two
hard parts a person would normally have to stand in for. Knowing when someone has
finished talking is one, and Part C showed that no threshold does it. Saying
something meaningful back about what they told you is the other.

Neither one is faked here. The first is handed to the person, who presses a
button when they are done. The second I cut in Part 1, because every reply I
drafted sounded like it was grading them. So there is nothing left for a wizard
to pretend to be, and the sessions run with nobody operating anything.

[`wizard.py`](wizard.py) exists anyway and can drive the same states from a
second terminal. It is there in case a button fails in the middle of a session,
not as part of the design.

It uses two sensors and needs nobody operating it. The webcam notices someone
sitting down, and the buttons on the screen let that person act.

| state | what starts it | what the person sees |
|---|---|---|
| idle | nothing | a dim dot |
| asking | the webcam sees movement for 3s | "How was your day?", spoken by Piper |
| listening | 2 seconds after the question | a yellow dot breathing, and a counter |
| thinking | the person says "that's it", or goes quiet for 8s | a still red dot, "finished" |
| saved | the transcript comes back | the text, then "Saved. Same time tomorrow?" |

The camera is frame differencing rather than face detection. It pulls 160x120
grayscale frames from ffmpeg at 4fps and compares each one to the last. With
nobody in front of it the difference sits at 1.3, somebody sitting still reads 4
to 5, and somebody moving normally reads 13 to 38, so the trigger is at 6.

The device never endpoints on a short pause. It sits in `listening` for as long
as the person wants, which is the whole point of Part 1, and the turn ends when
they say it has: "that's it", "that's all", "I'm done". Going quiet for eight
seconds ends it too. Eight is not a guess. The longest thinking pause measured in
Part C was 5.19s, so this leaves nearly three seconds of room before a pause is
mistaken for an ending. Button B does the same thing, kept for when neither of
the other two works.

Every entry is saved to `entries/` as a wav and a transcript.

## Test the system

### What worked well about the system and what didn't?

Most of it ran without anyone having to think about it. Someone sits down, the
device notices them and asks how their day was, they talk, and the turn ends
either on eight seconds of quiet or because they said it was over.

The part people liked was that it does not cut in. That was the whole point of
the design, and it is also what makes it feel unlike the voice assistants they
are used to.

Two things came back as missing. There is no way to redo an entry. One person
wanted to be able to say something like "I want to record that again, it did not
come out right", and nothing in the system allows for it. The other is that
nothing can be read back. A journal you cannot reopen is only half a journal, so
the obvious next piece is somewhere to see what you said last week, or on this
day a year ago.

### What worked well about the controller and what didn't?

There is nothing to learn. Walking up to it starts it, and the turn ends three
ways: say so, press the button, or stop talking for eight seconds. Nobody had to
be told what the input was or what the output would be.

What is missing is any sign that those options exist. The screen only says
`listening...`. Putting something like "say that's it when you are finished" on
it would stop people guessing, and they would be more comfortable using it.

### What lessons can you take away from the WoZ interactions for designing a more autonomous version of the system?

In the Part 1 session the person knew they were talking to me. That changes how a
turn ends. They could see me, so finishing was carried by a look or a change in
expression, and neither of us had to do anything deliberate about it. It happened
on its own.

An automated system has none of that. It cannot read a face, and the person has
no face to read back. So the ending has to be made explicit, and it has to be
obvious enough that nobody spends the first minute of the conversation working
out how to stop.

That is the part wizarding hides. A person in the loop absorbs the hardest bit of
the interaction for free, using social cues the device will never have, and you
come away thinking that bit did not need designing.

### How could you use your system to create a dataset of interaction? What other sensing modalities would make sense to capture?

It already makes one. Every session writes a wav and a transcript to `entries/`,
so what accumulates is paired audio and text of people talking about their day in
a room, with the pauses left in. Pauses are the thing most speech datasets throw
away, and they are exactly what I needed in Part C.

What is missing is the timing around the speech. The useful thing to log next is
the moment the turn ended relative to the last word, because that is a direct
measurement of the gap an automatic system would have to guess: how long after
someone stops talking do they consider themselves finished. A few dozen of those
would say more than any threshold I could pick by hand.

Which of the three endings people reach for is worth recording too. There are
three ways to finish a turn here, saying so, going quiet, and the button, and
nobody is told about any of them. Counting which one each person finds first
would say whether the design needs to explain itself.

The camera is already running and only its frame difference is used. Keeping a
low rate record of that would say whether people look at the screen while they
talk, which would tell me whether the breathing dot is doing anything at all.

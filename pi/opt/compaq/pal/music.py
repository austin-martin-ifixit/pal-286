"""PAL's music: 1980s chiptunes made on the spot (pulse waves, a triangle
bass and noise drums, like a NES or a Commodore 64), and singing in the
manner of the IBM 7094 that sang "Daisy Bell" at Bell Labs in 1961.

Tunes are written in a small text notation (COMPOSE_GUIDE explains it), so
Claude can compose new ones as well as play the library in TUNES:

    wav, timeline = render(parse(TUNES["fur-elise"]["score"]))
    wav, timeline = render(TUNES[find("play fur elise")]["score"])
    wav, timeline = sing("birthday", name="Joe")

Sound comes out as WAV bytes (mono, 16-bit, 22050 Hz) for aplay. The
timeline lists every note as (start seconds, length seconds, MIDI note,
voice name), sorted by start, for drawing them on screen as they play.
Drum hits use General MIDI drum numbers (36 kick, 38 snare, 42 hi-hat,
46 open hat, 49 crash); sung notes are in the voice "voice".
"""

import bisect
import concurrent.futures
import difflib
import io
import re
import subprocess
import unicodedata
import wave
from fractions import Fraction

import numpy as np

RATE = 22050
MAX_SECONDS = 60          # longer tunes are cut off (and faded) here
MAX_TEXT = 20000          # characters of notation
MAX_NOTES = 4000          # per voice, after repeats are written out

COMPOSE_GUIDE = """\
PAL plays tunes written in this notation, one item per line:

tempo 132
time 4/4
lead pulse25: E5/8 D#5/8 E5/8 B4/8 D5/8 C5/8 A4/4 | C4/8 E4/8 A4/8 B4/4. r/4 |
harmony pulse12: A3+C4+E4/2 E3+G#3+B3/2 | A3+C4+E4/2 E3+G#3+B3/2 |
bass triangle: A2/4 E3/4 A2/4 E3/4 | A2/4 E3/4 E2/2 |
drums: k/8 h/8 s/8 h/8 k/8 h/8 s/8 h/8 | k/8 h/8 s/8 h/8 k/4 c/4 |

- tempo: quarter notes per minute. time: the time signature.
- Voices: lead, harmony, bass, drums; use 1 to 4. Repeat a voice's line to continue it.
- Sounds: pulse12 (thin), pulse25 (bright), pulse50 (hollow), triangle (soft: bass or \
flute), optionally followed by staccato, legato or echo.
- Notes: letter, # or b, octave (C4 is middle C), then /length: /1 /2 /4 /8 /16 /32. \
Add . to dot it (/4.), t for a triplet (/8t). No key signatures: write every sharp and flat.
- r/4 is a rest. ~ after a note ties it to the next (same pitch). Join notes with + \
for a chord (played as a fast arpeggio).
- Drums: k kick, s snare, h hi-hat, o open hat, c crash; combine like k+h/8.
- | marks a bar. Every bar must add up to the time signature (the first may be a \
short pickup); keep the voices in step.
- ( ... )x2 repeats. @150 changes the tempo from there on.
- Keep it 15 to 30 seconds. Lead around C4-C6, bass C2-C3.
"""

VOICES = ("lead", "harmony", "bass", "drums")
VOICE_NAMES = {"lead": "lead", "melody": "lead", "harmony": "harmony", "harmonies": "harmony",
               "arp": "harmony", "arpeggio": "harmony", "chords": "harmony", "bass": "bass",
               "drums": "drums", "drum": "drums", "percussion": "drums"}
WAVES = ("pulse12", "pulse25", "pulse50", "triangle", "noise")
STYLES = ("staccato", "legato", "echo")
DEFAULT_WAVE = {"lead": "pulse25", "harmony": "pulse12", "bass": "triangle", "drums": "noise"}
DRUMS = {"k": 36, "s": 38, "h": 42, "o": 46, "c": 49}    # General MIDI drum numbers
LETTERS = {"c": 0, "d": 2, "e": 4, "f": 5, "g": 7, "a": 9, "b": 11}


# ------------------------------------------------------------------ notation

class Part:
    """One voice of a tune: its sound, and its notes as [start, length,
    MIDI notes, slurred] with times in beats (quarter notes)."""

    def __init__(self, name):
        self.name = name
        self.wave = DEFAULT_WAVE[name]
        self.styles = set()
        self.notes = []
        self.beats = Fraction(0)  # its length, rests included


class Tune:
    """A tune read from the notation: tempo, time signature, up to four parts."""

    def __init__(self):
        self.title = ""
        self.tempo = 120
        self.time = (4, 4)
        self.parts = {}
        self.tempos = {}          # beat -> tempo, for changes part-way through
        self.truncated = False    # cut off at MAX_SECONDS
        self._map = [(Fraction(0), 120, 0.0)]

    def _build_map(self):
        changes = sorted({Fraction(0): self.tempo, **self.tempos}.items())
        self._map, seconds, last = [], 0.0, None
        for beat, tempo in changes:
            if last:
                seconds += float(beat - last[0]) * 60 / last[1]
            self._map.append((beat, tempo, seconds))
            last = (beat, tempo)

    def seconds(self, beat):
        """When a beat comes, in seconds from the start."""
        if len(self._map) == 1:
            return float(beat) * 60 / self._map[0][1]
        for start, tempo, at in reversed(self._map):
            if beat >= start:
                return at + float(beat - start) * 60 / tempo
        return 0.0

    @property
    def beats(self):
        return max((n[0] + n[1] for p in self.parts.values() for n in p.notes), default=Fraction(0))

    @property
    def length(self):
        """How long the tune lasts, in seconds."""
        return self.seconds(self.beats)


TOKEN = re.compile(r"\(|\)\s*(?:[x*]\s*\d+)?|\||[^\s()|]+", re.I)
NOTE = re.compile(r"([a-g])([#b]?)(\d)$", re.I)
DURATION = re.compile(r"([^/~]+?)(?:/(\d+)([.t]*))?(~?)$")


def parse(text, strict=True):
    """Reads a tune written in PAL's notation (see COMPOSE_GUIDE) into a Tune.
    Bad input raises ValueError saying what's wrong and where, in words a
    model can act on. Tunes longer than MAX_SECONDS are cut off there.
    strict=False skips checking that every bar adds up to the time signature."""
    if not isinstance(text, str):
        raise ValueError("a tune must be text")
    if len(text) > MAX_TEXT:
        raise ValueError(f"the tune is too long to read ({len(text)} characters; at most {MAX_TEXT})")
    tune, tokens = Tune(), {}
    for number, raw in enumerate(text.splitlines(), 1):
        line = raw.strip()
        if not line or line.startswith(("#", "//", "%", "```")):
            continue
        header = re.match(r"(tempo|bpm|time|meter|title|key|composer|by|style)\b\s*[:=]?\s*(.*)$",
                          line, re.I)
        if header:
            _read_header(tune, header.group(1).lower(), header.group(2), number)
            continue
        voice = re.match(r"([a-z]+)([^:]*):(.*)$", line, re.I)
        if not voice:
            raise ValueError(f"line {number}: can't read {line[:40]!r}; expected 'tempo 120', "
                             "'time 4/4' or a voice line such as 'lead pulse25: C5/4 E5/4 G5/2 |'")
        name = VOICE_NAMES.get(voice.group(1).lower())
        if not name:
            raise ValueError(f"line {number}: {voice.group(1)!r} isn't a voice; "
                             f"use {', '.join(VOICES)}")
        part = tune.parts.setdefault(name, Part(name))
        for word in re.findall(r"[a-z0-9]+", voice.group(2).lower()):
            if word in WAVES:
                if (word == "noise") != (name == "drums"):
                    raise ValueError(f"line {number}: the {name} can't use {word} "
                                     "(noise is for drums only)")
                part.wave = word
            elif word in STYLES:
                part.styles.add(word)
            else:
                raise ValueError(f"line {number}: {word!r} isn't a sound; use one of "
                                 f"{', '.join(WAVES[:4])}, optionally with {', '.join(STYLES)}")
        tokens.setdefault(name, []).extend(TOKEN.findall(voice.group(3)))
    if not tokens:
        raise ValueError("no voices found; write lines such as 'lead pulse25: C5/4 E5/4 G5/2 |'")
    for name, items in tokens.items():
        _read_part(tune, tune.parts[name], _expand(items, name), strict)
    if not any(p.notes for p in tune.parts.values()):
        raise ValueError("the tune has no notes")
    tune._build_map()
    _cut(tune)
    return tune


def _read_header(tune, key, value, number):
    if key in ("tempo", "bpm"):
        found = re.search(r"(\d+(?:\.\d+)?)", value)
        if not found or not 40 <= float(found.group(1)) <= 300:
            raise ValueError(f"line {number}: tempo must be a number of beats a minute from 40 to 300")
        tune.tempo = float(found.group(1))
    elif key in ("time", "meter"):
        found = re.search(r"(\d+)\s*/\s*(\d+)", value)
        if not found or not 1 <= int(found.group(1)) <= 16 or int(found.group(2)) not in (1, 2, 4, 8, 16):
            raise ValueError(f"line {number}: time should look like 4/4, 3/4 or 6/8")
        tune.time = (int(found.group(1)), int(found.group(2)))
    elif key == "title":
        tune.title = value.strip()[:80]


def _expand(items, name):
    """Writes out ( ... )x3 repeats."""
    stack = [[]]
    for item in items:
        if item == "(":
            stack.append([])
        elif item.startswith(")"):
            if len(stack) == 1:
                raise ValueError(f"{name}: a ')' without its '('")
            times = int(re.sub(r"\D", "", item) or 2)
            if not 1 <= times <= 64:
                raise ValueError(f"{name}: repeat 1 to 64 times, not {times}")
            body = stack.pop()
            stack[-1].extend(body * times)
        else:
            stack[-1].append(item)
        if len(stack[-1]) > MAX_NOTES * 2:
            raise ValueError(f"{name}: too many notes (at most {MAX_NOTES} a voice)")
    if len(stack) > 1:
        raise ValueError(f"{name}: a '(' is never closed; close it with ')x2'")
    return stack[0]


def _pitch(text, name):
    """MIDI note numbers for 'C#4' or a chord 'C4+E4+G4' (drums: 'k+h')."""
    if text.lower() == "r":
        return ()
    found = []
    for item in text.split("+"):
        if name == "drums":
            if item.lower() not in DRUMS:
                raise ValueError(f"drums: {item!r} isn't a drum; use k (kick), s (snare), "
                                 "h (hi-hat), o (open hat), c (crash) or r (rest)")
            found.append(DRUMS[item.lower()])
            continue
        note = NOTE.match(item)
        if not note:
            raise ValueError(f"{name}: {item!r} isn't a note; notes look like C4, F#5 or Bb3 "
                             "(letter, optional # or b, octave)")
        letter, accidental, octave = note.groups()
        midi = 12 * (int(octave) + 1) + LETTERS[letter.lower()] + {"#": 1, "b": -1}.get(accidental, 0)
        if not 24 <= midi <= 108:
            raise ValueError(f"{name}: {item} is out of range (C1 to C8)")
        found.append(midi)
    if len(found) > 6:
        raise ValueError(f"{name}: a chord of {len(found)} notes; use at most 6")
    return tuple(found)


def _read_part(tune, part, items, strict):
    name, (top, bottom) = part.name, tune.time
    bar = Fraction(4 * top, bottom)
    position, bar_start, bar_number = Fraction(0), Fraction(0), 1
    length, tied = Fraction(1), False

    last_note = max((i for i, item in enumerate(items) if item not in ("|", "~") and
                     not item.startswith("@")), default=-1)
    checking = strict and "|" in items

    def check_bar(final=False):
        nonlocal bar_number, bar_start
        span = position - bar_start
        if span:
            short_ok = bar_number == 1 or final
            if checking and (span > bar or (span < bar and not short_ok)):
                eighths = span * bottom / 4
                said = f"{eighths.numerator}/{bottom}" if eighths.denominator == 1 else \
                    f"{float(span):.2f} beats"
                raise ValueError(f"{name}: bar {bar_number} adds up to {said}, but the time is "
                                 f"{top}/{bottom}")
            bar_number += 1
        bar_start = position

    for index, item in enumerate(items):
        if item == "|":
            check_bar(final=index > last_note)
            continue
        if item == "~":                              # a tie written apart from its note
            tied = bool(part.notes) and part.notes[-1][0] + part.notes[-1][1] == position
            continue
        if item.startswith("@"):
            if not re.fullmatch(r"@\d+(\.\d+)?", item) or not 40 <= float(item[1:]) <= 300:
                raise ValueError(f"{name}: {item!r} should be a tempo change such as @140 (40 to 300)")
            tune.tempos[position] = float(item[1:])
            if len(tune.tempos) > 64:                # (each one costs every note a look-up)
                raise ValueError(f"{name}: too many tempo changes (at most 64)")
            continue
        found = DURATION.match(item)
        if not found:
            raise ValueError(f"{name}: can't read {item!r}; notes look like E5/8, F#4/4. or r/2")
        pitches = _pitch(found.group(1), name)
        if found.group(2):
            size, marks = int(found.group(2)), found.group(3)
            if size not in (1, 2, 4, 8, 16, 32) or marks.count("t") > 1 or marks.count(".") > 2:
                raise ValueError(f"{name}: {item!r} has a length I can't read; use /1 /2 /4 /8 "
                                 "/16 /32, then . for dotted or t for a triplet")
            length = Fraction(4, size) * (2 - Fraction(1, 2 ** marks.count(".")))
            if "t" in marks:
                length *= Fraction(2, 3)
        if pitches and tied and part.notes and part.notes[-1][2] == pitches:
            part.notes[-1][1] += length              # a tie: the note just carries on
        elif pitches:
            if tied and part.notes:
                part.notes[-1][3] = True             # tied to another note: a slur
            part.notes.append([position, length, pitches, False])
            if len(part.notes) > MAX_NOTES:
                raise ValueError(f"{name}: too many notes (at most {MAX_NOTES} a voice)")
        tied = bool(found.group(4)) and bool(pitches)
        position += length
    check_bar(final=True)
    part.beats = position


def _cut(tune):
    """Stops a tune at MAX_SECONDS."""
    if tune.length <= MAX_SECONDS:
        return
    tune.truncated = True
    for part in tune.parts.values():
        kept = []
        for note in part.notes:
            if tune.seconds(note[0]) >= MAX_SECONDS - 0.05:
                break
            end = note[0] + note[1]
            if tune.seconds(end) > MAX_SECONDS:      # the note running over the end: halve in on where to cut it
                low, high = note[0], end
                for _ in range(20):
                    middle = (low + high) / 2
                    if tune.seconds(middle) > MAX_SECONDS:
                        high = middle
                    else:
                        low = middle
                end = low
            if end > note[0]:
                kept.append([note[0], end - note[0], note[2], note[3]])
        part.notes = kept


# ------------------------------------------------------------------ the synthesiser

ARP_RATE = 50             # chord notes a second, the C64's frame rate
LEVEL = {"lead": 0.30, "harmony": 0.18, "bass": 0.42, "drums": 0.28}
LOUDNESS = {"pulse12": 1.15, "pulse25": 1.0, "pulse50": 0.85, "triangle": 1.0}


def to_wav(samples, volume=0.8):
    """WAV bytes for samples, scaled so the loudest is at volume (0-1)."""
    peak = float(np.max(np.abs(samples))) if len(samples) else 0.0
    scale = 32767 * (volume / peak if peak > 0 else 1)
    pcm = np.clip(np.asarray(samples, dtype=np.float32) * np.float32(scale), -32767, 32767)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes(pcm.astype("<i2").tobytes())
    return buffer.getvalue()


def hertz(midi):
    return 440.0 * 2 ** ((np.asarray(midi, dtype=float) - 69) / 12)


# The NES triangle: 32 steps up and down, which gives it its buzz.
TRIANGLE = ((np.where(np.arange(32) < 16, np.arange(32), 31 - np.arange(32)) - 7.5) / 7.5).astype(np.float32)


def _envelope(n, gate, attack, decay, sustain, release):
    """One note's loudness, sample by sample: a quick rise, a fall to the
    sustain level, then a fade once the note is let go. Every edge is a ramp
    of a few milliseconds and every note ends silent, so nothing clicks."""
    t = np.arange(n, dtype=np.float32)
    env = np.minimum(t / np.float32(attack), np.float32(1))
    if decay:
        env = np.minimum(env, 1 - (1 - sustain) * np.clip((t - attack) / decay, 0, 1))
    return (env * np.clip(1 - (t - gate) / np.float32(release), 0, 1)).astype(np.float32)


def _blep(t, dt):
    """The correction that rounds off a jump in a waveform (PolyBLEP), so
    high notes don't fold back into harsh, out-of-tune whistles."""
    out = np.zeros_like(t)
    scalar = np.ndim(dt) == 0
    i = np.nonzero(t < dt)[0]
    x = t[i] / (dt if scalar else dt[i])
    out[i] = x + x - x * x - 1
    i = np.nonzero(t > 1 - dt)[0]
    x = (t[i] - 1) / (dt if scalar else dt[i])
    out[i] = x * x + x + x + 1
    return out


def _note(wave, hz, size, vibrato):
    """One note's raw wave (float32): a pulse or triangle at hz, or a fast
    arpeggio when hz holds several notes (a chord)."""
    t = np.arange(size, dtype=np.float32)
    if len(hz) > 1:
        steps = (np.arange(size) * ARP_RATE // RATE) % len(hz)
        step = (hz / RATE).astype(np.float32)[steps]
        phase = np.cumsum(step, dtype=np.float64)    # (added up exactly: float32 drifts flat over a long note)
    elif vibrato:
        time = t / RATE
        depth = 0.0012 * np.clip((time - 0.15) / 0.25, 0, 1)          # about 20 cents
        step = (hz[0] / RATE * (1 + depth * np.sin(2 * np.pi * 5.5 * time))).astype(np.float32)
        phase = np.cumsum(step, dtype=np.float64)
    else:
        step = np.float32(hz[0] / RATE)
        phase = t * step
    phase -= np.floor(phase)
    if wave == "triangle":
        return TRIANGLE[(phase * 32).astype(np.int32) & 31]
    duty = np.float32(0.125 if wave == "pulse12" else int(wave[5:]) / 100)
    y = (phase < duty).astype(np.float32) - duty
    y += 0.5 * _blep(phase, step)
    phase -= duty
    phase += phase < 0
    y -= 0.5 * _blep(phase, step)
    return y


def _part_samples(tune, part, out):
    """Adds one pitched voice to out: a pulse or triangle wave whose pitch
    and loudness follow its notes. Each note starts afresh (they all start
    and end silent), and a note played again is copied, not remade."""
    n = len(out)
    triangle = part.wave == "triangle"
    attack = (0.002 if triangle else 0.004) * RATE
    decay, sustain = (0, 1) if triangle else ((0.10, 0.72) if part.name == "lead" else (0.08, 0.55))
    decay *= RATE
    release_max = (0.012 if triangle else 0.03) * RATE
    level = LEVEL[part.name] * LOUDNESS[part.wave]
    if triangle and part.name != "bass":
        level *= 0.7              # a high triangle sounds louder than a low one
    echo = "echo" in part.styles
    target = np.zeros(n, dtype=np.float32) if echo else out
    made = {}
    for start, length, pitches, slurred in part.notes:
        s0, s1 = tune.seconds(start), tune.seconds(start + length)
        i0, i1 = int(round(s0 * RATE)), min(n, int(round(s1 * RATE)))
        size = i1 - i0
        if size < 16:
            continue
        duration = size / RATE
        if "legato" in part.styles or slurred:
            on = duration - 0.004
        elif "staccato" in part.styles:
            on = min(duration * 0.5, 0.12)
        else:
            on = duration - min(0.012 + 0.1 * duration, 0.06)
        gate = max(int(on * RATE), 8)
        vibrato = part.name == "lead" and len(pitches) == 1 and duration > 0.3
        key = (pitches, size, gate, vibrato)
        if key not in made:
            release = max(min(release_max, size - gate), 4)
            env = _envelope(size, min(gate, size - release), min(attack, size / 4), decay,
                            sustain, release)
            made[key] = _note(part.wave, hertz(pitches), size, vibrato) * env * np.float32(level)
        target[i0:i1] += made[key]
    if echo:
        delay = int(np.clip(0.75 * 60 / tune.tempo, 0.12, 0.35) * RATE)
        target[delay:] += np.float32(0.35) * target[:-delay]
        out += target


_DRUM_SOUNDS = {}


def _drum_sounds():
    """The five drums, made once: a falling-pitch thump, and noise bursts of
    different colours and lengths."""
    if _DRUM_SOUNDS:
        return _DRUM_SOUNDS
    rng = np.random.default_rng(1987)

    def noise(seconds, hold=1):
        values = rng.uniform(-1, 1, int(seconds * RATE) // hold + 1)
        return np.repeat(values, hold)[:int(seconds * RATE)]

    def tone(seconds, top, bottom, fall):
        t = np.arange(int(seconds * RATE)) / RATE
        phase = np.cumsum((bottom + (top - bottom) * np.exp(-t / fall)) / RATE)
        return np.sin(2 * np.pi * phase), t

    kick, t = tone(0.18, 170, 48, 0.03)
    kick = kick * np.exp(-t / 0.08) + noise(0.18) * np.exp(-t / 0.004) * 0.4
    body, t = tone(0.16, 220, 140, 0.02)
    snare = noise(0.16, 2) * np.exp(-t / 0.055) * 0.8 + body * np.exp(-t / 0.03) * 0.5
    hiss = np.diff(noise(1.0), prepend=0) * 0.5          # brighter: the high part of noise
    t = np.arange(len(hiss)) / RATE
    sounds = {36: kick, 38: snare,
              42: (hiss * np.exp(-t / 0.016))[:int(0.06 * RATE)],
              46: (hiss * np.exp(-t / 0.09))[:int(0.3 * RATE)],
              49: hiss * np.exp(-t / 0.3) * 0.7}
    for hit, sound in sounds.items():
        fade = min(len(sound), int(0.004 * RATE))
        sound[-fade:] *= np.linspace(1, 0, fade)
        sound[:12] *= np.linspace(0, 1, 12)
        _DRUM_SOUNDS[hit] = (sound * LEVEL["drums"]).astype(np.float32)
    return _DRUM_SOUNDS


def _drum_samples(tune, part, out):
    """Adds the drums to out."""
    n = len(out)
    sounds = _drum_sounds()
    for start, length, hits, _ in part.notes:
        i0 = int(round(tune.seconds(start) * RATE))
        for hit in hits:
            sound = sounds[hit][:max(0, n - i0)]
            out[i0:i0 + len(sound)] += sound


def _timeline(tune):
    lines = []
    for part in tune.parts.values():
        for start, length, pitches, _ in part.notes:
            s0 = tune.seconds(start)
            for midi in pitches:
                lines.append((round(s0, 3), round(tune.seconds(start + length) - s0, 3), midi, part.name))
    lines.sort(key=lambda line: (line[0], VOICES.index(line[3]) if line[3] in VOICES else -1))
    return lines


def _synth(tune):
    """The tune as float samples (peak about 1), and its timeline."""
    n = int((tune.length + 0.3) * RATE)
    mix = np.zeros(n, dtype=np.float32)
    for part in tune.parts.values():
        (_drum_samples if part.name == "drums" else _part_samples)(tune, part, mix)
    if tune.truncated:
        end = int(tune.length * RATE)
        fade = min(int(2 * RATE), end)               # (a cut tune can be shorter than the fade)
        if fade:
            mix[end - fade:end] *= np.linspace(1, 0, fade)
        mix[end:] = 0
    fade = int(0.01 * RATE)
    mix[-fade:] *= np.linspace(1, 0, fade)
    peak = float(np.max(np.abs(mix)))
    return (mix / peak if peak else mix), _timeline(tune)


def render(tune, volume=0.8):
    """Plays a tune (a Tune from parse(), or notation text): returns
    (WAV bytes, timeline). volume is the loudest sample, 0 to 1."""
    if isinstance(tune, str):
        tune = parse(tune)
    samples, timeline = _synth(tune)
    return to_wav(samples, volume), timeline


def seconds(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return w.getnframes() / w.getframerate()


# ------------------------------------------------------------------ singing
#
# Each syllable is spoken by espeak-ng, then re-pitched and stretched with
# PSOLA (pitch-synchronous overlap-add): the recording is cut into small
# pieces, one per vibration of the "vocal cords", and the pieces are laid
# down again at the spacing of the note wanted. That holds every note on a
# steady, exact pitch (the robotic sound of the 1961 IBM 7094) while keeping
# the vowels recognisable. Vowels are stretched to fill the note; consonants
# keep their natural speed.

SINGER = ["espeak-ng", "-v", "en-us", "-s", "140"]
FRAME, HOP = 1024, 220            # pitch analysis: 46 ms windows, 10 ms apart
UNVOICED_STEP = 110               # piece spacing in consonants (5 ms)
_SPOKEN = {}                      # (syllable, espeak pitch) -> Syllable, kept between songs


def _read_wav(data):
    """Float samples at RATE from WAV bytes. espeak-ng streams its WAV with
    a made-up length, so the data runs from its header to the end."""
    rate, start = RATE, data.find(b"data") + 8
    fmt = data.find(b"fmt ")
    if fmt >= 0:
        rate = int.from_bytes(data[fmt + 12:fmt + 16], "little")
    pcm = data[start:start + (len(data) - start) // 2 * 2]
    x = np.frombuffer(pcm, "<i2").astype(float) / 32768
    if rate != RATE and len(x):
        x = np.interp(np.arange(int(len(x) * RATE / rate)) * rate / RATE, np.arange(len(x)), x)
    return x


def _speak(text, pitch):
    out = subprocess.run([*SINGER, "-p", str(pitch), "--stdout", "--stdin"], input=text.encode(),
                         capture_output=True, check=True, timeout=30).stdout
    return _read_wav(out)


def _pitch_frames(x):
    """The pitch (Hz) of each 10 ms step of x, and whether it is voiced at
    all, by autocorrelation over 46 ms windows."""
    if len(x) < FRAME:
        x = np.pad(x, (0, FRAME - len(x)))
    frames = np.lib.stride_tricks.sliding_window_view(x, FRAME)[::HOP]
    frames = frames - frames.mean(axis=1, keepdims=True)
    window = np.hanning(FRAME)
    spectrum = np.fft.rfft(frames * window, 2 * FRAME)
    ac = np.fft.irfft(spectrum.real ** 2 + spectrum.imag ** 2)[:, :FRAME]
    own = np.fft.irfft(np.abs(np.fft.rfft(window, 2 * FRAME)) ** 2)[:FRAME]
    ac = ac / np.maximum(ac[:, :1], 1e-12) / np.maximum(own / own[0], 1e-3)
    low, high = RATE // 500, RATE // 50
    part = ac[:, low:high]
    best = part.max(axis=1)
    # The first peak nearly as high as the best one: avoids landing an octave low.
    lag = np.argmax(part >= 0.9 * best[:, None], axis=1) + low
    f0 = np.zeros(len(frames))
    for i, k in enumerate(lag):
        k += int(np.argmax(ac[i, k:k + max(2, k // 4)]))
        if 1 <= k < FRAME - 1:
            a, b, c = ac[i, k - 1], ac[i, k], ac[i, k + 1]
            shift = 0.5 * (a - c) / (a - 2 * b + c) if a - 2 * b + c else 0
            f0[i] = RATE / (k + shift)
    level = np.sqrt(np.mean(frames ** 2, axis=1))
    voiced = (best > 0.5) & (level > 0.08 * level.max()) & (f0 > 50) & (f0 < 500)
    return f0, voiced


def pitch_of(samples):
    """The main pitch of a sound, in Hz (0 if it has none): the median over
    its voiced parts."""
    f0, voiced = _pitch_frames(np.asarray(samples, dtype=float))
    return float(np.median(f0[voiced])) if voiced.any() else 0.0


class Syllable:
    """A spoken syllable, trimmed, with its pitch pulses found."""

    def __init__(self, x):
        power = np.concatenate(([0], np.cumsum(x ** 2)))
        level = np.sqrt(np.maximum(power[220:] - power[:-220], 0) / 220)      # 10 ms running level
        loud = np.nonzero(level > 0.03 * level.max())[0] if len(x) else []
        if len(loud):
            x = x[max(0, loud[0] - 110):loud[-1] + 330]
        self.x = x
        f0, voiced = _pitch_frames(x)
        centres = np.arange(len(f0)) * HOP + FRAME // 2
        everywhere = np.arange(len(x))
        self.voiced = np.interp(everywhere, centres, voiced.astype(float)) > 0.5 if voiced.any() \
            else np.zeros(len(x), bool)
        self.period = np.interp(everywhere, centres[voiced], RATE / f0[voiced]) if voiced.any() \
            else np.full(len(x), 100.0)
        self.pitch = float(np.median(f0[voiced])) if voiced.any() else 0.0
        edges = np.diff(np.concatenate(([0], self.voiced.astype(int), [0])))
        self.runs = [(a, b) for a, b in zip(np.nonzero(edges == 1)[0], np.nonzero(edges == -1)[0])
                     if b - a > 0.03 * RATE]
        self.marks = self._marks()
        self.positions = [m[0] for m in self.marks]

    def _marks(self):
        """Where each pitch pulse peaks in the voiced parts; evenly spaced
        points through the rest."""
        x, n = self.x, len(self.x)
        smooth = np.convolve(x, np.ones(5) / 5, "same")
        marks, i, last = [], 0, None
        while i < n:
            if self.voiced[i]:
                p = int(self.period[i])
                if last is not None and marks[-1][1]:
                    lo, hi = max(0, i - p // 4), min(n, i + p // 4 + 1)
                else:
                    lo, hi = i, min(n, i + p)
                j = lo + int(np.argmax(smooth[lo:hi])) if hi > lo else i
                j = max(j, (marks[-1][0] + p // 2) if marks else 0)
                marks.append((j, True, p))
                last, i = j, j + p
            else:
                marks.append((i, False, UNVOICED_STEP))
                last, i = i, i + UNVOICED_STEP
        return marks


def _knots(runs, start, end, length):
    """How time in the sung note maps onto the spoken syllable from start
    to end: the middles of the voiced stretches (vowels) take up the slack,
    consonants keep their natural speed."""
    pieces, at = [], start
    for a, b in runs:
        a, b = max(a, start), min(b, end)
        if b <= a:
            continue
        edge = min(0.03 * RATE, (b - a) / 4)
        if a + edge > at:
            pieces.append((at, a + edge, False))
        pieces.append((a + edge, b - edge, True))
        at = b - edge
    pieces.append((at, end, False))
    fixed = sum(b - a for a, b, s in pieces if not s)
    stretchy = sum(b - a for a, b, s in pieces if s)
    if stretchy > 0 and length > fixed + 0.25 * stretchy:
        scale = {False: 1.0, True: (length - fixed) / stretchy}
    else:
        scale = {False: length / max(end - start, 1), True: length / max(end - start, 1)}
    out, src, t = [0.0], [float(start)], 0.0
    for a, b, s in pieces:
        t += (b - a) * scale[s]
        out.append(t)
        src.append(float(b))
    return np.array(out), np.array(src)


def _psola(syllable, out_knots, src_knots, notes):
    """Lays the syllable's pieces down at the spacing of each note's pitch.
    notes: [(start sample, Hz)] within the sung note."""
    marks, positions = syllable.marks, syllable.positions
    length = int(out_knots[-1])
    starts = [start for start, _ in notes]
    periods = [RATE / hz for _, hz in notes]
    out, src = list(out_knots), list(src_knots)
    at, cut, halves = [], [], []
    t, knot = 0.0, 0
    while t < length:
        while knot < len(out) - 2 and t > out[knot + 1]:
            knot += 1
        span = out[knot + 1] - out[knot]
        where = src[knot] + (t - out[knot]) / span * (src[knot + 1] - src[knot]) if span > 0 \
            else src[knot]
        k = bisect.bisect_left(positions, where)
        if k == len(positions) or (k > 0 and where - positions[k - 1] < positions[k] - where):
            k -= 1
        pos, voiced, period = marks[k]
        at.append(int(t))
        cut.append(pos)
        halves.append(min(int(period), 500) if voiced else UNVOICED_STEP)
        t += periods[max(bisect.bisect_right(starts, t) - 1, 0)] if voiced else UNVOICED_STEP
    # Every piece is a Hann-windowed cut two periods wide, centred on a pulse;
    # they are all added in at once.
    big = max(halves)
    j = np.arange(-big, big)
    half = np.array(halves)[:, None]
    window = np.where(np.abs(j) < half, 0.5 + 0.5 * np.cos(np.pi * j / half), 0)
    padded = np.pad(syllable.x, big + 1)
    pieces = padded[np.array(cut)[:, None] + j + big + 1] * window
    where = np.array(at)[:, None] + j + big
    y = np.bincount(where.ravel(), pieces.ravel(), minlength=length + 2 * big + 1)
    return y[big:big + length]


def _sung(syllable, notes, length):
    """A syllable sung over one or more notes: [(seconds, Hz)], one after
    another, lasting length seconds in all."""
    n = len(syllable.x)
    total = int(length * RATE)
    starts = np.cumsum([0] + [int(s * RATE) for s, _ in notes[:-1]])
    plan = list(zip(starts, [hz for _, hz in notes]))
    runs = syllable.runs
    if len(notes) > 1 and len(runs) > 1:
        # Two syllables over two notes (e.g. a name): split the sound
        # between its first and second vowels, one part per note.
        gaps = [(runs[i][1] + runs[i + 1][0]) / 2 for i in range(len(runs) - 1)]
        cut = min(gaps, key=lambda g: abs(g / n - starts[1] / total))
        first = _knots(runs, 0, cut, starts[1])
        second = _knots(runs, cut, n, total - starts[1])
        out = np.concatenate([first[0], second[0][1:] + starts[1]])
        src = np.concatenate([first[1], second[1][1:]])
    else:
        out, src = _knots(runs, 0, n, total)
    y = _psola(syllable, out, src, plan)
    fade = min(len(y) // 4, int(0.008 * RATE))
    if fade:
        y[:fade] *= np.linspace(0, 1, fade)
        y[-fade:] *= np.linspace(1, 0, fade)
    frames = np.lib.stride_tricks.sliding_window_view(y, 441)[::220] if len(y) > 441 else y[None]
    level = np.percentile(np.sqrt(np.mean(frames ** 2, axis=1)), 95)
    return y * (0.25 / level) if level > 0 else y


def _espeak_pitch(hz):
    """espeak-ng's -p setting that speaks closest to hz, so PSOLA only
    nudges the pitch (measured: -p 0 is about 65 Hz, -p 99 about 160)."""
    return int(np.clip(round(np.log2(hz / 64.7) / 0.0131), 0, 99))


def _read_lyrics(text, name):
    """The sung line: 'word:A3/4' sings a syllable, a bare 'B2/2' carries the
    last one on to another note, 'r/4' rests. Returns [(text, [(midi,
    beats)])] with None for rests."""
    line = []
    for item in text.split():
        word, _, note = item.rpartition(":")
        pitch, size, dots = re.match(r"(\w#?b?\d?|r)/(\d+)(\.*)$", note).groups()
        beats = Fraction(4, int(size)) * (2 - Fraction(1, 2 ** len(dots)))
        midi = None if pitch == "r" else _pitch(pitch, "voice")[0]
        if word:
            line.append([word.replace("{name}", name), [(midi, beats)]])
        elif midi is None:
            line.append([None, [(None, beats)]])
        else:
            line[-1][1].append((midi, beats))
    return line


def sing(song_id, name=None, accompaniment=True, volume=0.8):
    """PAL sings: "daisy" (Daisy Bell, the first verse) or "birthday"
    (Happy Birthday, to name). Returns (WAV bytes, timeline). Without
    accompaniment it's the voice alone (for checking its pitch)."""
    key = {"daisy": "daisy", "daisy-bell": "daisy", "birthday": "birthday",
           "happy-birthday": "birthday"}.get(str(song_id).lower().strip())
    if not key:
        raise ValueError(f"no song {song_id!r}; PAL can sing {', '.join(SONGS)}")
    song = SONGS[key]
    who = " ".join(re.sub(r"[^A-Za-zÀ-ÖØ-öø-ÿ' -]", " ", name or "").split())[:30] or "friend"
    band = parse(song["accompaniment"], strict=False)
    line = _read_lyrics(song["lyrics"], who)
    # Speak every syllable first (four at a time; the Pi has four cores), at
    # an espeak pitch near the word's notes, and find their pitch pulses.
    heard = {}
    for word, notes in line:
        if word:
            heard.setdefault(word, []).append(float(hertz(notes[0][0])))
    heard = {word: _espeak_pitch(np.median(hz)) for word, hz in heard.items()}
    wanted = [(word, p) for word, p in heard.items() if (word, p) not in _SPOKEN]
    with concurrent.futures.ThreadPoolExecutor(4) as pool:
        for item, x in zip(wanted, pool.map(lambda w: _speak(*w), wanted)):
            _SPOKEN[item] = Syllable(x)
    while len(_SPOKEN) > 300:
        _SPOKEN.pop(next(iter(_SPOKEN)))
    total = max(band.length, band.seconds(sum(b for _, notes in line for _, b in notes)))
    voice = np.zeros(int((total + 0.5) * RATE))
    sung, beat, before = [], Fraction(0), 1.0
    for word, notes in line:
        span = sum(b for _, b in notes)
        if word:
            syllable = _SPOKEN[(word, heard[word])]
            start, end = band.seconds(beat), band.seconds(beat + span)
            parts, at = [], beat
            for midi, beats in notes:
                parts.append((band.seconds(at + beats) - band.seconds(at), float(hertz(midi))))
                sung.append((round(band.seconds(at), 3),
                             round(band.seconds(at + beats) - band.seconds(at), 3), midi, "voice"))
                at += beats
            # Consonants come just before the beat, so the vowel lands on it
            # (but without eating much of a short note before).
            lead_in = min(syllable.runs[0][0] / RATE if syllable.runs else 0, 0.07, before / 4)
            length = end - start - 0.02 + lead_in
            y = _sung(syllable, parts, length)
            i0 = max(0, int((start - lead_in) * RATE))
            y = y[:len(voice) - i0]
            voice[i0:i0 + len(y)] += y
        before = band.seconds(beat + span) - band.seconds(beat)
        beat += span
    timeline = sung
    if accompaniment:
        backing, played = _synth(band)
        size = min(len(backing), len(voice))
        voice[:size] += 0.32 * backing[:size]
        timeline = sorted(sung + played, key=lambda line: line[0])
    fade = int(0.01 * RATE)
    voice[-fade:] *= np.linspace(1, 0, fade)
    return to_wav(voice, volume), timeline


# ------------------------------------------------------------------ finding a tune

STOPWORDS = {"play", "the", "a", "an", "please", "pal", "can", "could", "would", "will", "you",
             "me", "us", "some", "song", "tune", "music", "by", "for", "to", "of", "in", "on",
             "that", "this", "one", "i", "want", "hear", "let", "lets", "s", "how", "about",
             "give", "do", "know", "sing", "and", "piece", "again", "now", "hey", "okay", "ok"}
GENERIC = {"march", "waltz", "rag", "dance", "overture", "theme", "suite", "symphony", "little"}


def _words(text):
    text = unicodedata.normalize("NFKD", str(text)).encode("ascii", "ignore").decode().lower()
    text = re.sub(r"\bcan\W*can\b", "cancan", re.sub(r"[^a-z0-9]+", " ", text))
    return [w for w in text.split() if w not in STOPWORDS]


def find(request):
    """The id of the tune in TUNES that a spoken request most likely means
    ("play fur elise", "the entertainer", "mountain king"), or None."""
    asked = _words(request)
    if not asked:
        return None
    best, best_score = None, 0.0
    for tune_id, tune in TUNES.items():
        for alias in [tune["title"], tune_id.replace("-", " "), *tune.get("aliases", ())]:
            words = _words(alias)
            if not words:
                continue
            weight = {w: 0.4 if w in GENERIC else 1.0 for w in words}
            got = sum(weight[w] for w in words if any(
                q == w or (len(w) > 3 and difflib.SequenceMatcher(None, q, w).ratio() >= 0.85)
                for q in asked))
            score = got / sum(weight.values()) + 0.01 * len(words)
            if got >= 1 and score > best_score:
                best, best_score = tune_id, score
    return best if best_score >= 0.6 else None


# ------------------------------------------------------------------ the library
#
# Public-domain music only (composers long gone, published before 1929),
# arranged here as chiptunes. Melodies were checked note by note against
# public-domain editions (Mutopia, Wikipedia's scores and folk-tune
# collections). "fact" is something PAL can say before playing.

TUNES = {
    "daisy-bell": {
        "title": "Daisy Bell", "composer": "Harry Dacre", "year": 1892,
        "fact": "In 1961 an IBM 7094 at Bell Labs sang this song, one of the first songs ever "
                "sung by a computer.",
        "aliases": ["daisy", "daisy daisy", "bicycle built for two", "a bicycle built for two"],
        "score": """
tempo 150
time 3/4
lead pulse25: G5/2. | E5/2. | C5/2. | G4/2. | A4/4 B4/4 C5/4 | A4/2 C5/4 | G4/2.~ | G4/4 r/2 |
lead: D5/2. | G5/2. | E5/2. | C5/2. | A4/4 B4/4 C5/4 | D5/2 E5/4 | D5/2.~ | D5/4 r/4 E5/4 |
lead: F5/4 E5/4 D5/4 | G5/2 E5/4 | D5/4 C5/2~ | C5/4 r/4 D5/4 | E5/2 C5/4 | A4/2 C5/4 | A4/4 G4/2~ | G4/4 r/4 G4/4 |
lead: C5/2 E5/4 | D5/2 G4/4 | C5/2 E5/4 | D5/2 E5/8 F5/8 | G5/4 E5/4 C5/4 | D5/2 G4/4 | C5/2.~ | C5/2 r/4 |
harmony pulse12 staccato: (r/4 C4+E4+G4/4 C4+E4+G4/4 |)x4 (r/4 C4+F4+A4/4 C4+F4+A4/4 |)x2 (r/4 C4+E4+G4/4 C4+E4+G4/4 |)x2
harmony: (r/4 B3+D4+F4/4 B3+D4+F4/4 |)x2 (r/4 C4+E4+G4/4 C4+E4+G4/4 |)x2 (r/4 A3+C4+F#4/4 A3+C4+F#4/4 |)x2 (r/4 B3+D4+G4/4 B3+D4+G4/4 |)x2
harmony: (r/4 B3+D4+F4/4 B3+D4+F4/4 |)x2 (r/4 C4+E4+G4/4 C4+E4+G4/4 |)x2 r/4 A3+C4+E4/4 A3+C4+E4/4 | r/4 C4+F4+A4/4 C4+F4+A4/4 | (r/4 C4+E4+G4/4 C4+E4+G4/4 |)x2
harmony: (r/4 C4+E4+G4/4 C4+E4+G4/4 | r/4 B3+D4+F4/4 B3+D4+F4/4 |)x3 r/4 C4+E4+G4/4 C4+E4+G4/4 | r/2. |
bass triangle: C3/4 r/2 | G2/4 r/2 | C3/4 r/2 | G2/4 r/2 | F2/4 r/2 | C3/4 r/2 | C3/4 r/2 | G2/4 r/2 |
bass: G2/4 r/2 | D3/4 r/2 | C3/4 r/2 | G2/4 r/2 | D3/4 r/2 | A2/4 r/2 | G2/4 r/2 | D3/4 r/2 |
bass: G2/4 r/2 | D3/4 r/2 | C3/4 r/2 | G2/4 r/2 | A2/4 r/2 | F2/4 r/2 | C3/4 r/2 | G2/4 r/2 |
bass: C3/4 r/2 | G2/4 r/2 | C3/4 r/2 | G2/4 r/2 | C3/4 r/2 | G2/4 r/2 | C3/2. | C3/4 r/2 |
"""},
    "happy-birthday": {
        "title": "Happy Birthday to You", "composer": "Mildred J. Hill and Patty Hill", "year": 1893,
        "fact": "The tune began in 1893 as 'Good Morning to All', a song for a kindergarten class "
                "in Louisville, Kentucky.",
        "aliases": ["happy birthday", "birthday", "birthday song"],
        "score": """
tempo 100
time 3/4
lead pulse50: G4/8. G4/16 | A4/4 G4/4 C5/4 | B4/2 G4/8. G4/16 | A4/4 G4/4 D5/4 | C5/2 G4/8. G4/16 |
lead: G5/4 E5/4 C5/4 | B4/4 A4/4 F5/8. F5/16 | E5/4 C5/4 D5/4 | C5/2 G4/8. G4/16 |
lead: A4/4 G4/4 C5/4 | B4/2 G4/8. G4/16 | A4/4 G4/4 D5/4 | C5/2 G4/8. G4/16 |
lead: G5/4 E5/4 C5/4 | @88 B4/4 A4/4 F5/8. F5/16 | @80 E5/4 C5/4 D5/4 | C5/2. |
harmony pulse12 staccato: r/4 | r/4 C4+E4+G4/4 C4+E4+G4/4 | (r/4 B3+D4+F4/4 B3+D4+F4/4 |)x2 r/4 C4+E4+G4/4 C4+E4+G4/4 |
harmony: r/4 Bb3+E4+G4/4 Bb3+E4+G4/4 | r/4 C4+F4+A4/4 C4+F4+A4/4 | r/4 C4+E4+G4/4 B3+D4+F4/4 | r/4 C4+E4+G4/4 C4+E4+G4/4 |
harmony: r/4 C4+E4+G4/4 C4+E4+G4/4 | (r/4 B3+D4+F4/4 B3+D4+F4/4 |)x2 r/4 C4+E4+G4/4 C4+E4+G4/4 |
harmony: r/4 Bb3+E4+G4/4 Bb3+E4+G4/4 | r/4 C4+F4+A4/4 C4+F4+A4/4 | r/4 C4+E4+G4/4 B3+D4+F4/4 | C4+E4+G4/2. |
bass triangle: r/4 | C3/4 r/2 | G2/4 r/2 | G2/4 r/2 | C3/4 r/2 | C3/4 r/2 | F2/4 r/2 | G2/4 r/4 G2/4 | C3/4 r/2 |
bass: C3/4 r/2 | G2/4 r/2 | G2/4 r/2 | C3/4 r/2 | C3/4 r/2 | F2/4 r/2 | G2/4 r/4 G2/4 | C3/2. |
drums: r/4 | (r/2. |)x8 (k/4 h/4 h/4 |)x7 k+c/4 r/2 |
"""},
    "fur-elise": {
        "title": "Für Elise", "composer": "Ludwig van Beethoven", "year": 1810,
        "fact": "Nobody knows for sure who Elise was, and the piece wasn't published until 1867, "
                "forty years after Beethoven died.",
        "aliases": ["fur elise", "fuer elise", "elise", "for elise", "beethoven"],
        "score": """
tempo 80
time 3/8
lead pulse25: E5/16 D#5/16 | E5/16 D#5/16 E5/16 B4/16 D5/16 C5/16 | A4/8 r/16 C4/16 E4/16 A4/16 | B4/8 r/16 E4/16 G#4/16 B4/16 | C5/8 r/16 E4/16 E5/16 D#5/16 |
lead: E5/16 D#5/16 E5/16 B4/16 D5/16 C5/16 | A4/8 r/16 C4/16 E4/16 A4/16 | B4/8 r/16 E4/16 C5/16 B4/16 | A4/4 E5/16 D#5/16 |
lead: E5/16 D#5/16 E5/16 B4/16 D5/16 C5/16 | A4/8 r/16 C4/16 E4/16 A4/16 | B4/8 r/16 E4/16 G#4/16 B4/16 | C5/8 r/16 E4/16 E5/16 D#5/16 |
lead: E5/16 D#5/16 E5/16 B4/16 D5/16 C5/16 | A4/8 r/16 C4/16 E4/16 A4/16 | B4/8 r/16 E4/16 C5/16 B4/16 | A4/8 r/16 B4/16 C5/16 D5/16 |
lead: E5/8. G4/16 F5/16 E5/16 | D5/8. F4/16 E5/16 D5/16 | C5/8. E4/16 D5/16 C5/16 | B4/8 r/16 E4/16 E5/16 r/16 |
lead: r/16 E5/16 E6/16 r/16 r/16 D#5/16 | E5/8 r/16 D#5/16 E5/16 D#5/16 | E5/16 D#5/16 E5/16 B4/16 D5/16 C5/16 |
lead: A4/8 r/16 C4/16 E4/16 A4/16 | B4/8 r/16 E4/16 G#4/16 B4/16 | C5/8 r/16 E4/16 E5/16 D#5/16 |
lead: E5/16 D#5/16 E5/16 B4/16 D5/16 C5/16 | A4/8 r/16 C4/16 E4/16 A4/16 | B4/8 r/16 E4/16 C5/16 B4/16 | A4/4. |
bass triangle: r/8 | r/4. | A2/16 E3/16 A3/16 r/16 r/8 | E2/16 E3/16 G#3/16 r/16 r/8 | A2/16 E3/16 A3/16 r/16 r/8 |
bass: r/4. | A2/16 E3/16 A3/16 r/16 r/8 | E2/16 E3/16 G#3/16 r/16 r/8 | A2/16 E3/16 A3/16 r/16 r/8 |
bass: r/4. | A2/16 E3/16 A3/16 r/16 r/8 | E2/16 E3/16 G#3/16 r/16 r/8 | A2/16 E3/16 A3/16 r/16 r/8 |
bass: r/4. | A2/16 E3/16 A3/16 r/16 r/8 | E2/16 E3/16 G#3/16 r/16 r/8 | A2/16 E3/16 A3/16 r/16 r/8 |
bass: C3/16 G3/16 C4/16 r/16 r/8 | G2/16 G3/16 B3/16 r/16 r/8 | A2/16 E3/16 A3/16 r/16 r/8 | E2/16 E3/16 E4/16 r/16 r/8 |
bass: r/4. | r/4. | r/4. |
bass: A2/16 E3/16 A3/16 r/16 r/8 | E2/16 E3/16 G#3/16 r/16 r/8 | A2/16 E3/16 A3/16 r/16 r/8 |
bass: r/4. | A2/16 E3/16 A3/16 r/16 r/8 | E2/16 E3/16 G#3/16 r/16 r/8 | A2/4. |
"""},
    "ode-to-joy": {
        "title": "Ode to Joy", "composer": "Ludwig van Beethoven", "year": 1824,
        "fact": "Beethoven was almost completely deaf when he wrote it; today it is the anthem "
                "of the European Union.",
        "aliases": ["ode to joy", "ode", "ninth symphony", "beethoven's ninth", "beethoven 9"],
        "score": """
tempo 132
time 4/4
lead pulse25: F#5/4 F#5/4 G5/4 A5/4 | A5/4 G5/4 F#5/4 E5/4 | D5/4 D5/4 E5/4 F#5/4 | F#5/4. E5/8 E5/2 |
lead: F#5/4 F#5/4 G5/4 A5/4 | A5/4 G5/4 F#5/4 E5/4 | D5/4 D5/4 E5/4 F#5/4 | E5/4. D5/8 D5/2 |
lead: E5/4 E5/4 F#5/4 D5/4 | E5/4 F#5/8 G5/8 F#5/4 D5/4 | E5/4 F#5/8 G5/8 F#5/4 E5/4 | D5/4 E5/4 A4/4 F#5/4~ |
lead: F#5/4 F#5/4 G5/4 A5/4 | A5/4 G5/4 F#5/4 E5/4 | D5/4 D5/4 E5/4 F#5/4 | E5/4. D5/8 D5/2 |
harmony pulse12 staccato: (r/4 D4+F#4+A4/4 r/4 D4+F#4+A4/4 |)x3 r/4 C#4+E4+A4/4 r/4 C#4+E4+G4/4 |
harmony: (r/4 D4+F#4+A4/4 r/4 D4+F#4+A4/4 | r/4 D4+F#4+A4/4 r/4 C#4+E4+A4/4 |)x2
harmony: (r/4 C#4+E4+A4/4 r/4 D4+F#4+A4/4 |)x2 r/4 C#4+E4+A4/4 r/4 C#4+E4+G4/4 | r/4 D4+F#4+A4/4 r/4 C#4+E4+A4/4 |
harmony: r/4 D4+F#4+A4/4 r/4 D4+F#4+A4/4 | r/4 D4+F#4+A4/4 r/4 C#4+E4+A4/4 | r/4 D4+F#4+A4/4 r/4 D4+F#4+A4/4 | r/4 C#4+E4+G4/4 r/4 D4+F#4+A4/4 |
bass triangle: D3/4 A2/4 D3/4 A2/4 | D3/4 A2/4 A2/4 E2/4 | D3/4 A2/4 D3/4 A2/4 | A2/4 E2/4 A2/4 E2/4 |
bass: D3/4 A2/4 D3/4 A2/4 | D3/4 A2/4 A2/4 E2/4 | D3/4 A2/4 D3/4 A2/4 | A2/4 E2/4 D3/2 |
bass: A2/4 E2/4 D3/4 A2/4 | A2/4 E2/4 D3/4 A2/4 | A2/4 E2/4 A2/4 C#3/4 | D3/4 A2/4 A2/4 A2/4 |
bass: D3/4 A2/4 D3/4 A2/4 | D3/4 A2/4 A2/4 E2/4 | D3/4 A2/4 D3/4 A2/4 | A2/4 E2/4 D3/2 |
drums: (k/8 h/8 s/8 h/8 k/8 h/8 s/8 h/8 |)x15 k+c/4 r/4 r/2 |
"""},
    "the-entertainer": {
        "title": "The Entertainer", "composer": "Scott Joplin", "year": 1902,
        "fact": "Joplin wrote 'Not fast' at the top of the music; he said it is never right to "
                "play ragtime fast.",
        "aliases": ["entertainer", "the entertainer", "joplin"],
        "score": """
tempo 84
time 2/4
lead pulse25: D6/16 E6/16 C6/16 A5/8 B5/16 G5/8 | D5/16 E5/16 C5/16 A4/8 B4/16 G4/8 | D4/16 E4/16 C4/16 A3/8 B3/16 A3/16 G#3/16 | G3/8 r/8 r/8 D5/16 D#5/16 |
lead: E5/16 C6/8 E5/16 C6/8 E5/16 C6/16~ | C6/4~ C6/16 C6/16 D6/16 D#6/16 | E6/16 C6/16 D6/16 E6/8 B5/16 D6/8 | C6/4. D5/16 D#5/16 |
lead: E5/16 C6/8 E5/16 C6/8 E5/16 C6/16~ | C6/4~ C6/8 A5/16 G5/16 | F#5/16 A5/16 C6/16 E6/8 D6/16 C6/16 A5/16 | D6/4. D5/16 D#5/16 |
lead: E5/16 C6/8 E5/16 C6/8 E5/16 C6/16~ | C6/4~ C6/16 C6/16 D6/16 D#6/16 | E6/16 C6/16 D6/16 E6/8 B5/16 D6/8 | C6/4. C6/16 D6/16 |
lead: E6/16 C6/16 D6/16 E6/8 C6/16 D6/16 C6/16 | E6/16 C6/16 D6/16 E6/8 C6/16 D6/16 C6/16 | E6/16 C6/16 D6/16 E6/8 B5/16 D6/8 | C6/4 r/4 |
harmony pulse12 staccato: r/2 | r/2 | r/2 | r/4 G3+B3+D4+F4/8 r/8 |
harmony: r/8 E4+G4+C5/8 r/8 E4+G4+Bb4/8 | r/8 F4+A4+C5/8 r/8 E4+G4+C5/8 | r/8 E4+G4+C5/8 r/8 F4+G4+B4/8 | r/8 E4+G4+C5/8 r/8 E4+G4+C5/8 |
harmony: r/8 E4+G4+C5/8 r/8 E4+G4+Bb4/8 | r/8 F4+A4+C5/8 r/8 E4+G4+C5/8 | r/8 F#4+A4+C5/8 r/8 F#4+A4+C5/8 | r/8 G4+B4+D5/8 r/8 F4+G4+B4/8 |
harmony: r/8 E4+G4+C5/8 r/8 E4+G4+Bb4/8 | r/8 F4+A4+C5/8 r/8 E4+G4+C5/8 | r/8 E4+G4+C5/8 r/8 F4+G4+B4/8 | r/8 E4+G4+C5/8 r/8 E4+G4+C5/8 |
harmony: r/8 E4+G4+C5/8 r/8 E4+G4+Bb4/8 | r/8 F4+A4+C5/8 r/8 F4+Ab4+C5/8 | r/8 E4+G4+C5/8 r/8 F4+G4+B4/8 | r/8 E4+G4+C5/8 r/4 |
bass triangle staccato: D5/16 E5/16 C5/16 A4/8 B4/16 G4/8 | D4/16 E4/16 C4/16 A3/8 B3/16 G3/8 | D3/16 E3/16 C3/16 A2/8 B2/16 A2/16 G#2/16 | G2/8 r/8 G2/8 r/8 |
bass: C2/8 r/8 G2/8 r/8 | F2/8 r/8 E2/8 r/8 | C2/8 r/8 G2/8 r/8 | C2/8 r/8 G2/8 r/8 |
bass: C2/8 r/8 G2/8 r/8 | F2/8 r/8 E2/8 r/8 | D2/8 r/8 A2/8 r/8 | G2/8 r/8 D2/8 r/8 |
bass: C2/8 r/8 G2/8 r/8 | F2/8 r/8 E2/8 r/8 | C2/8 r/8 G2/8 r/8 | C2/8 r/8 G2/8 r/8 |
bass: C2/8 r/8 G2/8 r/8 | F2/8 r/8 F2/8 r/8 | G2/8 r/8 G2/8 r/8 | C2/8 r/8 r/4 |
"""},
    "maple-leaf-rag": {
        "title": "Maple Leaf Rag", "composer": "Scott Joplin", "year": 1899,
        "fact": "It was named after the Maple Leaf Club in Sedalia, Missouri, and its success made "
                "Joplin the King of Ragtime.",
        "aliases": ["maple leaf", "maple leaf rag"],
        "score": """
tempo 92
time 2/4
lead pulse25: ( r/16 Ab4/16 Eb5/16 Ab4/16 C5/16 Eb5/8 Ab4/16 | Eb5/16 G4/16 Bb4/16 Eb5/16~ Eb5/4 |
lead: r/16 Ab4/16 Eb5/16 Ab4/16 C5/16 Eb5/8 Ab4/16 | Eb5/16 G4/16 Bb4/16 Eb5/16~ Eb5/4 |
lead: r/16 Ab4/16 B4/16 E5/16 r/16 Eb5/8 Eb5/16 | r/16 Ab4/16 B4/16 E5/16 r/16 Eb5/8. |
lead: Ab4/16 B4/16 Eb5/16 Ab5/16 Ab5/16 B5/16 Eb6/16 Ab6/16 | Ab4/16 B4/16 Eb5/16 Ab5/16 Ab5/16 B5/16 Eb6/16 Ab6/16 |
lead: ( Ab5/8 Ab5/8 Ab5/8 Ab5/16 Ab5/16~ | Ab5/16 Eb5/16 F5/16 C5/16 Eb5/16 F5/16~ F5/8 | Ab4/16 Bb4/16 B4/16 Ab4/16 Bb4/16 C5/8 Ab4/16 | C5/16 Ab4/16 Bb4/8 Ab4/8 r/8 | )x2 )x2
lead: Ab5/8 r/8 Ab4/8 r/8 |
harmony pulse12 staccato: ( ( r/8 Ab3+C4+Eb4/8 r/8 Ab3+C4+Eb4/8 | r/8 G3+Bb3+Db4/8 r/8 G3+Bb3+Db4/8 | )x2
harmony: ( r/8 E3+G#3+B3/8 r/8 Eb3+G3+Bb3/8 | )x2 r/2 | r/2 |
harmony: ( r/8 Ab3+B3+D4+F4/8 r/8 Ab3+B3+D4+F4/8 | r/8 Ab3+C4+Eb4/8 r/8 Ab3+C4+Eb4/8 | r/8 E3+G#3+B3/8 r/8 Ab3+C4+Eb4/8 | r/8 G3+Bb3+Db4/8 r/8 Ab3+C4+Eb4/8 | )x2 )x2
harmony: Ab3+C4+Eb4/8 r/8 r/4 |
bass triangle staccato: ( ( Ab2/8 r/8 Eb2/8 r/8 | Eb2/8 r/8 Bb2/8 r/8 | )x2 ( E2/8 r/8 Eb2/8 r/8 | )x2
bass: ( Ab2/16 B2/16 Eb3/16 Ab3/16 Ab3/16 B3/16 Eb4/16 Ab4/16 | )x2
bass: ( Ab2/8 r/8 F2/8 r/8 | Ab2/8 r/8 Eb2/8 r/8 | E2/8 r/8 Ab2/8 r/8 | Eb2/8 r/8 Ab2/8 r/8 | )x2 )x2
bass: Ab2/8 r/8 Ab1/8 r/8 |
drums: ( r/2 | )x16 ( k/8 h/8 s/8 h/8 | )x16 k+c/4 r/4 |
"""},
    "mountain-king": {
        "title": "In the Hall of the Mountain King", "composer": "Edvard Grieg", "year": 1875,
        "fact": "Grieg wrote it for the play Peer Gynt, and later grumbled that it reeked of cow "
                "pies and trollish self-satisfaction.",
        "aliases": ["mountain king", "hall of the mountain king", "in the hall of the mountain king",
                    "grieg", "troll"],
        "score": """
tempo 140
time 4/4
lead pulse25 staccato: @140 B3/8 C#4/8 D4/8 E4/8 F#4/8 D4/8 F#4/4 | F4/8 C#4/8 F4/4 E4/8 C4/8 E4/4 |
lead: @147 B3/8 C#4/8 D4/8 E4/8 F#4/8 D4/8 F#4/8 B4/8 | A4/8 F#4/8 D4/8 F#4/8 A4/4 r/4 |
lead: @154 B3/8 C#4/8 D4/8 E4/8 F#4/8 D4/8 F#4/4 | F4/8 C#4/8 F4/4 E4/8 C4/8 E4/4 |
lead: @161 B3/8 C#4/8 D4/8 E4/8 F#4/8 D4/8 F#4/8 B4/8 | A4/8 F#4/8 D4/8 F#4/8 A4/4 r/4 |
lead: @168 F#4/8 G#4/8 A#4/8 B4/8 C#5/8 A#4/8 C#5/4 | D5/8 A#4/8 D5/4 C#5/8 A#4/8 C#5/4 |
lead: @175 F#4/8 G#4/8 A#4/8 B4/8 C#5/8 A#4/8 C#5/4 | D5/8 A#4/8 D5/4 C#5/4 r/4 |
lead: @182 F#4/8 G#4/8 A#4/8 B4/8 C#5/8 A#4/8 C#5/4 | D5/8 A#4/8 D5/4 C#5/8 A#4/8 C#5/4 |
lead: @189 F#4/8 G#4/8 A#4/8 B4/8 C#5/8 A#4/8 C#5/4 | D5/8 A#4/8 D5/4 C#5/4 r/4 |
lead: @196 B4/8 C#5/8 D5/8 E5/8 F#5/8 D5/8 F#5/4 | F5/8 C#5/8 F5/4 E5/8 C5/8 E5/4 |
lead: @203 B4/8 C#5/8 D5/8 E5/8 F#5/8 D5/8 F#5/8 B5/8 | A5/8 F#5/8 D5/8 F#5/8 A5/4 r/4 |
lead: @210 B4/8 C#5/8 D5/8 E5/8 F#5/8 D5/8 F#5/4 | F5/8 C#5/8 F5/4 E5/8 C5/8 E5/4 |
lead: @217 B4/8 C#5/8 D5/8 E5/8 F#5/8 D5/8 F#5/8 B5/8 | A5/8 F#5/8 D5/8 F#5/8 A5/4 r/4 |
lead: @224 F#5/8 G#5/8 A#5/8 B5/8 C#6/8 A#5/8 C#6/4 | D6/8 A#5/8 D6/4 C#6/8 A#5/8 C#6/4 |
lead: @231 F#5/8 G#5/8 A#5/8 B5/8 C#6/8 A#5/8 C#6/4 | D6/8 A#5/8 D6/4 C#6/4 r/4 |
lead: @238 F#5/8 G#5/8 A#5/8 B5/8 C#6/8 A#5/8 C#6/4 | D6/8 A#5/8 D6/4 C#6/8 A#5/8 C#6/4 |
lead: @245 F#5/8 G#5/8 A#5/8 B5/8 C#6/8 A#5/8 C#6/4 | D6/8 A#5/8 D6/4 C#6/4 r/4 |
lead: @200 B4/4 r/4 F#4/4 r/4 | B3/4 r/4 r/2 |
harmony pulse12 staccato: ( r/1 | )x16
harmony: ( ( r/4 B3+D4+F#4/4 r/4 B3+D4+F#4/4 | )x3 r/4 D4+F#4+A4/4 r/4 D4+F#4+A4/4 | )x2
harmony: ( r/4 F#3+A#3+C#4/4 r/4 F#3+A#3+C#4/4 | r/4 F#3+A#3+D4/4 r/4 F#3+A#3+C#4/4 | )x4
harmony: B3+D4+F#4/4 r/4 F#3+A#3+C#4/4 r/4 | B3+D4+F#4/4 r/4 r/2 |
bass triangle staccato: ( ( B2/4 F#2/4 B2/4 F#2/4 | )x3 D3/4 A2/4 D3/4 A2/4 | )x2 ( ( F#2/4 C#3/4 F#2/4 C#3/4 | )x3 F#2/4 C#3/4 F#2/4 r/4 | )x2
bass: ( ( B2/4 F#2/4 B2/4 F#2/4 | )x3 D3/4 A2/4 D3/4 A2/4 | )x2 ( ( F#2/4 C#3/4 F#2/4 C#3/4 | )x3 F#2/4 C#3/4 F#2/4 r/4 | )x2
bass: B2/4 r/4 F#2/4 r/4 | B1/4 r/4 r/2 |
drums: ( r/1 | )x8 ( k/4 r/4 k/4 r/4 | )x8 ( k+h/8 h/8 s+h/8 h/8 k+h/8 h/8 s+h/8 h/8 | )x16
drums: k+c/4 r/4 k/4 r/4 | k+c/4 r/4 r/2 |
"""},
    "william-tell": {
        "title": "William Tell Overture (finale)", "composer": "Gioachino Rossini", "year": 1829,
        "fact": "It was the last opera Rossini ever wrote, though he lived for almost forty more "
                "years.",
        "aliases": ["william tell", "william tell overture", "guillaume tell", "lone ranger",
                    "rossini"],
        "score": """
tempo 152
time 2/4
lead pulse25: B4/16 B4/16 |
lead: B4/8 B4/16 B4/16 B4/8 B4/16 B4/16 | E5/8 F#5/8 G#5/8 B4/16 B4/16 | B4/8 B4/16 B4/16 E5/8 G#5/16 G#5/16 | F#5/8 D#5/8 B4/8 B4/16 B4/16 |
lead: B4/8 B4/16 B4/16 B4/8 B4/16 B4/16 | E5/8 F#5/8 G#5/8 E5/16 G#5/16 | B5/4~ B5/16 A5/16 G#5/16 F#5/16 | E5/8 G#5/8 E5/8 B5/16 B5/16 |
lead: B5/8 B5/16 B5/16 B5/8 B5/16 B5/16 | E6/8 F#6/8 G#6/8 B5/16 B5/16 | B5/8 B5/16 B5/16 E6/8 G#6/16 G#6/16 | F#6/8 D#6/8 B5/8 B5/16 B5/16 |
lead: B5/8 B5/16 B5/16 B5/8 B5/16 B5/16 | E6/8 F#6/8 G#6/8 E5/16 G#5/16 | B5/4~ B5/16 A5/16 G#5/16 F#5/16 | E5/8 G#5/8 E5/8 G#5/16 G#5/16 |
lead: G#5/8 G#5/16 G#5/16 G#5/8 G#5/16 G#5/16 | G#5/8 C#6/8 G#5/8 C#6/8 | G#5/8 C#6/8 G#5/8 F#5/8 | E5/8 D#5/8 C#5/8 G#5/16 G#5/16 |
lead: G#5/8 G#5/16 G#5/16 G#5/8 G#5/16 G#5/16 | G#5/8 C#6/8 G#5/8 C#6/8 | G#5/8 C#6/8 B5/8 A#5/8 | B5/8 A#5/8 B5/8 G#5/16 G#5/16 |
lead: G#5/8 G#5/16 G#5/16 G#5/8 G#5/16 G#5/16 | G#5/8 C#6/8 G#5/8 C#6/8 | G#5/8 C#6/8 G#5/8 F#5/8 | E5/8 D#5/8 C#5/8 G#5/16 G#5/16 |
lead: G#5/8 G#5/16 G#5/16 G#5/8 G#5/16 G#5/16 | G#5/8 C#6/8 G#5/8 C#6/8 | G#5/8 C#6/8 B5/8 A#5/8 | B5/8 r/8 r/8 B4/16 B4/16 |
lead: B4/8 B4/16 B4/16 B4/8 B4/16 B4/16 | E5/8 F#5/8 G#5/8 B4/16 B4/16 | B4/8 B4/16 B4/16 E5/8 G#5/16 G#5/16 | F#5/8 D#5/8 B4/8 B4/16 B4/16 |
lead: B4/8 B4/16 B4/16 B4/8 B4/16 B4/16 | E5/8 F#5/8 G#5/8 E5/16 G#5/16 | B5/4~ B5/16 A5/16 G#5/16 F#5/16 | E5/8 G#5/8 E5/8 r/8 |
lead: E5/8 r/8 B4/8 r/8 | E5/4 r/4 |
harmony pulse12 staccato: r/8 |
harmony: ( ( r/8 G#3+B3+E4/8 r/8 G#3+B3+E4/8 | )x3 r/8 F#3+A3+D#4/8 r/8 F#3+A3+D#4/8 | ( r/8 G#3+B3+E4/8 r/8 G#3+B3+E4/8 | )x2 r/8 F#3+A3+D#4/8 r/8 F#3+A3+D#4/8 | r/8 G#3+B3+E4/8 r/8 G#3+B3+E4/8 | )x2
harmony: ( r/8 G#3+C4+F#4/8 r/8 G#3+C4+F#4/8 | ( r/8 G#3+C#4+E4/8 r/8 G#3+C#4+E4/8 | )x3 r/8 G#3+C4+F#4/8 r/8 G#3+C4+F#4/8 | r/8 G#3+C#4+E4/8 r/8 G#3+C#4+E4/8 | r/8 F#3+A#3+E4/8 r/8 F#3+A#3+E4/8 | r/8 F#3+B3+D#4/8 r/8 F#3+B3+D#4/8 | )x2
harmony: ( r/8 G#3+B3+E4/8 r/8 G#3+B3+E4/8 | )x3 r/8 F#3+A3+D#4/8 r/8 F#3+A3+D#4/8 | ( r/8 G#3+B3+E4/8 r/8 G#3+B3+E4/8 | )x2 r/8 F#3+A3+D#4/8 r/8 F#3+A3+D#4/8 | r/8 G#3+B3+E4/8 r/4 |
harmony: G#3+B3+E4/8 r/8 F#3+A3+D#4/8 r/8 | G#3+B3+E4/4 r/4 |
bass triangle staccato: r/8 |
bass: ( ( E2/8 B2/8 E2/8 B2/8 | )x3 B2/8 F#2/8 B2/8 F#2/8 | ( E2/8 B2/8 E2/8 B2/8 | )x2 B2/8 F#2/8 B2/8 F#2/8 | E2/8 B2/8 E2/8 B2/8 | )x2
bass: ( G#2/8 D#3/8 G#2/8 D#3/8 | ( C#3/8 G#2/8 C#3/8 G#2/8 | )x3 G#2/8 D#3/8 G#2/8 D#3/8 | C#3/8 G#2/8 C#3/8 G#2/8 | F#2/8 C#3/8 F#2/8 C#3/8 | B2/8 F#2/8 B2/8 F#2/8 | )x2
bass: ( E2/8 B2/8 E2/8 B2/8 | )x3 B2/8 F#2/8 B2/8 F#2/8 | ( E2/8 B2/8 E2/8 B2/8 | )x2 B2/8 F#2/8 B2/8 F#2/8 | E2/8 B2/8 E2/8 r/8 |
bass: E2/8 r/8 B1/8 r/8 | E2/4 r/4 |
drums: r/8 | ( r/2 | )x8 ( k/8 h/16 h/16 s/8 h/16 h/16 | )x32 k+c/8 r/8 k/8 r/8 | k+c/4 r/4 |
"""},
    "pachelbel-canon": {
        "title": "Canon in D", "composer": "Johann Pachelbel", "year": 1700,
        "fact": "Written around 1700, it was almost forgotten until a recording in 1968 made it "
                "one of the most played pieces at weddings.",
        "aliases": ["canon", "canon in d", "pachelbel", "pachelbel's canon", "pachelbels canon"],
        "score": """
tempo 70
time 4/4
lead pulse25 legato echo: r/1 | r/1 | F#5/4 E5/4 D5/4 C#5/4 | B4/4 A4/4 B4/4 C#5/4 | D5/4 C#5/4 B4/4 A4/4 | G4/4 F#4/4 G4/4 E4/4 |
lead: D4/8 F#4/8 A4/8 G4/8 F#4/8 D4/8 F#4/8 E4/8 | D4/8 B3/8 D4/8 A4/8 G4/8 B4/8 A4/8 G4/8 |
lead: F#4/8 D4/8 E4/8 C#5/8 D5/8 F#5/8 A5/8 A4/8 | B4/8 G4/8 A4/8 F#4/8 D4/8 D5/8 D5/8. C#5/16 | D5/1 |
harmony pulse12 legato: r/1 | r/1 | r/1 | r/1 | F#5/4 E5/4 D5/4 C#5/4 | B4/4 A4/4 B4/4 C#5/4 | D5/4 C#5/4 B4/4 A4/4 | G4/4 F#4/4 G4/4 E4/4 |
harmony: D4/8 F#4/8 A4/8 G4/8 F#4/8 D4/8 F#4/8 E4/8 | D4/8 B3/8 D4/8 A4/8 G4/8 B4/8 A4/8 G4/8 | F#4/1 |
bass triangle legato: ( D3/4 A2/4 B2/4 F#2/4 | G2/4 D2/4 G2/4 A2/4 | )x5 D2/1 |
"""},
    "minuet-in-g": {
        "title": "Minuet in G", "composer": "Christian Petzold", "year": 1725,
        "fact": "For about 250 years everyone thought Bach wrote it, because it was found in a "
                "notebook Bach gave his wife Anna Magdalena.",
        "aliases": ["minuet", "minuet in g", "bach minuet", "petzold"],
        "score": """
tempo 138
time 3/4
lead pulse25: D5/4 G4/8 A4/8 B4/8 C5/8 | D5/4 G4/4 G4/4 | E5/4 C5/8 D5/8 E5/8 F#5/8 | G5/4 G4/4 G4/4 | C5/4 D5/8 C5/8 B4/8 A4/8 | B4/4 C5/8 B4/8 A4/8 G4/8 | F#4/4 G4/8 A4/8 B4/8 G4/8 | A4/2. |
lead: D5/4 G4/8 A4/8 B4/8 C5/8 | D5/4 G4/4 G4/4 | E5/4 C5/8 D5/8 E5/8 F#5/8 | G5/4 G4/4 G4/4 | C5/4 D5/8 C5/8 B4/8 A4/8 | B4/4 C5/8 B4/8 A4/8 G4/8 | A4/4 B4/8 A4/8 G4/8 F#4/8 | G4/2. |
lead: B5/4 G5/8 A5/8 B5/8 G5/8 | A5/4 D5/8 E5/8 F#5/8 D5/8 | G5/4 E5/8 F#5/8 G5/8 D5/8 | C#5/4 B4/8 C#5/8 A4/4 | A4/8 B4/8 C#5/8 D5/8 E5/8 F#5/8 | G5/4 F#5/4 E5/4 | F#5/4 A4/4 C#5/4 | D5/2. |
lead: D5/4 G4/8 F#4/8 G4/4 | E5/4 G4/8 F#4/8 G4/4 | D5/4 C5/4 B4/4 | A4/8 G4/8 F#4/8 G4/8 A4/4 | D4/8 E4/8 F#4/8 G4/8 A4/8 B4/8 | C5/4 B4/4 A4/4 | B4/8 D5/8 G4/4 F#4/4 | G4/2. |
bass triangle: G2/2 A2/4 | B2/2. | C3/2. | B2/2. | A2/2. | G2/2. | D3/4 B2/4 G2/4 | D3/4 D2/8 C3/8 B2/8 A2/8 |
bass: B2/2 A2/4 | G2/4 B2/4 G2/4 | C3/2. | B2/4 C3/8 B2/8 A2/8 G2/8 | A2/2 F#2/4 | G2/2 B2/4 | C3/4 D3/4 D2/4 | G2/2 G1/4 |
bass: G2/2. | F#2/2. | E2/4 G2/4 E2/4 | A2/2 A1/4 | A2/2. | B2/4 D3/4 C#3/4 | D3/4 F#2/4 A2/4 | D3/4 D2/4 C3/4 |
bass: B2/2 B2/4 | C3/2 C3/4 | B2/4 A2/4 G2/4 | D3/2 r/4 | D2/2. | E2/4 G2/4 F#2/4 | G2/4 B1/4 D2/4 | G2/4 D2/4 G1/4 |
"""},
    "greensleeves": {
        "title": "Greensleeves", "composer": "Traditional English", "year": 1580,
        "fact": "Legend says King Henry the Eighth wrote it, but the first record of the tune is "
                "from 1580, after he died.",
        "aliases": ["greensleeves", "green sleeves", "what child is this"],
        "score": """
tempo 84
time 6/8
lead pulse25 echo: A4/8 | C5/4 D5/8 E5/8. F#5/16 E5/8 | D5/4 B4/8 G4/8. A4/16 B4/8 | C5/4 A4/8 A4/8. G#4/16 A4/8 | B4/4 G#4/8 E4/4 A4/8 |
lead: C5/4 D5/8 E5/8. F#5/16 E5/8 | D5/4 B4/8 G4/8. A4/16 B4/8 | C5/8. B4/16 A4/8 G#4/8. F#4/16 G#4/8 | A4/2. |
lead: G5/4. G5/8. F#5/16 E5/8 | D5/4 B4/8 G4/8. A4/16 B4/8 | C5/4 A4/8 A4/8. G#4/16 A4/8 | B4/4 G#4/8 E4/4. |
lead: G5/4. G5/8. F#5/16 E5/8 | D5/4 B4/8 G4/8. A4/16 B4/8 | C5/8. B4/16 A4/8 G#4/8. F#4/16 G#4/8 | A4/2. |
harmony pulse12: r/8 | A3/8 C4/8 E4/8 A3/8 C4/8 E4/8 | G3/8 B3/8 D4/8 G3/8 B3/8 D4/8 | A3/8 C4/8 E4/8 A3/8 C4/8 E4/8 | E3/8 G#3/8 B3/8 E3/8 G#3/8 B3/8 |
harmony: A3/8 C4/8 E4/8 A3/8 C4/8 E4/8 | G3/8 B3/8 D4/8 G3/8 B3/8 D4/8 | A3/8 C4/8 E4/8 E3/8 G#3/8 B3/8 | A3/8 C4/8 E4/8 A3/8 C4/8 E4/8 |
harmony: C4/8 E4/8 G4/8 C4/8 E4/8 G4/8 | G3/8 B3/8 D4/8 G3/8 B3/8 D4/8 | A3/8 C4/8 E4/8 A3/8 C4/8 E4/8 | E3/8 G#3/8 B3/8 E3/8 G#3/8 B3/8 |
harmony: C4/8 E4/8 G4/8 C4/8 E4/8 G4/8 | G3/8 B3/8 D4/8 G3/8 B3/8 D4/8 | A3/8 C4/8 E4/8 E3/8 G#3/8 B3/8 | A3/8 C4/8 E4/8 A3/4. |
bass triangle: r/8 | A2/2. | G2/2. | A2/2. | E2/2. | A2/2. | G2/2. | A2/4. E2/4. | A2/2. |
bass: C3/2. | G2/2. | A2/2. | E2/2. | C3/2. | G2/2. | A2/4. E2/4. | A2/2. |
"""},
    "rondo-alla-turca": {
        "title": "Rondo alla Turca", "composer": "Wolfgang Amadeus Mozart", "year": 1783,
        "fact": "Mozart was copying the sound of Turkish military bands, which were all the rage "
                "in Vienna at the time.",
        "aliases": ["rondo alla turca", "turkish march", "turkish rondo", "alla turca", "rondo",
                    "mozart"],
        "score": """
tempo 126
time 2/4
lead pulse25: B4/16 A4/16 G#4/16 A4/16 |
lead: C5/8 r/8 D5/16 C5/16 B4/16 C5/16 | E5/8 r/8 F5/16 E5/16 D#5/16 E5/16 | B5/16 A5/16 G#5/16 A5/16 B5/16 A5/16 G#5/16 A5/16 | C6/4 A5/8 C6/8 |
lead: B5/8 A5/8 G5/8 A5/8 | B5/8 A5/8 G5/8 A5/8 | B5/8 A5/8 G5/8 F#5/8 | E5/4 B4/16 A4/16 G#4/16 A4/16 |
lead: C5/8 r/8 D5/16 C5/16 B4/16 C5/16 | E5/8 r/8 F5/16 E5/16 D#5/16 E5/16 | B5/16 A5/16 G#5/16 A5/16 B5/16 A5/16 G#5/16 A5/16 | C6/4 A5/8 C6/8 |
lead: B5/8 A5/8 G5/8 A5/8 | B5/8 A5/8 G5/8 A5/8 | B5/8 A5/8 G5/8 F#5/8 | E5/4 E5/8 F5/8 |
lead: G5/8 G5/8 A5/16 G5/16 F5/16 E5/16 | D5/4 E5/8 F5/8 | G5/8 G5/8 A5/16 G5/16 F5/16 E5/16 | D5/4 C5/8 D5/8 |
lead: E5/8 E5/8 F5/16 E5/16 D5/16 C5/16 | B4/4 C5/8 D5/8 | E5/8 E5/8 F5/16 E5/16 D5/16 C5/16 | B4/4 B4/16 A4/16 G#4/16 A4/16 |
lead: C5/8 r/8 D5/16 C5/16 B4/16 C5/16 | E5/8 r/8 F5/16 E5/16 D#5/16 E5/16 | B5/16 A5/16 G#5/16 A5/16 B5/16 A5/16 G#5/16 A5/16 | C6/4 A5/8 B5/8 |
lead: C6/8 B5/8 A5/8 G#5/8 | A5/8 E5/8 F5/8 D5/8 | C5/4 B4/8. A4/32 B4/32 | A4/4 r/4 |
harmony pulse12 staccato: r/4 |
harmony: ( r/8 C4+E4/8 C4+E4/8 C4+E4/8 | r/8 C4+E4/8 C4+E4/8 C4+E4/8 | r/8 C4+E4/8 r/8 C4+E4/8 | r/8 C4+E4/8 C4+E4/8 C4+E4/8 |
harmony: r/8 B3+E4/8 B3+E4/8 B3+E4/8 | r/8 B3+E4/8 B3+E4/8 B3+E4/8 | r/8 B3+E4/8 r/4 | )x2
harmony: r/2 | r/4 C5/8 D5/8 |
harmony: E5/8 E5/8 r/4 | B4/8 G4/8 C5/8 D5/8 | E5/8 E5/8 r/4 | B4/4 A4/8 B4/8 | C5/8 C5/8 r/4 | G#4/8 E4/8 A4/8 B4/8 | C5/8 C5/8 r/4 | G#4/4 r/4 |
harmony: r/8 C4+E4/8 C4+E4/8 C4+E4/8 | r/8 C4+E4/8 C4+E4/8 C4+E4/8 | r/8 C4+E4/8 r/8 C4+E4/8 | r/8 A3+D#4/8 A3+D#4/8 A3+D#4/8 |
harmony: r/8 A3+E4/8 r/8 F3+B3/8 | r/8 E3+A3/8 r/8 F3+B3/8 | E3+A3/8 E3+A3/8 E3+G#3/8 E3+G#3/8 | r/2 |
bass triangle staccato: r/4 |
bass: ( A2/8 r/8 r/4 | A2/8 r/8 r/4 | A2/8 r/8 A2/8 r/8 | A2/8 r/8 r/4 | E2/8 r/8 r/4 | E2/8 r/8 r/4 | E2/8 r/8 B1/8 B2/8 | E2/4 r/4 | )x2
bass: C3/8 C4/8 E3/8 E4/8 | G3/4 r/4 | C3/8 C4/8 E3/8 E4/8 | G3/4 r/4 | A2/8 A3/8 C3/8 C4/8 | E3/4 r/4 | A2/8 A3/8 C3/8 C4/8 | E3/4 r/4 |
bass: A2/8 r/8 r/4 | A2/8 r/8 r/4 | A2/8 r/8 A2/8 r/8 | F2/8 r/8 r/4 | E2/8 r/8 D2/8 r/8 | C2/8 r/8 D2/8 r/8 | E2/8 E2/8 E2/8 E2/8 | A2/4 r/4 |
"""},
    "marionette": {
        "title": "Funeral March of a Marionette", "composer": "Charles Gounod", "year": 1872,
        "fact": "Gounod wrote it in London as a musical joke, reportedly poking fun at a music "
                "critic he didn't like.",
        "aliases": ["funeral march of a marionette", "marionette", "funeral march", "gounod",
                    "puppet", "hitchcock"],
        "score": """
tempo 112
time 6/8
lead pulse50: D4/8 r/8 D4/8 D4/8 C#4/8 B3/8 | C#4/8 r/8 D4/8 E4/8 r/4 | D4/8 r/8 D4/8 D4/8 C#4/8 B3/8 | C#4/8 r/8 D4/8 E4/8 r/4 |
lead: D4/8 r/8 F4/8 A4/4 G4/8 | F4/8 r/8 A4/8 C5/4 Bb4/8 | A4/8 r/8 C5/8 E5/4 D5/8 | C#5/8 Bb4/8 A4/8 G4/8 F4/8 E4/8 |
lead: D4/8 r/8 D4/8 D4/8 C#4/8 B3/8 | C#4/8 r/8 D4/8 E4/8 r/4 | D4/8 r/8 D4/8 D4/8 C#4/8 B3/8 | C#4/8 r/8 D4/8 E4/8 r/8 C#4/8 |
lead: D4/8 r/8 A4/8 C5/4 Bb4/8 | A4/8 G4/8 F4/8 Eb4/8 G4/8 Bb4/8 | D4/8 C#4/8 D4/8 E4/8 r/8 F4/8 | E4/4. D4/8 r/4 |
harmony pulse12 staccato: ( r/8 F3+A3+D4/8 F3+A3+D4/8 r/8 F3+A3+D4/8 F3+A3+D4/8 | r/8 E3+G3+C#4/8 E3+G3+C#4/8 r/8 E3+G3+C#4/8 E3+G3+C#4/8 | )x2
harmony: r/8 F3+A3+D4/8 F3+A3+D4/8 r/8 E3+G3+C#4/8 E3+G3+C#4/8 | r/8 F3+A3+D4/8 F3+A3+D4/8 r/8 E3+G3+Bb3/8 E3+G3+Bb3/8 |
harmony: r/8 F3+A3+C4/8 F3+A3+C4/8 r/8 E3+G#3+D4/8 E3+G#3+D4/8 | r/8 E3+G3+C#4/8 E3+G3+C#4/8 r/8 E3+G3+C#4/8 E3+G3+C#4/8 |
harmony: ( r/8 F3+A3+D4/8 F3+A3+D4/8 r/8 F3+A3+D4/8 F3+A3+D4/8 | r/8 E3+G3+C#4/8 E3+G3+C#4/8 r/8 E3+G3+C#4/8 E3+G3+C#4/8 | )x2
harmony: r/8 F3+A3+D4/8 F3+A3+D4/8 r/8 E3+G3+Bb3/8 E3+G3+Bb3/8 | r/8 F3+A3+C4/8 F3+A3+C4/8 r/8 Eb3+G3+Bb3/8 Eb3+G3+Bb3/8 |
harmony: r/8 F3+A3+D4/8 F3+A3+D4/8 r/8 E3+G3+C#4/8 E3+G3+C#4/8 | r/8 E3+G3+C#4/8 E3+G3+C#4/8 F3+A3+D4/8 r/4 |
bass triangle staccato: ( D2/8 r/4 A2/8 r/4 | A2/8 r/4 E2/8 r/4 | )x2 D2/8 r/4 A2/8 r/4 | D2/8 r/4 C2/8 r/4 | F2/8 r/4 E2/8 r/4 | A2/8 r/4 E2/8 r/4 |
bass: ( D2/8 r/4 A2/8 r/4 | A2/8 r/4 E2/8 r/4 | )x2 D2/8 r/4 C2/8 r/4 | F2/8 r/4 Eb2/8 r/4 | D2/8 r/4 A2/8 r/4 | A2/8 r/4 D2/8 r/4 |
"""},
    "can-can": {
        "title": "Can-Can (Infernal Galop)", "composer": "Jacques Offenbach", "year": 1858,
        "fact": "In the operetta Orpheus in the Underworld, this wild dance is done by the gods "
                "of Mount Olympus, partying in the underworld.",
        "aliases": ["cancan", "can can", "infernal galop", "galop", "offenbach",
                    "orpheus in the underworld"],
        "score": """
tempo 144
time 2/4
lead pulse25: @144 ( C5/4 D5/16 F5/16 E5/16 D5/16 | G5/8 G5/8 G5/16 A5/16 E5/16 F5/16 | D5/8 D5/8 D5/16 F5/16 E5/16 D5/16 | C5/16 C6/16 B5/16 A5/16 G5/16 F5/16 E5/16 D5/16 |
lead: C5/4 D5/16 F5/16 E5/16 D5/16 | G5/8 G5/8 G5/16 A5/16 E5/16 F5/16 | D5/8 D5/8 D5/16 F5/16 E5/16 D5/16 | C5/16 G5/16 D5/16 E5/16 C5/8 G4/8 | )x2
lead: @156 ( C5/4 D5/16 F5/16 E5/16 D5/16 | G5/8 G5/8 G5/16 A5/16 E5/16 F5/16 | D5/8 D5/8 D5/16 F5/16 E5/16 D5/16 | C5/16 C6/16 B5/16 A5/16 G5/16 F5/16 E5/16 D5/16 |
lead: C5/4 D5/16 F5/16 E5/16 D5/16 | G5/8 G5/8 G5/16 A5/16 E5/16 F5/16 | D5/8 D5/8 D5/16 F5/16 E5/16 D5/16 | C5/16 G5/16 D5/16 E5/16 C5/8 G4/8 | @168 )x2
lead: C6/8 r/8 C5/8 r/8 |
harmony pulse12 staccato: ( r/8 E4+G4/8 r/8 F4+B4/8 | r/8 E4+G4/8 r/8 E4+G4/8 | r/8 F4+B4/8 r/8 F4+B4/8 | r/8 E4+G4/8 r/8 F4+B4/8 |
harmony: r/8 E4+G4/8 r/8 F4+B4/8 | r/8 E4+G4/8 r/8 E4+G4/8 | r/8 F4+B4/8 r/8 F4+B4/8 | r/8 E4+G4/8 r/8 E4+G4/8 | )x4
harmony: E4+G4+C5/8 r/8 r/4 |
bass triangle staccato: ( C3/8 G2/8 G2/8 D3/8 | C3/8 G2/8 C3/8 G2/8 | G2/8 D3/8 G2/8 D3/8 | C3/8 G2/8 G2/8 D3/8 |
bass: C3/8 G2/8 G2/8 D3/8 | C3/8 G2/8 C3/8 G2/8 | G2/8 D3/8 G2/8 D3/8 | C3/8 G2/8 C3/8 r/8 | )x4
bass: C3/8 r/8 C2/8 r/8 |
drums: ( r/2 | )x8 ( k/8 h/8 s/8 h/8 | )x24 k+c/8 r/8 k/8 r/8 |
"""},
    "habanera": {
        "title": "Habanera (from Carmen)", "composer": "Georges Bizet", "year": 1875,
        "fact": "Bizet thought the tune was a folk song, but it was really by Sebastián Yradier, "
                "so Bizet had to add a note crediting him.",
        "aliases": ["habanera", "carmen", "l'amour est un oiseau rebelle", "bizet"],
        "score": """
tempo 76
time 2/4
lead pulse25: r/2 | r/2 |
lead: ( r/4 D5/8 C#5/8 | C5/8t C5/8t C5/8t B4/8 Bb4/8 | A4/8 A4/16 A4/16 G#4/8 G4/8 | F4/16t G4/16t F4/16t E4/16 F4/16 G4/8 F4/8 |
lead: E4/8 r/8 D5/8 C#5/8 | C5/8t C5/8t C5/8t B4/8 Bb4/8 | A4/8 A4/16 A4/16 G4/8 F4/8 | E4/16t F4/16t E4/16t D4/16 E4/16 F4/8 E4/8 | D4/4 r/4 | )x2
bass triangle staccato: ( D2/8 r/16 A2/16 F3/8 A2/8 | )x19 D2/4 r/4 |
drums: ( r/2 | )x11 ( k/8. h/16 s/8 h/8 | )x8 k/4 r/4 |
"""},
    "blue-danube": {
        "title": "The Blue Danube", "composer": "Johann Strauss II", "year": 1867,
        "fact": "It's often called Austria's unofficial second national anthem, and Vienna plays "
                "it every New Year's Day.",
        "aliases": ["blue danube", "the blue danube", "danube", "blue danube waltz", "strauss"],
        "score": """
tempo 168
time 3/4
lead pulse25: D4/4 | D4/4 F#4/4 A4/4 | A4/2 A5/4 | A5/4 r/4 F#5/4 | F#5/4 r/4 D4/4 | D4/4 F#4/4 A4/4 | A4/2 A5/4 | A5/4 r/4 G5/4 | G5/4 r/4 C#4/4 |
lead: C#4/4 E4/4 B4/4 | B4/2 B5/4 | B5/4 r/4 G5/4 | G5/4 r/4 C#4/4 | C#4/4 E4/4 B4/4 | B4/2 B5/4 | B5/4 r/4 F#5/4 | F#5/4 r/4 D4/4 |
lead: D4/4 F#4/4 A4/4 | D5/2 D6/4 | D6/4 r/4 A5/4 | A5/4 r/4 D4/4 | D4/4 F#4/4 A4/4 | D5/2 D6/4 | D6/4 r/4 B5/4 | B5/4 r/4 E4/4 |
lead: E4/4 G4/4 B4/4 | B4/2.~ | B4/4 G#4/4 A4/4 | F#5/2.~ | F#5/4 D5/4 F#4/4 | F#4/2 E4/4 | B4/2 A4/4 | D4/4. D5/8 D5/4 | D5/4 r/2 |
harmony pulse12 staccato: r/4 | r/2. | ( r/4 F#3+A3+D4/4 F#3+A3+D4/4 | )x4 ( r/4 G3+C#4+E4/4 G3+C#4+E4/4 | )x8
harmony: ( r/4 F#3+A3+D4/4 F#3+A3+D4/4 | )x4 ( r/4 A3+D4+F#4/4 A3+D4+F#4/4 | )x4 ( r/4 G3+B3+E4/4 G3+B3+E4/4 | )x2 G3+B3+E4/2. | r/2. |
harmony: r/4 G3+C#4+E4/4 G3+C#4+E4/4 | r/4 G3+C#4+E4/4 G3+C#4+E4/4 | r/4 F#3+A3+D4/4 F#3+A3+D4/4 | r/4 A3+D4+F#4/4 A3+D4+F#4/4 |
harmony: G3+B3+D4/2. | E3+A3+C#4/2. | D3+F#3+A3/2 D3+F#3+A3/4 | D3+F#3+A3/4 r/2 |
bass triangle: r/4 | r/2. | ( D2/4 r/2 | )x4 ( E2/4 r/2 | )x8 ( D2/4 r/2 | )x4 ( F#2/4 r/2 | )x4 ( G2/4 r/2 | )x2 G2/2. |
bass: B2/4 G2/4 E2/4 | E2/4 r/2 | C#2/4 r/2 | D2/4 r/2 | F#2/4 r/2 | G2/2. | E2/2. | D2/2 D2/4 | D2/4 r/2 |
"""},
    "morning-mood": {
        "title": "Morning Mood", "composer": "Edvard Grieg", "year": 1875,
        "fact": "Everyone pictures a Norwegian sunrise, but in the play Peer Gynt it's the sun "
                "rising over the Sahara desert.",
        "aliases": ["morning mood", "peer gynt", "sunrise", "morgenstemning"],
        "score": """
tempo 100
time 6/8
lead triangle echo: B5/8 G#5/8 F#5/8 E5/8 F#5/8 G#5/8 | B5/8 G#5/8 F#5/8 E5/8 F#5/16 G#5/16 F#5/16 G#5/16 | B5/8 G#5/8 B5/8 C#6/8 G#5/8 C#6/8 | B5/8 G#5/8 F#5/8 E5/4. |
lead: B4/8 G#4/8 F#4/8 E4/8 F#4/8 G#4/8 | B4/8 G#4/8 F#4/8 E4/8 F#4/16 G#4/16 F#4/16 G#4/16 | B4/8 G#4/8 B4/8 C#5/8 G#4/8 C#5/8 | D#5/8 C5/8 A#4/8 G#4/4. |
lead: D#6/8 C6/8 A#5/8 G#5/8 A#5/8 C6/8 | D#6/8 C6/8 A#5/8 G#5/8 A#5/16 C6/16 A#5/16 C6/16 | D#6/8 C6/8 D#6/8 E6/8 C6/8 E6/8 | D#6/8 C6/8 A#5/8 G#5/4. |
lead: D#5/8 C5/8 A#4/8 G#4/8 A#4/8 C5/8 | D#5/8 C5/8 A#4/8 G#4/8 A#4/16 C5/16 A#4/16 C5/16 | D#5/8 C5/8 D#5/8 E5/8 C#5/8 E5/8 | F#5/8 D#5/8 C#5/8 B4/4. |
lead: B5/8 G#5/8 F#5/8 E5/8 F#5/8 G#5/8 | B5/8 G#5/8 F#5/8 E5/8 F#5/16 G#5/16 F#5/16 G#5/16 | B5/8 G#5/8 B5/8 C#6/8 G#5/8 C#6/8 | B5/8 G#5/8 F#5/8 E5/4.~ | E5/2. |
harmony pulse12: ( E3/8 B3/8 E4/8 G#4/8 E4/8 B3/8 | )x2 C#3/8 G#3/8 B3/8 E4/8 B3/8 G#3/8 | E3/8 B3/8 E4/8 G#4/8 E4/8 B3/8 |
harmony: ( E3/8 B3/8 E4/8 G#4/8 E4/8 B3/8 | )x2 C#3/8 G#3/8 B3/8 E4/8 B3/8 G#3/8 | G#2/8 D#3/8 G#3/8 C4/8 G#3/8 D#3/8 |
harmony: ( G#2/8 D#3/8 G#3/8 C4/8 G#3/8 D#3/8 | )x2 E3/8 G#3/8 C4/8 E4/8 C4/8 G#3/8 | G#2/8 D#3/8 G#3/8 C4/8 G#3/8 D#3/8 |
harmony: ( G#2/8 D#3/8 G#3/8 C4/8 G#3/8 D#3/8 | )x2 G#2/8 C#3/8 E3/8 G#3/8 E3/8 C#3/8 | B2/8 F#3/8 B3/8 D#4/8 B3/8 F#3/8 |
harmony: ( E3/8 B3/8 E4/8 G#4/8 E4/8 B3/8 | )x2 C#3/8 G#3/8 B3/8 E4/8 B3/8 G#3/8 | E3/8 B3/8 E4/8 G#4/8 E4/8 B3/8 | E3+G#3+B3/2. |
bass triangle legato: E2/2. | E2/2. | C#2/2. | E2/2. | E2/2. | E2/2. | C#2/2. | G#2/2. |
bass: G#2/2. | G#2/2. | E2/2. | G#2/2. | G#2/2. | G#2/2. | G#2/2. | B2/2. |
bass: E2/2. | E2/2. | C#2/2. | E2/2. | E2/2. |
"""},
    "twinkle": {
        "title": "Twinkle, Twinkle, Little Star", "composer": "Traditional French", "year": 1761,
        "fact": "The tune is French, from 1761; Mozart wrote twelve variations on it, and it is "
                "also the tune of the ABC song.",
        "aliases": ["twinkle twinkle", "twinkle twinkle little star", "little star", "abc song",
                    "ah vous dirai je maman"],
        "score": """
tempo 112
time 4/4
lead pulse25: C5/4 C5/4 G5/4 G5/4 | A5/4 A5/4 G5/2 | F5/4 F5/4 E5/4 E5/4 | D5/4 D5/4 C5/2 |
lead: G5/4 G5/4 F5/4 F5/4 | E5/4 E5/4 D5/2 | G5/4 G5/4 F5/4 F5/4 | E5/4 E5/4 D5/2 |
lead: C5/4 C5/4 G5/4 G5/4 | A5/4 A5/4 G5/2 | F5/4 F5/4 E5/4 E5/4 | D5/4 D5/4 C5/2 |
harmony pulse12: C4/8 E4/8 G4/8 E4/8 C4/8 E4/8 G4/8 E4/8 | C4/8 F4/8 A4/8 F4/8 C4/8 E4/8 G4/8 E4/8 | C4/8 F4/8 A4/8 F4/8 C4/8 E4/8 G4/8 E4/8 | B3/8 D4/8 G4/8 D4/8 C4/8 E4/8 G4/8 E4/8 |
harmony: ( C4/8 E4/8 G4/8 E4/8 C4/8 F4/8 A4/8 F4/8 | C4/8 E4/8 G4/8 E4/8 B3/8 D4/8 G4/8 D4/8 | )x2
harmony: C4/8 E4/8 G4/8 E4/8 C4/8 E4/8 G4/8 E4/8 | C4/8 F4/8 A4/8 F4/8 C4/8 E4/8 G4/8 E4/8 | C4/8 F4/8 A4/8 F4/8 C4/8 E4/8 G4/8 E4/8 | B3/8 D4/8 G4/8 D4/8 C4+E4+G4/2 |
bass triangle: C3/2 G2/2 | F2/2 C3/2 | F2/2 C3/2 | G2/2 C3/2 |
bass: ( C3/2 F2/2 | C3/2 G2/2 | )x2
bass: C3/2 G2/2 | F2/2 C3/2 | F2/2 C3/2 | G2/2 C3/2 |
"""},
    "jingle-bells": {
        "title": "Jingle Bells", "composer": "James Lord Pierpont", "year": 1857,
        "fact": "In December 1965 two astronauts on Gemini 6 played it on a harmonica and sleigh "
                "bells: the first song played in space.",
        "aliases": ["jingle bells", "jingle", "dashing through the snow"],
        "score": """
tempo 200
time 4/4
lead pulse25: G4/4 E5/4 D5/4 C5/4 | G4/2. G4/8 G4/8 | G4/4 E5/4 D5/4 C5/4 | A4/1 | A4/4 F5/4 E5/4 D5/4 | B4/1 | G5/4 G5/4 F5/4 D5/4 | E5/1 |
lead: G4/4 E5/4 D5/4 C5/4 | G4/1 | G4/4 E5/4 D5/4 C5/4 | A4/1 | A4/4 F5/4 E5/4 D5/4 | G5/4 G5/4 G5/4. G5/8 | A5/4 G5/4 F5/4 D5/4 | C5/2 G5/2 |
lead: E5/4 E5/4 E5/2 | E5/4 E5/4 E5/2 | E5/4 G5/4 C5/4. D5/8 | E5/1 | F5/4 F5/4 F5/4. F5/8 | F5/4 E5/4 E5/4 E5/8 E5/8 | E5/4 D5/4 D5/4 E5/4 | D5/2 G5/2 |
lead: E5/4 E5/4 E5/2 | E5/4 E5/4 E5/2 | E5/4 G5/4 C5/4. D5/8 | E5/1 | F5/4 F5/4 F5/4. F5/8 | F5/4 E5/4 E5/4 E5/8 E5/8 | G5/4 G5/4 F5/4 D5/4 | C5/2 r/2 |
harmony pulse12 staccato: ( r/4 C4+E4+G4/4 r/4 C4+E4+G4/4 | )x3 r/4 C4+F4+A4/4 r/4 C4+F4+A4/4 | r/4 D4+F4+A4/4 r/4 D4+F4+A4/4 | r/4 B3+D4+G4/4 r/4 B3+D4+G4/4 | r/4 B3+D4+F4/4 r/4 B3+D4+F4/4 | r/4 C4+E4+G4/4 r/4 C4+E4+G4/4 |
harmony: ( r/4 C4+E4+G4/4 r/4 C4+E4+G4/4 | )x2 r/4 C4+E4+G4/4 r/4 Bb3+E4+G4/4 | r/4 C4+F4+A4/4 r/4 C4+F4+A4/4 | r/4 D4+F4+A4/4 r/4 D4+F4+A4/4 | r/4 B3+D4+G4/4 r/4 B3+D4+G4/4 | r/4 B3+D4+F4/4 r/4 B3+D4+F4/4 | r/4 C4+E4+G4/4 r/4 B3+D4+F4/4 |
harmony: ( r/4 C4+E4+G4/4 r/4 C4+E4+G4/4 | )x2 r/4 A3+C4+E4/4 r/4 B3+D4+G4/4 | r/4 C4+E4+G4/4 r/4 Bb3+E4+G4/4 | r/4 C4+F4+A4/4 r/4 C4+F4+A4/4 | r/4 C4+E4+G4/4 r/4 C4+E4+G4/4 | r/4 A3+C4+F#4/4 r/4 A3+C4+F#4/4 | r/4 B3+D4+F4/4 r/4 B3+D4+F4/4 |
harmony: ( r/4 C4+E4+G4/4 r/4 C4+E4+G4/4 | )x2 r/4 A3+C4+E4/4 r/4 B3+D4+F4/4 | r/4 C4+E4+G4/4 r/4 Bb3+E4+G4/4 | r/4 C4+F4+A4/4 r/4 C4+F4+A4/4 | r/4 C4+E4+G4/4 r/4 C4+E4+G4/4 | r/4 B3+D4+F4/4 r/4 B3+D4+F4/4 | C4+E4+G4/4 r/4 r/2 |
bass triangle: C3/2 G2/2 | C3/2 G2/2 | C3/2 D3/4 E3/4 | F3/2 E3/2 | D3/2 A2/2 | G2/2 B2/2 | G2/2 A2/4 B2/4 | C3/4 B2/4 A2/4 G2/4 |
bass: C3/2 G2/2 | C3/2 G2/2 | C3/2 D3/4 E3/4 | F3/2 E3/2 | D3/2 C3/2 | B2/2 A2/2 | G2/2 A2/4 B2/4 | C3/2 G2/2 |
bass: C3/2 B2/2 | A2/2 G2/2 | A2/2 G2/2 | C3/2 Bb2/2 | A2/2 F2/2 | C3/2 G2/2 | D3/2 F#3/2 | G3/4 F3/4 E3/4 D3/4 |
bass: C3/2 B2/2 | A2/2 G2/2 | A2/2 G2/2 | C3/2 Bb2/2 | A2/2 F2/2 | C3/2 G2/2 | B2/2 G2/2 | C3/2 r/2 |
drums: ( h/4 h/4 h/4 h/4 | )x16 ( k/8 o/8 s/8 o/8 k/8 o/8 s/8 o/8 | )x15 k+c/4 r/4 r/2 |
"""},
    "auld-lang-syne": {
        "title": "Auld Lang Syne", "composer": "Traditional Scottish (words by Robert Burns)",
        "year": 1788,
        "fact": "Robert Burns wrote down the old words in 1788; 'auld lang syne' means 'old long "
                "since', or 'days gone by'.",
        "aliases": ["auld lang syne", "new year", "new years", "new year's song", "old lang syne"],
        "score": """
tempo 92
time 4/4
lead pulse25 echo: C5/4 | F5/4. F5/8 F5/4 A5/4 | G5/4. F5/8 G5/4 A5/4 | F5/4. F5/8 A5/4 C6/4 | D6/2. D6/4 |
lead: C6/4. A5/8 A5/4 F5/4 | G5/4. F5/8 G5/4 A5/4 | F5/4. D5/8 D5/4 C5/4 | F5/2. D6/4 |
lead: C6/4. A5/8 A5/4 F5/4 | G5/4. F5/8 G5/4 D6/4 | C6/4. A5/8 A5/4 C6/4 | D6/2. D6/4 |
lead: C6/4. A5/8 A5/4 F5/4 | G5/4. F5/8 G5/4 A5/4 | F5/4. D5/8 D5/4 C5/4 | F5/2. |
harmony pulse12 legato: r/4 | A3+C4+F4/1 | G3+Bb3+E4/1 | A3+C4+F4/1 | Bb3+D4+F4/1 | A3+C4+F4/1 | G3+Bb3+E4/1 | Bb3+D4+F4/2 G3+Bb3+E4/2 | A3+C4+F4/1 |
harmony: A3+C4+F4/1 | G3+Bb3+E4/1 | A3+C4+F4/1 | Bb3+D4+F4/1 | A3+C4+F4/1 | G3+Bb3+E4/1 | Bb3+D4+F4/2 G3+Bb3+E4/2 | A3+C4+F4/2. |
bass triangle: r/4 | F2/2 C3/2 | C3/2 G2/2 | F2/2 C3/2 | Bb2/2 F2/2 | F2/2 C3/2 | C3/2 G2/2 | Bb2/2 C3/2 | F2/2 C2/2 |
bass: F2/2 C3/2 | C3/2 G2/2 | F2/2 C3/2 | Bb2/2 F2/2 | F2/2 C3/2 | C3/2 G2/2 | Bb2/2 C3/2 | F2/2. |
"""},
    "take-me-out": {
        "title": "Take Me Out to the Ball Game", "composer": "Albert Von Tilzer and Jack Norworth",
        "year": 1908,
        "fact": "Neither of the men who wrote it had ever been to a baseball game.",
        "aliases": ["take me out to the ball game", "take me out to the ballgame", "ball game",
                    "ballgame", "baseball", "take me out"],
        "score": """
tempo 176
time 3/4
lead pulse50: C5/2 C6/4 | A5/4 G5/4 E5/4 | G5/2. | D5/2. | C5/2 C6/4 | A5/4 G5/4 E5/4 | G5/2.~ | G5/2. |
lead: A5/4 G#5/4 A5/4 | E5/4 F5/4 G5/4 | A5/2 F5/4 | D5/2. | A5/2 A5/4 | A5/4 B5/4 C6/4 | D6/4 B5/4 A5/4 | G5/4 E5/4 D5/4 |
lead: C5/2 C6/4 | A5/4 G5/4 E5/4 | G5/2. | D5/2 E5/4 | C5/2 D5/4 | E5/4 F5/4 G5/4 | A5/2.~ | A5/4 A5/4 B5/4 |
lead: C6/4 r/2 | C6/4 r/2 | C6/4 B5/4 A5/4 | G5/4 F#5/4 G5/4 | A5/2. | B5/2. | C6/2.~ | C6/4 r/2 |
harmony pulse12 staccato: r/4 C4+E4+G4/4 C4+E4+G4/4 | r/4 A3+C4+E4/4 A3+C4+E4/4 | ( r/4 B3+D4+F4/4 B3+D4+F4/4 | )x2 r/4 C4+E4+G4/4 C4+E4+G4/4 | r/4 A3+C4+E4/4 A3+C4+E4/4 | ( r/4 B3+D4+G4/4 B3+D4+G4/4 | )x2
harmony: ( r/4 C#4+E4+G4/4 C#4+E4+G4/4 | )x2 ( r/4 D4+F4+A4/4 D4+F4+A4/4 | )x2 ( r/4 A3+C4+F#4/4 A3+C4+F#4/4 | )x2 ( r/4 B3+D4+G4/4 B3+D4+G4/4 | )x2
harmony: r/4 C4+E4+G4/4 C4+E4+G4/4 | r/4 A3+C4+E4/4 A3+C4+E4/4 | ( r/4 B3+D4+F4/4 B3+D4+F4/4 | )x2 r/4 C4+E4+G4/4 C4+E4+G4/4 | r/4 Bb3+E4+G4/4 Bb3+E4+G4/4 | ( r/4 C4+F4+A4/4 C4+F4+A4/4 | )x2
harmony: r/4 C4+F4+A4/4 C4+F4+A4/4 | r/4 A3+C4+F#4/4 A3+C4+F#4/4 | r/4 B3+D4+G4/4 B3+D4+G4/4 | r/4 C#4+E4+G4/4 C#4+E4+G4/4 | r/4 D4+F4+A4/4 D4+F4+A4/4 | r/4 B3+D4+F4/4 B3+D4+F4/4 | r/4 C4+E4+G4/4 C4+E4+G4/4 | C4+E4+G4/4 r/2 |
bass triangle: C3/4 r/2 | A2/4 r/2 | G2/4 r/2 | D3/4 r/2 | C3/4 r/2 | A2/4 r/2 | G2/4 r/2 | D3/4 r/2 |
bass: A2/4 r/2 | E2/4 r/2 | D3/4 r/2 | A2/4 r/2 | D3/4 r/2 | A2/4 r/2 | G2/4 r/2 | D3/4 r/2 |
bass: C3/4 r/2 | A2/4 r/2 | G2/4 r/2 | D3/4 r/2 | C3/4 r/2 | C3/4 r/2 | F2/4 r/2 | C3/4 r/2 |
bass: F2/4 r/2 | F#2/4 r/2 | G2/4 r/2 | A2/4 r/2 | D3/4 r/2 | G2/4 r/2 | C3/4 r/2 | C3/4 r/2 |
drums: ( k/4 h/4 h/4 | )x31 k+c/4 r/2 |
"""},
}

for _id, _entry in TUNES.items():
    _entry["id"] = _id


# The two songs PAL sings. Lyrics: 'word:note/length', spelt the way
# espeak-ng says them right; '{name}' is the birthday person. Sung two
# octaves below the instrumentals, in a baritone's range, in D major.
SONGS = {
    "daisy": {
        "title": "Daisy Bell",
        "lyrics": """
day:A3/2. zee:F#3/2. day:D3/2. zee:A2/2. give:B2/4 me:C#3/4 your:D3/4 an:B2/2 sir:D3/4 doo:A2/2. A2/2 r/4
I'm:E3/2. half:A3/2. cray:F#3/2. zee:D3/2. all:B2/4 for:C#3/4 the:D3/4 love:E3/2 of:F#3/4 you:E3/2. E3/4 r/4 it:F#3/4
won't:G3/4 be:F#3/4 uh:E3/4 sty:A3/2 lish:F#3/4 mare:E3/4 ridge:D3/2 D3/4 r/4 I:E3/4
can't:F#3/2 uh:D3/4 ford:B2/2 uh:D3/4 care:B2/4 ridge:A2/2 A2/4 r/4 but:A2/4
you'll:D3/2 look:F#3/4 sweet:E3/2 up:A2/4 on:D3/2 the:F#3/4 seat:E3/2 of:F#3/8 uh:G3/8
bye:A3/4 sick:F#3/4 cull:D3/4 built:E3/2 for:A2/4 two:D3/2. D3/2 r/4
""",
        "accompaniment": """
tempo 126
time 3/4
harmony pulse12 staccato: ( r/4 D4+F#4+A4/4 D4+F#4+A4/4 | )x4 ( r/4 D4+G4+B4/4 D4+G4+B4/4 | )x2 ( r/4 D4+F#4+A4/4 D4+F#4+A4/4 | )x2
harmony: ( r/4 C#4+E4+G4/4 C#4+E4+G4/4 | )x2 ( r/4 D4+F#4+A4/4 D4+F#4+A4/4 | )x2 ( r/4 D4+E4+G#4/4 D4+E4+G#4/4 | )x2 ( r/4 C#4+E4+A4/4 C#4+E4+A4/4 | )x2
harmony: ( r/4 C#4+E4+G4/4 C#4+E4+G4/4 | )x2 ( r/4 D4+F#4+A4/4 D4+F#4+A4/4 | )x2 r/4 D4+F#4+B4/4 D4+F#4+B4/4 | r/4 D4+G4+B4/4 D4+G4+B4/4 | ( r/4 D4+F#4+A4/4 D4+F#4+A4/4 | )x2
harmony: ( r/4 D4+F#4+A4/4 D4+F#4+A4/4 | r/4 C#4+E4+G4/4 C#4+E4+G4/4 | )x3 r/4 D4+F#4+A4/4 D4+F#4+A4/4 | r/2. |
bass triangle: D2/4 r/2 | A2/4 r/2 | D2/4 r/2 | A2/4 r/2 | G2/4 r/2 | D2/4 r/2 | D2/4 r/2 | A2/4 r/2 |
bass: A2/4 r/2 | E2/4 r/2 | D2/4 r/2 | A2/4 r/2 | E2/4 r/2 | B2/4 r/2 | A2/4 r/2 | E2/4 r/2 |
bass: A2/4 r/2 | E2/4 r/2 | D2/4 r/2 | A2/4 r/2 | B2/4 r/2 | G2/4 r/2 | D2/4 r/2 | A2/4 r/2 |
bass: D2/4 r/2 | A2/4 r/2 | D2/4 r/2 | A2/4 r/2 | D2/4 r/2 | A2/4 r/2 | D2/2. | D2/4 r/2 |
"""},
    "birthday": {
        "title": "Happy Birthday to You",
        "lyrics": """
hap:A2/8. pee:A2/16 birth:B2/4 day:A2/4 to:D3/4 you:C#3/2
hap:A2/8. pee:A2/16 birth:B2/4 day:A2/4 to:E3/4 you:D3/2
hap:A2/8. pee:A2/16 birth:A3/4 day:F#3/4 dear:D3/4 {name}:C#3/4 B2/2
hap:G3/8. pee:G3/16 birth:F#3/4 day:D3/4 to:E3/4 you:D3/2.
""",
        "accompaniment": """
tempo 100
time 3/4
harmony pulse12 staccato: r/4 | r/4 D4+F#4+A4/4 D4+F#4+A4/4 | ( r/4 C#4+E4+G4/4 C#4+E4+G4/4 | )x2 r/4 D4+F#4+A4/4 D4+F#4+A4/4 |
harmony: r/4 C4+F#4+A4/4 C4+F#4+A4/4 | r/4 D4+G4+B4/4 D4+G4+B4/4 | r/4 | r/4 D4+F#4+A4/4 C#4+E4+G4/4 | D4+F#4+A4/2. |
bass triangle: r/4 | D2/4 r/2 | A2/4 r/2 | E2/4 r/2 | D2/4 r/2 | D2/4 r/2 | @84 G2/4 r/2 | r/4 | @92 A2/4 r/4 A2/4 | @80 D2/2. |
"""},
}

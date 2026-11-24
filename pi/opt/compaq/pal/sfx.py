"""PAL's sound effects, made on the spot from sine waves and noise (no
recordings): the PC's power-on beep, a disk drive's head ticking when PAL
has heard someone out, a floppy drive seeking while PAL thinks, and a
dial-up modem connecting while it searches the web.
Each function returns WAV bytes."""

import io
import wave

import numpy as np

RATE = 22050


def to_wav(samples):
    samples = np.clip(samples, -1, 1)
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(RATE)
        w.writeframes((samples * 32767).astype(np.int16).tobytes())
    return buffer.getvalue()


def t(seconds):
    return np.arange(int(RATE * seconds)) / RATE


def sine(freq, seconds, volume=0.3):
    return volume * np.sin(2 * np.pi * freq * t(seconds))


def square(freq, seconds, volume=0.2):
    return volume * np.sign(np.sin(2 * np.pi * freq * t(seconds)))


def silence(seconds):
    return np.zeros(int(RATE * seconds))


def fade(samples, seconds=0.01):
    """Soft edges, so tones don't click."""
    n = min(len(samples) // 2, int(RATE * seconds))
    if n:
        ramp = np.linspace(0, 1, n)
        samples[:n] *= ramp
        samples[-n:] *= ramp[::-1]
    return samples


def post_beep():
    """The short beep an IBM-compatible PC makes when it passes its power-on test."""
    return to_wav(fade(square(990, 0.22, 0.25)))


def shutter():
    """A camera click, for the photo booth."""
    rng = np.random.default_rng()
    click = rng.normal(0, 0.6, int(RATE * 0.012)) * np.exp(-np.linspace(0, 5, int(RATE * 0.012)))
    return to_wav(np.concatenate([click, silence(0.06), click * 0.7]))


def heard():
    """Three ticks of a drive's head stepping: "got it". When PAL is waiting
    on someone, the moment they stop talking (Whisper then takes 2 or 3
    seconds); otherwise as soon as Whisper finds "Hey PAL" in what it
    heard (Claude's first words take another second or two). A moment of
    silence comes first: a TV's HDMI sound takes a few tenths of a second
    to wake, and would swallow a sound this short whole."""
    rng = np.random.default_rng(5)
    n = int(RATE * 0.006)
    tick = rng.normal(0, 0.6, n) * np.exp(-np.linspace(0, 5, n))
    return to_wav(np.concatenate([silence(0.4), tick, silence(0.035), tick * 0.8, silence(0.035),
                                  tick * 0.65, silence(0.02)]))


def floppy():
    """A 5.25-inch drive: the head stepping across tracks, then a spin."""
    rng = np.random.default_rng()
    parts = []
    for _ in range(rng.integers(6, 12)):
        click = rng.normal(0, 0.5, int(RATE * 0.004)) * np.exp(-np.linspace(0, 6, int(RATE * 0.004)))
        parts += [click, silence(rng.uniform(0.02, 0.05))]
    hum = square(85, 0.5, 0.06) + rng.normal(0, 0.03, int(RATE * 0.5))
    hum *= 0.6 + 0.4 * np.sin(2 * np.pi * 7 * t(0.5))
    parts += [fade(hum, 0.05)]
    for _ in range(4):
        click = rng.normal(0, 0.4, int(RATE * 0.004))
        parts += [click, silence(0.03)]
    return to_wav(np.concatenate(parts))


def modem():
    """A dial-up modem: dial tone, touch-tone dialling, then the handshake
    screech, cut short (about 3 seconds; nobody misses the full minute)."""
    rng = np.random.default_rng()
    dtmf = {"5": (770, 1336), "5b": (770, 1336), "1": (697, 1209), "2": (697, 1336),
            "8": (852, 1336), "7": (852, 1209), "0": (941, 1336), "4": (770, 1209)}
    parts = [fade(sine(350, 0.35, 0.15) + sine(440, 0.35, 0.15))]
    for digit in "5551204":
        low, high = dtmf[digit]
        parts += [fade(sine(low, 0.07, 0.15) + sine(high, 0.07, 0.15)), silence(0.04)]
    parts += [silence(0.15), fade(sine(2100, 0.45, 0.2)), silence(0.05)]
    # The screech: tones warbling between 1200 and 2400 Hz, then noise.
    steps = np.arange(int(RATE * 0.8))
    freq = 1800 + 600 * np.sign(np.sin(2 * np.pi * 9 * steps / RATE))
    parts.append(fade(0.18 * np.sin(np.cumsum(2 * np.pi * freq / RATE))))
    hiss = rng.normal(0, 0.12, int(RATE * 0.6)) * (0.6 + 0.4 * np.sin(2 * np.pi * 30 * t(0.6)))
    parts.append(fade(hiss, 0.05))
    return to_wav(np.concatenate(parts))


def seconds(wav_bytes):
    with wave.open(io.BytesIO(wav_bytes)) as w:
        return w.getnframes() / w.getframerate()

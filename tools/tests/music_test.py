"""Tests PAL's music module (pi/opt/compaq/pal/music.py) on the Pi.

On the Mac:   python3 music_test.py
    Copies music.py and this script into a fresh temporary folder on the Pi
    (ssh pizero), runs the tests there, copies some WAVs back to
    ~/Desktop/Compaq/PAL voice samples/music/, then deletes the folder.
On the Pi:    python3 -I music_test.py --here OUTDIR   (what the Mac runs)

Nothing is played aloud, nothing needs sudo, and nothing outside the
temporary folder is touched.
"""

import os
import subprocess
import sys
import time

# (wherever the project folder is: this file is in compaq-pi/tools/tests)
PROJECT = os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
MUSIC = os.path.join(PROJECT, "compaq-pi/pi/opt/compaq/pal/music.py")
SAMPLES = os.path.join(PROJECT, "PAL voice samples/music")
KEEP = {  # file name -> what to render
    "daisy-sung.wav": ("sing", "daisy", None),
    "birthday-sung-joe.wav": ("sing", "birthday", "Joe"),
    "the-entertainer.wav": ("tune", "the-entertainer", None),
    "mountain-king.wav": ("tune", "mountain-king", None),
    "fur-elise.wav": ("tune", "fur-elise", None),
    "william-tell.wav": ("tune", "william-tell", None),
    "marionette.wav": ("tune", "marionette", None),
    "can-can.wav": ("tune", "can-can", None),
    "morning-mood.wav": ("tune", "morning-mood", None),
}


# ------------------------------------------------------------------ on the Mac

def mac():
    here = os.path.abspath(__file__)
    folder = subprocess.run(["ssh", "pizero", "mktemp -d /tmp/palmusic-test.XXXXXX"],
                            capture_output=True, text=True, check=True).stdout.strip()
    assert folder.startswith("/tmp/palmusic-test."), folder
    print("Pi folder:", folder, flush=True)
    try:
        subprocess.run(["scp", "-q", MUSIC, here, f"pizero:{folder}/"], check=True)
        result = subprocess.run(["ssh", "pizero", f"cd {folder} && python3 -I music_test.py "
                                 f"--here {folder}/out"])
        os.makedirs(SAMPLES, exist_ok=True)
        subprocess.run(["scp", "-q", *[f"pizero:{folder}/out/{name}" for name in KEEP], SAMPLES + "/"],
                       check=True)
        print(f"\nCopied {len(KEEP)} WAVs to {SAMPLES}")
        return result.returncode
    finally:
        subprocess.run(["ssh", "pizero", f"rm -rf {folder}"], check=True)
        print("Removed", folder, "from the Pi")


# ------------------------------------------------------------------ on the Pi

def pitch(x, rate):
    """An independent pitch measurement (not music.py's): the strongest
    plain autocorrelation peak between 60 and 450 Hz, preferring the
    shortest lag that is nearly as strong (so it can't land an octave low)."""
    import numpy as np
    x = x - x.mean()
    n = len(x)
    ac = np.fft.irfft(np.abs(np.fft.rfft(x, 2 * n)) ** 2)[:n]
    ac /= ac[0] * (n - np.arange(n)) / n + 1e-12          # unbiased
    lo, hi = int(rate / 450), int(rate / 60)
    seg = ac[lo:hi]
    k = int(np.argmax(seg >= 0.92 * seg.max())) + lo
    k += int(np.argmax(ac[k:k + k // 4 + 2]))
    a, b, c = ac[k - 1], ac[k], ac[k + 1]
    k = k + 0.5 * (a - c) / (a - 2 * b + c) if a - 2 * b + c else k
    return rate / k


def pi(out):
    import io
    import wave
    import numpy as np
    sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
    import music

    os.makedirs(out, exist_ok=True)
    problems = []

    def problem(text):
        problems.append(text)
        print("  PROBLEM:", text)

    def info(wav):
        with wave.open(io.BytesIO(wav)) as w:
            assert (w.getnchannels(), w.getsampwidth(), w.getframerate()) == (1, 2, 22050)
            x = np.frombuffer(w.readframes(w.getnframes()), "<i2").astype(float) / 32768
        return x

    print("== Compose guide")
    words = len(music.COMPOSE_GUIDE.split())
    print(f"  {words} words")
    if words >= 250:
        problem(f"COMPOSE_GUIDE has {words} words")
    example = music.COMPOSE_GUIDE.split("\n\n")[1]
    tune = music.parse(example)
    print(f"  its example parses: {len(tune.parts)} voices, {tune.length:.1f} s")

    print("\n== Library (strict parse, render on the Pi)")
    print(f"  {'id':20s} {'voices':7s} {'length':>7s} {'render':>7s}  title")
    times = {}
    for tune_id, entry in music.TUNES.items():
        for field in ("id", "title", "composer", "year", "fact", "score"):
            if field not in entry:
                problem(f"{tune_id}: no {field}")
        try:
            start = time.perf_counter()
            tune = music.parse(entry["score"], strict=True)
            wav, timeline = music.render(tune)
            took = time.perf_counter() - start
        except Exception as e:  # noqa: BLE001 - report every failure
            problem(f"{tune_id}: {type(e).__name__}: {e}")
            continue
        x = info(wav)
        length = len(x) / 22050
        times[tune_id] = (length, took, len(tune.parts))
        ends = {name: float(p.beats) for name, p in tune.parts.items()}
        print(f"  {tune_id:20s} {len(tune.parts):<7d} {length:6.1f}s {took:6.2f}s  {entry['title']}")
        if len(set(round(e, 6) for e in ends.values())) > 1:
            problem(f"{tune_id}: voices end at different beats {ends}")
        if not 20 <= tune.length <= 45:
            problem(f"{tune_id}: lasts {tune.length:.1f} s (want 20-45)")
        if not np.isfinite(x).all() or np.max(np.abs(x)) < 0.5:
            problem(f"{tune_id}: bad samples")
        if abs(x[0]) > 0.01 or abs(x[-1]) > 0.01:
            problem(f"{tune_id}: starts or ends with a click")
        if any(a[0] > b[0] for a, b in zip(timeline, timeline[1:])) or \
                any(s + d > length + 0.01 for s, d, _, _ in timeline):
            problem(f"{tune_id}: timeline out of order or too long")
        if tune_id in [v[1] for v in KEEP.values() if v[0] == "tune"]:
            name = [k for k, v in KEEP.items() if v[1] == tune_id][0]
            with open(os.path.join(out, name), "wb") as f:
                f.write(wav)
    if times:
        slowest = max(times.items(), key=lambda t: t[1][1])
        print(f"  slowest: {slowest[0]} ({slowest[1][0]:.1f} s of music in {slowest[1][1]:.2f} s)")

    print("\n== A dense 45-second, 4-voice tune (worst case)")
    dense = ("tempo 150\ntime 4/4\n"
             "lead pulse25 echo: ( C5/16 E5/16 G5/16 C6/16 B5/16 G5/16 E5/16 D5/16 A5/8 F5/8 G5/4 | )x28\n"
             "harmony pulse12: ( C4+E4+G4/8 r/8 A3+C4+E4/8 r/8 F3+A3+C4/8 r/8 G3+B3+D4/8 r/8 | )x28\n"
             "bass triangle: ( C3/8 C2/8 A2/8 A1/8 F2/8 F1/8 G2/8 G1/8 | )x28\n"
             "drums: ( k/8 h/8 s/8 h/8 k+h/8 h/8 s/8 o/8 | )x28\n")
    start = time.perf_counter()
    wav, timeline = music.render(dense)
    took = time.perf_counter() - start
    print(f"  {music.seconds(wav):.1f} s of music, {len(timeline)} notes, rendered in {took:.2f} s")
    if took > 3:
        problem(f"dense tune took {took:.2f} s")

    print("\n== find()")
    for request, wanted in [
            ("play fur elise", "fur-elise"), ("Play Für Elise please", "fur-elise"),
            ("for elise", "fur-elise"), ("the entertainer", "the-entertainer"),
            ("mountain king", "mountain-king"), ("in the hall of the mountain king", "mountain-king"),
            ("william tell", "william-tell"), ("can you play the can-can", "can-can"),
            ("cancan", "can-can"), ("play happy birthday", "happy-birthday"),
            ("daisy", "daisy-bell"), ("a bicycle built for two", "daisy-bell"),
            ("ode to joy", "ode-to-joy"), ("pachelbel's canon", "pachelbel-canon"),
            ("canon in d", "pachelbel-canon"), ("minuet in g", "minuet-in-g"),
            ("greensleeves", "greensleeves"), ("turkish march", "rondo-alla-turca"),
            ("rondo alla turca", "rondo-alla-turca"), ("funeral march of a marionette", "marionette"),
            ("habanera from carmen", "habanera"), ("the blue danube", "blue-danube"),
            ("morning mood", "morning-mood"), ("good morning", None), ("play some beethoven", "fur-elise"), ("beethovens ninth", "ode-to-joy"), ("something by mozart", "rondo-alla-turca"), ("twinkle twinkle little star", "twinkle"),
            ("jingle bells", "jingle-bells"), ("auld lang syne", "auld-lang-syne"),
            ("take me out to the ballgame", "take-me-out"), ("maple leaf rag", "maple-leaf-rag"),
            ("play the maple leaf", "maple-leaf-rag"), ("mountain kin", "mountain-king"),
            ("entertaner", "the-entertainer"), ("play something", None), ("the weather", None),
            ("", None), ("march", None)]:
        got = music.find(request)
        mark = "ok" if got == wanted else "WRONG"
        print(f"  {mark:5s} {request!r:38s} -> {got}")
        if got != wanted:
            problem(f"find({request!r}) gave {got}, wanted {wanted}")

    print("\n== Bad input gives clear errors")
    bad = {
        "not a tune": "hello there",
        "unknown voice": "tempo 120\nguitar: C4/4",
        "bad note": "lead: H5/4 C5/4",
        "bad length": "lead: C5/3",
        "bad tempo": "tempo 900\nlead: C5/4",
        "short bar": "time 4/4\nlead: C5/4 C5/4 C5/4 C5/4 | C5/4 C5/4 C5/4 | C5/1 |",
        "long bar": "time 3/4\nlead: C5/2 D5/2 |",
        "drum note in lead": "lead: k/4",
        "note in drums": "drums: C4/4",
        "noise on lead": "lead noise: C5/4",
        "open repeat": "lead: ( C5/4 D5/4",
        "huge repeat": "lead: ( C5/4 )x99",
        "out of range": "lead: C9/4",
        "empty": "",
        "only rests": "lead: r/1 r/1",
        "too long": "lead: " + "C5/4 " * 6000,
    }
    for label, text in bad.items():
        try:
            music.parse(text)
            problem(f"{label}: no error")
        except ValueError as e:
            print(f"  {label:18s} ValueError: {e}")
    print("\n== Forgiving where it's harmless")
    for label, text in {
            "no bar lines at all": "time 4/4\nlead: C5/4 D5/4 E5/4 F5/4 G5/2 G5/2 A5/1",
            "tie written apart": "lead: C5/2 ~ C5/2 | D5/1 |",
            "chatty headers": "```\nTitle: My Tune\nTempo: 140 bpm\nTime signature: 3/4\nKey: C major\n"
                              "Lead (pulse25): C5/4 E5/4 G5/4 | C6/2. |\nBass: C3/2. | C3/2. |\n```",
            "lowercase notes": "lead: c5/4 eb5/4 g5/2 |",
            "slur to another note": "lead: C5/4~ D5/4 E5/2 |"}.items():
        tune = music.parse(text)
        print(f"  {label:22s} ok: {sum(len(p.notes) for p in tune.parts.values())} notes, "
              f"{tune.tempo:.0f} bpm, {tune.time[0]}/{tune.time[1]}")
    # The bar check can be switched off, and a tune can be text or a Tune.
    music.render(music.parse("time 4/4\nlead: C5/4 C5/4 C5/4 | C5/1 |", strict=False))
    long_tune = music.parse("tempo 120\nlead: ( C5/4 E5/4 G5/4 C6/4 | )x16 ( C5/4 E5/4 G5/4 C6/4 | )x16")
    wav, timeline = music.render(long_tune)
    print(f"  a 64-second tune is cut to {music.seconds(wav):.1f} s (truncated={long_tune.truncated})")
    if music.seconds(wav) > 60.5:
        problem("long tune not cut at 60 s")

    print("\n== Singing")
    for song, name in (("daisy", None), ("birthday", "Joe")):
        start = time.perf_counter()
        wav, timeline = music.sing(song, name=name)
        took = time.perf_counter() - start
        print(f"  {song}{' for ' + name if name else ''}: {music.seconds(wav):.1f} s, "
              f"rendered in {took:.2f} s, {len(timeline)} timeline entries")
        target = [k for k, v in KEEP.items() if v[0] == "sing" and v[1] == song][0]
        with open(os.path.join(out, target), "wb") as f:
            f.write(wav)
        # The voice alone, to measure each sung note's pitch.
        voice, notes = music.sing(song, name=name, accompaniment=False)
        x = info(voice)
        errors, measured, skipped = [], [], 0
        for start_s, length, midi, who in notes:
            # The steady middle of the note, clear of the next syllable's
            # consonant, which starts up to 70 ms early.
            a = int((start_s + 0.25 * length) * 22050)
            b = int(min(start_s + 0.9 * length, start_s + length - 0.075) * 22050)
            if b - a < 0.04 * 22050:
                skipped += 1
                continue
            want = 440 * 2 ** ((midi - 69) / 12)
            got = pitch(x[a:b], 22050)
            errors.append(1200 * np.log2(got / want))
            measured.append((start_s, midi))
        errors = np.array(errors)
        if skipped:
            print(f"    ({skipped} notes too short to measure)")
        within = np.mean(np.abs(errors) <= 100) * 100
        print(f"    {len(errors)} notes: pitch error median {np.median(np.abs(errors)):.0f} cents, "
              f"worst {np.max(np.abs(errors)):.0f} cents, {within:.0f}% within a semitone")
        worst = np.argsort(-np.abs(errors))[:3]
        for i in worst:
            s, midi = measured[i]
            print(f"      at {s:5.2f}s MIDI {midi}: {errors[i]:+.0f} cents")
        if within < 90:
            problem(f"{song}: only {within:.0f}% of notes within a semitone")
    for name in ("Austin", "Mary Elizabeth", "<script>", "José", ""):
        wav, _ = music.sing("birthday", name=name)
        print(f"  birthday for {name!r}: {music.seconds(wav):.1f} s")
    try:
        music.sing("bohemian rhapsody")
        problem("unknown song: no error")
    except ValueError as e:
        print(f"  unknown song: ValueError: {e}")

    print("\n== Summary")
    print("  all good" if not problems else f"  {len(problems)} problem(s):\n    " +
          "\n    ".join(problems))
    return 1 if problems else 0


if __name__ == "__main__":
    if len(sys.argv) == 3 and sys.argv[1] == "--here":
        sys.exit(pi(sys.argv[2]))
    sys.exit(mac())

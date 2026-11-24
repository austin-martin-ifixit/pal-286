"""Pictures of PAL's music, in plain ASCII for the Compaq's screen.

Two views of the same timeline (from music.render or music.sing: (start
seconds, length seconds, MIDI note, voice) for every note):

- The jukebox in the menu (client.py jukebox): notes fall down the screen
  onto a keyboard, landing as they play. Each step is one new line at the
  top of the falling area (the terminal scrolls the rest down itself), so
  it keeps up at 9600 baud.
- PAL's "now playing" card (pal.py), drawn by the serial bridge: the title,
  a fun fact, a keyboard with the notes playing right now marked above it,
  and a progress bar. Only the marker row changes often.
"""

import textwrap
import unicodedata

LOW, HIGH = 36, 111            # C2 to D#8: one column a semitone
LEFT = 2                       # columns before the keyboard (drums go here)
BLACK = {1, 3, 6, 8, 10}       # black keys within an octave
MARK = {"lead": "@", "voice": "@", "harmony": "+", "bass": "O"}
DRUM = {36: "K", 38: "S", 42: ".", 46: "o", 49: "*"}
STEP = 0.15                    # seconds a line of the falling notes stands for


def column(midi):
    """Where a note sits on the keyboard (folded into range by octaves)."""
    while midi < LOW:
        midi += 12
    while midi > HIGH:
        midi -= 12
    return LEFT + midi - LOW


def keyboard():
    """Two rows: the black keys, then the white ones."""
    black = " " * LEFT + "".join("#" if (m % 12) in BLACK else " " for m in range(LOW, HIGH + 1))
    white = " " * LEFT + "=" * (HIGH - LOW + 1)
    return [black.rstrip(), white]


def ascii_text(text):
    """Plain ASCII for the Compaq: "Fur Elise", not "F?r Elise"."""
    text = unicodedata.normalize("NFKD", str(text))
    return "".join(c for c in text if " " <= c <= "~")


def octave_labels():
    row = [" "] * (LEFT + HIGH - LOW + 1)
    for m in range(LOW, HIGH + 1, 12):
        label = f"C{m // 12 - 1}"
        for i, ch in enumerate(label):
            if column(m) + i < len(row):
                row[column(m) + i] = ch
    return "".join(row).rstrip()


def sounding(timeline, t, drums=True):
    """{column: character} for the notes playing at t seconds."""
    cells = {}
    for start, length, midi, voice in timeline:
        if start > t:
            break
        if voice == "drums":
            if drums and t - start < 0.12:
                cells[0] = DRUM.get(midi, "x")
        elif start <= t < start + max(length, 0.08):
            cells.setdefault(column(midi), MARK.get(voice, "+"))
    return cells


def notes_now(timeline, t):
    """The notes (MIDI numbers) sounding at t seconds, drums aside: for the
    keyboard in dots (pal_screen)."""
    found = set()
    for start, length, midi, voice in timeline:
        if start > t:
            break
        if voice != "drums" and start <= t < start + max(length, 0.08):
            found.add(int(midi))
    return sorted(found)


def falling_line(timeline, t):
    """One line of the falling notes for the moment t: a note's first line
    shows its voice's mark, the rest of it a stem."""
    cells = {}
    for start, length, midi, voice in timeline:
        if start >= t + STEP:
            break
        if voice == "drums":
            if t <= start < t + STEP:
                cells[0] = DRUM.get(midi, "x")
            continue
        if start + length <= t:
            continue
        col = column(midi)
        if t <= start < t + STEP:
            cells[col] = MARK.get(voice, "+")
        elif col not in cells:
            cells[col] = "|"
    return compact(cells)


def compact(cells):
    """Cells as the fewest bytes to send: characters with cursor jumps
    (ESC [ n C) over the gaps. Starts at the left edge."""
    out, at = [], 0
    for col in sorted(cells):
        gap = col - at
        if gap > 4:
            out.append(f"\x1b[{gap}C")
        elif gap > 0:
            out.append(" " * gap)
        out.append(cells[col])
        at = col + 1
    return "".join(out)


def clock(seconds):
    seconds = max(0, int(seconds))
    return f"{seconds // 60}:{seconds % 60:02d}"


def progress(t, total, width=50):
    done = int(width * min(1.0, t / total)) if total else width
    return f"[{'#' * done}{'.' * (width - done)}]  {clock(t)} / {clock(total)}"


def card(meta, total):
    """PAL's "now playing" picture (22 rows, for the bridge's canvas),
    without the parts that move."""
    rows = ["", f"{'P A L   2 8 6   J U K E B O X':^79}", ""]
    rows.append(f"{ascii_text(meta.get('title', 'A tune')).upper()[:75]:^79}")
    by = ascii_text(", ".join(str(v) for v in (meta.get("composer"), meta.get("year")) if v))
    rows.append(f"{by[:75]:^79}")
    rows.append("")
    fact = textwrap.wrap(ascii_text(meta.get("fact", "")), 70)[:3]
    rows += [f"{line:^79}" for line in fact] + [""] * (3 - len(fact))
    rows += ["", ""]
    rows.append("")                          # row 12: what's playing, over the keys
    rows += keyboard()                       # rows 13-14
    rows.append(octave_labels())             # row 15
    rows += ["", ""]
    rows.append(f"{progress(0, total):^79}")  # row 18
    rows += ["", f"{'A KEY AT THE COMPAQ STOPS THE MUSIC':^79}"]
    rows += [""] * (22 - len(rows))
    return rows


MARKER_ROW, PROGRESS_ROW = 11, 17           # (0-based rows in card())


def marker_row(timeline, t):
    cells = sounding(timeline, t, drums=False)
    row = [" "] * (LEFT + HIGH - LOW + 1)
    for col, ch in cells.items():
        row[col] = ch
    return "".join(row).rstrip()

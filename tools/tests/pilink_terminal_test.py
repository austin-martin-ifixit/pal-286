# PILINK as the Compaq's whole terminal (PI.BAT), with PILINK played in
# Python (lib/pilink.py): the text encoder against it (changes, scrolling,
# runs, lost bytes), the shared session's VT102 text turned into text-mode
# cells (lib/text_screen.py), and the link taking up a PILINK that said
# hello by itself, showing text with its cursor, and asking it to leave for
# a file transfer.
# Usage: python3 pilink_terminal_test.py [path to lib]   (touches nothing live)
import sys
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "/opt/compaq/lib")
import numpy as np
import pilink
import text_screen

rng = np.random.default_rng(286)
failures = 0


def check(what, good, detail=""):
    global failures
    if good:
        print(f"ok   {what}")
    else:
        failures += 1
        print(f"FAIL {what} {detail}")


def text_memory(rows, attr=0x07):
    """25 rows of text (each up to 80 characters) as text-mode memory."""
    memory = pilink.BLANK_TEXT.copy()
    for y, row in enumerate(rows):
        data = row.ljust(80)[:80].encode("cp437")
        memory[y * 160:y * 160 + 160:2] = np.frombuffer(data, np.uint8)
        memory[y * 160 + 1:y * 160 + 160:2] = attr
    return memory


def words():
    return " ".join("".join(chr(c) for c in rng.integers(97, 123, rng.integers(2, 9))) for _ in range(12))[:79]


# ---- the text encoder against PILINK played in Python
screen, encoder = pilink.Screen(), pilink.TextEncoder()
screen.feed(encoder.setup())
lines = [words() for _ in range(24)]
frames = [("a full screen", text_memory(lines))]
for shift in (1, 3):                                       # scrolled up, new lines at the bottom
    lines = lines[shift:] + [words() for _ in range(shift)]
    frames.append((f"scrolled up {shift}", text_memory(lines)))
lines = [words(), words()] + lines[:22]                     # scrolled down 2 (a pager going back)
frames.append(("scrolled down 2", text_memory(lines)))
fixed = ["MENU HEADER"] + lines[2:23] + ["status line"]     # a fixed header and footer, the middle scrolling
frames.append(("header and footer", text_memory(fixed)))
fixed = ["MENU HEADER"] + lines[3:23] + [words(), "status line"]
frames.append(("the middle scrolled", text_memory(fixed)))
changed = text_memory(fixed)
changed[5 * 160 + 20:5 * 160 + 40:2] = ord("X")             # a word typed
changed[7 * 160 + 1:7 * 160 + 160:2] = 0x70                 # a reversed row (a menu bar)
changed[9 * 160 + 1:9 * 160 + 21:2] = 0x8F                  # bright and blinking
frames.append(("a word, a bar, a blink", changed))
frames.append(("cleared", pilink.BLANK_TEXT.copy()))
frames.append(("one line", text_memory(["", "", "Hello, Compaq."])))
sizes = []
for n, (what, memory) in enumerate(frames):
    if what == "cleared":
        encoder.forget()                                    # (as after lost bytes)
    ops = encoder.frame(memory)                             # (after forget(): the mode again, and all of it)
    sizes.append(len(ops))
    for cut in range(0, len(ops), 61):                      # in pieces, as a cable delivers
        screen.feed(ops[cut:cut + 61])
    same = np.array_equal(screen.memory[:4000], memory)
    check(f"text: {what} ({len(ops)} bytes)", same,
          f"{int((screen.memory[:4000] != memory).sum())} bytes differ")
check("text: nothing changed, nothing sent", encoder.frame(frames[-1][1]) == b"")
check("text: a full screen costs about a byte a character", sizes[0] < 24 * 85, sizes[0])
check("text: a one-line scroll costs about one line", sizes[1] < 200, sizes[1])
check("text: a long run of one character is copied, not sent", len(encoder.frame(text_memory(["=" * 80]))) < 40)

# ---- VT102 text into text-mode cells
vt = text_screen.TextScreen()
vt.feed(b"\x1b[H\x1b[2JHello\r\n\x1b[1mBright\x1b[0m \x1b[7mReversed\x1b[0m \x1b[5mBlink\x1b[0m"
        b"\x1b)0\x0elqk\x0f\x1b[10;20H")
memory, cursor = vt.cells()
rows = vt.rows()
check("vt: text", rows[0].startswith("Hello") and rows[1].startswith("Bright Reversed Blink"), rows[:2])
check("vt: bright, reversed, blinking", (memory[161], memory[2 * 7 + 161], memory[2 * 16 + 161])
      == (0x0F, 0x70, 0x87), (memory[161], memory[2 * 7 + 161], memory[2 * 16 + 161]))
check("vt: line drawing as the PC's own", bytes(memory[160 + 2 * 21:160 + 2 * 24:2]) == bytes((0xDA, 0xC4, 0xBF)),
      bytes(memory[160 + 2 * 21:160 + 2 * 24:2]))
check("vt: the cursor", cursor == (9, 19), cursor)
vt.feed(b"\x1b[?25l")
check("vt: a hidden cursor goes off the screen", vt.cells()[1] == text_screen.HIDDEN)
check("vt: the 25th row stays dark", (memory[24 * 160::2] == 0x20).all())


# ---- the link: a PILINK that started by itself
class Port:
    def __init__(self):
        self.out, self.baud = bytearray(), 9600

    def queue(self, data):
        self.out += data

    def drop(self):
        self.out.clear()

    def speed(self, baud):
        self.baud = baud


port = Port()
link = pilink.Link(port, 9600)
compaq = pilink.Screen(flags=0)                             # started by PI.BAT, not by Kermit
now = 0.0


def run(seconds=5.0):
    """Lets the two ends talk: what the Pi queued reaches the Compaq, and
    its answers come back."""
    global now
    end = now + seconds
    while now < end:
        if port.out:
            data, port.out = bytes(port.out), bytearray()
            said = compaq.feed(data)
            if compaq.speed:                                 # (PILINK takes the new speed)
                compaq.speed = None
            if said:
                link.feed(said, now)
        now += 0.05
        link.tick(now)


link.feed(b"\x00" + compaq.hello(), now)
run()
events = [e[0] for e in link.events]
check("link: takes up a PILINK nobody asked for", link.terminal and link.state == "on" and "up" in events,
      (link.terminal, link.state, events))
link.events.clear()
link.show(pilink.TEXT_80, text_memory(["C:\\> PI", "Welcome back."]), now, cursor=(1, 13))
run(1)
check("link: text and cursor on the Compaq", compaq.text()[1].startswith("Welcome back.") and compaq.cursor == (1, 13)
      and compaq.mode == pilink.TEXT, (compaq.text()[:2], compaq.cursor, compaq.mode))
link.feed(b"K\x1eK\x9e", now)
keys = [e for e in link.events if e[0] == "key"]
check("link: keys come back", keys and keys[0][1:] == (0x1e, True, b"a"), keys)
check("link: leaves for a transfer", link.leave(pilink.KERMIT_EXIT, now))
run(1)
check("link: gone, with PI.BAT's exit code", link.state == "off" and not link.terminal
      and compaq.exit_code == pilink.KERMIT_EXIT and ("down", "stopped") in link.events,
      (link.state, compaq.exit_code, link.events))
old = pilink.Link(Port(), 9600)
old.feed(b"\x1b_PL" + bytes((1 + 0x20, 0x20, 0x23)) + b"\x1b\\", 0.0)
old_compaq, old.port.out = pilink.Screen(), bytearray()
check("link: a version 1 PILINK can't be asked to leave", not old.leave(pilink.KERMIT_EXIT, 0.0))
kermit = pilink.Link(Port(), 9600)
kermit.feed(pilink.Screen(flags=2).hello(), 0.0)
check("link: one Kermit started isn't taken up unasked", kermit.state == "off")

# The real Compaq's BIOS doesn't hear the line while it sets a mode: what
# follows a mode command at once is lost ('N' 2, an overrun), and PILINK asks
# for the whole screen again, mode first (seen 2026-10-30, at 115200 baud).
port, link, compaq, now = Port(), pilink.Link(Port(), 9600), pilink.Screen(flags=0), 0.0
link.port = port
overruns = 0


def run_deaf(seconds=5.0):
    global now, overruns
    end, owed = now + seconds, b""
    while now < end:
        said = owed
        owed = b""
        if port.out:
            data, port.out = bytes(port.out), bytearray()
            if data[0] == pilink.MODE and len(data) > 2:     # the rest arrived mid-mode: lost
                said += compaq.feed(data[:2]) + b"N\x02"
                owed, overruns = b"R\x00", overruns + 1
            else:
                said += compaq.feed(data)
            compaq.speed = None
        if said:
            link.feed(said, now)
        now += 0.05
        link.tick(now)


link.feed(compaq.hello(), now)
run_deaf()
link.show(pilink.TEXT_80, text_memory(["C:\\> PI", "Welcome back."]), now, cursor=(1, 13))
run_deaf(2)
check("link: a mode on its own, the screen after the BIOS has set it",
      compaq.text()[1].startswith("Welcome back.") and overruns == 0, (compaq.text()[:2], overruns))
sys.exit(1 if failures else 0)

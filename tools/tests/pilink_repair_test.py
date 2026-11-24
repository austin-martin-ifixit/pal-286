# Lost bytes, repaired: a byte dropped at random inside real frames (still
# pictures, a film-like moving picture, every size), with PILINK 3's own
# rule for what happens next played out (it stops before acting on a count
# that came after a loss, so only what that frame changed can be wrong),
# then the Pi's repair (pilink.Encoder.doubt, the scale again) checked dot
# for dot, and its cost against sending the whole screen again. Then RUN
# and THERE (a DOS program the Pi asks for, a file on the Compaq's disk)
# through pilink.Link against PILINK played in Python.
# Usage: python3 pilink_repair_test.py [path to lib]   (touches nothing live)
import sys
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "/opt/compaq/lib")
import numpy as np
import pilink

rng = np.random.default_rng(286)
failures = 0


def check(what, good, detail=""):
    global failures
    if not good:
        failures += 1
        print(f"FAIL {what} {detail}")
    return good


def commands(ops):
    """(start, end of its opcode and arguments, end) of each command."""
    found, i = [], 0
    while i < len(ops):
        op = ops[i]
        if op < 0x40:
            head, body = 1, 0
        elif op < 0x80:
            head, body = 1, op - 0x3F
        elif op < 0xC0:
            head, body = 2, 0
        elif op == pilink.LITW:
            head, body = 3, ops[i + 1] | ops[i + 2] << 8
        elif op == pilink.FILLW:
            head, body = 4, 0
        else:
            head, body = 1 + pilink.ARGS[op], 0
        found.append((i, i + head, i + head + body))
        i += head + body
    return found


def spoil(screen, ops, k):
    """What PILINK 3 makes of ops with byte k lost: everything before the
    command it was in, then (if it was in that command's data) the data
    shifted along by one, then nothing: it says N, waits, says R, and sets
    its scale back. Returns the commands' kinds, for the record."""
    start, head, end = next(c for c in commands(ops) if c[0] <= k < c[2])
    screen.feed(ops[:start])
    if k >= head:                                  # in the data: shifted, as far as it goes
        rest = ops[head:k] + ops[k + 1:]
        screen.put(np.frombuffer(rest[:end - head], np.uint8))
    screen.pending = b""
    screen.wide = screen.tall = 1
    return "data" if k >= head else "count or address"


def frames_for(layout, count):
    """A still picture's worth of changes, then a film: a moving square on
    a dithered ramp, with noise flickering in a corner."""
    h, w = layout.height, layout.width
    ramp = (np.arange(w)[None, :] * 4 + np.arange(h)[:, None] * 3) % 17 < 8
    shots = []
    for t in range(count):
        dots = ramp.copy()
        x, y = (t * 13) % (w - 40), (t * 7) % (h - 30)
        dots[y:y + 30, x:x + 40] ^= True
        dots[:h // 5, -w // 5:] = rng.random((h // 5, w // 5)) < 0.5
        shots.append(dots)
    return shots


repaired = full = trials = 0
kinds = {"data": 0, "count or address": 0}
for name, sweep in (("CGA_320x100", True), ("CGA_320", True), ("CGA_640", False), ("PLASMA_640", True),
                    ("CGA_160", False)):
    layout = getattr(pilink, name)
    screen, encoder = pilink.Screen(), pilink.Encoder(layout, sweep)
    screen.feed(encoder.setup())
    shots = frames_for(layout, 40)
    for n, dots in enumerate(shots):
        ops = encoder.frame(layout.pack(dots))
        if n > 0 and n % 3 == 0 and ops:           # this one loses a byte on the way
            trials += 1
            kinds[spoil(screen, ops, int(rng.integers(len(ops))))] += 1
            check(f"{name}: the frame can be doubted", encoder.doubt())
            again = bytes((pilink.SCALE, layout.scale)) + encoder.frame(layout.pack(dots))
            repaired += len(again)
            full += layout.size
            screen.feed(again)
        else:
            screen.feed(ops)
        shown = screen.dots()
        want = np.repeat(np.repeat(dots, 640 // layout.width, axis=1), shown.shape[0] // layout.height, axis=0)
        if not check(f"{name} frame {n}", np.array_equal(shown, want),
                     f"{int((shown != want).sum())} dots wrong"):
            break
print(f"ok   {trials} lost bytes repaired dot for dot ({kinds['data']} in a picture's data, "
      f"{kinds['count or address']} in a count or address)")
print(f"     repairs took {repaired:,} bytes; sending each screen again whole: {full:,} "
      f"({full / max(repaired, 1):.0f} times as many, and a blank screen each time)")


class Cable:
    """A port whose bytes go straight to PILINK played in Python."""

    def __init__(self, screen):
        self.screen, self.back = screen, b""

    def queue(self, data):
        self.back += self.screen.feed(data)

    def drop(self): pass

    def speed(self, baud): pass


def linked(can_run, files=()):
    screen = pilink.Screen()
    screen.can_run, screen.files = can_run, set(files)
    cable = Cable(screen)
    link = pilink.Link(cable, "38400")
    link.feed(screen.hello(), 0.0)                 # (as PI.BAT starts it: the Compaq's terminal)
    for _ in range(20):                            # its speed test and the 640x400 question
        back, cable.back = cable.back, b""
        link.feed(back, 1.0)
        link.tick(1.0)
        if link.state == "on":
            break
    return link, screen, cable


def answers(link, cable, now=2.0):
    back, cable.back = cable.back, b""
    link.feed(back, now)
    events, link.events[:] = list(link.events), []
    return events


link, screen, cable = linked(True, ["C:\\DOOM\\DOOM4.WAD", "C:\\PI\\PILINK.COM"])
check("PILINK 3 comes up as the terminal", link.state == "on" and link.version == 3, link.state)
answers(link, cable)
link.there("C:\\DOOM\\DOOM4.WAD", 2.0)
link.there("C:\\WOLF\\*.EXE", 2.0)
events = answers(link, cable)
check("THERE: one file there, one not", ("there", "C:\\DOOM\\DOOM4.WAD", True) in events
      and ("there", "C:\\WOLF\\*.EXE", False) in events, repr(events))
batch = "ECHO OFF\nC:\nCD \\DOOM\nDOOM\nC:\nCD \\PI\nPI\n"
check("RUN is sent", link.run(batch, 3.0))
events = answers(link, cable, 3.0)
check("RUN: PILINK writes the batch file, with DOS line ends", screen.ran == batch.replace("\n", "\r\n").encode())
check("RUN: then leaves for DOS (exit code 12)", screen.exit_code == pilink.RUN_EXIT
      and ("down", "stopped") in events and link.state == "off", f"{screen.exit_code} {events} {link.state}")

link, screen, cable = linked(False)
answers(link, cable)
link.run(batch, 3.0)
events = answers(link, cable, 3.0)
check("RUN with no DOS to run it (the TV): it says so and stays", ("ran", False) in events and link.state == "on",
      f"{events} {link.state}")
check("RUN too long for PILINK: not sent", not link.run("X" * 2000, 4.0))

print("\n" + ("All passed." if not failures else f"{failures} failed."))
sys.exit(1 if failures else 0)

# The serial bridge hearing a PILINK hello that arrives in pieces, as the
# real cable's USB adapter hands it over (three bytes at a time at 9600
# baud, seen on the Compaq 2026-10-30), and in one piece, as the test rig's
# TCP cable does. Either way the bridge takes PILINK up as the terminal and
# none of the hello is typed into the shared session. Typing that only
# looks like the start of one still gets through. Then the night of
# 2026-11-03: the terminal PILINK stopped answering, the bridge took its
# "N" and "R" for Kermit typing and echoed them back, and the two answered
# each other until morning. Its messages are never typing now, and for a
# while after a lost link nothing is.
# Usage: python3 bridge_hello_test.py [path to lib]   (touches nothing live)
import sys
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "/opt/compaq/lib")
import pilink
import serial_bridge

failures = 0


def check(what, good, detail=""):
    global failures
    if good:
        print(f"ok   {what}")
    else:
        failures += 1
        print(f"FAIL {what} {detail}")


class Port:
    def __init__(self): self.sent = b""
    def queue(self, data): self.sent += data
    def speed(self, baud): pass
    def drop(self): pass


class Bridge:
    """Just what Bridge.from_compaq and the loop's hold use."""
    from_compaq = serial_bridge.Bridge.from_compaq

    def __init__(self, mode="kermit", lost_at=-1e9):
        self.port = Port()
        self.link = pilink.Link(self.port, "9600")
        self.mode, self.held, self.held_since, self.typed = mode, b"", 0.0, b""
        self.lost_at, self.hello_asked, self.line, self.woke = lost_at, -1e9, None, False

    def use(self, mode): self.mode = mode
    def wake(self, now): self.woke = True
    def link_news(self, now): self.link.events.clear()
    def compaq_typed(self, data, now): self.typed += data

    def cable(self, pieces, gap=0.01):
        """The loop's part: each read joined to what was held, and what's
        held for longer than HOLD_HELLO let go."""
        now = 0.0
        for piece in pieces:
            now += gap
            if self.held and now - self.held_since >= serial_bridge.HOLD_HELLO:
                held, self.held = self.held, b""
                self.from_compaq(held, now, hold=False)
            data, self.held = self.held + piece, b""
            self.from_compaq(data, now)
        now += 1.0
        if self.held:
            held, self.held = self.held, b""
            self.from_compaq(held, now, hold=False)


hello = pilink.Screen(flags=0).hello()
seen = b"\x1b_P", b'L" ', b"#\x1b\\"                     # (as strace saw it on the Pi)
for name, pieces in (("whole", [hello]), ("in the pieces the Pi saw", list(seen)),
                     ("a byte at a time", [bytes((b,)) for b in hello]),
                     ("after a key", [b"x" + hello[:5], hello[5:]])):
    bridge = Bridge()
    bridge.cable(pieces)
    check(f"hello {name}: PILINK is the terminal", bridge.link.terminal and bridge.mode == "pilink",
          f"(state {bridge.link.state}, mode {bridge.mode})")
    check(f"hello {name}: none of it typed", b"PL" not in bridge.typed and b"\x1b" not in bridge.typed,
          repr(bridge.typed))

for name, pieces in (("Escape, then a letter", [b"\x1b", b"q"]), ("plain typing", [b"dir", b"\r"])):
    bridge = Bridge()
    bridge.cable(pieces, gap=0.2)
    check(f"{name}: typed, not a terminal", bridge.typed == b"".join(pieces) and not bridge.link.terminal,
          repr(bridge.typed))

serial_bridge.write_all = lambda fd, data: None
for mode in ("kermit", "pilink"):
    bridge = Bridge(mode)
    bridge.cable([b"N\x01", b"R\x00"] * 6, gap=0.5)              # (what the cable carried all night)
    check(f"PILINK's N and R, the bridge in {mode} mode: never typed", bridge.typed == b"", repr(bridge.typed))
    check(f"... and it asks who's there (and stops sending Kermit text)",
          bytes((pilink.HELLO,)) in bridge.port.sent and bridge.mode == "pilink",
          f"{bridge.port.sent!r} {bridge.mode}")
    check(f"... but not every time: once every 2 seconds at most (6 seconds of it)",
          bridge.port.sent.count(pilink.HELLO) <= 4, repr(bridge.port.sent))
bridge = Bridge("pilink")
bridge.cable([b"N\x01"], gap=0.1)
bridge.cable([pilink.Screen(flags=0).hello()])
check("... and its hello then makes it the terminal again", bridge.link.terminal and bridge.mode == "pilink")

bridge = Bridge("pilink", lost_at=0.0)                             # PILINK just stopped answering
bridge.cable([b"\xfe\x13x", b"j\x9cA"], gap=0.5)                 # (at another speed: noise)
check("just after a lost link, noise isn't typing", bridge.typed == b"" and bridge.mode == "pilink",
      f"{bridge.typed!r} {bridge.mode}")
bridge = Bridge("pilink", lost_at=-30.0)                           # long after: someone started Kermit
bridge.cable([b"dir", b"\r"], gap=0.2)
check("long after, typing at Kermit gets Kermit back", bridge.mode == "kermit")
bridge = Bridge("kermit")
bridge.cable([b"A", b"\r", b"N", b"\t", b"Q", b"\x1b[A"], gap=0.2)
check("typing a letter then Enter, Tab or an arrow at Kermit is still typing", bridge.typed == b"A\rN\tQ\x1b[A"
      and bridge.mode == "kermit", repr(bridge.typed))

print("\n" + ("All passed." if not failures else f"{failures} failed."))
sys.exit(1 if failures else 0)

# F10 (Ctrl-\) at the Compaq reaching the main menu from anything: a
# picture a menu program put up, one PAL put up (FixBot's page, which
# F10 used to leave on the screen, 2026-11-01), a still picture with PI as
# the terminal, PAL's own screen, and through Kermit. The picture's owner
# hears "menu"; other keys still go to a moving picture's owner.
# Usage: python3 bridge_menu_key_test.py [path to lib]   (touches nothing live)
import sys
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "/opt/compaq/lib")
import pilink
import serial_bridge

failures = 0
sent, replies = [], []
serial_bridge.write_all = lambda fd, data: sent.append(data)
serial_bridge.reply = lambda conn, message: replies.append(message) or True


def check(what, good, detail=""):
    global failures
    if good:
        print(f"ok   {what}")
    else:
        failures += 1
        print(f"FAIL {what} {detail}")


class Port:
    def queue(self, data): pass
    def speed(self, baud): pass
    def drop(self): pass


class Picture:
    def __init__(self, moving):
        self.moving, self.conn = moving, None


class Bridge:
    """Just what a key from the Compaq goes through."""
    link_news = serial_bridge.Bridge.link_news
    menu_key = serial_bridge.Bridge.menu_key
    compaq_typed = serial_bridge.Bridge.compaq_typed

    def __init__(self, picture=None, scene=False, terminal=True):
        self.link = pilink.Link(Port(), "9600")
        self.link.terminal = terminal
        self.picture, self.scene_on, self.ended, self.woke = picture, scene, [], 0
        self.client, self.mode, self.last_key, self.last_activity = None, "pilink" if terminal else "kermit", 0.0, 0.0
        self.pilink_line, self.resends_said, self.resends_at = "", 0, 0.0

    def end_picture(self, why, now, key=b""):
        self.ended.append(why)
        self.picture = None

    def asleep(self):
        return self.scene_on or self.picture is not None

    def wake(self, now):
        self.woke += 1
        self.scene_on = False

    def redraw(self):
        pass

    def press(self, scancode, typed, now=10.0):
        self.link.events += [("key", scancode, True, typed), ("key", scancode, False, b"")]
        self.link_news(now)


F10 = 0x44
for name, bridge in (("FixBot's page (a moving picture PAL holds)", Bridge(Picture(True))),
                     ("a still picture, PI as the terminal", Bridge(Picture(False))),
                     ("PAL's own screen", Bridge(scene=True)),
                     ("the shared screen", Bridge())):
    sent.clear()
    had_picture = bridge.picture is not None
    bridge.press(F10, pilink.MENU_KEY)
    check(f"{name}: F10 reaches the menu, once", sent == [pilink.MENU_KEY], repr(sent))
    if had_picture:
        check(f"{name}: the picture comes down, its owner hears menu", bridge.ended == ["menu"], repr(bridge.ended))
    check(f"{name}: nothing left covering the menu", not bridge.asleep())

sent.clear()
kermit = Bridge(scene=True, terminal=False)
kermit.compaq_typed(pilink.MENU_KEY, 10.0)
check("through Kermit, over PAL's screen: F10 reaches the menu", sent == [pilink.MENU_KEY] and not kermit.asleep(),
      repr(sent))

sent.clear()
replies.clear()
game = Bridge(Picture(True))
game.press(0x48, b"\x1b[A")                            # an arrow, in Doom
check("another key with a moving picture up goes to its owner", not sent and replies and replies[0].get("down"),
      f"{sent!r} {replies!r}")

print("\n" + ("All passed." if not failures else f"{failures} failed."))
sys.exit(1 if failures else 0)

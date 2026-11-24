# When PAL's eye may cover the Compaq. Someone typed at the lobby keyboard
# a moment ago, then said "Hey PAL": the eye shows (it didn't, 2026-11-05).
# PAL's own greeting at that moment doesn't; someone typing on the web
# holds both back; the saver never does. And the bridge's log says why
# whenever it holds the eye back.
# Usage: python3 pal_eye_busy_test.py [path to lib] [path to pal]   (touches nothing live)
import sys
sys.path.insert(0, sys.argv[1] if len(sys.argv) > 1 else "/opt/compaq/lib")
sys.path.insert(0, sys.argv[2] if len(sys.argv) > 2 else "/opt/compaq/pal")
import serial_bridge

failures = 0


def check(what, good, detail=""):
    global failures
    if good:
        print(f"ok   {what}")
    else:
        failures += 1
        print(f"FAIL {what} {detail}")


LOBBY = 1161                 # the Compaq's own tmux client
typed = {"lobby": -1e9, "web": -1e9}   # wall-clock time each last typed


def last_typed(skip_pid=None):
    return max(typed["web"], typed["lobby"] if skip_pid != LOBBY else -1e9)


serial_bridge.last_typed = last_typed


class Saver:
    on = False


class Bridge:
    compaq_busy = serial_bridge.Bridge.compaq_busy

    def __init__(self):
        self.saver, self.client_pid, self.last_key = Saver(), LOBBY, -1e9


now_mono = 10_000.0
now_wall = serial_bridge.time.time()
b = Bridge()

b.last_key, typed["lobby"] = now_mono - 16, now_wall - 16      # typed at the Compaq 16 s ago
check("a greeting waits for the person typing", b.compaq_busy(now_mono, False).startswith("a key at the Compaq"),
      b.compaq_busy(now_mono, False))
check("\"Hey PAL\" from the same person: the eye shows", b.compaq_busy(now_mono, True) == "",
      b.compaq_busy(now_mono, True))

typed["web"] = now_wall - 10
check("someone typing on the web holds back even \"Hey PAL\"",
      b.compaq_busy(now_mono, True).startswith("typed on the web"), b.compaq_busy(now_mono, True))
typed["web"] = now_wall - 45
check("...but not 45 s later", b.compaq_busy(now_mono, True) == "")

b.last_key, typed["lobby"], typed["web"] = now_mono - 200, now_wall - 200, now_wall - 200
check("nobody typed for 200 s: a greeting shows", b.compaq_busy(now_mono, False) == "")

b.last_key, typed["lobby"] = now_mono - 5, now_wall - 5
b.saver.on = True
check("the saver is up: always free", b.compaq_busy(now_mono, False) == "")

# PAL's side: what Screen.begin asks the bridge for.
try:
    import pal
except Exception as e:                       # (pal.py needs the Pi's libraries)
    print(f"skip PAL's side: {e}")
else:
    asked = []
    screen = pal.Screen("PAL 286")
    screen.send = lambda **request: asked.append(request) or {"shown": True}
    screen.begin()
    check("a greeting asks as before (not requested)", asked[-1].get("requested") is False, asked[-1])
    screen.asked = True
    screen.begin()
    check("a chat begun with PAL's name asks as requested", asked[-1].get("requested") is True, asked[-1])
    screen.begin(canvas=True, requested=False)
    check("an explicit requested=False still wins", asked[-1].get("requested") is False, asked[-1])

print("\n" + ("All passed." if not failures else f"{failures} failed."))
sys.exit(1 if failures else 0)

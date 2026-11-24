# PAL's scene through the bridge, over a fake cable. Runs on the Pi as desk.
import json, os, socket, sys, time
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from bridge_test3_lib import FakeCable, WebViewer, go_welcome, shared

def pal(**request):
    s = socket.socket(socket.AF_UNIX); s.connect("/run/compaq-serial/bridge.sock")
    s.sendall((json.dumps(dict(op="pal", **request)) + "\n").encode())
    answer = json.loads(s.makefile().readline()); s.close(); return answer

print("0. welcome:", go_welcome())
cable = FakeCable(COMPAQ_SAVER_SECONDS="600", COMPAQ_PAL_IDLE_SECONDS="6")
try:
    cable.wait_for("This screen is shared", 6)
    cable.type("x"); cable.read(1); cable.type("\x7f"); cable.read(1)
    print("1. someone just typed, PAL is refused:", pal(action="begin")["shown"] is False)
    time.sleep(7)
    print("2. after 6 quiet seconds PAL may show:", pal(action="begin", name="PAL 286")["shown"])
    pal(action="say", who="pal", text="Good morning, Joe.\x1b[2J Welcome back, my g.", cps=40)
    pal(action="status", text="listening", blink=True)
    cable.read(3)
    print("3. the Compaq shows the eye, the words and the status:",
          cable.shows("P A L   2 8 6"), (cable.shows("Good morning, Joe. [2J Welcome back, my g.") or cable.shows("Good morning, Joe.  [2J Welcome back, my g.")), cable.shows("LISTENING"))
    print("   (escape sequence in the text was neutralised:", not cable.shows("Welcome back") or cable.shows("[2J"), ")")
    cable.type("q")
    cable.read(3)
    print("4. a key at the Compaq hands the screen back:", cable.shows("This screen is shared"),
          "| key swallowed:", "start. q" not in shared())
    print("5. PAL's next words stay off the screen:", pal(action="say", who="pal", text="Rude.")["shown"] is False)
    time.sleep(7)
    pal(action="begin"); cable.read(2)
    web = WebViewer(); time.sleep(1); web.type("\r")
    print("6. typing in a browser also hands it back:", cable.wait_for("Type a number", 8))
    web.close()
    go_welcome()
finally:
    cable.close()

cable = FakeCable(COMPAQ_SAVER_SECONDS="5", COMPAQ_PAL_IDLE_SECONDS="600")
try:
    print("7. saver on:", cable.wait_for("press a key", 20))
    print("8. PAL may show over the saver:", pal(action="begin")["shown"])
    pal(action="say", who="human", text="what's up pal", cps=200); cable.read(2)
    print("   shows what it heard:", cable.shows("> what's up pal"))
    pal(action="end"); cable.read(3)
    print("9. when PAL finishes, the saver returns:", cable.shows("press a key") and not cable.shows("P A L"))
finally:
    cable.close()
print("10. welcome:", go_welcome())

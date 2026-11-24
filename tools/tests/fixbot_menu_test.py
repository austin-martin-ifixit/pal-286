# The menu's FixBot (apps/10-fixbot -> lib/fixbot_menu.py) against the
# simulated PAL with the real iFixit login: the page comes up on the
# simulated TV, a question typed on the TV's own keyboard after Tab has taken
# the focus off the message box (with a typo fixed
# by Backspace; the way keys reach the page at the lobby) is answered on the
# page, Page Down, a second time in, and leaving takes it down. Runs as
# desk (the menu's account) on the Pi:
#   REAL_FIXBOT_PAGE=1 bash run_pal_tests.sh fixbot_menu_test.py:desk
# Saves the simulated TV: /tmp/pal-sim/menu-*.png
import os, shutil, subprocess, time

SIM = "/tmp/pal-sim/"
t0 = time.time()


def stamp(msg):
    print(f"[{time.time() - t0:5.1f}s] {msg}", flush=True)


def log():
    return open(SIM + "pal.log").read()


def snap(name):
    time.sleep(2.5)
    shutil.copy(SIM + "screen.png", SIM + f"menu-{name}.png")


results = {}
menu = subprocess.Popen(["python3", "/opt/compaq/lib/fixbot_menu.py"], stdin=subprocess.PIPE,
                        stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
for _ in range(60):
    if "on the screen from the menu" in log():
        break
    time.sleep(1)
results["the page came up on the screen"] = "on the screen from the menu" in log()
stamp("page up" if results["the page came up on the screen"] else "no page")
time.sleep(4)
snap("1-open")
def tv_types(typed):
    # (no O_CREAT: Linux's protected_fifos refuses that on another user's pipe in /tmp)
    keyboard = os.open(SIM + "keyboard", os.O_WRONLY)
    try:
        os.write(keyboard, typed)
    finally:
        os.close(keyboard)
    time.sleep(0.5)


tv_types(b"\t\t\t")                              # the focus off the message box: typing finds it anyway
for typed in (b"My iPhone 12 screen is crackef", b"\x7f", b"d. What tools do I need?", b"\r"):
    tv_types(typed)
stamp("typed a question; waiting for FixBot")
time.sleep(45)
snap("2-answer")
tv_types(b"\x1b[6~")                             # Page Down: the rest of the answer
snap("3-page-down")
results["the page stayed up through the typing"] = "off the screen (menu" not in log()
menu.stdin.close()                              # (as if F10: the menu program ends)
try:
    menu.wait(timeout=20)
    out = menu.stdout.read().decode(errors="replace")
except subprocess.TimeoutExpired:
    menu.kill()
    out = "(still running)"
time.sleep(3)
results["leaving took the page down"] = "off the screen (menu: left)" in log()
stamp("again: the menu's FixBot a second time")
again = subprocess.Popen(["python3", "/opt/compaq/lib/fixbot_menu.py"], stdin=subprocess.PIPE,
                         stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
time.sleep(12)
tv_types(b"x")
time.sleep(3)
results["it opens again, and stays up"] = (log().count("on the screen from the menu") == 2
                                           and log().count("off the screen (menu") == 1)
again.stdin.close()
again.wait(timeout=20)
stamp("menu program said: " + " ".join(out.split())[:200])
for line in [l for l in log().splitlines() if l.startswith("fixbot")]:
    stamp("   log: " + line)
results["no errors in PAL's log"] = not [l for l in log().splitlines()
                                         if any(w in l for w in ("main loop:", "Traceback", "menu request:",
                                                                 "Exception in thread", "screen stopped"))]
print()
for what, ok in results.items():
    print(("ok    " if ok else "FAIL  ") + what)
print("\n" + ("All passed (and look at menu-2-answer.png)." if all(results.values())
              else f"{sum(not v for v in results.values())} failed."))

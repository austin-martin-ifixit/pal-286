# Full fake-cable test of serial_bridge.py after the review fixes. pty A is the
# Pi's serial port, pty B the Compaq's COM1. Runs on the Pi as the desk user.
# Only harmless keys are typed, and it leaves the shared session at the
# welcome screen.
import filecmp, fcntl, os, pty, select, signal, struct, subprocess, sys, tempfile, termios
import threading, time, tty

import pyte

TMUX = ["tmux", "-L", "compaq"]


def shared():
    return subprocess.run(TMUX + ["capture-pane", "-p", "-t", "compaq"],
                          capture_output=True, text=True).stdout


def go_welcome():
    for _ in range(6):
        if "This screen is shared" in shared():
            return True
        # What F10 does, but to the welcome screen.
        subprocess.run(TMUX + ["respawn-pane", "-k", "-t", "compaq", "/opt/compaq/session"])
        time.sleep(2)
    return "This screen is shared" in shared()


class FakeCable:
    def __init__(self, **env):
        self.a_master, a_slave = pty.openpty()
        self.a_name = os.ttyname(a_slave)
        tty.setraw(a_slave)
        self.b_master, self.b_slave = pty.openpty()
        self.b_name = os.ttyname(self.b_slave)
        tty.setraw(self.b_slave)
        os.close(a_slave)
        self.running = True
        threading.Thread(target=self.relay, daemon=True).start()
        self.screen = pyte.Screen(80, 24)
        self.stream = pyte.ByteStream(self.screen)
        self.bridge = subprocess.Popen([sys.executable, "/opt/compaq/lib/serial_bridge.py",
                                        self.a_name, "9600"], env=dict(os.environ, **env))

    def relay(self):
        while self.running:
            ready, _, _ = select.select([self.a_master, self.b_master], [], [], 0.2)
            for src, dst in ((self.a_master, self.b_master), (self.b_master, self.a_master)):
                if src in ready:
                    try:
                        os.write(dst, os.read(src, 4096))
                    except OSError:
                        pass

    def read(self, seconds):
        end = time.time() + seconds
        while time.time() < end:
            ready, _, _ = select.select([self.b_slave], [], [], 0.2)
            if ready:
                self.stream.feed(os.read(self.b_slave, 4096))

    def shows(self, text):
        return any(text in line for line in self.screen.display)

    def wait_for(self, text, seconds):
        end = time.time() + seconds
        while time.time() < end:
            self.read(0.5)
            if self.shows(text):
                return True
        return False

    def type(self, keys):
        for ch in keys:
            os.write(self.b_slave, ch.encode())
            time.sleep(0.05)

    def close(self):
        self.running = False
        self.bridge.terminate()
        self.bridge.wait(timeout=5)


class WebViewer:
    """A second tmux client, like a browser at compaq.local."""
    def __init__(self):
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
            os.execvpe("tmux", TMUX + ["attach-session", "-t", "compaq"],
                       dict(os.environ, TERM="vt102", LANG="C", LC_ALL="C"))
        threading.Thread(target=self.drain, daemon=True).start()

    def drain(self):
        while True:
            try:
                if not os.read(self.fd, 4096):
                    return
            except OSError:
                return

    def type(self, keys):
        os.write(self.fd, keys.encode())

    def close(self):
        os.kill(self.pid, signal.SIGTERM)
        os.waitpid(self.pid, 0)


print("0. shared session at the welcome screen:", go_welcome())
pane_tty = subprocess.run(TMUX + ["display-message", "-p", "-t", "compaq", "#{pane_tty}"],
                          capture_output=True, text=True).stdout.strip()

cable = FakeCable(COMPAQ_SAVER_SECONDS="6")
try:
    print("1. the Compaq shows the welcome screen:", cable.wait_for("This screen is shared", 6))
    print("2. left idle, the saver comes on:", cable.wait_for("press a key", 20))
    with open(pane_tty, "w") as t:          # a program changing the screen, nobody typing
        t.write("\x1b7\x1b[24;60Hclock 12:34\x1b8")
    cable.read(5)
    print("3. a program redrawing by itself doesn't wake it:", cable.shows("press a key"))
    cable.type("x")
    cable.read(3)
    print("4. a key at the Compaq wakes it:", cable.shows("This screen is shared"),
          "| the key was swallowed:", "start. x" not in shared())
    print("5. idle again, the saver comes back:", cable.wait_for("press a key", 20))
    web = WebViewer()
    time.sleep(1)
    web.type("\r")                           # someone in a browser presses Enter
    print("6. typing in a browser wakes the Compaq:", cable.wait_for("Type a number", 8))
    web.close()
finally:
    cable.close()

cable = FakeCable(COMPAQ_SAVER_SECONDS="600", COMPAQ_QUIET_SECONDS="8")
try:
    cable.wait_for("Type a number", 6)
    cable.stream.feed(b"\x1b[H\x1b[2JGARBAGE")
    cable.read(10)
    cable.type("x")
    cable.read(3)
    print("7. first key after a quiet spell repaints:", not cable.shows("GARBAGE") and cable.shows("Type a number"))
    cable.type("\x7f")                       # rub out the x

    # Send a file to the "Compaq" through the menu: 8 = Transfer files, 1 = Send.
    docs = os.path.expanduser("~/compaq-files/documents")
    sample = os.path.join(docs, "HELLO.TXT")
    with open(sample, "w") as f:
        f.write("Hello from the Pi!\r\n" * 50)
    cable.type("@60-files\r")
    cable.read(2)
    cable.type("1\r")
    cable.read(3)
    number = next(l.split(".")[0].strip() for l in cable.screen.display if "HELLO.TXT" in l)
    incoming = tempfile.mkdtemp()
    cable.type(f"{number}\r")
    os.close(cable.b_slave)
    receiver = subprocess.run(["kermit", "-Y", "-B", "-C",
        f"set carrier-watch off, set line {cable.b_name}, set speed 9600, set flow-control none, "
        "set parity none, receive, exit"], cwd=incoming, capture_output=True, timeout=90)
    names = os.listdir(incoming)
    print("8. file sent to the Compaq:", names, "| identical:",
          bool(names) and filecmp.cmp(sample, os.path.join(incoming, names[0]), shallow=False))
    cable.b_slave = os.open(cable.b_name, os.O_RDWR | os.O_NOCTTY)
    tty.setraw(cable.b_slave)
    time.sleep(2)
    print("   menu reports:", "Done." in shared())
    os.remove(sample)

    # Cancel a receive: transfer.py killed while waiting must not hurt the bridge.
    waiting = subprocess.Popen([sys.executable, "/opt/compaq/lib/transfer.py", "receive",
                                tempfile.mkdtemp()], stdout=subprocess.PIPE, text=True)
    time.sleep(3)
    status_during = open("/run/compaq-serial/status").read().strip()
    waiting.kill()
    waiting.wait()
    time.sleep(3)
    print("9. cancelling a receive: status during", status_during, "| after",
          open("/run/compaq-serial/status").read().strip(),
          "| bridge still running:", cable.bridge.poll() is None)
finally:
    cable.close()

print("10. shared session back at the welcome screen:", go_welcome())

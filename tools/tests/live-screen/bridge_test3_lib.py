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



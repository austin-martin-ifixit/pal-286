# DOSBox with its COM1 on TCP port 5555, and the Pi's end of that cable, for
# the rig's tests of the real PILINK.COM (pilink_rig.py, dos_test.py).
import os, socket, subprocess, time
import pilink

X = {"DISPLAY": ":99"}


def launch(command, rxdelay=0):
    """DOSBox running command (DOS lines) from C: (/tmp/rig/c); returns the cable.
    rxdelay: milliseconds a byte waits for the program (0: a late byte is lost)."""
    subprocess.run("pkill -f '[d]osbox -conf /tmp/rig'", shell=True)
    time.sleep(1)
    os.makedirs("/tmp/rig/c", exist_ok=True)
    conf = open("/tmp/rig/dosbox.conf").read()
    conf = conf.replace("transparent:1", f"transparent:1 rxdelay:{rxdelay}")
    conf = conf[:conf.index("[autoexec]")] + f"[autoexec]\nmount c /tmp/rig/c\nc:\n{command}\n"
    open("/tmp/rig/pilink.conf", "w").write(conf)
    server = socket.socket()
    server.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    server.bind(("127.0.0.1", 5555))
    server.listen(1)
    if subprocess.run(["pgrep", "-f", "Xvfb :99"], capture_output=True).returncode:
        subprocess.Popen(["Xvfb", ":99", "-screen", "0", "800x600x24"], stdout=subprocess.DEVNULL,
                         stderr=subprocess.DEVNULL)
        time.sleep(1)
    subprocess.Popen(["setsid", "dosbox", "-conf", "/tmp/rig/pilink.conf"], env=dict(os.environ, **X, SDL_AUDIODRIVER="dummy"),
                     stdin=subprocess.DEVNULL, stdout=open("/tmp/rig/dosbox.log", "w"), stderr=subprocess.STDOUT)
    server.settimeout(30)
    conn, _ = server.accept()
    server.close()
    return conn


class Link:
    def __init__(self, conn):
        self.conn, self.buffer, self.inbox = conn, bytearray(), []

    def send(self, data):
        self.conn.sendall(data)

    def expect(self, letter, seconds, value=None):
        """Waits for a message (and its value); returns it, or None. Keys are kept aside in self.keys."""
        deadline = time.monotonic() + seconds
        while True:
            for i, message in enumerate(self.inbox):
                if message[0] == letter and (value is None or message[1] == value):
                    del self.inbox[:i + 1]
                    return message
            left = deadline - time.monotonic()
            if left <= 0:
                return None
            self.conn.settimeout(left)
            try:
                data = self.conn.recv(4096)
            except socket.timeout:
                return None
            if not data:
                return None
            self.buffer += data
            self.inbox += pilink.messages(self.buffer)


def check(what, good, detail=""):
    print(f"{'ok  ' if good else 'FAIL'} {what}{': ' + detail if detail else ''}", flush=True)
    return good

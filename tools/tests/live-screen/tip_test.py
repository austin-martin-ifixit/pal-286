# Struggling in Zork from the TV's keyboard; PAL should offer a tip. Root on the Pi.
import fcntl, os, subprocess, termios, time
TM = ["sudo", "-u", "desk", "tmux", "-L", "compaq"]
def screen(): return subprocess.run(TM + ["capture-pane", "-p", "-t", "compaq"], capture_output=True, text=True).stdout
def tv(keys):
    fd = os.open("/dev/tty7", os.O_RDWR | os.O_NOCTTY)
    for b in keys: fcntl.ioctl(fd, termios.TIOCSTI, bytes([b]))
    os.close(fd)
def pal_log(since):
    return subprocess.run(["journalctl", "-u", "compaq-pal", "--since", since, "--no-pager", "-o", "cat"],
                          capture_output=True, text=True).stdout
start = time.strftime("%Y-%m-%d %H:%M:%S")
subprocess.run(TM + ["respawn-pane", "-k", "-t", "compaq", "/opt/compaq/session menu"]); time.sleep(2)
tv(b"@40-games/10-adventures\r"); time.sleep(2); tv(b"1\r"); time.sleep(1.5); tv(b"\r"); time.sleep(3)
print("Zork open:", "West of House" in screen())
for attempt in (b"walk forward\r", b"move to the house\r", b"please let me in\r", b"walk\r"):
    tv(attempt); time.sleep(4)
for line in screen().splitlines()[-12:]:
    print("   |", line)
end = time.time() + 40
while time.time() < end and "tip:" not in pal_log(start):
    time.sleep(1)
time.sleep(12)
print("PAL log:\n" + "\n".join("   " + l for l in pal_log(start).splitlines() if "WARN" not in l and "sudo" not in l and "pam_unix" not in l))

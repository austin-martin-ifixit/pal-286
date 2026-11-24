# F10 / Ctrl-\ from inside programs, as a browser-style tmux client. Runs as desk.
import fcntl, os, pty, struct, subprocess, termios, threading, time
TM = ["tmux", "-L", "compaq"]
def screen(): return subprocess.run(TM + ["capture-pane", "-p", "-t", "compaq"], capture_output=True, text=True).stdout
def wait(text, secs=8):
    end = time.time() + secs
    while time.time() < end:
        if text in screen(): return True
        time.sleep(0.3)
    return False
pid, fd = pty.fork()
if pid == 0:
    fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
    os.execvpe("tmux", TM + ["attach", "-t", "compaq"], dict(os.environ, TERM="vt102"))
threading.Thread(target=lambda: [os.read(fd, 65536) for _ in iter(int, 1)], daemon=True).start()
def keys(k): os.write(fd, k); time.sleep(0.4)
time.sleep(1)
keys(b"\x1c")
print("1. Ctrl-\\ at the welcome screen -> main menu:", wait("Choose a number"), "| hint shown:", "F10 in any program: main menu" in screen())
keys(b"@40-games/10-adventures\r"); wait("TEXT ADVENTURES"); keys(b"1\r")
print("   intro tip shown:", wait("F10 (or Ctrl-\\) any time"))
keys(b"\r"); print("   Zork running:", wait("West of House", 10))
keys(b"\x1b[21~")
print("2. F10 (browser/TV form) inside Zork -> main menu:", wait("Choose a number") and "West of House" not in screen())
keys(b"@20-office/60-dictionary\r"); print("   dictionary open:", wait("Look up"))
keys(b"\x1bOx")
print("3. F10 (VT102 form) in the dictionary -> main menu:", wait("Choose a number") and "Look up" not in screen())
keys(b"@20-office/60-dictionary\r"); wait("Look up"); keys(b"\x1c")
print("4. Ctrl-\\ (what the Compaq's F10 sends) -> main menu:", wait("Choose a number") and "Look up" not in screen())
keys(b"0\r"); print("5. 0 still signs off to the welcome screen:", wait("Press Enter to start"))
os.kill(pid, 15)
print("\n".join(screen().splitlines()[:0]))

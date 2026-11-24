# The Pi Zero's floppy library (zero/floppy), without a Zero or a GoTEK: its
# USB side switched off, everything in a scratch folder. Checks putting
# disks in the library, the drive, ejecting, getting one back, and that what
# "the Compaq" writes to the disk in the drive is kept. Needs mtools and
# dosfstools (the Pi has both). Touches nothing live.
# Usage: python3 floppy_test.py PATH-TO-floppy
import os, subprocess, sys, tempfile

FLOPPY = os.path.abspath(sys.argv[1] if len(sys.argv) > 1 else "/usr/local/bin/floppy")
work = tempfile.mkdtemp(prefix="floppy-test-")
env = dict(os.environ, FLOPPY_HOME=os.path.join(work, "gotek"), FLOPPY_GADGET="none",
           MTOOLS_SKIP_CHECK="1", MTOOLS_NO_VFAT="1")
failures = 0


def floppy(*words, data=None, ssh=False):
    run_env = dict(env, SSH_ORIGINAL_COMMAND=" ".join(words)) if ssh else env
    done = subprocess.run([FLOPPY] if ssh else [FLOPPY, *words], input=data, capture_output=True, env=run_env)
    return done.returncode, done.stdout, done.stderr.decode()


def check(what, good, detail=""):
    global failures
    failures += 0 if good else 1
    print(f"{'ok  ' if good else 'FAIL'} {what}{': ' + str(detail) if detail else ''}")


def blank(path, label):
    """A 1.2 MB DOS floppy image with one file on it."""
    subprocess.run(["mformat", "-i", path, "-f", "1200", "-C", "-v", label, "::"], check=True, env=env)
    note = os.path.join(work, "note.txt")
    open(note, "w").write(f"This is {label}.\r\n")
    subprocess.run(["mcopy", "-i", path, note, "::NOTE.TXT"], check=True, env=env)
    return open(path, "rb").read()


def files_on(image_bytes):
    path = os.path.join(work, "look.img")
    open(path, "wb").write(image_bytes)
    return subprocess.run(["mdir", "-b", "-i", path, "::"], capture_output=True, env=env, text=True).stdout


kermit, games = blank(os.path.join(work, "a.img"), "KERMIT"), blank(os.path.join(work, "b.img"), "GAMES")
check("put a disk", floppy("put", "kermit", data=kermit)[0] == 0)
check("put another, over SSH", floppy("put", "games", data=games, ssh=True)[0] == 0)
code, out, _ = floppy("list")
check("list", code == 0 and out.decode().splitlines() == ["games\t1.2 MB\t", "kermit\t1.2 MB\t"], repr(out))
check("refuses something that isn't a floppy", floppy("put", "junk", data=b"x" * 1000)[0] != 0)
check("refuses a bad name", floppy("put", "../etc", data=kermit)[0] != 0)
check("refuses commands it doesn't know, over SSH", floppy("rm", "-rf", "/", ssh=True)[0] != 0)
code, out, _ = floppy("insert", "kermit")
check("insert", code == 0 and b"kermit" in out, out.decode().strip())
stick = os.path.join(work, "gotek", "stick.img")
inside = subprocess.run(["mdir", "-b", "-i", stick, "::"], capture_output=True, env=env, text=True).stdout
check("the stick holds FF.CFG and the disk", "FF.CFG" in inside and "DISK.IMG" in inside, inside.split())

# "The Compaq" saves a file onto the disk in the drive.
disk = os.path.join(work, "in-drive.img")
subprocess.run(["mcopy", "-n", "-i", stick, "::DISK.IMG", disk], check=True, env=env)
save = os.path.join(work, "save.txt")
open(save, "w").write("A saved game.\r\n")
subprocess.run(["mcopy", "-i", disk, save, "::SAVE.TXT"], check=True, env=env)
subprocess.run(["mcopy", "-o", "-i", stick, disk, "::DISK.IMG"], check=True, env=env)

code, out, _ = floppy("insert", "games")
check("swap to another disk", code == 0 and b"games" in out)
code, image, _ = floppy("get", "kermit")
check("what the Compaq saved on the first disk was kept", code == 0 and "SAVE.TXT" in files_on(image),
      files_on(image).split())
code, out, _ = floppy("status", ssh=True)
check("status", out.decode().strip() == "in the drive: games", out.decode().strip())
code, image, _ = floppy("get", "games", ssh=True)
check("get the disk in the drive, over SSH", code == 0 and len(image) == 1228800 and "NOTE.TXT" in files_on(image))
check("replace the disk in the drive", floppy("put", "games", data=kermit)[0] == 0 and
      floppy("status")[1].decode().strip() == "in the drive: games")
code, out, _ = floppy("eject")
inside = subprocess.run(["mdir", "-b", "-i", stick, "::"], capture_output=True, env=env, text=True).stdout
check("eject", code == 0 and "DISK.IMG" not in inside and floppy("status")[1].decode().strip() == "in the drive: nothing")
check("remove", floppy("remove", "games")[0] == 0 and "games" not in floppy("list")[1].decode())
check("no such disk", floppy("insert", "nope")[0] != 0)
subprocess.run(["rm", "-rf", work])
print("ALL OK" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)

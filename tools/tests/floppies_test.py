# The Pi's side of the floppy library (lib/floppies.py) against the Zero's
# (zero/floppy), without a Zero: a stand-in "ssh" runs the Zero's program
# here, the way the Zero's restricted key would, with its USB side off.
# Makes a disk from a folder, puts it in the drive, has "the Compaq" save a
# file on it, and copies that back. Touches nothing live.
# Usage: python3 floppies_test.py PATH-TO-lib PATH-TO-floppy
import os, stat, subprocess, sys, tempfile

LIB, FLOPPY = os.path.abspath(sys.argv[1]), os.path.abspath(sys.argv[2])
work = tempfile.mkdtemp(prefix="floppies-test-")
fake = os.path.join(work, "bin")
os.makedirs(fake)
with open(os.path.join(fake, "ssh"), "w") as f:      # what the Zero's forced command does
    f.write(f'#!/bin/bash\nSSH_ORIGINAL_COMMAND="${{@: -1}}" FLOPPY_HOME={work}/zero FLOPPY_GADGET=none exec {FLOPPY}\n')
os.chmod(os.path.join(fake, "ssh"), 0o755)
open(os.path.join(work, "key"), "w").write("(a stand-in)\n")
os.environ.update(PATH=fake + ":" + os.environ["PATH"] + ":/usr/sbin", GOTEK_KEY=os.path.join(work, "key"),
                  HOME=os.path.join(work, "home"), MTOOLS_SKIP_CHECK="1", MTOOLS_NO_VFAT="1")
docs = os.path.join(work, "home", "compaq-files", "documents")
os.makedirs(docs)
open(os.path.join(docs, "a letter to the office.txt"), "w").write("Dear office,\r\n")
open(os.path.join(docs, "BUDGET.WKS"), "wb").write(os.urandom(5000))
sys.path.insert(0, LIB)
import floppies

failures = 0
def check(what, good, detail=""):
    global failures
    failures += 0 if good else 1
    print(f"{'ok  ' if good else 'FAIL'} {what}{': ' + str(detail) if detail else ''}")

check("the drive starts empty", floppies.in_drive() == "nothing", floppies.in_drive())
image = floppies.make_disk([os.path.join(docs, n) for n in sorted(os.listdir(docs))], "documents")
check("a 1.2 MB disk made from a folder", len(image) == 1228800)
floppies.ask("put", "documents", data=image)
floppies.ask("insert", "documents")
check("in the drive", floppies.in_drive() == "documents" and ("documents", "1.2 MB", True) in floppies.disks(),
      floppies.disks())
# "The Compaq" saves a file on it.
stick = os.path.join(work, "zero", "stick.img")
disk = os.path.join(work, "disk.img")
subprocess.run(["mcopy", "-n", "-i", stick, "::DISK.IMG", disk], check=True)
open(os.path.join(work, "MEMO.DOC"), "w").write("From the Compaq.\r\n")
subprocess.run(["mcopy", "-i", disk, os.path.join(work, "MEMO.DOC"), "::MEMO.DOC"], check=True)
subprocess.run(["mcopy", "-o", "-i", stick, disk, "::DISK.IMG"], check=True)
folder = os.path.join(work, "home", "compaq-files", "from-floppy", "documents")
names = floppies.copy_off(floppies.ask("get", "documents"), folder)
check("what the Compaq saved comes back to the Pi", "MEMO.DOC" in [n.upper() for n in names], names)
check("long names were made DOS 8.3", all(len(n.split(".")[0]) <= 8 for n in names), names)
floppies.ask("eject")
check("eject", floppies.in_drive() == "nothing")
try:
    floppies.ask("insert", "../../etc")
    check("a bad name is refused", False)
except floppies.NotThere as e:
    check("a bad name is refused", "lower-case" in str(e), e)
os.remove(os.environ["GOTEK_KEY"])
try:
    floppies.in_drive()
    check("no key: says it isn't set up", False)
except floppies.NotThere as e:
    check("no key: says it isn't set up", "isn't set up" in str(e))
subprocess.run(["rm", "-rf", work])
print("ALL OK" if not failures else f"{failures} FAILED")
sys.exit(1 if failures else 0)

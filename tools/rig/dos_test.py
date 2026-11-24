# PILINK 3 starting DOS programs for the Pi, in DOSBox (needs setup.sh): the
# real PILINK.COM and PI.BAT in C:\PI, as on the Compaq. Checks THERE (a
# file there, one not, a drive that isn't), then RUN: the batch file written,
# PILINK gone with exit code 12, PI.BAT running it, and the batch's last
# line bringing PILINK back by itself with a new hello. Then a batch too
# long for PILINK is refused, and it stays.
# Usage (on the Pi): python3 /tmp/rig/dos_test.py
import os, shutil, sys
sys.path.insert(0, "/tmp/rig")
sys.path.insert(0, "/tmp/rig/lib")
import pilink
import build_disks
import dosbox_link as rig

shutil.rmtree("/tmp/rig/c/PI", ignore_errors=True)
for leftover in ("/tmp/rig/c/RAN.TXT",):
    if os.path.exists(leftover):
        os.remove(leftover)
os.makedirs("/tmp/rig/c/PI")
shutil.copy("/tmp/rig/c/PILINK.COM", "/tmp/rig/c/PI/PILINK.COM")
with open("/tmp/rig/c/PI/PI.BAT", "w", newline="\r\n") as f:
    f.write(build_disks.pi_bat("38400") + "\n")

results = []
link = rig.Link(rig.launch("PATH C:\\;C:\\PI\nPI"))                   # as AUTOEXEC.BAT starts it
hello = link.expect("H", 20)
results.append(rig.check("PI.BAT starts PILINK 3", hello is not None and hello[1][0] == 3, str(hello)))
if not hello:
    sys.exit(1)


def there(name):
    link.send(bytes((pilink.THERE,)) + pilink.word(len(name)) + name.encode())
    answer = link.expect("F", 5)
    return None if answer is None else bool(answer[1])


results.append(rig.check("THERE: C:\\PI\\PILINK.COM is there", there("C:\\PI\\PILINK.COM") is True))
results.append(rig.check("THERE: a wildcard", there("C:\\PI\\*.BAT") is True))
results.append(rig.check("THERE: C:\\NOPE.TXT isn't", there("C:\\NOPE.TXT") is False))
results.append(rig.check("THERE: a drive that isn't there (no question asked)", there("Q:\\X.TXT") is False))

batch = "ECHO OFF\r\nECHO RAN> C:\\RAN.TXT\r\nC:\r\nCD \\PI\r\nPI\r\n"
link.send(bytes((pilink.RUN,)) + pilink.word(len(batch)) + batch.encode())
results.append(rig.check("RUN: PILINK says it's going", link.expect("Q", 10) == ("Q", 0), str(link.inbox)))
again = link.expect("H", 30)
results.append(rig.check("RUN: the batch ran", os.path.exists("/tmp/rig/c/RAN.TXT")))
written = open("/tmp/rig/c/PI/PIRUN.BAT", "rb").read() if os.path.exists("/tmp/rig/c/PI/PIRUN.BAT") else b""
results.append(rig.check("RUN: C:\\PI\\PIRUN.BAT is the batch, byte for byte", written == batch.encode()))
results.append(rig.check("RUN: and PILINK is back by itself", again is not None and again[1][0] == 3, str(again)))

long = "REM " + "X" * 1100 + "\r\n"
link.send(bytes((pilink.RUN,)) + pilink.word(len(long)) + long.encode())
results.append(rig.check("RUN too long: refused", link.expect("E", 10) == ("E", 1), str(link.inbox)))
results.append(rig.check("RUN too long: and it stays", there("C:\\RAN.TXT") is True))

link.send(bytes((pilink.QUIT,)))
link.expect("Q", 5)
print("\n" + ("All passed." if all(results) else f"{results.count(False)} failed."))
sys.exit(0 if all(results) else 1)

#!/usr/bin/env python3
"""Builds the Compaq's floppy disk images, in the 1.2 MB 5.25" format.

Only 1.2 MB: MS-DOS 3.1 and the Portable III's BIOS predate 1.44 MB floppies,
so the GoTEK needs FlashFloppy to present these as the Compaq's own drive.

Runs on the Pi, which has mtools. Expects each download unpacked under
~/build/dos/<name>/files (make-disks.sh does this) and MS-DOS Kermit at
~/build/msk316/files/MSK316.EXE. Every disk gets a README.TXT. File names
are checked against DOS 3.1's 8.3 rule, and text files get CRLF endings.

The Kermit disk also gets PILINK.COM, the Compaq's link to the Pi
(tools/build-pilink.sh builds it into pi/opt/compaq/dos), and PI.BAT, and
its MSKERMIT.INI and SERVE.INI get the cable's speed from
pi/opt/compaq/data/cable-speed, the same file the Pi's end reads. Both are
looked for next to KERMIT_DISK_DIR, as make-disks.sh lays them out.

The boot disk starts from FreeDOS 1.3's own 1.2 MB boot floppy (from
fetch-dos.sh): its boot sector and kernel stay, the installer goes, and the
Kermit disk's files and an AUTOEXEC.BAT that runs PI go on.

Usage: build_disks.py KERMIT_DISK_DIR OUTPUT_DIR
"""

import atexit
import math
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

DOS = Path.home() / "build/dos"
FORMATS = {"1200k": 1200}
CAPACITY = 1_190_000  # bytes of files per disk: 1.2 MB less room for directories
NAME_8_3 = re.compile(r"^[A-Z0-9_$~!#%&'(){}@^`-]{1,8}(\.[A-Z0-9_$~!#%&'(){}@^`-]{1,3})?$")
ENV = dict(os.environ, MTOOLS_NO_VFAT="1", MTOOLS_SKIP_CHECK="1")


def on_disk(size):
    return math.ceil(size / 512) * 512


class Disk:
    def __init__(self, name, label, readme):
        self.name, self.label = name, label
        self.files = []  # (source path, DOS path such as "ZORK/FROTZ.EXE")
        self.texts = {"README.TXT": readme}
        self.base = None       # an image to start from instead of a blank disk (the boot disk)
        self.drop = ()         # what to take off it first ("FREEDOS/" a folder)
        self.reserved = 0      # bytes it keeps (its kernel)
        self.boot_sector = None  # a boot sector to start with (given this disk's geometry: see build)
        self.system = ()       # files made hidden, system and read-only (DOS's own)

    def add(self, source, dest):
        self.files.append((Path(source), dest.upper()))

    def add_dir(self, source_dir, dest_dir="", skip=()):
        for p in sorted(Path(source_dir).iterdir()):
            if p.is_file() and p.name.upper() not in skip:
                self.add(p, f"{dest_dir}/{p.name}" if dest_dir else p.name)

    def add_tree(self, source_dir, dest_dir=""):
        for p in sorted(Path(source_dir).rglob("*")):
            if p.is_file():
                rel = p.relative_to(source_dir).as_posix()
                self.add(p, f"{dest_dir}/{rel}" if dest_dir else rel)

    def text(self, dest, text):
        self.texts[dest.upper()] = text

    def size(self):
        # (a little over for text files that gain CRLF line ends on the way)
        return self.reserved + (sum(on_disk(p.stat().st_size + (p.read_bytes().count(b"\n") if d.endswith((".TXT", ".DOC")) else 0))
                    for p, d in self.files)
                + sum(on_disk(len(t) + t.count("\n")) for t in self.texts.values()))


def dos_text(text, where):
    lines = text.strip("\n").splitlines()
    for line in lines:
        if len(line) > 79:
            sys.exit(f"{where}: line wider than 79 columns: {line!r}")
    return ("\r\n".join(lines) + "\r\n").encode("ascii")


def build(disk, out):
    if disk.size() > CAPACITY:
        sys.exit(f"{disk.name}: {disk.size()} bytes won't fit on a 1.2 MB disk")
    with tempfile.TemporaryDirectory() as tmp:
        files = []
        for n, (source, dest) in enumerate(disk.files):
            # Text that came with a download may have Unix line ends, which
            # DOS's TYPE shows as a staircase: CRLF for those too.
            data = source.read_bytes()
            if dest.endswith((".TXT", ".DOC", ".ME", ".1ST")) and b"\0" not in data:
                fixed = Path(tmp) / f"text{n}"
                fixed.write_bytes(data.replace(b"\r\n", b"\n").replace(b"\n", b"\r\n"))
                source = fixed
            files.append((source, dest))
        for dest, text in disk.texts.items():
            path = Path(tmp) / dest.replace("/", "_")
            path.write_bytes(dos_text(text, f"{disk.name}:{dest}"))
            files.append((path, dest))
        for _, dest in files:
            for part in dest.split("/"):
                if not NAME_8_3.match(part):
                    sys.exit(f"{disk.name}: {dest} isn't a DOS 8.3 name")
        names = [dest for _, dest in files]
        if len(set(names)) != len(names):
            twice = sorted({name for name in names if names.count(name) > 1})
            sys.exit(f"{disk.name}: more than one file would be called {', '.join(twice)}")
        dirs = sorted({"/".join(dest.split("/")[:i])
                       for _, dest in files for i in range(1, dest.count("/") + 1)})
        for fmt, size in FORMATS.items():
            img = out / fmt / f"{disk.name}.img"
            img.parent.mkdir(parents=True, exist_ok=True)
            img.unlink(missing_ok=True)
            if disk.base:
                shutil.copyfile(disk.base, img)
                for gone in disk.drop:
                    mtools("mdeltree" if gone.endswith("/") else "mdel", "-i", img, f"::/{gone.rstrip('/')}")
                mtools("mlabel", "-i", img, f"::{disk.label}")
            else:
                mtools("mformat", "-C", "-f", str(size), *(["-v", disk.label] if disk.label else []),
                       "-i", img, "::")
                if disk.boot_sector:
                    # An older DOS's own boot sector, with this disk's geometry
                    # (the DOS 3.3 parameter block, bytes 0x0B to 0x1D) copied in.
                    # Not mformat -B: it writes a DOS 4 style block, whose serial
                    # number and label land on DOS 3.3's boot code at 0x2A.
                    with open(img, "r+b") as f:
                        made = f.read(512)
                        boot = bytearray(Path(disk.boot_sector).read_bytes()[:512])
                        boot[0x0B:0x1E] = made[0x0B:0x1E]
                        f.seek(0)
                        f.write(boot)
            for d in dirs:
                mtools("mmd", "-i", img, f"::/{d}")
            for src, dest in files:
                mtools("mcopy", "-i", img, src, f"::/{dest}")
            for name in disk.system:
                mtools("mattrib", "-i", img, "+h", "+s", "+r", f"::/{name}")
    print(f"  {disk.name:<26} {disk.size() / 1024:6.0f} KB  {len(disk.files)} files")


def mtools(*args):
    subprocess.run([str(a) for a in args], check=True, env=ENV)


# ---------------------------------------------------------------- the disks

def kermit_disk(kermit_dir):
    project = Path(kermit_dir).parent
    try:
        speed = (project / "pi/opt/compaq/data/cable-speed").read_text().split()[0]
    except (OSError, IndexError):
        speed = "9600"
    readme = (Path(kermit_dir) / "README.TXT").read_text().replace("\r", "")
    settings = (Path(kermit_dir) / "MSKERMIT.INI").read_text().replace("\r", "")
    if "set speed 9600" not in settings:
        sys.exit("MSKERMIT.INI: expected a 'set speed 9600' line to put the cable's speed in")
    serve = (Path(kermit_dir) / "SERVE.INI").read_text().replace("\r", "")
    if "set speed 9600" not in serve:
        sys.exit("SERVE.INI: expected a 'set speed 9600' line to put the cable's speed in")
    disk = Disk("kermit", "KERMIT", readme.replace("9600", speed))
    disk.add(Path.home() / "build/msk316/files/MSK316.EXE", "KERMIT.EXE")
    disk.text("MSKERMIT.INI", settings.replace("9600", speed))
    disk.text("SERVE.INI", serve.replace("9600", speed))
    pilink = project / "pi/opt/compaq/dos/PILINK.COM"
    if not pilink.is_file():
        sys.exit("PILINK.COM is missing: run tools/build-pilink.sh first")
    disk.add(pilink, "PILINK.COM")
    disk.text("PI.BAT", pi_bat(speed))
    disk.text("INSTALL.BAT", install_bat())
    return disk


def pi_bat(speed):
    """PI.BAT: PILINK as the Compaq's terminal, round and round. PILINK's
    exit code says what next: 10 a file transfer (Kermit as a server for
    the Pi's C-Kermit, whose BYE ends it), 12 a DOS program the Pi asked
    for (C:\\PI\\PIRUN.BAT, which PILINK just wrote: it ends by running PI
    again, as MS-DOS 3.1 has no CALL), 1 Ctrl+Alt+Esc (DOS). MS-DOS 3.1
    has no @ECHO OFF, so ECHO OFF shows itself once. PILINK is looked for
    where it's put: here, C:\\PI (INSTALL.BAT's, on the PATH), or the disk
    in A: (typed as A:PI from C:, it moves there). Not finding it would leave
    the exit code at 0, and go round forever."""
    return "\n".join([
        "ECHO OFF",
        "REM The Compaq as the Raspberry Pi's screen and keyboard (README.TXT).",
        "IF EXIST PILINK.COM GOTO LINK",
        "IF EXIST C:\\PI\\PILINK.COM GOTO LINK",
        "IF EXIST A:\\PILINK.COM A:",
        "IF NOT EXIST PILINK.COM GOTO NONE",
        ":LINK",
        f"PILINK {115200 // int(speed)}",
        "IF ERRORLEVEL 13 GOTO DOS",
        "IF ERRORLEVEL 12 GOTO RUN",
        "IF ERRORLEVEL 11 GOTO DOS",
        "IF ERRORLEVEL 10 GOTO FILES",
        "IF ERRORLEVEL 1 GOTO DOS",
        "GOTO LINK",
        ":FILES",
        "KERMIT -f SERVE.INI",
        "GOTO LINK",
        ":RUN",
        "IF NOT EXIST C:\\PI\\PIRUN.BAT GOTO LINK",
        "C:\\PI\\PIRUN",
        ":DOS",
        "ECHO Back at DOS. Type PI to go back to the Raspberry Pi.",
        "GOTO END",
        ":NONE",
        "ECHO No PILINK.COM here: put the Kermit disk in drive A and type A:PI",
        ":END"])


def install_bat():
    """INSTALL.BAT: the Kermit disk onto the hard disk (C:\\PI), and an
    AUTOEXEC.BAT that starts in the Pi, unless one is there already."""
    return "\n".join([
        "ECHO OFF",
        "IF NOT EXIST C:\\PI\\NUL MD C:\\PI",
        "COPY A:\\*.* C:\\PI",
        "IF EXIST C:\\AUTOEXEC.BAT GOTO HAVE",
        "ECHO ECHO OFF> C:\\AUTOEXEC.BAT",
        "ECHO PATH C:\\;C:\\PI>> C:\\AUTOEXEC.BAT",
        "ECHO PI>> C:\\AUTOEXEC.BAT",
        "ECHO Done. The Compaq starts in the Raspberry Pi from now on.",
        "GOTO END",
        ":HAVE",
        "ECHO Copied to C:\\PI. C:\\AUTOEXEC.BAT was there already, so it's unchanged:",
        "ECHO add C:\\PI to its PATH line, and PI as its last line.",
        ":END"])


def boot_disk(kermit):
    """FreeDOS 1.3's 1.2 MB boot floppy, made into one that starts the Pi
    link: the kernel stays where it is (its boot sector finds it by name),
    COMMAND.COM moves to the top, and the rest of the installer goes."""
    image = DOS / "freedos/files/120m/x86BOOT.img"
    if not image.is_file():
        sys.exit("FreeDOS's boot floppy is missing: run fetch-dos.sh")
    parts = Path(tempfile.mkdtemp())
    atexit.register(shutil.rmtree, parts, ignore_errors=True)
    tools = ("COMMAND.COM", "MEM.EXE", "MORE.EXE", "ATTRIB.COM", "DELTREE.COM", "FC.EXE",
             "FDISK.EXE", "FORMAT.EXE", "SYS.COM")
    for name in tools:
        mtools("mcopy", "-n", "-i", image, f"::/FREEDOS/BIN/{name}", parts / name)
    disk = Disk("boot-freedos-pi", "PI-BOOT", """
COMPAQ - RASPBERRY PI BOOT DISK (FreeDOS 1.3)

Starts the Compaq with no DOS of its own, and goes straight to the
Raspberry Pi: with this disk in the drive (the GoTEK), switch on.

WHAT'S ON IT
  KERNEL.SYS, COMMAND.COM  FreeDOS 1.3 (free software, GPL: freedos.org,
                           where its source is)
  PI.BAT, PILINK.COM       the link to the Pi, as on the Kermit disk
  KERMIT.EXE, *.INI        MS-DOS Kermit, for file transfers and the old
                           way in (see the Kermit disk's README.TXT)
  FREEDOS\\                 a few FreeDOS tools: MEM, MORE, ATTRIB,
                           DELTREE, FC; and FDISK, FORMAT and SYS for
                           setting up a new hard disk or CF card (they
                           erase disks: only on one that's blank)

When it starts it runs PI. Ctrl+Alt+Esc leaves the Pi for the DOS prompt;
type PI to go back. Files sent from the Pi arrive on this disk.

If the Compaq stops with a 162 error first, its clock battery is flat and
it has forgotten its settings: the message says which key carries on.
""")
    disk.base, disk.reserved = image, on_disk(46485)
    disk.drop = ("FREEDOS/", "FDAUTO.BAT", "FDCONFIG.SYS", "SETUP.BAT")
    disk.add(parts / "COMMAND.COM", "COMMAND.COM")
    for name in tools[1:]:
        disk.add(parts / name, f"FREEDOS/{name}")
    for source, dest in kermit.files:
        disk.add(source, dest)
    for dest, text in kermit.texts.items():
        if dest != "README.TXT":
            disk.text(dest, text)
    disk.text("FDCONFIG.SYS", "\n".join([
        "FILES=20",
        "BUFFERS=20",
        "LASTDRIVE=Z",
        "SHELL=A:\\COMMAND.COM A:\\ /E:1024 /P=A:\\AUTOEXEC.BAT"]))
    disk.text("AUTOEXEC.BAT", "\n".join([
        "@ECHO OFF",
        "PATH A:\\;A:\\FREEDOS",
        "ECHO.",
        "ECHO   Started from the Pi's FreeDOS boot disk. Connecting to the Pi:",
        "ECHO   Ctrl+Alt+Esc comes back to this DOS prompt; PI goes back.",
        "ECHO.",
        "PI"]))
    return disk


def pcjs_image(path):
    """A disk image from the PCjs archive's JSON format: each sector's bytes
    as 32-bit numbers, a repeated tail left off. Checked against the MD5
    the file gives."""
    import hashlib
    import json
    import struct
    data = json.loads(Path(path).read_text())
    out = bytearray()
    for cylinder in data["diskData"]:
        for head in cylinder:
            for sector in sorted(head, key=lambda s: s["s"]):
                words = list(sector.get("d", []))
                count = sector["l"] // 4
                words += [words[-1] if words else 0] * (count - len(words))
                out += b"".join(struct.pack("<i", w) for w in words[:count])
    if hashlib.md5(out).hexdigest() != data["imageInfo"]["hash"]:
        sys.exit(f"{path}: the disk didn't come out as PCjs says it should")
    return bytes(out)


def compaq_setup_disk():
    """Compaq's User Diagnostics 5.08 and SETUP 5.05 (360 KB, January 1988)
    made into a 1.2 MB disk that boots the same way: its own boot sector
    (DOS 3.3's, given the 1.2 MB geometry), and its DOS files first in the
    directory and on the disk, as that boot sector needs (so no volume
    label either: it would take the first directory entry)."""
    source = DOS / "compaq-diag/COMPAQ-DIAGS-508-012988-REVK.json"
    if not source.is_file():
        sys.exit("Compaq's diagnostics disk is missing: run fetch-dos.sh")
    parts = Path(tempfile.mkdtemp())
    atexit.register(shutil.rmtree, parts, ignore_errors=True)
    image = parts / "diags-360k.img"
    image.write_bytes(pcjs_image(source))
    (parts / "boot.bin").write_bytes(image.read_bytes()[:512])
    names = ["IBMBIO.COM", "IBMDOS.COM", "COMMAND.COM", "AUTOEXEC.BAT", "CONFIG.SYS", "DISKCOPY.COM",
             "ROMREV.COM", "USER.EXE", "TEST.COM", "SETUP.EXE", "README.CPQ", "1.BAT", "2.BAT", "3.BAT",
             "TEST.SCR", "SETUP.SCR", "ROMREV.SCR"]
    for name in names:
        mtools("mcopy", "-n", "-i", image, f"::/{name}", parts / name)
    disk = Disk("compaq-setup", None, """
COMPAQ USER DIAGNOSTICS 5.08 AND SETUP 5.05 (January 1988)

Compaq's own diagnostics diskette for its 286 and 386 machines, from the
PCjs archive (pcjs.org), made into a 1.2 MB disk for this drive. It starts
Compaq's DOS 3.3 and shows Compaq's notes.

SETUP sets the CMOS memory the clock battery keeps: the hard disk's type
(Compaq's 20 MB drive is Type 2), the floppy drive (1.2 MB), the memory,
the date and time. Type SETUP and press Enter. TEST runs the diagnostics.

With a flat clock battery the settings last until the Compaq is switched
off: restarting with Ctrl+Alt+Del keeps them.
""")
    disk.boot_sector = parts / "boot.bin"
    disk.system = ("IBMBIO.COM", "IBMDOS.COM")
    for name in names:
        disk.add(parts / name, name)
    return disk


def games1_disk():
    disk = Disk("games-zork-zzt-digger", "GAMES1", """
CLASSIC GAMES 1: ZORK I-III, ZZT, DIGGER

ZORK I, II AND III (Infocom, 1980-82)
  The famous text adventures. Microsoft released them free (MIT license) in
  2025. They run in Frotz 2.55 (free software, GPL).
  A:\\> CD \\ZORK    then type  ZORK1   (or ZORK2, ZORK3)
  Type commands like OPEN MAILBOX, GO NORTH, TAKE LAMP. SAVE keeps your place.

ZZT (Tim Sweeney, Epic MegaGames, 1991)
  Adventure game and game-maker, with all six original worlds. Freeware
  since 1997.
  A:\\> CD \\ZZT     then type  ZZT

DIGGER REMASTERED (Windmill Software 1983, remastered by Andrew Jenner)
  Dig tunnels, collect emeralds, dodge monsters. Free software (GPL).
  A:\\> CD \\DIGGER  then type  DIGGER /C     (/C = CGA graphics)

TO COPY A GAME TO THE HARD DISK, for example Zork:
  MD C:\\ZORK
  COPY A:\\ZORK\\*.* C:\\ZORK
""")
    frotz = DOS / "frotz/files/frotz255"
    for name in ("frotz.exe", "frotz.txt", "howto.txt", "COPYING.txt"):
        disk.add(frotz / name, f"ZORK/{name}")
    for n in (1, 2, 3):
        disk.add(Path(f"/var/lib/compaq/games/zork{n}.z3"), f"ZORK/ZORK{n}.Z3")
        disk.text(f"ZORK/ZORK{n}.BAT", f"FROTZ ZORK{n}.Z3")
    disk.add_dir(DOS / "zzt/files", "ZZT")
    disk.add_dir(DOS / "digger/files", "DIGGER")
    return disk


KROZ_GAMES = [  # (folder in krozfree.zip, folder on disk, program, title)
    ("1987 - Kingdom Of Kroz", "KINGDOM", "KINGDOM", "Kingdom of Kroz (1987)"),
    ("1988 - Caverns Of Kroz", "CAVERNS", "CAVERNS", "Caverns of Kroz (1988)"),
    ("1989 - Dungeons Of Kroz", "DUNGEONS", "DUNGEONS", "Dungeons of Kroz (1989)"),
    ("1989 - Castle Of Kroz", "CASTLE", "CASTLE", "Castle of Kroz (1989)"),
    ("1990 - Kingdom Of Kroz 2", "KINGDOM2", "KINGDOM", "Kingdom of Kroz II (1990)"),
    ("1990 - Caverns Of Kroz 2", "CAVERNS2", "CAVERNS", "Caverns of Kroz II (1990)"),
    ("1990 - Dungeons Of Kroz 2", "DUNGEON2", "DUNGEONS", "Dungeons of Kroz II (1990)"),
    ("1990 - Super Kroz Trilogy/1990 - Return To Kroz", "RETURN", "RETURN",
     "Return to Kroz (1990)"),
    ("1990 - Super Kroz Trilogy/1990 - Temple Of Kroz", "TEMPLE", "TEMPLE",
     "Temple of Kroz (1990)"),
    ("1990 - Super Kroz Trilogy/1990 - The Final Crusade Of Kroz", "CRUSADE", "CRUSADE",
     "The Final Crusade of Kroz (1990)"),
    ("1990 - Shrine Of Kroz", "SHRINE", "SHRINE", "Shrine of Kroz (1990)"),
    ("1990 - The Lost Adventures Of Kroz", "LOST", "LOST", "The Lost Adventures of Kroz"),
    ("1990 - Hints For Kroz", "HINTS", "KROZHINT", "Hints for every Kroz game"),
]


def kroz_disk():
    lines = [f"  {title:<36} CD \\KROZ\\{folder:<9} then {program}"
             for _, folder, program, title in KROZ_GAMES]
    disk = Disk("games-kroz", "KROZ", """
THE KROZ SERIES (Scott Miller, Apogee Software, 1987-1990)

Find your way through dungeons full of monsters, gems and secrets. Kroz was
one of Apogee's first games. Freeware since 2009 (source code under the GPL).

""" + "\n".join(lines) + "\n\nEach game explains its keys when it starts.")
    root = DOS / "kroz/files"
    disk.add(root / "readme.txt", "KROZ/README.TXT")
    for source, folder, _, _ in KROZ_GAMES:
        disk.add_dir(root / source, f"KROZ/{folder}", skip={"LOSTDEMO.EXE"})
    return disk


def adventures_disk():
    disk = Disk("games-supernova-titanic", "ADVENTURES", """
TEXT ADVENTURES BY SCOTT MILLER (Apogee Software)

SUPERNOVA (1987)
  A science-fiction text adventure.
  A:\\> CD \\SUPERNOV  then type  NOVA

BEYOND THE TITANIC (1986)
  It begins aboard the sinking Titanic.
  A:\\> CD \\TITANIC   then type  BEYOND

Both are freeware since 1998, with source code under the GPL since 2009.
To read how to play:  TYPE INSTRUCT.TXT | MORE
""")
    disk.add_dir(DOS / "supernova/files", "SUPERNOV")
    disk.add_dir(DOS / "titanic/files", "TITANIC")
    return disk


def office_disk():
    disk = Disk("office-aseasy-gwbasic", "OFFICE", """
OFFICE: AS-EASY-AS 5.7 SPREADSHEET, GW-BASIC

AS-EASY-AS 5.7 (TRIUS, Inc.)
  A Lotus 1-2-3 compatible spreadsheet. It needs a 286, MS-DOS 3.1 and
  512 KB, exactly the Compaq. TRIUS made full licenses free in 2011.
  To install it on the hard disk (needs about 1.2 MB):
    A:\\> INSTALL
  When asked for a serial number, type:  570-110-0424-3
  Any name works for the name and company. That number is TRIUS's own free
  license, published on its forum.

GW-BASIC (Microsoft, 1983)
  The classic BASIC. This is TK Chia's rebuild of the source Microsoft
  released under the MIT license in 2020: an early release, and without
  serial port support.
  A:\\> CD \\GWBASIC  then type  GWBASIC     (SYSTEM returns to DOS)

VISICALC (Dan Bricklin and Bob Frankston, 1979; this IBM PC version 1981)
  The first spreadsheet. Hosted by Dan Bricklin with permission from Lotus,
  which owns it: for personal use only, so please don't share copies.
  A:\\> CD \\VISICALC  then type  VC     (/ opens the commands; /SQY quits)
""")
    disk.add_dir(DOS / "asa/files")
    disk.add_dir(DOS / "gwbasic/files/DEVEL/GWBASIC", "GWBASIC")
    disk.add(DOS / "visicalc/files/VC.COM", "VISICALC/VC.COM")
    return disk


BORLAND = [  # (download, image name, label, title, what it is)
    ("tp55", "turbo-pascal55", "TP55", "TURBO PASCAL 5.5 (Borland, 1989)",
     "Borland's famous Pascal compiler, with its full-screen editor."),
    ("tc201", "turbo-c201", "TC201", "TURBO C 2.01 (Borland, 1989)",
     "Borland's C compiler, with its full-screen editor."),
]


def borland_disks():
    disks = []
    for download, image, label, title, about in BORLAND:
        sources = sorted((DOS / download / "files").iterdir())
        for n, source in enumerate(sources, 1):
            disk = Disk(f"{image}-disk{n}", f"{label}-{n}", f"""
{title} - DISK {n} OF {len(sources)}

{about}
Free from Embarcadero's "Antique Software" museum for personal use only,
so please don't share copies.

These are the original disks, so Borland's installer works as it did in
1989: put disk 1 in drive A: and type  A:INSTALL
""")
            disk.add_tree(source)
            disks.append(disk)
    return disks


def word_cleanup(subdirs):
    """WORDDEL.BAT: removes C:\\WORDSRC. DOS 3.1 has no DELTREE, and DEL *.*
    asks "Are you sure?", which ECHO Y answers. (No IF on the DEL lines: DOS
    splits a line at the pipe before IF runs, so it couldn't guard them.)"""
    bat = ["ECHO OFF",
           "C:",
           "CD \\",
           "ECHO This deletes C:\\WORDSRC, Word's setup files (Word itself stays).",
           "ECHO Press Ctrl-C now to cancel, or",
           "PAUSE"]
    for folder in subdirs:
        bat += [f"ECHO Y| DEL C:\\WORDSRC\\{folder}\\*.*",
                f"IF EXIST C:\\WORDSRC\\{folder}\\NUL RD C:\\WORDSRC\\{folder}"]
    bat += ["ECHO Y| DEL C:\\WORDSRC\\*.*",
            "IF EXIST C:\\WORDSRC\\NUL RD C:\\WORDSRC",
            "ECHO Done."]
    return "\n".join(bat)


def word_disks():
    root = DOS / "word55/files"
    subdirs = sorted(p.name for p in root.iterdir() if p.is_dir())
    items = [(p, p.name) for p in sorted(root.iterdir()) if p.is_file()]
    for sub in subdirs:
        items += [(p, f"{sub}/{p.name}") for p in sorted((root / sub).iterdir()) if p.is_file()]

    groups, group, size = [], [], 0
    for path, dest in items:
        need = on_disk(path.stat().st_size)
        if size + need > CAPACITY - 8192:  # leave room for README and COPYDISK
            groups.append(group)
            group, size = [], 0
        group.append((path, dest))
        size += need
    groups.append(group)

    disks, count = [], len(groups)
    for n, group in enumerate(groups, 1):
        last = n == count
        disk = Disk(f"word55-disk{n}", f"WORD55-{n}", f"""
MICROSOFT WORD 5.5 FOR DOS - DISK {n} OF {count}

Microsoft made Word 5.5 free in 1999. These {count} disks hold its setup
files, which Setup needs together in one folder on the hard disk
(about 4 MB, plus room for Word itself).

1. Put each disk in drive A:, from disk 1 to disk {count}, and type
     A:COPYDISK
   Each one is copied into C:\\WORDSRC.
2. Then type   C:   then   CD \\WORDSRC   then   SETUP
   Word includes a driver for the Compaq's plasma screen (COMPAQ3): pick
   the Compaq display if Setup offers it, otherwise CGA.
3. Once Word is installed, free the space: put disk {count} in drive A:
   and type  A:WORDDEL  (it deletes C:\\WORDSRC and its folders).
""")
        for path, dest in group:
            disk.add(path, dest)
        folders = sorted({dest.split("/")[0] for _, dest in group if "/" in dest})
        bat = ["ECHO OFF",
               f"ECHO Copying Word 5.5 disk {n} of {count} to C:\\WORDSRC",
               "IF NOT EXIST C:\\WORDSRC\\NUL MD C:\\WORDSRC",
               "COPY A:\\*.* C:\\WORDSRC"]
        for folder in folders:
            bat += [f"IF NOT EXIST C:\\WORDSRC\\{folder}\\NUL MD C:\\WORDSRC\\{folder}",
                    f"COPY A:\\{folder}\\*.* C:\\WORDSRC\\{folder}"]
        if last:
            bat += ["ECHO All disks copied. Now type  C:  then  CD \\WORDSRC  then  SETUP"]
        else:
            bat += [f"ECHO Disk {n} done. Put in disk {n + 1} and type  A:COPYDISK"]
        disk.text("COPYDISK.BAT", "\n".join(bat))
        if last:
            disk.text("WORDDEL.BAT", word_cleanup(subdirs))
        disks.append(disk)
    return disks


def doom_disks():
    """Doom8088: real Doom (the shareware first episode) for 16-bit PCs. Its
    data file is too big for one 1.2 MB disk, so it's split across two, and
    INSTALL.BAT joins it back up on the hard disk. (INSTALL.BAT runs a second
    batch file from C: before asking for disk 2: DOS reads a batch file from
    its disk line by line, so swapping disks under it would stop it.)"""
    src = DOS / "doom8088/files"
    wad = (src / "DOOM4.WAD").read_bytes()
    parts = Path(tempfile.mkdtemp())
    atexit.register(shutil.rmtree, parts, ignore_errors=True)
    first = 760_000
    (parts / "DOOM4.W1").write_bytes(wad[:first])
    (parts / "DOOM4.W2").write_bytes(wad[first:])
    about = """
DOOM8088 - REAL DOOM ON A 286 - DISK {n} OF 2

Doom (id Software, 1993) needs a 386. Doom8088 is a port of it for 16-bit
PCs like this Compaq: the shareware first episode, Knee-Deep in the Dead,
with PC speaker sound. By Frenkel Smeijers; free software (GPL), source at
github.com/FrenkelS/Doom8088. The shareware game data is id Software's.

It needs the hard disk (about 1.8 MB free): the game data doesn't fit on
one floppy.

TO INSTALL: put disk 1 in drive A: and type  A:INSTALL
TO PLAY:    C:   then   CD \\DOOM   then   DOOM
            DOOM is the crisp 640x200 two-color version, best on the plasma.
            DOOMCGA is the 4-color version (shades of amber; F5: palette).

KEYS: arrows walk and turn, Ctrl fires, Space opens doors, Alt strafes,
Shift runs, Tab shows the map, Esc is the menu, F10 quits to DOS.
IDDQD and IDKFA work, of course.
"""
    disk1 = Disk("doom8088-disk1", "DOOM-1", about.format(n=1))
    disk1.add(src / "D286CBW.EXE", "D286CBW.EXE")
    disk1.add(src / "D286CGA.EXE", "D286CGA.EXE")
    disk1.add(src / "README.TXT", "DOOM8088.TXT")
    disk1.add(parts / "DOOM4.W1", "DOOM4.W1")
    disk1.text("INSTALL.BAT", "\n".join([
        "ECHO OFF",
        "ECHO Installing Doom8088 in C:\\DOOM (it needs about 1.8 MB free)",
        "IF NOT EXIST C:\\DOOM\\NUL MD C:\\DOOM",
        "COPY A:\\D286CBW.EXE C:\\DOOM",
        "COPY A:\\D286CGA.EXE C:\\DOOM",
        "COPY A:\\DOOM8088.TXT C:\\DOOM",
        "COPY A:\\DOOM4.W1 C:\\DOOM",
        "COPY A:\\DOOM.BAT C:\\DOOM",
        "COPY A:\\DOOMCGA.BAT C:\\DOOM",
        "COPY A:\\INSTALL2.BAT C:\\DOOM",
        "C:",
        "CD \\DOOM",
        "INSTALL2"]))
    disk1.text("INSTALL2.BAT", "\n".join([
        "ECHO OFF",
        "ECHO Now take out disk 1, put DOOM disk 2 in drive A:, and",
        "PAUSE",
        "COPY A:\\DOOM4.W2 C:\\DOOM",
        "IF NOT EXIST DOOM4.W2 GOTO FAILED",
        "COPY /B DOOM4.W1+DOOM4.W2 DOOM4.WAD",
        "IF NOT EXIST DOOM4.WAD GOTO FAILED",
        "DEL DOOM4.W1",
        "DEL DOOM4.W2",
        "ECHO Done! Type  DOOM  to play (here in C:\\DOOM).",
        "GOTO END",
        ":FAILED",
        "ECHO Disk 2's game data didn't arrive. Put DOOM disk 2 in drive A: and",
        "ECHO type  INSTALL2  to try again.",
        ":END"]))
    disk1.text("DOOM.BAT", "D286CBW %1 %2 %3")
    disk1.text("DOOMCGA.BAT", "D286CGA %1 %2 %3")
    disk2 = Disk("doom8088-disk2", "DOOM-2", about.format(n=2))
    disk2.add(parts / "DOOM4.W2", "DOOM4.W2")
    return [disk1, disk2]


def main():
    kermit_dir, out = sys.argv[1], Path(sys.argv[2])
    kermit = kermit_disk(kermit_dir)
    disks = [kermit, boot_disk(kermit), compaq_setup_disk(), games1_disk(), kroz_disk(), adventures_disk(),
             office_disk(), *borland_disks(), *word_disks(), *doom_disks()]
    for disk in disks:
        build(disk, out)


if __name__ == "__main__":
    main()

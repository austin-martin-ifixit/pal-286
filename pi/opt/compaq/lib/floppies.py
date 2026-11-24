#!/usr/bin/env python3
"""The Compaq's floppy drive, from the Pi: which disk the GoTEK has in it.

A Raspberry Pi Zero W, plugged into the GoTEK where its USB stick would go,
pretends to be that stick, with a library of disk images behind it (see
zero/floppy and zero/README.md in the project folder). This asks it, over
Wi-Fi, to put a disk in the drive or take it out; it can also make a disk
from files on the Pi, and copy what the Compaq saved on one back to the Pi.
The key it uses (/etc/compaq/gotek-key) can do nothing else on the Zero.

Usage: floppies.py              the menu (Transfer files, then 3)
       floppies.py status       one line: what's in the drive (for setup-zero.sh)
"""

import os
import re
import shutil
import subprocess
import sys
import tempfile
try:
    import readline  # noqa: F401  (line editing at the prompts)
except ImportError:
    pass

ZERO = os.environ.get("GOTEK_ZERO", "compaq@gotek.local")
KEY = os.environ.get("GOTEK_KEY", "/etc/compaq/gotek-key")
KNOWN = "/etc/compaq/gotek-known-hosts"
FILES = os.path.expanduser("~/compaq-files")
NAME = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")
CAPACITY = 1_150_000                    # bytes of files a 1.2 MB disk takes, with room for its directory
MTOOLS = dict(os.environ, MTOOLS_SKIP_CHECK="1", MTOOLS_NO_VFAT="1")


class NotThere(Exception):
    """The Zero couldn't be asked, or said no: the message says why."""


def ask(*words, data=None, timeout=90):
    """Runs floppy WORDS on the Zero; returns what it printed (bytes)."""
    if not os.path.exists(KEY):
        raise NotThere("The floppy library isn't set up: it needs the Pi Zero (README: "
                       "'The Pi Zero as the GoTEK's USB stick').")
    try:
        done = subprocess.run(["ssh", "-i", KEY, "-o", "IdentitiesOnly=yes", "-o", "BatchMode=yes",
                               "-o", f"UserKnownHostsFile={KNOWN}", "-o", "StrictHostKeyChecking=accept-new",
                               "-o", "ConnectTimeout=10", ZERO, "floppy " + " ".join(words)],
                              input=data, capture_output=True, timeout=timeout)
    except subprocess.TimeoutExpired as e:
        raise NotThere("The Pi Zero took too long to answer.") from e
    if done.returncode == 255:
        raise NotThere("The Pi Zero isn't answering. Is it plugged into the GoTEK, and on the Wi-Fi?")
    if done.returncode != 0:
        message = done.stderr.decode(errors="replace").strip().removeprefix("floppy: ")
        raise NotThere("The floppy library said: " + (message[:150] or "no."))
    return done.stdout


def disks():
    """[(name, size, in the drive?)]"""
    found = []
    for line in ask("list").decode(errors="replace").splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and NAME.match(parts[0]):
            found.append((parts[0], parts[1], bool(parts[2])))
    return found


def in_drive():
    return ask("status").decode(errors="replace").strip().removeprefix("in the drive: ")


def dos_name(name, taken):
    """name as DOS 3.1 writes it: 8 letters, a dot and 3, upper case, and
    not one already in taken (which it joins). mtools would add a long name
    beside a short one, which DOS 3.1 shows as a stray entry."""
    base, ext = (name.rsplit(".", 1) if "." in name.strip(".") else (name, ""))
    def clean(part):
        return re.sub(r"[^A-Z0-9!#$%&'()@^_`{}~-]", "", part.upper())
    base, ext = clean(base) or "FILE", clean(ext)[:3]
    candidate, number = base[:8] + ("." + ext if ext else ""), 1
    while candidate in taken:
        tail = f"~{number}"
        candidate, number = base[:8 - len(tail)] + tail + ("." + ext if ext else ""), number + 1
    taken.add(candidate)
    return candidate


def make_disk(paths, label):
    """A 1.2 MB DOS disk (image bytes) holding paths, under 8.3 names."""
    with tempfile.TemporaryDirectory() as work:
        image = os.path.join(work, "disk.img")
        label = re.sub(r"[^A-Z0-9_-]", "", label.upper())[:11] or "PI"
        subprocess.run(["mformat", "-i", image, "-f", "1200", "-C", "-v", label, "::"],
                       check=True, capture_output=True, env=MTOOLS)
        taken = set()
        for path in paths:
            subprocess.run(["mcopy", "-i", image, path, "::" + dos_name(os.path.basename(path), taken)],
                           check=True, capture_output=True, env=MTOOLS)
        with open(image, "rb") as f:
            return f.read()


def copy_off(image, folder):
    """The files on a disk image into folder; returns their names."""
    os.makedirs(folder, exist_ok=True)
    with tempfile.TemporaryDirectory() as work:
        path = os.path.join(work, "disk.img")
        with open(path, "wb") as f:
            f.write(image)
        subprocess.run(["mcopy", "-s", "-n", "-o", "-i", path, "::*", folder], capture_output=True, env=MTOOLS)
    return sorted(os.listdir(folder))


# ---------------------------------------------------------------- the menu

def pick(prompt, count):
    try:
        answer = input(prompt).strip()
    except EOFError:
        return None
    return int(answer) if answer.isdigit() and len(answer) <= 3 and 1 <= int(answer) <= count else None


def put_in():
    found = disks()
    if not found:
        print("\n  The library has no disks yet (zero/setup-zero.sh puts the Compaq's in).")
        return
    print()
    for n, (name, size, here) in enumerate(found, 1):
        print(f"   {n:>2}. {name:<34} {size:>7}{'   (in the drive)' if here else ''}")
    choice = pick("\n  Which disk (a number; Enter: none)? ", len(found))
    if choice:
        print("  Putting it in...", flush=True)
        ask("insert", found[choice - 1][0])
        print(f"  Done: {found[choice - 1][0]} is in the Compaq's drive. To the Compaq it's a")
        print("  new disk: DIR A: shows what's on it.")


def from_files():
    folders = sorted(d for d in os.listdir(FILES) if os.path.isdir(os.path.join(FILES, d))
                     and not d.startswith(".") and d != "repair-queue") if os.path.isdir(FILES) else []
    if not folders:
        print("\n  There's nothing in ~/compaq-files to put on a disk.")
        return
    print()
    for n, folder in enumerate(folders, 1):
        count = len([f for f in os.listdir(os.path.join(FILES, folder)) if not f.startswith(".")])
        print(f"   {n:>2}. {folder:<30} {count} files")
    choice = pick("\n  Which folder goes on the disk (a number; Enter: none)? ", len(folders))
    if not choice:
        return
    folder = os.path.join(FILES, folders[choice - 1])
    paths = sorted(os.path.join(folder, f) for f in os.listdir(folder)
                   if not f.startswith(".") and os.path.isfile(os.path.join(folder, f)))
    kept, total = [], 0
    for path in paths:
        if total + os.path.getsize(path) <= CAPACITY:
            kept.append(path)
            total += os.path.getsize(path)
    if not kept:
        print("  Those files don't fit on a 1.2 MB floppy.")
        return
    name = folders[choice - 1].lower()
    name = re.sub(r"[^a-z0-9-]+", "-", name).strip("-")[:30] or "from-pi"
    print(f"  Making the disk \"{name}\" ({len(kept)} of {len(paths)} files, {total // 1024} KB)...", flush=True)
    ask("put", name, data=make_disk(kept, name))
    ask("insert", name)
    print("  Done: it's in the Compaq's drive. Long names were shortened to DOS's 8.3.")


def copy_back():
    name = in_drive()
    if not name or name == "nothing":
        print("\n  There's no disk in the drive.")
        return
    print(f"\n  Copying what's on \"{name}\" to the Pi...", flush=True)
    folder = os.path.join(FILES, "from-floppy", name)
    names = copy_off(ask("get", name), folder)
    print(f"  Done: {len(names)} files in ~/compaq-files/from-floppy/{name}")
    for line in names[:12]:
        print(f"     {line}")
    if len(names) > 12:
        print(f"     and {len(names) - 12} more")


def menu():
    while True:
        print("\033[H\033[2J", end="")
        print("\n  THE COMPAQ'S FLOPPY DRIVE           the GoTEK, its disks chosen by the Pi\n")
        try:
            print(f"  In the drive now: {in_drive()}\n")
        except NotThere as e:
            print(f"  {e}\n")
            input("  Press Enter to return to the menu. ")
            return
        print("     1.  Put a disk in the drive")
        print("     2.  Take the disk out")
        print("     3.  Make a disk from a folder of files on the Pi (~/compaq-files)")
        print("     4.  Copy the files on the disk in the drive to the Pi")
        print("     0.  Back to the menu\n")
        try:
            choice = input("  Type a number, then press Enter: ").strip()
        except EOFError:
            return
        try:
            if choice == "1":
                put_in()
            elif choice == "2":
                ask("eject")
                print("\n  Done: the drive is empty.")
            elif choice == "3":
                from_files()
            elif choice == "4":
                copy_back()
            else:
                return
        except NotThere as e:
            print(f"\n  {e}")
        input("\n  Press Enter. ")


def main():
    if sys.argv[1:] == ["status"]:
        try:
            print(f"The Pi asked the Zero: in the drive: {in_drive()}")
        except NotThere as e:
            sys.exit(str(e))
        return
    if len(sys.argv) == 3 and sys.argv[1] == "insert":        # (PAL, through voice-open)
        try:
            ask("insert", sys.argv[2])
        except NotThere as e:
            sys.exit(str(e))
        print(f"Done: {sys.argv[2]} is in the Compaq's floppy drive (its A: drive).")
        return
    menu()


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print()

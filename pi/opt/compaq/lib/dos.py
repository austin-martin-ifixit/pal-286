#!/usr/bin/env python3
"""DOS programs on the Compaq itself, started by the Pi.

Pictures the Pi draws crawl over the Compaq's cable (38400 baud: under 4,000
bytes a second), but a program running on the 286 draws as fast as the 286
can. The Pi stays in charge: it asks the serial bridge, PILINK (3, as the
Compaq's terminal) writes the batch file it's given as C:\\PI\\PIRUN.BAT and
goes to DOS to run it, and the batch ends by starting PI again, so the menu
here carries on. A program not on the Compaq's hard disk yet is put there
first, from its floppies in the GoTEK (the Pi Zero puts each one in).

Usage: dos.py play NAME     (doom)
Exit codes: 0 played (or the person went back), 1 it couldn't, 3 this
screen can't run DOS programs at all (the caller has another way).
"""

import json
import os
import socket
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import floppies  # noqa: E402

SOCKET = os.environ.get("COMPAQ_BRIDGE", "/run/compaq-serial/bridge.sock")   # the serial bridge
BACK = "C:\nCD \\PI\nPI\n"          # how every batch ends: PI again, from its own folder

GAMES = {
    "doom": {
        "title": "Doom8088",
        "check": "C:\\DOOM\\DOOM4.WAD",
        "intro": ["Real Doom (id Software, 1993), run by the Compaq's own 286: Doom8088",
                  "by Frenkel Smeijers, the shareware first episode, with PC speaker",
                  "sound. Arrows walk and turn, Ctrl fires, Space opens doors."],
        "quit": "F10",
        "play": "C:\nCD \\DOOM\nD286CBW\n",
        # (the game data is too big for one 1.2 MB floppy: build_disks.py splits it in two)
        "install": [("doom8088-disk1", "IF NOT EXIST C:\\DOOM\\NUL MD C:\\DOOM\n"
                                       "COPY A:\\D286CBW.EXE C:\\DOOM\nCOPY A:\\D286CGA.EXE C:\\DOOM\n"
                                       "COPY A:\\DOOM8088.TXT C:\\DOOM\nCOPY A:\\DOOM4.W1 C:\\DOOM\n"),
                    ("doom8088-disk2", "COPY A:\\DOOM4.W2 C:\\DOOM\nC:\nCD \\DOOM\n"
                                       "COPY /B DOOM4.W1+DOOM4.W2 DOOM4.WAD\n"
                                       "IF EXIST DOOM4.WAD DEL DOOM4.W1\nIF EXIST DOOM4.WAD DEL DOOM4.W2\n")],
    },
}


class Unavailable(Exception):
    """The Pi can't start DOS programs on this screen (the message says why)."""


def ask(request):
    """One request to the bridge; returns (its first answer, the connection)."""
    conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
    try:
        conn.connect(SOCKET)
        conn.sendall((json.dumps(request) + "\n").encode())
        answers = conn.makefile()
        return json.loads(answers.readline() or "{}"), answers
    except (OSError, ValueError) as e:
        conn.close()
        raise Unavailable("The Compaq isn't connected.") from e


def there(name):
    """Is that file on the Compaq's disks?"""
    answer, answers = ask({"op": "there", "name": name})
    answers.close()
    if not answer.get("ok"):
        raise Unavailable(answer.get("message", "No answer from the bridge."))
    return bool(answer.get("there"))


def run(batch, title):
    """Has DOS run batch on the Compaq; returns once PI is back. False if
    it couldn't start."""
    answer, answers = ask({"op": "run", "title": title, "batch": "ECHO OFF\n" + batch + BACK})
    try:
        if not answer.get("ok"):
            print(f"  {answer.get('message', 'No answer from the bridge.')}")
            return False
        for line in answers:                       # (until the bridge says PI is back)
            if json.loads(line).get("back"):
                break
        return True
    finally:
        answers.close()


def install(game):
    print(f"\n  {game['title']} isn't on the Compaq's hard disk yet: putting it there from its")
    print(f"  {len(game['install'])} floppies (a few minutes; watch the Compaq's screen).", flush=True)
    for n, (disk, batch) in enumerate(game["install"], 1):
        print(f"  Floppy {n}: in the drive...", flush=True)
        try:
            floppies.ask("insert", disk)
        except floppies.NotThere as e:
            print(f"  {e}")
            return False
        print(f"  Floppy {n}: copying...", flush=True)
        if not run(batch, f"installing {game['title']}"):
            return False
    try:
        floppies.ask("eject")                      # (a game disk left in A: stops the Compaq starting)
    except floppies.NotThere:
        pass
    return True


def back_to_menu():
    try:
        input("\n  Press Enter to return to the menu. ")
    except EOFError:
        pass


def play(name):
    game = GAMES[name]
    try:
        installed = there(game["check"])
    except Unavailable:
        return 3
    print(f"\n  {game['title'].upper()}, ON THE COMPAQ ITSELF\n")
    for line in game["intro"]:
        print(f"  {line}")
    print(f"  To come back here: {game['quit']}.\n")
    try:
        if input("  Press Enter to start, or 0 to go back: ").strip() == "0":
            return 0
    except EOFError:
        return 0
    try:
        if not installed and not (install(game) and there(game["check"])):
            print(f"\n  {game['title']} didn't get onto the Compaq's disk.")
            back_to_menu()
            return 1
        print(f"\n  {game['title']} is running on the Compaq. To come back: {game['quit']}.", flush=True)
        if not run(game["play"], game["title"]):
            back_to_menu()
            return 1
    except Unavailable as e:
        print(f"\n  {e}")
        back_to_menu()
        return 1
    return 0


def main():
    if len(sys.argv) != 3 or sys.argv[1] != "play" or sys.argv[2] not in GAMES:
        sys.exit(__doc__.strip())
    sys.exit(play(sys.argv[2]))


if __name__ == "__main__":
    main()

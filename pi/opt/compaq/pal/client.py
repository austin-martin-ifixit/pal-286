#!/usr/bin/env python3
"""The Compaq menu's side of PAL 286: teach it a face, make it forget one,
quiet mode, its voice, a voice test and status. Talks to compaq-pal.service over its
socket; PAL's own files (faces, notes, the Claude key) stay out of reach of
the shared session.

Usage: client.py enroll | forget | quiet | voice | status | about | gallery | jukebox
"""

import json
import os
import select
import socket
import sys
import termios
import tty
try:
    import readline  # noqa: F401  (line editing: an arrow key isn't typed into a name)
except ImportError:
    pass

sys.path.insert(0, "/opt/compaq/lib")
sys.path.insert(1, os.path.dirname(os.path.abspath(__file__)))
from chat import page, to_ascii  # noqa: E402
import jukebox as notes  # noqa: E402
import textwrap
import time

SOCKET = "/run/compaq-pal/pal.sock"
COLS = 76


def say(text=""):
    for line in textwrap.wrap(text, COLS) or [""]:
        print("  " + line)


def ask(request, timeout=120):
    """Sends a request; yields each line PAL answers with."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(timeout)
        s.connect(SOCKET)
        s.sendall((json.dumps(request) + "\n").encode())
        for line in s.makefile():
            yield json.loads(line)


def one(request, timeout=120):
    for answer in ask(request, timeout):
        return answer
    return {}


def pause():
    input("\n  Press Enter to return to the menu. ")


def clean(text, limit):
    """Plain ASCII on one line: "José" becomes "Jose", not "Jos"."""
    return " ".join("".join(c for c in to_ascii(text) if " " <= c <= "~").split())[:limit]


ABOUT = """\
PAL 286 is the lobby computer's voice. It uses a webcam, a microphone and a \
speaker on the Raspberry Pi behind the Compaq.

What it does: when someone walks up, it says hello (by name, if they've \
taught it their face). People can talk back and ask it things, have it \
play music or sing, run a quiz, open programs here, show the camera as \
a mirror or a photo booth, or put up a QR code to take a link away on a \
phone. Its replies come from Claude, an AI model made \
by Anthropic, over the internet. When nobody is using the Compaq, the \
conversation shows on this screen too.

What it keeps: for people who teach it their face here, their name, a \
face signature (128 numbers worked out from the camera, not a photo), \
short notes from their chats, and their birthday if they tell it (it sings \
to them on the day, when they're on their own). It also keeps general \
notes about the office. The photo booth paints a real photo on this \
screen (only here, not in browsers); it's kept only if you ask, and then \
only as text art anyone at this menu can see and delete. No video or recordings, \
and typed chats aren't saved. Speech is turned into text on the Pi, and \
the text of a conversation goes to Claude to work out a reply; when you ask \
PAL to look at something you're holding, one camera picture goes too. So \
it doesn't greet a visitor twice, it holds a visitor's face signature in \
memory (never on disk) for half an hour.

What it notices: movement in the lobby (not faces), to count roughly how \
many people pass and now and then call out hello. Counts and today's quiz \
scores stay in memory for the day, without names.

Who it knows: only people who chose to teach it, here, and said yes out \
loud at the camera. Everyone else is a visitor. Anyone can make it forget \
them at any time: PAL 286, then "Make PAL forget me" (and say "forget me" \
when it asks), or just ask it. That deletes their face, notes and birthday.

When it listens: only while someone is in front of the camera. Between \
conversations it listens only for its name ("Hey PAL"), except for half a \
minute after a chat, while that one person is still there, and during a \
text adventure at this keyboard, when it types the moves it hears into \
the game. Quiet mode turns it off for a while.

Tips and remarks: while someone uses a program from this keyboard, PAL \
watches the bottom of the screen. If the program keeps saying it doesn't \
understand, PAL offers a spoken tip, and it reacts when a player dies or \
wins a game; that bit of the screen goes to Claude to work out what to \
say. Nothing typed from a browser is watched, and nothing is kept."""


def about():
    print("\n  ABOUT PAL 286\n")
    lines = []
    for para in ABOUT.split("\n\n"):
        lines += textwrap.wrap(para, COLS) + [""]
    page(["  " + line for line in lines[:-1]])
    pause()


def enroll():
    print("\n  TEACH PAL YOUR FACE\n")
    say("PAL will greet you by name and remember what you chat about. It keeps "
        "your name, a face signature (numbers, not a photo) and short notes, "
        "only on this Pi. You can make it forget you any time.")
    print()
    if input("  Go ahead? (Y/N) ").strip().lower() != "y":
        return
    name = clean(input("  Your first name, as PAL should show it: "), 24)
    if not name:
        return
    say_as = clean(input(f"  How should PAL say \"{name}\"? (Enter if it's obvious; "
                         "or spell it how it sounds) "), 40)
    print()
    say("Stand in front of the camera and look at it. PAL will ask you out loud; when "
        "this screen says it's listening, say yes. Then hold still for about ten seconds.")
    print()
    for answer in ask({"op": "enroll", "name": name, "say_as": say_as}, timeout=180):
        if "say" in answer:
            say(answer["say"])
        if answer.get("done"):
            print()
            say(answer.get("message", ""))
            break
    pause()


def forget():
    print("\n  MAKE PAL FORGET YOU\n")
    say("Stand in front of the camera and look at it. PAL will ask you out loud; when "
        "this screen says it's listening, say \"forget me\".")
    print()
    for answer in ask({"op": "forget"}, timeout=60):
        if "say" in answer:
            say(answer["say"])
        if answer.get("done"):
            print()
            say(answer.get("message", ""))
            break
    pause()


def quiet():
    print("\n  QUIET MODE\n")
    status = one({"op": "status"}, timeout=10)
    if status.get("quiet_until"):
        left = int((status["quiet_until"] - time.time()) / 60) + 1
        say(f"PAL is in quiet mode for another {left} minute(s).")
        if input("  Wake it up now? (Y/N) ").strip().lower() == "y":
            one({"op": "quiet", "minutes": 0})
            say("PAL is awake.")
    else:
        say("Quiet mode stops PAL greeting people and listening.")
        minutes = input("  For how many minutes? (Enter for 60, 0 to cancel) ").strip() or "60"
        if minutes.isdigit() and int(minutes) > 0:
            one({"op": "quiet", "minutes": min(int(minutes), 24 * 60)})
            say(f"Quiet for {min(int(minutes), 24 * 60)} minutes.")
    pause()


def voice():
    """Picks how PAL sounds, for an hour (then its own voice again)."""
    print("\n  PAL'S VOICE\n")
    status = one({"op": "status"}, timeout=10)
    voices = status.get("voices") or []
    sounds = dict(voices)
    if status.get("usual_voice") in sounds:
        say(f"Right now PAL sounds like {sounds[status['usual_voice']]}. Pick another for the next hour "
            "(people can also ask, \"Hey PAL, talk like a butler\", for one conversation).")
    print()
    for n, (_, what) in enumerate(voices, 1):
        print(f"   {n:>2}.  {what[0].upper() + what[1:]}")
    choice = input("\n  Which one (a number; Enter: no change)? ").strip()
    if choice.isdigit() and 1 <= int(choice) <= len(voices):
        print("  Listen...", flush=True)
        answer = one({"op": "voice", "voice": voices[int(choice) - 1][0]}, timeout=60)
        if not answer.get("ok"):
            say(answer.get("message", "PAL didn't answer."))
    pause()


def gallery():
    """The photo booth's saved portraits, newest first."""
    folder = "/var/lib/compaq/portraits"
    i = 0
    while True:
        try:
            names = sorted((n for n in os.listdir(folder) if n.endswith(".txt")), reverse=True)
        except OSError:
            names = []
        if not names:
            print("\n  PHOTO BOOTH GALLERY\n")
            say("No portraits yet. Stand in front of the camera and say: Hey PAL, take my picture. "
                "Then ask it to save the picture.")
            pause()
            return
        i = max(0, min(i, len(names) - 1))
        try:
            with open(os.path.join(folder, names[i])) as f:
                rows = f.read().splitlines()[:23]
        except OSError:
            rows = ["(can't read this one)"]
        print("\033[H\033[2J", end="")
        print("\n".join(clean(r, 79) if r.strip() else "" for r in rows))
        choice = input(f"  {i + 1} of {len(names)}.  N: next  P: previous  D: delete  Enter: back  "
                       ).strip().lower()
        if choice == "n":
            i += 1
        elif choice == "p":
            i -= 1
        elif choice == "d":
            if input("  Delete this portrait? (Y/N) ").strip().lower() == "y":
                one({"op": "delete_portrait", "name": names[i]}, timeout=10)
        else:
            return


FALL_TOP, FALL_BOTTOM = 5, 20       # rows the notes fall down


def jukebox():
    """The jukebox: PAL plays a tune through the lobby speaker while its
    notes fall down this screen and land on a keyboard as they play."""
    tunes = one({"op": "tunes"}, timeout=10).get("tunes", [])
    while True:
        print("\033[H\033[2J", end="")
        print("\n  PAL 286 JUKEBOX: 1980s chiptunes, out of the lobby speaker\n")
        rows = [f"{i + 1:>2}. {clean(t['title'], 32)}" for i, t in enumerate(tunes)]
        half = (len(rows) + 1) // 2
        for left, right in zip(rows[:half], rows[half:] + [""]):
            print(f"  {left:<38}{right}")
        print()
        print("   D. PAL sings Daisy Bell (as a computer first did, in 1961)")
        print("   B. PAL sings Happy Birthday to someone")
        print()
        choice = input("  Type a number or letter, then press Enter (just Enter: back): ").strip().lower()
        if not choice:
            return
        if choice == "d":
            request = {"op": "play", "song": "daisy"}
        elif choice == "b":
            name = clean(input("  Whose birthday is it? "), 24)
            if not name:
                continue
            request = {"op": "play", "song": "birthday", "name": name}
        elif choice.isdigit() and 1 <= int(choice) <= len(tunes):
            request = {"op": "play", "tune": tunes[int(choice) - 1]["id"]}
        else:
            continue
        message = play(request)
        print("\033[r\033[H\033[2J", end="")
        print()
        say(message)
        pause()


def play(request):
    """Plays one tune, drawing it; returns what PAL said about it."""
    print("\n  Warming up the sound chip...", flush=True)
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as conn:
        conn.settimeout(30)
        conn.connect(SOCKET)
        conn.sendall((json.dumps(request) + "\n").encode())
        replies = conn.makefile()
        first = json.loads(replies.readline() or "{}")
        if not first.get("started"):
            return first.get("message", "PAL didn't play it.")
        start = time.monotonic()          # (the sound starts now)
        conn.settimeout(None)
        timeline = [tuple(n) for n in first["timeline"]]
        total = first["seconds"]
        notes_screen(first, timeline)
        stdin = sys.stdin.fileno()
        saved = termios.tcgetattr(stdin)
        tty.setcbreak(stdin)
        try:
            step, second, stopping = 1, -1, False
            while True:
                now = time.monotonic() - start
                if int(now) != second and now < total + 1:
                    second = int(now)
                    status_row(("Any key: stop" if not stopping else "Stopping...") + "   "
                               + notes.progress(now, total, 30))
                wake = min(start + step * notes.STEP, start + second + 1) - time.monotonic()
                ready, _, _ = select.select([conn, stdin], [], [], max(0.0, wake))
                if conn in ready:
                    answer = json.loads(replies.readline() or '{"done": true}')
                    if answer.get("done"):
                        return answer.get("message", "")
                if stdin in ready:
                    os.read(stdin, 64)
                    if not stopping:
                        stopping = True
                        one({"op": "stop"}, timeout=5)
                while time.monotonic() - start >= step * notes.STEP:
                    # Everything falls a row; the next moment's notes
                    # appear at the top. The bottom row is what's playing.
                    ahead = (step + FALL_BOTTOM - FALL_TOP) * notes.STEP
                    sys.stdout.write(f"\033[{FALL_TOP};1H\033M" + notes.falling_line(timeline, ahead))
                    step += 1
                sys.stdout.flush()
        finally:
            termios.tcsetattr(stdin, termios.TCSADRAIN, saved)
            sys.stdout.write("\033[r\033[?25h")
            sys.stdout.flush()


def notes_screen(info, timeline):
    """Draws the title, the falling area (filled with what's coming) and
    the keyboard."""
    out = ["\033[r\033[H\033[2J\033[?25l"]      # (no cursor blinking among the notes)
    title = f"{clean(info.get('title', ''), 60).upper()}"
    by = clean(", ".join(str(v) for v in (info.get("composer"), info.get("year")) if v), 70)
    out.append(f"\033[1;1H  PAL 286 JUKEBOX: {title}\033[2;1H  {by}")
    fact = textwrap.wrap(clean(info.get("fact", ""), 300), 76)[:2]
    for i, line in enumerate(fact):
        out.append(f"\033[{3 + i};1H  {line}")
    keys = notes.keyboard()
    out.append(f"\033[{FALL_BOTTOM + 1};1H{keys[0]}\033[{FALL_BOTTOM + 2};1H{keys[1]}"
               f"\033[{FALL_BOTTOM + 3};1H{notes.octave_labels()}")
    for row in range(FALL_TOP, FALL_BOTTOM + 1):
        out.append(f"\033[{row};1H" + notes.falling_line(timeline, (FALL_BOTTOM - row) * notes.STEP))
    out.append(f"\033[{FALL_TOP};{FALL_BOTTOM}r")      # only the falling area scrolls
    sys.stdout.write("".join(out))
    sys.stdout.flush()


def status_row(text):
    sys.stdout.write(f"\0337\033[24;1H\033[K  {text}\0338")


def status():
    print("\n  PAL 286 STATUS\n")
    s = one({"op": "status"}, timeout=10)
    rows = [("Camera", s.get("camera")), ("Microphone", s.get("microphone")),
            ("Speaker", s.get("speaker")), ("Claude", f"{s.get('brain')} ({s.get('model')})"),
            ("People it knows", s.get("people")), ("Greeted today", s.get("greeted_today")),
            ("Quiet", "yes" if s.get("asleep") else "no")]
    for label, value in rows:
        print(f"  {label + ':':<18}{value}")
    print()
    if input("  Test the speaker? (Y/N) ").strip().lower() == "y":
        say(f"Speaker: {one({'op': 'say_test'}, timeout=30).get('speaker')}")
    pause()


def main():
    jobs = {"enroll": enroll, "forget": forget, "quiet": quiet, "voice": voice, "status": status, "about": about,
            "gallery": gallery, "jukebox": jukebox}
    job = jobs.get(sys.argv[1] if len(sys.argv) > 1 else "", None)
    if not job:
        sys.exit(__doc__.strip())
    if job not in (about, gallery) and not os.path.exists(SOCKET):
        print("\n  PAL isn't running (compaq-pal.service). Ask whoever looks after the Pi.")
        pause()
        return
    try:
        job()
    except (EOFError, KeyboardInterrupt):
        print("\033[r")
    except (OSError, ValueError) as e:
        print(f"\n  Couldn't reach PAL ({e}).")
        pause()


if __name__ == "__main__":
    main()

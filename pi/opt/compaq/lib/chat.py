#!/usr/bin/env python3
"""Text chat sized for the Compaq's terminal.

Replies are cut down to what an 80x24 VT100 on a 9600-baud line can show:
plain ASCII, wrapped to 79 columns, one screenful at a time. The AI service
sits behind a small backend class (FixBot, or Echo for testing). Every
conversation is saved to ~/compaq-files/chats.
"""

import argparse
import datetime
import os
import re
import sys
import textwrap
import threading
import unicodedata

try:
    import readline  # noqa: F401  (gives input() line editing and arrow keys)
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ifixit  # noqa: E402

COLS = 79   # never write in column 80, so the terminal doesn't wrap on its own
PAGE = 20   # reply lines per screenful, leaving room for prompts
CONFIG = "/etc/compaq/fixbot.env"
LOG_DIR = os.path.expanduser("~/compaq-files/chats")
SETTINGS_DIR = os.path.expanduser("~/.config/compaq")

# Characters AI replies use that the Compaq can't display.
ASCII = {
    "‘": "'", "’": "'", "“": '"', "”": '"',
    "–": "-", "…": "...", "•": "*",
    "·": "-", "→": "->", "←": "<-", "×": "x",
    "°": " deg", "™": "(TM)", "®": "(R)", "©": "(C)",
    " ": " ", "≤": "<=", "≥": ">=", "≈": "~",
    # Measurements in repair steps: these must not quietly vanish.
    "\u2212": "-", "\u2010": "-", "\u2011": "-", "\u00b1": "+/-",
    "\u00b5": "u", "\u03bc": "u", "\u03a9": " ohm", "\u2126": " ohm",
    "\u2032": "'", "\u2033": '"', "\u2044": "/",
}


class BackendError(Exception):
    """A reply couldn't be fetched. The message is shown to the user."""


PAL_SOCKET = "/run/compaq-pal/pal.sock"


def ask_pal(request, timeout=120):
    """One request to PAL's service (compaq-pal), which holds the Claude and
    FixBot keys so the shared session never sees them."""
    import json
    import socket
    try:
        with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
            s.settimeout(timeout)
            s.connect(PAL_SOCKET)
            s.sendall((json.dumps(request) + "\n").encode())
            return json.loads(s.makefile().readline() or "{}")
    except (OSError, ValueError) as e:
        raise BackendError(f"Couldn't reach PAL's service ({e}).") from e


class FixBot:
    """iFixit's FixBot: each message refines one repair plan for one device.
    The key and the requests are PAL's service's (see ask_pal)."""

    name = "FixBot"
    default_device = "Compaq Portable III"
    keeps_transcripts = True

    def __init__(self):
        self.device = None
        self.chatid = None
        self.generation = 0     # a reply that arrives after "new" is ignored

    def ready(self):
        """None when usable, otherwise why not."""
        if not os.path.exists(PAL_SOCKET):
            return "FixBot isn't available: PAL's service (compaq-pal) isn't running."
        try:
            if not ask_pal({"op": "status"}, timeout=10).get("fixbot"):
                return ("FixBot is switched off right now. Try the iFixit repair guides on "
                        "the main menu, or talk to PAL.")
        except BackendError as e:
            return str(e)
        return None

    def start(self):
        """Begins a new conversation. Returns tips to show."""
        saved = os.path.join(SETTINGS_DIR, "fixbot-device")
        last = read_text(saved) or self.default_device
        answer = to_ascii(input(f"  Which device needs help? (Enter for {last}): ")).strip()
        self.device = answer or last
        write_text(saved, self.device)
        self.chatid = None
        self.generation += 1
        return [f"Describe what's wrong with the {self.device} and FixBot will write a "
                "repair plan, with the best iFixit guide and parts. Plans take a "
                "minute or two. Follow-up messages refine the same plan.",
                "Type new to start over with another device, quit to leave."]

    def reply(self, history):
        generation = self.generation
        answer = ask_pal({"op": "fixbot", "device": self.device, "text": history[-1][1],
                          "chatid": self.chatid}, timeout=ifixit.PLAN_TIMEOUT + 30)
        if not answer.get("ok"):
            raise BackendError(answer.get("message", "FixBot didn't answer."))
        if generation == self.generation:      # not a leftover from before "new"
            self.chatid = answer.get("chatid") or self.chatid
        return answer["text"]


class Echo:
    """Repeats each question back, for testing the screen and keyboard."""

    name = "Echo"

    def ready(self):
        return None

    def start(self):
        return ["Type a question and press Enter. Type quit to go back to the menu."]

    def reply(self, history):
        return "You said: " + history[-1][1]


class Pal:
    """PAL 286, the lobby greeter, through its own service, which holds the
    Claude key (compaq-pal.service; see /opt/compaq/pal)."""

    name = "PAL"
    keeps_transcripts = False   # PAL promises to keep no recordings of what people say

    def ready(self):
        if not os.path.exists(PAL_SOCKET):
            return "PAL isn't running (compaq-pal.service). Ask whoever looks after the Pi."
        return None

    def start(self):
        return ["Type to PAL 286, the lobby computer, and press Enter. It knows a great "
                "deal, can look things up, and is very proud of its 640 KB.",
                "Type new to start over, quit to leave."]

    def reply(self, history):
        # The latest of the conversation (an odd number, so it starts with
        # the person): PAL only reads the last 20 turns, and takes at most
        # 64 KB a request, which a long chat would otherwise outgrow for good.
        recent = [{"role": r, "content": t[:2000]} for r, t in history[-21:]]
        answer = ask_pal({"op": "chat", "messages": recent})
        if not answer.get("ok"):
            raise BackendError(answer.get("message", "PAL didn't answer."))
        return answer["text"]


BACKENDS = {"fixbot": FixBot, "pal": Pal, "echo": Echo}


def read_env(path):
    """KEY=value pairs from path. A missing or unreadable file reads as empty."""
    settings = {}
    for line in read_text(path).splitlines():
        key, sep, value = line.strip().partition("=")
        if sep and not key.startswith("#"):
            settings[key.strip()] = value.strip().strip("\"'")
    return settings


def read_text(path):
    try:
        with open(path) as f:
            return f.read().strip()
    except OSError:
        return ""


def write_text(path, text):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as f:
        f.write(text + "\n")


def to_ascii(text):
    text = re.sub(r"\s*—\s*", " - ", text)
    # "1\u00bd turns" is one and a half, not "112": a space before a fraction
    # that follows a digit (the fraction itself becomes 1/2 below).
    text = re.sub("(?<=\\d)(?=[\u00bc-\u00be\u2150-\u215e])", " ", text)
    text = "".join(ASCII.get(c, c) for c in text)
    # Split accented letters into letter + accent; the accent is dropped below.
    text = unicodedata.normalize("NFKD", text).replace("\u2044", "/")
    # Symbols with no ASCII version (emoji) go, along with the space after them.
    text = re.sub(r"(?m)(^|(?<= ))[^\x00-\x7f]+ ?", "", text)
    # Control characters (an Esc, say) would reach the shared screen as
    # commands: keep only newlines and tabs.
    text = re.sub(r"[\x00-\x08\x0b-\x1f\x7f]", "", text)
    return text.encode("ascii", "ignore").decode("ascii")


def unmarkdown(text):
    """Markdown to plain text. Headings become capitals, since there's no bold."""
    text = re.sub(r"(?m)^```.*\n?", "", text)
    text = re.sub(r"\*\*(.+?)\*\*|__(.+?)__", lambda m: m.group(1) or m.group(2), text)
    text = re.sub(r"(?m)^#{1,6}\s+(.*)$", lambda m: m.group(1).upper(), text)
    text = re.sub(r"`([^`\n]+)`", r"\1", text)
    text = re.sub(r"\[([^\]]+)\]\((\S+?)\)", r"\1 (\2)", text)
    text = re.sub(r"(?m)^(\s*)[-*+]\s+", r"\1* ", text)
    # Tables: drop the |---| rule, keep the cells separated by spaces.
    text = re.sub(r"(?m)^[ \t]*\|?([ \t]*:?-{3,}:?[ \t]*\|)+[ \t]*:?-*:?[ \t]*$\n?", "", text)
    text = re.sub(r"(?m)^[ \t]*\|(.*?)\|?[ \t]*$",
                  lambda m: re.sub(r"[ \t]*\|[ \t]*", "   ", m.group(1).strip()), text)
    return text


def fit(text):
    """Reply text as screen lines no wider than COLS."""
    lines = []
    for para in to_ascii(unmarkdown(text)).splitlines():
        if not para.strip():
            if lines and lines[-1]:
                lines.append("")
            continue
        # Wrapped lines of a list item line up under its text, not its bullet.
        bullet = re.match(r"\s*(?:\*|\d+[.)])\s+", para)
        indent = bullet.end() if bullet else len(para) - len(para.lstrip())
        lines += textwrap.wrap(para, COLS, subsequent_indent=" " * indent,
                               break_on_hyphens=False)
    while lines and not lines[-1]:
        lines.pop()
    return lines


def page(lines):
    """Print lines a screenful at a time."""
    for start in range(0, len(lines), PAGE):
        if start:
            answer = input("-- More: Enter to continue, Q to stop --")
            sys.stdout.write("\033[A\033[K")  # erase the prompt line
            if answer.strip().lower() == "q":
                return
        print("\n".join(lines[start:start + PAGE]))


def wait_for(bot, history):
    """bot.reply(history), printing a dot every few seconds while it works."""
    outcome = {}

    def work():
        try:
            outcome["answer"] = bot.reply(history)
        except BackendError as e:
            outcome["error"] = str(e)
        except Exception as e:  # keep the chat alive whatever goes wrong
            outcome["error"] = f"Something went wrong: {e}"

    thread = threading.Thread(target=work, daemon=True)
    thread.start()
    message = f"{bot.name} is working on it"
    print(message, end="", flush=True)
    dots = COLS - len(message)   # room left on the line
    try:
        while thread.is_alive():
            thread.join(timeout=5)
            if thread.is_alive() and dots > 0:
                print(".", end="", flush=True)
                dots -= 1
    except KeyboardInterrupt:
        outcome = {"error": "Stopped."}
    print()
    return outcome.get("answer"), outcome.get("error")


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--backend", choices=BACKENDS, default="fixbot")
    parser.add_argument("--device", help="start with this device (FixBot)")
    parser.add_argument("--ask", help="and ask this straight away")
    args = parser.parse_args()
    bot = BACKENDS[args.backend]()

    print(f"\n  {bot.name.upper()}\n")
    problem = bot.ready()
    if problem:
        print("\n".join("  " + line for line in textwrap.wrap(problem, COLS - 2)))
        try:
            input("\n  Press Enter to return to the menu. ")
        except (EOFError, KeyboardInterrupt):
            print()
        return

    try:
        os.makedirs(LOG_DIR, exist_ok=True)
    except OSError:
        pass
    started = datetime.datetime.now().strftime("%Y%m%d-%H%M")
    log_path = os.path.join(LOG_DIR, f"{args.backend}-{started}.txt")
    history = []
    starting = True
    first = None
    if args.device and hasattr(bot, "device"):
        # PAL looked at a device and asked for a plan: skip the questions.
        bot.device, starting = to_ascii(args.device)[:100], False
        print(f"  Device: {bot.device}")
        first = to_ascii(args.ask or "")[:500] or None

    while True:
        try:
            if starting:
                tips = bot.start()
                print()
                for tip in tips:
                    print("\n".join("  " + line for line in textwrap.wrap(tip, COLS - 2)))
                history, starting = [], False
            if first:
                question, first = first, None
                print(f"\nYou> {question}")
            else:
                question = to_ascii(input("\nYou> ")).strip()
        except (EOFError, KeyboardInterrupt):
            print()
            break
        if not question:
            continue
        if question.lower() in ("quit", "exit", "bye"):
            break
        if question.lower() == "new":
            starting = True
            continue

        history.append(("user", question))
        answer, error = wait_for(bot, history)
        if answer is None:
            history.pop()
            print("\n".join(textwrap.wrap(to_ascii(error), COLS)))
            continue
        history.append(("assistant", answer))
        lines = fit(answer)
        if getattr(bot, "keeps_transcripts", True):
            try:
                with open(log_path, "a") as log:
                    log.write(f"You: {question}\n\n{bot.name}:\n" + "\n".join(lines) + "\n\n")
            except OSError:
                pass             # (a full card mustn't cost them the answer)
        print(f"{bot.name}:")
        try:
            page(lines)
        except (EOFError, KeyboardInterrupt):
            print()   # stop paging; the conversation carries on


if __name__ == "__main__":
    main()

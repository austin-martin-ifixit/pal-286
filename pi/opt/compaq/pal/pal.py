#!/usr/bin/env python3
"""PAL 286, the lobby greeter (compaq-pal.service).

Watches the lobby through a webcam. When someone walks up it greets them out
loud, by name if they've taught it their face, and shows the conversation on
the Compaq's plasma screen if nobody is using the Compaq. Then it listens:
people can talk back, ask it anything, or ask it to open a program on the
Compaq. Between conversations it listens only for its name ("Hey PAL"), and
only while someone is in front of the camera.

Menu programs talk to it over a Unix socket (see client.py): teach it a
face, make it forget one, quiet mode, typed chat and status.

Settings: /etc/compaq/pal.conf. The Claude key comes from
/etc/compaq/claude.env through systemd.
"""

import base64
import collections
import grp
import io
import itertools
import json
import os
import queue
import random
import re
import select
import socket
import subprocess
import sys
import threading
import time
import traceback
import urllib.parse
import wave

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(1, "/opt/compaq/lib")
import boards  # noqa: E402
import brain as brain_module  # noqa: E402
import ifixit  # noqa: E402
import jukebox  # noqa: E402
import lines  # noqa: E402
import music  # noqa: E402
import pictures  # noqa: E402
import sfx  # noqa: E402
import vision  # noqa: E402
from people import SAME_PERSON, People, normalise  # noqa: E402
from senses import LANGUAGES, Ears, Eyes, Voice, log  # noqa: E402
import fixbot_mode  # noqa: E402
import fixbot_page  # noqa: E402

SETTINGS = os.environ.get("PAL_SETTINGS", "/etc/compaq/pal.conf")
APPS = "/opt/compaq/data/voice-apps"
SOCKET = os.environ.get("PAL_SOCKET", "/run/compaq-pal/pal.sock")
BRIDGE = os.environ.get("COMPAQ_BRIDGE", "/run/compaq-serial/bridge.sock")   # (the simulator has its own)
VOICE_OPEN = "/opt/compaq/lib/voice-open"
SCREEN_WATCH = "/opt/compaq/lib/screen-watch"
VOICE_TYPE = "/opt/compaq/lib/voice-type"
POTATO_SOUND = "/home/desk/compaq-files/.potato"   # PotatoTube's sound, for PAL to play
TEXT_ADVENTURES = {"frotz", "dfrotz", "advent"}
# Things worth a remark while someone plays (event: (what the screen says,
# what happened)): text adventures, DUSTRUN and NetHack.
ADVENTURE_EVENTS = {
    "died": (re.compile(r"You have died|You are dead|have been killed|eaten by a grue", re.I),
             "just died in the game"),
    "won": (re.compile(r"You have won|\*\*\*\s*You have won", re.I), "just won the game"),
    "scored": (re.compile(r"Your score has (?:just )?gone up|score has just gone up", re.I),
               "just scored points"),
}
GAME_EVENTS = {
    "adventure": ADVENTURE_EVENTS,
    "dustrun": {
        "died": (re.compile(r"swallowed your harvester|took your last harvester"),
                 "just lost a harvester to a burrower (a sandworm-like monster that hunts by sound)"),
        "oops": (re.compile(r"Out of fuel!"), "just ran out of fuel and got towed back to base"),
        "won": (re.compile(r"SEASON OVER"), "just finished all five days of the season"),
    },
    "nethack": {
        "died": (re.compile(r"You die\.\.\.|Do you want your possessions identified"), "just died in NetHack"),
    },
}
# Words people put round a game command that the game doesn't want.
# Words speech recognition splits that adventure games want whole.
JOINED = {"mail box": "mailbox", "flash light": "flashlight", "in ventory": "inventory",
          "north east": "northeast", "north west": "northwest", "south east": "southeast",
          "south west": "southwest", "trap door": "trapdoor", "light house": "lighthouse"}
FILLER = re.compile(r"^(?:(?:um+|uh+|er+|hmm+|okay|ok|so|well|and|then|now|alright|all right|"
                    r"let'?s|i want to|i'd like to|i would like to|i'll|i will|i'm going to|"
                    r"can i|can you|could you|please|try to|go ahead and)\b\W*)+", re.I)
LISTEN_SECONDS = 12      # how long PAL waits for an answer to a question it asked
FOLLOW_ON_SECONDS = 7    # and after any other reply, in case they carry on (Claude SKIPs chatter)
QUIZ_SECONDS = 25        # (longer during a quiz: people think)
FOLLOW_UP_SECONDS = 30   # "Hey PAL" again this soon picks the last conversation back up
TICK = [[1800, 0.012], [0, 0.045], [1500, 0.008]]   # "got it" on the Compaq's speaker (see sfx.heard)
# "Your turn", rising, on the Compaq's own speaker when PAL has asked something
# (PAL can't hear while it talks: an answer started over its last words is lost).
YOUR_TURN = [[660, 0.05], [0, 0.03], [990, 0.07]]
STRANGER_GAP = 600       # at most one hello to unrecognized visitors this often
STRANGER_MEMORY = 30 * 60   # a visitor's face signature is kept (in memory only) this long, to greet once
GONE_SECONDS = 4         # a face unseen this long has left
RECHECK_GAP = 2          # a known face unseen this long is looked at again when it's back
RECOGNISE_SIZE = 0.08    # faces this big (share of the picture's width) are near enough to recognise
# "Hey PAL" (as Whisper tends to hear it: "Hey Paul", "Hey Hal") or just
# "PAL," at the start, after at most a little "um" or "so". "Is Paul in
# today?", "say hi Paul" or "my computer won't boot" doesn't count.
# (Whisper's small model often hears "Hey PAL" as "PayPal", "Hey Powell",
# "Hey pile" or "Hey power": those count too.)
WAKE = re.compile(r"^\W*(?:(?:oh|um|uh|so|and|well)\W+)?(?:(?:hey|hi|hello|ok|okay|yo|ey|oye|hola|ola|salut|"
                  r"bonjour|hallo|ciao)\W+"
                  r"(?:pal|pals|pall|paul|pol|pow|power|pile|pale|pell|powell|hal|compaq|computer)"
                  r"|pay\W?pal|pal)\b\W*", re.I)
# A yes (or "forget me") counts near the start of what was said, and not
# with a no in it: "no, don't do it, okay?" is not a yes.
# Just the name, as Whisper hears it on its own ("K-PAL!", "A pal", "PayPal",
# "Hey pal"): a word or two at most, ending in "pal".
NAME_ONLY = re.compile(r"^\W*(?:\w+\W+)?\w{0,4}-?pal\W*$", re.I)
# (Not "okay" or "sure" on their own: Whisper's small model writes those for
# a cough or a door closing, and this yes lets PAL keep someone's face.)
YES = re.compile(r"^\W*(?:\w+\W+){0,2}?(?:yes|yeah|yep|yup|yah|yas|yess|jess|"
                 r"go ahead|do it|i agree|please do)\b", re.I)
FORGET = re.compile(r"^\W*(?:\w+\W+){0,3}?forget\b", re.I)
FORGET_WORD = re.compile(r"\bforget\b", re.I)
DONT_FORGET = re.compile(r"\b(?:don'?t|do not|never|not) forget\b", re.I)
NO = re.compile(r"\b(?:no|nope|nah|not|don'?t|do not|never|stop|wait|cancel)\b", re.I)
# What programs say when they didn't understand someone (Infocom games and
# others, Colossal Cave, Battlestar, the shell, NetHack, chess...), counted
# only in the programs below (not, say, a news story that says "illegal").
TROUBLE = re.compile(r"I don'?t know (?:the|that) word|not a verb I recogni[sz]e|isn'?t one I recogni[sz]e|"
                     r"I didn'?t understand that|There was no verb|I beg your pardon|"
                     r"in a way I don'?t understand|I only understood you as far as|"
                     r"You can'?t see any (?:such thing|[\w ]{1,30} here)|: How's that\?|"
                     r"command not found|Unknown command|Invalid move|Illegal move|Invalid command",
                     re.I)
TIP_PROGRAMS = {"frotz", "dfrotz", "advent", "adventure", "battlestar", "nethack", "hack", "moria",
                "gnuchess", "bash"}
# Someone walking past (movement, but no face turned to the camera): a quick
# shout-out now and then. Movement this share of the picture counts (less is
# a flicker, more is the lights or the camera adjusting).
MOTION_AREA = (0.02, 0.5)
TIP_AFTER = 3              # this many misunderstandings within TIP_WINDOW seconds: offer a tip
TIP_WINDOW = 180
TIP_GAP = 150              # and at most one tip this often


def read_settings(path=SETTINGS):
    settings = {}
    try:
        with open(path) as f:
            for line in f:
                key, sep, value = line.strip().partition("=")
                if sep and not key.startswith("#"):
                    settings[key.strip()] = value.strip().strip("\"'")
    except OSError:
        pass
    return settings


def read_apps(path=APPS, field=2):
    """The programs PAL may open: id -> description (or field=1: id -> its
    place in the menu, like 40-games/05-dustrun)."""
    apps = {}
    try:
        with open(path) as f:
            for line in f:
                parts = line.strip().split("|")
                if len(parts) == 3 and not parts[0].startswith("#"):
                    apps[parts[0]] = parts[field]
    except OSError:
        pass
    return apps


class Screen:
    """The Compaq's screen, borrowed through the serial bridge. Every call is
    best effort: no Compaq connected, or someone using it, just means PAL
    talks without it."""

    def __init__(self, name):
        self.name = name
        self.shown = False
        self.canvas = False          # showing a full-screen picture or board
        self.pictures = 0
        self.asked = False           # this chat began with PAL's name (see begin)

    def send(self, **request):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(10)        # the bridge may be busy writing a screenful at 9600 baud
                s.connect(BRIDGE)
                s.sendall((json.dumps(dict(op="pal", **request)) + "\n").encode())
                return json.loads(s.makefile().readline() or "{}")
        except (OSError, ValueError):
            return {}

    def begin(self, canvas=False, requested=None):
        """PAL's eye scene, or (canvas) a blank screen for full-screen
        pictures. requested: someone in the lobby asked for it (the mirror),
        so only a browser user typing holds it back. Left out, it's whether
        this chat began with PAL's name: whoever said it is most likely the
        one at the lobby keyboard, so their own typing mustn't hide the eye
        (it did, 2026-11-05). PAL's own greetings and shout-outs still wait
        for two quiet minutes, so they don't cover someone's program."""
        requested = self.asked if requested is None else requested
        self.shown = bool(self.send(action="begin", name=self.name, canvas=canvas,
                                    requested=requested).get("shown"))
        self.canvas = canvas and self.shown
        if self.canvas:
            self.pictures += 1           # (each full-screen picture, so a timer can tell it's still up)
        return self.shown

    def frame(self, lines, board=None):
        """A full-screen board: its rows of text, and (board) what it means,
        which the bridge draws properly when the Compaq can show dots
        (pal_screen.board says what each kind holds)."""
        if self.shown:
            request = {"action": "frame", "lines": lines}
            if board:
                request["board"] = board
            self.shown = bool(self.send(**request).get("shown"))
        self.canvas = self.canvas and self.shown
        return self.shown

    def say(self, who, text, cps=40):
        if self.shown:
            self.shown = bool(self.send(action="say", who=who, text=text, cps=cps).get("shown"))

    def status(self, text, blink=False):
        if self.shown:
            self.shown = bool(self.send(action="status", text=text, blink=blink).get("shown"))

    def beep(self, notes):
        """Notes ([[hertz, seconds], ...]) on the Compaq's own speaker, when
        the Compaq runs PILINK as its terminal; False if it can't."""
        return bool(self.send(action="beep", notes=notes).get("beeped"))

    def end(self, wake=False):
        """Hands the screen back: to the saver or the shared screen, or (wake)
        straight to the shared screen, e.g. to show a program PAL opened."""
        if self.shown:
            self.send(action="end", wake=wake)
        self.shown = self.canvas = False


ASKING = re.compile(r"^\W*(?:(?:just|so|then|ok|okay)\W+)?(?:say|tell me|let me know)\b", re.I)


def asks(text):
    """Did PAL end by asking something, so it should wait for an answer: a
    question, or "Say yes and I'll do it." / "Tell me when you're ready."?"""
    sentences = re.split(r"(?<=[.!?])\s+", (text or "").strip())
    last = sentences[-1] if sentences else ""
    return last.endswith("?") or bool(ASKING.match(last))


def clean_command(heard):
    """A spoken game command, plain: lower case, no "um" or "please", no
    trailing punctuation, split words joined ("mail box": "mailbox")."""
    command = FILLER.sub("", " ".join(re.sub(r"[^a-z0-9 ,.'?!-]", " ", heard.lower()).split()))
    command = re.sub(r"\bplease\b", "", command).strip(" ,.!?")
    command = " ".join(command.split())
    for split, whole in JOINED.items():
        command = re.sub(rf"\b{split}\b", whole, command)
    return command[:60]


def agreed(heard, answer):
    """Did they say it (yes, or forget me), without a no?"""
    return bool(answer.search(heard)) and not NO.search(heard)


# Numbers the speech synthesizer would read the long way ("two hundred and
# eighty-six"), said the way people say them.
SPOKEN = [(re.compile(r"\bPAL\b"), "Pal"), (re.compile(r"\b286\b"), "two eighty-six"),
          (re.compile(r"\b640 ?(?:KB|K)\b", re.I), "six forty K"), (re.compile(r"\b640\b"), "six forty"),
          (re.compile(r"\b386\b"), "three eighty-six"), (re.compile(r"\b486\b"), "four eighty-six")]


def spoken(text):
    for pattern, said in SPOKEN:
        text = pattern.sub(said, text)
    return text


def trim(wav, timeline, seconds):
    """The first seconds of a tune, faded out over its last two."""
    with wave.open(io.BytesIO(wav)) as w:
        rate, width = w.getframerate(), w.getsampwidth()
        samples = np.frombuffer(w.readframes(int(rate * seconds)), np.int16).astype(np.float32)
    fade = min(len(samples), rate * 2)
    samples[-fade:] *= np.linspace(1, 0, fade)
    out = io.BytesIO()
    with wave.open(out, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(width)
        w.setframerate(rate)
        w.writeframes(samples.astype(np.int16).tobytes())
    return out.getvalue(), [n for n in timeline if n[0] < seconds]


class Left(Exception):
    """F10 took FixBot's page away while PAL waited on it."""


# PAL's name anywhere in what was said to FixBot ("no PAL, I'm good"), as
# Whisper writes it (WAKE has the name at the start).
NAMED = re.compile(r"\b(?:pal|paypal|k-pal)\b|^\W*(?:\w+\W+)?paul\b", re.I)


def describe(present):
    """Who's in view, in a few words: "Joe and 1 unidentified human"."""
    parts = [p["name"] for p in present["people"]]
    if present["strangers"]:
        parts.append(f"{present['strangers']} unidentified human" + ("s" if present["strangers"] > 1 else ""))
    return "In view: " + (" and ".join(parts) if parts else "nobody") + "."


class Sentences:
    """Collects Claude's words as they stream in and hands on whole
    sentences: the first as soon as there is one (so PAL starts talking),
    then a sentence or two at a time."""

    END = re.compile(r"[.!?][\"')\]]*\s")

    def __init__(self, out):
        self.out, self.text, self.first = out, "", True

    def add(self, words):
        if words == "\n":           # the end of a block of text ("One moment." before a search)
            if self.text.strip():
                self.flush()
                self.first = False
            return
        self.text += words
        while True:
            shortest = 10 if self.first else 40
            match = next((m for m in self.END.finditer(self.text) if m.end() >= shortest), None)
            if not match:
                return
            sentence, self.text = self.text[:match.end()].strip(), self.text[match.end():]
            self.first = False
            if sentence:
                self.out(sentence)

    def flush(self):
        if self.text.strip():
            self.out(self.text.strip())
        self.text = ""


class Mouth:
    """PAL's voice, a sentence at a time: one thread turns the next sentence
    into sound while another plays the current one and types it on the
    Compaq. The microphone is deaf while PAL talks, and a moment after (a
    TV plays its sound a little late)."""

    def __init__(self, pal):
        self.pal = pal
        self.texts, self.sounds = queue.Queue(), queue.Queue()
        self.pending = 0
        self.done = threading.Condition()
        threading.Thread(target=self.render, daemon=True).start()
        threading.Thread(target=self.play, daemon=True).start()

    def say(self, text):
        with self.done:
            self.pending += 1
        self.texts.put(("text", text))

    def sound(self, wav):
        """A sound effect, in turn with the speech."""
        with self.done:
            self.pending += 1
        self.texts.put(("wav", wav))

    def wait(self, timeout=90):
        with self.done:
            self.done.wait_for(lambda: self.pending == 0, timeout)

    def hush(self):
        """Stops talking: what's waiting to be said, and what's playing."""
        for waiting in (self.texts, self.sounds):
            while True:
                try:
                    waiting.get_nowait()
                except queue.Empty:
                    break
                with self.done:
                    self.pending -= 1
                    self.done.notify_all()
        self.pal.voice.stop()

    def render(self):
        while True:
            kind, text = self.texts.get()
            if kind == "wav":
                self.sounds.put((None, text, sfx.seconds(text)))
                continue
            wav, seconds = None, 0
            try:
                said = spoken(text) if self.pal.voice.language == "en" else text
                for person in self.pal.present()["people"]:
                    if person.get("say_as"):
                        said = re.sub(rf"\b{re.escape(person['name'])}\b", person["say_as"], said)
                wav, seconds = self.pal.voice.render(said)
            except Exception as e:  # one bad sentence mustn't silence PAL for good
                log("voice:", repr(e))
            self.sounds.put((text, wav, seconds))

    def play(self):
        ears, screen = self.pal.ears, self.pal.screen
        while True:
            text, wav, seconds = self.sounds.get()
            try:
                if wav:
                    ears.deaf_until = time.monotonic() + seconds + 5
                    if text:
                        screen.status("")
                        screen.say("pal", text, max(8.0, len(text) / max(seconds, 0.5)))
                    self.pal.voice.play(wav, text)
            except Exception as e:  # nor one failed playback
                log("speaker:", repr(e))
            finally:
                # (a Bluetooth speaker plays a few tenths of a second late)
                ears.deaf_until = time.monotonic() + (1.0 if self.pal.voice.wireless() else 0.6)
                with self.done:
                    self.pending -= 1
                    self.done.notify_all()


class Track:
    """One face followed from frame to frame while it stays in view."""

    def __init__(self, face, now):
        self.x, self.y, self.w = face.centre[0], face.centre[1], face.w
        self.near_enough = False      # big enough to recognise, in the latest frame
        self.prev_seen = None         # when PAL last saw this (known) person, before now
        self.first = self.last = now
        self.frames = 1
        self.pid = None
        self.signature = None
        self.handled = False          # greeted, or decided not to
        self.recheck = False          # out of sight a moment: is it still the same person?
        self.serial = next(Track.serials)

    serials = itertools.count()       # (each track's own number: Python reuses id()s)

    def near(self, face):
        cx, cy = face.centre
        return abs(cx - self.x) < self.w * 0.8 and abs(cy - self.y) < self.w * 0.8

    def follow(self, face, now):
        self.x, self.y, self.w = face.centre[0], face.centre[1], face.w
        self.last = now
        self.frames += 1


class Pal:
    def __init__(self):
        self.settings = read_settings()
        s = self.settings
        self.name = s.get("NAME", "PAL 286")
        self.apps = read_apps()
        self.app_paths = read_apps(field=1)
        self.people = People()
        self.brain = brain_module.Brain(s, self.apps)
        self.brain.voices = {k: v for k, v in Voice.SOUNDS.items() if k in Voice.STYLES}
        self.eyes = Eyes(s.get("CAMERA", ""))
        self.ears = Ears(s.get("MICROPHONE", ""))
        self.voice = Voice(s.get("VOICE", "mainframe"), int(s.get("SPEED", 150) or 150),
                           int(s.get("PITCH", 28) or 28), int(s.get("VOLUME", 80) or 80),
                           s.get("SPEAKER", ""))
        self.screen = Screen(self.name)
        self.mouth = Mouth(self)
        self.greet_every = float(s.get("GREET_EVERY_HOURS", 4) or 4) * 3600
        self.quiet_hours = s.get("QUIET_HOURS", "")
        if self.quiet_hours and not re.match(r"^\s*\d+\s*-\s*\d+\s*$", self.quiet_hours):
            log(f"QUIET_HOURS={self.quiet_hours!r} isn't hours like 21-7; ignoring it")
        self.speak_typed = s.get("SPEAK_TYPED_CHAT", "no").lower() in ("yes", "1", "true")
        self.tips = s.get("TIPS", "yes").lower() in ("yes", "1", "true")
        self.passerby = s.get("PASSERBY", "yes").lower() in ("yes", "1", "true")
        self.heard_tick = sfx.heard() if s.get("HEARD_TICK", "yes").lower() in ("yes", "1", "true") else None
        try:
            self.music_volume = min(1.0, max(0.05, float(s.get("MUSIC_VOLUME", 0.5) or 0.5)))
        except ValueError:
            self.music_volume = 0.5
        try:
            self.passerby_gap = max(1.0, float(s.get("PASSERBY_MINUTES", 20) or 20)) * 60
        except ValueError:
            self.passerby_gap = 1200.0

        self.lock = threading.RLock()        # tracks, arrivals, latest frame
        self.vision = threading.Lock()       # the face models (one thread at a time)
        self.tracks = []
        self.arrivals = []
        self.arrived_at = 0.0
        self.strangers = []                  # (signature, when): greeted lately, in memory only
        self.last_stranger_greeting = 0.0
        self.latest = (None, [], 0.0)        # newest frame and its faces, for enrolling
        self.enrolling = False
        self.busy = threading.Lock()         # one face to learn or forget at a time
        self.talking = False                 # in a conversation
        self.wrap_up = threading.Event()     # the menu needs PAL: end the conversation
        self.fixbot_left = threading.Event() # F10 took FixBot's page off the screen: FixBot's turn is over
        self.fixbot_handed = False           # PAL opened FixBot by voice (and said so)
        self.turn = threading.Lock()         # one conversation or tip at a time
        self.last_tip = -1e9
        self.game_seen = 0.0                 # when the screen last showed a text adventure in use
        self.game_text = ""                  # and what it showed
        self.last_quip = -1e9
        self.voice_hinted = -1e9             # when PAL last said moves can be spoken
        self.showing = ("", "")              # what's open on the Compaq: (title, menu id)
        self.requests = threading.BoundedSemaphore(6)   # menu requests at once
        self.quiet_until = 0.0
        self.day, self.greeted_today = time.strftime("%F"), 0
        self.last_talk = -1e9
        self.last_convo = None               # to carry on a conversation (see carry_on)
        self.private = False                 # talking to one person, with PAL's notes about them in mind
        self.whisper_tried = 0.0             # when Whisper was last restarted
        self.memory = threading.Lock()       # one conversation's notes written at a time
        # The lobby, as the camera sees it (counts only, in memory only).
        self.burst = None                    # (when movement started after stillness, frames of it)
        self.last_motion = -1e9              # the last frame with movement
        self.passed_today = 0                # roughly how many went past today
        self.last_face = -1e9                # when a face was last in view
        self.last_activity = time.monotonic()
        self.quiet_gap = (0.0, -1e9)         # (how long the lobby had been still, when that ended)
        self.last_shout = -1e9               # the last shout-out to a passer-by
        self.shouts = collections.deque()    # when the last hour's shout-outs were
        self.shouts_today = 0
        self.shout_misses = 0                # shout-outs in a row that nobody stopped for
        self.shout_due = False
        self.keyboard_seen = -1e9            # when someone last used the lobby keyboard
        self.playing = False                 # a tune is playing
        self.quiz_best = (0, 0)              # today's best lobby-quiz score (no names)
        self.english_at = 0.0                # when to go back to English after another language
        self.own_voice = self.voice.style    # pal.conf's VOICE
        self.lobby_voice, self.lobby_voice_until = None, 0.0   # one picked at the menu, for an hour
        self.usual_voice_at = 0.0            # when to go back to it after a conversation in another
        self.fixbot_repair = None            # the repair FixBot is helping with (fixbot_mode.Session)
        self.fixbot_shot = None              # a guide photo on the screen (its connection to the bridge)
        self.fixbot_web = None               # FixBot's own page, when it's open: {page, stop, thread, holders, used}
        self.fixbot_screen = threading.Lock()   # (the page's screen and who's holding it: one change at a time)
        self.passing = None                  # ("fixbot" or "pal", what they said): the conversation changes hands

    # ---------------------------------------------------------- state

    def asleep(self):
        """Quiet mode or quiet hours: no greeting, no listening."""
        if time.time() < self.quiet_until:
            return True
        match = re.match(r"^\s*(\d+)\s*-\s*(\d+)\s*$", self.quiet_hours)
        if match:
            start, end, hour = int(match.group(1)), int(match.group(2)), time.localtime().tm_hour
            if start == end:
                return False
            return start <= hour < end if start < end else hour >= start or hour < end
        return False

    def anyone_here(self):
        now = time.monotonic()
        with self.lock:
            return any(now - t.last < GONE_SECONDS for t in self.tracks)

    def lost_sight(self):
        """The camera stopped: nobody is "seen" any more, and nobody waits
        to be greeted."""
        with self.lock:
            self.tracks, self.arrivals = [], []
            self.latest = (None, [], 0.0)

    def present(self):
        """Who's in front of the camera, for the brain. Every face counts,
        recognised or not; "solo" is the known person's id when they are
        the only face in view (only then are their notes used, or "forget
        me" allowed)."""
        now = time.monotonic()
        with self.lock:
            tracks = [t for t in self.tracks if now - t.last < GONE_SECONDS]
        people = []
        for pid in {t.pid for t in tracks if t.pid}:
            person = self.people.get(pid)
            if person:
                before = next((t.prev_seen for t in tracks if t.pid == pid and t.prev_seen is not None), None)
                people.append(dict(person, pid=pid, **({"last_seen": before} if before is not None else {})))
        solo = tracks[0].pid if len(tracks) == 1 and tracks[0].pid and people else None
        return {"people": people, "strangers": sum(1 for t in tracks if not t.pid), "solo": solo}

    def count_greeting(self, n):
        self.new_day()
        self.greeted_today += n

    def new_day(self):
        today = time.strftime("%F")
        if today != self.day:
            self.day, self.greeted_today, self.passed_today, self.shouts_today = today, 0, 0, 0

    def awareness(self):
        """What the camera has noticed about the lobby, in a sentence or two,
        for the brain: how busy it's been, whether this visitor broke a long
        quiet spell, how long they've been standing there."""
        now = time.monotonic()
        self.new_day()
        notes = [f"Lobby today: about {self.passed_today} people walked past and you greeted "
                 f"{self.greeted_today}."]
        gap, ended = self.quiet_gap
        if gap >= 3600 and now - ended < 300:
            notes.append(f"Before this visitor the lobby had been empty for about {round(gap / 3600, 1):g} hours.")
        if getattr(self, "quiz_day", "") == time.strftime("%F") and self.quiz_best[1]:
            notes.append(f"Today's best lobby-quiz score: {self.quiz_best[0]} out of {self.quiz_best[1]}.")
        return " ".join(notes)

    def screen_now(self):
        """What's open on the Compaq, for the brain, in a sentence."""
        title, app = self.showing
        if not title:
            return ""
        ids = {path: name for name, path in self.app_paths.items()}
        known = f" (that's {ids[app]} in open_on_compaq)" if app in ids else ""
        return (f"Open on the Compaq's screen right now: {title}{known}. Don't offer to open "
                "what's already open.")

    def notice(self, now, faces, busy=False):
        """Keeps the lobby counts, and spots someone walking past without
        turning to the camera (worth a quick shout-out now and then). busy:
        someone was already in view."""
        seen = bool(faces) or busy
        if seen:
            self.last_face = now
        moving = not busy and MOTION_AREA[0] <= self.eyes.area <= MOTION_AREA[1]
        if seen or moving:
            if now - self.last_activity > 300:      # the lobby wakes up after a quiet spell
                self.quiet_gap = (now - self.last_activity, now)
            self.last_activity = now
        if seen:
            if self.shouts and now - self.shouts[-1] < 60:
                self.shout_misses = 0                # someone stopped after a shout-out
            return
        # Someone going past is a short burst of movement after stillness;
        # people moving about for longer (someone waiting, fidgeting) aren't.
        if not moving:
            if self.burst and now - self.last_motion >= 2:
                start, frames = self.burst
                self.burst = None
                if frames >= 2 and self.last_motion - start < 6:
                    self.passed(now)
            return
        if self.burst is None and now - self.last_motion >= 10:
            self.burst = (now, 0)
        if self.burst:
            self.burst = (self.burst[0], self.burst[1] + 1)
        self.last_motion = now

    def passed(self, now):
        """Someone just walked past: counted, and now and then a shout-out.
        At most 3 an hour and 15 a day, and further apart each time nobody
        stops (a busy corridor doesn't need a running commentary)."""
        self.new_day()
        self.passed_today += 1
        while self.shouts and now - self.shouts[0] > 3600:
            self.shouts.popleft()
        if self.shout_misses and now - self.last_shout > 4 * 3600:
            self.shout_misses = 0                    # a fresh start after a quiet few hours
        gap = self.passerby_gap * min(4, 2 ** self.shout_misses) * random.uniform(1, 1.5)
        if (self.passerby and not self.asleep() and not self.talking and not self.enrolling
                and now - self.last_shout >= gap and self.shouts_today < 15 and len(self.shouts) < 3
                and now - self.last_face > 20 and now - self.last_talk > 60
                and now - self.keyboard_seen > 60):
            self.shout_due = True

    # ---------------------------------------------------------- watching

    def watch(self):
        """The camera loop: follows faces, works out who they are, and queues
        arrivals to greet."""
        while True:
            if not self.eyes.open():
                self.lost_sight()
                time.sleep(30)
                continue
            log("camera:", self.eyes.status)
            looked = 0.0
            while True:
                try:
                    # Someone has just spoken: Whisper gets the processor (it
                    # takes seconds on a Pi 3, and they're waiting), though
                    # never for so long that people in view count as gone.
                    if self.ears.transcribing and time.monotonic() - looked < 2.0:
                        time.sleep(0.1)
                        continue
                    looked = time.monotonic()
                    image = self.eyes.frame()
                    if image is None:
                        self.lost_sight()
                        break
                    now = time.monotonic()
                    with self.lock:
                        busy = bool(self.tracks)
                    moving = busy or self.eyes.moved(image)
                    if not moving and not self.enrolling:
                        self.notice(now, [])
                        time.sleep(0.4)                # an empty, still lobby: rest
                        continue
                    with self.vision:
                        faces = self.eyes.faces(image)
                    self.see(image, faces, now)
                    self.notice(now, faces, busy)
                    # Quick while someone new needs a look; slower once
                    # everyone in view is known, and slower still while PAL
                    # talks, which leaves the processor (and the Pi's
                    # temperature) to Whisper and the voice.
                    with self.lock:
                        new_face = any(t.signature is None and t.near_enough for t in self.tracks)
                    time.sleep(0.15 if self.enrolling or (new_face and not self.talking)
                               else 1.0 if self.talking else 0.7)
                except Exception as e:  # keep watching whatever goes wrong
                    log("camera loop:", repr(e))
                    self.lost_sight()             # don't keep "seeing" people who left
                    time.sleep(2)
            time.sleep(5)

    def see(self, image, faces, now):
        width = image.shape[1]
        with self.lock:
            self.latest = (image, faces, now)
            fresh, again = [], []
            for face in faces:
                track = next((t for t in self.tracks if t.near(face)), None)
                if track:
                    if track.signature is not None and now - track.last >= RECHECK_GAP:
                        track.recheck = True
                    track.follow(face, now)
                else:
                    track = Track(face, now)
                    self.tracks.append(track)
                track.near_enough = face.w >= RECOGNISE_SIZE * width
                if track.signature is None and track.frames >= 2 and track.near_enough:
                    fresh.append((track, face))
                elif track.recheck and track.near_enough:
                    again.append((track, face))
            self.tracks = [t for t in self.tracks if now - t.last < GONE_SECONDS]
        if self.enrolling:
            return
        for track, face in ([] if fresh else again[:1]):
            # A face back in the same spot after a gap needn't be the same
            # person (one steps aside, another steps up): look again, and
            # if it's someone else, they're a new arrival, not the first
            # person's name and notes.
            with self.vision:
                signature = normalise(self.eyes.signature(image, face))
            with self.lock:
                track.recheck = False
                same = float(signature @ track.signature) >= SAME_PERSON
                if not same:
                    self.tracks = [t for t in self.tracks if t is not track]
                    track = Track(face, now)
                    track.frames, track.near_enough, track.signature = 2, True, signature
                    self.tracks.append(track)
            if not same:
                pid, _ = self.people.match(signature)
                with self.lock:
                    track.pid = pid
                self.consider(track)
        for track, face in fresh[:1]:          # someone new has stayed a moment: who is it?
            # (one a pass: each takes about a second on a Pi 3)
            with self.vision:
                signature = normalise(self.eyes.signature(image, face))
            pid, _ = self.people.match(signature)
            with self.lock:
                track.signature, track.pid = signature, pid
            self.consider(track)

    def consider(self, track):
        """Should PAL greet this newly identified face?"""
        now = time.time()
        if track.pid:
            person = self.people.get(track.pid)
            track.prev_seen = person.get("last_seen", 0)     # for "last seen ...", before it's updated
            fields = {"last_seen": now}
            if now - person.get("last_seen", 0) > 2 * 3600:
                fields["visits"] = person.get("visits", 0) + 1
            self.people.update(track.pid, **fields)
            due = now - person.get("last_greeted", 0) >= self.greet_every
        else:
            self.strangers = [(s, t) for s, t in self.strangers if now - t < STRANGER_MEMORY]
            seen = any(float(s @ track.signature) >= SAME_PERSON for s, _ in self.strangers)
            self.strangers.append((track.signature, now))
            # One greeting for a stream of visitors, not one each.
            due = not seen and now - self.last_stranger_greeting > STRANGER_GAP
        if due and not self.asleep():
            with self.lock:
                if not self.arrivals:
                    self.arrived_at = time.monotonic()
                self.arrivals.append(track)
        else:
            track.handled = True

    def take_arrivals(self):
        """Arrivals to greet, gathered for a second so a group gets one greeting."""
        with self.lock:
            if not self.arrivals or time.monotonic() - self.arrived_at < 1.0:
                return []
            # Only those still here (not someone who walked through during
            # the last conversation).
            arrivals = [t for t in self.arrivals if t in self.tracks]
            self.arrivals = []
        return arrivals

    # ---------------------------------------------------------- talking

    def speak(self, text):
        """Says text (and types it on the Compaq), returning when it's said."""
        self.note_said(text)
        self.mouth.say(text)
        self.mouth.wait()

    def note_said(self, text):
        """Remembers what PAL said, so it doesn't repeat its jokes today.
        Not what it said to someone on their own from its notes about them:
        that list goes into later conversations with other people."""
        if not self.private:
            self.brain.note(self.anonymous(text))

    def act(self, tool, args, convo):
        """Runs a tool Claude asked for during a spoken conversation."""
        log(f"tool: {tool}")
        if tool == "open_on_compaq":
            program = str(args.get("program", ""))
            if program not in self.apps:
                return "There's no such program."
            if program == "fixbot" and brain_module.fixbot_on():
                # FixBot by voice: its page on the screen, listening. (The
                # menu's FixBot is typed, and PAL would stop listening.)
                self.passing, self.fixbot_handed = ("fixbot", ""), True
                convo["opened"] = True
                return "FixBot has the conversation now and answers them itself. Say nothing more."
            result = subprocess.run(["sudo", "-n", "-u", "desk", VOICE_OPEN, program],
                                    capture_output=True, text=True, timeout=20)
            message = (result.stdout or result.stderr).strip() or "It didn't work."
            if result.returncode == 0:
                convo["opened"] = True
                self.screen.end(wake=True)      # show the program, not PAL
            return message
        if tool == "look":
            with self.lock:
                image = self.latest[0]
            if image is None or not self.eyes.status.startswith(("ok", "test")):
                return f"The camera isn't working ({self.eyes.status})."
            log("look: someone showed the camera something")
            return self.brain.see(vision.jpeg_base64(image), str(args.get("question", ""))[:300])
        if tool == "find_repair_guides":
            try:
                results = [r for r in ifixit.search(str(args.get("search", ""))[:100])
                           if isinstance(r, dict) and r.get("id")][:5]
            except ifixit.FixBotError as e:
                return f"The guide search didn't work: {e}"
            if not results:
                return "No guides found; try fewer or different words."
            return "Guides: " + "; ".join(
                f"{r['id']}: {r.get('title', '?')} (https://www.ifixit.com/Guide/"
                f"{urllib.parse.quote_plus(str(r.get('title') or '_'))}/{r['id']})" for r in results)
        if tool == "show_guide":
            guide = str(args.get("guide", ""))
            result = subprocess.run(["sudo", "-n", "-u", "desk", VOICE_OPEN, "guide", guide],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode == 0:
                convo["opened"] = True
                self.screen.end(wake=True)
            return (result.stdout or result.stderr).strip() or "It didn't work."
        if tool == "insert_floppy":
            disk = str(args.get("disk", "")).strip().lower()
            result = subprocess.run(["sudo", "-n", "-u", "desk", VOICE_OPEN, "floppy", disk],
                                    capture_output=True, text=True, timeout=60)
            return (result.stdout or result.stderr).strip() or "It didn't work."
        if tool in ("show_web_search", "play_youtube"):
            words = " ".join(re.sub(r"[^A-Za-z0-9 ,.'?!&:+-]", " ", str(args.get("search", ""))).split())[:100]
            if not words:
                return "Search for what? Ask them."
            what = ("search" if tool == "show_web_search"
                    else "youtube-hd" if args.get("hd") is True else "youtube")
            result = subprocess.run(["sudo", "-n", "-u", "desk", VOICE_OPEN, what, words],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode == 0:
                convo["opened"] = True
                self.screen.end(wake=True)
            return (result.stdout or result.stderr).strip() or "It didn't work."
        if tool == "fixbot":
            # FixBot takes over, with what they said as they said it.
            heard = convo.get("last_heard", "")
            if heard.startswith("(said your name") or args.get("just_open") is True:
                heard = ""                       # (FixBot asks what they're fixing)
            self.passing, self.fixbot_handed = ("fixbot", heard), True
            convo["opened"] = True
            return "FixBot has the conversation now and answers them itself. Say nothing more."
        if tool == "fixbot_plan":
            if not brain_module.key_from_file(brain_module.FIXBOT_ENV, "FIXBOT_API_KEY"):
                return ("FixBot isn't switched on yet (no key), so offer the iFixit guide "
                        "instead (find_repair_guides, show_guide).")
            device = re.sub(r"[^A-Za-z0-9 ,.()?!/+-]", "", str(args.get("device", "")))[:100]
            problem = re.sub(r"[^A-Za-z0-9 ,.'()?!/+-]", "", str(args.get("problem", "")))[:300]
            result = subprocess.run(["sudo", "-n", "-u", "desk", VOICE_OPEN, "fixbot-ask",
                                     device or "unknown device", problem or "What's wrong with it?"],
                                    capture_output=True, text=True, timeout=20)
            if result.returncode == 0:
                convo["opened"] = True
                self.screen.end(wake=True)
            return (result.stdout or result.stderr).strip() or "It didn't work."
        if tool == "mirror":
            return self.mirror(convo, min(60, max(10, int(args.get("seconds", 30) or 30))))
        if tool == "take_photo":
            return self.take_photo(convo)
        if tool == "show_qr_code":
            return self.show_qr_code(str(args.get("link", "")).strip(), str(args.get("caption") or ""))
        if tool == "save_photo":
            if not convo.get("photo"):
                return "There's no photo to save yet: take one first."
            name = vision.save_portrait(*convo["photo"])
            log("photo booth: saved a portrait")
            return f"Saved to the gallery (PAL 286 menu, Photo booth gallery) as {name}."
        if tool == "play_music":
            return self.play_music(tune=args.get("tune"), notation=args.get("notation"),
                                   title=str(args.get("title") or ""), convo=convo)
        if tool == "sing":
            return self.play_music(song=str(args.get("song", "")), name=str(args.get("name") or ""),
                                   convo=convo)
        if tool == "remember_birthday":
            solo = self.present()["solo"]
            if not solo or solo != convo.get("solo"):
                return "Not saved: only for the one recognized person in view, about themselves."
            try:
                when = time.strptime(f"2000-{int(args.get('month'))}-{int(args.get('day'))}", "%Y-%m-%d")
            except (TypeError, ValueError):
                return "That isn't a date."
            self.people.update(solo, birthday=time.strftime("%m-%d", when))
            log("remembered a birthday")
            return "Saved. You'll sing to them when you first see them on the day."
        if tool == "speak_language":
            code = str(args.get("language") or "en").lower().split("-")[0]
            if code not in LANGUAGES:
                return "Your voice can't do that language; say so in character."
            heard = self.ears.set_language(code)
            self.voice.language = code
            convo["language"] = code
            log(f"language: {code}")
            if code == "en":
                return "Back to English."
            return ("Switched: your voice speaks it now, so answer in it, simply."
                    + ("" if heard else " But you can't understand it spoken (its speech model isn't "
                       "installed), so they'll need to speak English to you."))
        if tool == "change_voice":
            style = str(args.get("voice") or "")
            style = self.usual_voice() if style == "usual" else style
            if style not in Voice.STYLES:
                return "You don't have that voice: say so in character."
            self.voice.style = style
            log(f"voice: {style}")
            if style == self.usual_voice():
                return "Back to your usual voice."
            return (f"You sound like {Voice.SOUNDS[style]} now, for the rest of this conversation: play the "
                    "part a little in what you say, kindly, in the same plain words.")
        if tool == "quiz_board":
            convo["quiz"] = True
            return self.quiz_board(args, convo)
        if tool == "quiet_mode":
            try:
                minutes = min(120, max(5, int(args.get("minutes", 60))))
            except (TypeError, ValueError, OverflowError):
                minutes = 60
            self.quiet_until = time.time() + minutes * 60
            convo["quiet"] = True
            log(f"quiet mode for {minutes} minutes")
            return f"Quiet mode is on for {minutes} minutes, starting when you stop talking."
        if tool == "forget_me":
            # Checked here, not left to the model: only the one recognised
            # person in view, who has asked in their own words ("forget me")
            # and has just said it again or said yes when PAL checked.
            solo = self.present()["solo"]
            heard = convo.get("last_heard", "")
            said_so = (FORGET_WORD.search(heard) and not DONT_FORGET.search(heard)) or agreed(heard, YES)
            if not solo or solo != convo.get("solo") or not convo.get("asked_forget") or not said_so:
                return ("Not done: that only works when the one recognised person in view "
                        "asks, in their own words, for you to forget them, and confirms.")
            name = self.people.get(solo).get("name", "them")
            self.people.forget(solo)
            convo["forgot"] = solo
            with self.lock:
                for t in self.tracks:
                    if t.pid == solo:
                        t.pid = None
            log("forgot someone, at their request")
            return f"Done: {name}'s face and notes are gone."
        return "Unknown tool."

    def mirror(self, convo, seconds):
        """The webcam as live text art on the Compaq: a mirror, in 1987."""
        if not self.eyes.status.startswith(("ok", "test")):
            return f"The camera isn't working ({self.eyes.status})."
        if not self.screen.begin(canvas=True, requested=True):
            return "Couldn't take over the screen: someone is using it from a browser."
        log("mirror: on")
        end, shown = time.monotonic() + seconds, 0
        while time.monotonic() < end and self.screen.shown:
            with self.lock:
                image = self.latest[0]
            if image is not None:
                small = vision.picture(image).resize((160, 120))           # (the dots' version)
                self.screen.frame(vision.text_art(image, rows=21) + [f"{'- MIRROR MODE -':^79}"],
                                  {"kind": "mirror", "width": 160, "height": 120,
                                   "image": base64.b64encode(small.tobytes()).decode()})
                shown += 1
            time.sleep(0.25)
        still = self.screen.shown
        self.screen.end()
        self.screen.begin()                  # back to PAL's eye for the rest of the chat
        return (f"Mirror mode ran for {seconds} seconds (you can't see it: no remarks on looks)." if still
                else "Someone pressed a key at the Compaq, so the mirror stopped.")

    def take_photo(self, convo):
        """The photo booth: a countdown, then the person painted on the
        Compaq's screen as a real photo, dithered into amber dots (or as
        text art if pictures can't go up). Only a text-art version is ever
        kept, and only if they ask (save_photo)."""
        if not self.eyes.status.startswith(("ok", "test")):
            return f"The camera isn't working ({self.eyes.status})."
        for word in ("Three.", "Two.", "One.", "Say cheese!"):
            self.speak(word)
        with self.lock:
            image = self.latest[0]
        if image is None:
            return "The camera didn't give me a picture."
        self.mouth.sound(sfx.shutter())
        lines = vision.text_art(image, rows=21)
        caption = f"PAL 286 PHOTO BOOTH   {time.strftime('%d %b %Y  %I:%M %p').replace(' 0', ' ')}"
        convo["photo"] = (lines, caption)
        if not self.screen.begin(canvas=True, requested=True):     # (is the screen free?)
            return "Took the photo, but couldn't show it: someone is using the screen from a browser."
        log("photo booth: took a picture")
        seconds = self.show_picture(vision.picture(image), caption, 30)
        if seconds:
            # (a second or two through PILINK; ten, painting down the screen, through Kermit)
            arriving = (f"painting line by line down the cable like 1987, about {round(seconds)} seconds to arrive"
                        if seconds >= 4 else "there in a blink, every dot the plasma has")
            return (f"Took the photo; it's on the Compaq's screen now, a real photo in amber dots "
                    f"({arriving}, then up for half a minute). It isn't kept unless they ask you to save "
                    f"it (save_photo), and the gallery keeps only a text-art version, never the photo. "
                    f"You can't see it: joke about the booth or the dots, never how they look, and "
                    f"don't count down again (the booth did).")
        self.screen.frame(lines + [f"{caption:^79}"])
        threading.Thread(target=self.hold_photo, args=(self.screen.pictures,), daemon=True).start()
        return ("Took the photo; it's on the Compaq's screen as text art for 20 seconds. "
                "It isn't kept unless they ask you to save it (save_photo). You can't see it: "
                "joke about the booth or the text art, never how they look, and don't count down "
                "again (the booth did).")

    def hold_photo(self, picture):
        time.sleep(20)
        if self.screen.shown and self.screen.canvas and self.screen.pictures == picture and self.talking:
            self.screen.begin()              # back to the eye if the chat goes on

    def show_picture(self, image, caption, seconds):
        """A real picture on the Compaq's screen (through the serial bridge,
        in place of PAL's scene), left up for seconds once it's painted, or
        until a key there or another picture. Only the lobby sees it, like
        PAL's scenes: not browsers watching the shared screen. The seconds
        it takes to paint, or 0 if it couldn't go up."""
        try:
            conn, paint = pictures.put_up(image, caption, lobby_only=True)
        except pictures.NotShown as e:
            log(f"picture: {e}")
            return 0
        self.screen.shown = self.screen.canvas = False   # (the picture took the scene's place)

        def hold():
            try:
                select.select([conn], [], [], paint + seconds)
            finally:
                conn.close()                 # (the shared screen comes back)
        threading.Thread(target=hold, daemon=True).start()
        return max(1, round(paint))

    def show_qr_code(self, link, caption):
        """A QR code for a web address on the Compaq's screen, for phones."""
        parsed = urllib.parse.urlparse(link)
        if (parsed.scheme not in ("http", "https") or not parsed.netloc or len(link) > 400
                or any(c.isspace() or not c.isprintable() for c in link)):
            return "That isn't a web address I can make a QR code for."
        try:
            code = pictures.qr(link)
        except pictures.NotShown as e:
            return str(e)
        if not self.screen.begin(canvas=True, requested=True):     # (is the screen free?)
            return "Couldn't show it: someone is using the Compaq's screen from a browser."
        host = parsed.netloc.lower().removeprefix("www.")
        caption = " ".join(re.sub(r"[^A-Za-z0-9 ,.'&:!?()-]", " ", caption).split())[:40]
        label = f"{caption} ({host})" if caption else f"Scan to open {host}"
        if not self.show_picture(code, label[:79], 60):
            return "The Compaq's screen didn't take it."
        log("qr code: shown")
        return (f"The QR code for {host} is on the Compaq's screen for a minute: they point their "
                f"phone's camera at it.")

    # ---------------------------------------------------------- music

    def play_music(self, tune=None, notation=None, title="", song=None, name="", convo=None,
                   show=True, on_start=None, longest=32):
        """Plays a tune from the library (tune), one Claude just wrote
        (notation), or sings (song: daisy or birthday, to name), showing it
        on the Compaq if the screen is free. on_start(meta, timeline,
        seconds) hears when the sound starts (the jukebox draws its own
        picture). Returns what happened, for Claude."""
        try:
            if song:
                if song not in music.SONGS:
                    return "There's no such song: daisy or birthday."
                name = " ".join(re.sub(r"[^A-Za-z' -]", "", name).split())[:24]
                sung = next((p.get("say_as") for p in self.present()["people"]
                             if p.get("say_as") and p.get("name", "").lower() == name.lower()), name)
                wav, timeline = music.sing(song, name=sung or None, volume=self.music_volume)
                meta = {"title": music.SONGS[song]["title"], "composer": "Sung by PAL 286",
                        "fact": (f"Happy birthday, {name}!" if song == "birthday" and name else
                                 "Happy birthday!" if song == "birthday" else
                                 "In 1961 an IBM 7094 at Bell Labs sang this song: one of the first "
                                 "songs a computer ever sang.")}
            elif notation:
                wav, timeline = music.render(music.parse(str(notation)[:music.MAX_TEXT]),
                                             volume=self.music_volume)
                if music.seconds(wav) < 10:
                    return (f"That tune is only {music.seconds(wav):.0f} seconds long. Make it 15 to 30 "
                            "seconds (more bars, or repeat sections with ( )x2) and call play_music again.")
                meta = {"title": " ".join(re.sub(r"[^ -~]", "", title).split())[:60] or "Untitled",
                        "composer": "Composed live by PAL 286",
                        "fact": "Written a moment ago, just for this lobby."}
            else:
                tune_id = tune if tune in music.TUNES else music.find(str(tune or ""))
                if not tune_id:
                    return "That isn't in your library."
                meta = music.TUNES[tune_id]
                wav, timeline = music.render(meta["score"], volume=self.music_volume)
        except ValueError as e:
            return f"The tune didn't work: {e} Fix it and call play_music again."
        if longest and music.seconds(wav) > longest:
            wav, timeline = trim(wav, timeline, longest)   # (the whole thing is in the Jukebox)
        seconds = music.seconds(wav)
        self.playing = True                   # (no "one sec" from here on)
        self.mouth.wait()                     # (after whatever PAL is saying)
        stop = threading.Event()
        shown = show and self.screen.begin(canvas=True, requested=True)
        painter = threading.Thread(target=self.show_music, args=(meta, timeline, seconds, stop),
                                   daemon=True)
        if shown:
            painter.start()
        log(f"music: {'a song' if song else 'a new tune' if notation else 'a tune'} ({seconds:.0f} s)")
        self.ears.deaf_until = time.monotonic() + seconds + 3
        started = time.monotonic()
        try:
            if on_start:
                on_start(meta, timeline, seconds)
            self.voice.play(wav)
        finally:
            stop.set()
            self.playing = False
            self.ears.deaf_until = time.monotonic() + 0.8
        if shown:
            painter.join(2)
            self.screen.end()
            if convo is not None and not convo.get("opened"):
                self.screen.begin()          # back to the eye for the rest of the chat
        if self.voice.stopped:
            return f"Stopped after {time.monotonic() - started:.0f} seconds: someone turned it off."
        return f"Played {meta['title']} ({seconds:.0f} seconds) to the lobby."

    def show_music(self, meta, timeline, seconds, stop):
        """PAL's "now playing" card while a tune plays. A key at the
        Compaq takes the screen back, and stops the music too."""
        rows = jukebox.card(meta, seconds)
        by = ", ".join(str(v) for v in (meta.get("composer"), meta.get("year")) if v)
        start, second = time.monotonic(), -1
        while not stop.is_set():
            t = time.monotonic() - start
            rows[jukebox.MARKER_ROW] = jukebox.marker_row(timeline, t)
            if int(t) != second:
                second = int(t)
                rows[jukebox.PROGRESS_ROW] = f"{jukebox.progress(t, seconds):^79}"
            board = {"kind": "music", "title": jukebox.ascii_text(meta.get("title", "A tune")),
                     "by": jukebox.ascii_text(by), "fact": jukebox.ascii_text(meta.get("fact", "")),
                     "notes": jukebox.notes_now(timeline, t), "t": t, "total": seconds}
            if not self.screen.frame(rows, board):
                self.voice.stop()
                return
            stop.wait(0.25)

    def quiz_board(self, args, convo):
        """The lobby quiz's board on the Compaq: a question with its
        choices, or (final) the final score."""
        def number(key, default=0):
            try:
                return max(0, min(99, int(args.get(key, default))))
            except (TypeError, ValueError):
                return default
        score, total = number("score"), number("total")
        if args.get("final"):
            convo["quiz"] = False
            rows = boards.final(score, total, str(args.get("title") or ""))
            board = {"kind": "final", "score": score, "total": total, "title": boards.plain(args.get("title"), 70)}
            today = time.strftime("%F")
            best = self.quiz_best if getattr(self, "quiz_day", "") == today else (0, 0)
            if total and (best[1] == 0 or score / total > best[0] / best[1]):
                self.quiz_best, self.quiz_day = (score, total), today
            log(f"quiz: final score {score}/{total}")
        else:
            choices = [str(c) for c in args.get("choices") or [] if str(c).strip()][:4]
            self.brain.note_quiz(args.get("question") or "")
            rows = boards.quiz(str(args.get("question") or ""), choices, number("number"), total,
                               score, str(args.get("topic") or ""))
            board = {"kind": "quiz", "question": boards.plain(args.get("question")),
                     "choices": [boards.plain(c, 120) for c in choices], "number": number("number"),
                     "total": total, "score": score, "topic": boards.plain(args.get("topic"), 30)}
        shown = self.screen.canvas and self.screen.frame(rows, board)
        if not shown:               # (lost the screen for a moment: take it again)
            shown = self.screen.begin(canvas=True, requested=True) and self.screen.frame(rows, board)
        if args.get("final"):
            after = ""
        else:
            after = (" When they've answered, call quiz_board again with the next question and the "
                     "new score (or final: true after the last one).")
        if shown:
            return "It's on the Compaq's screen. Read it out too: not everyone can see it." + after
        return "Read it out (no need to mention the screen)." + after

    def anonymous(self, text):
        """text without the names of people PAL knows (for its list of what
        it said today, which shouldn't say who came in)."""
        for name, _ in self.people.names():
            if name:
                text = re.sub(rf"\b{re.escape(name)}\b", "you", text, flags=re.I)
        return text

    def respond(self, job):
        """Speaks Claude's words sentence by sentence as they're written (the
        first is said while the rest are still coming), with a short "one
        moment" if nothing has come after a few seconds. job(on_text,
        on_search, on_tool) runs the request. Returns (everything said,
        sources), or (None, []) when Claude says it wasn't meant for PAL."""
        said, searching, skipped, tooled = [], [], [], []

        asked_at = time.monotonic()

        def out(sentence):
            if self.passing:
                return                   # (FixBot has the conversation now: Claude's done)
            if re.fullmatch(r"\W*SKIP\W*", sentence):
                skipped.append(True)     # (not meant for PAL: a phone call, say)
            else:
                if not said:             # how long people waited (seconds only, for tuning)
                    speech, whisper = self.ears.timing
                    log(f"timing: {speech:.1f} s of speech, Whisper {whisper:.1f} s, "
                        f"first words {time.monotonic() - asked_at:.1f} s later")
                said.append(sentence)
                self.mouth.say(sentence)

        sentences = Sentences(out)

        def on_search():                 # a web search: the modem dials
            searching.append(True)
            self.mouth.sound(sfx.modem())

        def on_tool(name):
            tooled.append(name)          # (no "one sec" over a photo countdown or a tune)
            if name == "play_music" and not self.playing:
                self.mouth.sound(sfx.floppy())   # composing takes a while: the drive grinds

        # Nothing yet after a moment: the floppy drive grinds; still
        # nothing: a quick "one sec".
        quiet = lambda: said or tooled or self.playing  # noqa: E731
        timers = [threading.Timer(2.0, lambda: None if quiet() else self.mouth.sound(sfx.floppy())),
                  threading.Timer(5.0, lambda: None if quiet() else
                                  self.mouth.say(lines.thinking(search=bool(searching))))]
        for timer in timers:
            timer.start()
        sources, failed = [], False
        try:
            _, sources = job(sentences.add, on_search, on_tool)
        except brain_module.BrainError as e:
            log("brain:", e)
            failed = True
        except Exception as e:  # keep talking whatever goes wrong
            log("brain:", repr(e))
            failed = True
        finally:
            for timer in timers:
                timer.cancel()
            sentences.flush()
        if not said and skipped and not failed:
            return None, []
        if not said:
            text = lines.offline() if failed else lines.huh()
            said.append(text)
            self.mouth.say(text)
        self.note_said(" ".join(said))
        self.mouth.wait()
        if sources:
            self.screen.say("pal", "(Source: " + ", ".join(sources[:2]) + ")", 200)
        return " ".join(said), sources

    def listen(self, seconds, until=None):
        """The next thing someone says within seconds, or None (also when
        everyone has walked away, or until is set). The moment they stop
        talking, a soft tick says PAL heard (Whisper then takes a few
        seconds)."""
        if self.heard_tick:
            self.ears.cue = self.tick
        self.ears.listening = True
        self.screen.status("your turn - just talk", blink=True)
        start = time.monotonic()
        deadline = start + seconds
        try:
            while not self.wrap_up.is_set() and not (until and until.is_set()):
                try:
                    return self.ears.utterances.get(timeout=0.3)
                except queue.Empty:
                    pass
                now = time.monotonic()
                if (self.ears.capturing or self.ears.transcribing) and now < start + seconds + 20:
                    deadline = max(deadline, now + 1.0)     # they're mid-sentence: hear them out
                elif not self.anyone_here() and self.eyes.status.startswith("ok"):
                    deadline = min(deadline, now + 2)
                if now >= deadline:
                    return None
            return None
        finally:
            self.ears.listening = False
            self.ears.cue = None

    def tick(self):
        """PAL's "got it": from the Compaq's own speaker when it can (PILINK
        as its terminal), else the lobby speaker. (Off the caller's thread:
        the microphone's must keep reading.)"""
        threading.Thread(target=lambda: self.screen.beep(TICK) or self.mouth.sound(self.heard_tick),
                         daemon=True).start()

    def conversation(self, arrivals=None, first=None):
        """A greeting and/or a back-and-forth, until people stop talking."""
        asked = time.monotonic()
        with self.turn:
            # (PAL's turn may have been a while coming: a tune or a video's
            # sound was playing. Don't greet people who've left since, or
            # answer a "Hey PAL" from minutes ago.)
            if arrivals:
                with self.lock:
                    arrivals = [t for t in arrivals if t in self.tracks]
                if not arrivals:
                    return
            elif time.monotonic() - asked > 8:
                return
            try:
                self.talk("pal", first, arrivals)
            finally:
                self.private = False

    def talk(self, who, first, arrivals=None):
        """PAL's conversation or FixBot's, then whichever one it handed
        over to ("Hey FixBot" in PAL's, "Hey PAL" in FixBot's)."""
        while who:
            self.passing = None
            if who == "fixbot":
                self.fixbot_talk(first)
            else:
                self.converse(arrivals, first)
            arrivals = None
            who, first = self.passing or (None, None)
        self.passing = None

    def carry_on(self, present):
        """The last conversation, if this is the same people picking it up
        again within FOLLOW_UP_SECONDS (so "and what about tomorrow?" makes
        sense); else None."""
        last, self.last_convo = self.last_convo, None
        if not last or time.monotonic() - last["ended"] > FOLLOW_UP_SECONDS:
            return None
        with self.lock:
            here = {t.serial for t in self.tracks if time.monotonic() - t.last < GONE_SECONDS}
        if describe(present) != last["view"] or present["solo"] != last["convo"]["solo"] \
                or here != last["faces"]:
            return None             # (someone new, even if they look the same to a count)
        if len(last["messages"]) > 40 or last["convo"].get("quiet") or last["convo"].get("forgot"):
            return None
        return last

    def converse(self, arrivals, first):
        self.talking = True
        if first is None:
            self.ears.clear()            # (after "Hey PAL", the rest may still be on its way)
        self.screen.asked = not arrivals     # ("Hey PAL", or handed over by FixBot: not a greeting)
        self.screen.begin()
        present = self.present()
        if arrivals:
            self.count_greeting(len(arrivals))   # (before the brain is told the day's total)
        present["lobby"] = self.awareness()
        present["screen"] = self.screen_now()
        last = None if arrivals else self.carry_on(present)
        if last:
            ctx, messages, convo, view = last["ctx"], last["messages"], last["convo"], last["view"]
            convo.pop("opened", None)
        else:
            # PAL's instructions are fixed for the whole conversation (Claude
            # needs the start of a conversation to stay the same from turn to
            # turn); changes in who's in view go into what people say instead.
            ctx = self.brain.prepare(present, self.greeted_today) if self.brain.ready() else None
            view = describe(present)
            messages, convo = [], {"solo": present["solo"], "notes_for": present["solo"],
                                   "screen": present["screen"]}
        self.private = bool(convo.get("notes_for"))
        transcript = []
        asked = False              # did PAL just ask something? (only then does it wait for an answer)
        log("conversation" + (" (greeting)" if arrivals else " (carrying on)" if last else ""))
        try:
            if arrivals:
                names = list(dict.fromkeys(self.people.get(t.pid).get("name") for t in arrivals
                                           if t.pid and self.people.get(t.pid)))
                strangers = sum(1 for t in arrivals if not t.pid)
                for track in arrivals:
                    track.handled = True
                    if track.pid:
                        self.people.update(track.pid, last_greeted=time.time())
                if strangers:
                    self.last_stranger_greeting = time.time()
                log(f"greeted {len(names)} known, {strangers} visitor(s)")   # no names in the log
                if ctx:
                    ask = self.brain.greeting_ask(names, strangers)
                    text, _ = self.respond(lambda on_text, *_: (self.brain.greet(ctx, ask, on_text), []))
                    text = text or lines.greeting(names, strangers, time.localtime().tm_hour)
                else:
                    ask = "[Someone arrived and you greeted them.]"
                    text = lines.greeting(names, strangers, time.localtime().tm_hour)
                    self.speak(text)
                messages = [{"role": "user", "content": ask}, {"role": "assistant", "content": text}]
                transcript.append(f"{self.name}: {text}")
                asked = asks(text)
                # A birthday they told PAL about: sung when they're alone (it
                # isn't PAL's to announce to others).
                solo = self.present()["solo"]
                person = self.people.get(solo) if solo else None
                if person and person.get("birthday") == time.strftime("%m-%d") \
                        and person.get("sung") != time.strftime("%F"):
                    self.people.update(solo, sung=time.strftime("%F"))
                    log("singing happy birthday")
                    self.play_music(song="birthday", name=person.get("name", ""), convo=convo)
                    convo["note"] = "[You just sang Happy Birthday to them.]"
            question = first
            if question == "":
                # Just "Hey PAL": the rest often follows after a breath.
                question = self.listen(2.5) or ""
            while not convo.get("quiet") and not convo.get("opened") and not self.wrap_up.is_set():
                if question is None:
                    # An answer to a question PAL asked, or a few seconds in
                    # case they carry on (people talking among themselves
                    # afterwards aren't talking to PAL: Claude says SKIP).
                    if asked or convo.get("quiz"):
                        self.screen.beep(YOUR_TURN)
                    question = self.listen(QUIZ_SECONDS if convo.get("quiz") else
                                           LISTEN_SECONDS if asked else FOLLOW_ON_SECONDS)
                    if question is None:
                        break
                fix = fixbot_mode.WAKE.match(question)
                if fix or fixbot_mode.just_the_name(question):    # "Hey FixBot, ...": FixBot's turn
                    self.passing = ("fixbot", question[fix.end():].strip() if fix else "")
                    break
                name = WAKE.match(question) or NAME_ONLY.match(question)
                if name:                       # ("Hey PAL, ..." mid-conversation: just the rest)
                    question = question[name.end():].strip()
                present = self.present()
                if present["solo"] != convo["solo"]:
                    convo["solo"] = None       # someone else joined (or left): no one person's notes
                    if convo.get("notes_for") and ctx:
                        # PAL's notes about the person it was alone with are
                        # in this conversation's instructions, and so is what
                        # it said from them. With someone else listening it
                        # starts again without either.
                        present["lobby"], present["screen"] = self.awareness(), self.screen_now()
                        ctx, messages = self.brain.prepare(present, self.greeted_today), []
                        view = describe(present)
                        convo["notes_for"], convo["screen"] = None, present["screen"]
                        self.private = False
                speaker = (self.people.get(present["solo"]).get("name", "Someone")
                           if present["solo"] else "Someone")
                self.screen.say("human", question or "...", 200)
                self.screen.status("processing...")
                said = question or "(said your name, then nothing else)"
                convo["last_heard"] = said
                if FORGET_WORD.search(said) and not DONT_FORGET.search(said):
                    convo["asked_forget"] = True
                now_view = describe(present)
                prefix = ""
                if now_view != view:
                    others = (" Others can hear you now: leave your notes about anyone out."
                              if convo.get("notes_for") and present["solo"] != convo["notes_for"] else "")
                    prefix = f"[{now_view}{others}] "
                view = now_view
                if self.screen_now() != convo.get("screen"):      # (something else is open now)
                    convo["screen"] = self.screen_now()
                    prefix += f"[{convo['screen']}] " if convo["screen"] else ""
                mark = len(messages)
                messages.append({"role": "user", "content": f"{prefix}{speaker} says: {said}"})
                transcript.append(f"{speaker}: {said}")
                if convo.get("note"):
                    messages[-1]["content"] = convo.pop("note") + " " + messages[-1]["content"]
                if ctx:
                    text, _ = self.respond(lambda on_text, on_search, on_tool: self.brain.reply(
                        ctx, messages, lambda tool, args: self.act(tool, args, convo),
                        on_text=on_text, on_search=on_search, on_tool=on_tool))
                else:
                    text = lines.offline()
                    self.speak(text)
                if text is None:
                    # Not meant for PAL (a phone call, people chatting): as if unheard.
                    del messages[mark:]
                    transcript.pop()
                    log("not meant for PAL")
                    break
                if not messages or messages[-1]["role"] != "assistant":
                    # Claude didn't answer (an error, or it declined): what PAL
                    # said instead keeps the conversation in order.
                    messages.append({"role": "assistant", "content": text})
                transcript.append(f"{self.name}: {text}")
                asked = asks(text)
                question = None
        finally:
            self.screen.end()
            self.screen.asked = False
            self.ears.clear()
            self.talking = False
            self.last_talk = time.monotonic()
            log(f"conversation over ({sum(1 for line in transcript if not line.startswith(self.name))} said to PAL)")
        if ctx and messages and messages[-1]["role"] == "assistant":
            with self.lock:
                faces = {t.serial for t in self.tracks if time.monotonic() - t.last < GONE_SECONDS}
            self.last_convo = {"ctx": ctx, "messages": messages, "convo": convo, "view": view,
                               "ended": time.monotonic(), "faces": faces}
        if self.voice.language != "en":
            self.english_at = time.monotonic() + FOLLOW_UP_SECONDS   # (in case they carry on)
        if self.voice.style != self.usual_voice():
            self.usual_voice_at = time.monotonic() + FOLLOW_UP_SECONDS
        if len(transcript) > 1 and self.brain.ready():
            threading.Thread(target=self.remember, args=(transcript, convo), daemon=True).start()

    def remember(self, transcript, convo):
        # Notes about someone only if they were the one face in view the
        # whole time (not someone else's words in their file).
        if convo.get("forgot"):      # they asked to be forgotten: nothing from this chat is kept
            return
        pid = convo.get("solo")
        with self.memory:            # (a second chat's notes build on the first's, not over them)
            person = dict(self.people.get(pid), pid=pid) if pid and self.people.get(pid) else None
            try:
                notes = self.brain.remember(person, "\n".join(transcript))
            except Exception as e:
                log("memory:", repr(e))
                return
            if person and notes and self.people.get(person["pid"]):
                self.people.update(person["pid"], notes=notes)

    # ---------------------------------------------------------- FixBot mode

    def fixbot_conversation(self, first):
        """ "Hey FixBot": FixBot's conversation, in PAL's place."""
        asked = time.monotonic()
        with self.turn:
            if time.monotonic() - asked > 8:     # (as with "Hey PAL": not one from minutes ago)
                return
            self.talk("fixbot", first)

    def fixbot_talk(self, first):
        """FixBot's side, until they go quiet or say they're done. What they
        say goes to FixBot word for word, and PAL reads out and shows what
        it answers; next, back, step 12 and photo move through that answer
        and the guide FixBot recommends (fixbot_mode). Nothing about the
        repair comes from Claude. The repair is kept for the next "Hey
        FixBot" (fixbot_mode.IDLE_SECONDS)."""
        if fixbot_page.login():               # (FixBot's own page, logged in: the real thing)
            return self.fixbot_page_talk(first)
        self.talking = True
        if first is None:
            self.ears.clear()
        if self.fixbot_repair is None or self.fixbot_repair.stale(time.monotonic()):
            self.fixbot_repair = fixbot_mode.Session()
        s = self.fixbot_repair
        log("fixbot: " + ("carrying on" if s.chatid or s.guide else "a new repair"))
        turns = 0
        try:
            self.screen.begin(canvas=True, requested=True)
            self.fixbot_draw(s)
            key = brain_module.key_from_file(brain_module.FIXBOT_ENV, "FIXBOT_API_KEY")
            if not key:
                self.fixbot_say("FixBot isn't switched on here yet: it still needs its key.")
                return
            question = first
            if question == "":
                question = self.listen(2.5) or ""     # (the rest often follows after a breath)
            if question == "":
                self.fixbot_say("Go ahead." if s.chatid or s.guide else
                                "FixBot here. What are you fixing, and what's going on with it?")
                question = None
            while not self.wrap_up.is_set():
                if question is None:
                    self.fixbot_draw(s, "listening")
                    question = self.listen(fixbot_mode.LISTEN_SECONDS)
                    if question is None:
                        break
                pal = WAKE.match(question) or NAME_ONLY.match(question)
                if pal:                         # "Hey PAL, ...": PAL's turn (the repair waits)
                    self.passing = ("pal", question[pal.end():].strip())
                    break
                again = fixbot_mode.WAKE.match(question)
                if again or fixbot_mode.just_the_name(question):
                    question = question[again.end():].strip() if again else ""
                    if not question:            # (just the name again)
                        self.fixbot_say("Go ahead.")
                        question = None
                        continue
                s.used = time.monotonic()
                turns += 1
                if not self.fixbot_turn(s, key, question):
                    break
                question = None
        finally:
            self.fixbot_unpicture()
            self.screen.end()
            self.ears.clear()
            self.talking = False
            self.last_talk = time.monotonic()
            log(f"fixbot: conversation over ({turns} said)")

    def fixbot_turn(self, s, key, heard):
        """One thing said to FixBot. False: they're done."""
        name, number = fixbot_mode.command(heard)
        self.screen.say("human", heard or "...", 200)
        more = s.answer is not None and s.view == "chat" and s.shown + 1 < len(s.answer.chunks)
        if name == "ack":
            pass
        elif name == "end":
            self.fixbot_repair = None
            self.fixbot_say("Good luck with the repair.")
            return False
        elif name == "new":
            s.__init__()
            self.fixbot_draw(s)
            self.fixbot_say("Starting over. What are you fixing, and what's going on with it?")
        elif name == "next" and more:
            self.fixbot_read(s, s.shown + 1)
        elif name == "next" and s.guide:
            self.fixbot_step(s, s.step + 1)
        elif name == "next" and s.recommended:
            self.fixbot_open_guide(s)
        elif name == "next" and not re.match(r"\W*(?:yes|yeah|yep|sure)\b", heard, re.I):
            self.fixbot_say("That's all of FixBot's answer. Ask it anything else, or say we're done.")
        elif name == "back" and s.view == "chat" and s.answer and s.shown > 0:
            self.fixbot_read(s, s.shown - 1)
        elif name == "back" and s.guide:
            self.fixbot_step(s, s.step - 1)
        elif name == "repeat" and s.view == "guide" and s.guide:
            self.fixbot_step(s, s.step)
        elif name == "repeat" and s.answer:
            self.fixbot_read(s, s.shown)
        elif name == "step" and s.guide:
            self.fixbot_step(s, number)
        elif name == "photo" and s.guide:
            self.fixbot_photo(s)
        elif name == "camera":
            self.fixbot_say("FixBot can't see through the camera yet. Tell it what you see, "
                            "and it'll take it from there.")
        elif name == "guide" and s.guide:
            self.fixbot_step(s, s.step)
        elif name == "guide" and s.recommended:
            self.fixbot_open_guide(s)
        elif name in ("back", "repeat", "step", "photo") and not s.answer and not s.guide:
            self.fixbot_say("Nothing to go back to yet. What are you fixing, and what's going on with it?")
        else:
            self.fixbot_ask(s, key, heard)    # a question (or a yes, or a guide FixBot hasn't named yet)
        return True

    def fixbot_say(self, text):
        """PAL's voice, a sentence at a time (typed under the page as it goes)."""
        for sentence in re.split(r"(?<=[.!?:])\s+", (text or "").strip()):
            if sentence:
                self.mouth.say(sentence)
        self.mouth.wait()

    def fixbot_draw(self, s, status=""):
        """The page: the conversation, or the guide step."""
        if self.fixbot_shot:
            return                           # (a guide photo is up: the page comes back after it)
        if not self.screen.shown:
            self.screen.begin(canvas=True, requested=True)
        body = s.guide_text()[0] if s.view == "guide" and s.guide else s.chat_lines()
        self.screen.frame(s.page(status, body))

    def fixbot_ask(self, s, key, words, retried=False):
        """Their words to FixBot, in this repair's conversation, and its
        answer read out. (Where they are in the guide goes with them.)"""
        s.asked, s.view, s.answer, s.shown = words, "chat", None, 0
        self.fixbot_unpicture()
        self.fixbot_draw(s, "thinking")
        self.mouth.say("Asking FixBot.")
        # The first time, what they said is the device too: FixBot finds it
        # there, and says which it matched.
        device = s.device or words
        box = {}

        def call():
            try:
                box["result"] = ifixit.plan(key, device[:200], (words + s.where())[:2000], s.chatid)
            except Exception as e:  # (an answer FixBot couldn't give mustn't take PAL down)
                box["error"] = e
        asking = threading.Thread(target=call, daemon=True)
        asking.start()
        started, nudged = time.monotonic(), 0
        while asking.is_alive():
            asking.join(1.0)
            waited = time.monotonic() - started
            self.fixbot_draw(s, f"thinking {waited:.0f}s")
            if nudged == 0 and waited > 25:
                self.mouth.say("FixBot's still working on it.")
                nudged = 1
            elif nudged == 1 and waited > 80:
                self.mouth.say("Its answers can take a minute or two.")
                nudged = 2
            if self.wrap_up.is_set():
                log("fixbot: stopped waiting (the menu needs PAL)")
                return
        self.mouth.wait()
        waited = time.monotonic() - started
        error = box.get("error")
        if error is not None:
            code = getattr(error.__cause__, "code", None)
            log(f"fixbot: no answer after {waited:.0f} s ({code or type(error).__name__})")
            if code == 404 and s.chatid and not retried:    # (FixBot no longer has the conversation)
                s.chatid = None
                return self.fixbot_ask(s, key, words, retried=True)
            if code in (400, 422):
                self.fixbot_say("FixBot needs to know which device it is and what's wrong with it. "
                                "What are you fixing?")
            elif isinstance(error, ifixit.FixBotError):
                self.fixbot_say(str(error))
            else:
                self.fixbot_say("FixBot sent something unexpected. Try asking again.")
            self.fixbot_draw(s)
            return
        result = box["result"] if isinstance(box.get("result"), dict) else {}
        plan = str(result.get("plan") or "")
        log(f"fixbot: answered in {waited:.0f} s ({len(plan)} characters)")
        s.chatid = str(result.get("chatid") or result.get("chatId") or "") or s.chatid
        s.device = str(result.get("matchedDevice") or "") or s.device or words[:100]
        guide = result.get("primaryGuide")
        guide = guide if isinstance(guide, dict) and str(guide.get("guideid", "")).isdecimal() else None
        extra = []
        parts = [p for p in result.get("partsEstimate") or [] if isinstance(p, dict) and p.get("name")]
        if parts:
            def priced(p):
                cost, currency = p.get("cost"), str(p.get("currency") or "")
                return str(p["name"]) + (f" ({cost:.2f} {currency})".replace(" )", ")")
                                         if isinstance(cost, (int, float)) else "")
            extra.append(("Parts: " + "; ".join(priced(p) for p in parts[:6]),
                          "Parts: " + "; ".join(str(p["name"]) for p in parts[:6]) + "."))
        wants_guide = bool(fixbot_mode.WANTS_GUIDE.search(words))
        if guide:
            s.recommended = guide
            if not wants_guide and str(guide["guideid"]) != str(s.offered):
                s.offered = guide["guideid"]
                extra.append(f"FixBot's guide for this: {guide.get('title', 'its guide')}. "
                             f"Say \"open the guide\" to go through it step by step.")
        s.answer = fixbot_mode.Answer(plan or "FixBot didn't say anything back. Try asking another way.",
                                      extra)
        self.fixbot_read(s, 0)
        if guide and wants_guide:
            self.fixbot_open_guide(s)
        elif len(s.answer.chunks) > 1:
            self.fixbot_say("Say next for more.")

    def fixbot_read(self, s, chunk):
        """Part of FixBot's answer, shown and read out."""
        s.view, s.shown = "chat", chunk
        self.fixbot_unpicture()
        self.fixbot_draw(s)
        self.fixbot_say(s.answer.words(chunk))

    def fixbot_open_guide(self, s):
        """The guide FixBot recommended, from FixBot, at its overview."""
        try:
            guide = ifixit.guide(s.recommended["guideid"])
        except ifixit.FixBotError as e:
            self.fixbot_say(str(e))
            return
        if not isinstance(guide, dict) or not guide.get("title"):
            self.fixbot_say("FixBot's guide didn't come through. Try again in a moment.")
            return
        log(f"fixbot: guide {s.recommended['guideid']}, {len(guide.get('steps') or [])} steps")
        s.guide, s.offered = guide, s.recommended["guideid"]
        self.fixbot_step(s, 0)

    def fixbot_step(self, s, number):
        """A page of the guide: its overview (0), a step, or its end."""
        s.step, s.view, s.photo = max(0, min(number, len(s.steps()) + 1)), "guide", 0
        self.fixbot_unpicture()
        self.fixbot_draw(s)
        self.fixbot_say(s.guide_text()[1])

    def fixbot_photo(self, s):
        """This step's photos on the Compaq's screen, one each time they ask."""
        urls = s.photos() if s.view == "guide" else []
        if not urls:
            self.fixbot_say("There's no photo on this page." if s.view == "guide" else
                            "Say \"guide\" first, then \"photo\".")
            return
        url, number = urls[s.photo % len(urls)], s.photo % len(urls) + 1
        s.photo += 1
        self.fixbot_unpicture()
        steps = s.steps()
        caption = (f"Step {s.step}: " + str(steps[s.step - 1].get("title") or "") if 1 <= s.step <= len(steps)
                   else str(s.guide.get("title", "")))
        caption = fixbot_mode.to_ascii(caption)[:60] + (f" ({number} of {len(urls)})" if len(urls) > 1 else "")
        try:
            conn, _ = pictures.put_up(pictures.fetch(url), caption, lobby_only=True)
        except pictures.NotShown as e:
            self.fixbot_say(str(e))
            return
        self.screen.shown = self.screen.canvas = False      # (the photo took the page's place)
        self.fixbot_shot = conn
        self.fixbot_say(f"Photo {number} of {len(urls)}. Say photo again for the next one."
                        if len(urls) > 1 else "Here's the photo.")

    def fixbot_unpicture(self):
        """Takes a guide photo down, so the page can come back."""
        conn, self.fixbot_shot = self.fixbot_shot, None
        if conn:
            try:
                conn.close()
            except OSError:
                pass
            time.sleep(0.5)                  # (the bridge puts the text back first)

    # ---------------------------------------------------------- FixBot's own page

    def fixbot_page_talk(self, first):
        """FixBot through its own web page (lib/fixbot_page.py), logged in:
        what they say is typed into its message box, its answers are read
        out in PAL's voice, and the page itself is on the Compaq's screen
        when it can show it. A few words press the page's buttons (open the
        guide, take a picture, start over); everything else is FixBot's."""
        self.talking = True
        if first is None:
            self.ears.clear()
        turns, claim = 0, None
        handed, self.fixbot_handed = self.fixbot_handed, False   # (PAL has just said it's opening)
        self.fixbot_left.clear()
        try:
            if self.fixbot_web is None and not handed:
                self.mouth.say("Opening FixBot.")
            claim = object()                     # (this conversation keeps the page on the screen)
            web = self.fixbot_page_open(claim)
            if web is None:
                self.fixbot_say("FixBot's page didn't open. Its iFixit login may have ended.")
                return
            page = web["page"]
            question = first
            if question == "":
                question = self.listen(2.5, until=self.fixbot_left) or ""   # (the rest often follows after a breath)
            if question == "" and not self.fixbot_left.is_set():
                self.fixbot_say("FixBot here. What are you fixing?")
                question = None
            while not self.wrap_up.is_set():
                if question is None:
                    self.screen.beep(YOUR_TURN)
                    question = self.listen(fixbot_mode.LISTEN_SECONDS, until=self.fixbot_left)
                if self.fixbot_left.is_set():   # F10 at the keyboard: FixBot's gone, and so is its turn
                    log("fixbot page: left with F10")
                    break
                if question is None:
                    break
                pal = WAKE.match(question) or NAME_ONLY.match(question)
                if pal:                         # "Hey PAL, ...": PAL's turn (FixBot's page stays open)
                    self.passing = ("pal", question[pal.end():].strip())
                    break
                if fixbot_mode.page_command(question) == "menu":   # "...take me to the main menu"
                    self.fixbot_say("Here's the main menu.")
                    subprocess.run(["sudo", "-n", "-u", "desk", VOICE_OPEN, "main-menu"],
                                   capture_output=True, timeout=20)
                    break
                if NAMED.search(question):      # "no PAL, I'm good": all of it is for PAL, not FixBot
                    self.passing = ("pal", question)
                    break
                again = fixbot_mode.WAKE.match(question)
                if again or fixbot_mode.just_the_name(question):
                    question = question[again.end():].strip() if again else ""
                    if not question:
                        self.fixbot_say("Go ahead.")
                        question = None
                        continue
                web["used"] = time.monotonic()
                turns += 1
                name = fixbot_mode.page_command(question)
                if os.environ.get("PAL_SIM_LOG_WORDS"):     # (the simulator only: tools/tests/run_sim.sh)
                    log(f"fixbot page: heard {question!r} ({name or 'for FixBot'})")
                if name == "end":
                    page.new_chat()
                    self.fixbot_say("Good luck with the repair.")
                    break
                if name == "new":
                    page.new_chat()
                    self.fixbot_say("Starting over. What are you fixing?")
                elif name == "guide":
                    self.fixbot_say("The guide's on the screen." if page.click("Open guide") else
                                    "There's no guide to open yet. Ask FixBot for one.")
                elif name == "close":
                    page.click("Close")         # (F2 at the keyboard does both)
                elif name == "camera":
                    self.fixbot_page_photo(page)
                elif name != "ack":
                    self.fixbot_page_ask(page, question)
                question = None
        except fixbot_page.PageError as e:
            log(f"fixbot page: {e}")
            self.fixbot_say("FixBot's page stopped working. Try again in a moment.")
            self.fixbot_page_close()
        finally:
            if self.fixbot_web:
                self.fixbot_web["holders"].discard(claim)
            self.fixbot_page_hide()
            self.ears.clear()
            self.talking = False
            self.last_talk = time.monotonic()
            log(f"fixbot page: conversation over ({turns} said)")

    def fixbot_page_ask(self, page, question):
        """Their words into FixBot's message box, and its answer read out."""
        started = time.monotonic()
        before = page.send(question)
        self.mouth.say("Asking FixBot.")
        nudged = []

        def waiting(seconds):
            if self.fixbot_left.is_set():
                raise Left()
            if seconds > 25 and not nudged:
                nudged.append(True)
                self.mouth.say("FixBot's still thinking.")
        try:
            said = page.answer(before, waiting=waiting)
        except Left:
            self.mouth.hush()
            return
        log(f"fixbot page: answered in {time.monotonic() - started:.0f} s ({len(said)} characters)")
        if not said:
            self.fixbot_say("FixBot didn't answer. Try asking again.")
            return
        # Read out with the page following along: the answer's start at the
        # top of the conversation, then on down as PAL gets through it.
        self.mouth.wait()
        page.follow(0)
        sentences = [x for x in re.split(r"(?<=[.!?:])\s+", said.strip()) if x]
        for sentence in sentences:
            self.mouth.say(sentence)
        while True:
            with self.mouth.done:
                left = self.mouth.pending
            if left <= 0:
                break
            if self.fixbot_left.is_set():
                self.mouth.hush()
                break
            page.follow((len(sentences) - left) / len(sentences))
            time.sleep(0.7)
        self.mouth.wait()

    def fixbot_page_photo(self, page):
        """A photo from the webcam into FixBot's own photo button, only when
        they ask: it goes to FixBot with whatever they say next."""
        if not self.eyes.status.startswith(("ok", "test")):
            self.fixbot_say(f"The camera isn't working ({self.eyes.status}).")
            return
        self.fixbot_say("Hold it up to the camera. Three, two, one.")
        with self.lock:
            image = self.latest[0]
        if image is None:
            self.fixbot_say("The camera didn't catch that. Try again.")
            return
        path = os.path.join(page.home, f"photo-{int(time.time())}.jpg")
        with open(path, "wb") as f:
            f.write(base64.b64decode(vision.jpeg_base64(image, longest=1280)))
        page.attach(path)
        log("fixbot page: a photo for FixBot")
        self.fixbot_say("Got it. Now ask FixBot about it.")

    def fixbot_page_open(self, claim):
        """FixBot's page in the Pi's browser (opened the first time and kept
        between conversations; fresh after fixbot_mode.IDLE_SECONDS), and on
        the Compaq's screen when it can show 640x400 dots, held there for
        claim until it's let go (fixbot_page_hide). None if the page didn't
        open."""
        web = self.fixbot_web
        if web and (web["page"].chrome.process.poll() is not None
                    or time.monotonic() - web["used"] > fixbot_mode.IDLE_SECONDS):
            self.fixbot_page_close()
            web = None
        if web is None:
            try:
                page = fixbot_page.Page()
            except fixbot_page.PageError as e:
                log(f"fixbot page: {e} ({e.detail})")
                return None
            if not page.ready():
                page.close()
                log("fixbot page: no message box (has the login ended?)")
                return None
            web = self.fixbot_web = {"page": page, "stop": None, "thread": None, "holders": set(),
                                     "used": time.monotonic()}
            log("fixbot page: open" + (" (logged in)" if page.logged_in else " (as a guest)"))
        with self.fixbot_screen:                 # (the claim is taken in the same breath as the screen)
            web["holders"].add(claim)
            self.fixbot_page_screen(web)
        return web

    def fixbot_page_screen(self, web):
        """The page onto the Compaq's screen, unless it's already there (with
        self.fixbot_screen held)."""
        if web["thread"] is not None and (web["stop"] is None or web["stop"].is_set()):
            web["thread"].join(3)                # (the last screen still coming down: one at a time)
        if web["thread"] is not None and not web["thread"].is_alive():
            web["stop"] = web["thread"] = None   # (that screen went: F10, or the Compaq unplugged)
        if web["stop"] is None:
            try:
                canvas = pictures.Canvas("640x400", lobby_only=True)
            except pictures.NotShown as e:
                log(f"fixbot page: voice only ({e})")
                return
            if (canvas.width, canvas.height) != (fixbot_page.WIDTH, fixbot_page.HEIGHT):
                canvas.close()
                log("fixbot page: voice only (the screen can't show 640x400 dots)")
                return
            web["stop"] = threading.Event()
            web["thread"] = threading.Thread(target=self.fixbot_page_show, args=(web["page"], canvas, web["stop"]),
                                             daemon=True)
            web["thread"].start()

    def fixbot_page_menu(self, conn, send):
        """The menu's FixBot: FixBot's own page on the Compaq's screen, with
        what's typed at the shared session (the TV's keyboard, or a browser)
        coming over this connection as keys; until they leave (F10 closes
        the menu program, and the connection) or the screen is taken away.
        Keys at the Compaq itself reach the page through the screen."""
        if not fixbot_page.login():
            send({"ok": False, "message": "FixBot's page needs its iFixit login (set-ifixit-login.sh)."})
            return
        claim = object()                         # (this menu visit keeps the page on the screen)
        web = self.fixbot_page_open(claim)
        if web is None:
            send({"ok": False, "message": "FixBot's page didn't open. Its iFixit login may have ended."})
            return
        stop, thread = web["stop"], web["thread"]
        if not stop:
            web["holders"].discard(claim)
            send({"ok": False, "message": "This screen can't show FixBot's page: it needs PILINK (the TV, or "
                                          "the Compaq running PI)."})
            return
        log("fixbot page: on the screen from the menu")
        send({"ok": True})
        pending, why = b"", "the screen went"
        try:
            while not stop.is_set() and thread.is_alive():
                ready, _, _ = select.select([conn], [], [], 0.3)
                if ready:
                    data = conn.recv(512)
                    if not data:
                        why = "left"
                        break                    # (the menu program ended: F10)
                    web["used"] = time.monotonic()
                    keys, pending = fixbot_page.split_keys(pending + data)
                elif pending:                    # (a lone Esc, not the start of a sequence after all)
                    keys, pending = [pending], b""
                else:
                    continue
                for key in keys:
                    web["page"].key(key)
        finally:
            if why != "left" and stop.is_set():
                why = "put away"
            web["holders"].discard(claim)
            self.fixbot_page_hide()
            log(f"fixbot page: off the screen (menu: {why})")
            try:
                send({"done": True})
            except OSError:
                pass

    def fixbot_page_show(self, page, canvas, stop):
        """The page on the Compaq's screen until stop (or the screen is taken
        away); keys at the Compaq type into it."""
        try:
            fixbot_page.show(page, canvas, stop=stop)
            if canvas.closed and canvas.why == "menu":
                self.fixbot_left.set()          # (F10: the conversation with FixBot is over too)
            log("fixbot page: screen " + ("put away" if stop.is_set() else
                                          f"taken back by the bridge ({canvas.why or 'no reason'})"
                                          if canvas.closed else "ended"))
        except fixbot_page.PageError as e:
            log(f"fixbot page: {e}")
        except Exception as e:  # (whatever goes wrong on the screen, PAL carries on)
            where = traceback.extract_tb(e.__traceback__)[-1]
            log(f"fixbot page: the screen stopped: {e!r} ({os.path.basename(where.filename)}:{where.lineno})")
        finally:
            canvas.close()

    def fixbot_page_hide(self):
        """The page off the screen (the browser stays, for the next turn),
        unless someone still has it up (the menu, or a conversation)."""
        with self.fixbot_screen:
            web = self.fixbot_web
            if web and web["stop"] and not web["holders"]:
                web["stop"].set()
                web["stop"] = None

    def fixbot_page_close(self):
        web, self.fixbot_web = self.fixbot_web, None
        if web:
            if web["stop"]:
                web["stop"].set()
            web["page"].close()

    # ---------------------------------------------------------- tips for the stuck

    def watch_screen(self):
        """Offers a spoken tip when someone at the lobby keyboard seems
        stuck: the program they're using has said it didn't understand them
        TIP_AFTER times in a few minutes. screen-watch (run as the shared
        session's account) shows PAL the screen only while the lobby
        keyboard is in use and a program is open. (It also tells PAL when
        someone is playing a text adventure, for talking to the game.)"""
        while True:
            try:
                watcher = subprocess.Popen(["sudo", "-n", "-u", "desk", SCREEN_WATCH],
                                           stdout=subprocess.PIPE, stderr=subprocess.DEVNULL, text=True)
                previous, program, misses = None, None, collections.deque()
                events = {}
                for line in watcher.stdout:
                    state = json.loads(line)
                    now = time.monotonic()
                    # (the shared session can set the title to anything: only
                    # plain words reach PAL's instructions)
                    self.showing = (re.sub(r"[^A-Za-z0-9 ,.'&:()/+-]", " ", str(state.get("showing", "")))[:60],
                                    str(state.get("app", ""))[:60])
                    if state.get("active"):
                        self.keyboard_seen = now
                    else:
                        previous, program = None, None
                        misses.clear()
                        events = {}
                        continue
                    if state.get("program") in TEXT_ADVENTURES:
                        self.game_seen, self.game_text = now, state["text"]
                        if now - self.voice_hinted > 1800 and self.anyone_here():
                            self.voice_hinted = now   # (so nobody is surprised it listens)
                            threading.Thread(target=self.hint_voice, daemon=True).start()
                    self.heckle(state, events, now)
                    count = len(TROUBLE.findall(state["text"])) if state.get("program") in TIP_PROGRAMS else 0
                    if state.get("program") != program:
                        program, previous = state.get("program"), None
                        misses.clear()
                    if previous is not None and count > previous:
                        misses.extend([now] * (count - previous))
                    previous = count
                    while misses and now - misses[0] > TIP_WINDOW:
                        misses.popleft()
                    if self.tips and len(misses) >= TIP_AFTER and self.can_tip(now):
                        misses.clear()
                        self.tip(program, state["text"])
                watcher.wait()
            except Exception as e:  # keep watching whatever goes wrong
                log("tips:", repr(e))
            time.sleep(10)

    def game_mode(self):
        """Someone at the lobby keyboard is playing a text adventure: what
        they say (without "Hey PAL") is typed into the game."""
        return time.monotonic() - self.game_seen < 6

    def play_move(self, heard):
        """Types what the player said into the game. Short commands go in
        as said ("go north"); anything chattier ("I want to get the paper
        out of the mailbox") Claude turns into what the game understands
        ("take leaflet"), using the screen for "it" and names."""
        command = clean_command(heard)
        if not command:
            return
        if self.brain.ready() and (len(command.split()) > 3 or re.search(r"\b(it|that|this|them|thing)\b", command)):
            try:
                # (nothing back means it wasn't a move: people talking to each
                # other near a game aren't typed into it)
                command = clean_command(self.brain.game_command(heard, self.game_text))
            except brain_module.BrainError as e:
                log("brain:", e)
        command = command.lstrip("-,.!? ")
        if not command:
            return
        result = subprocess.run(["sudo", "-n", "-u", "desk", VOICE_TYPE, command],
                                capture_output=True, text=True, timeout=10)
        log("game: typed a spoken command" if result.returncode == 0
            else f"game: didn't type it ({result.stdout.strip()})")

    def heckle(self, state, counts, now):
        """A quick remark when something happens in a game (the player
        died, won, or scored), like a friend watching over their shoulder."""
        text, program = state["text"], state.get("program")
        kind = "adventure" if program in TEXT_ADVENTURES else "nethack" if program in ("nethack", "hack") \
            else program
        for event, (pattern, what) in GAME_EVENTS.get(kind, {}).items():
            count = len(pattern.findall(text))
            before = counts.get(event)
            counts[event] = count
            if before is None or count <= before:
                continue
            # A friend over the shoulder, not a sportscaster: scores rarely,
            # and at most a few remarks a game.
            gap = 180 if event == "scored" else 30
            if now - self.last_quip < gap or not self.can_tip(now, gap=0) or \
                    counts.get("remarks", 0) >= 4 or (event == "scored" and random.random() < 0.75):
                continue
            counts["remarks"] = counts.get("remarks", 0) + 1
            self.last_quip = now
            tail = "\n".join(text.rstrip().splitlines()[-12:])
            threading.Thread(target=self.quip, args=(event, what, tail), daemon=True).start()
            break

    def quip(self, event, what, screen):
        with self.turn:
            self.talking = True
            try:
                log(f"game: a remark ({event})")
                if self.brain.ready():
                    self.respond(lambda on_text, *_: (self.brain.quip(what, screen, self.present(),
                                                                       self.greeted_today, on_text), []))
                else:
                    self.speak(lines.quip(event))
            finally:
                self.talking = False

    def shout_out(self):
        """A quick line for someone walking past the lobby."""
        with self.turn:
            if self.anyone_here() or self.asleep() or self.enrolling:
                return                   # they stopped: a proper greeting is coming
            self.talking = True
            try:
                self.last_shout = time.monotonic()
                self.shouts.append(self.last_shout)
                self.shouts_today += 1
                self.shout_misses += 1        # (back to 0 if someone stops)
                log("passer-by: a shout-out")
                line = (self.brain.shout_out(self.awareness(), self.greeted_today)
                        if self.brain.ready() else None)
                self.screen.begin()
                self.speak(line or lines.passerby())
            finally:
                self.screen.end()
                self.talking = False

    def hint_voice(self):
        """Tells the player they can say their moves out loud."""
        time.sleep(4)                        # (let them read the game's opening first)
        with self.turn:
            if self.asleep() or not self.game_mode():
                return
            self.talking = True
            try:
                log("game: told the player they can speak their moves")
                self.speak(lines.voice_hint())
            finally:
                self.talking = False

    def can_tip(self, now, gap=None):
        return (now - self.last_tip > (TIP_GAP if gap is None else gap) and not self.talking
                and not self.enrolling and not self.asleep() and self.mouth.pending == 0)

    def tip(self, program, screen):
        with self.turn:
            self.talking = True
            try:
                self.last_tip = time.monotonic()
                log(f"tip: someone seems stuck in {program}")
                tail = "\n".join(screen.rstrip().splitlines()[-18:])
                if self.brain.ready():
                    self.respond(lambda on_text, *_: (self.brain.tip(program, tail, self.present(),
                                                                     self.greeted_today, on_text), []))
                else:
                    self.speak(lines.tip(program))
            finally:
                self.talking = False
                self.last_talk = time.monotonic()

    # ---------------------------------------------------------- the menu's requests

    def serve(self):
        try:
            os.unlink(SOCKET)
        except FileNotFoundError:
            pass
        server = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
        server.bind(SOCKET)
        os.chmod(SOCKET, 0o660)
        try:
            os.chown(SOCKET, -1, grp.getgrnam("desk").gr_gid)   # the menu runs as desk
        except (KeyError, PermissionError):
            pass
        server.listen(4)
        while True:
            conn, _ = server.accept()
            if not self.requests.acquire(blocking=False):
                conn.close()                 # too many at once
                continue
            threading.Thread(target=self.handle, args=(conn,), daemon=True).start()

    def handle(self, conn):
        def send(message):
            conn.sendall((json.dumps(message) + "\n").encode())

        with conn:
            try:
                conn.settimeout(10)
                request = json.loads(conn.makefile().readline(65536) or "null")
                conn.settimeout(None)
                if not isinstance(request, dict):
                    return
                op = request.get("op")
                if op == "status":
                    send(self.status())
                elif op == "enroll":
                    self.enroll(send, str(request.get("name", "")), str(request.get("say_as", "")))
                elif op == "forget":
                    self.forget(send)
                elif op == "quiet":
                    try:
                        minutes = min(24 * 60, max(0, int(request.get("minutes", 0))))
                    except (TypeError, ValueError, OverflowError):
                        minutes = 0
                    self.quiet_until = time.time() + minutes * 60 if minutes > 0 else 0
                    send({"ok": True})
                elif op == "chat":
                    send(self.typed_chat(request.get("messages")))
                elif op == "fixbot":
                    send(self.fixbot(request))
                elif op == "fixbot_page":
                    self.fixbot_page_menu(conn, send)
                elif op == "delete_portrait":
                    name = str(request.get("name", ""))
                    if re.fullmatch(r"\d{8}-\d{6}\.txt", name):
                        try:
                            os.remove(os.path.join(vision.PORTRAITS, name))
                        except FileNotFoundError:
                            pass
                    send({"ok": True})
                elif op == "tunes":
                    send({"tunes": [{"id": k, "title": v["title"], "composer": v["composer"],
                                     "year": v["year"]} for k, v in music.TUNES.items()]})
                elif op == "play":
                    send(self.jukebox_play(request, send))
                elif op == "stop":
                    self.voice.stop()
                    send({"ok": True})
                elif op == "play_file":
                    send(self.play_file(request, send))
                elif op == "search":
                    send(self.web_results(request))
                elif op == "voice":
                    send(self.menu_voice(str(request.get("voice", ""))))
                elif op == "say_test":
                    self.speak(f"Hello. {self.name} here. Voice check, one, two. Please do not be alarmed.")
                    send({"ok": True, "speaker": self.voice.status})
            except Exception as e:  # nothing a menu sends can take PAL down
                log("menu request:", repr(e))
            finally:
                self.requests.release()

    def jukebox_play(self, request, send):
        """The menu's jukebox: plays a tune (or sings), telling the menu when
        the sound starts, with its notes, so it can draw them falling."""
        if self.enrolling:           # (it's listening for a spoken yes: nothing else may speak)
            return {"done": True, "ok": False, "message": "PAL is busy with someone's face. Try again in a minute."}
        if not self.turn.acquire(timeout=8):
            return {"done": True, "ok": False, "message": "PAL is busy talking. Try again in a moment."}
        try:
            if self.asleep():
                return {"done": True, "ok": False, "message": "PAL is in quiet mode, so no music."}

            def started(meta, timeline, seconds):
                send({"started": True, "title": meta["title"], "composer": meta.get("composer", ""),
                      "year": meta.get("year", ""), "fact": meta.get("fact", ""),
                      "seconds": round(seconds, 2),
                      "timeline": [[round(a, 3), round(b, 3), m, v] for a, b, m, v in timeline]})

            song = str(request.get("song") or "") or None
            self.talking = True
            result = self.play_music(tune=str(request.get("tune") or ""), song=song,
                                     name=str(request.get("name") or ""), show=False, on_start=started,
                                     longest=None)
            return {"done": True, "ok": result.startswith(("Played", "Stopped")), "message": result}
        finally:
            self.talking = False
            self.turn.release()

    def play_file(self, request, send):
        """PotatoTube's sound, through the lobby speaker: a WAV file from its
        own folder only, never during quiet hours."""
        path = os.path.realpath(str(request.get("path", "")))
        if not (path.startswith(POTATO_SOUND + "/") and path.endswith(".wav")):
            return {"done": True, "ok": False, "message": "not a sound PAL plays"}
        if self.asleep():
            return {"done": True, "ok": False, "message": "PAL's quiet hours: no sound"}
        if self.enrolling:           # (it's listening for a spoken yes: nothing else may speak)
            return {"done": True, "ok": False, "message": "PAL is busy with someone's face"}
        try:
            with brain_module.open_file(path) as f:      # (an ordinary file only: see open_file)
                wav = f.read(60_000_001)
            if len(wav) > 60_000_000:
                return {"done": True, "ok": False, "message": "too long"}
            # How long it plays, from the sound itself, so the microphone
            # stays shut until it's over whatever its rate.
            with wave.open(io.BytesIO(wav)) as w:
                seconds = w.getnframes() / w.getframerate()
        except (OSError, wave.Error, EOFError, ZeroDivisionError):
            return {"done": True, "ok": False, "message": "PAL can't play that sound"}
        if not self.turn.acquire(timeout=8):
            return {"done": True, "ok": False, "message": "PAL is busy talking"}
        try:
            if self.enrolling:
                return {"done": True, "ok": False, "message": "PAL is busy with someone's face"}
            self.talking = self.playing = True
            log(f"potatotube: sound ({seconds:.0f} s)")
            send({"started": True})
            self.ears.deaf_until = time.monotonic() + seconds + 3
            self.voice.play(wav)
            return {"done": True, "ok": True}
        finally:
            self.ears.deaf_until = time.monotonic() + 0.8
            self.talking = self.playing = False
            self.turn.release()

    def web_results(self, request):
        """Web search results for the Compaq's search page, when its usual
        source doesn't answer: Claude's web search."""
        query = " ".join(str(request.get("query", "")).split())[:200]
        if not query or not self.brain.ready():
            return {"ok": False, "message": "PAL can't search right now."}
        try:
            return {"ok": True, "results": self.brain.web_results(query)}
        except brain_module.BrainError as e:
            log("brain:", e)
            return {"ok": False, "message": "PAL couldn't reach its search."}

    def fixbot(self, request):
        """A FixBot plan for the menu's "Ask FixBot", made with the key only
        PAL's account can read."""
        key = brain_module.key_from_file(brain_module.FIXBOT_ENV, "FIXBOT_API_KEY")
        if not key:
            return {"ok": False, "message": "FixBot needs a key: run set-fixbot-key.sh on the Mac."}
        try:
            result = ifixit.plan(key, str(request.get("device") or "")[:100],
                                 str(request.get("text") or "")[:2000],
                                 str(request.get("chatid") or "") or None)
            return {"ok": True, "chatid": result.get("chatid") or result.get("chatId"),
                    "text": ifixit.plan_text(result)}
        except ifixit.FixBotError as e:
            return {"ok": False, "message": str(e)}
        except Exception as e:  # a bad answer from FixBot mustn't take PAL down
            return {"ok": False, "message": f"FixBot sent something unexpected ({e})."}

    def usual_voice(self):
        """The voice PAL goes back to: the one picked at the menu, for its
        hour, else pal.conf's."""
        return self.lobby_voice if self.lobby_voice and time.time() < self.lobby_voice_until else self.own_voice

    def menu_voice(self, style):
        """The menu's "Change PAL's voice": that one for an hour (PAL's own
        again: at once), said out loud so whoever picked it hears it."""
        if style not in Voice.STYLES:
            return {"ok": False, "message": "PAL doesn't have that voice."}
        if not self.turn.acquire(timeout=8):
            return {"ok": False, "message": "PAL is busy talking. Try again in a moment."}
        try:
            self.lobby_voice = None if style == self.own_voice else style
            self.lobby_voice_until = time.time() + 3600
            self.voice.style = style
            log(f"voice: {style} (the menu)")
            self.speak("Back to my own voice." if style == self.own_voice else
                       f"Voice changed. I'm {Voice.SOUNDS[style]} for the next hour.")
        finally:
            self.turn.release()
        return {"ok": True}

    def status(self):
        return {"camera": self.eyes.status, "microphone": self.ears.status,
                "voice": self.voice.style, "usual_voice": self.usual_voice(),
                "voices": [[k, v] for k, v in Voice.SOUNDS.items() if k in Voice.STYLES],
                "fixbot": brain_module.fixbot_on(),
                "speaker": self.voice.status, "brain": self.brain.status,
                "model": self.brain.model, "people": self.people.count(),
                "quiet_until": self.quiet_until if self.quiet_until > time.time() else 0,
                "asleep": self.asleep(), "greeted_today": self.greeted_today,
                "talking": self.talking}

    def faces_now(self, seconds):
        """Waits up to seconds for a fresh frame with exactly one face in it;
        returns (image, face) or (None, reason)."""
        deadline = time.monotonic() + seconds
        reason = "I can't see anyone. Stand in front of the camera."
        if not self.eyes.status.startswith(("ok", "test")):
            return None, f"The camera isn't working ({self.eyes.status})."
        seen = 0.0
        while time.monotonic() < deadline:
            with self.lock:
                image, faces, when = self.latest
            if when > seen and image is not None:
                seen = when
                if len(faces) == 1:
                    return image, faces[0]
                if len(faces) > 1:
                    reason = "I see more than one face. One at a time, please."
            time.sleep(0.2)
        return None, reason

    def confirm(self, prompt, answer, send, cue):
        """Asks out loud, and waits for the one person in view to say it.
        So nobody can teach PAL, or make it forget, a face from a browser:
        the person at the camera has to agree. The menu says when PAL is
        listening (it can't hear while it talks), and what it heard if that
        wasn't the answer."""
        self.ears.clear()
        self.speak(prompt)
        self.ears.clear()
        self.ears.listening = True
        send({"say": cue})
        try:
            deadline = time.monotonic() + 12
            while time.monotonic() < deadline:
                try:
                    heard = self.ears.utterances.get(timeout=0.3)
                except queue.Empty:
                    continue
                now = time.monotonic()
                with self.lock:
                    # Faces seen in the last moment (ignores tracking
                    # flickers), or if none, in the last few seconds: while
                    # Whisper works the camera can fall a little behind.
                    recent = [t for t in self.tracks if now - t.last < GONE_SECONDS]
                    faces = sum(1 for t in recent if now - t.last < 1.5) or len(recent)
                yes = agreed(heard, answer) and faces == 1
                with self.lock:
                    ages = sorted(round(now - t.last, 1) for t in self.tracks)
                log(f"consent: heard {len(heard.split())} words, " + ("agreed" if yes else "not agreed")
                    + ("" if faces == 1 else f" ({faces} faces in view; tracks last seen {ages} s ago)"))
                if yes:
                    return True
                if faces > 1:
                    send({"say": "PAL sees more than one face. It needs you on your own."})
                elif faces == 0:
                    send({"say": "PAL can't see you. Stand in front of the camera."})
                else:
                    send({"say": f'PAL heard "{heard[:60]}". Try again, clearly.'})
            return False
        finally:
            self.ears.listening = False

    def free_for_menu(self, send):
        """Gets PAL ready for enroll/forget: one at a time, and any
        conversation (the hello it just gave the person at the camera, say)
        politely ended first. On success the caller must release self.busy
        and clear self.enrolling."""
        if not self.busy.acquire(blocking=False):
            send({"done": True, "ok": False, "message": "PAL is busy with someone else's face. "
                                                         "Try again in a minute."})
            return False
        self.enrolling = True            # no new conversations meanwhile
        try:
            if self.talking:
                send({"say": "PAL is finishing what it was saying..."})
                self.wrap_up.set()
                deadline = time.monotonic() + 30
                while self.talking and time.monotonic() < deadline:
                    time.sleep(0.2)
                self.wrap_up.clear()
                if self.talking:
                    self.enrolling = False
                    self.busy.release()
                    send({"done": True, "ok": False, "message": "PAL is busy talking. Try again in a minute."})
                    return False
        except BaseException:            # (whoever asked hung up: PAL isn't left waiting for them)
            self.wrap_up.clear()
            if self.enrolling:
                self.enrolling = False
                self.busy.release()
            raise
        return True

    def enroll(self, send, name, say_as):
        name = " ".join("".join(c for c in name if c.isalnum() or c in " -'.").split())[:24]
        say_as = " ".join("".join(c for c in say_as if c.isalnum() or c in " -'").split())[:40]
        if not name:
            send({"done": True, "ok": False, "message": "A name is needed."})
            return
        if not self.free_for_menu(send):
            return
        try:
            image, face = self.faces_now(8)
            if image is None:
                send({"done": True, "ok": False, "message": face})
                return
            send({"say": "PAL is asking you something out loud. Listen..."})
            if not self.confirm(f"{say_as or name}, if you want me to remember your face, say yes.", YES,
                                send, "PAL is listening now: say yes."):
                send({"done": True, "ok": False, "message": "PAL didn't hear a yes, so it kept nothing."})
                return
            send({"say": "Look at the camera and hold still."})
            self.speak(random.choice(["Hold still, I'm scanning that face.",
                                      "Hold still. Memorizing your face. This is my favorite part.",
                                      "Freeze. Saving your face to memory. No sudden moves."]))
            signatures, failures = [], 0
            while len(signatures) < 5 and failures < 8:
                image, face = self.faces_now(6)
                if image is None:
                    failures += 1
                    send({"say": face})
                    continue
                with self.vision:
                    signatures.append(normalise(self.eyes.signature(image, face)))
                send({"say": f"Got {len(signatures)} of 5."})
                time.sleep(0.4)
            if len(signatures) < 5:
                send({"done": True, "ok": False,
                      "message": "I couldn't get a good look. Try again in better light."})
                return
            stack = np.stack(signatures)
            similarity = stack @ stack.T
            if float(similarity[np.triu_indices(5, 1)].mean()) < 0.5:
                send({"done": True, "ok": False,
                      "message": "Those didn't look like one person. Hold still and try again."})
                return
            mean = normalise(stack.mean(axis=0))
            pid, score = self.people.match(mean)
            known = self.people.get(pid) if pid else None
            if known and (score < 0.6 or known["name"].lower() != name.lower()):
                # A lookalike, or someone else's name: never merge two people.
                self.speak("Hold up. You look familiar. Too familiar. Does not compute, so I saved nothing.")
                send({"done": True, "ok": False,
                      "message": "You look a lot like someone PAL already knows, so it saved nothing. "
                                 "If PAL knows you already, use the same name as before."})
                return
            pid = self.people.add(name, say_as, signatures, pid=pid if known else None)
            self.people.update(pid, last_seen=time.time(), last_greeted=time.time(),
                               visits=(known or {}).get("visits", 0) + 1)
            with self.lock:     # they're standing right here: no second hello
                for track in self.tracks:
                    track.signature, track.pid, track.handled = mean, pid, True
                self.arrivals = [t for t in self.arrivals if t not in self.tracks]
            log("taught a face" + (" (refreshed)" if known else ""))
            self.speak(random.choice([
                f"Face saved as numbers, not a photo, {say_as or name}. Say forget me any time.",
                f"Done, {say_as or name}. You're in my memory banks, as numbers, not a picture. "
                "Welcome aboard.",
                f"Got it, {say_as or name}. I'll know you next time. Want me to forget you? Just ask. Radical."]))
            send({"done": True, "ok": True,
                  "message": "Refreshed: PAL knows your face better now." if known
                  else f"Done. PAL will greet you by name, {name}."})
        finally:
            self.enrolling = False
            self.busy.release()

    def forget(self, send):
        """The menu's "Make PAL forget me": whoever is at the camera, if they
        say so out loud."""
        if not self.free_for_menu(send):
            return
        try:
            image, face = self.faces_now(8)
            if image is None:
                send({"done": True, "ok": False, "message": face})
                return
            with self.vision:
                signature = self.eyes.signature(image, face)
            pid, _ = self.people.match(signature)
            if not pid:
                send({"done": True, "ok": True,
                      "message": "PAL doesn't know your face, so there's nothing to forget."})
                return
            person = self.people.get(pid)
            send({"say": "PAL is asking you something out loud. Listen..."})
            if not self.confirm(f"{person.get('say_as') or person['name']}, to make me forget you, "
                                "say forget me.", FORGET, send, "PAL is listening now: say \"forget me\"."):
                send({"done": True, "ok": False,
                      "message": "PAL didn't hear \"forget me\", so nothing changed."})
                return
            self.people.forget(pid)
            with self.lock:
                for t in self.tracks:
                    if t.pid == pid:
                        t.pid = None
            log("forgot someone, at their request")
            self.speak(random.choice(["Done. You're wiped from my memory banks. Who are you again? Hello, stranger.",
                                      "Deleted. I have no idea who you are now. Nice to meet you, stranger."]))
            send({"done": True, "ok": True,
                  "message": f"Forgotten. PAL no longer has {person['name']}'s face or notes."})
        finally:
            self.enrolling = False
            self.busy.release()

    def typed_chat(self, history):
        """A reply for the "Talk to PAL" chat at the Compaq."""
        if not self.brain.ready():
            return {"ok": False, "message": "PAL has no Claude key yet. Run set-claude-key.sh on the Mac."}
        if not isinstance(history, list):
            return {"ok": False, "message": "Bad request."}
        messages = [{"role": m["role"], "content": str(m.get("content", ""))[:2000]}
                    for m in history[-20:] if isinstance(m, dict) and m.get("role") in ("user", "assistant")]
        while messages and messages[0]["role"] != "user":
            messages.pop(0)              # a conversation must start with the person
        if not messages or messages[-1]["role"] != "user":
            return {"ok": False, "message": "Bad request."}
        try:
            ctx = self.brain.prepare({"people": [], "strangers": 0, "solo": None},
                                     self.greeted_today, typed=True)
            text, sources = self.brain.reply(ctx, messages, None)
        except brain_module.BrainError as e:
            log("brain:", e)
            return {"ok": False, "message": "PAL couldn't reach Claude just now. Try again in a minute."}
        text = text or lines.offline()
        if self.speak_typed and not self.asleep():
            threading.Thread(target=self.speak, args=(text,), daemon=True).start()
        if sources:
            text += "\n\nSources: " + ", ".join(sources[:3])
        return {"ok": True, "text": text}

    # ---------------------------------------------------------- the main loop

    def run(self):
        log(f"{self.name} starting. Claude: {self.brain.status}; model {self.brain.model}; "
            f"{self.people.count()} people known.")
        self.ears.start_whisper()
        # The power-on beep: from the Compaq itself when it can.
        threading.Thread(target=lambda: self.screen.beep([[990, 0.22]]) or self.voice.play(sfx.post_beep()),
                         daemon=True).start()
        threads = [threading.Thread(target=job, daemon=True)
                   for job in (self.watch, self.ears.run, self.serve)]
        for thread in threads:
            thread.start()
        threading.Thread(target=self.watch_screen, daemon=True).start()
        while True:
            if not all(t.is_alive() for t in threads):
                log("a part of PAL stopped; restarting")
                sys.exit(1)                  # systemd starts it again
            try:
                self.step()
            except Exception as e:           # keep going whatever goes wrong
                log("main loop:", repr(e))
                self.talking = False
                time.sleep(1)

    def step(self):
        """One turn of the main loop: greet, or hear something."""
        if self.ears.server and self.ears.server.poll() is not None \
                and time.monotonic() - self.whisper_tried > 30:
            self.whisper_tried = time.monotonic()
            log("whisper stopped; restarting it")
            self.ears.start_whisper()
        if self.ears.any_server and self.ears.any_server.poll() is not None:
            log("the other-languages whisper stopped; back to English")
            self.ears.set_language("en")
            self.voice.language = "en"
        if self.enrolling:               # enroll/forget is using the ears
            time.sleep(0.3)
            return
        if self.fixbot_web and not self.talking \
                and time.monotonic() - self.fixbot_web["used"] > fixbot_mode.IDLE_SECONDS:
            log("fixbot page: closed (quiet for a while)")
            self.fixbot_page_close()     # (its browser's memory back; the next visit starts afresh)
        if self.voice.language != "en" and not self.talking and time.monotonic() > self.english_at:
            self.ears.set_language("en")
            self.voice.language = "en"
            log("language: en")
        if self.voice.style != self.usual_voice() and not self.talking and time.monotonic() > self.usual_voice_at:
            self.voice.style = self.usual_voice()        # (an ogre for one chat, or the menu's hour is up)
            log(f"voice: {self.voice.style}")
        # Between conversations, listen only for "Hey PAL" (or, during a
        # text adventure at the lobby keyboard, for moves to type), and
        # only while someone is in front of the camera.
        self.ears.listening = self.anyone_here() and not self.asleep()
        arrivals = self.take_arrivals()
        if arrivals and not self.enrolling and not self.asleep():
            self.shout_due = False
            self.conversation(arrivals=arrivals)
            return
        if self.shout_due:
            self.shout_due = False
            self.shout_out()
            return
        try:
            heard = self.ears.utterances.get(timeout=0.3)
        except queue.Empty:
            return
        if self.enrolling:
            return
        fix = fixbot_mode.WAKE.match(heard)
        if (fix or fixbot_mode.just_the_name(heard)) and not self.asleep():
            log(f"heard {len(heard.split())} words with FixBot's name")
            if self.heard_tick:
                self.tick()
            self.fixbot_conversation(heard[fix.end():].strip() if fix else "")
            return
        woke = WAKE.match(heard) or NAME_ONLY.match(heard)
        if not woke and not fix and self.game_mode() and not self.asleep():
            self.play_move(heard)        # "open the mailbox": into the game
            return
        # Only "Hey PAL" starts PAL talking: people chatting with each other
        # in front of it are none of its business.
        log(f"heard {len(heard.split())} words" + (" with its name" if woke else ""))
        if woke and not self.asleep() and not self.enrolling:
            if self.heard_tick:           # (its name was in it: "got it", while Claude thinks)
                self.tick()
            self.conversation(first=heard[woke.end():].strip())


if __name__ == "__main__":
    os.umask(0o077)     # faces and notes: PAL's eyes only
    try:
        Pal().run()
    except KeyboardInterrupt:
        pass

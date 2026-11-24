#!/usr/bin/env python3
"""FixBot's own web page (fixbot.ifixit.com), the real one, on the Compaq.

The Pi's headless Chromium draws the page at the plasma's 640x400, and it
goes to the Compaq in amber dots whenever it changes, through the
moving-picture channel (pictures.Canvas, which needs PILINK). Keys at the
Compaq type into the page. It is logged in with the iFixit login saved by
set-ifixit-login.sh, which only PAL's account can read, so this runs as PAL.

Chromium is driven over its DevTools pipe (file descriptors 3 and 4), never
a network port, so nothing else on the Pi can reach the logged-in browser.
Its letters are drawn without smoothing (fontconfig), so they survive the
trip to one-bit dots, and its profile is a fresh private folder each time,
removed afterwards.

Try it (as pal): python3 -I fixbot_page.py [seconds]
"""

import base64
import fcntl
import io
import json
import os
import queue
import shutil
import subprocess
import sys
import tempfile
import threading
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pictures  # noqa: E402

URL = "https://fixbot.ifixit.com/"
LOGIN = os.environ.get("IFIXIT_SESSION_FILE", "/etc/compaq/ifixit-session.env")
BROWSER = "chromium-headless-shell"
WIDTH, HEIGHT = 640, 400
CUT = 200            # greys darker than this are lit dots (a light page: its text and lines glow)
ZOOM = 1.0           # the page at its own size: its text in the Compaq's font (SCREEN_CSS) reads best so
FONT_FILE = "/opt/compaq/web/vendor/Compaq_Port3.woff"   # VileR's Compaq Portable III font, CC BY-SA
HINT = "Ask FixBot...   F2: the guide   PgUp/PgDn: scroll   F10: leave"
# What the lobby doesn't show of the logged-in account: its FixBot history
# (the sidebar and its toggle), the share button, and an iFixit employee's
# staff tools (Admin, the persona switch). Hidden things can't be reached
# with Tab either.
LOBBY_CSS = ", ".join(f"[data-testid={name}]" for name in (
    "sidebar-toggle-button", "sidebar-menu", "sidebar-content", "sidebar-footer", "sidebar-user-nav-menu",
    "chat-options-button", "share-chat-button", "persona-selector-trigger", "admin-info-dropdown-trigger")) \
    + ", [data-sidebar=sidebar] { display: none !important; }"
# The page in the Compaq's own font (8x16 dots, drawn for this screen), the
# answers' lines closer together, and the message box one line tall, so a
# 400-dot screen holds more than a few lines of an answer. The source
# numbers go (the Sources list under an answer stays). FixBot's guide panel
# is its own frame (ifixit.com), drawn as is.
try:
    with open(FONT_FILE, "rb") as _f:
        _FONT = ('@font-face { font-family: "CompaqPort3"; src: url(data:font/woff;base64,'
                 + base64.b64encode(_f.read()).decode() + ') format("woff"); } '
                 'body, body *:not(svg):not(path) { font-family: "CompaqPort3", monospace !important;'
                 ' font-size: 16px !important; letter-spacing: 0 !important; } ')
except OSError:
    _FONT = ""
SCREEN_CSS = _FONT + (
    "[data-testid=message-content], [data-testid=message-content] *, [data-role=user] * {"
    " line-height: 20px !important; } "
    "[data-testid=citation-badge] { display: none !important; } "
    "[data-testid=chat-input] { height: 22px !important; min-height: 22px !important; padding-top: 2px !important;"
    " padding-bottom: 0 !important; line-height: 20px !important; }")
LOBBY_JS = ("(() => { const add = () => { if (document.getElementById('compaq-lobby')) return;"
            " const s = document.createElement('style'); s.id = 'compaq-lobby'; s.textContent = %s;"
            " (document.head || document.documentElement).appendChild(s); };"
            " add(); document.addEventListener('DOMContentLoaded', add);"
            # (the empty message box says which keys do what)
            " setInterval(() => { const t = document.querySelector('[data-testid=chat-input]');"
            " if (t && t.placeholder !== %s) t.placeholder = %s; }, 1000); })()"
            % (json.dumps(LOBBY_CSS + " " + SCREEN_CSS), json.dumps(HINT), json.dumps(HINT)))
# Typing goes to the message box unless something else that takes typing
# has the focus: the Compaq has no mouse to click into it. True if it moved.
FOCUS_JS = ("(() => { const a = document.activeElement;"
            " if (a && (a.isContentEditable || /^(INPUT|TEXTAREA|SELECT)$/.test(a.tagName))) return false;"
            " const t = document.querySelector('[data-testid=chat-input]');"
            " if (!t) return false; t.focus(); return true; })()")
# Where the page's pictures are (in the screen's dots), so they're dithered
# like photos while its text stays crisp.
PICTURES_JS = """[...document.querySelectorAll('img, video, canvas')].map(e => {
  const r = e.getBoundingClientRect();
  if (r.width < 8 || r.height < 8 || r.bottom <= 0 || r.right <= 0 || r.top >= innerHeight) return null;
  // Only the rows where it's on top: not under the message box, nor scrolled away.
  const x = Math.min(innerWidth - 1, Math.max(0, r.left + r.width / 2));
  let top = null, bottom = null;
  for (let y = Math.max(0, r.top) + 1; y < Math.min(innerHeight, r.bottom); y += 2) {
    const hit = document.elementFromPoint(x, y);
    if (hit && hit !== document.body && (hit === e || hit.contains(e))) {
      if (top === null) top = y - 1;
      bottom = y + 1;
    }
  }
  return top === null ? null : [r.left, top, r.width, bottom - top];
}).filter(Boolean)"""
# Keeps the reading place of the last answer on the screen: fraction 0 puts
# its start at the top of the conversation, 1 its end.
FOLLOW_JS = """(fraction => {
  const all = [...document.querySelectorAll('[data-role=assistant]')];
  const m = all[all.length - 1];
  if (!m) return false;
  let box = m.parentElement;
  while (box && !(box.scrollHeight > box.clientHeight + 4 && /auto|scroll/.test(getComputedStyle(box).overflowY)))
    box = box.parentElement;
  if (!box) return false;
  const top = m.getBoundingClientRect().top - box.getBoundingClientRect().top + box.scrollTop;
  const spare = Math.max(0, m.offsetHeight - box.clientHeight * 0.75);
  box.scrollTop = top - 8 + fraction * spare;
  return true;
})"""
# FixBot's page marks its parts (data-testid): the message box, an answer's
# words (message-content), its source numbers (citation-badge), its cards
# (resource-card), and the thumbs up that appears once an answer is finished.
ANSWER_JS = r"""(() => {
  const all = [...document.querySelectorAll('[data-role=assistant]')];
  const m = all[all.length - 1];
  if (!m) return {count: 0};
  const words = m.querySelector('[data-testid=message-content]');
  let said = '';
  if (words) {
    const copy = words.cloneNode(true);
    copy.querySelectorAll('[data-testid=citation-badge], sup, img, svg').forEach(e => e.remove());
    copy.querySelectorAll('.resource-card').forEach(card => {
      const parts = [...card.querySelectorAll('span')].filter(e => !e.children.length).map(e => e.innerText.trim()).filter(Boolean);
      card.replaceWith(document.createTextNode(parts.length > 1 ? parts[0] + ': ' + parts[1] + '. ' : ''));
    });
    copy.querySelectorAll('li').forEach(li => li.append(document.createTextNode('.')));
    document.body.append(copy);
    copy.style.position = 'absolute'; copy.style.left = '-99999px';
    said = copy.innerText;
    copy.remove();
  }
  // (an answer that ends in buttons to pick from has no thumbs up: its "Thinking (5s)" turning
  // into "Thought for 6s" is the sign it's finished)
  const thought = [...m.querySelectorAll('button')].some(b => /^Thought for/.test(b.innerText.trim()));
  return {count: all.length, said, done: !!m.querySelector('[data-testid=upvote-button]'), thought,
          text: m.innerText.length};
})()"""
FONTS = ('<?xml version="1.0"?><!DOCTYPE fontconfig SYSTEM "fonts.dtd"><fontconfig><match target="font">'
         '<edit name="antialias" mode="assign"><bool>false</bool></edit>'
         '<edit name="hinting" mode="assign"><bool>true</bool></edit>'
         '<edit name="hintstyle" mode="assign"><const>hintfull</const></edit></match></fontconfig>')
# Keys that aren't typing, as the Compaq's keyboard sends them (pilink.OTHER):
# (DevTools key name, Windows key code).
SPECIAL = {b"\x1b": ("Escape", 27), b"\x7f": ("Backspace", 8), b"\t": ("Tab", 9), b"\r": ("Enter", 13),
           b"\x1b[A": ("ArrowUp", 38), b"\x1b[B": ("ArrowDown", 40), b"\x1b[C": ("ArrowRight", 39),
           b"\x1b[D": ("ArrowLeft", 37), b"\x1b[5~": ("PageUp", 33), b"\x1b[6~": ("PageDown", 34),
           b"\x1b[1~": ("Home", 36), b"\x1b[4~": ("End", 35), b"\x1b[3~": ("Delete", 46),
           b"\x1bOQ": ("F2", 113), b"\x1b[[B": ("F2", 113), b"\x1b[12~": ("F2", 113)}


def split_keys(typed):
    """Bytes typed at a terminal (the shared session: the TV's keyboard, a
    browser) as keys for key(): escape sequences whole. Returns (keys, the
    start of a sequence still on its way)."""
    keys, i = [], 0
    longest = sorted(SPECIAL, key=len, reverse=True)
    while i < len(typed):
        rest = typed[i:]
        if any(len(seq) > len(rest) and seq.startswith(rest) for seq in longest):
            break                                # (the rest of an escape sequence is coming)
        whole = next((seq for seq in longest if rest.startswith(seq)), rest[:1])
        keys.append(whole)
        i += len(whole)
    return keys, typed[i:]


class PageError(Exception):
    """The page couldn't be shown. The message is for the person at the
    Compaq; .detail (for the log) says what Chromium said last."""

    def __init__(self, message, detail=""):
        super().__init__(message)
        self.detail = detail


def login():
    """The saved iFixit session cookie, or "" (then the page is a guest's)."""
    try:
        with open(LOGIN) as f:
            for line in f:
                name, _, value = line.strip().partition("=")
                if name == "IFIXIT_SESSION":
                    return value.strip()
    except OSError:
        pass
    return ""


class Chrome:
    """Headless Chromium and its DevTools pipe: call() a method and wait for
    its answer; events (a new picture of the page) arrive in .events."""

    def __init__(self, home):
        os.makedirs(f"{home}/.config/fontconfig")
        with open(f"{home}/.config/fontconfig/fonts.conf", "w") as f:
            f.write(FONTS)
        to_r, self.to_w = os.pipe()
        from_r, from_w = os.pipe()

        def wire():
            # Chromium reads on fd 3 and writes on fd 4. The pipe's ends go out of
            # the way first (fd 10 and up): one already at 3 or 4 would be "copied"
            # onto itself, which does nothing and keeps it closing at exec (a
            # process with many files open, like PAL, gets low numbers back).
            high_r = fcntl.fcntl(to_r, fcntl.F_DUPFD, 10)
            high_w = fcntl.fcntl(from_w, fcntl.F_DUPFD, 10)
            os.dup2(high_r, 3)
            os.dup2(high_w, 4)
            os.set_inheritable(3, True)
            os.set_inheritable(4, True)
        self.home = home
        self.process = subprocess.Popen(
            [BROWSER, "--remote-debugging-pipe", f"--user-data-dir={home}/profile", "--no-first-run",
             "--disable-gpu", "--mute-audio", "--disable-extensions", "--hide-scrollbars",
             "--font-render-hinting=full", "--disable-font-subpixel-positioning",
             f"--window-size={WIDTH},{HEIGHT}", "about:blank"],
            preexec_fn=wire, close_fds=False, cwd=home, stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=open(f"{home}/chrome.log", "wb"), env=dict(os.environ, HOME=home), start_new_session=True)
        os.close(to_r)
        os.close(from_w)
        self.reader = os.fdopen(from_r, "rb", buffering=0)
        self.lock = threading.Lock()
        self.waiting = {}                 # id: [threading.Event, answer]
        self.events = queue.Queue()
        self.next_id = 0
        threading.Thread(target=self.read, daemon=True).start()

    def read(self):
        pending = b""
        while True:
            try:
                chunk = self.reader.read(1 << 16)
            except OSError:
                chunk = b""
            if not chunk:
                break
            pending += chunk
            while b"\0" in pending:
                raw, pending = pending.split(b"\0", 1)
                try:
                    message = json.loads(raw)
                except ValueError:
                    continue
                box = self.waiting.pop(message.get("id"), None) if "id" in message else None
                if box:
                    box[1] = message
                    box[0].set()
                elif "method" in message:
                    self.events.put(message)
        for box in list(self.waiting.values()):      # (Chromium has gone: nobody waits for ever)
            box[0].set()
        self.events.put(None)

    def call(self, method, params=None, session=None, timeout=30):
        with self.lock:
            self.next_id += 1
            ask = {"id": self.next_id, "method": method, "params": params or {}}
            if session:
                ask["sessionId"] = session
            box = self.waiting[self.next_id] = [threading.Event(), None]
            try:
                os.write(self.to_w, json.dumps(ask).encode() + b"\0")
            except OSError as e:
                raise PageError("The Pi's browser stopped.", self.last_words()) from e
        if not box[0].wait(timeout) or box[1] is None:
            raise PageError("The Pi's browser didn't answer.", self.last_words())
        if "error" in box[1]:
            raise PageError(f"The Pi's browser refused {method}: {box[1]['error'].get('message', '')}")
        return box[1].get("result", {})

    def last_words(self):
        """How Chromium ended, and the last thing it said (for the log)."""
        try:
            with open(f"{self.home}/chrome.log", errors="replace") as f:
                said = [line.strip() for line in f if line.strip() and "dbus" not in line][-2:]
        except OSError:
            said = []
        code = self.process.poll()
        return ("still running" if code is None else f"exit {code}") + ("; " + " | ".join(said) if said else "")

    def close(self):
        # (its whole group: the renderers too, so nothing writes into the
        # profile while it's being removed)
        try:
            os.killpg(self.process.pid, 9)
        except OSError:
            pass
        self.process.wait()
        for fd in (self.to_w,):
            try:
                os.close(fd)
            except OSError:
                pass


class Page:
    """The FixBot page in the Pi's browser, logged in when there's a login."""

    def __init__(self, url=URL):
        state = os.environ.get("STATE_DIRECTORY", "/var/lib/compaq-pal")
        self.home = tempfile.mkdtemp(prefix="fixbot-page-", dir=state if os.access(state, os.W_OK) else None)
        self.chrome = Chrome(self.home)
        try:
            # The login first, browser-wide; then FixBot in a fresh tab of its own
            # (a tab that navigates from about:blank to another site moves to a new
            # renderer, and the connection to it goes).
            cookie = login()
            self.logged_in = bool(cookie)
            if cookie:
                self.chrome.call("Storage.setCookies", {"cookies": [{
                    "name": "session", "value": cookie, "domain": ".ifixit.com", "path": "/",
                    "secure": True, "httpOnly": True}]})
            target = self.chrome.call("Target.createTarget", {"url": url, "width": WIDTH, "height": HEIGHT})
            self.session = self.chrome.call("Target.attachToTarget",
                                            {"targetId": target["targetId"], "flatten": True})["sessionId"]
            for method in ("Page.enable", "Runtime.enable"):
                self.call(method)
            self.call("Page.addScriptToEvaluateOnNewDocument", {"source": LOBBY_JS})   # (each later load)
            self.call("Emulation.setDeviceMetricsOverride",
                      {"width": round(WIDTH / ZOOM), "height": round(HEIGHT / ZOOM), "deviceScaleFactor": ZOOM,
                       "mobile": False})
        except Exception:
            self.close()
            raise

    def call(self, method, params=None, timeout=30):
        return self.chrome.call(method, params, self.session, timeout)

    def js(self, expression):
        answer = self.call("Runtime.evaluate", {"expression": expression, "returnByValue": True,
                                                "awaitPromise": True})
        return answer.get("result", {}).get("value")

    def key(self, typed):
        """What a key at the Compaq typed: a character, or a key like Enter.
        Page Up and Page Down scroll the conversation (a laptop's trackpad
        would; the Compaq has no mouse)."""
        if typed in (b"\x1b[5~", b"\x1b[6~"):
            # A mouse wheel turned over the middle of the screen: it scrolls
            # whatever is there, the conversation or the guide (its own frame).
            self.call("Input.dispatchMouseEvent", {
                "type": "mouseWheel", "x": WIDTH // 2, "y": HEIGHT // 3, "deltaX": 0,
                "deltaY": (0.6 if typed == b"\x1b[6~" else -0.6) * HEIGHT})
            return
        if typed in (b"\x1bOQ", b"\x1b[[B", b"\x1b[12~"):   # F2 (any terminal's): the guide, opened or closed
            self.guide()
            return
        if typed not in SPECIAL or SPECIAL[typed][0] == "Backspace":
            self.js(FOCUS_JS)                    # (letters always land in the message box)
        if typed in SPECIAL:
            name, code = SPECIAL[typed]
            down = {"type": "rawKeyDown", "key": name, "code": name, "windowsVirtualKeyCode": code}
            if name == "Enter":
                down.update(type="keyDown", text="\r")
            self.call("Input.dispatchKeyEvent", down)
            self.call("Input.dispatchKeyEvent", {"type": "keyUp", "key": name, "code": name,
                                                 "windowsVirtualKeyCode": code})
        else:
            text = typed.decode("latin-1")
            if text.isprintable():
                self.call("Input.insertText", {"text": text})

    def ready(self, timeout=40):
        """Waits for the message box; False if it never came (the login
        ended, or FixBot is down)."""
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            if self.js("!!document.querySelector('[data-testid=chat-input]')"):
                self.js(LOBBY_JS)                # (this load: it began before the tab was ours)
                self.js(FOCUS_JS)                # (the cursor in the box, ready to type)
                return True
            time.sleep(0.5)
        return False

    def follow(self, fraction):
        """Scrolls the conversation to the reading place in the last answer
        (0: its start, 1: its end), as someone reading along would."""
        try:
            self.js(f"({FOLLOW_JS})({max(0.0, min(1.0, fraction)):.3f})")
        except PageError:
            pass

    def pictures(self):
        """Where the page's pictures are now, in the screen's dots: [(x, y, w, h)]."""
        try:
            return [tuple(round(v * ZOOM) for v in r) for r in self.js(PICTURES_JS) or []]
        except PageError:
            return []

    def answers(self):
        """How many answers the conversation has, and the last one: its
        words to say, and whether it's finished."""
        return self.js(ANSWER_JS) or {"count": 0}

    def send(self, text):
        """Types text into FixBot's message box and sends it, as a person
        would, and checks it went (a page still starting up can leave it in
        the box): up to three tries. Returns how many answers there were
        before."""
        before = self.answers().get("count", 0)
        for _ in range(3):
            asked = self.js("document.querySelectorAll('[data-role=user]').length") or 0
            # (focus and select what's in the box, so the words replace a message that didn't go)
            self.js("(() => { const t = document.querySelector('[data-testid=chat-input]');"
                    " if (t) { t.focus(); if (t.select) t.select(); } })()")
            self.call("Input.insertText", {"text": text})
            time.sleep(0.4)
            if not self.js("(() => { const b = document.querySelector('[data-testid=send-button]');"
                           " if (!b || b.disabled) return false; b.click(); return true; })()"):
                self.key(b"\r")
            for _ in range(12):
                time.sleep(0.5)
                if (self.js("document.querySelectorAll('[data-role=user]').length") or 0) > asked:
                    return before
            time.sleep(2)
        raise PageError("FixBot's page didn't take the message.")

    def answer(self, before, timeout=240, waiting=None):
        """The words of the answer after before, once FixBot has finished it
        (its thumbs up appears; or it says it has thought, and its text has
        stood still a moment; or its text has stood still a while). "" if
        none came. waiting(seconds) is called about each second until then."""
        started = last_change = time.monotonic()
        last = None
        while time.monotonic() - started < timeout:
            now = self.answers()
            if now.get("count", 0) > before:
                if now.get("done"):
                    return now.get("said", "").strip()
                if (now.get("text"), now.get("said")) != last:
                    last, last_change = (now.get("text"), now.get("said")), time.monotonic()
                elif now.get("said") and time.monotonic() - last_change > (1.5 if now.get("thought") else 20):
                    return now["said"].strip()
            if waiting:
                waiting(time.monotonic() - started)
            time.sleep(0.5)
        return ""

    def click(self, label):
        """Clicks the last thing on the page labelled label (any case): a
        button or link with those words, or with those words inside it (the
        "Open guide" on a guide card), as a person would. False if none."""
        return bool(self.js("(() => { const want = %s.toLowerCase();"
                            " const said = e => (e.getAttribute('aria-label') || '').trim().toLowerCase() === want"
                            "   || (!e.children.length && (e.innerText || '').trim().toLowerCase() === want);"
                            " const all = [...document.querySelectorAll('button, a, span, p, div')].filter(said);"
                            " const e = all[all.length - 1]; if (!e) return false;"
                            " (e.closest('button, a') || e).click(); return true; })()" % json.dumps(label)))

    def attach(self, path):
        """A photo into FixBot's own photo button (its file input), as if
        picked from a phone's camera roll; it goes with the next message."""
        root = self.call("DOM.getDocument", {"depth": 0})["root"]["nodeId"]
        inputs = self.call("DOM.querySelectorAll", {"nodeId": root, "selector": "input[type=file]"})["nodeIds"]
        if not inputs:
            raise PageError("FixBot's page has no photo button right now.")
        self.call("DOM.setFileInputFiles", {"files": [path], "nodeId": inputs[-1]})

    def guide(self):
        """Opens the latest guide FixBot offered (its card's "Open guide"),
        or closes the guide if it's open. True if either happened."""
        if self.js("[...document.querySelectorAll('button')].some(b => /ask fixbot about this step/i.test("
                   "b.innerText) && b.offsetParent !== null)"):
            return self.click("Close")
        return self.click("Open guide")

    def new_chat(self):
        """A fresh conversation, for the next person."""
        self.call("Page.navigate", {"url": URL})
        self.ready()

    def watch(self):
        """Pictures of the page from now on, each time it changes (into
        .chrome.events as Page.screencastFrame)."""
        try:
            self.call("Page.stopScreencast")       # (one left running by a show that ended badly)
        except PageError:
            pass
        self.call("Page.startScreencast", {"format": "png", "maxWidth": WIDTH, "maxHeight": HEIGHT,
                                           "everyNthFrame": 1})

    def close(self):
        self.chrome.close()
        shutil.rmtree(self.home, ignore_errors=True)


BAYER = ((0, 8, 2, 10), (12, 4, 14, 6), (3, 11, 1, 9), (15, 7, 13, 5))


def dots(png, pictures=()):
    """A picture of the page as the Compaq's dots: True where a dot glows.
    The page is light, so its darker parts, text and lines, glow; its
    pictures ((x, y, w, h) in dots) are dithered the right way round, bright
    parts glowing, like a photo on the plasma."""
    import numpy as np
    from PIL import Image
    grey = np.asarray(Image.open(io.BytesIO(png)).convert("L"))
    lit = np.zeros((HEIGHT, WIDTH), bool)
    h, w = min(HEIGHT, grey.shape[0]), min(WIDTH, grey.shape[1])
    lit[:h, :w] = grey[:h, :w] < CUT
    pattern = (np.array(BAYER, np.float32) + 0.5) / 16
    for x, y, width, height in pictures:
        x0, y0, x1, y1 = max(0, x), max(0, y), min(w, x + width), min(h, y + height)
        if x1 - x0 < 4 or y1 - y0 < 4:
            continue
        part = grey[y0:y1, x0:x1].astype(np.float32)
        low, high = np.percentile(part, (2, 98))
        level = np.clip((part - low) / max(high - low, 24.0), 0, 1)
        tiles = np.tile(pattern, (-(-(y1 - y0) // 4) + 1, -(-(x1 - x0) // 4) + 1))
        lit[y0:y1, x0:x1] = level > tiles[y0 % 4:y0 % 4 + y1 - y0, x0 % 4:x0 % 4 + x1 - x0]
    return lit


def show(page, canvas, seconds=None, on_key=None, stop=None):
    """The page on the canvas until the screen is taken away (or seconds,
    or stop is set): a new screenful whenever the page changes and the last
    one has arrived, and keys at the Compaq typed into it (on_key sees them
    first, and may return True to keep one)."""
    page.watch()
    try:
        watching(page, canvas, seconds, on_key, stop)
    finally:
        try:
            page.call("Page.stopScreencast")
        except PageError:
            pass


def watching(page, canvas, seconds, on_key, stop):
    latest, sent = None, None
    end = time.monotonic() + seconds if seconds else None
    events = page.chrome.events
    while not canvas.closed and (end is None or time.monotonic() < end) and not (stop and stop.is_set()):
        try:
            event = events.get(timeout=0.1)
        except queue.Empty:
            event = False
        if event is None:
            raise PageError("The Pi's browser stopped.")
        if event and event.get("method") == "Page.screencastFrame":
            params = event["params"]
            latest = params["data"]
            try:
                page.call("Page.screencastFrameAck", {"sessionId": params["sessionId"]})
            except PageError:
                pass
        for key, pressed, typed in canvas.news(0):
            # (the screen says what a key typed as text; key() takes bytes)
            typed = typed.encode("latin-1", "replace") if isinstance(typed, str) else typed
            if pressed and typed and not (on_key and on_key(typed)):
                try:
                    page.key(typed)
                except PageError:
                    pass                           # (one key the page didn't take isn't worth the page)
        if latest and latest is not sent and canvas.ready:
            canvas.send(dots(base64.b64decode(latest), page.pictures()))
            sent = latest


def main():
    seconds = float(sys.argv[1]) if len(sys.argv) > 1 else None
    try:
        canvas = pictures.Canvas("640x400", lobby_only=True)
    except pictures.NotShown as e:
        sys.exit(str(e))
    if (canvas.width, canvas.height) != (WIDTH, HEIGHT):
        canvas.close()
        sys.exit("This screen can't show FixBot's page: it needs the plasma's 640x400 dots (PILINK).")
    page = None
    try:
        page = Page()
        print("FixBot's page" + (" (logged in)" if page.logged_in else " (as a guest)") + " is on the screen.",
              flush=True)
        show(page, canvas, seconds)
    except PageError as e:
        print(e)
    finally:
        if page:
            page.close()
        canvas.close()


if __name__ == "__main__":
    main()

"""FixBot mode: PAL as the voice and screen of FixBot, iFixit's repair
assistant ("Hey FixBot").

FixBot does all the thinking, through its Partner API (lib/ifixit.py): the
plan, the guide it recommends, every answer. What someone says goes to it
word for word. PAL only hears (Whisper turns speech into text) and speaks
(espeak). This module holds the parts that aren't FixBot's and decide
nothing about the repair: the wake phrase, a few fixed voice commands that
move through what FixBot sent (next, back, step 12, the photo, we're done),
and how FixBot's answer is laid out on the Compaq's screen and read out a
piece at a time.
"""

import re
import textwrap
import time

import ifixit
from chat import to_ascii, unmarkdown

WIDTH = 77              # text width on the page (the frame is 79 columns)
ROWS = 22               # the page's rows (PAL's spoken words scroll in the two below)
LISTEN_SECONDS = 20     # after FixBot's turn, how long PAL listens without "Hey FixBot"
IDLE_SECONDS = 30 * 60  # a repair this quiet for this long is over: "Hey FixBot" starts a new one
CHUNK_WORDS = 60        # an answer is read about this much at a time ("next" for more)

# "Hey FixBot" as PAL's Whisper (the small English model) writes it, or
# "FixBot," on its own at the start. Recordings of the Mac's voices, heard
# the way PAL hears them: at the start of a sentence it comes out well
# ("Hey Fixbot, I'm trying to...", "Hey fix, but", "Hey Fix What?", "Hey fix
# that"); said on its own, a short clip, much less so ("A fixed spot",
# "K-fix spot", "Hey fix not", "Hey fix dot", "HAVicsbot", "A fixbodge"):
# just_the_name() takes those. (espeak can't say it: "Hey, big smart".)
WAKE = re.compile(
    r"^\W*(?:(?:oh|um|uh|so|and|well)\W+)?"
    r"(?:(?:hey|hi|hello|hay|ok|okay|yo|ey|a|k)\W+"
    r"(?:fix(?:ed|es)?\W{0,2}(?:it\W{0,2})?(?:bot|bots|but|bought|pot|pots|box|bob|bod|bodge|spot|dot|not|"
    r"what|that)|fixbot|fixpot)"
    r"|fix\W?bot)\b\W*", re.I)
NOT_THE_NAME = re.compile(r"\bfix(?:ed|es|ing)?\s+(?:it|this|that|my|me|the|a|your|up)\b|^fix(?:ing|es)$")


def just_the_name(heard):
    """Only "Hey FixBot", as Whisper writes it said on its own: up to four
    words, one of them fix-something (or "Vics"), and not "fix it" or "fix
    my"."""
    words = re.findall(r"[a-z]+", heard.lower())
    return (1 <= len(words) <= 4 and any(re.search(r"fix|vics|fics", w) for w in words)
            and not NOT_THE_NAME.search(" ".join(words)))


NUMBERS = {"one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6, "seven": 7, "eight": 8,
           "nine": 9, "ten": 10, "eleven": 11, "twelve": 12, "thirteen": 13, "fourteen": 14,
           "fifteen": 15, "sixteen": 16, "seventeen": 17, "eighteen": 18, "nineteen": 19,
           "twenty": 20, "first": 1}
# The commands, matched against all of what was said (lower case, no
# punctuation, without a leading "okay" or a trailing "please"). Anything
# else goes to FixBot.
FILLER = re.compile(r"^(?:(?:ok|okay|alright|all right|right|um|uh|so|and|cool|great|now|then|hey)\s+)+")
TRAILING = re.compile(r"(?:\s+(?:please|thanks|thank you|now|fixbot|fix bot))+$")
STEP = re.compile(r"(?:(?:go|jump|skip|back) (?:to |back to )?|show (?:me )?|read (?:me )?)?"
                  r"step (?:number )?(\d{1,3}|[a-z]+)")
COMMANDS = [(name, re.compile(pattern)) for name, pattern in (
    ("ack", r"thanks|thank you|cool|great|nice|awesome|perfect|wow|hmm+|ok|okay|alright|oh|uh|um"),
    ("next", r"next(?: (?:step|one|page|bit|part))?|continue|go on|keep going|carry on|what's next|"
             r"what next|and then|more|tell me more|done|finished|got it|ready|i'm ready|let's go|"
             r"let's start|start|go ahead|yes|yeah|yep|sure"),
    ("end", r"(?:we're|i'm|we are|i am|all) (?:done|finished)(?: (?:with (?:it|this|that|the repair)|"
            r"for (?:now|today)|here))?|that's (?:all|it)|(?:stop|quit|exit|goodbye|good bye|bye|"
            r"never mind|nevermind)(?: fixbot| fix bot)?"),
    ("back", r"(?:go )?back(?: one)?|previous(?: step| one)?|(?:the )?last step|step back|go back a step"),
    ("repeat", r"repeat(?: that| it| the step)?|say (?:that|it) again|again|come again|pardon|what|"
               r"what was that|read (?:that|it) again|one more time|i missed that"),
    ("photo", r"(?:show (?:me )?|see |let me see )?(?:the |a )?(?:next )?(?:photo|photos|picture|pictures|"
              r"pic|image)|show me|let me see"),
    ("camera", r"(?:take|snap) (?:a |the )?(?:photo|picture|pic)(?: of (?:this|it|that))?|"
               r"look at (?:this|it|that)|can you see (?:this|it|that)|see this|what do you see"),
    ("guide", r"(?:(?:open|show|pull up|bring up|start|go to|back to) )?(?:me )?(?:the )?guide"),
    ("new", r"start over|start again|new repair|something else|(?:a )?different (?:repair|device|problem|phone)|"
            r"new (?:device|problem)"),
)]
# On FixBot's own page (lib/fixbot_page.py) everything said goes to FixBot,
# except these, which press the page's own buttons or end the visit.
PAGE_COMMANDS = [(name, re.compile(pattern)) for name, pattern in (
    ("ack", r"thanks|thank you|cool|great|nice|awesome|perfect|wow|hmm+|ok|okay|alright|oh|uh|um"),
    ("end", r"(?:we're|i'm|we are|i am|all) (?:done|finished)(?: (?:with (?:it|this|that|the repair)|"
            r"for (?:now|today)|here))?|that's (?:all|it)|(?:stop|quit|exit|goodbye|good bye|bye|"
            r"never mind|nevermind)(?: fixbot| fix bot)?|(?:no )?(?:i'm|we're|i am|we are) (?:good|all set|"
            r"okay|ok|fine)|all set|no thanks|no thank you|that's enough"),
    ("new", r"start over|start again|new chat|new repair|something else|(?:a )?different (?:repair|device|problem|phone)"),
    ("guide", r"(?:(?:open|show|pull up|bring up) )(?:me )?(?:the )?guide"),
    ("close", r"close (?:the )?guide|hide (?:the )?guide"),
    ("camera", r"(?:take|snap) (?:a |the )?(?:photo|picture|pic)(?: of (?:this|it|that))?|"
               r"look at (?:this|it|that)|can you see (?:this|it|that)|see this|what do you see"),
)]


# Leaving FixBot, said any way and anywhere in a sentence: back to the
# main menu ("menu"), or just FixBot closed ("end").
MENU = re.compile(r"\bmain menu\b|\bhome screen\b|\b(?:go|back|take me|bring me|return|get) (?:\w+ ){0,3}the menu\b")
LEAVE = re.compile(r"\b(?:close|exit|leave|quit|stop|end|shut|turn off)(?: down)? (?:the )?fix ?bot\b")


def page_command(heard):
    """A button on FixBot's page, or leaving ("end", or "menu" for the main
    menu; "ack" to let pass), else None: it goes to FixBot as said."""
    words = plain_words(heard)
    if not words:
        return "ack"
    if MENU.search(words):
        return "menu"
    if LEAVE.search(words):
        return "end"
    if len(words.split()) > 8:
        return None
    trimmed = TRAILING.sub("", FILLER.sub("", words + " ").strip()).strip() or words
    return next((name for name, pattern in PAGE_COMMANDS if pattern.fullmatch(trimmed)), None)


# "...pull up the guide and walk me through it": they want the guide FixBot recommends opened.
WANTS_GUIDE = re.compile(r"\b(?:guide|walk me through|step by step|instructions)\b", re.I)


def plain_words(heard):
    """What was said, for matching commands: lower case, no punctuation, and
    said once (Whisper's small model sometimes writes a short phrase twice:
    "Open the guide. Open the guide.")."""
    words = " ".join(re.sub(r"[^a-z0-9' ]", " ", heard.lower().replace("\u2019", "'")).split())
    half = words.split()
    if len(half) % 2 == 0 and half[:len(half) // 2] == half[len(half) // 2:]:
        words = " ".join(half[:len(half) // 2])
    return words


def command(heard):
    """(name, step number or None) for a fixed command, else (None, None):
    a question for FixBot. Only short things count ("what's the next step
    after the screen?" is a question)."""
    words = plain_words(heard)
    if not words:
        return "ack", None
    if len(words.split()) > 8:
        return None, None
    trimmed = TRAILING.sub("", FILLER.sub("", words + " ").strip()).strip() or words
    found = STEP.fullmatch(trimmed)
    if found:
        number = found.group(1)
        number = int(number) if number.isdecimal() else NUMBERS.get(number)
        if number:
            return "step", number
    for name, pattern in COMMANDS:
        if pattern.fullmatch(trimmed):
            return name, None
    return None, None


def said_words(text):
    """Text for the voice: no web addresses, no Markdown marks."""
    text = re.sub(r"\s*\(https?://\S+?\)|https?://\S+", "", text)
    text = re.sub(r"[*_#`|>]+", " ", text)
    return " ".join(to_ascii(text).split())


def blocks_of(markdown):
    """FixBot's Markdown as blocks, each (its lines on the page, its words
    to say): a heading, a list item, or a paragraph; long ones split
    between sentences so each can be read on its own."""
    out, current = [], []

    def close():
        if current:
            text = "\n".join(current)
            heading = len(current) == 1 and text.isupper() and len(text.split()) <= 12
            say = said_words(text.capitalize() if heading else text)
            if say and not re.search(r"[.!?:]$", say):
                say += "."
            pieces, piece = [], []
            for sentence in re.split(r"(?<=[.!?])\s+", say):
                if piece and len(" ".join(piece + [sentence]).split()) > CHUNK_WORDS:
                    pieces.append(" ".join(piece))
                    piece = []
                piece.append(sentence)
            if piece:
                pieces.append(" ".join(piece))
            if len(pieces) == 1:
                out.append((wrap(text), pieces[0], heading))
            else:
                for i, piece_text in enumerate(pieces):     # (the page shows each piece as it's read)
                    out.append((wrap(("  " if i else "") + piece_text), piece_text, False))
            current.clear()

    for line in to_ascii(unmarkdown(markdown or "")).splitlines():
        if not line.strip():
            close()
        elif re.match(r"\s*(?:\* |\d+[.)] )", line) or (line.isupper() and line.strip()):
            close()
            current.append(line.rstrip())
        else:
            current.append(line.rstrip())
    close()
    return out


def wrap(text, width=WIDTH):
    """Lines for the page: list items hang under their bullet."""
    lines = []
    for line in to_ascii(text).splitlines():
        if not line.strip():
            lines.append("")
            continue
        bullet = re.match(r"\s*(?:\* |- |\d+[.)] )", line)
        hang = " " * (bullet.end() if bullet else len(line) - len(line.lstrip()))
        lines += textwrap.wrap(line, width, subsequent_indent=hang) or [""]
    return lines


class Answer:
    """One answer from FixBot, read out a chunk at a time."""

    def __init__(self, markdown, extra=()):
        """extra: more to show and say after FixBot's words, each text or
        (text, words to say)."""
        self.blocks = blocks_of(markdown)
        for item in extra:
            shown, say = item if isinstance(item, tuple) else (item, item)
            self.blocks.append(([""] + wrap(shown), said_words(say), False))
        self.chunks = []              # (first block, end), about CHUNK_WORDS words each
        start, words = 0, 0
        for i, (_, say, heading) in enumerate(self.blocks):
            if i > start and words + len(say.split()) > CHUNK_WORDS and not self.blocks[i - 1][2]:
                self.chunks.append((start, i))
                start, words = i, 0
            words += len(say.split())
        if start < len(self.blocks):
            self.chunks.append((start, len(self.blocks)))
        self.at = 0                   # the next chunk to read

    def words(self, chunk):
        first, end = self.chunks[chunk]
        return " ".join(say for _, say, _ in self.blocks[first:end] if say)

    def lines(self, chunk):
        """The page from chunk on (a blank line before headings)."""
        first = self.chunks[chunk][0] if chunk < len(self.chunks) else len(self.blocks)
        out = []
        for lines, _, heading in self.blocks[first:]:
            if heading and out:
                out.append("")
            out += lines
        return out


class Session:
    """One repair with FixBot: its conversation (chatid) and where they are."""

    def __init__(self):
        self.chatid = None
        self.device = ""              # FixBot's name for the device, once it has matched one
        self.asked = ""               # what they last asked FixBot
        self.answer = None            # FixBot's last answer
        self.shown = 0                # the chunk of it on the page
        self.recommended = None       # the guide FixBot recommended: {guideid, title, url}
        self.offered = None           # (that guide's id once PAL has pointed it out)
        self.guide = None             # the guide being followed (FixBot's copy of it)
        self.step = 0                 # 0: its overview; then its steps; then its end
        self.photo = 0                # the next of this step's photos to show
        self.view = "chat"            # what the page shows: "chat" or "guide"
        self.used = time.monotonic()

    def stale(self, now):
        return now - self.used > IDLE_SECONDS

    def steps(self):
        return [s for s in (self.guide or {}).get("steps") or [] if isinstance(s, dict)]

    def where(self):
        """Where they are in the guide, for FixBot: "(I'm on step 9 of the
        guide "iPhone 12 Screen Replacement": Disconnect the display.)"."""
        steps = self.steps()
        if not self.guide or not 1 <= self.step <= len(steps):
            return ""
        title = to_ascii(str(steps[self.step - 1].get("title") or "")).strip()
        return (f" (I'm on step {self.step} of {len(steps)} of the guide "
                f"\"{to_ascii(str(self.guide.get('title', '')))}\"" + (f": {title}" if title else "") + ".)")

    def page(self, status="", body=()):
        """The page: a header with the device and status, what's being read
        or the guide step, and what to say."""
        head = " FIXBOT" + (f"  {to_ascii(self.device)[:44]}" if self.device else "")
        status = status.upper()[:30]
        top = head.ljust(78 - len(status)) + status
        rule = " " + "-" * 77
        if self.view == "guide" and self.guide:
            foot = ' Say: "next"  "back"  "step 12"  "photo"  "we\'re done", or ask FixBot anything'
        elif self.answer and self.shown + 1 < len(self.answer.chunks):
            foot = ' Say: "next" for more  "repeat"  "we\'re done", or ask FixBot anything'
        elif self.guide:
            foot = ' Say: "next" to go on with the guide  "repeat"  "we\'re done", or ask anything'
        elif self.recommended:
            foot = ' Say: "open the guide"  "repeat"  "start over"  "we\'re done", or ask anything'
        else:
            foot = ' Ask FixBot anything.  Say "start over" or "we\'re done" when you are.'
        room = ROWS - 4
        lines = list(body)[:room]
        return [top[:79], rule] + [(" " + line)[:79] for line in lines] + [""] * (room - len(lines)) + [rule, foot[:79]]

    def photos(self):
        """The photos for where they are in the guide."""
        steps = self.steps()
        if not self.guide:
            return []
        if self.step == 0:
            url = str(self.guide.get("image_url") or "")
            return [url] if url.startswith("https://") else []
        return ifixit.step_photos(steps[self.step - 1]) if self.step <= len(steps) else []

    def guide_text(self):
        """(The page's lines, the words to say) for where they are in the guide."""
        g, steps = self.guide, self.steps()
        title = to_ascii(str(g.get("title", "")))
        if self.step == 0:
            facts = [f"Difficulty: {g['difficulty']}." if g.get("difficulty") else "",
                     f"Time: {g['time_required']}." if g.get("time_required") else ""]
            tools = [to_ascii(str(t["text"])) for t in g.get("tools") or [] if isinstance(t, dict) and t.get("text")]
            say = " ".join(f for f in [f"{title}.", *facts, f"{len(steps)} steps."] if f)
            if tools:
                say += " Tools: " + ", ".join(tools[:8]) + "."
            say += " Say next when you're ready."
            lines = wrap(unmarkdown(ifixit.guide_overview(g)))
        elif self.step <= len(steps):
            step = steps[self.step - 1]
            name = to_ascii(str(step.get("title") or "")).strip()
            said = [f"Step {self.step}." + (f" {name}." if name else "")]
            for line in step.get("lines") or []:
                text = said_words(ifixit.strip_html(line.get("text_rendered")))
                label = ifixit.BULLET_LABELS.get(line.get("bullet"), "")
                if text:
                    said.append(label + text + ("" if re.search(r"[.!?:]$", text) else "."))
            say = " ".join(said)
            lines = wrap(ifixit.step_text(step, len(steps)).replace("## ", "", 1))
        else:
            end = said_words(ifixit.strip_html(g.get("conclusion")))
            say = (end + " " if end else "") + ("That's the end of the guide. Ask FixBot anything, "
                                                "or say we're done.")
            lines = wrap(f"The end of {title}.\n\n" + (end or "") + f"\n\nThe whole guide, with every photo "
                         f"in colour: {g.get('source_url') or g.get('url') or ''}")
        photos = self.photos()
        if photos:
            lines += ["", f"[{len(photos)} photo{'s' if len(photos) > 1 else ''}: say \"photo\"]"]
        return [f"{title[:70]}", ""] + lines, say

    def chat_lines(self):
        out = []
        if self.asked:
            asked = wrap("You: " + to_ascii(self.asked), WIDTH)
            out += asked[:2] + (["     ..."] if len(asked) > 2 else []) + [""]
        if self.answer:
            out += self.answer.lines(self.shown)
        return out

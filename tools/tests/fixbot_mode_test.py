# FixBot mode's own parts (pal/fixbot_mode.py), no PAL needed: the wake
# phrase, the voice commands, an answer read in chunks, the page, and a real
# guide from FixBot's open guide lookup (needs the internet).
# Runs anywhere with the repo: python3 tools/tests/fixbot_mode_test.py
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
ROOT = os.path.join(HERE, "..", "..", "pi", "opt", "compaq")
sys.path[:0] = [os.path.join(ROOT, "pal"), os.path.join(ROOT, "lib")]
import fixbot_mode as fm  # noqa: E402

failed = []


def check(what, ok):
    print(("ok    " if ok else "FAIL  ") + what)
    if not ok:
        failed.append(what)


# The wake phrase, and what it must not catch.
for heard, rest in [("Hey FixBot, I'm trying to fix my iPhone 12 screen.", "I'm trying to fix my iPhone 12 screen."),
                    ("Hey, fix bot. Next step.", "Next step."), ("Okay fixed bot what does this do", "what does this do"),
                    ("FixBot, open the guide.", "open the guide."), ("Hey Fixbot", ""), ("hey fix-it bot step 3", "step 3"),
                    ("K-fix bot.", ""), ("Hey fixpot, I'm trying to fix my iPhone 12 screen.",
                                         "I'm trying to fix my iPhone 12 screen."),
                    ("hay fixpot.", ""), ("Hey fix, spot.", ""), ("Hey fix what? Next step.", "Next step."),
                    ("Hey fix, but I'm trying to fix my iPhone 12 screen.", "I'm trying to fix my iPhone 12 screen.")]:
    m = fm.WAKE.match(heard)
    check(f"wake: {heard!r}", bool(m) and heard[m.end():].strip() == rest)
for heard in ["Hey PAL, what's the weather?", "I need to fix my phone", "Fix the bot later", "hey fixing it now"]:
    check(f"not a wake: {heard!r}", not fm.WAKE.match(heard))
# The name said on its own, as Whisper writes the short clip.
for heard in ["A fixed spot.", "K-fix spot.", "Hey fix not.", "Hey fix dot", "HAVicsbot", "A fixbodge. A fixbodge."]:
    check(f"just the name: {heard!r}", fm.WAKE.match(heard) or fm.just_the_name(heard))
for heard in ["Hey, thanks, man.", "Fix it.", "I fixed it", "Can you fix my phone?", "Fixing.", "Hey, you start"]:
    check(f"not the name: {heard!r}", not fm.WAKE.match(heard) and not fm.just_the_name(heard))

# Commands; anything longer or different is a question for FixBot.
for heard, want in [("Next step.", ("next", None)), ("Okay, next please.", ("next", None)), ("Done.", ("next", None)),
                    ("Go back.", ("back", None)), ("Go to step 12.", ("step", 12)), ("step twelve", ("step", 12)),
                    ("Show me the photo.", ("photo", None)), ("Photo", ("photo", None)),
                    ("Take a picture of this.", ("camera", None)), ("Open the guide.", ("guide", None)),
                    ("Pull up the guide", ("guide", None)), ("We're done.", ("end", None)), ("That's all.", ("end", None)),
                    ("Say that again.", ("repeat", None)), ("Start over.", ("new", None)), ("Thanks.", ("ack", None)),
                    ("Okay.", ("ack", None)), ("", ("ack", None)), ("Yes.", ("next", None)),
                    ("What does this cable do?", (None, None)), ("What's the best way to reapply the adhesive?", (None, None)),
                    ("what's the next step after the screen comes off", (None, None)), ("No.", (None, None))]:
    check(f"command: {heard!r} -> {want}", fm.command(heard) == want)

# On FixBot's own page: only the page's buttons and goodbyes are PAL's;
# everything else (next step, go back, step 12) is FixBot's to answer.
for heard, want in [("Open the guide.", "guide"), ("Pull up the guide", "guide"), ("Close the guide.", "close"),
                    ("Take a picture of this.", "camera"), ("Look at this.", "camera"), ("We're done.", "end"),
                    ("Start over.", "new"), ("New chat.", "new"), ("Thanks.", "ack"), ("", "ack"),
                    ("Open the guide. Open the guide.", "guide"), ("We're done, we're done.", "end"),
                    ("Next step.", None), ("Go back.", None), ("Go to step 12.", None), ("Show me the photo.", None),
                    ("What does this cable do?", None), ("Yes.", None),
                    ("Can you open the guide for the iPhone 12 battery please and walk me through it", None)]:
    check(f"page command: {heard!r} -> {want}", fm.page_command(heard) == want)

# An answer in chunks: every word of it said once, in order, headings kept
# with what follows them, nothing over about a chunk's worth.
plan = """## iPhone 12 screen replacement

Replacing an iPhone 12 screen takes about an hour. You'll need a **P2 pentalobe** driver,
a [suction handle](https://www.ifixit.com/products/suction-handle) and an opening pick.

1. Power off the phone and remove the two pentalobe screws next to the Lightning port.
2. Heat the bottom edge to soften the adhesive, then lift the screen with the suction handle.
3. Disconnect the battery before anything else, then the display cables.

### Reassembly

Apply new display adhesive, reconnect the cables, and test before you seal it up.
""" + " ".join(["This sentence pads a long paragraph so it has to be split up."] * 12)
answer = fm.Answer(plan, [("Parts: iPhone 12 Screen (89.99 USD)", "Parts: iPhone 12 Screen.")])
spoken = " ".join(answer.words(i) for i in range(len(answer.chunks)))
check("answer: several chunks", len(answer.chunks) >= 3)
check("answer: chunks are near the limit", all(len(answer.words(i).split()) <= fm.CHUNK_WORDS + 25
                                               for i in range(len(answer.chunks))))
check("answer: no web address or Markdown said", "http" not in spoken and "**" not in spoken and "#" not in spoken)
check("answer: all of it said, in order", spoken.index("Power off") < spoken.index("Heat the") < spoken.index("Apply new")
      and spoken.endswith("Parts: iPhone 12 Screen."))
check("answer: no chunk ends on a heading", all(not answer.blocks[end - 1][2] for _, end in answer.chunks[:-1]))
check("answer: the page from a chunk starts with it", answer.lines(1)[0].strip()[:12] in plan.replace("\n", " ")
      or answer.lines(1)[0].strip().startswith(("1.", "2.", "3.", "REASSEMBLY", "This")))
check("answer: the parts' price on the page", any("89.99 USD" in line for line in answer.lines(0)))

# The page: 22 rows of at most 79 columns, ASCII, whatever it holds.
s = fm.Session()
s.asked, s.answer, s.device = "I'm trying to fix my iPhone 12 screen " * 4, answer, "iPhone 12"
for status in ("", "thinking 112s", "listening"):
    page = s.page(status, s.chat_lines())
    check(f"page ({status or 'plain'}): 22 rows, 79 columns, ASCII",
          len(page) == fm.ROWS and all(len(r) <= 79 and r.isascii() for r in page))
check("page: the device and status in the header", "iPhone 12" in page[0] and page[0].endswith("LISTENING"))
check("page: what they asked, cut to two lines", page[2].startswith(" You: ") and page[4].strip() == "...")
s.recommended = {"guideid": 140572, "title": "iPhone 12 Screen Replacement"}
s.shown = len(answer.chunks) - 1
check("page: the foot offers the guide at the end", "open the guide" in s.page("", s.chat_lines())[-1])
check("where: nothing outside a guide", s.where() == "")

# A real guide, from FixBot's open guide lookup.
try:
    guide = fm.ifixit.guide(140572)
except fm.ifixit.FixBotError as e:
    guide = None
    check(f"guide 140572 fetched ({e})", False)
if guide:
    s.guide, s.view = guide, "guide"
    steps = s.steps()
    check(f"guide: {guide.get('title')!r}, {len(steps)} steps", len(steps) > 10)
    s.step = 0
    lines, say = s.guide_text()
    check("guide overview: title, steps and 'say next'", guide["title"] in say and f"{len(steps)} steps" in say
          and say.endswith("Say next when you're ready."))
    s.step = 3
    lines, say = s.guide_text()
    check(f"guide step 3 said: {say[:70]!r}...", say.startswith("Step 3.") and "<" not in say and say.isascii())
    check("guide step 3 page: fits, names the step, offers its photos",
          all(len(" " + line) <= 79 and line.isascii() for line in lines)
          and lines[2].startswith("Step 3 of") and (not s.photos() or "say \"photo\"" in lines[-1]))
    check("where: the step, for FixBot", s.where().startswith(" (I'm on step 3 of") and guide["title"] in s.where())
    s.step = len(steps) + 1
    lines, say = s.guide_text()
    check("guide end: says so", "end of the guide" in say)
    page = s.page("", s.guide_text()[0])
    check("guide page: 22 rows, 79 columns", len(page) == fm.ROWS and all(len(r) <= 79 for r in page))
    s.view, s.shown = "chat", len(answer.chunks) - 1
    check("an answer mid-guide: the foot says next goes on with it",
          "go on with the guide" in s.page("", s.chat_lines())[-1])

print("\n" + ("All passed." if not failed else f"{len(failed)} failed."))
sys.exit(1 if failed else 0)

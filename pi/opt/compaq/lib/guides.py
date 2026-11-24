#!/usr/bin/env python3
"""Search iFixit's repair guides and read them on the Compaq, a step at a
time, with each step's photos painted on its screen (dithered amber, down
the serial cable, like an old BBS) and a QR code to carry on reading the
step on a phone.

Uses the FixBot API's open search and guide lookups, so no API key needed.
Each page's photos, and the next page's, are fetched in the background while
it's read, so P shows them without waiting for the web.
"""

import collections
import os
import sys
import textwrap
import threading

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import ifixit  # noqa: E402
import pictures  # noqa: E402
from chat import fit, page, to_ascii  # noqa: E402

CLEAR = "\033[H\033[2J"


class Ahead:
    """Photos fetched in the background before anyone asks for them: this
    page's and the next one's. The last dozen are kept. (Daemon threads:
    leaving the guide never waits for a fetch.)"""

    KEEP = 12

    def __init__(self):
        self.fetching = collections.OrderedDict()     # url: {"done": Event, "image" or "error"}

    def want(self, urls):
        for url in urls:
            if url in self.fetching:
                self.fetching.move_to_end(url)
                continue
            box = {"done": threading.Event()}

            def fetch(url=url, box=box):
                try:
                    box["image"] = pictures.fetch(url)
                except pictures.NotShown as e:
                    box["error"] = e
                box["done"].set()
            threading.Thread(target=fetch, daemon=True).start()
            self.fetching[url] = box
        while len(self.fetching) > self.KEEP:
            self.fetching.popitem(last=False)

    def ready(self, url):
        return url in self.fetching and self.fetching[url]["done"].is_set()

    def get(self, url):
        """The picture (raises pictures.NotShown, as fetch does; a failed
        fetch is tried afresh next time)."""
        self.want([url])
        box = self.fetching[url]
        box["done"].wait()
        if "error" in box:
            self.fetching.pop(url, None)
            raise box["error"]
        return box["image"]


AHEAD = Ahead()


def page_photos(guide, at):
    """The photo addresses on page at (0: the overview; then the steps)."""
    steps = [s for s in guide.get("steps") or [] if isinstance(s, dict)]
    if at == 0:
        return [guide["image_url"]] if str(guide.get("image_url", "")).startswith("https://") else []
    if at <= len(steps):
        return ifixit.step_photos(steps[at - 1])
    return []


def photos(urls, caption):
    """The photos on the Compaq's screen, one after another, until they run
    out or someone presses Q."""
    for i, url in enumerate(urls, 1):
        label = caption if len(urls) == 1 else f"{caption}, photo {i} of {len(urls)}"
        what = "the photo" if len(urls) == 1 else f"photo {i} of {len(urls)}"
        if not AHEAD.ready(url):
            print(f"\n  Fetching {what}...", flush=True)
        try:
            key = pictures.show(AHEAD.get(url), label,
                                told=pictures.saying(what, more=i < len(urls)))
        except pictures.NotShown as e:
            print(f"  {e}")
            return
        if pictures.stops(key):
            return


def phone(url, caption):
    """A QR code for url on the Compaq's screen."""
    print("\n  Point a phone's camera at the Compaq's screen.")
    try:
        pictures.show(pictures.qr(url), caption, told=pictures.saying("a QR code", more=False))
    except pictures.NotShown as e:
        print(f"  {e}")


def read(guide):
    """A guide, a page at a time: its overview, each step, then the end."""
    steps = [s for s in guide.get("steps") or [] if isinstance(s, dict)]
    url = str(guide.get("source_url") or "")
    at = 0                                   # 0: the overview; 1 to len(steps): a step
    while True:
        print(CLEAR, end="")
        shots = page_photos(guide, at)
        AHEAD.want(shots + page_photos(guide, at + 1))      # (while this page is read)
        if at == 0:
            text = ifixit.guide_overview(guide)
            link, caption = url, to_ascii(str(guide.get("title", "")))[:60]
        elif at <= len(steps):
            step = steps[at - 1]
            text = ifixit.step_text(step, len(steps))
            link = str(step.get("stepLink") or url)
            caption = to_ascii(f"Step {at}: {step.get('title') or ''}").strip(": ")[:52]
        else:
            text = ifixit.strip_html(guide.get("conclusion")) or "That's the last step."
            text += f"\n\nThe whole guide, with every photo in colour:\n{url}"
            link, caption = url, "The whole guide"
        page(fit(text))
        choices = ["Enter: next" if at <= len(steps) else "Enter: done", "B: back"]
        if shots:
            choices.append(f"P: photo{'s' if len(shots) > 1 else ''} ({len(shots)})")
        if link.startswith("https://"):
            choices.append("L: link for your phone")
        choices.append("X: leave")
        while True:
            # (After a photo the bridge repaints this screen as it was, so
            # the page stays put and only the question comes again.)
            answer = input("\n  " + "  ".join(choices) + ": ").strip().lower()
            if answer == "p" and shots:
                photos(shots, caption)
            elif answer == "l" and link.startswith("https://"):
                phone(link, "Scan to read this on your phone")
            elif answer in ("", "b", "x", "q") or (answer.isdecimal() and len(answer) <= 3
                                                   and int(answer) <= len(steps)):
                break
            # (anything else: just the question again, not the whole page down the cable)
        if answer in ("x", "q"):
            return
        if answer == "b":
            at = max(0, at - 1)
        elif answer.isdecimal():
            at = int(answer)                 # (a step number: straight there)
        elif answer == "":
            if at > len(steps):
                return
            at += 1


def show(guide_id):
    """Loads one guide and reads it."""
    print("  Loading the guide...")
    try:
        guide = ifixit.guide(guide_id)
    except ifixit.FixBotError as e:
        print("\n".join("  " + line for line in textwrap.wrap(to_ascii(str(e)), 76)))
        return
    if not isinstance(guide, dict) or "title" not in guide:
        print("  iFixit sent something unexpected for that guide. Try another.")
        return
    try:
        read(guide)
    except (KeyError, TypeError, ValueError, AttributeError):
        print("\n  iFixit sent something unexpected in that guide. Try another.")


def main():
    print("\n  IFIXIT REPAIR GUIDES")
    print("  Read a step at a time, with its photos on the Compaq's screen.")
    # "guides.py GUIDE-ID": PAL found the guide (it looked at a device).
    if len(sys.argv) > 1 and sys.argv[1].isdecimal():
        show(sys.argv[1])
    while True:
        print()
        query = input("  Search for (like: Compaq floppy drive), or Enter to leave: ").strip()
        if not query:
            return
        try:
            results = ifixit.search(query)[:15]
        except ifixit.FixBotError as e:
            print("\n".join("  " + line for line in textwrap.wrap(to_ascii(str(e)), 76)))
            continue
        if not isinstance(results, list):
            results = []
        results = [r for r in results if isinstance(r, dict) and "id" in r]
        if not results:
            print("  No guides found. Try fewer or different words.")
            continue

        print()
        for i, result in enumerate(results, 1):
            print(f"  {i:>2}. {to_ascii(str(result.get('title', '?')))[:72]}")
        print()
        choice = input("  Guide number (Enter to search again): ").strip()
        if not choice.isdecimal() or len(choice) > 3 or not 1 <= int(choice) <= len(results):
            continue

        show(results[int(choice) - 1]["id"])


if __name__ == "__main__":
    try:
        main()
    except (EOFError, KeyboardInterrupt):
        print()

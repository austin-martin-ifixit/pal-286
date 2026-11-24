#!/usr/bin/env python3
"""Web search on the Compaq: a search in, ten results out, and any of them
read in Lynx (or, with P, seen as a picture of the real page, squashed into
text art by a browser on the Pi).

The results come from DuckDuckGo's page for text-only browsers. (Google has
no search service a program like this may use: its search API is closed to
newcomers and ends in January 2027, and its own pages turn away robots.) If
that page doesn't answer, PAL looks it up instead, with Claude's web search.

Usage: websearch.py [SEARCH]   (given a search, it's typed in as if by PAL)
"""

import html.parser
import http.client
import json
import os
import shutil
import signal
import socket
import subprocess
import sys
import textwrap
import time
import urllib.parse
import urllib.request
try:
    import readline  # noqa: F401  (line editing for the search box)
except ImportError:
    pass

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pictures  # noqa: E402
from chat import to_ascii  # noqa: E402

AGENT = "CompaqPortableIII/1.0 (a text-only web browser on a Raspberry Pi)"
PAL_SOCKET = "/run/compaq-pal/pal.sock"
SNAPSHOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "snapshot.py")
PER_SCREEN = 5
COLS = 79


class Results(html.parser.HTMLParser):
    """The results on DuckDuckGo's text-only page: a link (class
    result-link), then its snippet (class result-snippet)."""

    def __init__(self):
        super().__init__()
        self.found, self.into = [], None

    def handle_starttag(self, tag, attrs):
        attrs = dict(attrs)
        if tag == "a" and "result-link" in (attrs.get("class") or ""):
            self.found.append({"title": "", "url": real_address(attrs.get("href", "")), "snippet": ""})
            self.into = "title"
        elif tag == "td" and "result-snippet" in (attrs.get("class") or "") and self.found:
            self.into = "snippet"

    def handle_endtag(self, tag):
        if (tag == "a" and self.into == "title") or (tag == "td" and self.into == "snippet"):
            self.into = None

    def handle_data(self, data):
        if self.into and self.found:
            self.found[-1][self.into] += data


def real_address(href):
    """DuckDuckGo's links go through a redirect: the address it leads to."""
    parts = urllib.parse.urlparse(urllib.parse.urljoin("https://duckduckgo.com/", href))
    if parts.netloc.endswith("duckduckgo.com"):
        target = urllib.parse.parse_qs(parts.query).get("uddg")
        return target[0] if target else ""        # (an advert, or something odd: skipped)
    return urllib.parse.urlunparse(parts)


def duckduckgo(query):
    """Results from DuckDuckGo's text-only page, asked the way its own search
    box asks (a form, posted). If it ever answers with a robot check, that's
    left alone: PAL's search fills in."""
    request = urllib.request.Request("https://lite.duckduckgo.com/lite/",
                                     data=urllib.parse.urlencode({"q": query}).encode(),
                                     headers={"User-Agent": AGENT})
    with urllib.request.urlopen(request, timeout=15) as response:
        if response.status != 200:
            return []
        page = response.read(500_000).decode("utf-8", "replace")
    # (A robot check has no results on it, so nothing comes of it.)
    parser = Results()
    parser.feed(page)
    return [r for r in parser.found if r["url"].startswith(("http://", "https://"))]


def ask_pal(query):
    """The same search done by PAL (Claude's web search), if DuckDuckGo fails."""
    with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
        s.settimeout(60)
        s.connect(PAL_SOCKET)
        s.sendall((json.dumps({"op": "search", "query": query}) + "\n").encode())
        answer = json.loads(s.makefile().readline() or "{}")
    if not isinstance(answer, dict) or not answer.get("ok"):
        raise OSError(answer.get("message", "PAL couldn't search.") if isinstance(answer, dict)
                      else "PAL couldn't search.")
    found = []
    for result in answer.get("results") or []:       # (only what a result should be, web links only)
        if isinstance(result, dict) and str(result.get("url", "")).startswith(("http://", "https://")):
            found.append({"title": str(result.get("title") or result["url"]), "url": str(result["url"]),
                          "snippet": str(result.get("snippet") or "")})
    return found


def search(query):
    """Results for query, from wherever answers; (results, where from)."""
    try:
        found = duckduckgo(query)
        if found:
            return found, "DuckDuckGo"
    except (OSError, ValueError, http.client.HTTPException):    # (offline, or cut off part-way)
        pass
    try:
        return ask_pal(query), "PAL"
    except (OSError, ValueError, http.client.HTTPException) as e:
        print(f"\n  The search didn't work ({to_ascii(str(e))[:60]}). Try again in a minute.")
        return [], ""


def clean(text, limit):
    return " ".join(to_ascii(text).split())[:limit]


def header(query, typed=False):
    print("\033[H\033[2J", end="")
    print("  W E B   S E A R C H" + "the 2026 internet, via the Pi".rjust(COLS - 23))
    print("  Search: ", end="", flush=True)
    if typed:
        for c in query:                       # PAL typing it in
            print(c, end="", flush=True)
            time.sleep(0.07)
        print()
    else:
        print(query[:COLS - 13])
    print("  " + "-" * (COLS - 4))


def show(query, results, start, source):
    header(query)
    for n, r in enumerate(results[start:start + PER_SCREEN], start + 1):
        print(f"  {n:>2}. {clean(r['title'], COLS - 7)}")
        snippet = textwrap.shorten(clean(r.get("snippet", ""), 300), COLS - 7, placeholder="...")
        print(f"      {snippet}")
        host = urllib.parse.urlparse(r["url"])
        print(f"      {clean(host.netloc + host.path, COLS - 7)}")
    shown = min(len(results), start + PER_SCREEN)
    more = "  M: more." if shown < len(results) else ""
    picture = "  P1: see it." if shutil.which("chromium-headless-shell") else ""
    print(f"\n  {start + 1}-{shown} of {len(results)}, from {source}.{more}")
    return input(f"  A number: read it.{picture}  L1: phone link.  S: search.  Enter: done. ").strip().lower()


def run(command):
    """Runs a program on this screen. Ctrl-C belongs to it while it runs
    (it stops a page loading in Lynx): it mustn't also end the search, and
    with it the list of results."""
    old = signal.signal(signal.SIGINT, lambda *_: None)
    try:
        subprocess.run(command)
    finally:
        signal.signal(signal.SIGINT, old)


def read(url):
    """The page in Lynx (plain text, the Compaq's way)."""
    run(["lynx", "-cookies", "-nocolor", "-display_charset=us-ascii", url])


def picture(url):
    """The real page, as the Pi's browser draws it, squashed onto the
    Compaq's screen (dithered pictures, or text art)."""
    run([sys.executable, "-I", SNAPSHOT, url])


def phone(url):
    """A QR code for the page on the Compaq's screen, to open it on a phone."""
    print("\n  Point a phone's camera at the Compaq's screen.")
    try:
        pictures.show(pictures.qr(url), "Scan to open this on your phone",
                      told=pictures.saying("a QR code", more=False))
    except pictures.NotShown as e:
        print(f"  {e}")
        input("  Press Enter. ")


def main():
    query = clean(" ".join(sys.argv[1:]), 200)
    typed = bool(query)
    while True:
        if not query:
            print("\033[H\033[2J", end="")
            print("  W E B   S E A R C H" + "the 2026 internet, via the Pi".rjust(COLS - 23))
            print("\n  Type what to search for, then press Enter (just Enter: back).\n")
            query = clean(input("  Search: "), 200)
            if not query:
                return
        header(query, typed)
        typed = False
        print("\n  Searching the information superhighway...", flush=True)
        results, source = search(query)
        if not results:
            input("\n  Nothing found. Press Enter to search again. ")
            query = ""
            continue
        start = 0
        while True:
            choice = show(query, results, start, source)
            if choice == "m" and start + PER_SCREEN < len(results):
                start += PER_SCREEN
            elif choice == "s":
                query = ""
                break
            elif len(choice) > 4:                     # (a held-down key, say: not a choice)
                continue
            elif choice.isdigit() and 1 <= int(choice) <= len(results):
                read(results[int(choice) - 1]["url"])
            elif choice.startswith("p") and choice[1:].strip().isdigit() \
                    and 1 <= int(choice[1:]) <= len(results) and shutil.which("chromium-headless-shell"):
                picture(results[int(choice[1:]) - 1]["url"])
            elif choice.startswith("l") and choice[1:].strip().isdigit() \
                    and 1 <= int(choice[1:]) <= len(results):
                phone(results[int(choice[1:]) - 1]["url"])
            elif not choice:
                return


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print()

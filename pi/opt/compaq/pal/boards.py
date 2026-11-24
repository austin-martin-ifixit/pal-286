"""Game boards PAL puts on the Compaq's screen (22 rows of plain ASCII, for
the serial bridge's canvas; PAL's words scroll along the two rows below).

The lobby quiz: each question with its choices and the score, then the
final score with a title to brag about.
"""

import textwrap
import unicodedata

WIDTH = 79


def plain(text, limit=400):
    text = unicodedata.normalize("NFKD", str(text or ""))
    return " ".join("".join(c for c in text if " " <= c <= "~").split())[:limit]


def centred(text):
    return f"{text[:WIDTH]:^{WIDTH}}".rstrip()


def banner(title):
    return centred("*  *  *   " + "  ".join(title.upper()) + "   *  *  *")


def quiz(question, choices, number=0, total=0, score=0, topic=""):
    rows = ["", banner("lobby quiz"), ""]
    left = f"QUESTION {number} OF {total}" if number and total else "QUESTION"
    if topic:
        left += f"  -  {plain(topic, 30).upper()}"
    right = f"SCORE: {score}"
    rows.append(f"   {left}{right:>{WIDTH - 6 - len(left)}}")
    rows.append("   " + "-" * (WIDTH - 6))
    rows.append("")
    asked = textwrap.wrap(plain(question), WIDTH - 10)[:4]
    rows += ["     " + line for line in asked] + [""] * (4 - len(asked))
    rows.append("")
    options = []
    for letter, choice in zip("ABCD", choices[:4]):
        lines = textwrap.wrap(plain(choice, 120), WIDTH - 16)[:2] or [""]
        options.append([f"       {letter})  {lines[0]}"] + [f"            {line}" for line in lines[1:]])
    # A blank row between choices, if there's room for every one of them.
    spaced = sum(len(o) + 1 for o in options) <= 20 - len(rows)
    for option in options:
        rows += option + ([""] if spaced else [])
    while len(rows) < 21:
        rows.append("")
    rows = rows[:20] + [centred("Say the letter, or the answer.")]
    return rows + [""]


def final(score, total, title=""):
    rows = ["", banner("lobby quiz"), "", "", "", centred("F I N A L   S C O R E"), "", ""]
    rows.append(centred(f"{score}   OUT OF   {total}"))
    rows += ["", "", ""]
    if title:
        rows.append(centred(plain(title, 70).upper()))
    while len(rows) < 21:
        rows.append("")
    return rows[:20] + [centred("(C) 1987 PAL SOFTWARE.  ALL RIGHTS RESERVED."), ""]

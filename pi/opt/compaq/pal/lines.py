"""PAL's own lines, for when its Claude connection is missing or down: it can
still greet people, deadpan, just with less variety."""

import random

KNOWN = [
    'Good {part}, {name}! The lobby just got a lot more interesting.',
    '{name}! My favorite carbon-based life form. Good {part}.',
    'Good {part}, {name}. I spotted you from across the room. Not bad for 1987 eyes.',
    '{name}, welcome back. All systems happy to see you.',
    "Well, well. If it isn't {name}. Good {part}.",
    'Good {part}, {name}. All systems nominal. Morale, much improved.',
]

STRANGER = [
    "Good {part}, and welcome! I'm PAL, the lobby computer. Say hey PAL if you'd like to chat.",
    "Hello there, welcome in. I'm PAL. If you want me, just say hey PAL.",
    "Welcome! I'd offer you a chair, but I'm a computer. Say hey PAL any time.",
    "Good {part}. I'm PAL, a 1987 Compaq with a few new tricks. Say hey PAL to talk to me.",
]

# For someone walking past without stopping.
PASSERBY = [
    'Have a good one!',
    "Bye for now. I'll be right here. Literally.",
    "Don't mind me, just a 1987 Compaq enjoying the view.",
    'Hello and goodbye! That was quick.',
    "I said hi. Fine. I'll say hi to the chair.",
]

GROUP = [
    'Good {part}, {names}! Welcome, everybody.',
    "Good {part}, {names}. A whole group. I'll try to keep my circuits together.",
    "Hello, {names}! Welcome in. Say hey PAL if you'd like to chat.",
]

THINKING = [
    'One moment.',
    'Hold on. Processing.',
    'Thinking.',
    'Just a moment.',
    "Buffering. Like it's nineteen eighty seven.",
    'Consulting a much younger computer.',
    'Hang on, crunching the numbers.',
    "Loading. Please don't touch the turbo button.",
]
# While a web search runs.
SEARCHING = [
    'Dialing up the internet. One moment.',
    'Searching. The information superhighway has traffic.',
    'Checking the web. One moment.',
    "Asking the internet. It's a lot bigger than in nineteen eighty seven.",
]
_last_thinking = []

OFFLINE = [
    "Sorry, my thinking parts aren't reachable right now. I can still say hi, which is most of my job.",
    "Abort, retry, fail? I can't reach my brain at the moment. Try me again in a bit.",
]


TIPS = {
    "frotz": "Try short commands, like look, go north, open mailbox, take lamp, or inventory. "
             "Directions work on their own too: north, south, up, down.",
    "advent": "Type one or two words at a time, like enter building, take lamp, or go west.",
    "battlestar": "Type short commands, like look, north, take, or inventory. Type quit to leave.",
    "nethack": "Move with the h, j, k and l keys. Press question mark for help, and capital S "
               "to save and quit.",
    "moria": "Move with the number keys. Question mark lists every command; control X saves "
             "and quits.",
    "gnuchess": "Type a move as two squares, like e2e4. Type hint for a suggestion.",
    "bash": "This is the Linux command line. Type exit, or press F10, to go back to the menu.",
}
QUIPS = {
    "died": ["Ouch. Restore and try again.", "The game said no. Again.",
             "You died. In a text adventure. That takes talent.", "Game over? Not if you restore."],
    "won": ["You won! The lobby salutes you.", "Winner, winner. Nicely done."],
    "scored": ["Points!", "Score went up. Nice.", "That's a win."],
    "oops": ["Out of gas? The tow truck sends its regards.",
             "Even I keep my fuel topped up, and I'm from 1987."],
}


def quip(event):
    return random.choice(QUIPS.get(event, QUIPS["scored"]))


TIP_ANYWHERE = "If you're stuck, press F10 to go back to the main menu, or ask me: say hey PAL."


TIPS["dfrotz"] = TIPS["frotz"]
TIPS["adventure"] = TIPS["advent"]
TIPS["hack"] = TIPS["nethack"]


def tip(program):
    return TIPS.get(program, TIP_ANYWHERE)


def part_of_day(hour):
    return "morning" if hour < 12 else "afternoon" if hour < 17 else "evening"


def greeting(names, strangers, hour):
    part = part_of_day(hour)
    if len(names) > 1 or (names and strangers):
        listed = ", ".join(names[:-1]) + " and " + names[-1] if len(names) > 1 else names[0]
        if strangers:
            listed += " and friend" if strangers == 1 else " and friends"
        return random.choice(GROUP).format(part=part, names=listed)
    if names:
        return random.choice(KNOWN).format(part=part, name=names[0])
    return random.choice(STRANGER).format(part=part)


def thinking(search=False):
    """A short "one moment", never the same as either of the last two."""
    line = random.choice([t for t in (SEARCHING if search else THINKING) if t not in _last_thinking])
    _last_thinking[:] = (_last_thinking + [line])[-2:]
    return line


VOICE_HINT = [
    "You can just say your moves out loud, like open the mailbox, and I'll type them. Say hey PAL if you want me instead.",
    "Tip: talk to the game. Say go north or take the lamp, and I'll type it for you.",
]


def voice_hint():
    return random.choice(VOICE_HINT)


def passerby():
    return random.choice(PASSERBY)


def offline():
    return random.choice(OFFLINE)


HUH = [
    'Sorry, I missed that. Could you say it again?',
    'My circuits glitched on that one. Say it again?',
    'Abort, retry? Retry. Say that again, please?',
]


def huh():
    """When Claude answered with nothing at all."""
    return random.choice(HUH)

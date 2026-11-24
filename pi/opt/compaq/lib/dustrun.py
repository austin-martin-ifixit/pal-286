#!/usr/bin/env python3
"""DUSTRUN: harvest crystals on the salt flats without waking the burrowers.

An original turn-based game for the Compaq menu: 80x24, keyboard only, plain
ASCII, and frugal with screen updates so it plays well at 9600 baud.
Everyone shares one high-score table (compaq-files/saves/dustrun-scores.json).

Rules in brief: drive the harvester (H) to crystal fields (*), dig with the
space bar, and bring the haul back to base (B) to sell. Engines and digging
make noise; burrowers hunt noise but can't cross rock (#). Five days a season.
"""

import curses
import json
import os
import random
import time

W, H = 120, 40                 # the salt flats
VIEW_W, VIEW_H = 58, 21        # the map window on screen
SIDE = 61                      # sidebar column
DAYS, DAY_TURNS = 5, 160
SCORES = os.path.expanduser("~/compaq-files/saves/dustrun-scores.json")
SAND, DUNE, ROCK, CRYSTAL, BASE = ".", ":", "#", "*", "B"

MOVES = {
    curses.KEY_UP: (0, -1), curses.KEY_DOWN: (0, 1),
    curses.KEY_LEFT: (-1, 0), curses.KEY_RIGHT: (1, 0),
    ord("k"): (0, -1), ord("j"): (0, 1), ord("h"): (-1, 0), ord("l"): (1, 0),
    ord("y"): (-1, -1), ord("u"): (1, -1), ord("b"): (-1, 1), ord("n"): (1, 1),
    ord("8"): (0, -1), ord("2"): (0, 1), ord("4"): (-1, 0), ord("6"): (1, 0),
    ord("7"): (-1, -1), ord("9"): (1, -1), ord("1"): (-1, 1), ord("3"): (1, 1),
}

# The title, in figlet's "standard" letters.
LETTERS = {
    "D": [" ____  ", "|  _ \\ ", "| | | |", "| |_| |", "|____/ "],
    "U": [" _   _ ", "| | | |", "| | | |", "| |_| |", " \\___/ "],
    "S": [" ____  ", "/ ___| ", "\\___ \\ ", " ___) |", "|____/ "],
    "T": [" _____ ", "|_   _|", "  | |  ", "  | |  ", "  |_|  "],
    "R": [" ____  ", "|  _ \\ ", "| |_) |", "|  _ < ", "|_| \\_\\"],
    "N": [" _   _ ", "| \\ | |", "|  \\| |", "| |\\  |", "|_| \\_|"],
}
TITLE = ["".join(LETTERS[c][row] for c in "DUSTRUN").rstrip() for row in range(5)]

SHOP = [  # key, name, base price, what it does
    ("1", "Bigger hold", 300, "+10 crystal capacity (dearer each time)"),
    ("2", "Quiet treads", 400, "driving makes less noise (once)"),
    ("3", "Long-range sensor", 250, "see burrowers 4 squares further (once)"),
    ("4", "Decoy beacon", 60, "drop with D; lures burrowers for 20 hours"),
    ("5", "Spare harvester", 600, "another life"),
]

HELP = """\
HOW TO PLAY

You run a crystal harvester on the salt flats. Dig crystals (*), haul them
back to base (B) and sell them. The price changes every day.

The catch: burrowers live under the sand. They hunt by sound, and they
can't cross rock (#). Driving makes noise, dunes (:) more so, and digging
most of all. Watch the noise bar and the tremor warning; ripples (~) show
burrowers your sensor can pick up. Park on rock to be safe.

Fuel runs down as you drive and dig; base refuels you (1 credit a unit).
Run dry and the tow costs 100 credits and your cargo. Lose a harvester to
a burrower and you lose its cargo too. At base, press S for the shop.

KEYS   arrows, hjkl or the number pad: move (yubn / 7913 diagonally)
       space: dig     . : wait a turn     d: drop a decoy beacon
       s: shop (at base)     ?: this help     q: quit

Five days make a season. Score = credits at the end of day five."""


def chebyshev(ax, ay, bx, by):
    return max(abs(ax - bx), abs(ay - by))


class Game:
    def __init__(self, seed=None):
        self.rng = random.Random(seed)
        self.make_map()
        self.day, self.turn = 1, 0
        self.credits, self.price = 200, 12
        self.hold, self.cargo = 20, 0
        self.tank = self.fuel = 120
        self.harvesters, self.decoys = 3, 1
        self.quiet, self.sensor = False, 6
        self.hold_upgrades = 0
        self.noise = 0
        self.decoy = None              # [x, y, hours left]
        self.worms = []
        self.px, self.py = self.base
        self.message = "Welcome to the salt flats. Press ? for help."
        self.over = False
        self.dug = 0
        self.start_day()

    # ------------------------------------------------------------- world

    def make_map(self):
        r = self.rng
        g = self.grid = [[SAND] * W for _ in range(H)]
        for _ in range(60):            # dune ridges
            x, y = r.randrange(W), r.randrange(H)
            for _ in range(r.randint(10, 40)):
                g[y][x] = DUNE
                x = min(W - 1, max(0, x + r.choice((-1, 0, 1, 1))))
                y = min(H - 1, max(0, y + r.choice((-1, 0, 0, 1))))
        for _ in range(20):            # rock outcrops: safe ground
            cx, cy = r.randrange(W), r.randrange(H)
            for _ in range(r.randint(4, 14)):
                x = min(W - 1, max(0, cx + r.randint(-3, 3)))
                y = min(H - 1, max(0, cy + r.randint(-1, 1)))
                g[y][x] = ROCK
        self.crystals = {}
        for _ in range(28):            # crystal fields
            cx, cy = r.randrange(4, W - 4), r.randrange(2, H - 2)
            for _ in range(r.randint(3, 9)):
                x, y = cx + r.randint(-3, 3), cy + r.randint(-1, 1)
                if g[y][x] in (SAND, DUNE):
                    g[y][x] = CRYSTAL
                    self.crystals[(x, y)] = r.randint(2, 6)
        bx, by = W // 2, H // 2
        for y in range(by - 1, by + 2):
            for x in range(bx - 3, bx + 4):
                g[y][x] = ROCK
                self.crystals.pop((x, y), None)
        g[by][bx] = BASE
        self.base = (bx, by)

    def passable_for_worm(self, x, y):
        return 0 <= x < W and 0 <= y < H and self.grid[y][x] not in (ROCK, BASE)

    def far_spot(self):
        while True:
            x, y = self.rng.randrange(W), self.rng.randrange(H)
            if self.passable_for_worm(x, y) and chebyshev(x, y, *self.base) > 22:
                return [x, y]

    def start_day(self):
        self.turn = 0
        self.price = self.rng.randint(9, 16)
        self.px, self.py = self.base
        self.fuel = self.tank
        self.noise = 0
        self.decoy = None
        wanted = self.day + 1          # two burrowers on day one, then more
        self.worms = [self.far_spot() for _ in range(wanted)]

    # ------------------------------------------------------------- turns

    def act(self, key):
        """Handles one key. Returns True if it used up a turn."""
        if key in MOVES:
            return self.drive(*MOVES[key])
        if key == ord(" "):
            return self.dig()
        if key in (ord("."), ord("w")):
            self.message = "You wait, engine idling."
            self.end_turn(0)
            return True
        if key in (ord("d"), ord("D")):
            return self.drop_decoy()
        return False

    def drive(self, dx, dy):
        x, y = self.px + dx, self.py + dy
        if not (0 <= x < W and 0 <= y < H):
            self.message = "That's the edge of the survey area."
            return False
        tile = self.grid[y][x]
        cost = 2 if tile == DUNE else 1
        if self.fuel == 0:
            self.stranded()
            return True
        if self.fuel < cost:
            if self.boxed_in():
                self.stranded()     # dunes all round and too little fuel: towed home
                return True
            self.message = "Not enough fuel to climb that dune. Go around it."
            return False
        self.fuel -= cost
        self.px, self.py = x, y
        noise = (1 if self.quiet else 2) + (1 if tile == DUNE else 0)
        self.message = {DUNE: "Climbing a dune: slow and loud.",
                        ROCK: "Rock underfoot. Burrowers can't reach you here.",
                        CRYSTAL: f"Crystals here ({self.crystals.get((x, y), 0)} left). Space digs.",
                        }.get(tile, "")
        if tile == BASE:
            self.at_base()
            noise = 0
        self.end_turn(noise)
        return True

    def boxed_in(self):
        """True if every square around is a dune (or the edge)."""
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                x, y = self.px + dx, self.py + dy
                if (dx or dy) and 0 <= x < W and 0 <= y < H and self.grid[y][x] != DUNE:
                    return False
        return True

    def dig(self):
        here = (self.px, self.py)
        if here not in self.crystals:
            self.message = "Nothing to dig here."
            return False
        if self.cargo >= self.hold:
            self.message = "The hold is full. Head back to base."
            return False
        if self.fuel < 1:
            self.stranded()
            return True
        amount = min(self.rng.randint(1, 3), self.crystals[here], self.hold - self.cargo)
        self.cargo += amount
        self.dug += amount
        self.crystals[here] -= amount
        self.fuel -= 1
        if self.crystals[here] <= 0:
            del self.crystals[here]
            self.grid[self.py][self.px] = SAND
            self.message = f"Dug {amount}. That field is worked out."
        else:
            self.message = f"Dug {amount} crystal{'s' if amount > 1 else ''}. The drill is loud!"
        self.end_turn(4)
        return True

    def drop_decoy(self):
        if self.decoys < 1:
            self.message = "No decoy beacons left. Buy some at base."
            return False
        self.decoys -= 1
        self.decoy = [self.px, self.py, 20]
        self.message = "Decoy beacon dropped. It thumps away for 20 hours."
        self.end_turn(0)
        return True

    def at_base(self):
        earned = self.cargo * self.price
        self.credits += earned
        need = self.tank - self.fuel
        bought = min(need, self.credits)
        self.credits -= bought
        self.fuel += bought
        parts = []
        if self.cargo:
            parts.append(f"Sold {self.cargo} for {earned} cr.")
        if bought:
            parts.append(f"Refuelled ({bought} cr).")
        parts.append("Press S for the shop.")
        self.cargo = 0
        self.message = " ".join(parts)

    def stranded(self):
        self.message = "Out of fuel! The tow costs 100 cr and your cargo."
        self.credits = max(0, self.credits - 100)
        self.cargo = 0
        self.px, self.py = self.base
        self.fuel = self.tank
        self.end_turn(0)

    def end_turn(self, action_noise):
        self.turn += 1
        # Noise fades by 2 a turn, so steady driving holds near 2 (1 with
        # quiet treads) while dunes and digging push it up.
        self.noise = min(10, max(0, self.noise - 2) + action_noise)
        if self.decoy:
            self.decoy[2] -= 1
            if self.decoy[2] <= 0:
                self.decoy = None
        self.move_worms()
        if any(w == [self.px, self.py] for w in self.worms):
            self.lose_harvester()
        if self.turn >= DAY_TURNS and not self.over:
            self.day_over = True

    def move_worms(self):
        for w in self.worms:
            target = None
            if self.decoy and chebyshev(*w, *self.decoy[:2]) <= 30:
                target = self.decoy[:2]
            elif self.noise >= 2 and chebyshev(*w, self.px, self.py) <= 4 + 3 * self.noise:
                target = [self.px, self.py]
            if target:
                # Never onto rock, not even to reach the target: rock is safe ground.
                options = [(w[0] + dx, w[1] + dy) for dx in (-1, 0, 1) for dy in (-1, 0, 1)
                           if self.passable_for_worm(w[0] + dx, w[1] + dy)]
                if not options:
                    continue
                best = min(chebyshev(*o, *target) for o in options)
                w[0], w[1] = self.rng.choice([o for o in options if chebyshev(*o, *target) == best])
            elif self.rng.random() < 0.5:
                dx, dy = self.rng.randint(-1, 1), self.rng.randint(-1, 1)
                if self.passable_for_worm(w[0] + dx, w[1] + dy):
                    w[0] += dx
                    w[1] += dy
            if self.decoy and w == self.decoy[:2]:
                self.decoy = None
                self.message = "A burrower swallowed your decoy beacon."

    def lose_harvester(self):
        self.harvesters -= 1
        lost = self.cargo
        self.cargo = 0
        for w in self.worms:
            if w == [self.px, self.py]:
                w[:] = self.far_spot()
        if self.harvesters <= 0:
            self.message = "A burrower took your last harvester."
            self.over = True
            return
        # (it must fit the one message line: the advice is the point)
        self.message = (f"Harvester lost{f' with {lost} crystals' if lost else ''}! "
                        "A spare rolls out. Hide on rock (#) sooner.")
        self.px, self.py = self.base
        self.fuel = self.tank
        self.noise = 0

    def nearest_worm(self):
        return min((chebyshev(*w, self.px, self.py) for w in self.worms), default=99)

    def buy(self, key):
        for k, name, price, _ in SHOP:
            if key != ord(k):
                continue
            if k == "1":
                price += 150 * self.hold_upgrades
            if (k == "2" and self.quiet) or (k == "3" and self.sensor > 6):
                return f"You already have {name.lower()}."
            if self.credits < price:
                return f"{name} costs {price} cr. You have {self.credits}."
            self.credits -= price
            if k == "1":
                self.hold += 10
                self.hold_upgrades += 1
            elif k == "2":
                self.quiet = True
            elif k == "3":
                self.sensor += 4
            elif k == "4":
                self.decoys += 1
            elif k == "5":
                self.harvesters += 1
            return f"Bought: {name}."
        return ""


# ----------------------------------------------------------------- screens

class Screen:
    MARGIN = 6   # scroll the map only when the harvester gets this close to an edge

    def __init__(self, scr):
        self.scr = scr
        self.vx = self.vy = None
        curses.noecho()
        curses.cbreak()
        scr.keypad(True)
        try:
            curses.curs_set(0)
        except curses.error:
            pass

    def put(self, y, x, text, attr=0):
        try:
            self.scr.addstr(y, x, text[:max(0, 80 - x)], attr)
        except curses.error:   # writing the bottom-right corner
            pass

    KEYPAD = {ord(c): ord(d) for c, d in zip("pqrstuvwxy", "0123456789")}
    KEYPAD[ord("M")] = 10   # keypad Enter

    def key(self):
        """One key. Number-pad keys arrive as ESC O <letter> in application
        keypad mode (tmux sets it), so those become plain digits here."""
        key = self.scr.getch()
        if key != 27:
            return key
        self.scr.timeout(60)
        try:
            second = self.scr.getch()
            if second == ord("["):
                # A key curses doesn't know (Shift and an arrow from a
                # browser, say): all of it is one key that does nothing,
                # not an Esc and then its digits as moves.
                for _ in range(16):
                    last = self.scr.getch()
                    if last == -1 or 0x40 <= last <= 0x7e:
                        break
                return -1
            if second != ord("O"):
                if second != -1:
                    curses.ungetch(second)
                return 27
            third = self.scr.getch()
            return self.KEYPAD.get(third, 27)
        finally:
            self.scr.timeout(-1)

    def page(self, lines, footer="Press any key."):
        self.scr.erase()
        for i, line in enumerate(lines[:22]):
            self.put(i, 0, line)
        self.put(23, 0, footer, curses.A_REVERSE)
        self.scr.refresh()
        return self.key()

    def draw(self, g):
        s = self.put
        self.scr.erase()
        s(0, 0, " DUSTRUN".ljust(56) + "? help   q quit ".rjust(24), curses.A_REVERSE)
        # Re-centre only near an edge: shifting the whole map costs over a
        # second at 9600 baud, while a normal move changes a few characters.
        if (self.vx is None or not self.MARGIN <= g.px - self.vx < VIEW_W - self.MARGIN
                or not self.MARGIN // 2 <= g.py - self.vy < VIEW_H - self.MARGIN // 2):
            self.vx = min(max(0, g.px - VIEW_W // 2), W - VIEW_W)
            self.vy = min(max(0, g.py - VIEW_H // 2), H - VIEW_H)
        vx, vy = self.vx, self.vy
        visible = {tuple(w) for w in g.worms if chebyshev(*w, g.px, g.py) <= g.sensor}
        for row in range(VIEW_H):
            y = vy + row
            line = "".join("~" if (x, y) in visible else g.grid[y][x]
                           for x in range(vx, vx + VIEW_W))
            s(row + 1, 0, line)
        if g.decoy and vx <= g.decoy[0] < vx + VIEW_W and vy <= g.decoy[1] < vy + VIEW_H:
            s(g.decoy[1] - vy + 1, g.decoy[0] - vx, "!", curses.A_BOLD)
        bx, by = g.base
        if vx <= bx < vx + VIEW_W and vy <= by < vy + VIEW_H and (bx, by) != (g.px, g.py):
            s(by - vy + 1, bx - vx, BASE, curses.A_BOLD)
        s(g.py - vy + 1, g.px - vx, "H", curses.A_REVERSE)
        for row in range(1, VIEW_H + 1):
            s(row, VIEW_W + 1, "|")

        near = g.nearest_worm()
        tremor = ("DANGER!" if near <= 2 else "close" if near <= 5 else
                  "faint" if near <= 9 else "none")
        noise = "#" * g.noise + "-" * (10 - g.noise)
        stats = [
            f"DAY {g.day} of {DAYS}",
            f"Hour {g.turn} of {DAY_TURNS}",
            "",
            f"Credits {g.credits:>8}",
            f"Crystal  @{g.price:>3} cr",
            "",
            f"Cargo   {g.cargo:>3}/{g.hold}",
            f"Fuel    {g.fuel:>3}/{g.tank}",
            f"Harvesters  {g.harvesters:>3}",
            f"Decoys      {g.decoys:>3}",
            "",
            f"Noise [{noise}]",
            f"Tremors: {tremor}",
        ]
        extras = [name for flag, name in ((g.quiet, "quiet treads"), (g.sensor > 6, "long sensor")) if flag]
        if extras:
            stats += ["", "Fitted:"] + [f" {name}" for name in extras]
        # Every line is padded to full width, overwriting the last frame, so
        # curses sends only the characters that actually changed.
        for row in range(1, VIEW_H + 1):
            line = stats[row - 2] if 0 <= row - 2 < len(stats) else ""
            attr = curses.A_BOLD if line.startswith("Tremors") and near <= 2 else 0
            s(row, SIDE - 1, f" {line:<18}", attr)
        s(22, 0, g.message[:79].ljust(79))
        s(23, 0, "Move: arrows/hjkl  Dig: space  Wait: .  Decoy: d  Shop at base: s")
        self.scr.refresh()

    def shop(self, g):
        note = ""
        while True:
            lines = ["", "  BASE SUPPLY DEPOT", "",
                     f"  Credits: {g.credits}", ""]
            for k, name, price, what in SHOP:
                if k == "1":
                    price += 150 * g.hold_upgrades
                lines.append(f"  {k}.  {name:<18} {price:>4} cr   {what}")
            lines += ["", f"  {note}"]
            key = self.page(lines, "Press 1-5 to buy, or any other key to leave.")
            if not ord("1") <= key <= ord("5"):
                return
            note = g.buy(key)

    def ask_name(self):
        self.put(21, 2, "Your name for the high scores: ")
        curses.echo()
        try:
            curses.curs_set(1)
        except curses.error:
            pass
        raw = self.scr.getstr(21, 33, 12)
        curses.noecho()
        try:
            curses.curs_set(0)
        except curses.error:
            pass
        name = "".join(c for c in raw.decode("ascii", "ignore") if c.isprintable()).strip()
        return name or "Anonymous"


def load_scores():
    """The shared score table. Anyone at the command line can edit the file,
    so only entries that are what a score should be count."""
    try:
        with open(SCORES, errors="replace") as f:
            scores = json.load(f)
    except (OSError, ValueError):
        return []
    if not isinstance(scores, list):
        return []
    return [{"name": str(s.get("name", "?"))[:12], "score": s["score"], "days": s.get("days", 0),
             "date": str(s.get("date", ""))[:10]}
            for s in scores if isinstance(s, dict) and type(s.get("score")) is int]


def save_score(name, score, day):
    scores = load_scores()
    scores.append({"name": name, "score": score, "days": day,
                   "date": time.strftime("%Y-%m-%d")})
    scores.sort(key=lambda s: -s["score"])
    os.makedirs(os.path.dirname(SCORES), exist_ok=True)
    tmp = SCORES + ".new"
    with open(tmp, "w") as f:
        json.dump(scores[:10], f, indent=1)
    os.replace(tmp, SCORES)


def score_lines():
    scores = load_scores()
    lines = ["", "  HIGH SCORES (shared by everyone at the office)", ""]
    if not scores:
        lines.append("  No scores yet. Be the first.")
    for i, s in enumerate(scores, 1):
        lines.append(f"  {i:>2}.  {s['name']:<12}  {s['score']:>7} cr   {s['date']}")
    return lines


def rating(score):
    for limit, title in ((4000, "Crystal Baron"), (2500, "Flats Veteran"),
                         (1200, "Prospector"), (0, "Sand Rat")):
        if score >= limit:
            return title


def play(scr):
    ui = Screen(scr)
    if curses.LINES < 24 or curses.COLS < 80:
        ui.page(["DUSTRUN needs an 80x24 screen."])
        return
    while True:
        key = ui.page(["", ""] + ["  " + line for line in TITLE] + [
            "",
            "  Harvest crystals on the salt flats of Kesh, and keep quiet:",
            "  the burrowers under the sand hunt anything that makes noise.",
            "",
            "  Drive the H with the arrow keys. Stop on a crystal (*) and press Space",
            "  to dig, then drive back to base (B) to sell. Noise wakes burrowers:",
            "  when Tremors says close, get onto rock (#) and wait (.) till it fades.",
        ], "Enter: play    S: high scores    ?: how to play    Q: quit")
        if key in (ord("q"), ord("Q"), 27):
            return
        if key in (ord("s"), ord("S")):
            ui.page(score_lines())
            continue
        if key == ord("?"):
            ui.page(HELP.splitlines())
            continue
        if key in (10, 13, curses.KEY_ENTER):
            ui.vx = ui.vy = None
            run(ui, Game())


def run(ui, g):
    g.day_over = False
    while True:
        ui.draw(g)
        key = ui.key()
        if key in (ord("q"), ord("Q")):
            if ui.page(["", "  Quit this season? Your score won't be saved.", "",
                        "  Y: yes, quit    any other key: keep playing"]) in (ord("y"), ord("Y")):
                return
            continue
        if key == ord("?"):
            ui.page(HELP.splitlines())
            continue
        if key in (ord("s"), ord("S")):
            if (g.px, g.py) == g.base:
                ui.shop(g)
            else:
                g.message = "The shop is at base (B)."
            continue
        g.act(key)
        if g.over:
            break
        if g.day_over:
            late = g.cargo * g.price // 2
            g.credits += late
            summary = ["", f"  END OF DAY {g.day}", "",
                       f"  Credits: {g.credits}"]
            if g.cargo:
                summary.append(f"  Cargo still aboard sold at half price: {late} cr")
            g.cargo = 0
            g.day_over = False
            if g.day >= DAYS:
                ui.page(summary, "Press any key to see how the season went.")
                break
            g.day += 1
            g.start_day()
            summary += ["", f"  Day {g.day}: crystals sell for {g.price} cr.",
                        f"  {g.day + 1} burrowers are out there now."]
            ui.page(summary, "Press any key to start the day.")
    ui.scr.erase()
    lines = ["", "  SEASON OVER" if not g.over else "  GAME OVER", "",
             f"  Final credits: {g.credits}",
             f"  Crystals dug:  {g.dug}",
             f"  Rating:        {rating(g.credits)}", ""]
    for i, line in enumerate(lines):
        ui.put(i, 0, line)
    ui.scr.refresh()
    name = ui.ask_name()
    save_score(name, g.credits, g.day)
    ui.page(score_lines())


def main():
    try:
        curses.wrapper(play)
    except KeyboardInterrupt:
        pass


if __name__ == "__main__":
    main()

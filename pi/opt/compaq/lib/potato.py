#!/usr/bin/env python3
"""PotatoTube: YouTube on the Compaq, in the worst quality ever offered.

The Pi fetches the smallest version YouTube has (144p video, about 80
kilobits a second), squashes every frame into text art at a few frames a
second (one a second when the real Compaq's cable runs at 9600 baud: about
all Kermit's terminal can take), and PAL plays the sound through the lobby
speaker. The worse it looks, the better.

Each video can be watched two ways, asked once it's picked: in characters
(the classic: text art) or in HD, the same potato in real dots: each frame
dithered to 320x200 amber dots and sent through PILINK, the Compaq's fast
picture program, as fast as the cable carries what changed (6 to 9 frames a
second at 115200 baud). HD needs PILINK on the Compaq (or the TV standing
in); without it there's no question, just characters.

Usage: potato.py [--hd] [SEARCH]   (with a search, the top result plays after
a short countdown, in HD with --hd; any key picks from the list instead)
"""

import glob
import json
import os
import select
import shutil
import signal
import socket
import subprocess
import sys
import tempfile
import termios
import time
import tty
try:
    import readline  # noqa: F401  (line editing for the search box)
except ImportError:
    pass

import numpy as np

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import pictures  # noqa: E402
from chat import to_ascii  # noqa: E402

YTDLP = "/opt/compaq-net/venv/bin/yt-dlp"
# QuickJS answers YouTube's JavaScript checks (the usual engine, Deno, has no
# build for the Pi's 32-bit system).
YTDLP_ARGS = ["--js-runtimes", "quickjs", "--ignore-config", "--no-playlist", "--no-progress",
              "--no-warnings", "-q"]
PAL_SOCKET = os.environ.get("PAL_SOCKET", "/run/compaq-pal/pal.sock")   # (another, for testing)
SOUND_DIR = os.path.expanduser("~/compaq-files/.potato")   # PAL reads the sound from here
LONGEST = 600                    # seconds: longer videos are too much potato
RAMP = " .'`,:;-~+=*xoaO0#%@"    # dark to bright: on the amber plasma, more ink is more glow
TOP, ROWS = 2, 21                # the picture's rows on the screen
COLS = 79
RUNTIME = os.environ.get("COMPAQ_RUNTIME", "/run/compaq-serial")   # the serial bridge's status and speed
HD_FPS = 12                      # frames a second asked of the film for PotatoTube HD (the cable decides)
HD_SLOW = 9000                   # bytes a second: a slower cable gets half the rows, so it still moves


def clean(text, limit):
    return " ".join(to_ascii(str(text)).split())[:limit]


def ytdlp(*args, timeout=120):
    return subprocess.run([YTDLP, *YTDLP_ARGS, *args], capture_output=True, text=True, timeout=timeout)


def find(query):
    """[(id, seconds, title)]: YouTube's top results, not live, not too long."""
    result = ytdlp("--flat-playlist", "--print", "%(id)s\t%(duration)s\t%(title)s", f"ytsearch8:{query}",
                   timeout=60)
    found = []
    for line in result.stdout.splitlines():
        parts = line.split("\t", 2)
        if len(parts) == 3 and parts[1].replace(".", "", 1).isdigit():
            seconds = int(float(parts[1]))
            if seconds <= LONGEST:
                found.append((parts[0], seconds, clean(parts[2], 70)))
    return found


def has_video(path):
    return "video" in subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream=codec_type",
                                      "-of", "csv=p=0", path], capture_output=True, text=True).stdout


def fetch(video, work):
    """Downloads the smallest picture and sound YouTube has, in one go (one
    JavaScript check for both): (video file or None, sound file or None,
    what went wrong)."""
    url = f"https://www.youtube.com/watch?v={video}"
    try:
        # Sound: the video's own language. YouTube dubs many videos into a
        # dozen others, and "the smallest sound" alone can pick, say, the
        # Chinese dub; a dubbed video marks its original track as preferred.
        done = ytdlp("-f", "160/278/worst[vcodec!=none][height<=240],"
                     "ba[language_preference>0][abr<=64]/wa[language_preference>0]/139/249/worstaudio",
                     "-o", os.path.join(work, "%(format_id)s.%(ext)s"), url, timeout=300)
        problem = (done.stderr.strip().splitlines() or [""])[-1]
    except subprocess.TimeoutExpired:
        problem = "YouTube took more than five minutes"
    files = [f for f in glob.glob(os.path.join(work, "*")) if not f.endswith((".part", ".ytdl"))]
    videos = [f for f in files if has_video(f)]
    sounds = [f for f in files if f not in videos]
    return (videos[0] if videos else None), (sounds[0] if sounds else None), problem


def thumbnail(video):
    """The video's thumbnail (a PIL image, its black bars trimmed), or None."""
    try:
        image = pictures.fetch(f"https://i.ytimg.com/vi/{video}/hqdefault.jpg").convert("L")
    except pictures.NotShown:
        return None
    w, h = image.size
    bar = (h - w * 9 // 16) // 2                 # (a wide picture letterboxed to 4:3)
    if bar > 4 and max(image.crop((0, 0, w, bar - 2)).getextrema()[1],
                       image.crop((0, h - bar + 2, w, h)).getextrema()[1]) < 24:
        image = image.crop((0, bar, w, h - bar))
    return image


def size_of(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "v:0", "-show_entries",
                          "stream=width,height", "-of", "csv=p=0", path],
                         capture_output=True, text=True).stdout.strip().split(",")
    try:
        return int(out[0]), int(out[1])
    except (ValueError, IndexError):
        return 192, 144


def fit(width, height):
    """Columns and rows for the picture (a character is twice as tall as wide)."""
    cols = min(COLS, int(ROWS * 2 * width / height))
    rows = min(ROWS, int(cols * height / width / 2))
    return cols - cols % 2, rows


def cable():
    """(frames a second for text art, bytes a second the cable carries or
    None when there's no cable to wait for). The TV and browsers get 4
    frames a second; the real Compaq, through Kermit, what its cable's
    speed carries: 1 a second at 9600 baud, 4 at 38400."""
    try:
        with open(os.environ.get("COMPAQ_STATUS", RUNTIME + "/status")) as f:
            if f.read().strip() != "connected":
                return 4, None
        with open(RUNTIME + "/speed") as f:
            carries = int(f.read().split()[0]) // 10
    except (OSError, ValueError, IndexError):
        return 4, None
    return max(1, min(4, carries // 960)), carries


def sound_ready(sound):
    """The sound as a WAV file PAL may read (or None)."""
    if not sound:
        return None
    os.makedirs(SOUND_DIR, exist_ok=True)
    os.chmod(SOUND_DIR, 0o750)                      # (PAL is in the desk group)
    wav = os.path.join(SOUND_DIR, "now-playing.wav")
    done = subprocess.run(["ffmpeg", "-v", "error", "-y", "-i", sound, "-ac", "1", "-ar", "22050",
                           "-t", str(LONGEST), wav], capture_output=True)
    if done.returncode != 0 or not os.path.exists(wav):
        return None
    os.chmod(wav, 0o640)
    return wav


class Sound:
    """The sound, played by PAL: started() says when it began (or that it
    can't play); stop() ends it."""

    def __init__(self, wav, title):
        self.conn, self.message = None, ""
        if not wav:
            self.message = "no sound"
            return
        try:
            self.conn = socket.socket(socket.AF_UNIX, socket.SOCK_STREAM)
            self.conn.settimeout(15)
            self.conn.connect(PAL_SOCKET)
            self.conn.sendall((json.dumps({"op": "play_file", "path": wav, "title": title}) + "\n").encode())
            self.replies = self.conn.makefile()
            first = json.loads(self.replies.readline() or "{}")
            if not first.get("started"):
                self.message = first.get("message", "PAL couldn't play the sound")
                self.conn.close()
                self.conn = None
            else:
                self.conn.settimeout(None)
        except (OSError, ValueError) as e:
            self.message = "no sound: PAL isn't answering"
            self.conn = None

    def finished(self):
        if not self.conn:
            return False
        ready, _, _ = select.select([self.conn], [], [], 0)
        return bool(ready)

    def stop(self):
        try:
            with socket.socket(socket.AF_UNIX, socket.SOCK_STREAM) as s:
                s.settimeout(5)
                s.connect(PAL_SOCKET)
                s.sendall(b'{"op": "stop"}\n')
                s.makefile().readline()
        except OSError:
            pass
        if self.conn:
            self.conn.close()


def frame_text(pixels, cols, rows):
    """One frame as rows of text art, contrast stretched (potatoes need it)."""
    low, high = np.percentile(pixels, (2, 98))
    scaled = np.clip((pixels.astype(np.float32) - low) / max(high - low, 1), 0, 0.999)
    levels = (scaled * len(RAMP)).astype(int).reshape(rows, cols)
    return ["".join(RAMP[v] for v in row) for row in levels]


def draw(previous, lines, left):
    """Only what changed since the last frame: what a 9600-baud cable needs."""
    out = []
    for y, (old, new) in enumerate(zip(previous, lines)):
        if old == new:
            continue
        first = next(i for i in range(len(new)) if i >= len(old) or old[i] != new[i])
        last = max(i for i in range(len(new)) if i >= len(old) or old[i] != new[i])
        out.append(f"\033[{TOP + y};{left + first + 1}H{new[first:last + 1]}")
    return "".join(out)


def play_hd(canvas, picture, wav, seconds, title):
    """PotatoTube HD: the film in real dots on a canvas (pictures.Canvas),
    each frame the one the sound has reached, whenever the screen is ready
    for another. Returns a line to show afterwards."""
    tall = 2 if canvas.layout == "320x100" else 1          # (dots twice as tall as wide there)
    width, height = size_of(picture)
    scale = min(canvas.width / width, canvas.height * tall / height)
    w, h = max(2, int(width * scale) // 2 * 2), max(2, int(height * scale / tall) // 2 * 2)
    left, top = (canvas.width - w) // 2, (canvas.height - h) // 2
    decoder = subprocess.Popen(["ffmpeg", "-v", "error", "-i", picture, "-vf",
                                f"fps={HD_FPS},scale={w}:{h}:flags=area,format=gray",
                                "-f", "rawvideo", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
    dither = pictures.Dots(w, h, sharpen=0.5, tall=tall == 2)
    screen = np.zeros((canvas.height, canvas.width), bool)
    stdin = sys.stdin.fileno()
    saved = termios.tcgetattr(stdin)
    tty.setcbreak(stdin)
    sound_player = None
    try:
        sound_player = Sound(wav, title)
        print("\033[H\033[2J\033[?25l", end="")
        print(f"\n  POTATOTUBE HD\n\n  {title}\n")
        print(f"  Playing on the Compaq's screen in {canvas.width}x{canvas.height} real dots"
              + ("." if sound_player.conn else f" ({sound_player.message})."))
        print("  Any key stops it.", flush=True)
        start, frame_no, shown = time.monotonic(), -1, 0
        while True:
            keys = canvas.news(0.0 if canvas.ready else 0.03)
            elapsed = time.monotonic() - start
            if canvas.closed:
                return "The screen was needed for something else."
            if any(pressed for _, pressed, _ in keys) or select.select([stdin], [], [], 0)[0]:
                if select.select([stdin], [], [], 0)[0]:
                    os.read(stdin, 64)
                return "Stopped. The potato rests."
            if sound_player.finished():
                break
            if not canvas.ready:
                continue
            due = int(elapsed * HD_FPS)                  # the frame the sound has reached
            if due <= frame_no:
                time.sleep(min(0.03, max(0.0, (frame_no + 1) / HD_FPS - elapsed)))
                continue
            while frame_no < due:                        # (frames the cable had no time for are skipped)
                pixels = decoder.stdout.read(w * h)
                frame_no += 1
                if len(pixels) < w * h:
                    break
            if len(pixels) < w * h:
                break
            screen[top:top + h, left:left + w] = dither.dots(np.frombuffer(pixels, np.uint8).reshape(h, w))
            screen[-1, :] = False                        # how far along: a line growing across the bottom
            screen[-1, :int(canvas.width * min(1.0, elapsed / max(seconds, 1)))] = True
            canvas.send(screen)
            shown += 1
        elapsed = max(1.0, time.monotonic() - start)
        return f"That's the end. {shown} pictures in real dots, {shown / elapsed:.1f} a second."
    finally:
        decoder.kill()
        if sound_player:
            sound_player.stop()
        termios.tcsetattr(stdin, termios.TCSADRAIN, saved)
        sys.stdout.write("\033[?25h\033[H\033[2J")
        sys.stdout.flush()
        if wav and os.path.exists(wav):
            os.remove(wav)


def open_canvas():
    """A canvas for PotatoTube HD: 320x200, or half the rows on a slow
    cable. Raises pictures.NotShown when this screen can't."""
    canvas = pictures.Canvas("320x200")
    if canvas.bps < HD_SLOW:
        canvas.close()
        canvas = pictures.Canvas("320x100")
    return canvas


def play(video, seconds, title, hd=False):
    """Fetches, then plays one video (hd: in real dots, if this screen
    can); returns a line to show afterwards."""
    print("\033[H\033[2J", end="")
    print(f"\n  POTATOTUBE\n\n  {title}\n")
    print("  Dialing up YouTube and asking for its very worst quality...")
    print("  (about half a minute: the Pi has to solve YouTube's puzzle first)", flush=True)
    # Meanwhile, its thumbnail, painted on the Compaq's screen: a real
    # picture, though the video itself will be text. Half size, so it's
    # done in a few seconds (YouTube is often quicker than a whole one).
    held, shot = None, thumbnail(video)
    if shot:
        try:
            held, paint = pictures.put_up(pictures.dither(pictures.fit(shot, 320, 100)),
                                          f"{title[:50]}: loading, in glorious 144p")
            painted = time.monotonic() + paint + 2
            print("  (Meanwhile, its thumbnail is on the Compaq's screen.)", flush=True)
        except pictures.NotShown:
            pass
    with tempfile.TemporaryDirectory(prefix="potato-") as work:
        try:
            picture, sound, problem = fetch(video, work)
        finally:
            if held:
                time.sleep(max(0.0, min(8.0, painted - time.monotonic())))   # (let it finish)
                held.close()                     # (the screen is the video's now)
        if not picture:
            return ("YouTube wouldn't hand that one over. Try another. ("
                    + clean(problem.replace("ERROR: ", ""), 120) + ")")
        print("  Squashing it into 1987...", flush=True)
        wav = sound_ready(sound)
        if hd:
            try:
                with open_canvas() as canvas:
                    return play_hd(canvas, picture, wav, seconds, title)
            except pictures.NotShown as e:
                print(f"  {e}\n  So it's the text version.", flush=True)
                wav = sound_ready(sound)             # (a failed start may have removed it)
                time.sleep(2)
        width, height = size_of(picture)
        cols, rows = fit(width, height)
        fps, cable_bytes = cable()
        left = (COLS - cols) // 2
        decoder = subprocess.Popen(["ffmpeg", "-v", "error", "-i", picture, "-vf",
                                    f"fps={fps},scale={cols}:{rows}:flags=area,format=gray",
                                    "-f", "rawvideo", "-"], stdout=subprocess.PIPE, stderr=subprocess.DEVNULL)
        stdin = sys.stdin.fileno()
        saved = termios.tcgetattr(stdin)
        tty.setcbreak(stdin)
        sound_player = None
        try:
            sound_player = Sound(wav, title)
            quality = f"144p -> {cols}x{rows} text @ {fps} fps" + ("" if sound_player.conn else
                                                                  f" ({sound_player.message})")
            print("\033[H\033[2J\033[?25l", end="")
            print(f" POTATOTUBE  {quality}"[:COLS])
            start, shown, previous, frame_no = time.monotonic(), "", [""] * rows, 0
            # On the real cable a frame can take longer to send than to
            # show: the line's own clock (when it will have sent everything
            # so far) skips frames it can't carry, so the picture keeps up
            # with the sound instead of drifting further behind.
            line_free = time.monotonic()
            while True:
                pixels = decoder.stdout.read(cols * rows)
                if len(pixels) < cols * rows:
                    break
                due = start + frame_no / fps
                frame_no += 1
                if time.monotonic() > due + 1 / fps:
                    continue                          # behind: skip this one
                if cable_bytes and line_free > due + 0.5:
                    continue                          # the cable's still busy: skip this one
                lines = frame_text(np.frombuffer(pixels, np.uint8), cols, rows)
                out = draw(previous, lines, left)
                sys.stdout.write(out)
                previous = lines
                if cable_bytes:
                    line_free = max(time.monotonic(), line_free) + len(out) / cable_bytes
                clock = f" {title[:50]}  {int(due - start) // 60}:{int(due - start) % 60:02d} / " \
                        f"{seconds // 60}:{seconds % 60:02d}   any key: stop"
                if clock != shown:
                    sys.stdout.write(f"\0337\033[24;1H\033[K{clock[:COLS]}\0338")
                    shown = clock
                sys.stdout.flush()
                while time.monotonic() < due + 1 / fps:
                    ready, _, _ = select.select([stdin], [], [], max(0.0, due + 1 / fps - time.monotonic()))
                    if ready:
                        os.read(stdin, 64)
                        return "Stopped. The potato rests."
                if sound_player.finished():
                    break
            return "That's the end. Truly the worst it has ever looked."
        finally:
            decoder.kill()
            if sound_player:
                sound_player.stop()
            termios.tcsetattr(stdin, termios.TCSADRAIN, saved)
            sys.stdout.write("\033[?25h\033[H\033[2J")
            sys.stdout.flush()
            if wav and os.path.exists(wav):
                os.remove(wav)


def hd_possible():
    """Can this screen show PotatoTube HD? Not once the serial bridge has
    found the Compaq has no PILINK. (Not tried yet: say yes; if it can't,
    the video plays in characters after all.)"""
    try:
        with open(RUNTIME + "/pilink") as f:
            return not f.read().startswith("not")
    except OSError:
        return True


def ask_how():
    """Characters or dots, for the video just picked? True for HD."""
    print("\n  Watch it in   C: characters, the classic potato (text art)")
    print("                H: HD, real amber dots")
    try:
        answer = input("  C or H (just Enter: C): ").strip().lower()
    except EOFError:
        answer = ""
    return answer.startswith("h")


def countdown(seconds, how="the top one"):
    """True unless a key is pressed in the next seconds."""
    stdin = sys.stdin.fileno()
    saved = termios.tcgetattr(stdin)
    tty.setcbreak(stdin)
    try:
        for left in range(seconds, 0, -1):
            print(f"\r  Playing {how} in {left}... (any key: choose another) ", end="", flush=True)
            if select.select([stdin], [], [], 1)[0]:
                os.read(stdin, 64)
                return False
        return True
    finally:
        termios.tcsetattr(stdin, termios.TCSADRAIN, saved)
        print()


def main():
    # (F10 closes this screen under us: leave the way Python usually does,
    # so the sound stops and the downloaded video is cleared away)
    signal.signal(signal.SIGHUP, lambda *_: sys.exit(1))
    if not (os.path.exists(YTDLP) and shutil.which("ffmpeg") and shutil.which("qjs")):
        print("\n  PotatoTube isn't set up on this Pi yet (run fetch-net.sh on the Mac).")
        input("  Press Enter. ")
        return
    words = sys.argv[1:]
    want_hd = "--hd" in words and hd_possible()       # (asked for out loud: "...in HD")
    query = clean(" ".join(w for w in words if w != "--hd"), 100)
    auto = bool(query)
    while True:
        print("\033[H\033[2J", end="")
        print("\n  P O T A T O T U B E      YouTube, in the worst quality ever offered\n")
        if not query:
            query = clean(input("  Search YouTube (just Enter: back): "), 100)
            if not query:
                return
        else:
            print(f"  Search YouTube: {query}")
        print("\n  Searching...", flush=True)
        try:
            found = find(query)
        except subprocess.TimeoutExpired:
            found = []
        if not found:
            input("\n  Nothing playable (videos up to 10 minutes). Press Enter. ")
            query, auto = "", False
            continue
        print("\033[2A\033[J", end="")
        for n, (_, seconds, title) in enumerate(found, 1):
            print(f"   {n}. {title[:62]}  {seconds // 60}:{seconds % 60:02d}")
        print()
        hd = False
        if auto and countdown(3, "the top one in HD" if want_hd else "the top one"):
            pick, hd = 1, want_hd
        else:
            choice = input("  A number to watch it. S: new search. Enter: back. ").strip().lower().replace(" ", "")
            if choice == "s":
                query, auto = "", False
                continue
            hd = choice.startswith("h")              # (H and a number, or C and a number: no question)
            plain = choice.startswith("c")
            choice = choice.lstrip("hc")
            if not (choice.isdigit() and len(choice) <= 2 and 1 <= int(choice) <= len(found)):
                return
            pick = int(choice)
            if not (hd or plain) and hd_possible():
                hd = ask_how()
        auto = False
        video, seconds, title = found[pick - 1]
        message = play(video, seconds, title, hd)
        print(f"\n  {message}")
        if input("  Press Enter for the list, or L: watch it properly on your phone. ").strip().lower() == "l":
            print("\n  Point a phone's camera at the Compaq's screen.")
            try:
                pictures.show(pictures.qr(f"https://youtu.be/{video}"), "Scan to watch it in colour",
                              told=pictures.saying("a QR code", more=False))
            except pictures.NotShown as e:
                print(f"  {e}")
                input("  Press Enter for the list. ")


if __name__ == "__main__":
    try:
        main()
    except (KeyboardInterrupt, EOFError):
        print("\033[?25h")

"""PAL's senses: the webcam (faces), the microphone (speech, via Whisper on
the Pi) and the voice (espeak-ng through sox, for that 1980s sound).

Nothing here keeps a picture or a recording: frames are looked at and
dropped, and speech is turned into text and dropped.

For testing without the hardware, CAMERA, MICROPHONE and SPEAKER in pal.conf
can name folders instead ("dir:/path"): the camera sees current.jpg in its
folder (nobody, if there isn't one), WAV files in the microphone's folder are
heard one at a time when PAL listens, and what PAL says is written to WAV
files. With PAL_SIM_REALTIME=1 in its surroundings (the lobby simulator,
tools/tests/lobby_sim.sh) it all takes as long as it would at the lobby: a
WAV in the microphone's folder is played into a quiet room, a frame at a
time, through the same speech finder as the real microphone, and what PAL
says takes as long to "play" as it would on the speaker.
"""

import collections
import glob
import io
import json
import os
import queue
import re
import subprocess
import threading
import time
import urllib.error
import urllib.request
import uuid
import wave

import cv2
import numpy as np

MODELS = "/var/lib/compaq/pal-models/"
DETECTOR = MODELS + "face_detection_yunet_2023mar.onnx"
RECOGNISER = MODELS + "face_recognition_sface_2021dec_int8.onnx"
WHISPER_MODEL = MODELS + "ggml-tiny.en-q8_0.bin"
WHISPER_SERVER = "/opt/compaq-pal/bin/whisper-server"
WHISPER_PORT = 8178
# Other languages, when someone asks PAL to speak one: the multilingual
# model, told which language to expect (left to guess, on a Pi 3 it takes
# 5 seconds and mostly guesses wrong). Started when first needed.
WHISPER_ANY_MODEL = MODELS + "ggml-tiny-q8_0.bin"
WHISPER_ANY_PORT = 8179
# Languages PAL can switch to: Whisper's code -> espeak-ng's voice.
LANGUAGES = {"en": "en-us", "es": "es", "fr": "fr-fr", "de": "de", "it": "it", "pt": "pt-br",
             "nl": "nl", "pl": "pl", "ru": "ru", "uk": "uk", "zh": "cmn", "ja": "ja", "ko": "ko",
             "hi": "hi", "ar": "ar", "tr": "tr", "vi": "vi", "sv": "sv", "da": "da", "nb": "nb",
             "fi": "fi", "el": "el", "he": "he", "id": "id", "cs": "cs", "ro": "ro", "hu": "hu"}
WIDTH, HEIGHT = 320, 240
RATE = 16000
REALTIME = os.environ.get("PAL_SIM_REALTIME") == "1"   # (the test folders at the lobby's pace)


def log(*args):
    print(*args, flush=True)


# ------------------------------------------------------------------ camera

def find_camera():
    """The first USB webcam (the Pi's own video devices aren't cameras)."""
    found = sorted(glob.glob("/dev/v4l/by-id/*-video-index0"))
    return found[0] if found else None


class Face:
    """One face in one frame: where it is, how big, and (once worked out)
    its signature."""

    def __init__(self, row):
        self.row = row
        self.x, self.y, self.w, self.h = (float(v) for v in row[:4])
        self.signature = None

    @property
    def centre(self):
        return self.x + self.w / 2, self.y + self.h / 2


class Eyes:
    """The webcam: finds faces a few times a second and can say whose they are."""

    def __init__(self, source=""):
        self.source = source
        self.capture = None
        self.folder = None
        self.previous = None
        self.area = 0.0               # share of the picture that changed in the last frame
        self.status = "no camera"
        try:
            self.detector = cv2.FaceDetectorYN.create(DETECTOR, "", (WIDTH, HEIGHT), 0.85, 0.3, 10)
            self.recogniser = cv2.FaceRecognizerSF.create(RECOGNISER, "")
        except cv2.error:
            # Without them PAL can't see, and so (it only listens while
            # someone is in view) can't hear either; typed chat still works.
            self.detector = self.recogniser = None
            self.status = "face models missing, so PAL can't see or listen (run fetch-pal.sh)"

    def open(self):
        if self.detector is None:
            return False
        if self.source.startswith("dir:"):
            self.folder = self.source[4:]
            self.status = f"test pictures ({self.folder})"
            return True
        device = self.source or find_camera()
        if not device:
            self.status = "no camera plugged in"
            return False
        capture = cv2.VideoCapture(device, cv2.CAP_V4L2)
        if not capture.isOpened():
            self.status = f"can't open {device}"
            return False
        capture.set(cv2.CAP_PROP_FOURCC, cv2.VideoWriter_fourcc(*"MJPG"))
        capture.set(cv2.CAP_PROP_FRAME_WIDTH, 640)
        capture.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
        capture.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.capture = capture
        self.status = f"ok ({os.path.basename(device)})"
        return True

    def frame(self):
        """The newest frame, or None if the camera has gone."""
        if self.folder:
            path = os.path.join(self.folder, "current.jpg")
            image = cv2.imread(path) if os.path.exists(path) else None
            return image if image is not None else np.zeros((480, 640, 3), np.uint8)
        if not self.capture:
            return None
        self.capture.grab()           # drop the frame that waited in the buffer
        ok, image = self.capture.read()
        if not ok:
            self.capture.release()
            self.capture = None
            self.status = "camera unplugged"
            return None
        return image

    def moved(self, image):
        """Did anything change since the last frame? (Cheap: a tiny grey copy.)
        Also sets self.area, how much of the picture changed: someone walking
        past changes a good part of it; a light flickering, little or all."""
        small = cv2.cvtColor(cv2.resize(image, (80, 60)), cv2.COLOR_BGR2GRAY)
        before, self.previous = self.previous, small
        if before is None:
            self.area = 0.0
            return True
        diff = cv2.absdiff(small, before)
        self.area = float(np.count_nonzero(diff > 25)) / diff.size
        return float(np.mean(diff)) > 2.0

    def faces(self, image, smallest=0.04):
        """Faces at least `smallest` of the picture's width: anyone within a
        few metres. (Recognising someone needs them closer; see pal.py.)"""
        h, w = image.shape[:2]
        scale = WIDTH / w
        small = cv2.resize(image, (WIDTH, int(h * scale)))
        self.detector.setInputSize((small.shape[1], small.shape[0]))
        _, found = self.detector.detect(small)
        if found is None:
            return []
        faces = []
        for row in found:
            row = row.copy()
            row[:14] /= scale                     # back to the full picture
            if row[2] >= smallest * w:
                faces.append(Face(row))
        return faces

    def signature(self, image, face):
        """128 numbers that describe a face; the same person gives similar numbers."""
        aligned = self.recogniser.alignCrop(image, face.row)
        face.signature = self.recogniser.feature(aligned).ravel()
        return face.signature


# ------------------------------------------------------------------ hearing

def sound_cards(command):
    """[(card name, description)] that `aplay -l` or `arecord -l` lists."""
    try:
        out = subprocess.run([command, "-l"], capture_output=True, text=True, timeout=5).stdout
    except (OSError, subprocess.TimeoutExpired):
        return []
    return re.findall(r"^card \d+: (\w+) \[([^\]]*)\]", out, re.M)


def listener(port):
    """Who listens on TCP port on this machine: "us", "nobody", or
    "someone else". PAL sends the lobby's sound to its speech engine on a
    local port, and only to its own: another account that got to the port
    first (while Whisper was restarting, say) would hear the lobby and could
    tell PAL what was "said"."""
    owners = set()
    for table in ("/proc/net/tcp", "/proc/net/tcp6"):
        try:
            with open(table) as f:
                for line in list(f)[1:]:
                    fields = line.split()
                    if fields[3] == "0A" and fields[1].endswith(f":{port:04X}"):     # 0A: listening
                        owners.add(int(fields[7]))
        except (OSError, ValueError, IndexError):
            return "someone else"                    # (can't tell: don't risk it)
    if not owners:
        return "nobody"
    return "us" if owners == {os.getuid()} else "someone else"


def find_microphone():
    """A proper USB microphone if there is one (better for speech than a
    webcam's), else the first one there is (usually the webcam's)."""
    cards = sound_cards("arecord")
    for card, description in cards:
        if re.search(r"mic|yeti|snowball|rode|samson|fifine|audio-technica", card + description, re.I):
            return f"plughw:CARD={card},DEV=0"
    return f"plughw:CARD={cards[0][0]},DEV=0" if cards else None


def to_wav(pcm, rate=RATE):
    buffer = io.BytesIO()
    with wave.open(buffer, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(rate)
        w.writeframes(pcm)
    return buffer.getvalue()


class Ears:
    """The microphone and Whisper. Only while PAL is listening does it look
    for speech at all; each thing someone says comes out of heard() as text."""

    FRAME = 480                   # 30 ms of 16 kHz audio
    # What Whisper makes of noise: no one says just "the" to a computer. (A
    # lone "A" stays: it's a quiz answer.)
    HALLUCINATIONS = re.compile(r"^\W*(thanks? (you )?for watching|subscribe|you|i|the|\.+)\W*$", re.I)
    # (No "Hey PAL" hint for Whisper: it helps "Hey PAL" said on its own,
    # but in a whole sentence it sometimes leaves the "Hey PAL" out
    # altogether. pal.py's WAKE knows the usual mishearings instead.)

    def __init__(self, source=""):
        self.source = source
        self.listening = False
        self.utterances = queue.Queue()
        self.speech = queue.Queue()       # sound waiting for Whisper
        self.deaf_until = 0.0             # while PAL itself is talking (see Mouth in pal.py)
        self.sent = collections.deque()   # when recent clips went to Whisper
        self.status = "no microphone"
        self.capturing = False            # someone is talking right now
        self.transcribing = False         # Whisper is working on what they said
        self.language = "en"              # what people are speaking (see set_language)
        self.timing = (0.0, 0.0)          # the last thing heard: (seconds of speech, seconds Whisper took)
        self.cue = None                   # called when an utterance goes to Whisper (PAL's "got it" tick)
        self.server = None
        self.any_server = None            # the multilingual one, while it's needed
        threading.Thread(target=self.transcriber, daemon=True).start()

    # Whisper runs as a small local server so its model stays loaded.
    @staticmethod
    def whisper(model, port, language):
        # One server a port: a stray one left on it would answer half the time.
        subprocess.run(["pkill", "-u", str(os.getuid()), "-f", f"^{WHISPER_SERVER} -m {model} "],
                       stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        time.sleep(0.5)
        return subprocess.Popen(
            [WHISPER_SERVER, "-m", model, "--host", "127.0.0.1", "--port", str(port),
             "-t", "3", "-nt", "-nf", "-sns", "-l", language, "-bo", "1"],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)

    def start_whisper(self):
        if self.server and self.server.poll() is None:
            return True
        if not (os.path.exists(WHISPER_SERVER) and os.path.exists(WHISPER_MODEL)):
            self.status = "Whisper isn't installed (run fetch-pal.sh)"
            return False
        self.server = self.whisper(WHISPER_MODEL, WHISPER_PORT, "en")
        return True

    def set_language(self, code):
        """Listens for code (like "es") from now on; "en" goes back to the
        usual English model. False if that language can't be heard."""
        if code == "en":
            self.language = "en"
            if self.any_server:
                self.any_server.kill()      # (frees its memory until next time)
                self.any_server.wait()
                self.any_server = None
            return True
        if code not in LANGUAGES or not os.path.exists(WHISPER_ANY_MODEL):
            return False
        if not (self.any_server and self.any_server.poll() is None):
            self.any_server = self.whisper(WHISPER_ANY_MODEL, WHISPER_ANY_PORT, code)
        self.language = code
        return True

    def transcribe(self, pcm):
        """What was said in pcm (16 kHz mono 16-bit), as text."""
        seconds = len(pcm) / (2 * RATE)
        # Whisper normally works on 30-second windows; telling it the clip is
        # short makes it several times faster. It needs about 3 seconds of
        # room beyond the clip (160 steps; 50 a second): with less it can
        # loop on its own words, taking 20 seconds instead of 2.
        audio_ctx = min(1500, max(320, -(-int(seconds * 50 + 160) // 64) * 64))
        boundary = uuid.uuid4().hex
        parts = []
        language = self.language
        port = WHISPER_ANY_PORT if language != "en" else WHISPER_PORT
        for name, value, extra in (("file", to_wav(pcm), '; filename="speech.wav"'),
                                   ("audio_ctx", str(audio_ctx).encode(), ""),
                                   ("language", language.encode(), ""),
                                   ("response_format", b"json", "")):
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="{name}"{extra}\r\n\r\n'
                         .encode() + value + b"\r\n")
        body = b"".join(parts) + f"--{boundary}--\r\n".encode()
        request = urllib.request.Request(
            f"http://127.0.0.1:{port}/inference", data=body,
            headers={"Content-Type": f"multipart/form-data; boundary={boundary}"})
        server = self.server if language == "en" else self.any_server
        for attempt in range(20):      # the server may still be loading its model
            if not server or server.poll() is not None:
                raise RuntimeError("Whisper isn't running")
            heard_by = listener(port)
            if heard_by == "someone else":
                raise RuntimeError("something other than PAL's Whisper is listening where Whisper should be")
            if heard_by == "nobody":   # (not up yet)
                if attempt == 19:
                    raise RuntimeError("Whisper isn't answering")
                time.sleep(0.5)
                continue
            try:
                with urllib.request.urlopen(request, timeout=60) as response:
                    text = json.load(response).get("text", "")
                break
            except (ConnectionError, urllib.error.URLError) as e:
                if attempt == 19 or not isinstance(getattr(e, "reason", e), ConnectionError):
                    raise
                time.sleep(0.5)
        text = " ".join(re.sub(r"\[[^\]]*\]|\([^)]*\)", " ", text).split())
        return "" if self.HALLUCINATIONS.match(text) else text

    def run(self):
        """Reads the microphone forever, finding speech while listening."""
        while True:
            try:
                if self.source.startswith("dir:"):
                    self.from_files(self.source[4:])
                else:
                    self.from_microphone()
            except Exception as e:  # keep listening whatever goes wrong
                log("microphone:", e)
            time.sleep(10)

    def from_microphone(self):
        device = self.source or find_microphone()
        if not device:
            self.status = "no microphone plugged in"
            return
        recorder = subprocess.Popen(["arecord", "-q", "-D", device, "-f", "S16_LE", "-r", str(RATE),
                                     "-c", "1", "-t", "raw"], stdout=subprocess.PIPE,
                                    stderr=subprocess.DEVNULL)
        self.status = f"ok ({device})"
        try:
            self.find_speech(lambda: recorder.stdout.read(self.FRAME * 2))
        finally:
            recorder.kill()
            recorder.wait()
            self.status = "microphone unplugged"

    def from_files(self, folder):
        """Test mode: a WAV file put in folder is "said" (then removed) the
        next time PAL listens."""
        self.status = f"test recordings ({folder})"
        if REALTIME:
            return self.find_speech(self.room(folder))
        while True:
            # (not one still being written)
            files = sorted(f for f in glob.glob(os.path.join(folder, "*.wav"))
                           if time.time() - os.path.getmtime(f) > 0.5)
            if not files or not self.hearing():
                time.sleep(0.2)
                continue
            with wave.open(files[0]) as w:
                pcm = w.readframes(w.getnframes())
            os.remove(files[0])
            self.handle(pcm)

    def room(self, folder):
        """Test mode at the lobby's pace: a microphone in a quiet room, read
        30 ms at a time, into which each WAV put in folder (16 kHz mono) is
        spoken as it arrives (then removed), whether PAL is listening or not."""
        rng = np.random.default_rng()
        state = {"due": time.monotonic(), "words": b"", "looked": 0.0}

        def read():
            state["due"] += self.FRAME / RATE
            wait = state["due"] - time.monotonic()
            if wait > 0:
                time.sleep(wait)
            else:
                state["due"] = time.monotonic()      # (fell behind: carry on from now)
            if not state["words"] and time.monotonic() - state["looked"] > 0.2:
                state["looked"] = time.monotonic()
                files = sorted(f for f in glob.glob(os.path.join(folder, "*.wav"))
                               if time.time() - os.path.getmtime(f) > 0.5)
                if files:
                    with wave.open(files[0]) as w:
                        state["words"] = w.readframes(w.getnframes())
                    os.remove(files[0])
            chunk, state["words"] = state["words"][:self.FRAME * 2], state["words"][self.FRAME * 2:]
            hiss = rng.normal(0, 40, self.FRAME).astype(np.int16).tobytes()
            return chunk + hiss[len(chunk):]
        return read

    def find_speech(self, read):
        """Splits the microphone into utterances: speech starts when it's
        clearly louder than the room, and ends after 1 s of quiet. (0.6 s
        cut people off when they paused to think mid-sentence.)"""
        floor = 200.0                      # the room's background level, learnt as we go
        levels = collections.deque(maxlen=100)   # the last 3 s between speech
        speech, quiet, loud, before = [], 0, 0, []
        while True:
            self.capturing = bool(speech)
            chunk = read()
            if len(chunk) < self.FRAME * 2:
                self.capturing = False
                return
            if not self.hearing():
                speech, loud, before = [], 0, []
                continue
            level = float(np.sqrt(np.mean(np.frombuffer(chunk, np.int16).astype(np.float32) ** 2)))
            threshold = max(floor * 3.0, 300.0)
            if not speech:
                before = (before + [chunk])[-10:]       # 0.3 s before speech starts
                loud = loud + 1 if level > threshold else 0
                if loud >= 3:
                    speech, quiet, speech_levels = list(before), 0, []
                else:
                    levels.append(level)
                    # The quieter end of the last few seconds: steady noise
                    # (a fan, a TV) raises it, so it isn't taken for speech.
                    floor = max(50.0, sorted(levels)[len(levels) // 5])
                continue
            speech_levels.append(level)
            speech.append(chunk)
            quiet = quiet + 1 if level < threshold * 0.7 else 0
            if quiet >= 33 or len(speech) >= 400:     # 1 s of quiet, or 12 s
                pcm = b"".join(speech)
                if len(speech) >= 400:
                    # 12 s without a pause is more likely noise than someone
                    # talking to PAL: hear the room as louder from now on.
                    # (Into the remembered levels, which the floor is worked
                    # out from again at the next quiet moment.)
                    levels.extend(speech_levels[-100:])
                    floor = max(floor, sorted(speech_levels)[len(speech_levels) // 2] / 3)
                speech, loud, before = [], 0, []
                if len(pcm) >= RATE * 2 * 0.5 and self.allowed():   # half a second at least
                    self.handle(pcm)

    def hearing(self):
        return self.listening and time.monotonic() >= self.deaf_until

    def allowed(self):
        """At most 12 things a minute go to Whisper (it uses the whole Pi)."""
        now = time.monotonic()
        while self.sent and now - self.sent[0] > 60:
            self.sent.popleft()
        if len(self.sent) >= 12:
            return False
        self.sent.append(now)
        return True

    def handle(self, pcm):
        """Hands sound to the transcriber, so the microphone keeps listening
        (a backlog would make PAL answer later and later)."""
        if self.hearing():
            self.speech.put(pcm)
            cue = self.cue
            if cue:
                cue()

    def transcriber(self):
        while True:
            pcm = self.speech.get()
            while not self.speech.empty():     # fell behind: the newest matters most
                pcm = self.speech.get_nowait()
            if not self.listening:
                continue
            self.transcribing = True
            started = time.monotonic()
            try:
                text = self.transcribe(pcm)
                self.timing = (len(pcm) / (2 * RATE), time.monotonic() - started)
            except Exception as e:
                log("whisper:", e)
                continue
            finally:
                self.transcribing = False
            if text and self.listening:
                self.utterances.put(text)

    def clear(self):
        """Forgets anything heard but not yet handled (e.g. PAL's own voice)."""
        for q in (self.speech, self.utterances):
            while not q.empty():
                try:
                    q.get_nowait()
                except queue.Empty:
                    break


# ------------------------------------------------------------------ voice

def find_speaker():
    """A USB speaker if there is one, else the Pi's headphone socket. A USB
    device that also records is a microphone or headset (its playback side
    is a headphone jack on the mic), so it doesn't count."""
    cards = sound_cards("aplay")
    recorders = {card for card, _ in sound_cards("arecord")}
    for card, description in cards:
        if card not in ("Headphones", "vc4hdmi") and "HDMI" not in description \
                and card not in recorders:
            return f"plughw:CARD={card},DEV=0"
    return "plughw:CARD=Headphones,DEV=0" if any(c == "Headphones" for c, _ in cards) else None


class Voice:
    """Speech: espeak-ng's formant voices are the 1980s-computer part; sox
    makes them sound like they come out of a small cabinet speaker."""

    # Clarity: less rumble, a lift where consonants live, and gentle
    # compression so quiet syllables carry across a lobby.
    CLEAR = ["highpass", "110", "equalizer", "2800", "1.2q", "+5", "equalizer", "250", "1q", "-3",
             "compand", "0.02,0.15", "6:-60,-60,-36,-22,-20,-12,0,-6", "-4", "-20", "0.05"]
    STYLES = {
        # A calm mainframe at a normal talking pace, with short pauses
        # between words. Tuned with Whisper as the listener: it misses about
        # 8% of words, against 26% for the first version (deeper, slower,
        # with an echo).
        "mainframe": (["-v", "en-us", "-g", "5"], ["-r", "22050"], ["gain", "-8", *CLEAR]),
        # DECtalk-style terminal, 8-bit at 11 kHz.
        "dectalk": (["-v", "en-us+klatt4", "-g", "3"], ["-r", "11025", "-b", "8"],
                    ["gain", "-6", "highpass", "120", "lowpass", "4000"]),
        # An arcade robot, 8-bit telephone quality.
        "arcade": (["-v", "en-us+robosoft3", "-g", "2"], ["-r", "8000", "-b", "8"],
                   ["gain", "-6", "highpass", "250", "lowpass", "3200", "overdrive", "4"]),
        # The same mainframe at a normal talking pace (mainframe's gaps
        # between words suit Whisper better than people).
        "clear": (["-v", "en-us", "-g", "1"], ["-r", "22050"], ["gain", "-8", *CLEAR]),
        # Characters, for fun ("Hey PAL, talk like an ogre", or the menu).
        # (sox's reverb comes out in stereo: back to one channel for CLEAR.)
        "ogre": (["-v", "en-gb-scotland+croak", "-g", "1"], ["-r", "22050"],
                 ["pitch", "-300", "bass", "+8", "overdrive", "6", "8", "gain", "-8", *CLEAR]),
        "trailer": (["-v", "en-us+m7", "-g", "2"], ["-r", "22050"],
                    ["pitch", "-350", "bass", "+6", "reverb", "35", "50", "70", "channels", "1", "gain", "-8", *CLEAR]),
        "villain": (["-v", "en-us+Demonic", "-g", "2"], ["-r", "22050"],
                    ["pitch", "-450", "bass", "+5", "reverb", "60", "40", "90", "channels", "1", "gain", "-8", *CLEAR]),
        "chipmunk": (["-v", "en-us+Tweaky", "-g", "1"], ["-r", "22050"], ["pitch", "+600", "gain", "-8", *CLEAR]),
        "butler": (["-v", "en-gb-x-rp+m3", "-g", "1"], ["-r", "22050"],
                   ["reverb", "20", "50", "40", "channels", "1", "gain", "-8", *CLEAR]),
        "radio": (["-v", "en-us+announcer", "-g", "1"], ["-r", "22050"],
                  ["highpass", "500", "lowpass", "3000", "overdrive", "8", "12", "gain", "-8", *CLEAR]),
        "grandpa": (["-v", "en-us+grandpa", "-g", "2"], ["-r", "22050"], ["gain", "-8", *CLEAR]),
        "whisper": (["-v", "en-us+whisper", "-g", "2"], ["-r", "22050"],
                    ["reverb", "50", "50", "60", "channels", "1", "gain", "-4", *CLEAR]),
    }
    # A voice's own pace (words a minute, pitch), where pal.conf's SPEED and
    # PITCH (for PAL's own voice) would spoil it.
    PACE = {"clear": (165, 40), "ogre": (135, 22), "trailer": (125, 12), "villain": (115, 8),
            "chipmunk": (170, 70), "butler": (140, 32), "radio": (165, 45), "grandpa": (125, 25),
            "whisper": (140, 35)}
    # What each sounds like, for the menu and for Claude (change_voice).
    SOUNDS = {"mainframe": "PAL's own voice, a calm 1980s mainframe", "clear": "PAL at a normal talking pace",
              "dectalk": "a 1984 DECtalk terminal", "arcade": "an 8-bit arcade robot",
              "ogre": "an ogre with a Scottish accent, fresh from his swamp", "trailer": "a movie-trailer narrator",
              "villain": "a space villain", "chipmunk": "a chipmunk", "butler": "a posh British butler",
              "radio": "a 1940s radio announcer", "grandpa": "a grandpa", "whisper": "a spooky whisper"}

    def __init__(self, style="mainframe", speed=150, pitch=28, volume=80, device=""):
        self.style = style if style in self.STYLES else "mainframe"
        self.speed, self.pitch, self.volume = speed, pitch, volume
        self.device = device
        found = device or find_speaker()
        self.status = f"ok ({found})" if found else "no speaker found"
        self.counter = 0
        self.player = None            # the aplay playing right now
        self.stopped = False
        self.speaker = threading.Lock()   # one sound at a time (the device can't mix)
        self.language = "en"          # speaks this language's voice (see LANGUAGES)

    def render(self, text):
        """(WAV bytes, seconds) for text."""
        voice, rate, effects = self.STYLES[self.style]
        if self.language != "en":
            # The same character, with another language's voice ("en-us+klatt4" -> "es+klatt4").
            name = LANGUAGES.get(self.language, "en-us")
            voice = [name + v[5:] if v.startswith("en-us") else v for v in voice]
        # The words go in on standard input (UTF-8): one starting with "-"
        # would be taken for an option on the command line.
        speed, pitch = self.PACE.get(self.style, (self.speed, self.pitch))
        spoken = subprocess.run(["espeak-ng", *voice, "-b", "1", "-s", str(speed), "-p", str(pitch),
                                 "--stdout", "--stdin"], input=text.encode(), capture_output=True,
                                check=True, timeout=30).stdout
        loudness = 20 * np.log10(max(self.volume, 1) / 100)        # 0-100 -> dB
        wav = subprocess.run(["sox", "-t", "wav", "-", *rate, "-t", "wav", "-", *effects,
                              "gain", "-n", f"{loudness - 2:.1f}"],
                             input=spoken, capture_output=True, check=True, timeout=30).stdout
        # sox can't fill in the length when writing to a pipe, so measure
        # the sound itself: everything after the "data" header.
        with wave.open(io.BytesIO(wav)) as w:
            bytes_per_second = w.getframerate() * w.getsampwidth() * w.getnchannels()
        start = wav.find(b"data") + 8
        seconds = max(0, len(wav) - start) / bytes_per_second
        return wav, seconds

    def play(self, wav, text=None):
        """Plays WAV bytes; returns when done. (Test mode: writes them to a
        file, with the words beside it in a .txt.)"""
        if self.device.startswith("dir:"):
            self.counter += 1
            folder = self.device[4:]
            os.makedirs(folder, exist_ok=True)
            if text:
                with open(os.path.join(folder, f"said-{self.counter:03d}.txt"), "w") as f:
                    f.write(text + "\n")
            with open(os.path.join(folder, f"said-{self.counter:03d}.wav"), "wb") as f:
                f.write(wav)
            self.status = f"writing to {folder}"
            if REALTIME:
                with wave.open(io.BytesIO(wav)) as w:
                    rate = w.getframerate() * w.getsampwidth() * w.getnchannels()
                time.sleep(max(0, len(wav) - wav.find(b"data") - 8) / rate)
            return
        device = self.device or find_speaker()
        if not device:
            self.status = "no speaker found"
            return
        with self.speaker:
            self.stopped = False
            code, error = self.aplay(device, wav)
            if code != 0 and self.device and not self.stopped:
                # The speaker in pal.conf has gone (unplugged, say): try any other.
                other = find_speaker()
                if other and other != device:
                    device = other
                    code, error = self.aplay(device, wav)
            if not self.stopped:
                self.status = f"ok ({device})" if code == 0 else f"can't play on {device}: {error[:80]}"

    def aplay(self, device, wav):
        """(exit code, error) for playing wav on device."""
        player = subprocess.Popen(["aplay", "-q", "-D", device, "-"], stdin=subprocess.PIPE,
                                  stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        self.player = player
        try:
            # (never stuck for good on a speaker that stopped answering: no
            # sound here plays slower than 8000 bytes a second)
            _, error = player.communicate(wav, timeout=len(wav) / 8000 + 15)
        except subprocess.TimeoutExpired:
            player.kill()
            _, error = player.communicate()
        finally:
            self.player = None
        return player.returncode, error.decode(errors="replace").strip()

    def wireless(self):
        """Is the speaker a Bluetooth one (bluealsa)?"""
        return self.device.startswith("bluealsa")

    def stop(self):
        """Stops whatever is playing (a tune someone wants to end)."""
        player = self.player
        if player and player.poll() is None:
            self.stopped = True
            player.kill()

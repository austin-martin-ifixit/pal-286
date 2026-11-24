#!/usr/bin/env python3
"""Compaq on the web: the shared Compaq session at http://compaq.local.

Anyone on the office network with the office password sees the Compaq's
screen live and can type into it. Each browser is one more tmux client of
the shared session, the same session the Compaq's cable is attached to, so
it's the real Compaq, not a copy. Runs as the limited "desk" account
(compaq-web.service), so nothing typed here can take over the Pi.

The office password is set with set-office-password.sh; only its PBKDF2
hash is stored, in /etc/compaq/web.env. Changing it signs everyone out.

Usage: server.py [--port 80]
"""

import argparse
import base64
import ctypes
import fcntl
import hashlib
import hmac
import http.cookies
import http.server
import ipaddress
import json
import os
import pty
import queue
import secrets
import signal
import socket
import struct
import termios
import threading
import time
import urllib.parse
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/vendor/xterm.js": ("vendor/xterm.js", "text/javascript"),
    "/vendor/xterm.css": ("vendor/xterm.css", "text/css"),
    "/vendor/Compaq_Port3.woff": ("vendor/Compaq_Port3.woff", "font/woff"),
}
PASSWORD_FILE = "/etc/compaq/web.env"
STATUS_FILE = "/run/compaq-serial/status"
PICTURE = "/run/compaq-serial/picture"     # .json and .png: a picture the Compaq shows (serial_bridge.py)
VIEWERS_FILE = "/run/compaq-web/viewers"   # read by the menu's header
TMUX = ["tmux", "-L", "compaq"]
COOKIE = "compaq_session"
COOKIE_DAYS = 30
HEADER = "X-Compaq"           # required on every POST (see allowed())
MAX_VIEWERS = 12
MAX_CONNECTIONS = 64          # beyond this, new connections are dropped at once
MAX_PER_ADDRESS = 16          # ...and this many from one computer (a browser uses a handful)
MAX_BODY = 65536
UNCLAIMED_SECONDS = 15        # a viewer whose page never reads it is closed
LOGIN_LIMIT = (5, 300)        # at most 5 password tries per 5 minutes per address
LOGIN_LIMIT_ALL = (300, 300)  # and 300 from everyone together (one a second: the checks are slow anyway)

viewers = {}                  # id -> Viewer
signed_out = {}               # cookie token -> when it was signed out (until it would expire)
attempts = {}                 # client address -> times of password tries
lock = threading.Lock()
hashing = threading.BoundedSemaphore(1)   # one slow password check at a time


COOKIE_KEY = secrets.token_bytes(32)   # replaced by the saved one, if systemd hands it over (load_key)


def load_key():
    """The key that signs sign-in cookies. It lives in a file only root can
    read (/etc/compaq/web-cookie.key); systemd opens it and hands this
    program the open file (OpenFile= in compaq-web.service), so the shared
    session's account, which this program runs as, can't read it. Without
    it, a random key: sign-ins then end when the server restarts. Also makes
    this process off-limits to the same account's debugging tools (it holds
    the key and the password hash in memory)."""
    global COOKIE_KEY
    try:
        ctypes.CDLL(None).prctl(4, 0, 0, 0, 0)     # PR_SET_DUMPABLE, 0
    except (OSError, AttributeError):
        pass
    names = os.environ.pop("LISTEN_FDNAMES", "").split(":")
    count = int(os.environ.pop("LISTEN_FDS", "0") or 0)
    os.environ.pop("LISTEN_PID", None)
    for i, name in enumerate(names[:count]):
        fd = 3 + i
        try:
            if name == "cookie-key":
                key = os.read(fd, 256).strip()
                if len(key) >= 32:
                    COOKIE_KEY = key
        except OSError:
            pass
        finally:
            try:
                os.close(fd)
            except OSError:
                pass


def login_mac(issued, current):
    return hmac.new(COOKIE_KEY, b"compaq-login:" + issued.encode() + b":" + current.encode(),
                    hashlib.sha256).hexdigest()


def make_token():
    """A sign-in cookie: when it was issued, signed with a key only this
    server knows, over the office password's stored hash. Nothing to
    remember, so sign-ins outlast a restart; a new password signs everyone
    out."""
    issued = f"{time.time():.6f}"
    return f"{issued}.{login_mac(issued, office_hash() or '')}"


def token_ok(token):
    current = office_hash()
    if not current or not token or token in signed_out:
        return False
    issued, _, mac = token.rpartition(".")
    try:
        age = time.time() - float(issued)
    except ValueError:
        return False
    # (a day's grace the other way: the Pi has no clock battery, so its time
    # can jump at start-up)
    return (-86400 < age < COOKIE_DAYS * 86400 and mac.isascii()
            and hmac.compare_digest(mac, login_mac(issued, current)))


def office_hash():
    """The stored hash, "pbkdf2_sha256$iterations$salt$digest", or None."""
    try:
        with open(Handler.password_file) as f:
            for line in f:
                key, _, value = line.strip().partition("=")
                if key == "OFFICE_PASSWORD":
                    return value
    except OSError:
        pass
    return None


def password_ok(password):
    stored = office_hash()
    try:
        _, iterations, salt, digest = stored.split("$")
    except (AttributeError, ValueError):
        return False
    test = hashlib.pbkdf2_hmac("sha256", password.encode(), bytes.fromhex(salt), int(iterations))
    return hmac.compare_digest(test.hex(), digest)


def picture_info():
    """The picture the Compaq is showing instead of the shared screen's text,
    if any: {"id", "caption"}."""
    try:
        with open(PICTURE + ".json") as f:
            info = json.load(f)
        return {"id": int(info["id"]), "caption": str(info.get("caption", ""))[:80]}
    except (OSError, ValueError, KeyError, TypeError):
        return None


def compaq_status():
    try:
        with open(STATUS_FILE) as f:
            return f.read().strip() or "not connected"
    except OSError:
        return "not connected"


class Viewer:
    """One browser's tmux client of the shared session, on its own 80x24 pty."""

    def __init__(self):
        self.pid, self.fd = pty.fork()
        if self.pid == 0:
            try:
                fcntl.ioctl(0, termios.TIOCSWINSZ, struct.pack("HHHH", 24, 80, 0, 0))
                env = dict(os.environ, TERM="vt102", LANG="C", LC_ALL="C")
                os.execvpe(TMUX[0], TMUX + ["attach-session", "-t", "compaq"], env)
            finally:
                os._exit(127)          # never a second copy of the server
        # Bounded: a browser that stops reading gets dropped, not buffered forever.
        self.output = queue.Queue(maxsize=256)
        self.claimed = False
        self.closed = False
        self.fd_open = True
        self.closing = threading.Lock()
        self.started = time.monotonic()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        """Copies the client's output to the queue. The only place the pty is
        closed, so send() can never write to a recycled descriptor."""
        try:
            while True:
                try:
                    data = os.read(self.fd, 4096)
                except OSError:
                    break
                if not data:
                    break
                try:
                    self.output.put(data, timeout=30)
                except queue.Full:
                    break
        finally:
            with self.closing:
                self.fd_open = False
                os.close(self.fd)
            try:
                self.output.put_nowait(None)
            except queue.Full:
                pass
            if not self.closed:
                self.close()

    def send(self, data):
        with self.closing:
            if self.fd_open:
                try:
                    os.write(self.fd, data)
                except OSError:
                    pass

    def close(self):
        # Called from /api/close, the stream's cleanup and _read; only the
        # first does anything. Ending the tmux client ends _read too.
        with self.closing:
            if self.closed:
                return
            self.closed = True
        try:
            os.kill(self.pid, signal.SIGTERM)
        except ProcessLookupError:
            pass
        try:
            os.waitpid(self.pid, 0)
        except ChildProcessError:
            pass


def publish_viewers():
    """How many browsers are watching, for the Compaq menu's header. Counted
    and written under the lock, so the last write is always the latest count."""
    with lock:
        count = sum(1 for v in viewers.values() if v.claimed)
        try:
            with open(VIEWERS_FILE + ".new", "w") as f:
                f.write(f"{count}\n")
            os.replace(VIEWERS_FILE + ".new", VIEWERS_FILE)
        except OSError:
            pass


def reap_unclaimed():
    while True:
        time.sleep(5)
        now = time.monotonic()
        with lock:
            stale = [i for i, v in viewers.items()
                     if not v.claimed and now - v.started > UNCLAIMED_SECONDS]
            closing = [viewers.pop(i) for i in stale]
        for viewer in closing:
            viewer.close()


class Handler(http.server.BaseHTTPRequestHandler):
    names = {"compaq.local", "compaq", "localhost"}
    password_file = PASSWORD_FILE
    # A connection that sends or reads nothing for this long is closed. The
    # screen stream writes at least every 5 seconds, so it never trips this.
    timeout = 30

    def log_message(self, *args):
        pass

    # ------------------------------------------------------------ checks

    def host_ok(self):
        """Answers only to the Pi's own names and addresses, which blocks DNS
        rebinding (another site's name pointed at the Pi)."""
        host = urllib.parse.urlsplit("//" + self.headers.get("Host", "")).hostname or ""
        if host.lower() in self.names:
            return True
        try:
            ipaddress.ip_address(host)
            return True
        except ValueError:
            return False

    def allowed(self, post):
        ok = self.host_ok()
        if post:
            # Other sites' pages can't send a custom header without a CORS
            # preflight, which this server never approves.
            origin = self.headers.get("Origin")
            if origin is not None:
                ok = ok and urllib.parse.urlsplit(origin).netloc == self.headers.get("Host")
            ok = ok and self.headers.get(HEADER) == "1"
        if not ok:
            self.send_error(403)
        return ok

    def token(self):
        cookies = http.cookies.SimpleCookie(self.headers.get("Cookie", ""))
        return cookies[COOKIE].value if COOKIE in cookies else None

    def logged_in(self):
        return token_ok(self.token())

    # ------------------------------------------------------------ routes

    def do_GET(self):
        if not self.allowed(post=False):
            return
        if self.path in FILES:
            name, kind = FILES[self.path]
            # The terminal library and font never change between deploys of
            # the same version; let browsers keep them rather than re-fetch
            # 300 KB over the Pi Zero's Wi-Fi on every visit.
            cache = "public, max-age=86400" if self.path.startswith("/vendor/") else "no-cache"
            self.send_body((HERE / name).read_bytes(), kind, cache=cache)
        elif self.path == "/api/state":
            self.reply({"setUp": office_hash() is not None, "signedIn": self.logged_in(),
                        "compaq": compaq_status()})
        elif self.path.startswith("/api/stream/"):
            if not self.logged_in():
                return self.send_error(401)
            self.stream(self.path.rsplit("/", 1)[-1])
        elif self.path.startswith("/api/picture/"):
            if not self.logged_in():
                return self.send_error(401)
            current = picture_info()
            if not current or self.path != f"/api/picture/{current['id']}":
                return self.send_error(404)
            try:
                with open(PICTURE + ".png", "rb") as f:
                    body = f.read(1_000_000)
            except OSError:
                return self.send_error(404)
            self.send_body(body, "image/png", cache="private, max-age=600")
        else:
            self.send_error(404)

    def do_POST(self):
        if not self.allowed(post=True):     # checked before reading a byte of the body
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= MAX_BODY:
            return self.send_error(413 if length > MAX_BODY else 400)
        body = self.rfile.read(length)
        if self.path == "/api/login":
            return self.login(body)
        if self.path == "/api/logout":
            token = self.token()
            if token_ok(token):
                with lock:
                    signed_out[token] = time.time()
                    for old in [t for t, at in signed_out.items() if time.time() - at > COOKIE_DAYS * 86400]:
                        del signed_out[old]
            return self.reply({"ok": True}, cookie=f"{COOKIE}=; Max-Age=0; Path=/; HttpOnly; SameSite=Strict")
        if not self.logged_in():
            return self.send_error(401)
        if self.path == "/api/viewer":
            with lock:
                if len(viewers) >= MAX_VIEWERS:
                    return self.send_error(429, "Too many people are connected")
                viewer_id = secrets.token_hex(16)
                viewers[viewer_id] = Viewer()
            self.reply({"id": viewer_id})
        elif self.path.startswith("/api/input/"):
            viewer = viewers.get(self.path.rsplit("/", 1)[-1])
            if viewer:
                viewer.send(body)
            self.reply({"ok": bool(viewer)})
        elif self.path.startswith("/api/close/"):
            with lock:
                viewer = viewers.pop(self.path.rsplit("/", 1)[-1], None)
            if viewer:
                viewer.close()
            self.reply({"ok": True})
        else:
            self.send_error(404)

    def login(self, body):
        address = self.client_address[0]
        now = time.monotonic()
        # The try is counted before the (slow) check, so a burst of parallel
        # guesses can't all slip under the limit.
        with lock:
            for key in list(attempts):
                attempts[key] = [t for t in attempts[key] if now - t < LOGIN_LIMIT[1]]
                if not attempts[key]:
                    del attempts[key]
            mine = attempts.setdefault(address, [])
            everyone = sum(len(times) for times in attempts.values())
            if len(mine) >= LOGIN_LIMIT[0] or everyone >= LOGIN_LIMIT_ALL[0]:
                return self.reply({"ok": False, "message": "Too many tries. Wait five minutes."}, 429)
            mine.append(now)
        try:
            password = str(json.loads(body or b"{}").get("password", ""))[:200]
        except (ValueError, AttributeError):
            password = ""
        with hashing:
            ok = password_ok(password)
        if not ok:
            return self.reply({"ok": False, "message": "That's not the office password."}, 403)
        with lock:
            if now in attempts.get(address, []):
                attempts[address].remove(now)
            for old in [t for t, at in signed_out.items() if time.time() - at > COOKIE_DAYS * 86400]:
                del signed_out[old]
        token = make_token()
        cookie = (f"{COOKIE}={token}; Max-Age={COOKIE_DAYS * 86400}; Path=/; "
                  "HttpOnly; SameSite=Strict")
        self.reply({"ok": True}, cookie=cookie)

    def stream(self, viewer_id):
        """The shared screen as server-sent events: base64 output, plus an
        "info" event with who's here and whether the Compaq is plugged in."""
        with lock:
            viewer = viewers.get(viewer_id)
            if viewer and viewer.claimed:
                viewer = None
            if viewer:
                viewer.claimed = True
        if not viewer:
            return self.send_error(404)
        publish_viewers()
        # Notice browsers that vanish without closing (a laptop going to
        # sleep) within a couple of minutes, so the watching count is right.
        sock = self.connection
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_KEEPALIVE, 1)
        for option, value in (("TCP_KEEPIDLE", 60), ("TCP_KEEPINTVL", 15), ("TCP_KEEPCNT", 4)):
            if hasattr(socket, option):
                sock.setsockopt(socket.IPPROTO_TCP, getattr(socket, option), value)
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            self.send_info()
            picture, told = picture_info(), time.monotonic()
            while True:
                try:
                    data = viewer.output.get(timeout=1)
                except queue.Empty:
                    data = b""
                # News: a picture went up or came down (checked every
                # second), or every 5 quiet seconds, who's here.
                if picture_info() != picture or (not data and time.monotonic() - told >= 5):
                    if not self.logged_in():      # signed out, or the password changed
                        break
                    picture, told = self.send_info(), time.monotonic()
                if data == b"":
                    continue
                if data is None:
                    self.wfile.write(b"event: end\ndata: 0\n\n")
                    self.wfile.flush()
                    break
                while not viewer.output.empty() and viewer.output.queue[0] is not None:
                    data += viewer.output.get()
                self.wfile.write(b"data: " + base64.b64encode(data) + b"\n\n")
                self.wfile.flush()
        except OSError:          # the browser went away, or stopped reading (timeout)
            pass
        finally:
            with lock:
                viewers.pop(viewer_id, None)
            viewer.close()
            publish_viewers()

    def send_info(self):
        """Who's here, the Compaq's cable, and any picture; returns the picture."""
        info = {"viewers": len(viewers), "compaq": compaq_status(), "picture": picture_info()}
        self.wfile.write(f"event: info\ndata: {json.dumps(info)}\n\n".encode())
        self.wfile.flush()
        return info["picture"]

    # ------------------------------------------------------------ helpers

    def send_body(self, body, kind, status=200, cookie=None, cache="no-cache"):
        self.send_response(status)
        self.send_header("Content-Type", kind)
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", cache)
        self.send_header("X-Frame-Options", "DENY")
        if cookie:
            self.send_header("Set-Cookie", cookie)
        self.end_headers()
        self.wfile.write(body)

    def reply(self, data, status=200, cookie=None):
        self.send_body(json.dumps(data).encode(), "application/json", status, cookie)


class Server(http.server.ThreadingHTTPServer):
    """One thread per connection, up to MAX_CONNECTIONS; more are dropped,
    so a flood of idle connections can't use up the Pi. One computer gets
    at most MAX_PER_ADDRESS of them, so it can't hold every place by
    opening connections and saying nothing (nobody else could reach the
    page, signed in or not)."""

    daemon_threads = True
    slots = threading.BoundedSemaphore(MAX_CONNECTIONS)
    open_from = {}                # address -> connections open from it
    counting = threading.Lock()

    def take(self, address):
        with self.counting:
            if self.open_from.get(address, 0) >= MAX_PER_ADDRESS:
                return False
            if not self.slots.acquire(blocking=False):
                return False
            self.open_from[address] = self.open_from.get(address, 0) + 1
            return True

    def give_back(self, address):
        with self.counting:
            left = self.open_from.get(address, 1) - 1
            if left > 0:
                self.open_from[address] = left
            else:
                self.open_from.pop(address, None)
        self.slots.release()

    def process_request(self, request, client_address):
        if not self.take(client_address[0]):
            self.shutdown_request(request)
            return
        try:
            super().process_request(request, client_address)
        except Exception:
            self.give_back(client_address[0])
            raise

    def process_request_thread(self, request, client_address):
        try:
            super().process_request_thread(request, client_address)
        finally:
            self.give_back(client_address[0])


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=80)
    parser.add_argument("--bind", default="", help="address to listen on (default: all)")
    parser.add_argument("--password-file", default=PASSWORD_FILE, help=argparse.SUPPRESS)
    args = parser.parse_args()
    load_key()
    Handler.password_file = args.password_file
    hostname = socket.gethostname().lower()
    Handler.names |= {hostname, f"{hostname}.local"}

    server = Server((args.bind, args.port), Handler)
    threading.Thread(target=reap_unclaimed, daemon=True).start()
    publish_viewers()
    print(f"Compaq on the web: listening on port {args.port}", flush=True)
    server.serve_forever()


if __name__ == "__main__":
    main()

#!/usr/bin/env python3
"""Virtual Compaq: previews the Compaq's screen on the Mac.

Serves a page styled like the Compaq Portable III's amber plasma display. The
page plays the Compaq's part (a DOS prompt, then MS-DOS Kermit), and each
Kermit connection here opens an SSH session to the Pi running the same menu
the serial cable runs: 80x24, VT100, plain ASCII. Only the login is skipped,
since SSH already uses the Mac's key.

Usage: python3 server.py [--open] [--port 8086] [--pi pizero]
Then browse to http://127.0.0.1:8086 (--open does that for you).
"""

import argparse
import base64
import http.server
import json
import os
import queue
import secrets
import subprocess
import threading
import time
import webbrowser
from pathlib import Path

HERE = Path(__file__).resolve().parent
FILES = {
    "/": ("index.html", "text/html; charset=utf-8"),
    "/vendor/xterm.js": ("vendor/xterm.js", "text/javascript"),
    "/vendor/xterm.css": ("vendor/xterm.css", "text/css"),
    "/vendor/Compaq_Port3.woff": ("vendor/Compaq_Port3.woff", "font/woff"),
}
# The shared Compaq session, joined the way the Compaq's cable joins it: as
# the limited "desk" account, 80x24, VT100, plain ASCII. So this window shows
# the same screen as the real Compaq and http://compaq.local.
REMOTE = ("stty rows 24 cols 80; exec sudo -u desk env TERM=vt102 LANG=C LC_ALL=C "
          "tmux -L compaq attach-session -t compaq")

MAX_SESSIONS = 4
UNCLAIMED_SECONDS = 15   # a session nobody starts reading within this is closed
# Every POST must carry this header. Browsers won't let another site's page
# send a custom header here, so only this page can open sessions or type.
TOKEN_HEADER = "X-Virtual-Compaq"

sessions = {}
sessions_lock = threading.Lock()


class Session:
    """One SSH connection to the Pi's menu."""

    def __init__(self, pi):
        self.proc = subprocess.Popen(
            ["ssh", "-tt", "-q", "-e", "none", "-o", "BatchMode=yes",
             "-o", "ConnectTimeout=10", "-o", "ServerAliveInterval=15", pi, REMOTE],
            stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            bufsize=0)
        self.output = queue.Queue()
        self.claimed = False
        self.started = time.monotonic()
        threading.Thread(target=self._read, daemon=True).start()

    def _read(self):
        while True:
            data = os.read(self.proc.stdout.fileno(), 4096)
            if not data:
                break
            self.output.put(data)
        self.output.put(None)

    def send(self, data):
        try:
            self.proc.stdin.write(data)
            self.proc.stdin.flush()
        except (BrokenPipeError, ValueError):
            pass

    def close(self):
        if self.proc.poll() is None:
            self.proc.terminate()
            try:
                self.proc.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.proc.kill()


def reap_unclaimed():
    """Closes sessions whose page never started reading them."""
    while True:
        time.sleep(5)
        now = time.monotonic()
        with sessions_lock:
            stale = [i for i, s in sessions.items()
                     if not s.claimed and now - s.started > UNCLAIMED_SECONDS]
            closing = [sessions.pop(i) for i in stale]
        for session in closing:
            session.close()


class Handler(http.server.BaseHTTPRequestHandler):
    pi = "pizero"
    port = 8086

    def log_message(self, *args):
        pass

    def allowed(self, post):
        """Only this page may use the server. Checking Host blocks DNS
        rebinding; the header and Origin checks block other sites' pages."""
        hosts = {f"127.0.0.1:{self.port}", f"localhost:{self.port}"}
        ok = self.headers.get("Host") in hosts
        origin = self.headers.get("Origin")
        if origin is not None:
            ok = ok and origin in {f"http://{h}" for h in hosts}
        if post:
            ok = ok and self.headers.get(TOKEN_HEADER) == "1"
        if not ok:
            self.send_error(403)
        return ok

    def do_GET(self):
        if not self.allowed(post=False):
            return
        if self.path in FILES:
            name, kind = FILES[self.path]
            body = (HERE / name).read_bytes()
            self.send_response(200)
            self.send_header("Content-Type", kind)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()
            self.wfile.write(body)
        elif self.path.startswith("/api/stream/"):
            self.stream(self.path.rsplit("/", 1)[-1])
        else:
            self.send_error(404)

    def do_POST(self):
        if not self.allowed(post=True):     # checked before reading a byte of the body
            return
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            length = -1
        if not 0 <= length <= 65536:
            return self.send_error(400)
        body = self.rfile.read(length)
        if self.path == "/api/session":
            with sessions_lock:
                if len(sessions) >= MAX_SESSIONS:
                    self.send_error(429, "Too many Virtual Compaq windows are open")
                    return
                session_id = secrets.token_hex(16)
                sessions[session_id] = Session(self.pi)
            self.reply({"id": session_id})
        elif self.path.startswith("/api/input/"):
            session = sessions.get(self.path.rsplit("/", 1)[-1])
            if session:
                session.send(body)
            self.reply({"ok": bool(session)})
        elif self.path.startswith("/api/close/"):
            with sessions_lock:
                session = sessions.pop(self.path.rsplit("/", 1)[-1], None)
            if session:
                session.close()
            self.reply({"ok": True})
        else:
            self.send_error(404)

    def reply(self, data):
        body = json.dumps(data).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def stream(self, session_id):
        """The Pi's output as server-sent events, base64 encoded."""
        with sessions_lock:
            session = sessions.get(session_id)
            if session and session.claimed:
                session = None   # each session has one reader
            if session:
                session.claimed = True
        if not session:
            self.send_error(404)
            return
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Cache-Control", "no-cache")
        self.end_headers()
        try:
            while True:
                try:
                    data = session.output.get(timeout=15)
                except queue.Empty:
                    self.wfile.write(b": still here\n\n")
                    self.wfile.flush()
                    continue
                if data is None:
                    code = session.proc.wait()
                    self.wfile.write(f"event: end\ndata: {code}\n\n".encode())
                    self.wfile.flush()
                    break
                while not session.output.empty() and session.output.queue[0] is not None:
                    data += session.output.get()
                self.wfile.write(b"data: " + base64.b64encode(data) + b"\n\n")
                self.wfile.flush()
        except (BrokenPipeError, ConnectionResetError):
            pass
        finally:
            with sessions_lock:
                sessions.pop(session_id, None)
            session.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--port", type=int, default=8086)
    parser.add_argument("--pi", default="pizero", help="SSH host for the Pi")
    parser.add_argument("--open", action="store_true", help="open it in the browser")
    args = parser.parse_args()
    Handler.pi = args.pi
    Handler.port = args.port

    url = f"http://127.0.0.1:{args.port}"
    try:
        server = http.server.ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    except OSError:  # already running: just show it
        print(f"Virtual Compaq is already running at {url}")
        if args.open:
            webbrowser.open(url)
        return
    server.daemon_threads = True
    threading.Thread(target=reap_unclaimed, daemon=True).start()
    print(f"Virtual Compaq is running at {url}  (Ctrl-C here to stop it)")
    if args.open:
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        for session in list(sessions.values()):
            session.close()


if __name__ == "__main__":
    main()

# Exercises the Compaq web server end to end against a temporary copy on
# 127.0.0.1:8099 that uses a throwaway password (never printed). Runs on the Pi.
import base64, hashlib, http.client, json, os, secrets, subprocess, time

TEST = "/tmp/compaq-web-test"
os.makedirs(TEST, exist_ok=True)
os.chmod(TEST, 0o755)
password = secrets.token_urlsafe(12)
salt = os.urandom(16)
digest = hashlib.pbkdf2_hmac("sha256", password.encode(), salt, 100000).hex()
with open(f"{TEST}/web.env", "w") as f:
    f.write(f"OFFICE_PASSWORD=pbkdf2_sha256${100000}${salt.hex()}${digest}\n")
os.chmod(f"{TEST}/web.env", 0o644)
with open(f"{TEST}/password", "w") as f:   # for the browser check; deleted afterwards
    f.write(password)
os.chmod(f"{TEST}/password", 0o600)

server = subprocess.Popen(["sudo", "-u", "desk", "python3", "/opt/compaq/web/server.py",
                           "--port", "8099", "--bind", "127.0.0.1",
                           "--password-file", f"{TEST}/web.env"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
time.sleep(2)

def call(method, path, body=None, cookie=None, headers=None):
    conn = http.client.HTTPConnection("127.0.0.1", 8099, timeout=10)
    h = {"X-Compaq": "1", "Host": "127.0.0.1:8099"}
    if cookie:
        h["Cookie"] = cookie
    h.update(headers or {})
    conn.request(method, path, body=body, headers=h)
    r = conn.getresponse()
    return r.status, r.getheader("Set-Cookie"), r.read()

def screen():
    return subprocess.run(["sudo", "-u", "desk", "tmux", "-L", "compaq", "capture-pane", "-p", "-t", "compaq"],
                          capture_output=True, text=True).stdout

try:
    s, _, b = call("POST", "/api/login", json.dumps({"password": "wrong-guess"}))
    print("wrong password       ->", s, json.loads(b)["message"])
    s, set_cookie, _ = call("POST", "/api/login", json.dumps({"password": password}))
    cookie = set_cookie.split(";")[0]
    print("right password       ->", s, "| cookie is HttpOnly and SameSite=Strict:",
          "HttpOnly" in set_cookie and "SameSite=Strict" in set_cookie)
    s, _, b = call("GET", "/api/state", cookie=cookie)
    print("state when signed in ->", s, b.decode())
    s, _, b = call("POST", "/api/viewer", cookie=cookie)
    viewer = json.loads(b)["id"]
    print("open a viewer        ->", s)

    # Read the stream for a few seconds, like the page's EventSource does.
    conn = http.client.HTTPConnection("127.0.0.1", 8099, timeout=10)
    conn.request("GET", f"/api/stream/{viewer}", headers={"Cookie": cookie, "Host": "127.0.0.1:8099"})
    stream = conn.getresponse()
    out, info, start = b"", None, time.time()
    stream.fp.raw._sock.settimeout(1)
    while time.time() - start < 4:
        try:
            line = stream.fp.readline()
        except Exception:
            continue
        if line.startswith(b"data: {"):
            info = line[6:].strip().decode()
        elif line.startswith(b"data: "):
            out += base64.b64decode(line[6:].strip())
    print("stream info event    ->", info)
    print("screen via the web contains the welcome text:", b"Press Enter to start" in out)

    # Type through the web: Enter, then 5 (Games).
    for keys in ("\r", "5\r"):
        call("POST", f"/api/input/{viewer}", keys.encode(), cookie=cookie)
        time.sleep(1.5)
    shown = screen()
    print("after typing Enter, 5, Enter, the shared screen shows GAMES:", "GAMES" in shown)
    call("POST", f"/api/input/{viewer}", b"0\r", cookie=cookie)
    time.sleep(1)
    call("POST", f"/api/input/{viewer}", b"0\r", cookie=cookie)   # sign off -> welcome
    time.sleep(1.5)
    print("signing off returns to the welcome screen:", "Press Enter to start" in screen())

    s, _, _ = call("POST", f"/api/close/{viewer}", cookie=cookie)
    s, _, _ = call("POST", "/api/logout", cookie=cookie)
    s, _, _ = call("POST", "/api/viewer", cookie=cookie)
    print("after sign-out, opening a viewer ->", s)
    codes = [call("POST", "/api/login", json.dumps({"password": "guess"}))[0] for _ in range(6)]
    print("six wrong guesses in a row ->", codes)
finally:
    subprocess.run(["sudo", "pkill", "-f", "server.py --port 8099"])

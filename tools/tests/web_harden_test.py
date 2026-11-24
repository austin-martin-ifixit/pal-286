# The web server's new defences, against a throwaway copy on 127.0.0.1:8099
# with a throwaway password (never printed). Runs on the Pi as root.
import base64, concurrent.futures, hashlib, http.client, json, os, secrets, socket, subprocess, time

TEST = "/tmp/compaq-web-test"
os.makedirs(TEST, exist_ok=True); os.chmod(TEST, 0o755)
def set_password(pw):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 100000).hex()
    with open(f"{TEST}/web.env.new", "w") as f:
        f.write(f"OFFICE_PASSWORD=pbkdf2_sha256${100000}${salt.hex()}${digest}\n")
    os.chmod(f"{TEST}/web.env.new", 0o644); os.replace(f"{TEST}/web.env.new", f"{TEST}/web.env")
password = secrets.token_urlsafe(12); set_password(password)
server = subprocess.Popen(["sudo", "-u", "desk", "python3", "-I", "/opt/compaq/web/server.py", "--port", "8099",
                           "--bind", "127.0.0.1", "--password-file", f"{TEST}/web.env"],
                          stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
time.sleep(2)

def call(method, path, body=None, cookie=None, length=None):
    conn = http.client.HTTPConnection("127.0.0.1", 8099, timeout=40)
    conn.putrequest(method, path)
    conn.putheader("Host", "127.0.0.1:8099"); conn.putheader("X-Compaq", "1")
    if cookie: conn.putheader("Cookie", cookie)
    data = body.encode() if isinstance(body, str) else (body or b"")
    conn.putheader("Content-Length", str(len(data)) if length is None else length)
    conn.endheaders(); conn.send(data)
    r = conn.getresponse(); out = (r.status, r.getheader("Set-Cookie"), r.read()); conn.close()
    return out

try:
    status, cookie, _ = call("POST", "/api/login", json.dumps({"password": password}))
    cookie = cookie.split(";")[0]
    print("1. right password signs in:", status == 200)
    print("2. bad body sizes refused before reading:",
          [call("POST", "/api/input/x", cookie=cookie, length=v)[0] for v in ("-1", "70000", "abc")])
    status, _, body = call("POST", "/api/viewer", cookie=cookie)
    viewer = json.loads(body)["id"]
    conn = http.client.HTTPConnection("127.0.0.1", 8099, timeout=20)
    conn.request("GET", f"/api/stream/{viewer}", headers={"Host": "127.0.0.1:8099", "Cookie": cookie})
    stream = conn.getresponse()
    got = stream.fp.readline()
    print("3. the screen streams:", stream.status == 200 and bool(got))
    set_password(secrets.token_urlsafe(12))          # the owner changes the office password
    start = time.time(); ended = False
    while time.time() - start < 15:
        line = stream.fp.readline()
        if not line: ended = True; break
    print(f"4. changing the password ends the open screen: {ended} (after {time.time()-start:.0f} s)")
    conn.close()
    set_password(password)
    with concurrent.futures.ThreadPoolExecutor(12) as pool:
        codes = list(pool.map(lambda _: call("POST", "/api/login", '{"password": "wrong"}')[0], range(12)))
    print("5. 12 guesses at once: wrong-password answers", codes.count(403), "| refused", codes.count(429))
    socks = []
    for _ in range(70):
        s = socket.create_connection(("127.0.0.1", 8099)); socks.append(s)
    time.sleep(1)
    closed = 0
    for s in socks:
        s.settimeout(0.2)
        try:
            if s.recv(1) == b"": closed += 1
        except socket.timeout:
            pass
    print("6. 70 idle connections: dropped at once", closed, "(the cap is 64, less those still open)")
    t = time.time(); socks[0].settimeout(40)
    try: socks[0].recv(1)
    except OSError: pass
    print(f"7. an idle connection is closed after {time.time()-t:.0f} s")
    for s in socks: s.close()
finally:
    server.terminate(); server.wait()
    subprocess.run(["rm", "-rf", TEST])
    err = server.stderr.read().decode()
    print("server errors:", err.strip()[-300:] or "none")

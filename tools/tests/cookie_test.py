# Web sign-in cookies signed with a key systemd hands over: a throwaway
# server on 127.0.0.1:8099 with a throwaway password and key. Root on the Pi.
import hashlib, hmac, http.client, json, os, secrets, subprocess, time

TEST = "/tmp/compaq-cookie-test"
os.makedirs(TEST, exist_ok=True); os.chmod(TEST, 0o755)
KEY = f"{TEST}/key"
with open(KEY, "w") as f:
    f.write(secrets.token_urlsafe(48))
os.chmod(KEY, 0o600)                     # root's alone, like the real one


def set_password(pw):
    salt = os.urandom(16)
    digest = hashlib.pbkdf2_hmac("sha256", pw.encode(), salt, 100000).hex()
    with open(f"{TEST}/web.env.new", "w") as f:
        f.write(f"OFFICE_PASSWORD=pbkdf2_sha256${100000}${salt.hex()}${digest}\n")
    os.chmod(f"{TEST}/web.env.new", 0o644); os.replace(f"{TEST}/web.env.new", f"{TEST}/web.env")


def start():
    subprocess.run(["systemd-run", "--quiet", "--unit=compaq-cookie-test", "-p", "User=desk",
                    "-p", f"OpenFile={KEY}:cookie-key:read-only", "/usr/bin/python3", "-I",
                    "/opt/compaq/web/server.py", "--port", "8099", "--bind", "127.0.0.1",
                    "--password-file", f"{TEST}/web.env"], check=True)
    time.sleep(2.5)


def stop():
    subprocess.run(["systemctl", "stop", "compaq-cookie-test"], capture_output=True)
    time.sleep(1)


def call(method, path, body=b"", cookie=None):
    conn = http.client.HTTPConnection("127.0.0.1", 8099, timeout=30)
    conn.putrequest(method, path)
    conn.putheader("Host", "127.0.0.1:8099"); conn.putheader("X-Compaq", "1")
    if cookie: conn.putheader("Cookie", cookie)
    conn.putheader("Content-Length", str(len(body))); conn.endheaders(); conn.send(body)
    r = conn.getresponse(); out = (r.status, r.getheader("Set-Cookie"), r.read()); conn.close()
    return out


def signed_in(cookie):
    return json.loads(call("GET", "/api/state", cookie=cookie)[2])["signedIn"]


password = secrets.token_urlsafe(12); set_password(password)
stop(); start()
try:
    status, set_cookie, _ = call("POST", "/api/login", json.dumps({"password": password}).encode())
    cookie = set_cookie.split(";")[0]
    print("signed in:", status == 200 and signed_in(cookie))
    stop(); start()
    print("still signed in after a restart:", signed_in(cookie))
    # A cookie made the old way (signed with the stored hash, which desk can read).
    stored = open(f"{TEST}/web.env").read().strip().split("=", 1)[1]
    issued = f"{time.time():.6f}"
    forged = "compaq_session=" + issued + "." + hmac.new(stored.encode(), b"compaq-login:" + issued.encode(),
                                                         hashlib.sha256).hexdigest()
    print("forged cookie refused:", not signed_in(forged))
    pid = subprocess.run(["systemctl", "show", "-p", "MainPID", "--value", "compaq-cookie-test"],
                         capture_output=True, text=True).stdout.strip()
    peek = subprocess.run(["sudo", "-u", "desk", "cat", f"/proc/{pid}/environ"], capture_output=True)
    print("desk can't read the server's process:", peek.returncode != 0,
          f"({peek.stderr.decode().strip()[:60]})")
    peek = subprocess.run(["sudo", "-u", "desk", "cat", KEY], capture_output=True)
    print("desk can't read the key file:", peek.returncode != 0)
    call("POST", "/api/logout", cookie=cookie)
    print("signed out after logout:", not signed_in(cookie))
    status, set_cookie, _ = call("POST", "/api/login", json.dumps({"password": password}).encode())
    cookie = set_cookie.split(";")[0]
    set_password(secrets.token_urlsafe(12))
    print("a new password signs everyone out:", not signed_in(cookie))
finally:
    stop()
    subprocess.run(["rm", "-rf", TEST])

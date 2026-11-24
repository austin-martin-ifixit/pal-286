# Passers-by: someone walks across the camera's view without facing it; the
# lights flicker; nobody's there. Runs as pal on the Pi against the simulator
# (PASSERBY_MINUTES=1).
# Usage: passerby_test.py  (after: bash run_sim.sh with pal-sim-passerby.conf)
import glob, os, time
import cv2
import numpy as np

SIM = "/tmp/pal-sim/"
CAM = SIM + "camera/current.jpg"
rng = np.random.default_rng(3)
base = np.full((480, 640, 3), 150, np.uint8)
base[300:, :] = 110                                   # a floor
base[60:260, 420:600] = (90, 120, 160)                # a door
base = cv2.add(base, rng.integers(0, 12, base.shape, dtype=np.uint8))


def put(image):
    cv2.imwrite(CAM + ".new.jpg", image)
    os.replace(CAM + ".new.jpg", CAM)


def walk(seconds=4.0):
    """A dark, person-sized shape crossing from left to right."""
    start = time.time()
    while time.time() - start < seconds:
        x = int(-120 + (time.time() - start) / seconds * 800)
        frame = base.copy()
        cv2.rectangle(frame, (x, 120), (x + 110, 470), (40, 40, 50), -1)
        cv2.circle(frame, (x + 55, 95), 38, (60, 60, 70), -1)   # a head, from behind
        put(frame)
        time.sleep(0.1)
    put(base)


def log():
    return open(SIM + "pal.log").read()


def said():
    return [open(f).read().strip() for f in sorted(glob.glob(SIM + "said/*.txt"))]


put(base)
time.sleep(70)          # past the start-up quiet minute, the room learned
before = log().count("passer-by")
print("1. lights flicker (the whole picture changes)")
for level in (60, -60, 40, -40):
    shift = (abs(level),) * 3 + (0,)
    put(cv2.add(base, shift) if level > 0 else cv2.subtract(base, shift))
    time.sleep(0.6)
put(base)
time.sleep(5)
print("   no shout-out:", log().count("passer-by") == before)

print("2. someone walks past")
walk()
time.sleep(8)
first = log().count("passer-by")
print("   shout-out:", first > before, "|", said()[-1:] if first > before else "")

print("3. someone else, 20 seconds later (too soon)")
time.sleep(20)
walk()
time.sleep(6)
print("   held back:", log().count("passer-by") == first)

print("4. someone fidgeting in view for 15 seconds (not a passer-by)")
end = time.time() + 15
while time.time() < end:
    walk(1.5)
time.sleep(5)
print("   held back:", log().count("passer-by") == first)

print("5. someone else, after the gap (doubled: nobody stopped last time)")
time.sleep(190)
walk()
time.sleep(10)
print("   shout-out:", log().count("passer-by") > first, "|", said()[-1:])
os.remove(CAM)

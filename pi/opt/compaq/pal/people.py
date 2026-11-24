"""The people PAL knows: only those who taught it their face themselves, at
the Compaq menu (PAL 286, Teach PAL your face).

For each: a name, how to say it, a few face signatures (128 numbers each,
worked out from the camera; no photo is ever kept), short notes PAL keeps
from their chats, and when PAL last saw and greeted them. It all lives in
PAL's state directory, which only PAL's own account can read.
"""

import json
import os
import threading
import time
import uuid

import numpy as np

HOME = os.environ.get("STATE_DIRECTORY", "/var/lib/compaq-pal")
# Two signatures this similar (cosine, -1 to 1) are the same person. SFace's
# authors suggest 0.363; a little stricter avoids calling Joe "Maria".
SAME_PERSON = 0.42


def normalise(vector):
    vector = np.asarray(vector, dtype=np.float32).ravel()
    return vector / (np.linalg.norm(vector) or 1.0)


class People:
    def __init__(self, home=HOME):
        self.lock = threading.RLock()
        self.path = os.path.join(home, "people.json")
        self.faces_dir = os.path.join(home, "faces")
        os.makedirs(self.faces_dir, mode=0o700, exist_ok=True)
        try:
            with open(self.path) as f:
                self.people = json.load(f)
        except (OSError, ValueError):
            self.people = {}
        self.faces = {}
        for pid in list(self.people):
            try:
                self.faces[pid] = np.load(os.path.join(self.faces_dir, pid + ".npy"))
            except (OSError, ValueError):
                del self.people[pid]   # no signatures: can't recognise them

    def save(self):
        with self.lock:
            tmp = self.path + ".new"
            with open(tmp, "w") as f:
                json.dump(self.people, f, indent=1)
            os.replace(tmp, self.path)

    def match(self, signature):
        """(person id, similarity) for the closest known face, or (None, best)."""
        signature = normalise(signature)
        best, best_score = None, -1.0
        with self.lock:
            for pid, faces in self.faces.items():
                score = float(np.max(faces @ signature))
                if score > best_score:
                    best, best_score = pid, score
        return (best, best_score) if best_score >= SAME_PERSON else (None, best_score)

    def add(self, name, say_as, signatures, pid=None):
        """Adds someone, or (given pid) refreshes their face and name."""
        faces = np.stack([normalise(s) for s in signatures])
        with self.lock:
            if pid in self.people:
                faces = np.concatenate([self.faces[pid], faces])[-12:]
                self.people[pid].update(name=name, say_as=say_as)
            else:
                pid = uuid.uuid4().hex[:12]
                self.people[pid] = {"name": name, "say_as": say_as, "notes": "",
                                    "enrolled": time.strftime("%Y-%m-%d"),
                                    "last_seen": 0, "last_greeted": 0, "visits": 0}
            np.save(os.path.join(self.faces_dir, pid + ".npy"), faces)
            self.faces[pid] = faces
            self.save()
        return pid

    def forget(self, pid):
        """Removes everything PAL keeps about someone."""
        with self.lock:
            self.people.pop(pid, None)
            self.faces.pop(pid, None)
            try:
                os.remove(os.path.join(self.faces_dir, pid + ".npy"))
            except FileNotFoundError:
                pass
            self.save()

    def get(self, pid):
        with self.lock:
            return dict(self.people.get(pid, {}))

    def update(self, pid, **fields):
        with self.lock:
            if pid in self.people:
                self.people[pid].update(fields)
                self.save()

    def count(self):
        return len(self.people)

    def names(self):
        with self.lock:
            return sorted((p["name"], pid) for pid, p in self.people.items())

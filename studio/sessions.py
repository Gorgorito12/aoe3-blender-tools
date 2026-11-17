# SPDX-License-Identifier: GPL-3.0-or-later
"""What a screen has loaded and keeps between calls (a unit with its texture and its islands, a
measured flag set), by id. Old ones are dropped: a few at a time, an hour after their last use."""
import secrets
import threading
import time

KEEP = 8
IDLE = 3600


class Sessions:
    def __init__(self):
        self.items = {}
        self.lock = threading.Lock()

    def add(self, value):
        sid = secrets.token_hex(8)
        with self.lock:
            self._drop_old()
            self.items[sid] = [value, time.time()]
        return sid

    def get(self, sid):
        with self.lock:
            item = self.items.get(sid or "")
            if item is None:
                raise KeyError("this work is no longer loaded: load it again")
            item[1] = time.time()
            return item[0]

    def _drop_old(self):
        now = time.time()
        for sid in [k for k, (_v, t) in self.items.items() if now - t > IDLE]:
            del self.items[sid]
        while len(self.items) >= KEEP:
            del self.items[min(self.items, key=lambda k: self.items[k][1])]

"""Keeps the live sound across restarts of the controller.

The pedal restarts its audio chain when the audio interface changes (melon-audio), after a crash or a reboot.
Every couple of seconds the current sound (Pedal.snapshot(): chain, values, selected block, bypass, the preset
it came from) is written to a small JSON file, but only when it changed. At start the controller loads it again,
so the pedal comes back exactly as it was, unsaved edits included. --preset N or --plugin X still win.
"""
import json
import os
import threading
import time

STATE_PATH = os.path.expanduser("~/.config/melon-pedald/state.json")


class StateKeeper:
    def __init__(self, path, pedal, interval=2.0):
        self.path = path
        self.pedal = pedal
        self.interval = interval
        self.last = None

    def read(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return None
        except (OSError, ValueError) as e:
            print(f"! could not read the last sound ({e})")
            return None
        return data if isinstance(data, dict) else None

    def save_now(self):
        with self.pedal.lock:
            snap = self.pedal.snapshot()
        text = json.dumps(snap, indent=1, sort_keys=True)
        if text == self.last:
            return False
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            f.write(text)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)
        self.last = text
        return True

    def start(self):
        def loop():
            while True:
                try:
                    self.save_now()
                except Exception as e:      # never let this stop the pedal
                    print(f"! could not save the last sound ({e})")
                time.sleep(self.interval)
        threading.Thread(target=loop, daemon=True, name="state-keeper").start()

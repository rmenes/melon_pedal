"""Preset storage: 24 slots (4 banks of 6) in one JSON file.

A preset = plugin URI + parameter values + name, plus "files": the NAM / IR file of
Melon NAM / Melon Cab as a path inside the library folder (the index alone would
point at another file once files are added). The file is written to a
temporary file first and then renamed, so pulling the plug can't leave a
half-written file.
"""
import json
import os
import time

DEFAULT_PATH = os.path.expanduser("~/.config/melon-pedald/presets.json")
BANK_SIZE = 6
BANKS = 4
SLOTS = BANK_SIZE * BANKS
NAME_LEN = 16
CHARSET = " ABCDEFGHIJKLMNOPQRSTUVWXYZabcdefghijklmnopqrstuvwxyz0123456789-_.'&!#+"


class PresetStore:
    def __init__(self, path=DEFAULT_PATH):
        self.path = path
        self.slots = [None] * SLOTS
        self.load()

    def load(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
        except FileNotFoundError:
            return
        except (OSError, ValueError) as e:
            print(f"! could not read presets ({e}); starting empty")
            return
        for k, p in (data.get("presets") or {}).items():
            try:
                i = int(k) - 1
            except ValueError:
                continue
            if 0 <= i < SLOTS and isinstance(p, dict) and p.get("plugin"):
                self.slots[i] = p

    def save_file(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        data = {"version": 1,
                "presets": {str(i + 1): p for i, p in enumerate(self.slots) if p}}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def get(self, slot):
        return self.slots[slot] if 0 <= slot < SLOTS else None

    def put(self, slot, name, plugin, values, files=None):
        self.slots[slot] = {
            "name": name, "plugin": plugin.uri, "plugin_name": plugin.name,
            "values": dict(values), "saved": time.strftime("%Y-%m-%d %H:%M"),
        }
        if files:
            self.slots[slot]["files"] = {k: v for k, v in files.items() if v}
        self.save_file()

    def first_empty(self):
        return next((i for i, p in enumerate(self.slots) if p is None), None)


def label(slot):
    """Slot index -> '1-03' (bank-number)."""
    return f"{slot // BANK_SIZE + 1}-{slot % BANK_SIZE + 1:02d}"

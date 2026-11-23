"""Preset storage: 24 slots (4 banks of 6) in one JSON file.

Version 2 (multi-FX): a preset = name + "chain", a list of blocks in signal order:
    {"plugin": uri, "plugin_name": "Melon Dirt", "values": {key: value}, "files": {key: path}, "on": true}
plus "cur" (the block shown on the knobs). "files" holds the NAM / IR file of Melon NAM /
Melon Cab as a path inside the library folder (the index alone would point at another file
once files are added). "plugin" / "plugin_name" at the top level stay for the apps: the first
block's URI and a short summary of the chain ("Dirt + NAM + Cab").

Version 1 presets (one plugin: "plugin" + "values" + "files") are read as a chain of one block.

The file is written to a temporary file first and then renamed, so pulling the plug can't
leave a half-written file.
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
            if 0 <= i < SLOTS and isinstance(p, dict) and (p.get("chain") or p.get("plugin")):
                self.slots[i] = p

    def save_file(self):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        data = {"version": 2,
                "presets": {str(i + 1): p for i, p in enumerate(self.slots) if p}}
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

    def get(self, slot):
        return self.slots[slot] if 0 <= slot < SLOTS else None

    def put(self, slot, name, blocks, cur=0):
        """Save a chain (list of chain.Block) as preset `slot`."""
        chain = chain_entries(blocks)
        self.slots[slot] = {
            "name": name, "chain": chain, "cur": int(cur),
            "plugin": chain[0]["plugin"] if chain else "", "plugin_name": summary(chain),
            "saved": time.strftime("%Y-%m-%d %H:%M"),
        }
        self.save_file()

    def first_empty(self):
        return next((i for i, p in enumerate(self.slots) if p is None), None)


def chain_entries(blocks):
    """Blocks (list of chain.Block) -> the "chain" list stored in presets and in the live state."""
    chain = []
    for b in blocks:
        entry = {"plugin": b.plugin.uri, "plugin_name": b.plugin.name,
                 "values": dict(b.values), "on": bool(b.on)}
        files = {k: v for k, v in b.files.items() if v}
        if files:
            entry["files"] = files
        chain.append(entry)
    return chain


def chain_of(preset):
    """The blocks of a preset (version 1 presets: one block)."""
    if not preset:
        return []
    if preset.get("chain"):
        return preset["chain"]
    return [{"plugin": preset["plugin"], "plugin_name": preset.get("plugin_name", ""),
             "values": preset.get("values", {}), "files": preset.get("files", {}), "on": True}]


def summary(chain):
    """'Dirt + NAM + Cab' (what the browsers show under a preset name)."""
    names = [(e.get("plugin_name") or e.get("plugin", "?").rsplit("/", 1)[-1]).replace("Melon ", "")
             for e in chain]
    return " + ".join(names)


def label(slot):
    """Slot index -> '1-03' (bank-number)."""
    return f"{slot // BANK_SIZE + 1}-{slot % BANK_SIZE + 1:02d}"

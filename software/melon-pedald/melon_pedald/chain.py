"""Multi-FX chain: blocks, plugin categories (default order) and the DSP budget.

A preset is a chain of up to MAX_BLOCKS blocks in series. Each block is its own
mod-host instance. See docs/multifx-design.md and docs/dsp-budget.md.
"""
import collections
import json
import os
import re
import threading
import time
from dataclasses import dataclass, field

MAX_BLOCKS = 10

# --- categories: where "add block" puts a plugin --------------------------------------------------
CATEGORY_ORDER = ["gate", "pitch", "dynamics", "drive", "amp", "cab", "mod", "delay", "reverb", "eq"]
CATEGORY_LABEL = {"gate": "GATE", "pitch": "PITCH", "dynamics": "COMP", "drive": "DRIVE", "amp": "AMP",
                  "cab": "CAB", "mod": "MOD", "delay": "DLY", "reverb": "REV", "eq": "EQ",
                  "other": "FX", "tuner": "TUNE"}

# plugin URI slug (after "melon", letters and digits only) -> category. One line per plugin.
CATEGORIES = {
    "gatesofdoom": "gate", "simplegate": "gate",
    "shifter": "pitch", "guitarsynth": "pitch",
    "comp": "dynamics",
    "dirt": "drive", "muffs": "drive",
    "nam": "amp",
    "cab": "cab",
    "chorus": "mod", "flanger": "mod", "multimod": "mod",
    "delay2290": "delay", "multidelay": "delay",
    "reverberare": "reverb",
    "graphiceq": "eq", "proeq": "eq",
    "tuner": "tuner",
}


def _slug(uri):
    tail = uri.rstrip("/").rsplit("/", 1)[-1].lower()
    tail = re.sub(r"[^a-z0-9]", "", tail)
    return tail[len("melon"):] if tail.startswith("melon") else tail


def category(plugin):
    cat = CATEGORIES.get(_slug(plugin.uri))
    if cat:
        return cat
    if plugin.is_tuner:
        return "tuner"
    return "other"


def rank(cat):
    """Position of a category in the default chain. Unknown plugins go just before Delay."""
    if cat == "tuner":
        return -1
    if cat in CATEGORY_ORDER:
        return CATEGORY_ORDER.index(cat)
    return CATEGORY_ORDER.index("delay") - 0.5


@dataclass(eq=False)
class Block:
    plugin: object
    inst: int                                  # mod-host instance (stays the same when the block moves)
    values: dict = field(default_factory=dict)  # control key -> value
    files: dict = field(default_factory=dict)   # control key -> library path (Melon NAM / Melon Cab)
    on: bool = True

    @property
    def category(self):
        return category(self.plugin)

    @property
    def tag(self):
        return CATEGORY_LABEL.get(self.category, "FX")

    @property
    def short_name(self):
        return self.plugin.name.replace("Melon ", "")


def insert_position(chain, plugin):
    """Index where a new block of this plugin goes: after every block of the same or an earlier category."""
    r = rank(category(plugin))
    for i, b in enumerate(chain):
        if rank(b.category) > r:
            return i
    return len(chain)


# --- DSP budget ------------------------------------------------------------------------------------
BASELINE = 1.1          # % JACK load with no plugin (measured 2026-11-22)
CHAIN_FACTOR = 1.1      # a chain costs ~1.1 x the sum of its blocks
LIMIT = 85.0            # % peak: refuse a block above this
DEFAULT_COST = 10.0     # % for a plugin that was never benched (cautious)
NAM_COST = {"full": 41.2, "light": 9.1, "none": 0.9}   # Melon NAM by Model Size (bench 2026-11-22)

COST_PATHS = ["/data/plugin_costs.json", os.path.expanduser("~/plugin_costs.json")]


class CostTable:
    """Per-plugin DSP cost (% of the JACK period) from dsp_bench.py's plugin_costs.json."""

    def __init__(self, path=None):
        self.path = None
        self.costs = {}          # uri -> highest cost_peak over its variants
        self.buffer = None
        for p in ([path] if path else COST_PATHS):
            if p and os.path.exists(p):
                self.load(p)
                break

    def load(self, path):
        try:
            with open(path, encoding="utf-8") as f:
                data = json.load(f)
        except (OSError, ValueError) as e:
            print(f"! could not read DSP cost table {path}: {e}")
            return
        self.path = path
        self.buffer = data.get("buffer")
        for uri, entry in (data.get("plugins") or {}).items():
            peaks = [v.get("cost_peak") for v in (entry.get("variants") or {}).values()
                     if isinstance(v.get("cost_peak"), (int, float))]
            if peaks:
                self.costs[uri] = max(peaks)
        print(f"DSP cost table: {len(self.costs)} plugins from {path} (buffer {self.buffer})")

    def cost(self, block):
        """Estimated cost of a block. Melon NAM depends on its Model Size and whether a model is loaded."""
        pl = block.plugin
        if _slug(pl.uri) == "nam":
            model = pl.control("model_index")
            size = pl.control("size")
            if model is not None and block.values.get(model.key, -1) < 0 and not block.files.get(model.key):
                return NAM_COST["none"]
            light = size is not None and block.values.get(size.key, size.default) >= 0.5
            return NAM_COST["light" if light else "full"]
        return self.costs.get(pl.uri, DEFAULT_COST)

    def predicted(self, blocks):
        """Expected JACK load (%) of a chain. Blocks that are off still count: switching them on
        mid-song must never overload the Pi."""
        return BASELINE + CHAIN_FACTOR * sum(self.cost(b) for b in blocks)


class DspMeter:
    """Live JACK DSP load and xruns (python3-jack-client). Optional: None of this is needed to play."""

    def __init__(self):
        import jack                                   # ImportError -> caller runs without a meter
        self.client = jack.Client("melon-dsp", no_start_server=True)
        self.xruns = 0
        self.client.set_xrun_callback(self._xrun)
        self.client.activate()
        self.samples = collections.deque(maxlen=60)   # (time, load) for the last ~3 s
        threading.Thread(target=self._run, daemon=True, name="dsp-meter").start()

    def _xrun(self, delay):
        self.xruns += 1

    def _run(self):
        while True:
            try:
                self.samples.append((time.time(), self.client.cpu_load()))
            except Exception:
                pass
            time.sleep(0.05)

    def load(self):
        return self.samples[-1][1] if self.samples else 0.0

    def peak(self, seconds=1.0):
        now = time.time()
        recent = [v for t, v in self.samples if now - t <= seconds]
        return max(recent) if recent else 0.0


def open_meter():
    try:
        m = DspMeter()
        print("DSP meter: reading JACK load")
        return m
    except Exception as e:
        print(f"DSP meter off ({e.__class__.__name__}: {e}); the chain limit uses the cost table only")
        return None

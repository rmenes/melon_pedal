"""melon-pedald, test version 0.4: multi-FX chain + Livtra NexFoot + mod-host + presets + remote API.

A preset is a chain of up to 10 blocks in series (docs/multifx-design.md). The knobs, the LCD
and the app's Sound screen work on the SELECTED block.

Footswitch-knobs A-D (play screen):
  turn A-D   -> parameters 1-4 of the current page (of the selected block)
  press A    -> bypass the whole pedal on/off
  press B    -> next page (wraps around)
  hold B     -> select the next block of the chain (wraps around)
  press C    -> selected block on/off
  press D    -> next plugin in the selected block
  hold C     -> save preset
  hold D     -> preset / plugin browser

Browser:  turn A = move · press A = back · press B = presets <-> plugins · press D = load
          plugins tab: press D = replace the selected block · press C = add as a new block
Files:    (turning the Library Model / Library IR knob of Melon NAM / Melon Cab opens it)
          that knob: turn = one by one, press = open folder / choose file
          press A = up a folder / back, turn A = jump  (B and C instead when it was opened with A)
Save:     turn A = cursor · turn B = character · turn C = slot · press D = save · press A = cancel

Knobs send absolute values (0-127), so on the play screen a knob only "picks up"
a parameter once it passes the parameter's current position. Until then the
terminal says which way to turn. Lists and switches follow the knob directly.

Run (with jackd and `mod-host -n -p 5555` already running):
  python3 -m melon_pedald
  python3 -m melon_pedald --plugin chorus --capture system:capture_2
  python3 -m melon_pedald --list
"""
import argparse
import re
import shutil
import subprocess
import sys
import threading
import time

from . import catalog, library, tuner
from .chain import (CHAIN_FACTOR, LIMIT, MAX_BLOCKS, NAM_COST, Block, CostTable, insert_position,
                    open_meter)
from .display import Display
from .engine import FakeEngine, Feedback, ModHost, ModHostError
from .presets import CHARSET, DEFAULT_PATH, NAME_LEN, SLOTS, PresetStore, chain_of, label
from .remote import RemoteHub

TURN_CC = [57, 68, 74, 89]     # NexFoot A, B, C, D (turn)
PRESS_CC = [21, 25, 26, 27]    # NexFoot A, B, C, D (press)
PRESS_LOW = True               # NexFoot sends 0 when pressed, 127 when released (--press-high: the opposite)
NAMES = "ABCD"
PICKUP_WINDOW = 3 / 127        # "close enough" to pick up a parameter
HOLD_SECONDS = 0.7

CC_LINE = re.compile(r"Control change\s+(\d+),\s*controller\s+(\d+),\s*value\s+(\d+)")
WATCH_SECONDS = 1.5            # after adding a block: watch the live DSP load this long


class ChainError(RuntimeError):
    """A chain change that was refused (full chain, not enough DSP, ...). The pedal keeps playing."""


class Pedal:
    def __init__(self, engine, plugins, capture, playback, display=None, presets=None, costs=None, meter=None):
        self.engine = engine
        self.plugins = plugins
        self.capture = capture
        self.playback = playback
        self.display = display or Display(enabled=False)
        self.presets = presets or PresetStore()
        self.costs = costs or CostTable()
        self.meter = meter               # live JACK load (chain.DspMeter) or None
        self.chain = []                  # Blocks in signal order
        self.cur = 0                     # selected block (knobs, LCD, app Sound screen)
        self.page = 0
        self.bypassed = False
        self.last_cc = [None] * 4
        self.picked = [False] * 4
        self.last_hint = [0.0] * 4
        self.slot = None                 # preset slot the current sound came from
        self.mode = "play"               # play | browse | save
        self.tab = "presets"             # browser tab: presets | plugins
        self.sel = 0                     # browser selection
        self.save_name = []
        self.save_cursor = 0
        self.save_slot = 0
        self.lock = threading.RLock()    # MIDI thread + hold timers
        self.down = [False] * 4
        self.consumed = [False] * 4      # press already used by a hold / mode change
        self.timers = [None] * 4
        self.readout_seen = False        # Melon Tuner: first reading arrived from mod-host
        self.libs = library.libraries()  # NAM / IR files for Melon NAM / Melon Cab
        self.fb = None                   # file browser state (mode "files")
        self.fb_closed = (None, 0.0)     # (knob, time): ignore that knob briefly after choosing

    # --- the selected block ---
    @property
    def block(self):
        return self.chain[self.cur] if self.chain else None

    @property
    def plugin(self):
        return self.block.plugin

    @property
    def idx(self):
        """Index of the selected block's plugin in self.plugins."""
        b = self.block
        return next((i for i, pl in enumerate(self.plugins) if b and pl is b.plugin), 0)

    @property
    def values(self):
        return self.block.values if self.block else {}

    @property
    def files(self):
        """control key -> chosen file (path inside its library), of the selected block."""
        return self.block.files if self.block else {}

    def send(self, c, value, block=None):
        """Set control c of a block (default: the selected one) in mod-host."""
        return self.engine.set((block or self.block).inst, c, value)

    def notice(self, text):
        print(f"! {text}")
        self.display.notice(text)

    def layout(self):
        """The knob pages: 4 controls each, in plugin order.

        Melon Tuner is different: page 1 is the tuner screen (needle), with knob 1 = Mute,
        and its settings follow on page 2 onwards. "Display" (needle/strobe) is only for
        the plugin's own window, so it is left out.
        """
        controls = list(self.plugin.controls)
        pages = []
        if self.plugin.is_tuner:
            mute = self.plugin.control("mute")
            pages.append([mute, None, None, None])
            controls = [c for c in controls if c is not mute and c.short_id != "display"]
        for i in range(0, len(controls), 4):
            pages.append((controls[i:i + 4] + [None] * 4)[:4])
        return pages or [[None] * 4]

    @property
    def pages(self):
        return len(self.layout())

    def page_controls(self):
        pages = self.layout()
        return pages[min(self.page, len(pages) - 1)]

    @property
    def tuner_visible(self):
        return self.plugin.is_tuner and self.page == 0 and self.mode == "play"

    def tuner_state(self):
        """Tuning, reference and mute of the loaded Melon Tuner (for the tuner screen)."""
        def val(sid, default):
            c = self.plugin.control(sid)
            return self.values.get(c.key, default) if c else default
        idx = int(round(val("tuning", 0)))
        return {"index": idx, "tuning": tuner.tuning_name(idx), "strings": tuner.string_names(idx),
                "reference": val("reference", 440.0), "mute": val("mute", 0) >= 0.5}

    def on_patch(self, inst, uri, value):
        """A value sent by a plugin (mod-host feedback thread)."""
        with self.lock:
            b = self.block
            if b is None or b.inst != inst or uri != b.plugin.readout:
                return
            if not self.readout_seen:
                self.readout_seen = True
                print("tuner: readings arriving from mod-host")
            if not self.tuner_visible:
                return
            st = self.tuner_state()
            r = tuner.reading(value, st["reference"], st["index"])
        self.display.tuner(r)

    @property
    def edited(self):
        p = self.presets.get(self.slot) if self.slot is not None else None
        if not p:
            return False
        entries = chain_of(p)
        if [b.plugin.uri for b in self.chain] != [e["plugin"] for e in entries]:
            return True
        for b, e in zip(self.chain, entries):
            if b.on != e.get("on", True):
                return True
            saved, saved_files = e.get("values", {}), e.get("files", {})
            for c in b.plugin.controls:
                if self.lib_of(c) is not None:
                    if b.files.get(c.key) != saved_files.get(c.key):
                        return True
                elif abs(b.values[c.key] - float(saved.get(c.key, c.default))) > 1e-6:
                    return True
        return False

    # --- NAM / IR library (Melon NAM model_index, Melon Cab ir_index) ---
    def lib_of(self, c):
        """The Library behind control c, or None for an ordinary control."""
        if c is None or c.kind != "param":
            return None
        kind = library.LIB_PARAMS.get(c.short_id)
        return self.libs.get(kind) if kind else None

    def lib_text(self, c, value):
        """What the LCD shows for a library control: the file name ("None" = no file)."""
        if self.lib_of(c) is None:
            return None
        return library.title(self.files.get(c.key)) if value >= 0 else "None"

    def set_file(self, c, rel, block=None):
        """Load `rel` (path inside c's library, None = no file) into a block's plugin."""
        b = block or self.block
        lib = self.lib_of(c)
        idx = lib.index_of(rel) if rel else library.NONE
        if rel and idx == library.NONE:
            print(f"! {rel} is not in {lib.root} any more")
            rel = None
        if idx >= 0 and abs(b.values.get(c.key, c.default) - idx) < 1e-9:
            self.send(c, float(library.NONE), b)   # same number: the plugin only reacts to a change
        b.values[c.key] = float(idx)
        b.files[c.key] = rel
        return self.send(c, float(idx), b)

    def _apply_files(self, values, files, block=None):
        """After loading a plugin / preset: point a block's library controls at the preset's files."""
        b = block or self.block
        lib_controls = [c for c in b.plugin.controls if self.lib_of(c) is not None]
        for lib in {id(self.lib_of(c)): self.lib_of(c) for c in lib_controls}.values():
            lib.refresh()
        for c in lib_controls:
            rel = (files or {}).get(c.key)
            if rel is None and values and float(values.get(c.key, -1)) >= 0:
                rel = self.lib_of(c).path_at(int(float(values[c.key])))   # preset saved before "files"
            if rel != b.files.get(c.key) or (rel and b.values.get(c.key, -1) < 0):
                self.set_file(c, rel, b)

    # --- chain plumbing ---
    def _free_inst(self):
        used = {b.inst for b in self.chain}
        return next(i for i in range(MAX_BLOCKS) if i not in used)

    def route(self):
        self.engine.route([b.inst for b in self.chain], self.capture, self.playback)

    def apply_bypass(self, b):
        """A block is bypassed in mod-host when it is off or the whole pedal is bypassed."""
        self.engine.bypass(b.inst, self.bypassed or not b.on)

    def set_bypass(self, on):
        self.bypassed = bool(on)
        for b in self.chain:
            self.apply_bypass(b)
        print(f"*** {'BYPASS' if self.bypassed else 'EFFECT ON'} ***")
        self.display.bypass(self.bypassed)

    def _load_block(self, b, plugin, values=None, files=None):
        """(Re)load block b with `plugin` and set its values. Raises ModHostError."""
        t = time.time()
        self.engine.add(b.inst, plugin)
        b.plugin = plugin
        b.values = {c.key: c.default for c in plugin.controls}
        b.files = {}
        for c in plugin.controls:
            if values and c.key in values and self.lib_of(c) is None:
                b.values[c.key] = float(values[c.key])
                self.send(c, b.values[c.key], b)
        self._apply_files(values, files, b)
        if self.bypassed or not b.on:
            self.apply_bypass(b)
        return (time.time() - t) * 1000

    def dsp(self):
        """DSP numbers for the LCD and the apps (% of the JACK period)."""
        d = {"predicted": round(self.costs.predicted(self.chain), 1), "limit": LIMIT}
        if self.meter:
            d.update(load=round(self.meter.load(), 1), peak=round(self.meter.peak(2.0), 1),
                     xruns=self.meter.xruns)
        return d

    def _check_budget(self, new_chain, delta):
        """Refuse a change whose predicted DSP load is over the limit.

        new_chain: the chain after the change; delta: its cost minus the current chain's cost.
        Uses the cost table, and the live JACK load when the meter runs (whichever is higher)."""
        pred = self.costs.predicted(new_chain)
        if self.meter:
            pred = max(pred, self.meter.peak(2.0) + CHAIN_FACTOR * delta)
        if pred <= LIMIT:
            return
        hint = ""
        full_nam = [b for b in new_chain if self.costs.cost(b) >= NAM_COST["full"] - 1e-6]
        if full_nam:
            hint = " Tip: set Melon NAM's Model Size to Light (about 32% less)."
        raise ChainError(f"not enough DSP: the chain would need about {pred:.0f}% (limit {LIMIT:.0f}%).{hint}")

    # --- actions ---
    def load(self, idx, values=None, files=None):
        """Put plugin `idx` into the selected block (an empty chain gets its first block)."""
        new = not self.chain
        if new:
            plugin = self.plugins[idx % len(self.plugins)]
            self.chain = [Block(plugin, inst=self._free_inst())]
            self.cur = 0
        else:
            b, plugin = self.block, self.plugins[idx % len(self.plugins)]
            trial = Block(plugin, inst=b.inst, values={c.key: c.default for c in plugin.controls})
            others = [x for x in self.chain if x is not b]
            self._check_budget(others + [trial], self.costs.cost(trial) - self.costs.cost(b))
        b = self.block
        for attempt in range(len(self.plugins)):
            plugin = self.plugins[(idx + attempt) % len(self.plugins)]
            try:
                ms = self._load_block(b, plugin, values, files)
                break
            except ModHostError as e:
                print(f"! {e}")
        else:
            raise SystemExit("no plugin could be loaded")
        self.route()
        self.page = 0
        self.readout_seen = False
        self.release_knobs()
        print(f"\n=== {self.plugin.name}  ({len(self.plugin.controls)} parameters, "
              f"loaded in {ms:.0f} ms) · block {self.cur + 1}/{len(self.chain)} ===")
        self.show_page()

    def load_preset(self, slot):
        p = self.presets.get(slot)
        if not p:
            return False
        entries = chain_of(p)
        by_uri = {pl.uri: pl for pl in self.plugins}
        missing = [e.get("plugin_name") or e["plugin"] for e in entries if e["plugin"] not in by_uri]
        if missing or not entries:
            print(f"! preset {label(slot)} needs {', '.join(missing) or 'a plugin'}, which is not installed")
            return False
        self.slot = slot
        print(f"\n>>> preset {label(slot)} {p['name']}  ({len(entries)} block{'s' if len(entries) > 1 else ''})")
        if [b.plugin.uri for b in self.chain] == [e["plugin"] for e in entries]:
            for b, e in zip(self.chain, entries):     # same chain: just set the values (no gap)
                saved = e.get("values", {})
                for c in b.plugin.controls:
                    if self.lib_of(c) is not None:
                        continue
                    v = float(saved.get(c.key, c.default))
                    if abs(v - b.values[c.key]) > 1e-9:
                        b.values[c.key] = v
                        self.send(c, v, b)
                self._apply_files(saved, e.get("files"), b)
                if b.on != e.get("on", True):
                    b.on = e.get("on", True)
                    self.apply_bypass(b)
        else:                                         # other plugins: rebuild the chain
            for b in self.chain:
                self.engine.remove(b.inst)
            self.chain = []
            for e in entries:
                b = Block(by_uri[e["plugin"]], inst=self._free_inst(), on=e.get("on", True))
                self.chain.append(b)
                try:
                    self._load_block(b, b.plugin, e.get("values"), e.get("files"))
                except ModHostError as err:
                    print(f"! {err}")
                    self.chain.remove(b)
            if not self.chain:
                raise SystemExit("no plugin of the preset could be loaded")
            self.route()
        pred = self.costs.predicted(self.chain)
        if pred > LIMIT:
            print(f"! this preset is predicted at {pred:.0f}% DSP (limit {LIMIT:.0f}%)")
        self.cur = min(max(int(p.get("cur", 0)), 0), len(self.chain) - 1)
        self.page = 0
        self.readout_seen = False
        self.release_knobs()
        self.show_page()
        return True

    # --- chain editing ---
    def _block_index(self, i):
        i = int(i)
        if not 0 <= i < len(self.chain):
            raise ChainError(f"no block {i + 1} (the chain has {len(self.chain)})")
        return i

    def add_block(self, plugin_idx, pos=None):
        """Add plugin `plugin_idx` as a new block: at its category's place, or at `pos`."""
        if len(self.chain) >= MAX_BLOCKS:
            raise ChainError(f"the chain is full ({MAX_BLOCKS} blocks)")
        plugin = self.plugins[int(plugin_idx)]
        b = Block(plugin, inst=self._free_inst(), values={c.key: c.default for c in plugin.controls})
        self._check_budget(self.chain + [b], self.costs.cost(b))
        pos = insert_position(self.chain, plugin) if pos is None else min(max(int(pos), 0), len(self.chain))
        xruns = self.meter.xruns if self.meter else 0
        try:
            ms = self._load_block(b, plugin)
        except ModHostError as e:
            raise ChainError(str(e))
        self.chain.insert(pos, b)
        self.route()
        print(f"\n+++ block {pos + 1}/{len(self.chain)}: {plugin.name} (loaded in {ms:.0f} ms, "
              f"predicted DSP {self.costs.predicted(self.chain):.0f}%)")
        self.select_block(pos)
        if self.meter:
            t = threading.Timer(WATCH_SECONDS, self._after_add, (b, xruns))
            t.daemon = True
            t.start()
        return pos

    def _after_add(self, b, xruns_before):
        """A moment after adding a block: take it out again if the Pi can't keep up."""
        with self.lock:
            if b not in self.chain or len(self.chain) < 2:
                return
            peak, xr = self.meter.peak(WATCH_SECONDS), self.meter.xruns - xruns_before
            if peak <= LIMIT and xr == 0:
                return
            self.remove_block(self.chain.index(b))
            self.notice(f"{b.short_name} removed again: DSP {peak:.0f}%"
                        + (f", {xr} xruns" if xr else "") + f" (limit {LIMIT:.0f}%)")

    def remove_block(self, i):
        i = self._block_index(i)
        if len(self.chain) == 1:
            raise ChainError("the last block can't be removed (load another plugin instead)")
        b = self.chain.pop(i)
        self.engine.remove(b.inst)
        self.route()
        print(f"--- removed block {i + 1}: {b.plugin.name}")
        self.select_block(min(self.cur if i > self.cur else max(self.cur - 1, 0), len(self.chain) - 1))

    def move_block(self, i, to):
        i = self._block_index(i)
        to = min(max(int(to), 0), len(self.chain) - 1)
        if i == to:
            return
        sel = self.block
        b = self.chain.pop(i)
        self.chain.insert(to, b)
        self.route()
        self.cur = self.chain.index(sel)
        print(f"<-> {b.plugin.name}: block {i + 1} -> {to + 1}")
        self.show_page()

    def block_on(self, i, on=None):
        b = self.chain[self._block_index(i)]
        b.on = (not b.on) if on is None else bool(on)
        self.apply_bypass(b)
        print(f"  block {self.chain.index(b) + 1} {b.plugin.name}: {'ON' if b.on else 'off'}")
        self.show_page()

    def select_block(self, i):
        self.cur = self._block_index(i)
        self.page = 0
        self.readout_seen = False
        self.release_knobs()
        self.show_page()

    def save_preset(self, slot, name):
        self.presets.put(slot, name, self.chain, self.cur)
        self.slot = slot

    def release_knobs(self):
        self.picked = [False] * 4

    def show_page(self):
        state = "BYPASS" if self.bypassed else "on"
        pre = ""
        if self.slot is not None:
            pre = f"{label(self.slot)} {self.presets.get(self.slot)['name']}{' *' if self.edited else ''} | "
        blk = f"block {self.cur + 1}/{len(self.chain)}{'' if self.block.on else ' (off)'} " if len(self.chain) > 1 else ""
        print(f"--- {pre}{blk}{self.plugin.name} | page {self.page + 1}/{self.pages} | {state}")
        if len(self.chain) > 1:
            print("    chain: " + " > ".join(("[" if i == self.cur else "") + b.short_name + ("" if b.on else " off")
                                          + ("]" if i == self.cur else "") for i, b in enumerate(self.chain)))
        for name, c in zip(NAMES, self.page_controls()):
            if c:
                txt = self.lib_text(c, self.values[c.key]) or c.format(self.values[c.key])
                print(f"  {name}  {c.label:<22} {txt}")
            else:
                print(f"  {name}  -")
        self.display.page(self)

    def turn(self, k, cc_value):
        if self.mode != "play":
            return self.menu_turn(k, cc_value)
        c = self.page_controls()[k]
        prev, self.last_cc[k] = self.last_cc[k], cc_value
        if c is None:
            return
        if self.lib_of(c) is not None:          # Library Model / Library IR: pick a file by name
            knob, t = self.fb_closed
            if knob != k or time.time() - t > 0.6:
                self.open_files(k, c)
            return
        target = cc_value / 127
        current = c.to_norm(self.values[c.key])
        if not self.picked[k] and not c.discrete:
            crossed = prev is not None and (prev / 127 - current) * (target - current) <= 0
            if abs(target - current) <= PICKUP_WINDOW or crossed:
                self.picked[k] = True
            else:
                now = time.time()
                if now - self.last_hint[k] > 1.0:
                    way = "up" if target < current else "down"
                    print(f"  {NAMES[k]}  {c.label}: turn {way} to pick up "
                          f"(knob {target:.0%}, value {current:.0%})")
                    self.last_hint[k] = now
                return
        value = c.from_norm(target)
        if abs(value - self.values[c.key]) < 1e-9:
            return
        was_edited = self.edited
        self.values[c.key] = value
        code = self.send(c, value)
        err = "" if code >= 0 else f"   ! mod-host error {code}"
        print(f"  {NAMES[k]}  {c.label:<22} {c.format(value)}{err}")
        self.display.value(k, c, value)
        if self.edited != was_edited:
            self.display.page(self, popup=False)   # EDITED chip on/off

    # --- presses: A/B act at once; C/D wait to see if it is a hold ---
    def press_down(self, k):
        self.down[k] = True
        self.consumed[k] = False
        if self.mode != "play":
            self.consumed[k] = True
            return self.menu_press(k)
        if k == 0:
            self.consumed[k] = True
            self.short_press(k)
        else:
            t = threading.Timer(HOLD_SECONDS, self._hold, (k,))
            t.daemon = True
            self.timers[k] = t
            t.start()

    def press_up(self, k):
        self.down[k] = False
        if self.timers[k]:
            self.timers[k].cancel()
            self.timers[k] = None
        if not self.consumed[k] and self.mode == "play":
            self.short_press(k)
        self.consumed[k] = True

    def _hold(self, k):
        with self.lock:
            if not self.down[k] or self.consumed[k] or self.mode != "play":
                return
            self.consumed[k] = True
            self.timers[k] = None
            if k == 1:
                if len(self.chain) > 1:
                    self.select_block((self.cur + 1) % len(self.chain))
            elif k == 2:
                self.open_save()
            elif k == 3:
                self.open_browser()

    def short_press(self, k):
        if k == 0:
            self.set_bypass(not self.bypassed)
        elif k == 1:
            self.page = (self.page + 1) % self.pages
            self.release_knobs()
            self.show_page()
        elif k == 2:
            self.block_on(self.cur)
        elif k == 3:
            self.load(self.idx + 1)

    # --- browser ---
    def open_browser(self):
        self.mode, self.tab = "browse", "presets"
        self.sel = self.slot if self.slot is not None else 0
        print("\n[ presets ]  turn A = move · press D = load · press B = plugins · press A = back")
        self.show_menu()

    def browser_rows(self):
        if self.tab == "presets":
            return [self.presets.get(i) for i in range(SLOTS)]
        return self.plugins

    def show_menu(self):
        if self.mode == "browse":
            if self.tab == "presets":
                p = self.presets.get(self.sel)
                print(f"  > {label(self.sel)}  {p['name'] + '  (' + p.get('plugin_name', '') + ')' if p else '- empty -'}")
            else:
                print(f"  > {self.plugins[self.sel].name}")
            self.display.browser(self)
        elif self.mode == "files":
            kind, name = self.fb["rows"][self.sel]
            where = self.fb["folder"] or "/"
            shown = {"none": "- none -", "dir": f"[{name}]"}.get(kind, name)
            print(f"  > {where}: {shown}")
            self.display.files(self)
        elif self.mode == "save":
            name = "".join(self.save_name)
            old = self.presets.get(self.save_slot)
            where = f"{label(self.save_slot)} " + (f"(replaces {old['name']})" if old else "(empty)")
            print(f"  save: [{name[:self.save_cursor]}|{name[self.save_cursor]}|{name[self.save_cursor + 1:]}]  -> {where}")
            self.display.save(self, where)

    def menu_turn(self, k, v):
        n = v / 128
        if self.mode == "files":
            prev, self.last_cc[k] = self.last_cc[k], v
            rows = self.fb["rows"]
            if k == self.fb["k"]:                          # the knob that opened it: one row per step
                if prev is None:
                    return
                sel = max(0, min(len(rows) - 1, self.sel + (v - prev)))
            elif k == self.fb["jump"]:                     # jump through the list
                sel = int(n * len(rows))
            else:
                return
            if sel != self.sel:
                self.sel = sel
                self.show_menu()
            return
        if self.mode == "browse" and k == 0:
            sel = int(n * len(self.browser_rows()))
            if sel != self.sel:
                self.sel = sel
                self.show_menu()
        elif self.mode == "save":
            if k == 0:
                self.save_cursor = int(n * NAME_LEN)
            elif k == 1:
                self.save_name[self.save_cursor] = CHARSET[int(n * len(CHARSET))]
            elif k == 2:
                self.save_slot = int(n * SLOTS)
            else:
                return
            self.show_menu()

    def menu_press(self, k):
        if self.mode == "files":
            return self.files_press(k)
        if self.mode == "browse":
            if k == 0:
                self.back()
            elif k == 1 or (k == 2 and self.tab == "presets"):
                self.tab = "plugins" if self.tab == "presets" else "presets"
                self.sel = self.idx if self.tab == "plugins" else (self.slot or 0)
                print(f"\n[ {self.tab} ]" + ("  press D = replace the selected block · press C = add as a new block"
                                             if self.tab == "plugins" else ""))
                self.show_menu()
            elif k == 2:                                   # plugins tab: add as a new block
                self.mode = "play"
                self.add_block(self.sel)
            elif k == 3:
                if self.tab == "presets":
                    if not self.presets.get(self.sel):
                        print("  (empty slot)")
                        return
                    self.mode = "play"
                    self.load_preset(self.sel)
                else:
                    self.mode = "play"
                    self.load(self.sel)
        elif self.mode == "save":
            if k == 0:
                print("  save cancelled")
                self.back()
            elif k == 3:
                name = "".join(self.save_name).strip() or self.plugin.name
                self.save_preset(self.save_slot, name)
                print(f"  saved {label(self.save_slot)} {name}")
                self.back()

    # --- file browser (Melon NAM models, Melon Cab IRs) ---
    def open_files(self, k, c):
        lib = self.lib_of(c)
        lib.refresh()                       # pick up files from a USB import
        cur = self.files.get(c.key)
        self.mode = "files"
        # The knob that opened the browser scrolls (turn) and chooses (press).
        # "Up / back" and "jump" go to A, or to B and C when the browser was opened with A.
        back, jump = (1, 2) if k == 0 else (0, 0)
        self.fb = {"k": k, "back": back, "jump": jump, "c": c, "lib": lib,
                   "folder": library.folder_of(cur), "rows": []}
        self._fb_list(("file", cur.rsplit("/", 1)[-1]) if cur else ("none", None))
        print(f"\n[ {c.label} ]  turn {NAMES[k]} = one by one · press {NAMES[k]} = open / choose · "
              f"press {NAMES[back]} = up / back · turn {NAMES[jump]} = jump")
        self.show_menu()

    def _fb_list(self, select=None):
        fb = self.fb
        dirs, files = fb["lib"].list_folder(fb["folder"])
        if fb["folder"] and not dirs and not files:     # folder gone (files deleted): back to the top
            fb["folder"] = ""
            dirs, files = fb["lib"].list_folder("")
        rows = [] if fb["folder"] else [("none", None)]
        rows += [("dir", d) for d in dirs] + [("file", f) for f in files]
        fb["rows"] = rows
        self.sel = rows.index(select) if select in rows else 0

    def files_press(self, k):
        fb = self.fb
        if k == fb["back"]:                                # up a folder, or back at the top
            if fb["folder"]:
                parent, _, name = fb["folder"].rpartition("/")
                fb["folder"] = parent
                self._fb_list(("dir", name))
                self.show_menu()
            else:
                self.close_files()
        elif k == fb["k"]:                                 # open the folder / choose the file
            kind, name = fb["rows"][self.sel]
            if kind == "dir":
                fb["folder"] = f"{fb['folder']}/{name}" if fb["folder"] else name
                self._fb_list()
                self.show_menu()
            else:
                rel = None if kind == "none" else (f"{fb['folder']}/{name}" if fb["folder"] else name)
                code = self.set_file(fb["c"], rel)
                err = "" if code >= 0 else f"   ! mod-host error {code}"
                print(f"  {fb['c'].label}: {rel or 'none'}{err}")
                self.close_files()

    def close_files(self):
        self.fb_closed = (self.fb["k"], time.time())
        self.fb = None
        self.back()

    def open_save(self):
        self.mode = "save"
        cur = self.presets.get(self.slot) if self.slot is not None else None
        name = (cur["name"] if cur else self.plugin.name.replace("Melon ", ""))[:NAME_LEN]
        self.save_name = list(name.ljust(NAME_LEN))
        self.save_cursor = min(len(name.rstrip()), NAME_LEN - 1)
        empty = self.presets.first_empty()
        self.save_slot = self.slot if self.slot is not None else (empty if empty is not None else 0)
        print("\n[ save ]  turn A = cursor · B = letter · C = slot · press D = save · press A = cancel")
        self.show_menu()

    def back(self):
        self.mode = "play"
        self.release_knobs()
        self.show_page()

    def midi(self, line):
        m = CC_LINE.search(line)
        if not m:
            return
        _, cc, value = map(int, m.groups())
        with self.lock:
            try:
                if cc in TURN_CC:
                    self.turn(TURN_CC.index(cc), value)
                elif cc in PRESS_CC:
                    k = PRESS_CC.index(cc)
                    pressed = value < 64 if PRESS_LOW else value >= 64
                    if pressed and not self.down[k]:
                        self.press_down(k)
                    elif not pressed and self.down[k]:
                        self.press_up(k)
            except ChainError as e:
                self.mode = "play"
                self.notice(str(e))
                self.show_page()


def main():
    ap = argparse.ArgumentParser(prog="melon_pedald", description="Melon pedal test controller (NexFoot + mod-host)")
    ap.add_argument("--plugin", default="", help="start with the plugin whose name/URI contains this text")
    ap.add_argument("--preset", type=int, help="start with this preset (1-24)")
    ap.add_argument("--match", default="melon", help="only cycle through plugins containing this text ('' = all)")
    ap.add_argument("--lv2-dir", action="append", help="LV2 folder to scan (default: ~/.lv2 and system folders)")
    ap.add_argument("--midi-port", default="Nexfoot MIDI:1", help="ALSA MIDI port of the controller")
    ap.add_argument("--capture", default="system:capture_1", help="JACK input(s), comma separated")
    ap.add_argument("--playback", default="system:playback_1,system:playback_2", help="JACK outputs")
    ap.add_argument("--turn-cc", default=",".join(map(str, TURN_CC)),
                    help="CC numbers of knobs A,B,C,D when turned (check with aseqdump)")
    ap.add_argument("--press-cc", default=",".join(map(str, PRESS_CC)),
                    help="CC numbers of knobs A,B,C,D when pressed (check with aseqdump)")
    ap.add_argument("--press-high", action="store_true",
                    help="controller sends 127 when a knob is pressed and 0 when released (NexFoot: the opposite)")
    ap.add_argument("--port", type=int, default=5555, help="mod-host TCP port")
    ap.add_argument("--feedback-port", type=int, default=0,
                    help="mod-host feedback port (default: --port + 1, i.e. mod-host -f 5556)")
    ap.add_argument("--presets", default=DEFAULT_PATH, help="preset file")
    ap.add_argument("--costs", default=None,
                    help="DSP cost table from dsp_bench.py (default: /data/plugin_costs.json, then ~/plugin_costs.json)")
    ap.add_argument("--no-dsp-meter", action="store_true",
                    help="don't read the live JACK load (the chain limit then uses the cost table only)")
    ap.add_argument("--list", action="store_true", help="list plugins and their parameters, then exit")
    ap.add_argument("--fake", action="store_true", help="no mod-host: print the commands instead")
    ap.add_argument("--stdin", action="store_true", help="read aseqdump-style lines from stdin instead of MIDI")
    ap.add_argument("--no-lcd", action="store_true", help="don't send state to the melon-display service")
    ap.add_argument("--remote-port", type=int, default=5601,
                    help="local TCP port of the remote API used by melon-ble / apps (0 = off)")
    ap.add_argument("-v", "--verbose", action="store_true", help="show every mod-host command")
    args = ap.parse_args()
    for name, target in (("--turn-cc", TURN_CC), ("--press-cc", PRESS_CC)):
        nums = [int(x) for x in getattr(args, name[2:].replace("-", "_")).split(",")]
        if len(nums) != 4:
            raise SystemExit(f"{name} needs 4 numbers (A,B,C,D)")
        target[:] = nums
    global PRESS_LOW
    PRESS_LOW = not args.press_high

    plugins = catalog.scan(args.lv2_dir, args.match)
    if not plugins:
        raise SystemExit(f"no LV2 plugins matching {args.match!r} found")

    if args.list:
        for p in plugins:
            print(f"{p.name}  <{p.uri}>  in={p.audio_in} out={p.audio_out}")
            for i, c in enumerate(p.controls):
                extra = f" [{', '.join(l for _, l in c.choices)}]" if c.choices else ""
                print(f"   {i + 1:>2}. {c.label:<22} {c.format(c.minimum)} .. {c.format(c.maximum)}"
                      f"  (default {c.format(c.default)}){extra}  {c.short_id}")
        return

    engine = FakeEngine() if args.fake else ModHost(port=args.port, verbose=args.verbose)
    pedal_ref = []              # the feedback thread starts before the Pedal exists
    try:
        engine.connect()
        if not args.fake:
            # mod-host only answers commands once a client is connected to its feedback port too,
            # so connect that first (and wait for it) before the first command.
            fb = Feedback(lambda *a: pedal_ref and pedal_ref[0].on_patch(*a),
                          lambda: engine.cmd("output_data_ready"),
                          port=args.feedback_port or args.port + 1, verbose=args.verbose)
            fb.start()
            t = time.time()
            while not fb.connected and time.time() - t < 10:
                time.sleep(0.05)
            if not fb.connected:
                print("! mod-host feedback port not connected yet; mod-host may not answer until it is")
        engine.clear()          # instances left by a previous run (a restart of only this controller)
    except (ModHostError, OSError) as e:
        raise SystemExit(f"mod-host does not answer: {e}")
    costs = CostTable(args.costs)
    meter = None if (args.fake or args.no_dsp_meter) else open_meter()

    display = Display(enabled=not args.no_lcd)
    hub = RemoteHub(port=args.remote_port) if args.remote_port else None
    if hub:
        display = hub.wrap(display)      # LCD updates also go to the apps
    store = PresetStore(args.presets)
    pedal = Pedal(engine, plugins, args.capture.split(","), args.playback.split(","), display, store, costs, meter)
    pedal_ref.append(pedal)
    if hub:
        try:
            hub.start(pedal)
        except OSError as e:
            print(f"! remote API off: {e}")
    start = next((i for i, p in enumerate(plugins) if args.plugin.lower() in (p.uri + p.name).lower()), 0)
    print(f"Found {len(plugins)} plugins: " + ", ".join(p.name for p in plugins))
    print(f"{sum(1 for p in store.slots if p)} presets in {args.presets}")
    print(f"press: A = bypass, B = next page, C = block on/off, D = next plugin | "
          f"hold B = next block, hold C = save, hold D = presets   (press CCs A-D: {PRESS_CC})")
    with pedal.lock:
        if not (args.preset and pedal.load_preset(args.preset - 1)):
            pedal.load(start)

    if meter:
        def dsp_header():
            """Keep the LCD header's "DSP nn%" live (only sends when it changes by 1 % or more)."""
            last = None
            while True:
                time.sleep(1.0)
                v = round(meter.load())
                if last is None or abs(v - last) >= 1:
                    last = v
                    display.dsp_load(v)
        threading.Thread(target=dsp_header, daemon=True, name="dsp-header").start()

    proc = [None]

    def midi_lines():
        """aseqdump lines; waits (keeping the plugin loaded) while the controller is missing."""
        waiting = False
        while True:
            cmd = ["aseqdump", "-p", args.midi_port]
            if shutil.which("stdbuf"):
                cmd = ["stdbuf", "-oL"] + cmd  # line-buffered, so knob moves arrive at once
            proc[0] = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                       stderr=subprocess.STDOUT, text=True, bufsize=1)
            connected = False
            for line in proc[0].stdout:
                if "Invalid port" in line or "Cannot connect" in line:
                    break
                if not connected:
                    connected = True
                    if waiting:
                        print(f"MIDI: {args.midi_port} connected")
                    waiting = False
                    display.midi(True)
                yield line
            proc[0].wait()
            if not waiting:
                print(f"MIDI: waiting for {args.midi_port} (plug in / switch on the controller; "
                      f"`aconnect -l` lists the ports)")
                waiting = True
                display.midi(False)
            time.sleep(2)

    try:
        source = sys.stdin if args.stdin else midi_lines()
        for line in source:
            pedal.midi(line)
    except KeyboardInterrupt:
        print()
    except ModHostError as e:
        print(f"! {e}")
    finally:
        display.stopped()
        if proc[0]:
            proc[0].terminate()
        try:
            engine.unload()
        except Exception:
            pass
        print("bye")


if __name__ == "__main__":
    main()

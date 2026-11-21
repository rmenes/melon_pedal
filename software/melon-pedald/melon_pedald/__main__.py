"""melon-pedald, test version 0.2: Livtra NexFoot + mod-host + presets.

Footswitch-knobs A-D (play screen):
  turn A-D   -> parameters 1-4 of the current page
  press A    -> bypass on/off
  press B/C  -> previous / next page
  press D    -> next plugin
  hold C     -> save preset
  hold D     -> preset / plugin browser

Browser:  turn A = move · press A = back · press B/C = presets <-> plugins · press D = load
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

from . import catalog
from .display import Display
from .engine import FakeEngine, ModHost, ModHostError
from .presets import CHARSET, DEFAULT_PATH, NAME_LEN, SLOTS, PresetStore, label

TURN_CC = [57, 68, 74, 89]     # NexFoot A, B, C, D (turn)
PRESS_CC = [21, 25, 26, 27]    # NexFoot A, B, C, D (press: 127 down, 0 up)
NAMES = "ABCD"
PICKUP_WINDOW = 3 / 127        # "close enough" to pick up a parameter
HOLD_SECONDS = 0.7

CC_LINE = re.compile(r"Control change\s+(\d+),\s*controller\s+(\d+),\s*value\s+(\d+)")


class Pedal:
    def __init__(self, engine, plugins, capture, playback, display=None, presets=None):
        self.engine = engine
        self.plugins = plugins
        self.capture = capture
        self.playback = playback
        self.display = display or Display(enabled=False)
        self.presets = presets or PresetStore()
        self.idx = 0
        self.page = 0
        self.values = {}
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

    @property
    def plugin(self):
        return self.plugins[self.idx]

    @property
    def pages(self):
        n = len(self.plugin.controls)
        return max(1, (n + 3) // 4)

    def page_controls(self):
        c = self.plugin.controls
        return [c[i] if i < len(c) else None for i in range(self.page * 4, self.page * 4 + 4)]

    @property
    def edited(self):
        p = self.presets.get(self.slot) if self.slot is not None else None
        if not p:
            return False
        saved = p.get("values", {})
        return any(abs(self.values[c.key] - saved.get(c.key, c.default)) > 1e-6
                   for c in self.plugin.controls)

    # --- actions ---
    def load(self, idx, values=None):
        for attempt in range(len(self.plugins)):
            self.idx = (idx + attempt) % len(self.plugins)
            try:
                t = time.time()
                self.engine.load(self.plugin, self.capture, self.playback)
                ms = (time.time() - t) * 1000
                break
            except ModHostError as e:
                print(f"! {e}")
        else:
            raise SystemExit("no plugin could be loaded")
        self.values = {c.key: c.default for c in self.plugin.controls}
        for c in self.plugin.controls:
            if values and c.key in values:
                self.values[c.key] = float(values[c.key])
                self.engine.set(c, self.values[c.key])
        self.page = 0
        if self.bypassed:
            self.engine.bypass(True)
        self.release_knobs()
        print(f"\n=== {self.plugin.name}  ({len(self.plugin.controls)} parameters, "
              f"loaded in {ms:.0f} ms) ===")
        self.show_page()

    def load_preset(self, slot):
        p = self.presets.get(slot)
        if not p:
            return False
        idx = next((i for i, pl in enumerate(self.plugins) if pl.uri == p["plugin"]), None)
        if idx is None:
            print(f"! preset {label(slot)} needs {p.get('plugin_name', p['plugin'])}, which is not installed")
            return False
        self.slot = slot
        print(f"\n>>> preset {label(slot)} {p['name']}")
        if idx == self.idx and self.engine.loaded is self.plugin:
            for c in self.plugin.controls:      # same plugin: just set the values
                v = float(p["values"].get(c.key, c.default))
                if abs(v - self.values[c.key]) > 1e-9:
                    self.values[c.key] = v
                    self.engine.set(c, v)
            self.page = 0
            self.release_knobs()
            self.show_page()
        else:
            self.load(idx, p.get("values"))
        return True

    def release_knobs(self):
        self.picked = [False] * 4

    def show_page(self):
        state = "BYPASS" if self.bypassed else "on"
        pre = ""
        if self.slot is not None:
            pre = f"{label(self.slot)} {self.presets.get(self.slot)['name']}{' *' if self.edited else ''} | "
        print(f"--- {pre}{self.plugin.name} | page {self.page + 1}/{self.pages} | {state}")
        for name, c in zip(NAMES, self.page_controls()):
            if c:
                print(f"  {name}  {c.label:<22} {c.format(self.values[c.key])}")
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
        code = self.engine.set(c, value)
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
        if k in (0, 1):
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
            if k == 2:
                self.open_save()
            elif k == 3:
                self.open_browser()

    def short_press(self, k):
        if k == 0:
            self.bypassed = not self.bypassed
            self.engine.bypass(self.bypassed)
            print(f"*** {'BYPASS' if self.bypassed else 'EFFECT ON'} ***")
            self.display.bypass(self.bypassed)
        elif k in (1, 2):
            self.page = (self.page + (1 if k == 2 else -1)) % self.pages
            self.release_knobs()
            self.show_page()
        elif k == 3:
            self.slot = None
            self.load(self.idx + 1)

    # --- browser ---
    def open_browser(self):
        self.mode, self.tab = "browse", "presets"
        self.sel = self.slot if self.slot is not None else 0
        print("\n[ presets ]  turn A = move · press D = load · press B/C = plugins · press A = back")
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
        elif self.mode == "save":
            name = "".join(self.save_name)
            old = self.presets.get(self.save_slot)
            where = f"{label(self.save_slot)} " + (f"(replaces {old['name']})" if old else "(empty)")
            print(f"  save: [{name[:self.save_cursor]}|{name[self.save_cursor]}|{name[self.save_cursor + 1:]}]  -> {where}")
            self.display.save(self, where)

    def menu_turn(self, k, v):
        n = v / 128
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
        if self.mode == "browse":
            if k == 0:
                self.back()
            elif k in (1, 2):
                self.tab = "plugins" if self.tab == "presets" else "presets"
                self.sel = self.idx if self.tab == "plugins" else (self.slot or 0)
                print(f"\n[ {self.tab} ]")
                self.show_menu()
            elif k == 3:
                if self.tab == "presets":
                    if not self.presets.get(self.sel):
                        print("  (empty slot)")
                        return
                    self.mode = "play"
                    self.load_preset(self.sel)
                else:
                    self.mode, self.slot = "play", None
                    self.load(self.sel)
        elif self.mode == "save":
            if k == 0:
                print("  save cancelled")
                self.back()
            elif k == 3:
                name = "".join(self.save_name).strip() or self.plugin.name
                self.presets.put(self.save_slot, name, self.plugin, self.values)
                self.slot = self.save_slot
                print(f"  saved {label(self.save_slot)} {name}")
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
            if cc in TURN_CC:
                self.turn(TURN_CC.index(cc), value)
            elif cc in PRESS_CC:
                k = PRESS_CC.index(cc)
                if value >= 64 and not self.down[k]:
                    self.press_down(k)
                elif value < 64 and self.down[k]:
                    self.press_up(k)


def main():
    ap = argparse.ArgumentParser(prog="melon_pedald", description="Melon pedal test controller (NexFoot + mod-host)")
    ap.add_argument("--plugin", default="", help="start with the plugin whose name/URI contains this text")
    ap.add_argument("--preset", type=int, help="start with this preset (1-24)")
    ap.add_argument("--match", default="melon", help="only cycle through plugins containing this text ('' = all)")
    ap.add_argument("--lv2-dir", action="append", help="LV2 folder to scan (default: ~/.lv2 and system folders)")
    ap.add_argument("--midi-port", default="Nexfoot MIDI:1", help="ALSA MIDI port of the controller")
    ap.add_argument("--capture", default="system:capture_1", help="JACK input(s), comma separated")
    ap.add_argument("--playback", default="system:playback_1,system:playback_2", help="JACK outputs")
    ap.add_argument("--port", type=int, default=5555, help="mod-host TCP port")
    ap.add_argument("--presets", default=DEFAULT_PATH, help="preset file")
    ap.add_argument("--list", action="store_true", help="list plugins and their parameters, then exit")
    ap.add_argument("--fake", action="store_true", help="no mod-host: print the commands instead")
    ap.add_argument("--stdin", action="store_true", help="read aseqdump-style lines from stdin instead of MIDI")
    ap.add_argument("--no-lcd", action="store_true", help="don't send state to the melon-display service")
    ap.add_argument("-v", "--verbose", action="store_true", help="show every mod-host command")
    args = ap.parse_args()

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
    try:
        engine.connect()
    except ModHostError as e:
        raise SystemExit(str(e))

    display = Display(enabled=not args.no_lcd)
    store = PresetStore(args.presets)
    pedal = Pedal(engine, plugins, args.capture.split(","), args.playback.split(","), display, store)
    start = next((i for i, p in enumerate(plugins) if args.plugin.lower() in (p.uri + p.name).lower()), 0)
    print(f"Found {len(plugins)} plugins: " + ", ".join(p.name for p in plugins))
    print(f"{sum(1 for p in store.slots if p)} presets in {args.presets}")
    print("A: turn = param 1, press = bypass | B/C: params 2/3, press = page -/+ | "
          "D: param 4, press = next plugin | hold C = save | hold D = presets")
    with pedal.lock:
        if not (args.preset and pedal.load_preset(args.preset - 1)):
            pedal.load(start)

    proc = None
    try:
        if args.stdin:
            source = sys.stdin
        else:
            cmd = ["aseqdump", "-p", args.midi_port]
            if shutil.which("stdbuf"):
                cmd = ["stdbuf", "-oL"] + cmd  # line-buffered, so knob moves arrive at once
            proc = subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                    stderr=subprocess.STDOUT, text=True, bufsize=1)
            source = proc.stdout
        for line in source:
            if proc and ("Invalid port" in line or "Cannot connect" in line):
                raise SystemExit(f"MIDI: {line.strip()} - check `aconnect -l` and use --midi-port")
            pedal.midi(line)
        if proc:
            print("MIDI input ended (controller unplugged?)")
    except KeyboardInterrupt:
        print()
    except ModHostError as e:
        print(f"! {e}")
    finally:
        display.stopped()
        if proc:
            proc.terminate()
        try:
            engine.unload()
        except Exception:
            pass
        print("bye")


if __name__ == "__main__":
    main()

"""melon-pedald, test version 0.1: Livtra NexFoot + mod-host.

Footswitch-knobs A-D:
  turn A-D   -> parameters 1-4 of the current page
  press A    -> bypass on/off
  press B/C  -> previous / next page
  press D    -> next plugin

Knobs send absolute values (0-127), so a knob only "picks up" a parameter
once it passes the parameter's current position. Until then the terminal
says which way to turn. Lists and switches follow the knob directly.

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
import time

from . import catalog
from .display import Display
from .engine import FakeEngine, ModHost, ModHostError

TURN_CC = [57, 68, 74, 89]     # NexFoot A, B, C, D (turn)
PRESS_CC = [21, 25, 26, 27]    # NexFoot A, B, C, D (press)
NAMES = "ABCD"
PICKUP_WINDOW = 3 / 127        # "close enough" to pick up a parameter

CC_LINE = re.compile(r"Control change\s+(\d+),\s*controller\s+(\d+),\s*value\s+(\d+)")


class Pedal:
    def __init__(self, engine, plugins, capture, playback, display=None):
        self.engine = engine
        self.display = display or Display(enabled=False)
        self.plugins = plugins
        self.capture = capture
        self.playback = playback
        self.idx = 0
        self.page = 0
        self.values = {}
        self.bypassed = False
        self.last_cc = [None] * 4
        self.picked = [False] * 4
        self.last_hint = [0.0] * 4

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

    # --- actions ---
    def load(self, idx):
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
        self.page = 0
        if self.bypassed:
            self.engine.bypass(True)
        self.release_knobs()
        print(f"\n=== {self.plugin.name}  ({len(self.plugin.controls)} parameters, "
              f"loaded in {ms:.0f} ms) ===")
        self.show_page()

    def release_knobs(self):
        self.picked = [False] * 4

    def show_page(self):
        state = "BYPASS" if self.bypassed else "on"
        print(f"--- {self.plugin.name} | page {self.page + 1}/{self.pages} | {state}")
        for name, c in zip(NAMES, self.page_controls()):
            if c:
                print(f"  {name}  {c.label:<22} {c.format(self.values[c.key])}")
            else:
                print(f"  {name}  -")
        self.display.page(self)

    def turn(self, k, cc_value):
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
        self.values[c.key] = value
        code = self.engine.set(c, value)
        err = "" if code >= 0 else f"   ! mod-host error {code}"
        print(f"  {NAMES[k]}  {c.label:<22} {c.format(value)}{err}")
        self.display.value(k, c, value)

    def press(self, k):
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
            self.load(self.idx + 1)

    def midi(self, line):
        m = CC_LINE.search(line)
        if not m:
            return
        _, cc, value = map(int, m.groups())
        if cc in TURN_CC:
            self.turn(TURN_CC.index(cc), value)
        elif cc in PRESS_CC and value >= 64:
            self.press(PRESS_CC.index(cc))


def main():
    ap = argparse.ArgumentParser(prog="melon_pedald", description="Melon pedal test controller (NexFoot + mod-host)")
    ap.add_argument("--plugin", default="", help="start with the plugin whose name/URI contains this text")
    ap.add_argument("--match", default="melon", help="only cycle through plugins containing this text ('' = all)")
    ap.add_argument("--lv2-dir", action="append", help="LV2 folder to scan (default: ~/.lv2 and system folders)")
    ap.add_argument("--midi-port", default="Nexfoot MIDI:1", help="ALSA MIDI port of the controller")
    ap.add_argument("--capture", default="system:capture_1", help="JACK input(s), comma separated")
    ap.add_argument("--playback", default="system:playback_1,system:playback_2", help="JACK outputs")
    ap.add_argument("--port", type=int, default=5555, help="mod-host TCP port")
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
    pedal = Pedal(engine, plugins, args.capture.split(","), args.playback.split(","), display)
    start = next((i for i, p in enumerate(plugins) if args.plugin.lower() in (p.uri + p.name).lower()), 0)
    print(f"Found {len(plugins)} plugins: " + ", ".join(p.name for p in plugins))
    print("A: turn = param 1, press = bypass | B/C: params 2/3, press = page -/+ | D: param 4, press = next plugin")
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

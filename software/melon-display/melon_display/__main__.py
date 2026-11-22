"""melon-display: draws the pedal GUI on the ST7789 from state sent by the controller.

    python3 -m melon_display                 # service: listen on UDP 127.0.0.1:5600
    python3 -m melon_display --test          # colour bars + TOP arrow (set rotation/invert/bgr)
    python3 -m melon_display --demo          # fake knob moves, no controller needed
    python3 -m melon_display --png out/      # render sample screens to PNG files (no hardware)
"""
import argparse
import copy
import json
import math
import os
import socket
import sys
import time

from . import ui

POPUP_SECONDS = 1.0
MIN_FRAME = 1 / 30

SAMPLE_DRIVE = {
    "screen": "play", "bank": "BANK 1", "page": 1, "pages": 2, "cpu": 18, "midi": True,
    "preset": {"number": "03", "name": "Crunch Lead", "edited": True},
    "plugin": "Melon Drive",
    "params": [
        {"label": "Drive", "value": 62, "min": 0, "max": 100, "unit": "%", "default": 50},
        {"label": "Tone", "value": 4800, "min": 200, "max": 10000, "unit": "Hz", "log": True, "default": 2000},
        {"label": "Level", "value": -3, "min": -24, "max": 12, "unit": "dB", "default": 0},
        {"label": "Mode", "value": 1, "kind": "enum", "options": ["Sym", "Asym", "Fuzz"]},
    ],
}
EQ_GAINS = [0, 1, 2, 2.5, 3, 3, 2.5, 2, 4.5, 3, -1.5, -3, -4, -4.5, -4, -3, -2, -1, 0, 1, 2, 3,
            3.5, 4, 4, 3.5, 3, 2, 1, 0, -1]
EQ_FREQS = ["20", "25", "31.5", "40", "50", "63", "80", "100", "125", "160", "200", "250", "315",
            "400", "500", "630", "800", "1k", "1.25k", "1.6k", "2k", "2.5k", "3.15k", "4k", "5k",
            "6.3k", "8k", "10k", "12.5k", "16k", "20k"]
SAMPLE_EQ = {
    "screen": "play", "bank": "BANK 1", "page": 3, "pages": 8, "cpu": 21,
    "preset": {"number": "01", "name": "Clean Sparkle"},
    "plugin": "Melon GraphicEQ", "graph_note": "GraphicEQ · bands 9–12",
    "graph": {"values": EQ_GAINS, "min": -12, "max": 12, "highlight": [8, 11],
              "labels": [[0, "20"], [7, "100"], [17, "1k"], [27, "10k"]]},
    "params": [{"label": f"{EQ_FREQS[b]} Hz", "value": EQ_GAINS[b], "min": -12, "max": 12,
                "unit": "dB", "default": 0, "band": b} for b in range(8, 12)],
}
SAMPLE_CHAIN = dict(SAMPLE_DRIVE, plugin="3/7 · Melon Dirt", chain=[
    {"tag": "GATE", "on": True}, {"tag": "COMP", "on": False}, {"tag": "DRIVE", "on": True, "sel": True},
    {"tag": "AMP", "on": True}, {"tag": "CAB", "on": True}, {"tag": "MOD", "on": False},
    {"tag": "DLY", "on": True}])
TUNER_BASE = {
    "screen": "tuner", "bank": "PLUGIN 16/16", "page": 1, "pages": 3, "midi": True,
    "preset": {"number": "--", "name": "Melon Tuner"}, "plugin": "Melon Tuner",
    "tuner": {"tuning": "Chromatic", "strings": [], "reference": 440.0, "mute": False, "reading": None},
}
TUNER_READING = {"note": "A", "acc": "", "octave": 2, "cents": -12.4, "hz": 109.2, "string": None,
                 "hint": "", "in_tune": False}
BOOT = {"screen": "boot", "boot": {"steps": [["Display", "ok"], ["Waiting for controller", "wait"]]}}


class Screen:
    def __init__(self, lcd):
        self.lcd = lcd
        self.st = copy.deepcopy(BOOT)
        self.popup, self.popup_until, self.fine = None, 0.0, False
        self.dirty, self.last = True, 0.0
        self.tuner_idle_since = None        # time the last tuner note ended

    def tuner_idle(self):
        return None if self.tuner_idle_since is None else time.monotonic() - self.tuner_idle_since

    # ---- state
    def apply(self, m):
        op = m.get("op", "update")
        if op == "update":
            m = {k: v for k, v in m.items() if k != "op"}
            if "params" in m and "screen" not in m and self.st.get("screen") == "boot":
                m["screen"] = "play"
            self.st.update(m)
        elif op == "param":
            i, params = int(m.get("index", 0)), self.st.get("params") or []
            if 0 <= i < len(params) and params[i] is not None:
                p = params[i]
                p["value"] = m.get("value", p.get("value"))
                p["text"] = m.get("text")
                g = self.st.get("graph")
                if g and p.get("band") is not None and 0 <= p["band"] < len(g.get("values", [])):
                    g["values"][p["band"]] = p["value"]
                if m.get("popup", True):
                    self.popup, self.popup_until = i, time.monotonic() + POPUP_SECONDS
        elif op == "fine":
            self.fine = bool(m.get("on"))
        elif op == "tuner":                 # frequent: reading (or None) / mute
            t = self.st.setdefault("tuner", {})
            if "mute" in m:
                t["mute"] = bool(m["mute"])
            if "reading" in m:
                r = m["reading"]
                if r:
                    t["last"], self.tuner_idle_since = r, None
                elif t.get("reading") is not None:
                    self.tuner_idle_since = time.monotonic()
                t["reading"] = r
            if self.st.get("screen") != "tuner":
                return
        if op == "update" and m.get("screen") == "tuner":
            self.tuner_idle_since = None
            self.st.get("tuner", {}).pop("last", None)
        self.dirty = True

    # ---- drawing
    def frame(self):
        scr = self.st.get("screen", "play")
        if scr == "boot":
            return ui.boot(self.st)
        if scr == "test":
            return ui.test_pattern(*self.lcd_settings())
        if scr == "list":
            return ui.list_screen(self.st)
        if scr == "save":
            return ui.save_screen(self.st)
        if scr == "tuner":
            return ui.tuner(self.st, idle=self.tuner_idle())
        pop = self.popup if time.monotonic() < self.popup_until or self.fine else None
        return ui.play(self.st, popup=pop, fine=self.fine)

    def lcd_settings(self):
        a = getattr(self.lcd, "settings", (90, True, False))
        return a

    def tick(self):
        now = time.monotonic()
        if self.popup is not None and not self.fine and now >= self.popup_until:
            self.popup = None
            self.dirty = True
        idle = self.tuner_idle() if self.st.get("screen") == "tuner" else None
        if idle is not None and idle >= 1.5:          # the dimmed last note goes away
            self.tuner_idle_since = None
            self.st.get("tuner", {}).pop("last", None)
            self.dirty = True
        if self.dirty and now - self.last >= MIN_FRAME:
            self.lcd.show(self.frame())
            self.dirty, self.last = False, now

    def next_wakeup(self):
        now = time.monotonic()
        t = 0.5
        if self.popup is not None and not self.fine:
            t = min(t, max(0.0, self.popup_until - now))
        if self.dirty:
            t = min(t, max(0.0, MIN_FRAME - (now - self.last)))
        idle = self.tuner_idle()
        if idle is not None:
            t = min(t, max(0.0, 1.5 - idle))
        return max(0.005, t)


def serve(screen, port):
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.bind(("127.0.0.1", port))
    print(f"melon-display: listening on udp://127.0.0.1:{port}", flush=True)
    while True:
        try:
            screen.tick()
        except Exception as e:                       # a bad state must not kill the service
            print(f"melon-display: draw failed: {e!r}", file=sys.stderr, flush=True)
            screen.dirty, screen.last = False, time.monotonic()
        sock.settimeout(screen.next_wakeup())
        try:
            data, _ = sock.recvfrom(65535)
        except socket.timeout:
            continue
        while data:
            try:
                msg = json.loads(data)
                if not isinstance(msg, dict):
                    raise ValueError("message must be a JSON object")
                screen.apply(msg)
            except Exception as e:
                print(f"melon-display: bad message ({e}): {data[:200]!r}", file=sys.stderr, flush=True)
            sock.settimeout(0)
            try:
                data, _ = sock.recvfrom(65535)       # drain the queue, draw once
            except (BlockingIOError, socket.timeout):
                data = None


def demo(screen):
    """Moves fake knobs so the screen can be checked without a controller."""
    screen.apply({"op": "update", **copy.deepcopy(SAMPLE_DRIVE)})
    t0 = time.monotonic()
    phase = -1
    while True:
        t = time.monotonic() - t0
        ph = int(t // 6) % 4
        if ph != phase:
            phase = ph
            if ph == 2:
                screen.apply({"op": "update", **copy.deepcopy(SAMPLE_EQ)})
            if ph == 0:
                screen.apply({"op": "update", **copy.deepcopy(SAMPLE_DRIVE)})
            screen.apply({"op": "update", "bypass": ph == 3})
        if ph in (0, 2) and int(t * 10) % 3 == 0:
            k = int(t // 1.5) % 4 if ph == 0 else int(t // 1.5) % 4
            p = screen.st["params"][k]
            if p.get("kind") != "enum":
                lo, hi = p["min"], p["max"]
                v = lo + (hi - lo) * (0.5 + 0.45 * math.sin(t * 1.3 + k))
                screen.apply({"op": "param", "index": k, "value": round(v, 1)})
        screen.tick()
        time.sleep(0.03)


class PngSink:
    def __init__(self):
        self.img = None

    def show(self, img):
        self.img = img


def render_pngs(outdir):
    os.makedirs(outdir, exist_ok=True)
    cases = {
        "play": (SAMPLE_DRIVE, None, False),
        "bypass": (dict(SAMPLE_DRIVE, bypass=True), None, False),
        "popup": (SAMPLE_DRIVE, 0, False),
        "fine": (dict(SAMPLE_DRIVE, params=[dict(SAMPLE_DRIVE["params"][0], value=62.2)] + SAMPLE_DRIVE["params"][1:]), 0, True),
        "popup-enum": (SAMPLE_DRIVE, 3, False),
        "eq": (SAMPLE_EQ, None, False),
        "chain": (SAMPLE_CHAIN, None, False),
        "chain-bypass": (dict(SAMPLE_CHAIN, bypass=True), None, False),
        "chain-popup": (SAMPLE_CHAIN, 1, False),
        "boot": (BOOT, None, False),
    }
    def tun(reading=None, **kw):
        st = copy.deepcopy(TUNER_BASE)
        st.update({k: v for k, v in kw.items() if k != "tuner"})
        st["tuner"].update(kw.get("tuner", {}), reading=reading)
        return st
    tuner_cases = {
        "tuner-idle": (tun(), None),
        "tuner-flat": (tun(TUNER_READING), None),
        "tuner-intune": (tun(dict(TUNER_READING, cents=0.8, hz=110.1, in_tune=True)), None),
        "tuner-muted-sharp": (tun(dict(TUNER_READING, note="F", acc="#", octave=3, cents=21.0, hz=187.2),
                                  tuner={"mute": True}), None),
        "tuner-bypass": (tun(dict(TUNER_READING, cents=-3.5), bypass=True), None),
        "tuner-strings": (tun(dict(TUNER_READING, note="G", octave=3, cents=-37.0, hz=191.9, string=3),
                              tuner={"tuning": "Guitar Standard", "strings": ["E", "A", "D", "G", "B", "E"]}), None),
        "tuner-tune-up": (tun(dict(TUNER_READING, note="E", octave=2, cents=-180.0, hz=74.4, string=0, hint="Tune up"),
                              tuner={"tuning": "Guitar Drop D", "strings": ["D", "A", "D", "G", "B", "E"]}), None),
        "tuner-fading": (tun(None, tuner={"last": dict(TUNER_READING, cents=1.5, in_tune=True)}), 0.5),
    }
    for name, (st, idle) in tuner_cases.items():
        path = os.path.join(outdir, f"{name}.png")
        ui.tuner(st, idle=idle).save(path)
        print(path)
    for name, (st, pop, fine) in cases.items():
        img = ui.boot(st) if st.get("screen") == "boot" else ui.play(st, popup=pop, fine=fine)
        path = os.path.join(outdir, f"{name}.png")
        img.save(path)
        print(path)
    ui.test_pattern(90, True, False).save(os.path.join(outdir, "test.png"))


def main():
    ap = argparse.ArgumentParser(prog="melon-display", description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--port", type=int, default=5600)
    ap.add_argument("--rotation", type=int, choices=(0, 90, 180, 270), default=90)
    ap.add_argument("--no-invert", action="store_true", help="for panels that show inverted colours")
    ap.add_argument("--bgr", action="store_true", help="for panels that swap red and blue")
    ap.add_argument("--spi-hz", type=int, default=40_000_000)
    ap.add_argument("--dc", type=int, default=25)
    ap.add_argument("--rst", type=int, default=24)
    ap.add_argument("--offset-x", type=int, default=0)
    ap.add_argument("--offset-y", type=int, default=0)
    g = ap.add_mutually_exclusive_group()
    g.add_argument("--test", action="store_true")
    g.add_argument("--demo", action="store_true")
    g.add_argument("--png", metavar="DIR")
    a = ap.parse_args()

    if a.png:
        render_pngs(a.png)
        return

    from .st7789 import ST7789
    lcd = ST7789(dc=a.dc, rst=a.rst, speed_hz=a.spi_hz, rotation=a.rotation,
                 invert=not a.no_invert, bgr=a.bgr, offset_x=a.offset_x, offset_y=a.offset_y)
    lcd.settings = (a.rotation, not a.no_invert, a.bgr)
    screen = Screen(lcd)
    try:
        if a.test:
            screen.apply({"op": "update", "screen": "test"})
            screen.tick()
            print("Test pattern shown. Ctrl+C to quit.")
            while True:
                time.sleep(1)
        elif a.demo:
            demo(screen)
        else:
            serve(screen, a.port)
    except KeyboardInterrupt:
        pass
    finally:
        lcd.close()


if __name__ == "__main__":
    main()

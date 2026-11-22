"""Sends the pedal state to the melon-display service (software/melon-display).

JSON over UDP to 127.0.0.1:5600. Never blocks and never raises, so the pedal
keeps working when the display service is stopped or not installed.
"""
import json
import socket
from collections import Counter


class Display:
    def __init__(self, enabled=True, host="127.0.0.1", port=5600):
        self.enabled = enabled
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)
        self.bands = []            # GraphicEQ-style plugins: controls drawn as a graph
        self.pedal = None          # set by page(): file names for the Library controls

    def _send(self, msg):
        if not self.enabled:
            return
        try:
            self.sock.sendto(json.dumps(msg).encode(), self.addr)
        except OSError:
            pass

    # ---- what the pedal calls
    def page(self, pedal, popup=False):
        """Full state: after loading a plugin or preset, changing page or bypass."""
        plugin = pedal.plugin
        self.pedal = pedal
        self.tuner_mute = None
        if getattr(pedal, "tuner_visible", False):
            return self._tuner_page(pedal)
        self.bands = _bands(plugin.controls)
        controls = pedal.page_controls()
        preset = pedal.presets.get(pedal.slot) if pedal.slot is not None else None
        if preset:
            bank = f"BANK {pedal.slot // 6 + 1}"
            band = {"number": f"{pedal.slot % 6 + 1:02d}", "name": preset["name"], "edited": pedal.edited}
            sub = plugin.name
        else:
            bank = f"PLUGIN {pedal.idx + 1}/{len(pedal.plugins)}"
            band = {"number": "--", "name": plugin.name, "edited": False}
            sub = "not saved · hold C to save"
        msg = {
            "op": "update", "screen": "play", "midi": getattr(self, "midi_ok", True),
            "bank": bank, "preset": band, "plugin": sub,
            "page": pedal.page + 1, "pages": pedal.pages,
            "bypass": pedal.bypassed,
            "params": [self._param(c, pedal.values[c.key]) if c else None for c in controls],
            "graph": None,
        }
        if self.bands:
            on = [self.bands.index(c) for c in controls if c in self.bands]
            msg["graph"] = {
                "values": [pedal.values[c.key] for c in self.bands],
                "min": self.bands[0].minimum, "max": self.bands[0].maximum,
                "highlight": [min(on), max(on)] if on else [],
                "labels": [],
            }
            msg["graph_note"] = (f"bands {min(on) + 1}–{max(on) + 1} · page {pedal.page + 1}/{pedal.pages}"
                                 if on else f"page {pedal.page + 1}/{pedal.pages}")
        self._send(msg)

    def value(self, k, control, value):
        """Knob k (0-3) changed `control` to `value`."""
        if getattr(self, "tuner_mute", None) is control:      # tuner screen: knob 1 = Mute
            self._send({"op": "tuner", "mute": value >= 0.5 * (control.minimum + control.maximum)})
            return
        p = self._param(control, value)
        self._send({"op": "param", "index": k, "value": p["value"], "text": p.get("text"), "popup": True})

    def browser(self, pedal):
        from .presets import SLOTS, BANK_SIZE, BANKS
        if pedal.tab == "presets":
            rows = []
            for i in range(SLOTS):
                p = pedal.presets.get(i)
                rows.append({"n": f"{i % BANK_SIZE + 1:02d}",
                             "name": p["name"] if p else "— empty —", "empty": not p,
                             "meta": (p.get("plugin_name", "").replace("Melon ", "") if p else ""),
                             "mark": "▶" if i == pedal.slot else ""})
            lst = {"title": "Presets", "right": f"BANK {pedal.sel // BANK_SIZE + 1} of {BANKS}",
                   "hints": [["1", "move · back"], ["2", "plugins"], ["4", "push: load", True]]}
        else:
            rows = [{"n": f"{i + 1:02d}", "name": pl.name, "meta": f"{len(pl.controls)} params",
                     "mark": "✓" if i == pedal.idx else ""} for i, pl in enumerate(pedal.plugins)]
            lst = {"title": "Plugins", "right": f"{len(rows)} installed",
                   "hints": [["1", "move · back"], ["2", "presets"], ["4", "push: load", True]]}
        lst.update(rows=rows, selected=pedal.sel)
        self._send({"op": "update", "screen": "list", "list": lst})

    def files(self, pedal):
        """File browser of Melon NAM / Melon Cab: folders first, then files."""
        from . import library
        fb = pedal.fb
        lib, c = fb["lib"], fb["c"]
        current = pedal.files.get(c.key)
        here = fb["folder"]
        rows = []
        for kind, name in fb["rows"]:
            if kind == "none":
                rows.append({"n": "", "name": "— None —", "empty": True, "mark": "✓" if not current else ""})
            elif kind == "dir":
                inside = f"{here}/{name}/" if here else f"{name}/"
                n = sum(1 for f in lib.files if f.startswith(inside))
                rows.append({"n": "▸", "name": name, "meta": str(n)})
            else:
                rel = f"{here}/{name}" if here else name
                ext = name.rsplit(".", 1)[-1].upper() if "." in name else ""
                rows.append({"n": "", "name": library.title(name), "meta": ext,
                             "mark": "✓" if rel == current else ""})
        title = here.rsplit("/", 1)[-1] if here else f"{library.LIB_PARAMS.get(c.short_id, '')} library"
        lst = {"title": title[:22], "right": f"{pedal.sel + 1}/{len(rows)}",
               "hints": [[str(fb["back"] + 1), "push: up" + (" · jump" if fb["jump"] == fb["back"] else "")],
                         [str(fb["jump"] + 1), "jump"] if fb["jump"] != fb["back"] else None,
                         [str(fb["k"] + 1), "turn · push: open", True]],
               "rows": rows, "selected": pedal.sel}
        lst["hints"] = [h for h in lst["hints"] if h]
        self._send({"op": "update", "screen": "list", "list": lst})

    def save(self, pedal, where):
        from .presets import CHARSET
        name, cur = pedal.save_name, pedal.save_cursor
        ch = name[cur]
        i = CHARSET.find(ch) if ch in CHARSET else 0
        wheel = [CHARSET[(i + d) % len(CHARSET)] for d in range(-3, 4)]
        self._send({"op": "update", "screen": "save", "save": {
            "name": "".join(name), "cursor": cur, "wheel": wheel, "plugin": pedal.plugin.name,
            "tiles": [
                {"label": "cursor · push: cancel", "value": f"◂ {cur + 1}/{len(name)} ▸"},
                {"label": "turn: character", "value": "space" if ch == " " else ch},
                {"label": "turn: slot", "value": where},
                {"label": "push", "value": "Save", "accent": True},
            ]}})

    def tuner(self, reading):
        """A new tuner reading (tuner.reading() dict, or None = no note). Called ~50 times/s."""
        self._send({"op": "tuner", "reading": reading})

    def _tuner_page(self, pedal):
        st = pedal.tuner_state()
        self.tuner_mute = pedal.plugin.control("mute")
        preset = pedal.presets.get(pedal.slot) if pedal.slot is not None else None
        self._send({
            "op": "update", "screen": "tuner", "midi": getattr(self, "midi_ok", True),
            "bank": f"BANK {pedal.slot // 6 + 1}" if preset else f"PLUGIN {pedal.idx + 1}/{len(pedal.plugins)}",
            "preset": {"number": f"{pedal.slot % 6 + 1:02d}" if preset else "--",
                       "name": preset["name"] if preset else pedal.plugin.name, "edited": pedal.edited},
            "plugin": pedal.plugin.name,
            "page": pedal.page + 1, "pages": pedal.pages, "bypass": pedal.bypassed,
            "params": [], "graph": None,
            "tuner": {"tuning": st["tuning"], "strings": st["strings"], "reference": st["reference"],
                      "mute": st["mute"], "reading": None},
        })

    def midi(self, connected):
        self.midi_ok = connected
        self._send({"op": "update", "midi": bool(connected)})

    def bypass(self, on):
        self._send({"op": "update", "bypass": bool(on)})

    def stopped(self):
        self._send({"op": "update", "screen": "boot",
                    "boot": {"steps": [["Display", "ok"], ["Waiting for controller", "wait"]]}})

    # ---- Control -> display parameter
    def _param(self, c, value):
        p = {"label": c.label, "min": c.minimum, "max": c.maximum, "default": c.default}
        if c.choices:
            vals = [v for v, _ in c.choices]
            idx = min(range(len(vals)), key=lambda i: abs(vals[i] - value))
            p.update(kind="enum", options=[lab for _, lab in c.choices], value=idx,
                     default=min(range(len(vals)), key=lambda i: abs(vals[i] - c.default)),
                     min=0, max=len(vals) - 1)
        elif c.toggled:
            mid = (c.minimum + c.maximum) / 2
            p.update(kind="toggle", value=1 if value >= mid else 0, min=0, max=1)
        else:
            p.update(value=value, unit=c.unit, log=c.logarithmic)
            if c.integer:
                p["kind"] = "int"
        if c in self.bands:
            p["band"] = self.bands.index(c)
        text = self.pedal.lib_text(c, value) if self.pedal is not None else None
        if text is not None:                       # Melon NAM / Melon Cab: show the file name
            n = len(self.pedal.lib_of(c).files)
            p.update(kind="file", text=text, unit="", min=-1, max=max(0, n - 1))
        return p


def _bands(controls):
    """Ten or more dB controls with the same range (e.g. Melon GraphicEQ) -> draw them as a graph."""
    db = [c for c in controls if c.unit == "dB" and not c.choices and not c.toggled]
    if len(db) < 10:
        return []
    rng, n = Counter((c.minimum, c.maximum) for c in db).most_common(1)[0]
    return [c for c in db if (c.minimum, c.maximum) == rng] if n >= 10 and rng[0] < 0 < rng[1] else []

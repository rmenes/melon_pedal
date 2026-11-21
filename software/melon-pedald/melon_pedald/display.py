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

    def _send(self, msg):
        if not self.enabled:
            return
        try:
            self.sock.sendto(json.dumps(msg).encode(), self.addr)
        except OSError:
            pass

    # ---- what the pedal calls
    def page(self, pedal):
        """Full state: after loading a plugin, changing page or bypass."""
        plugin = pedal.plugin
        self.bands = _bands(plugin.controls)
        controls = pedal.page_controls()
        msg = {
            "op": "update", "screen": "play", "midi": True,
            "bank": f"PLUGIN {pedal.idx + 1}/{len(pedal.plugins)}",
            "preset": {"number": f"{pedal.idx + 1:02d}", "name": plugin.name},
            "plugin": f"{len(plugin.controls)} parameters",
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
        p = self._param(control, value)
        self._send({"op": "param", "index": k, "value": p["value"], "popup": True})

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
        return p


def _bands(controls):
    """Ten or more dB controls with the same range (e.g. Melon GraphicEQ) -> draw them as a graph."""
    db = [c for c in controls if c.unit == "dB" and not c.choices and not c.toggled]
    if len(db) < 10:
        return []
    rng, n = Counter((c.minimum, c.maximum) for c in db).most_common(1)[0]
    return [c for c in db if (c.minimum, c.maximum) == rng] if n >= 10 and rng[0] < 0 < rng[1] else []

"""Tiny client for melon-display. Standard library only: copy this file into any
controller, or `from melon_display.client import Display`.

    d = Display()
    d.update(preset={"number": "03", "name": "Crunch Lead"}, plugin="Melon GraphicEQ",
             params=[{"label": "125 Hz", "value": 4.5, "min": -12, "max": 12, "unit": "dB", "default": 0},
                     ...up to 4...])
    d.param(0, 4.6)          # knob 1 moved: updates the tile and shows the value pop-up
    d.bypass(True)

Messages are JSON over UDP to 127.0.0.1:5600. Sending never blocks and never
raises if the display service is not running, so it can't stall the controller.
"""
import json
import socket


class Display:
    def __init__(self, host="127.0.0.1", port=5600):
        self.addr = (host, port)
        self.sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.sock.setblocking(False)

    def send(self, msg):
        try:
            self.sock.sendto(json.dumps(msg).encode(), self.addr)
        except OSError:
            pass

    def update(self, **state):
        """Merge top-level keys into the screen state: bank, preset, plugin, page,
        pages, params, bypass, cpu, midi, graph, graph_note, bypass_note, boot, screen."""
        self.send({"op": "update", **state})

    def param(self, index, value, text=None, popup=True):
        """Value of tile `index` (0-3) changed. text = optional preformatted value."""
        m = {"op": "param", "index": index, "value": value, "popup": popup}
        if text is not None:
            m["text"] = text
        self.send(m)

    def fine(self, on):
        """Fine adjust on/off (knob 3 held): pop-up shows the zoomed ruler."""
        self.send({"op": "fine", "on": bool(on)})

    def bypass(self, on):
        self.update(bypass=bool(on))

    def screen(self, name):
        """'play' | 'boot' | 'test'"""
        self.update(screen=name)

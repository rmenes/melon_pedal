"""Which inputs and outputs of the audio interface the pedal uses.

melon-audio (software/system) picks the interface and starts JACK on it; the interface's channels then appear
as JACK ports system:capture_1..N and system:playback_1..M. This module lists the choices for them:

  inputs   mono "In k" (one channel, fed to both sides of a stereo plugin) and stereo pairs "In k+k+1"
  outputs  stereo pairs "Out k+k+1" and mono "Out k" (left side of the chain only)

Changing them only changes JACK connections, so it is instant (no restart). The choice is remembered per
interface (melon-audio's card id, env MELON_CARD) in ~/.config/melon-pedald/audio-ports.json, so the Sono and
an AMS-22 each keep their own.
"""
import json
import os
import re
import shutil
import subprocess

PORTS_PATH = os.path.expanduser("~/.config/melon-pedald/audio-ports.json")
CAP, PB = "system:capture_", "system:playback_"


def card():
    """The interface in use (set by melon-audio in /run/melon-pedal/audio.env), or 'default'."""
    return os.environ.get("MELON_CARD") or "default"


def card_info():
    return os.environ.get("MELON_CARD_INFO") or ""


def _num(port):
    m = re.search(r"_(\d+)$", port)
    return int(m.group(1)) if m else 0


def jack_counts(fallback_in=2, fallback_out=2):
    """(number of capture ports, number of playback ports) of the JACK system client."""
    if shutil.which("jack_lsp"):
        try:
            out = subprocess.run(["jack_lsp"], capture_output=True, text=True, timeout=3).stdout.split()
            n_in = max((_num(p) for p in out if p.startswith(CAP)), default=0)
            n_out = max((_num(p) for p in out if p.startswith(PB)), default=0)
            if n_in and n_out:
                return n_in, n_out
        except (OSError, subprocess.SubprocessError):
            pass
    return fallback_in, fallback_out


def input_options(n):
    opts = [{"id": str(k), "label": f"In {k}", "ports": [f"{CAP}{k}"], "stereo": False} for k in range(1, n + 1)]
    opts += [{"id": f"{k}+{k + 1}", "label": f"In {k}+{k + 1}", "ports": [f"{CAP}{k}", f"{CAP}{k + 1}"],
              "stereo": True} for k in range(1, n, 2)]
    return opts


def output_options(n):
    opts = [{"id": f"{k}+{k + 1}", "label": f"Out {k}+{k + 1}", "ports": [f"{PB}{k}", f"{PB}{k + 1}"],
             "stereo": True} for k in range(1, n, 2)]
    opts += [{"id": str(k), "label": f"Out {k}", "ports": [f"{PB}{k}"], "stereo": False} for k in range(1, n + 1)]
    return opts


def option_id(ports):
    """['system:capture_1','system:capture_2'] -> '1+2'; ['system:playback_3'] -> '3'."""
    nums = [_num(p) for p in ports]
    if len(nums) == 1:
        return str(nums[0])
    if len(nums) == 2 and nums[1] == nums[0] + 1:
        return f"{nums[0]}+{nums[1]}"
    return "custom"


def find(options, oid):
    return next((o for o in options if o["id"] == oid), None)


class PortStore:
    """Remembered capture / playback ports per interface."""

    def __init__(self, path=PORTS_PATH):
        self.path = path

    def _read(self):
        try:
            with open(self.path, encoding="utf-8") as f:
                data = json.load(f)
            return data if isinstance(data, dict) else {}
        except (OSError, ValueError):
            return {}

    def get(self, card_id):
        e = self._read().get(card_id) or {}
        cap, pb = e.get("capture"), e.get("playback")
        ok = lambda v: isinstance(v, list) and v and all(isinstance(x, str) for x in v)  # noqa: E731
        return (cap if ok(cap) else None), (pb if ok(pb) else None)

    def put(self, card_id, capture, playback):
        data = self._read()
        data[card_id] = {"capture": list(capture), "playback": list(playback)}
        os.makedirs(os.path.dirname(self.path) or ".", exist_ok=True)
        tmp = self.path + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(data, f, indent=1, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, self.path)

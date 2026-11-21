"""Finds installed LV2 plugins and reads their controls from the .ttl files.

Two kinds of controls are supported:
- LV2 parameters (lv2:Parameter / patch:writable), which JUCE plugins such as
  Melon Plugins use. Set with mod-host `patch_set`.
- Classic control input ports (most other LV2 plugins). Set with `param_set`.
"""
import math
import os
from dataclasses import dataclass, field

from .ttl import IRI, Graph

LV2 = "http://lv2plug.in/ns/lv2core#"
RDF = "http://www.w3.org/1999/02/22-rdf-syntax-ns#"
RDFS = "http://www.w3.org/2000/01/rdf-schema#"
DOAP = "http://usefulinc.com/ns/doap#"
PATCH = "http://lv2plug.in/ns/ext/patch#"
PPROP = "http://lv2plug.in/ns/ext/port-props#"
UNITS = "http://lv2plug.in/ns/extensions/units#"

UNIT_SUFFIX = {
    "db": "dB", "hz": "Hz", "khz": "kHz", "mhz": "MHz", "ms": "ms", "s": "s",
    "pc": "%", "bpm": "BPM", "semitone12TET": "st", "cent": "ct", "oct": "oct",
}

DEFAULT_LV2_DIRS = [
    os.path.expanduser("~/.lv2"),
    "/usr/local/lib/lv2",
    "/usr/lib/lv2",
    "/usr/lib/aarch64-linux-gnu/lv2",
]


@dataclass
class Control:
    kind: str          # "param" (LV2 parameter, patch_set) or "port" (control port, param_set)
    key: str           # parameter URI or port symbol
    label: str
    minimum: float
    maximum: float
    default: float
    unit: str = ""
    toggled: bool = False
    integer: bool = False
    logarithmic: bool = False
    choices: list = field(default_factory=list)   # [(value, label)] for enumerations

    @property
    def short_id(self):
        return self.key.rsplit(":", 1)[-1].rsplit("#", 1)[-1] if self.kind == "param" else self.key

    def to_norm(self, value):
        if self.choices:
            vals = [v for v, _ in self.choices]
            idx = min(range(len(vals)), key=lambda i: abs(vals[i] - value))
            return (idx + 0.5) / len(vals)
        lo, hi = self.minimum, self.maximum
        if hi == lo:
            return 0.0
        if self.logarithmic and lo > 0:
            return math.log(value / lo) / math.log(hi / lo)
        return (value - lo) / (hi - lo)

    def from_norm(self, n):
        n = min(max(n, 0.0), 1.0)
        if self.choices:
            return self.choices[min(int(n * len(self.choices)), len(self.choices) - 1)][0]
        if self.toggled:
            return self.maximum if n >= 0.5 else self.minimum
        lo, hi = self.minimum, self.maximum
        v = lo * (hi / lo) ** n if (self.logarithmic and lo > 0) else lo + n * (hi - lo)
        return float(round(v)) if self.integer else v

    @property
    def discrete(self):
        return bool(self.choices) or self.toggled

    def format(self, value):
        for v, lab in self.choices:
            if abs(v - value) < 1e-6:
                return lab
        if self.toggled:
            return "On" if value >= 0.5 * (self.minimum + self.maximum) else "Off"
        unit = self.unit
        if unit == "Hz" and abs(value) >= 1000:
            value, unit = value / 1000, "kHz"
        if self.integer:
            txt = f"{value:.0f}"
        elif abs(value) >= 100:
            txt = f"{value:.0f}"
        elif abs(value) >= 10:
            txt = f"{value:.1f}"
        else:
            txt = f"{value:.2f}"
        if txt in ("-0.0", "-0.00", "-0"):
            txt = txt[1:]
        return f"{txt} {unit}".strip()


@dataclass
class Plugin:
    uri: str
    name: str
    bundle: str
    audio_in: list
    audio_out: list
    controls: list


def _num(x, default=0.0):
    try:
        return float(x)
    except (TypeError, ValueError):
        return default


def _control(g, node, kind, key, label):
    props = set(g.objects(node, IRI(LV2 + "portProperty")))
    unit = g.value(node, IRI(UNITS + "unit"))
    unit_txt = ""
    if isinstance(unit, IRI) and unit.startswith(UNITS):
        unit_txt = UNIT_SUFFIX.get(unit[len(UNITS):], "")
    elif unit is not None:
        sym = g.value(unit, IRI(UNITS + "symbol"))
        unit_txt = str(sym) if sym else ""
    choices = []
    for sp in g.objects(node, IRI(LV2 + "scalePoint")):
        choices.append((_num(g.value(sp, IRI(RDF + "value"))), str(g.value(sp, IRI(RDFS + "label"), ""))))
    choices.sort()
    lo = _num(g.value(node, IRI(LV2 + "minimum")), 0.0)
    hi = _num(g.value(node, IRI(LV2 + "maximum")), 1.0)
    enum = IRI(LV2 + "enumeration") in props
    return Control(
        kind=kind, key=key, label=str(label), minimum=lo, maximum=hi,
        default=_num(g.value(node, IRI(LV2 + "default")), lo),
        unit=unit_txt,
        toggled=IRI(LV2 + "toggled") in props,
        integer=IRI(LV2 + "integer") in props,
        logarithmic=IRI(PPROP + "logarithmic") in props,
        choices=choices if (enum or choices) else [],
    )


def _hidden(key, label):
    return key.rsplit(":", 1)[-1].lower() == "bypass" or str(label).lower() == "bypass"


def load_bundle(path):
    """Read every .ttl in a bundle; return the plugins it describes."""
    g = Graph()
    for name in sorted(os.listdir(path)):
        if name.endswith(".ttl"):
            fp = os.path.join(path, name)
            with open(fp, encoding="utf-8") as f:
                g.parse(f.read(), base="file://" + fp)
    plugins = []
    for uri in g.subjects(IRI(RDF + "type"), IRI(LV2 + "Plugin")):
        name = g.value(uri, IRI(DOAP + "name")) or uri.rsplit("/", 1)[-1]
        audio_in, audio_out, ports = [], [], []
        for port in g.objects(uri, IRI(LV2 + "port")):
            types = set(g.objects(port, IRI(RDF + "type")))
            sym = str(g.value(port, IRI(LV2 + "symbol"), ""))
            idx = _num(g.value(port, IRI(LV2 + "index")), 0)
            is_in = IRI(LV2 + "InputPort") in types
            if IRI(LV2 + "AudioPort") in types:
                (audio_in if is_in else audio_out).append((idx, sym))
            elif IRI(LV2 + "ControlPort") in types and is_in:
                if g.value(port, IRI(LV2 + "designation")) is not None:
                    continue  # host housekeeping: enabled, freewheel, ...
                props = set(g.objects(port, IRI(LV2 + "portProperty")))
                if IRI(PPROP + "notOnGUI") in props:
                    continue
                label = g.value(port, IRI(LV2 + "name"), sym)
                if not _hidden(sym, label):
                    ports.append((idx, _control(g, port, "port", sym, label)))
        params = []
        for p in g.objects(uri, IRI(PATCH + "writable")):
            label = g.value(p, IRI(RDFS + "label"), p.rsplit(":", 1)[-1])
            if not _hidden(p, label):
                params.append((g.first_seen.get(p, 1e9), _control(g, p, "param", str(p), label)))
        controls = [c for _, c in sorted(ports, key=lambda t: t[0])]
        controls += [c for _, c in sorted(params, key=lambda t: t[0])]
        plugins.append(Plugin(
            uri=str(uri), name=str(name), bundle=path,
            audio_in=[s for _, s in sorted(audio_in)],
            audio_out=[s for _, s in sorted(audio_out)],
            controls=controls,
        ))
    return plugins


def scan(dirs=None, match=""):
    """All plugins in the LV2 folders whose URI or name contains `match`."""
    found = {}
    for d in dirs or DEFAULT_LV2_DIRS:
        if not os.path.isdir(d):
            continue
        for entry in sorted(os.listdir(d)):
            path = os.path.join(d, entry)
            if not (entry.endswith(".lv2") and os.path.isfile(os.path.join(path, "manifest.ttl"))):
                continue
            try:
                for p in load_bundle(path):
                    if match.lower() in (p.uri + " " + p.name).lower():
                        found.setdefault(p.uri, p)
            except Exception as e:  # a broken bundle must not stop the pedal
                print(f"  ! skipped {entry}: {e}")
    return sorted(found.values(), key=lambda p: p.name.lower())

"""Draws the Melon Pedal LCD screens (docs/lcd-gui-design.md) with Pillow.

All coordinates are real LCD pixels (320x240). Frames are drawn at 2x and
reduced, which gives anti-aliased arcs, circles and rounded corners.
"""
import math
import os

from PIL import Image, ImageDraw, ImageFont

W, H, S = 320, 240, 2

# Tokens (docs/lcd-gui-design.md §3)
GROUND, SURFACE, LINE, RIND = "#0D1610", "#172A1F", "#2E4A39", "#1E3A2B"
CREAM, SAGE, DIM, LIME, AMBER = "#F3ECD6", "#93AC9A", "#7A9582", "#A6E07A", "#FFB547"
BYPASS_RED, FLESH, IDLE, RULE = "#C8262B", "#FF7B8A", "#3E5C49", "#21392B"

FONT_DIR = os.environ.get("MELON_FONTS", os.path.join(os.path.dirname(__file__), "fonts"))
FALLBACK = {
    500: "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed.ttf",
    600: "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
    700: "/usr/share/fonts/truetype/dejavu/DejaVuSansCondensed-Bold.ttf",
}
BARLOW = {500: "BarlowSemiCondensed-Medium.ttf", 600: "BarlowSemiCondensed-SemiBold.ttf",
          700: "BarlowSemiCondensed-Bold.ttf"}
FREDOKA = "Fredoka-Variable.ttf"

_fonts = {}


def font(family, weight, px):
    """family 'fredoka' (names) or 'barlow' (numbers, labels); px = LCD pixels."""
    key = (family, weight, px)
    if key in _fonts:
        return _fonts[key]
    f = None
    try:
        if family == "fredoka":
            f = ImageFont.truetype(os.path.join(FONT_DIR, FREDOKA), px * S)
            try:
                axes = f.get_variation_axes()
                names = [a["name"].decode() if isinstance(a["name"], bytes) else str(a["name"])
                         for a in axes]
                f.set_variation_by_axes([weight if "eight" in n else a["default"]
                                         for n, a in zip(names, axes)])
            except Exception:
                pass
        else:
            f = ImageFont.truetype(os.path.join(FONT_DIR, BARLOW[weight]), px * S)
    except OSError:
        f = ImageFont.truetype(FALLBACK[weight], int(px * S * (0.86 if family == "barlow" else 0.9)))
    _fonts[key] = f
    return f


class Canvas:
    """Pillow drawing in 1x LCD coordinates on a 2x image."""

    def __init__(self, bg=GROUND, size=(W, H)):
        self.im = Image.new("RGB", (size[0] * S, size[1] * S), bg)
        self.d = ImageDraw.Draw(self.im)

    def rect(self, x, y, w, h, fill=None, r=0, outline=None, width=1):
        box = [x * S, y * S, (x + w) * S - 1, (y + h) * S - 1]
        self.d.rounded_rectangle(box, radius=r * S, fill=fill, outline=outline,
                                 width=int(width * S))

    def circle(self, cx, cy, r, fill=None, outline=None, width=1):
        self.d.ellipse([(cx - r) * S, (cy - r) * S, (cx + r) * S, (cy + r) * S],
                       fill=fill, outline=outline, width=int(width * S))

    def arc(self, cx, cy, r, start, end, color, width):
        """Ring arc with round caps; r = centreline radius; angles clockwise from 3 o'clock."""
        if end - start < 0.5:
            return
        o = r + width / 2
        self.d.arc([(cx - o) * S, (cy - o) * S, (cx + o) * S, (cy + o) * S],
                   start, end, fill=color, width=int(width * S))
        for a in (start, end):
            t = math.radians(a)
            self.circle(cx + r * math.cos(t), cy + r * math.sin(t), width / 2, fill=color)

    def text(self, x, y, s, f, fill, anchor="ls", spacing=0):
        if not spacing:
            self.d.text((x * S, y * S), s, font=f, fill=fill, anchor=anchor)
            return
        w = self.textw(s, f, spacing)
        if anchor[0] == "m":
            x -= w / 2
        elif anchor[0] == "r":
            x -= w
        for ch in s:
            self.d.text((x * S, y * S), ch, font=f, fill=fill, anchor="l" + anchor[1])
            x += self.d.textlength(ch, font=f) / S + spacing

    def textw(self, s, f, spacing=0):
        return self.d.textlength(s, font=f) / S + spacing * max(0, len(s) - 1)

    def center(self, cx, cy, s, f, fill):
        """Centre text on (cx, cy) by its cap height (looks right for digits and capitals)."""
        top = self.d.textbbox((0, 0), "H", font=f, anchor="ls")[1] / S
        self.text(cx, cy - top / 2, s, f, fill, anchor="ms")

    def fit(self, s, f, maxw):
        if self.textw(s, f) <= maxw:
            return s
        while s and self.textw(s + "…", f) > maxw:
            s = s[:-1]
        return s.rstrip() + "…"

    def image(self):
        return self.im.reduce(S)


# ---------------------------------------------------------------- values

def frac(p):
    lo, hi, v = float(p.get("min", 0)), float(p.get("max", 1)), float(p.get("value", 0))
    if hi == lo:
        return 0.0
    if p.get("log") and lo > 0 and v > 0:
        f = math.log(v / lo) / math.log(hi / lo)
    else:
        f = (v - lo) / (hi - lo)
    return max(0.0, min(1.0, f))


def num(v, decimals, plus=False):
    s = f"{abs(v):.{decimals}f}"
    if v < 0 and float(s) != 0:
        return "−" + s
    if plus and v > 0:
        return "+" + s
    return s


def decimals_for(p, span):
    if "decimals" in p:
        return p["decimals"]
    if p.get("kind") == "int":
        return 0
    return 0 if span >= 100 else 1 if span >= 10 else 2


def fmt(p, fine=False):
    """-> (value text, unit text)"""
    if p.get("text") is not None:
        return str(p["text"]), p.get("unit", "")
    kind, v = p.get("kind", "float"), float(p.get("value", 0))
    if kind == "enum":
        opts = p.get("options") or ["?"]
        i = max(0, min(len(opts) - 1, int(round(v))))
        return str(opts[i]), f"{i + 1}/{len(opts)}"
    if kind == "toggle":
        return ("On" if v >= 0.5 else "Off"), ""
    unit = p.get("unit", "")
    lo, hi = float(p.get("min", 0)), float(p.get("max", 1))
    plus = lo < 0 < hi
    if unit == "Hz" and abs(v) >= 1000:
        return num(v / 1000, 2 if abs(v) < 10000 and fine else 1, plus), "kHz"
    d = decimals_for(p, hi - lo) + (1 if fine else 0)
    return num(v, d, plus), unit


def fmt_bound(p, v):
    q = dict(p, value=v, text=None)
    t, u = fmt(q)
    return f"{t} {u}".strip() if u in ("kHz", "Hz") else t


# ---------------------------------------------------------------- pieces

def header(c, st):
    c.rect(0, 20, W, 1, fill=RULE)
    f = font("barlow", 600, 12)
    c.text(8, 14.5, st.get("bank", ""), f, SAGE, spacing=0.5)
    pages, page = int(st.get("pages", 1) or 1), int(st.get("page", 1) or 1)
    if pages > 1:
        x = W / 2 - (pages * 6 + (pages - 1) * 4) / 2
        for i in range(pages):
            c.circle(x + 3 + i * 10, 10.5, 3, fill=CREAM if i + 1 == page else IDLE)
    x = W - 8
    if st.get("cpu") is not None:
        s = f"CPU {int(round(st['cpu']))}%"
        c.text(x, 14.5, s, f, AMBER if st["cpu"] >= 80 else SAGE, anchor="rs")
        x -= c.textw(s, f) + 8
    if st.get("midi") is not None:
        c.text(x, 14.5, "MIDI", f, SAGE, anchor="rs")
        x -= c.textw("MIDI", f) + 3
        c.circle(x - 2.5, 10.5, 2.5, fill=LIME if st["midi"] else IDLE)


def preset_band(c, st, y, h, bypassed):
    pr = st.get("preset") or {}
    num_s = str(pr.get("number", ""))
    by = y + (h - 44) / 2
    c.rect(8, by, 44, 44, fill=LINE if bypassed else LIME, r=8)
    c.center(30, by + 22, num_s, font("fredoka", 600, 24), CREAM if bypassed else GROUND)
    edited = pr.get("edited") and not bypassed
    maxw = W - 60 - 8 - (52 if edited else 0)
    f = font("fredoka", 500, 26)
    c.text(60, by + 22, c.fit(pr.get("name", ""), f, maxw), f, CREAM)
    if bypassed:
        sub = st.get("bypass_note", "Dry signal · effect bypassed")
    else:
        sub = st.get("plugin", "")
        if int(st.get("pages", 1) or 1) > 1:
            sub += f" · page {st.get('page', 1)}/{st.get('pages')}"
    fs = font("barlow", 500, 13)
    c.text(60, by + 40, c.fit(sub, fs, W - 68), fs, SAGE)
    if edited:
        fe = font("barlow", 700, 11)
        w = c.textw("EDITED", fe) + 8
        c.rect(W - 8 - w, by + 2, w, 15, fill=AMBER, r=4)
        c.text(W - 8 - w / 2, by + 13.5, "EDITED", fe, GROUND, anchor="ms")


def knob_ring(c, cx, cy, p, n, color):
    c.arc(cx, cy, 16, 135, 405, LINE, 4)
    if p is not None:
        if p.get("kind") == "enum" and p.get("options"):
            k = len(p["options"])
            i = max(0, min(k - 1, int(round(float(p.get("value", 0))))))
            for j in range(k):
                a = math.radians(135 + (270 * j / (k - 1) if k > 1 else 135))
                c.circle(cx + 16 * math.cos(a), cy + 16 * math.sin(a),
                         3.5 if j == i else 3, fill=color if j == i else IDLE)
        else:
            c.arc(cx, cy, 16, 135, 135 + 270 * frac(p), color, 4)
    c.center(cx, cy, str(n), font("barlow", 700, 13), SAGE)


def tile(c, x, y, w, h, p, n, color=LIME):
    c.rect(x, y, w, h, fill=SURFACE, r=8)
    knob_ring(c, x + 28, y + h / 2, p, n, color)
    if p is None:
        return
    fl, fv, fu = font("barlow", 600, 12), font("barlow", 600, 24), font("barlow", 500, 13)
    tx, maxw = x + 56, w - 56 - 6
    c.text(tx, y + h / 2 - 9, c.fit(str(p.get("label", "")).upper(), fl, maxw), fl, SAGE, spacing=0.6)
    if p.get("kind") == "file":                    # file name: smaller, up to two lines
        ff = font("barlow", 600, 15)
        lines = wrap(c, str(p.get("text") or "None"), ff, maxw, 2)
        for j, line in enumerate(lines):
            c.text(tx, y + h / 2 + 9 + j * 17, line, ff, CREAM)
        return
    val, unit = fmt(p)
    val = c.fit(val, fv, maxw - (c.textw(unit, fu) + 2 if unit else 0))
    c.text(tx, y + h / 2 + 15, val, fv, CREAM)
    if unit:
        c.text(tx + c.textw(val, fv) + 2, y + h / 2 + 15, unit, fu, SAGE)


def wrap(c, text, f, maxw, max_lines):
    """Split text into lines that fit maxw; the last line gets "…" if text is left over."""
    words, lines, cur = text.split(), [], ""
    for i, wd in enumerate(words):
        test = f"{cur} {wd}".strip()
        if c.textw(test, f) <= maxw or not cur:
            cur = test
            continue
        lines.append(cur)
        cur = wd
        if len(lines) == max_lines - 1:
            cur = " ".join(words[i:])
            break
    lines.append(cur)
    return [c.fit(line, f, maxw) for line in lines[:max_lines]]


def tiles_grid(c, params, top, bottom, tile_fn=tile):
    gw = (W - 12 - 6) / 2
    gh = (bottom - top - 6) / 2
    for i in range(4):
        p = params[i] if i < len(params) else None
        tile_fn(c, 6 + (i % 2) * (gw + 6), top + (i // 2) * (gh + 6), gw, gh, p, i + 1)


def compact_tile(c, x, y, w, h, p, n, color=LIME):
    c.rect(x, y, w, h, fill=SURFACE, r=6)
    c.circle(x + 17, y + h / 2, 8, outline=LINE, width=2)
    c.center(x + 17, y + h / 2, str(n), font("barlow", 700, 11), SAGE)
    if p is None:
        return
    fl, fv, fu = font("barlow", 600, 12), font("barlow", 600, 20), font("barlow", 500, 11)
    val, unit = fmt(p)
    vw = c.textw(val, fv) + (c.textw(unit, fu) + 1 if unit else 0)
    c.text(x + w - 8 - vw, y + h / 2 + 7, val, fv, CREAM)
    if unit:
        c.text(x + w - 8 - c.textw(unit, fu), y + h / 2 + 7, unit, fu, SAGE)
    bx, bw = x + 31, w - 31 - vw - 16
    c.text(bx, y + h / 2 - 3, c.fit(str(p.get("label", "")), fl, bw), fl, SAGE)
    by = y + h / 2 + 3
    c.rect(bx, by, bw, 4, fill=LINE, r=2)
    lo, hi = float(p.get("min", 0)), float(p.get("max", 1))
    f = frac(p)
    if lo < 0 < hi:
        z = (0 - lo) / (hi - lo)
        a, b = sorted((z, f))
        if b - a > 0.005:
            c.rect(bx + bw * a, by, bw * (b - a), 4, fill=color, r=2)
        c.rect(bx + bw * z - 0.5, by - 2, 1, 8, fill=SAGE)
    elif f > 0.005:
        c.rect(bx, by, bw * f, 4, fill=color, r=2)


def eq_graph(c, g, y, h=78):
    vals = g.get("values") or []
    n = len(vals)
    if not n:
        return
    lo, hi = float(g.get("min", -12)), float(g.get("max", 12))
    gap = 3 if n > 16 else 4
    bw = (W - 12 - (n - 1) * gap) / n
    mid = y + h / 2
    zero = (0 - lo) / (hi - lo) if lo < 0 < hi else 0
    base = y + h * (1 - zero)
    hl = g.get("highlight") or []
    if len(hl) == 2:
        x0 = 6 + hl[0] * (bw + gap) - 2
        c.rect(x0, y, (hl[1] - hl[0] + 1) * (bw + gap) - gap + 4, h, fill="#1F3A2A", r=4)
    c.rect(6, base, W - 12, 1, fill=LINE)
    for i, v in enumerate(vals):
        f = max(0.0, min(1.0, (float(v) - lo) / (hi - lo)))
        top = y + h * (1 - f)
        on = len(hl) == 2 and hl[0] <= i <= hl[1]
        y0, y1 = sorted((top, base))
        if y1 - y0 < 1:
            y0, y1 = base - 0.5, base + 0.5
        c.rect(6 + i * (bw + gap), y0, bw, y1 - y0, fill=LIME if on else IDLE, r=1.5)
    fl = font("barlow", 600, 11)
    for i, label in g.get("labels", []):
        c.text(6 + i * (bw + gap), y + h + 12, str(label), fl, SAGE)


# ---------------------------------------------------------------- screens

def play(st, popup=None, fine=False):
    """Play screen; popup = index of the tile whose value pop-up is shown."""
    bypassed = bool(st.get("bypass"))
    params = st.get("params") or []
    c = Canvas()
    graph = st.get("graph")
    if bypassed:
        c.rect(0, 0, W, 26, fill=BYPASS_RED)
        c.text(W / 2, 19.5, "BYPASS", font("barlow", 700, 18), "#FFFFFF", anchor="ms", spacing=3)
        preset_band(c, st, 26, 52, True)
        top = 78
    elif graph:
        header(c, st)
        pr = st.get("preset") or {}
        ff = font("fredoka", 600, 18)
        c.text(8, 40, str(pr.get("number", "")), ff, LIME)
        nx = 8 + c.textw(str(pr.get("number", "")), ff) + 6
        sub = st.get("graph_note", st.get("plugin", ""))
        fs = font("barlow", 600, 12)
        c.text(W - 8, 40, sub, fs, SAGE, anchor="rs")
        fn = font("fredoka", 500, 18)
        c.text(nx, 40, c.fit(pr.get("name", ""), fn, W - 8 - c.textw(sub, fs) - 8 - nx), fn, CREAM)
        eq_graph(c, graph, 48)
        tiles_grid(c, params, 140, 234, compact_tile)
        top = None
    else:
        header(c, st)
        preset_band(c, st, 21, 56, False)
        top = 77
    if top is not None:
        if bypassed:
            layer = Canvas()
            tiles_grid(layer, params, top, 234, lambda *a: tile(*a, color=SAGE))
            box = (0, top * S, W * S, H * S)
            region = Image.blend(Image.new("RGB", (W * S, (H - top) * S), GROUND),
                                 layer.im.crop(box), 0.45)
            c.im.paste(region, box[:2])
        else:
            tiles_grid(c, params, top, 234)
    if popup is not None and popup < len(params) and params[popup] is not None:
        value_popup(c, params[popup], popup + 1, fine)
    return c.image()


def value_popup(c, p, n, fine):
    c.im.paste(Image.blend(c.im, Image.new("RGB", c.im.size, GROUND), 0.78))
    x, y, w, h = 10, 30, 300, 180
    c.rect(x, y, w, h, fill=SURFACE, r=12, outline=LIME, width=2)
    c.circle(x + 26, y + 22, 9, outline=LIME, width=2)
    c.center(x + 26, y + 22, str(n), font("barlow", 700, 12), LIME)
    c.text(x + 42, y + 28, str(p.get("label", "")).upper(), font("barlow", 700, 16), SAGE, spacing=1.2)
    if fine:
        fc = font("barlow", 700, 12)
        cw = c.textw("FINE ×10", fc) + 12
        c.rect(x + w - 14 - cw, y + 13, cw, 17, fill=AMBER, r=4)
        c.text(x + w - 14 - cw / 2, y + 25.5, "FINE ×10", fc, GROUND, anchor="ms")
    if p.get("kind") == "file":                    # Melon NAM / Melon Cab: a file name, not a number
        val = str(p.get("text") or "None")
        one = next((px for px in (40, 32, 26) if c.textw(val, font("barlow", 700, px)) <= w - 28), None)
        if one:
            c.text(x + w / 2, y + 108, val, font("barlow", 700, one), CREAM, anchor="ms")
        else:                                      # long name: two lines
            fv = font("barlow", 700, 24)
            for j, line in enumerate(wrap(c, val, fv, w - 28, 2)):
                c.text(x + w / 2, y + 92 + j * 30, line, fv, CREAM, anchor="ms")
        lo, hi, v = float(p.get("min", -1)), float(p.get("max", 0)), float(p.get("value", -1))
        if v >= 0:
            c.text(x + w / 2, y + 150, f"{int(v) + 1} of {int(hi) + 1}", font("barlow", 600, 14), SAGE, anchor="ms")
        return
    val, unit = fmt(p, fine)
    fv, fu = font("barlow", 700, 68), font("barlow", 600, 26)
    total = c.textw(val, fv) + (c.textw(unit, fu) + 4 if unit else 0)
    if total > w - 28:
        fv = font("barlow", 700, 48)
        total = c.textw(val, fv) + (c.textw(unit, fu) + 4 if unit else 0)
    vx = x + (w - total) / 2
    c.text(vx, y + 112, val, fv, CREAM)
    if unit:
        c.text(vx + c.textw(val, fv) + 4, y + 112, unit, fu, SAGE)
    bx, bw, by = x + 14, w - 28, y + 132
    fl = font("barlow", 600, 12)
    kind = p.get("kind", "float")
    if kind in ("enum", "toggle"):
        opts = p.get("options") if kind == "enum" else ["Off", "On"]
        if opts:
            k = len(opts)
            i = max(0, min(k - 1, int(round(float(p.get("value", 0))))))
            sw = (bw - (k - 1) * 4) / k
            for j, o in enumerate(opts):
                c.rect(bx + j * (sw + 4), by, sw, 22, fill=LIME if j == i else LINE, r=5)
                c.text(bx + j * (sw + 4) + sw / 2, by + 15.5, c.fit(str(o), fl, sw - 4), fl,
                       GROUND if j == i else SAGE, anchor="ms")
        return
    lo, hi = float(p.get("min", 0)), float(p.get("max", 1))
    if not fine:
        c.rect(bx, by, bw, 10, fill=LINE, r=5)
        f = frac(p)
        if f > 0.01:
            c.rect(bx, by, max(10, bw * f), 10, fill=LIME, r=5)
        if p.get("default") is not None:
            df = frac(dict(p, value=p["default"]))
            c.rect(bx + bw * df - 1, by - 4, 2, 18, fill=CREAM)
            c.text(x + w / 2, by + 30, "default " + fmt_bound(p, float(p["default"])), fl, SAGE, anchor="ms")
        c.text(bx, by + 30, fmt_bound(p, lo), fl, SAGE)
        c.text(bx + bw, by + 30, fmt_bound(p, hi), fl, SAGE, anchor="rs")
    else:
        v = float(p.get("value", 0))
        win = (hi - lo) / 25
        a = max(lo, min(hi - win, v - win / 2))
        for t in range(21):
            th = 14 if t % 5 == 0 else 7
            c.rect(bx + bw * t / 20 - 0.5, by + 18 - th, 1, th, fill="#5E7D69")
        mx = bx + bw * (v - a) / win
        c.rect(mx - 1.5, by, 3, 18, fill=AMBER, r=1.5)
        c.text(bx, by + 32, fmt_bound(p, a), fl, SAGE)
        c.text(bx + bw, by + 32, fmt_bound(p, a + win), fl, SAGE, anchor="rs")


def boot(st):
    c = Canvas(bg=RIND)
    # melon slice logo + wordmark
    fw = font("fredoka", 600, 46)
    lx, ly = (W - (60 + c.textw("melon", fw))) / 2, 24
    c.d.chord([(lx) * S, (ly - 26) * S, (lx + 52) * S, (ly + 26) * S], 0, 180, fill=LIME)
    c.d.chord([(lx + 4) * S, (ly - 22) * S, (lx + 48) * S, (ly + 22) * S], 0, 180, fill=FLESH)
    for sx, sy in ((lx + 17, ly + 8), (lx + 26, ly + 13), (lx + 35, ly + 8)):
        c.d.ellipse([(sx - 1.4) * S, (sy - 2.1) * S, (sx + 1.4) * S, (sy + 2.1) * S], fill=RIND)
    c.text(lx + 60, 58, "melon", fw, CREAM)
    c.text(W / 2, 80, "EFFECTS PEDAL", font("barlow", 600, 13), "#B9CDBE", anchor="ms", spacing=4)
    f = font("barlow", 600, 14)
    y = 112
    for label, status in (st.get("boot") or {}).get("steps", []):
        col = "#B9CDBE" if status == "pending" else CREAM
        c.text(50, y, label, f, col)
        mark, mc = {"ok": ("✓", LIME), "wait": ("…", CREAM), "fail": ("✗", AMBER)}.get(status, ("·", "#B9CDBE"))
        c.text(270, y, mark, f, mc, anchor="rs")
        y += 20
    note = (st.get("boot") or {}).get("note", "Dry signal passes while the pedal starts")
    c.text(W / 2, 228, note, font("barlow", 600, 12), "#B9CDBE", anchor="ms")
    return c.image()


def test_pattern(rotation, invert, bgr):
    """Colour bars + orientation arrow, for setting --rotation / --invert / --bgr."""
    c = Canvas()
    bars = (("#FF0000", "RED"), ("#00FF00", "GREEN"), ("#0000FF", "BLUE"), ("#FFFFFF", "WHITE"))
    bw = W / 4
    for i, (col, name) in enumerate(bars):
        c.rect(i * bw, 120, bw, 120, fill=col)
        c.text(i * bw + bw / 2, 230, name, font("barlow", 700, 14), "#000000" if name in ("GREEN", "WHITE") else "#FFFFFF", anchor="ms")
    c.d.polygon([(W / 2 * S, 8 * S), ((W / 2 - 18) * S, 34 * S), ((W / 2 + 18) * S, 34 * S)], fill=LIME)
    c.text(W / 2, 54, "TOP (back edge)", font("barlow", 700, 16), CREAM, anchor="ms")
    c.text(W / 2, 80, f"rotation {rotation} · invert {'on' if invert else 'off'} · bgr {'on' if bgr else 'off'}",
           font("barlow", 600, 13), SAGE, anchor="ms")
    c.text(W / 2, 102, "Background should be near-black green", font("barlow", 600, 13), SAGE, anchor="ms")
    return c.image()


# ---------------------------------------------------------------- lists and save

def top_bar(c, title, right=""):
    c.rect(0, 24, W, 1, fill=RULE)
    c.text(8, 17.5, title, font("fredoka", 600, 16), CREAM)
    if right:
        c.text(W - 8, 17, right, font("barlow", 700, 13), SAGE, anchor="rs")


def footer(c, hints):
    """hints: [[knob number, text, accent?], ...] -> spread left / centre / right."""
    c.rect(0, 218, W, 1, fill=RULE)
    f, fb = font("barlow", 600, 12), font("barlow", 700, 10)
    n = len(hints)
    for i, h in enumerate(hints):
        num, text = str(h[0]), str(h[1])
        col = LIME if len(h) > 2 and h[2] else SAGE
        w = 14 + 4 + c.textw(text, f)
        x = 8 if i == 0 else W - 8 - w if i == n - 1 else (W - w) / 2
        c.circle(x + 7, 229, 6.25, outline=col, width=1.5)
        c.center(x + 7, 229, num, fb, col)
        c.text(x + 18, 233.5, text, f, SAGE)


def list_screen(st):
    L = st.get("list") or {}
    rows, sel = L.get("rows") or [], int(L.get("selected", 0))
    c = Canvas()
    top_bar(c, L.get("title", ""), L.get("right", ""))
    vis = 6
    start = max(0, min(sel - 2, len(rows) - vis))
    fn, fname, fm = font("barlow", 700, 15), font("fredoka", 500, 17), font("barlow", 600, 12)
    x, rw = 6, W - 6 - 13
    for i, r in enumerate(rows[start:start + vis]):
        y = 28 + i * 31
        on = start + i == sel
        if on:
            c.rect(x, y, rw, 29, fill=LIME, r=6)
        fg = GROUND if on else CREAM
        sub = "#24412F" if on else SAGE
        c.text(x + 8, y + 20, str(r.get("n", "")), fn, sub)
        meta = str(r.get("meta", ""))
        mark = str(r.get("mark", ""))
        right = x + rw - (20 if mark else 8)
        mw = c.textw(meta, fm)
        if meta:
            c.text(right, y + 19.5, meta, fm, sub, anchor="rs")
        name = c.fit(str(r.get("name", "")), fname, right - mw - 10 - (x + 36))
        c.text(x + 36, y + 20.5, name, fname, (sub if on else DIM) if r.get("empty") else fg)
        if mark:
            c.text(x + rw - 8, y + 19.5, mark, fm, GROUND if on else LIME, anchor="rs")
    if len(rows) > vis:
        c.rect(W - 9, 28, 3, 184, fill=RULE, r=1.5)
        th = 184 * vis / len(rows)
        c.rect(W - 9, 28 + (184 - th) * start / (len(rows) - vis), 3, th, fill="#5E7D69", r=1.5)
    footer(c, L.get("hints", []))
    return c.image()


def hint_tile(c, x, y, w, h, num, label, value, accent=False):
    bg, fg = (LIME, GROUND) if accent else (SURFACE, CREAM)
    c.rect(x, y, w, h, fill=bg, r=8)
    c.circle(x + 17, y + h / 2, 8, outline=GROUND if accent else LINE, width=2)
    c.center(x + 17, y + h / 2, str(num), font("barlow", 700, 11), fg)
    fl, fv = font("barlow", 600, 12), font("barlow", 700, 17)
    c.text(x + 32, y + h / 2 - 4, c.fit(label, fl, w - 38), fl, "#24412F" if accent else SAGE)
    c.text(x + 32, y + h / 2 + 14, c.fit(value, fv, w - 38), fv, fg)


def save_screen(st):
    sv = st.get("save") or {}
    name, cur = str(sv.get("name", "")), int(sv.get("cursor", 0))
    c = Canvas()
    top_bar(c, "Save preset", sv.get("plugin", ""))
    n = max(len(name), 1)
    bw, gap = 18, 1
    x0 = (W - (n * (bw + gap) - gap)) / 2
    fc = font("fredoka", 500, 22)
    for i, ch in enumerate(name):
        x = x0 + i * (bw + gap)
        on = i == cur
        if on:
            c.rect(x, 33, bw, 32, fill=LIME, r=3)
        c.rect(x, 65, bw, 2, fill=LIME if on else LINE)
        if ch != " ":
            c.text(x + bw / 2, 58, ch, fc, GROUND if on else CREAM, anchor="ms")
    wheel = sv.get("wheel") or []
    if wheel:
        mid = len(wheel) // 2
        fs, fb = font("barlow", 600, 16), font("barlow", 700, 21)
        for i, ch in enumerate(wheel):
            ch = "␣" if ch == " " else ch
            on = i == mid
            c.text(W / 2 + (i - mid) * 22, 93, ch, fb if on else fs, LIME if on else DIM, anchor="ms")
    tiles = sv.get("tiles") or []
    gw, gh = (W - 18) / 2, (234 - 104 - 6) / 2
    for i, t in enumerate(tiles[:4]):
        hint_tile(c, 6 + (i % 2) * (gw + 6), 104 + (i // 2) * (gh + 6), gw, gh, i + 1,
                  t.get("label", ""), t.get("value", ""), t.get("accent", False))
    return c.image()


# ---------------------------------------------------------------- tuner (Melon Tuner, page 1)

TUNER_CX, TUNER_CY, TUNER_R = 160, 214, 132      # needle pivot and scale radius
DEG_PER_CENT = 0.9                                # +-50 cents = +-45 degrees


def _tuner_point(cents, r):
    a = math.radians(-90 + max(-50.0, min(50.0, cents)) * DEG_PER_CENT)
    return TUNER_CX + r * math.cos(a), TUNER_CY + r * math.sin(a)


def tuner(st, idle=None):
    """Tuner screen. st["tuner"] = {tuning, strings, reference, mute, reading};
    reading = {note, acc, octave, cents, hz, string, hint, in_tune} or None.
    idle = seconds since the last note (the last reading stays, dimmed, for 1.5 s)."""
    t = st.get("tuner") or {}
    r = t.get("reading") or t.get("last")
    fading = t.get("reading") is None and r is not None and idle is not None and idle < 1.5
    if t.get("reading") is None and not fading:
        r = None
    bypassed, muted = bool(st.get("bypass")), bool(t.get("mute"))
    c = Canvas()

    # top: BYPASS bar, or the normal header
    if bypassed:
        c.rect(0, 0, W, 22, fill=BYPASS_RED)
        c.text(W / 2, 16.5, "BYPASS · SIGNAL PASSES", font("barlow", 700, 14), "#FFFFFF", anchor="ms", spacing=1.5)
    else:
        header(c, st)

    # output state chip + tuning / reference
    fchip = font("barlow", 700, 12)
    if not bypassed:
        label, bg, fg = ("MUTED", AMBER, GROUND) if muted else ("LIVE", None, LIME)
        w = c.textw(label, fchip, 1) + 14
        c.rect(8, 27, w, 18, fill=bg, r=5, outline=None if bg else LIME, width=1.5)
        c.text(8 + w / 2, 40.5, label, fchip, fg, anchor="ms", spacing=1)
    fr = font("barlow", 600, 13)
    ref = float(t.get("reference", 440) or 440)
    right = f"{t.get('tuning', 'Chromatic')} · A4 {ref:g} Hz"
    c.text(W - 8, 40.5, c.fit(right, fr, W - 90), fr, SAGE, anchor="rs")

    # strings of the tuning
    strings = t.get("strings") or []
    if strings:
        fs = font("barlow", 700, 13)
        bw, gap = 30, 4
        x0 = (W - (len(strings) * (bw + gap) - gap)) / 2
        cur = r.get("string") if r else None
        for i, name in enumerate(strings):
            x = x0 + i * (bw + gap)
            on = cur == i and not fading
            col = (LIME if r.get("in_tune") else AMBER) if on else None
            c.rect(x, 51, bw, 17, fill=col or SURFACE, r=4)
            c.text(x + bw / 2, 64, name, fs, GROUND if on else SAGE, anchor="ms")

    # scale: arc, ticks every 10 cents, labels
    cx, cy, R = TUNER_CX, TUNER_CY, TUNER_R
    c.arc(cx, cy, R, -90 - 50 * DEG_PER_CENT, -90 + 50 * DEG_PER_CENT, LINE, 3)
    fl = font("barlow", 600, 11)
    for cents in range(-50, 51, 10):
        major = cents in (-50, 0, 50)
        x1, y1 = _tuner_point(cents, R - (12 if major else 7))
        x2, y2 = _tuner_point(cents, R)
        col = LIME if cents == 0 else (SAGE if major else IDLE)
        c.d.line([(x1 * S, y1 * S), (x2 * S, y2 * S)], fill=col, width=int((3 if major else 2) * S))
    for cents, txt in ((-50, "−50"), (50, "+50")):
        x, y = _tuner_point(cents, R + 12)
        c.text(x, y + 4, txt, fl, DIM, anchor="ms")
    # in-tune window (+-2 cents)
    c.arc(cx, cy, R, -90 - 2 * DEG_PER_CENT, -90 + 2 * DEG_PER_CENT, LIME if r and r.get("in_tune") and not fading else IDLE, 5)

    # flat / sharp lights either side of the note (both lime when in tune)
    def light(x, d, on, col):
        y = 172
        pts = [(x - 7 * d, y - 8), (x - 7 * d, y + 8), (x + 8 * d, y)]
        c.d.polygon([(px * S, py * S) for px, py in pts], fill=col if on else IDLE)
    live = r is not None and not fading
    cents = float(r.get("cents", 0)) if r else 0.0
    in_tune = live and r.get("in_tune")
    light(82, -1, live and (in_tune or cents < 0), LIME if in_tune else AMBER)
    light(238, 1, live and (in_tune or cents > 0), LIME if in_tune else AMBER)

    # needle
    if r is not None:
        col = (LIME if in_tune else AMBER) if live else IDLE
        x1, y1 = _tuner_point(cents, 96)
        x2, y2 = _tuner_point(cents, R + 6)
        c.d.line([(x1 * S, y1 * S), (x2 * S, y2 * S)], fill=col, width=int(4 * S))
        c.circle(x2, y2, 2, fill=col)

    # note name, accidental, octave
    if r is not None:
        col = CREAM if live else IDLE
        fn, fa, fo = font("fredoka", 600, 58), font("fredoka", 600, 24), font("barlow", 700, 16)
        note, acc, octave = str(r.get("note", "")), str(r.get("acc", "")), str(r.get("octave", ""))
        nw = c.textw(note, fn)
        aw = max(c.textw(acc, fa), c.textw(octave, fo)) if (acc or octave) else 0
        x = W / 2 - (nw + 3 + aw) / 2
        c.text(x, 190, note, fn, col)
        if acc:
            c.text(x + nw + 3, 158, acc, fa, col)
        c.text(x + nw + 3, 190, octave, fo, SAGE if live else IDLE)
        fv = font("barlow", 600, 15)
        cents_txt = ("+" if cents > 0.05 else "−" if cents < -0.05 else "") + f"{abs(cents):.1f} ¢"
        c.text(10, 211, cents_txt, fv, (LIME if in_tune else AMBER) if live else IDLE)
        c.text(W - 10, 211, f"{float(r.get('hz', 0)):.1f} Hz", fv, SAGE if live else IDLE, anchor="rs")
        if r.get("hint") and live:
            c.text(W / 2, 211, r["hint"], font("barlow", 700, 14), AMBER, anchor="ms")
    else:
        c.text(W / 2, 180, "Play a note", font("fredoka", 500, 24), DIM, anchor="ms")

    footer(c, [["1", "turn: mute · push: bypass"], ["2", "push: settings"]])
    return c.image()

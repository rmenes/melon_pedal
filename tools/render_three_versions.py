"""Melon Pedal: V1 (PoC), V2 (HiFiBerry wedge), V3 (touch screen, output section, battery). To scale.

    python3 tools/render_three_versions.py   ->  docs/images/three-versions.png  (matplotlib)
"""
import math
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.patches import Polygon, Rectangle, Circle, FancyBboxPatch

DARK, CREAM, LIME, GHOST = "#0D1610", "#F3ECD6", "#A6E07A", "#93AC9A"
TOP, FRONT, SIDE = "#2C5E43", "#1E3A2B", "#16301F"
METAL, METAL_D = "#C9CFCB", "#7D8580"
CELL = "#C8562F"

TH, PH = math.radians(32), math.radians(38)
def proj(p):
    x, y, z = p
    X = x * math.cos(TH) - y * math.sin(TH)
    Y = x * math.sin(TH) + y * math.cos(TH)
    return (X, Y * math.sin(PH) + z * math.cos(PH)), Y * math.cos(PH) - z * math.sin(PH)

class Scene:
    def __init__(self):
        self.polys = []
    def add(self, pts, fc, ec="#0b140e", lw=0.6, bias=0.0, layer=1):
        pr = [proj(p) for p in pts]
        d = sum(q[1] for q in pr) / len(pr) + bias
        self.polys.append((layer, d, [q[0] for q in pr], fc, ec, lw))
    def draw(self, ax, dx=0.0, dy=0.0):
        for layer, d, pts, fc, ec, lw in sorted(self.polys, key=lambda t: (t[0], -t[1])):
            ax.add_patch(Polygon([(u + dx, v + dy) for u, v in pts], closed=True, facecolor=fc, edgecolor=ec, lw=lw))

def wedge(sc, x0, x1, y0, y1, hf, hb, top=TOP, front=FRONT, side=SIDE):
    A, B, C, D = (x0, y0, 0), (x1, y0, 0), (x1, y1, 0), (x0, y1, 0)
    E, F, G, H = (x0, y0, hf), (x1, y0, hf), (x1, y1, hb), (x0, y1, hb)
    sc.add([E, F, G, H], top, layer=0); sc.add([A, B, F, E], front, layer=0); sc.add([A, D, H, E], side, layer=0)
    sc.add([B, C, G, F], side, layer=0); sc.add([D, C, G, H], side, bias=5, layer=0)

def zt(y, y0, y1, hf, hb):
    return hf + (y - y0) * (hb - hf) / (y1 - y0)

def cylinder(sc, cx, cy, z0, r, h, color, side_color, n=28, slope=None):
    pts = [(cx + r * math.cos(2 * math.pi * i / n), cy + r * math.sin(2 * math.pi * i / n)) for i in range(n)]
    base = lambda x, y: z0 if slope is None else zt(y, *slope)
    for i in range(n):
        (xa, ya), (xb, yb) = pts[i], pts[(i + 1) % n]
        sc.add([(xa, ya, base(xa, ya)), (xb, yb, base(xb, yb)), (xb, yb, base(xb, yb) + h), (xa, ya, base(xa, ya) + h)],
               side_color, ec=side_color, lw=0.2, bias=-0.5, layer=4)
    sc.add([(x, y, base(x, y) + h) for x, y in pts], color, ec="#333", lw=0.3, bias=-1.5, layer=4)

def lid_rect(sc, x0, x1, ya, yb, slope, fc, ec=LIME, lift=0.4, bias=0.0, layer=3):
    sc.add([(x0, ya, zt(ya, *slope) + lift), (x1, ya, zt(ya, *slope) + lift),
            (x1, yb, zt(yb, *slope) + lift), (x0, yb, zt(yb, *slope) + lift)], fc, ec=ec, lw=0.9, bias=bias, layer=layer)

def knob(sc, x, y, slope):
    cylinder(sc, x, y, None, 7.0, 15, "#EDE6D0", "#B9B29E", slope=slope)

def stepped(sc, x, y, slope, r=7.6):
    """Stepped knob: wide skirt, narrower cap on top (V3)."""
    cylinder(sc, x, y, None, r, 4.0 * r / 7.6, "#2a2d2b", "#1c1e1d", slope=slope)
    sk = (slope[0], slope[1], slope[2] + 4.0 * r / 7.6, slope[3] + 4.0 * r / 7.6)
    cylinder(sc, x, y, None, 0.64 * r, 10.5 * r / 7.6, "#C9CFCB", "#2a2d2b", slope=sk)

def footswitch(sc, x, y, slope):
    cylinder(sc, x, y, None, 7.5, 5, METAL, METAL_D, slope=slope)

def led(sc, x, y, slope):
    cylinder(sc, x, y, None, 2.2, 1.5, LIME, "#5f8a45", n=14, slope=slope)

def screen(sc, cx, cy, w, h, slope, ui=True):
    lid_rect(sc, cx - w / 2 - 3, cx + w / 2 + 3, cy - h / 2 - 3, cy + h / 2 + 3, slope, "#0A120D", ec="#3a4a3f", layer=1)
    lid_rect(sc, cx - w / 2, cx + w / 2, cy - h / 2, cy + h / 2, slope, "#11241A", ec=LIME, layer=2)
    if ui:   # a few UI blocks, like the chain strip
        n = 5; bw = (w - 10) / n
        for i in range(n):
            x0 = cx - w / 2 + 5 + i * bw
            lid_rect(sc, x0 + 1, x0 + bw - 1, cy + h / 2 - 16, cy + h / 2 - 6, slope,
                     ["#d2923f", "#3fb08c", LIME, "#9a82d6", "#d07a5a"][i], ec="none", lift=0.8, bias=-1.2)
        lid_rect(sc, cx - w / 2 + 5, cx + w / 2 - 5, cy - h / 2 + 5, cy - h / 2 + 9, slope, "#2E4A39", ec="none",
                 lift=0.8, bias=-1.2)

def box(sc, x0, x1, y0, y1, z0, z1, top, front, side):
    wedge(sc, x0, x1, y0, y1, z1 - z0, z1 - z0, top, front, side) if z0 == 0 else None

# ------------------------------------------------------------------ the three pedals
def v1(sc, dx=0):
    W, L, H = 72, 120, 40
    y0, y1 = -L / 2, L / 2
    s = (y0, y1, H, H)
    wedge(sc, dx - W / 2, dx + W / 2, y0, y1, H, H)
    footswitch(sc, dx, -42, s); led(sc, dx, -27, s)
    screen(sc, dx, -2, 42, 32, s, ui=False)
    for x in (-14, 14):
        for y in (27, 47):
            knob(sc, dx + x, y, s)
    # external USB interface (Zoom AMS-22 size) behind/right, with a cable
    ax0 = dx + W / 2 + 18
    wedge(sc, ax0, ax0 + 68, 5, 63, 46, 46, top="#3a3f44", front="#2a2e32", side="#22262a")
    cylinder(sc, ax0 + 20, 25, 46, 8, 3, "#555", "#444")
    return W, L

def v2(sc, dx=0):
    W, L, hf, hb = 100, 135, 40, 65
    y0, y1 = -L / 2, L / 2
    s = (y0, y1, hf, hb)
    wedge(sc, dx - W / 2, dx + W / 2, y0, y1, hf, hb)
    footswitch(sc, dx, -48, s); led(sc, dx, -33, s)
    screen(sc, dx, -2, 57.6, 43.2, s)                      # 2.8" ILI9341, landscape
    for x, y in V2_KNOBS:
        knob(sc, dx + x, y, s)
    return W, L

V2_KNOBS = [(-24, 33), (24, 33), (-24, 55), (24, 55)]

V3 = dict(W=240, L=170, hf=45, hb=70)
def v3(sc, dx=0):
    W, L, hf, hb = V3["W"], V3["L"], V3["hf"], V3["hb"]
    y0, y1 = -L / 2, L / 2
    s = (y0, y1, hf, hb)
    wedge(sc, dx - W / 2, dx + W / 2, y0, y1, hf, hb)
    for x in (-90, -30, 30, 90):
        footswitch(sc, dx + x, -62, s); led(sc, dx + x, -46, s)
    screen(sc, dx + V3_SCREEN[0], V3_SCREEN[1], 111.5, 63, s)
    for x in V3_ENC:
        stepped(sc, dx + x, -22, s)
    for (x, y), r, _ in V3_OUT:
        stepped(sc, dx + x, y, s, r)
    return W, L

V3_SCREEN = (-40, 35)                       # window centre; Touch Display 2 5": viewing 111.5 x 63, module 143.5 x 91.5
V3_ENC = [-86.8, -55.6, -24.4, 6.8]          # encoders 1-4 under the screen, inside its width
V3_OUT = [((50, 60), 7.6, "BASS"), ((73, 60), 7.6, "MID"), ((96, 60), 7.6, "TREBLE"), ((73, 22), 9.8, "VOLUME")]

# ------------------------------------------------------------------ figure
fig = plt.figure(figsize=(17, 12.5), facecolor=DARK)
ax = fig.add_axes([0.0, 0.47, 1.0, 0.5]); ax.set_facecolor(DARK); ax.set_aspect("equal"); ax.axis("off")
sc = Scene(); v1(sc); sc.draw(ax, dx=-305)
sc = Scene(); v2(sc); sc.draw(ax, dx=-90)
sc = Scene(); v3(sc); sc.draw(ax, dx=190, dy=-22)
for x, t, sub in [(-300, "V1 · Proof of concept", "72 × 120 × 40 mm + external USB interface"),
                  (-90, "V2 · HiFiBerry wedge (new layout)", "100 × 135 mm · 40 → 65 mm · 2.8\" screen, knobs at the back"),
                  (190, "V3 · 5\" touch screen, output section, battery", "240 × 170 mm · 45 → 70 mm high (estimate)")]:
    ax.text(x, 128, t, color=CREAM, fontsize=14, fontweight="bold", ha="center")
    ax.text(x, 117, sub, color=GHOST, fontsize=10, ha="center")
ax.set_xlim(-400, 360); ax.set_ylim(-140, 140)

# ---- top views, all to the same scale
axt = fig.add_axes([0.0, 0.03, 1.0, 0.43]); axt.set_facecolor(DARK); axt.set_aspect("equal"); axt.axis("off")

def dims(cx, y0, y1, W, color=LIME):
    axt.annotate("", xy=(cx - W / 2, y1 + 12), xytext=(cx + W / 2, y1 + 12), arrowprops=dict(arrowstyle="<->", color=color))
    axt.text(cx, y1 + 17, f"{W:.0f} mm", color=color, ha="center", fontsize=10, fontweight="bold")
    axt.annotate("", xy=(cx + W / 2 + 10, y0), xytext=(cx + W / 2 + 10, y1), arrowprops=dict(arrowstyle="<->", color=color))
    axt.text(cx + W / 2 + 14, (y0 + y1) / 2, f"{y1 - y0:.0f} mm", color=color, rotation=90, va="center", fontsize=10,
             fontweight="bold")

def inner(x0, y0, w, h, label, color=GHOST, fill=None):
    axt.add_patch(Rectangle((x0, y0), w, h, fill=fill is not None, facecolor=fill or "none", edgecolor=color, ls=":",
                            lw=1, alpha=0.9))
    axt.text(x0 + w / 2, y0 + h / 2, label, color=color, fontsize=6.5, ha="center", va="center")

# V1
cx = -300
axt.add_patch(Rectangle((cx - 36, -60), 72, 120, facecolor=TOP, edgecolor=CREAM))
axt.add_patch(Circle((cx, -42), 7.5, color=METAL)); axt.add_patch(Circle((cx, -27), 2.2, color=LIME))
axt.add_patch(Rectangle((cx - 21, -18), 42, 32, facecolor="#11241A", edgecolor=LIME))
for x in (-14, 14):
    for y in (27, 47):
        axt.add_patch(Circle((cx + x, y), 7, color=CREAM))
dims(cx, -60, 60, 72)
axt.add_patch(Rectangle((cx + 55, 5), 68, 58, facecolor="#3a3f44", edgecolor="#888"))
axt.text(cx + 89, 34, "USB\ninterface\n(AMS-22)", color="#ccc", fontsize=7, ha="center", va="center")
axt.text(cx, -78, "no battery · USB-C power", color=GHOST, fontsize=8.5, ha="center")

# V2
cx = -90
axt.add_patch(Rectangle((cx - 50, -67.5), 100, 135, facecolor=TOP, edgecolor=CREAM))
axt.add_patch(Circle((cx, -48), 7.5, color=METAL)); axt.add_patch(Circle((cx, -33), 2.2, color=LIME))
axt.add_patch(Rectangle((cx - 43, -27), 86, 50, facecolor="#0A120D", edgecolor="#3a4a3f"))
axt.add_patch(Rectangle((cx - 28.8, -23.6), 57.6, 43.2, facecolor="#11241A", edgecolor=LIME))
axt.text(cx, -2, '2.8"\n320 × 240', color=LIME, fontsize=7.5, ha="center", va="center")
axt.add_patch(Rectangle((cx - 21, -18), 42, 32, fill=False, edgecolor=GHOST, ls="--", lw=0.8))
for x, y in V2_KNOBS:
    axt.add_patch(Circle((cx + x, y), 7, color=CREAM))
dims(cx, -67.5, 67.5, 100)
axt.text(cx, -85, "no battery · 9 V pedal supply", color=GHOST, fontsize=8.5, ha="center")
axt.text(cx, -95, "dashed = today's 2\" screen", color=GHOST, fontsize=8, ha="center")

# V3
cx = 190; W, L = V3["W"], V3["L"]
axt.add_patch(Rectangle((cx - W / 2, -L / 2), W, L, facecolor=TOP, edgecolor=CREAM))
sx, sy = cx + V3_SCREEN[0], V3_SCREEN[1]
axt.add_patch(Rectangle((sx - 71.75, sy - 45.75), 143.5, 91.5, fill=False, edgecolor=GHOST, ls="--", lw=0.8))
axt.add_patch(Rectangle((sx - 59, sy - 34.5), 118, 69, facecolor="#0A120D", edgecolor="#3a4a3f"))
axt.add_patch(Rectangle((sx - 55.75, sy - 31.5), 111.5, 63, facecolor="#11241A", edgecolor=LIME))
axt.text(sx, sy, "5\" touch\n1280 × 720", color=LIME, fontsize=8, ha="center", va="center")
for i, x in enumerate(V3_ENC):
    axt.add_patch(Circle((cx + x, -22), 7.6, color="#2a2d2b", ec=CREAM, lw=0.6))
    axt.add_patch(Circle((cx + x, -22), 4.9, color=METAL))
    axt.text(cx + x, -34, str(i + 1), color=CREAM, fontsize=6.5, ha="center", va="center")
for (x, y), r, lab in V3_OUT:
    axt.add_patch(Circle((cx + x, y), r, color="#2a2d2b", ec=CREAM, lw=0.6))
    axt.add_patch(Circle((cx + x, y), 0.64 * r, color=METAL))
    axt.text(cx + x, y - r - 5, lab, color=CREAM, fontsize=6, ha="center", va="center")
axt.text(cx + 73, 75, "OUTPUT", color=LIME, fontsize=6.5, ha="center", va="center", fontweight="bold")
axt.text(cx + 70, -20, "MELON", color=CREAM, fontsize=12, ha="center", va="center", fontweight="bold")
for x in (-90, -30, 30, 90):
    axt.add_patch(Circle((cx + x, -62), 7.5, color=METAL)); axt.add_patch(Circle((cx + x, -46), 2.2, color=LIME))
dims(cx, -L / 2, L / 2, W)
axt.text(cx, -L / 2 - 15, "battery: 4 × 18650 (2S2P, ~44 Wh) → about 5 h, or the 9 V supply", color="#E8A07F",
         fontsize=8.5, ha="center")
axt.text(cx, -L / 2 - 26, "inside: Pi 5 + 6 in / 8 out board · battery bay (floor hatch) · "
         "dashed = screen module under the lid", color=GHOST, fontsize=8, ha="center")

axt.set_xlim(-400, 360); axt.set_ylim(-125, 115)
fig.text(0.5, 0.012, "Same scale for all three (mm). V3 is a first estimate: Raspberry Pi Touch Display 2 (5\", 111.5 × 63 mm "
         "visible); encoders 1-4 within the screen width; output section BASS · MID · TREBLE + bigger VOLUME; stepped knobs; "
         "footswitches 60 mm apart.", color=GHOST, ha="center", fontsize=9.5)
import os
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "docs", "images", "three-versions.png")
plt.savefig(OUT, dpi=110, facecolor=DARK)
print("ok")

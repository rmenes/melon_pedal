"""Generate the 3D-printable Melon Pedal enclosure as STL files.

Variant: HIFIBERRY WEDGE (v0.2). Audio through the HiFiBerry DAC2 ADC Pro HAT on the Pi.

    python3 hardware/enclosure/hifiberry-wedge/make_enclosure.py            # STLs next to this script
    python3 hardware/enclosure/hifiberry-wedge/make_enclosure.py --preview  # + preview PNGs + clearance report

Needs numpy, scipy and matplotlib (no CAD program).

Shape: a wedge like the BOSS 200 series. 40 mm high at the front (footswitch),
65 mm at the back (jacks); the top slopes about 10.5 degrees toward the player.

Two parts:
  * melon-pedal-tray.stl  floor + four walls. The Pi 4 and the I/O board mount
                          on its floor, the jacks in its back wall.
                          Print UPRIGHT (floor on the bed), no supports.
  * melon-pedal-lid.stl   the sloped top. Encoders, LCD, footswitch and LED
                          mount on it. Print UPSIDE DOWN (top face on the bed).
The lid is held by four M3 screws into heat-set inserts in the tray's corner
bosses; the bosses are tilted so the screws go in square to the lid.

Every dimension is a parameter in the PARAMETERS section. Measure your real
parts (jacks, encoders, footswitch, LCD module) and adjust before printing.

How the mesh is built: each feature is a flat 2D shape (outline minus holes)
extruded through a thickness, so every hole is exact and the files stay small.
A part is several closed shells that overlap a little; slicers (PrusaSlicer,
Bambu Studio, OrcaSlicer, Cura) merge overlapping shells of one object.

Coordinates (mm): x = width (player's left is -x), y = length (front -y,
back/jacks +y), z = up from the underside of the floor.
"""
import argparse
import glob
import math
import os
import struct

import numpy as np
from matplotlib.path import Path as MplPath
from matplotlib.textpath import TextPath
from matplotlib.font_manager import FontProperties, findfont
from scipy.spatial import Delaunay

HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = HERE

# =========================================================== PARAMETERS
# --- outer shape -----------------------------------------------------
W, L = 100.0, 135.0          # outside width and length
H_FRONT, H_BACK = 40.0, 65.0 # outside height at the front and back edge
R_CORNER = 5.0               # vertical corner radius
WALL = 3.0                   # wall thickness
FLOOR = 3.0                  # floor thickness
LID_T = 3.0                  # lid thickness (measured square to the lid)
HW, HL = W / 2, L / 2

SLOPE = (H_BACK - H_FRONT) / L
ALPHA = math.atan(SLOPE)     # ~10.5 degrees
C, S = math.cos(ALPHA), math.sin(ALPHA)


def z_top(y):
    """Height of the lid's top surface above y."""
    return H_FRONT + (y + HL) * SLOPE


def z_under(y):
    """Height of the lid's underside (= top edge of the tray walls) above y."""
    return z_top(y) - LID_T / C


# --- lid: controls. Positions are (x, y) seen from straight above ------
# Knob order matches the LCD tiles: 1 front-left, 2 front-right, 3 back-left, 4 back-right
# v0.3 layout (2026-11-24): 2.8" screen in the middle, the four knobs in a 2 x 2 grid at the back (like the PoC)
KNOBS = [(-24.0, 33.0), (24.0, 33.0), (-24.0, 55.0), (24.0, 55.0)]
ENC_HOLE = 7.6            # EC11 M7 bushing
ENC_POCKET = 13.6         # square pocket under the lid for the EC11 body -> lid is 2 mm there
ENC_LID_T = 2.0
FOOT_XY = (0.0, -50.0)
FOOT_HOLE = 12.4          # soft-touch footswitch, 12 mm thread
LED_XY = (0.0, -35.0)
LED_HOLE = 6.2            # 3 mm LED chrome bezel (check yours: 5.0-6.5)
LCD_C = (0.0, -3.0)       # LCD window centre
LCD_VIEW = (58.0, 44.0)   # visible window (2.8" ILI9341 active area 57.6 x 43.2, landscape)
LCD_BEZEL = (62.0, 48.0)  # outer recess around the window
LCD_BEZEL_DEPTH = 1.0
LCD_POCKET = (70.0, 51.0) # pocket under the lid for the glass (panel ~69.3 x 50.2); set to your module's glass size
KNOB_NUMBER_DX = 11.5     # knob number beside the knob, on the outer side (x sign of the knob)
KNOB_NUMBER_DY = 0.0
LID_SCREWS = [(-44.0, -61.5), (44.0, -61.5), (-44.0, 59.5), (44.0, 59.5)]  # on the top surface
LID_SCREW_HOLE = 3.4
LID_SCREW_HEAD = (6.6, 1.6)   # counterbore diameter, depth (M3 button head sits flush)

# --- tray: lid screw bosses (M3 heat-set inserts) ---------------------
BOSS_D = 8.0
INSERT_HOLE = 4.0         # for M3 x 5.7 brass inserts (check your kit: 4.0-4.2)
INSERT_DEPTH = 9.0        # measured from the lid underside, along the screw
BOSS_CAP = 2.2            # solid end of the tilted boss

# --- tray back wall: jacks (x of centre, hole diameter, inner pocket diameter, label) ---
JACK_Z = 17.0             # jack centre height above the underside
JACKS = [
    (-36.0, 9.5, 18.0, "OUT"),    # 6.35 mm TRS, M9 thread (check: some are 11 mm)
    (-16.0, 11.0, 15.0, "9V"),    # DC-022B 5.5 x 2.1 (check: 8-11 mm)
    (1.0, 6.2, 10.0, "OUT"),      # PJ-392 3.5 mm TRS, M6 thread -> MIDI OUT
    (16.0, 6.2, 10.0, "IN"),      # PJ-392 3.5 mm TRS -> MIDI IN
    (36.0, 9.5, 18.0, "IN"),      # 6.35 mm TRS
]
JACK_WALL_T = 2.0         # wall thickness inside the jack pockets (nut thread length)
LABEL_Z = 29.0            # jack label centre height
MIDI_LABEL = ("MIDI", 8.5, 35.0)  # text, x, z: one word over both MIDI jacks
LABEL_CAP = 3.6           # label capital height
ENGRAVE = 0.6             # engraving depth

# --- Pi 4 (rotated: 85 mm side across the width, GPIO header to the back,
#     USB/Ethernet end to the right wall) ------------------------------
PI_X0 = -41.5             # left board edge; ports end ~1 mm inside the right wall
PI_Y0 = -26.0             # front board edge (GPIO edge is at PI_Y0 + 56)
PI_STANDOFF = 6.0         # Pi board underside above the floor
PI_HOLES = [(3.5, 3.5), (61.5, 3.5), (3.5, 52.5), (61.5, 52.5)]
PI_PILOT = 2.2            # M2.5 screw self-taps into PETG/ASA
STANDOFF_D = 6.0
USB_CUT_Y = (PI_Y0 + 0.5, PI_Y0 + 35.5)   # both USB stacks (USB 2 centre 9, USB 3 centre 27)
USB_CUT_Z = (FLOOR + PI_STANDOFF - 1.0, FLOOR + PI_STANDOFF + 1.4 + 16.0 + 2.0)
USB_CUT_R = 2.0

# --- I/O board standoffs ---------------------------------------------
IO_BOARD = dict(x=(-39.0, 39.0), y=(35.0, 61.5), hole_inset=3.5, standoff=5.0, pilot=2.5)

# --- vents (vertical slots print without supports) --------------------
VENT_YS = [-20.0 + 5.0 * i for i in range(9)]   # left wall
VENT_Z = (14.0, 36.0)
VENT_W = 2.6
FLOOR_VENTS_X = [-30.0 + 5.0 * i for i in range(9)]
FLOOR_VENT_Y = (PI_Y0 + 10.0, PI_Y0 + 46.0)

SEG = 0.45                # max segment length for circles/arcs
EPS = 0.2                 # overlap between shells of the same part
TOPFLAG = 500.0           # sketch height that means "up to the lid underside"

# --- approximate envelopes of the parts inside, for the clearance check ---
# floor parts: axis-aligned boxes (x0, x1, y0, y1, z0, z1)
_PZ = FLOOR + PI_STANDOFF
FLOOR_PARTS = {
    "Pi 4 board": (PI_X0, PI_X0 + 85, PI_Y0, PI_Y0 + 56, _PZ, _PZ + 1.4),
    "Pi USB + Ethernet": (PI_X0 + 65, PI_X0 + 87.5, PI_Y0 + 1.5, PI_Y0 + 54, _PZ + 1.4, _PZ + 1.4 + 16),
    "HiFiBerry (board + parts)": (PI_X0, PI_X0 + 65, PI_Y0, PI_Y0 + 56, _PZ + 1.4 + 11.5, _PZ + 1.4 + 11.5 + 1.6 + 3.0),
    "HiFiBerry RCA/3.5 jacks (position to verify)": (PI_X0 + 48, PI_X0 + 65, PI_Y0 + 2, PI_Y0 + 54, _PZ + 14.5, _PZ + 14.5 + 11),
    "6.35 jacks (bodies)": (-43.0, 43.0, 40.0, HL - WALL, JACK_Z - 7, JACK_Z + 7),
    "I/O board": (-39.0, 39.0, 35.0, 61.5, FLOOR + 5.0, FLOOR + 6.6),
}
# lid parts: (x, y) centre on the top surface, size along x, size along the slope, depth below the underside
LID_PARTS = {
    "encoder 1": (*KNOBS[0], 13.6, 13.6, 13.0),
    "encoder 2": (*KNOBS[1], 13.6, 13.6, 13.0),
    "encoder 3": (*KNOBS[2], 13.6, 13.6, 13.0),
    "encoder 4": (*KNOBS[3], 13.6, 13.6, 13.0),
    "LCD module": (*LCD_C, 86.0, 50.0, 8.7),     # 2.8" ILI9341 board 86 x 50 x 8.7
    "footswitch": (*FOOT_XY, 14.0, 14.0, 25.0),
    "LED": (*LED_XY, 6.0, 6.0, 8.0),
}


# ======================================================= 2D geometry
def circle(cx, cy, d):
    r = d / 2
    n = max(24, min(180, int(math.ceil(2 * math.pi * r / SEG))))
    t = np.linspace(0, 2 * math.pi, n, endpoint=False)
    return np.c_[cx + r * np.cos(t), cy + r * np.sin(t)]


def rrect(cx, cy, w, h, r):
    r = min(r, w / 2 - 1e-6, h / 2 - 1e-6)
    pts = []
    n = max(4, int(math.ceil(0.5 * math.pi * r / SEG)))
    for (sx, sy, a0) in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        ccx, ccy = cx + sx * (w / 2 - r), cy + sy * (h / 2 - r)
        for i in range(n + 1):
            a = math.radians(a0 + 90.0 * i / n)
            pts.append((ccx + r * math.cos(a), ccy + r * math.sin(a)))
    return np.array(pts)


def rect(x0, y0, x1, y1):
    return np.array([(x0, y0), (x1, y0), (x1, y1), (x0, y1)], float)


def arc_band(cx, cy, r_in, r_out, a0, a1):
    """Annular sector (degrees a0..a1)."""
    n = max(6, int(math.ceil(math.radians(a1 - a0) * r_out / SEG)))
    t = np.radians(np.linspace(a0, a1, n + 1))
    outer = np.c_[cx + r_out * np.cos(t), cy + r_out * np.sin(t)]
    inner = np.c_[cx + r_in * np.cos(t[::-1]), cy + r_in * np.sin(t[::-1])]
    return np.vstack([outer, inner])


# ------------------------------------------------------------- text
FONT_DIRS = [os.path.join(HERE, "..", "..", "..", "tools", "fonts"),
             os.path.join(HERE, "..", "..", "..", "..", "melon_plugins", "branding", "fonts")]  # E:\melon_plugins next to E:\melon_pedal


def find_font():
    """Brand font (Fredoka) if found in FONT_DIRS, else matplotlib's DejaVu Sans Bold."""
    for pat in ("Fredoka-SemiBold*.ttf", "Fredoka-Bold*.ttf", "Fredoka*.ttf"):
        for d in FONT_DIRS:
            hits = sorted(glob.glob(os.path.join(d, "**", pat), recursive=True))
            if hits:
                return FontProperties(fname=hits[0], weight="semibold")
    return FontProperties(fname=findfont(FontProperties(family="DejaVu Sans", weight="bold")))


FONT = find_font()


def text_rings(s, cx, cy, cap):
    """Glyph outlines of s, centred at (cx, cy), capital height cap (mm)."""
    tp = TextPath((0, 0), s, size=cap / 0.73, prop=FONT)
    rings = []
    for poly in tp.to_polygons(closed_only=True):
        poly = np.asarray(poly, float)
        if len(poly) > 1 and np.allclose(poly[0], poly[-1]):
            poly = poly[:-1]
        keep = np.r_[True, np.linalg.norm(np.diff(poly, axis=0), axis=1) > 1e-3]
        poly = poly[keep]
        if len(poly) >= 3 and abs(signed_area(poly)) > 1e-4:
            rings.append(poly)
    allp = np.vstack(rings)
    ox = (allp[:, 0].min() + allp[:, 0].max()) / 2
    oy = (allp[:, 1].min() + allp[:, 1].max()) / 2
    return [r - (ox, oy) + (cx, cy) for r in rings]


# ------------------------------------------------- triangulation
def signed_area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)


def _tri_area(pts, tri):
    a, b, c = pts[tri[:, 0]], pts[tri[:, 1]], pts[tri[:, 2]]
    return 0.5 * np.sum((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))


def triangulate(rings):
    """Triangulate the even-odd region of `rings` (outline first, then holes/islands).

    Conforming Delaunay: boundary segments missing from the triangulation are
    split until every one is a triangulation edge. Returns (points, tris,
    loops); loops[i] lists ring i's point indices with the region on the left.
    """
    rings = [np.asarray(r, float) for r in rings]
    for _ in range(40):
        pts = np.vstack(rings)
        dl = Delaunay(pts)
        if len(dl.coplanar):
            raise RuntimeError("duplicate points in outline")
        tri = dl.simplices
        edges = set()
        for a, b in ((0, 1), (1, 2), (2, 0)):
            edges.update(map(tuple, np.sort(tri[:, [a, b]], axis=1)))
        new_rings, missing, base = [], 0, 0
        for r in rings:
            n = len(r)
            out = []
            for i in range(n):
                out.append(r[i])
                if tuple(sorted((base + i, base + (i + 1) % n))) not in edges:
                    out.append((r[i] + r[(i + 1) % n]) / 2)
                    missing += 1
            new_rings.append(np.array(out))
            base += n
        if not missing:
            break
        rings = new_rings
    else:
        raise RuntimeError("could not recover outline edges")

    paths = [MplPath(r) for r in rings]
    cen = pts[tri].mean(axis=1)
    inside = np.zeros(len(tri), int)
    for p in paths:
        inside += p.contains_points(cen)
    tri = tri[inside % 2 == 1]
    a, b, c = pts[tri[:, 0]], pts[tri[:, 1]], pts[tri[:, 2]]
    cross = (b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0])
    tri[cross < 0] = tri[cross < 0][:, [0, 2, 1]]
    tri = tri[np.abs(cross) > 1e-12]

    depth = [sum(paths[j].contains_point(r[0]) for j in range(len(rings)) if j != i) for i, r in enumerate(rings)]
    loops, base = [], 0
    for i, r in enumerate(rings):
        idx = list(range(base, base + len(r)))
        if (signed_area(r) > 0) != (depth[i] % 2 == 0):
            idx = idx[::-1]
        loops.append(idx)
        base += len(r)
    want = sum(abs(signed_area(r)) * (1 if depth[k] % 2 == 0 else -1) for k, r in enumerate(rings))
    got = _tri_area(pts, tri)
    if abs(want - got) > 1e-6 * max(1.0, want) + 1e-6:
        raise RuntimeError(f"triangulation area mismatch {want:.4f} vs {got:.4f}")
    return pts, tri, loops


# ------------------------------------------------------- 3D shells
class Frame:
    """2D sketch plane: point = o + a*u + b*v + d*n (u x v = n)."""

    def __init__(self, n, origin=(0, 0, 0)):
        n = np.asarray(n, float)
        self.n = n / np.linalg.norm(n)
        if abs(self.n[2]) > 0.5:     # (near-)horizontal sketch: u = x
            self.u = np.array([1.0, 0, 0])
            self.v = np.cross(self.n, self.u)
        else:                        # wall sketch, seen from outside: u = right, v = up
            self.u = np.cross(-self.n, [0, 0, 1.0])
            self.v = np.array([0, 0, 1.0])
        self.o = np.asarray(origin, float)

    def to3d(self, p2, d):
        return self.o + p2[:, :1] * self.u + p2[:, 1:2] * self.v + d * self.n


FLAT = Frame((0, 0, 1))
LID = Frame((0, -S, C), origin=(0, 0, z_top(0.0)))   # d = 0 is the lid's top surface


def lid2d(x, y):
    """Top-surface point seen from above at (x, y) -> lid sketch coordinates."""
    return x, y / C


def to_lid_top(V):
    """Lift sketch-height TOPFLAG vertices onto the lid underside."""
    m = V[:, 2] > TOPFLAG - 1
    V[m, 2] = z_under(V[m, 1])
    return V


def extrude(rings, d0, d1, frame=FLAT, to_top=False, vertical_edges=False):
    """Closed shell: even-odd region of rings, from d0 to d1 along the frame normal.

    to_top: vertices sketched at TOPFLAG height end on the sloped lid underside.
    vertical_edges: (lid) the outline (rings[0]) gets vertical side faces
    instead of faces square to the lid, so it lines up with the tray walls.
    """
    pts, tri, loops = triangulate(rings)
    n = len(pts)
    v0, v1 = frame.to3d(pts, d0), frame.to3d(pts, d1)
    if vertical_edges:
        o = np.array(loops[0])
        for V, d in ((v0, d0), (v1, d1)):    # slide along the slope back to the top-surface y
            V[o] += (d * S / C) * frame.v
    verts = np.vstack([v0, v1])
    if to_top:
        verts = to_lid_top(verts)
    faces = [tri[:, ::-1], tri + n]
    for lp in loops:
        a = np.array(lp)
        b = np.roll(a, -1)
        faces.append(np.c_[a, b, b + n])
        faces.append(np.c_[a, b + n, a + n])
    return verts, np.vstack(faces)


def tube(cx, cy, d_out, d_in, z0, z1, frame=FLAT):
    rings = [circle(cx, cy, d_out)] + ([circle(cx, cy, d_in)] if d_in else [])
    return extrude(rings, z0, z1, frame)


class Part:
    def __init__(self, name):
        self.name, self.shells = name, []

    def add(self, shell):
        self.shells.append(shell)

    def triangles(self):
        return np.vstack([v[f] for v, f in self.shells])

    def write_stl(self, path):
        tris = self.triangles().astype(np.float32)
        nrm = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-20
        with open(path, "wb") as f:
            f.write(f"Melon Pedal {self.name}".encode().ljust(80, b" "))
            f.write(struct.pack("<I", len(tris)))
            rec = np.zeros(len(tris), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
            rec["n"], rec["v"] = nrm, tris
            f.write(rec.tobytes())
        return len(tris)


# ============================================================ lid
def outline():
    return rrect(0, 0, W, L, R_CORNER)


def lid_outline():
    o = outline()
    return np.c_[o[:, 0], o[:, 1] / C]


def screw_axis(x, y, d):
    """3D point on the axis of the lid screw at (x, y), depth d (d = 0 top surface)."""
    a, b = lid2d(x, y)
    return LID.to3d(np.array([[a, b]]), d)[0]


def lid():
    part = Part("lid")
    P = lambda x, y: lid2d(x, y)
    through = [circle(*P(x, y), ENC_HOLE) for x, y in KNOBS]
    through += [circle(*P(*FOOT_XY), FOOT_HOLE), circle(*P(*LED_XY), LED_HOLE)]
    bezel = rrect(*P(*LCD_C), *LCD_BEZEL, 2.5)
    view = rrect(*P(*LCD_C), *LCD_VIEW, 1.0)
    heads = [circle(*P(x, y), LID_SCREW_HEAD[0]) for x, y in LID_SCREWS]
    shanks = [circle(*P(x, y), LID_SCREW_HOLE) for x, y in LID_SCREWS]
    numbers = []
    for i, (x, y) in enumerate(KNOBS):
        numbers += text_rings(str(i + 1), *P(x + math.copysign(KNOB_NUMBER_DX, x), y + KNOB_NUMBER_DY), 4.0)
    pockets = [rrect(*P(x, y), ENC_POCKET, ENC_POCKET, 1.5) for x, y in KNOBS]
    pockets += [circle(*P(*FOOT_XY), FOOT_HOLE), circle(*P(*LED_XY), LED_HOLE), rrect(*P(*LCD_C), *LCD_POCKET, 1.0)]

    o = lid_outline()
    e = EPS / 2
    h = LID_SCREW_HEAD[1]
    layers = [  # (depth range below the top, holes)
        ((0.0, ENGRAVE), [bezel] + through + heads + numbers),
        ((ENGRAVE - e, LCD_BEZEL_DEPTH), [bezel] + through + heads),
        ((LCD_BEZEL_DEPTH - e, h), [view] + through + heads),
        ((h - e, ENC_LID_T), [view] + through + shanks),
        ((ENC_LID_T - e, LID_T), pockets + shanks),
    ]
    for (t0, t1), holes in layers:
        part.add(extrude([o] + holes, -t1, -t0, LID, vertical_edges=True))
    return part


# ============================================================ tray
def tray():
    part = Part("tray")
    # floor with vents
    vents = [rrect(x, sum(FLOOR_VENT_Y) / 2, VENT_W, FLOOR_VENT_Y[1] - FLOOR_VENT_Y[0], VENT_W / 2)
             for x in FLOOR_VENTS_X]
    part.add(extrude([outline()] + vents, 0, FLOOR))

    # back wall (normal +y). Sketch coords: a = -x (right as seen from behind), b = z
    back = Frame((0, 1, 0))
    span = HW - R_CORNER + EPS
    wall_rect = rect(-span, 0, span, TOPFLAG)
    jack_holes = [circle(-x, JACK_Z, d) for x, d, _, _ in JACKS]
    labels = []
    for x, _, _, txt in JACKS:
        labels += text_rings(txt, -x, LABEL_Z, LABEL_CAP)
    labels += text_rings(MIDI_LABEL[0], -MIDI_LABEL[1], MIDI_LABEL[2], LABEL_CAP)
    part.add(extrude([wall_rect] + jack_holes + labels, HL - ENGRAVE, HL, back, to_top=True))
    part.add(extrude([wall_rect] + jack_holes, HL - JACK_WALL_T, HL - ENGRAVE + EPS / 2, back, to_top=True))
    jack_pockets = [circle(-x, JACK_Z, p) for x, _, p, _ in JACKS]
    part.add(extrude([wall_rect] + jack_pockets, HL - WALL, HL - JACK_WALL_T + EPS / 2, back, to_top=True))

    # front wall (normal -y)
    part.add(extrude([wall_rect], HL - WALL, HL, Frame((0, -1, 0)), to_top=True))

    # right wall (normal +x): a = y. USB cut-out.
    span_y = HL - R_CORNER + EPS
    side_rect = rect(-span_y, 0, span_y, TOPFLAG)
    (y0, y1), (z0, z1) = USB_CUT_Y, USB_CUT_Z
    usb = rrect((y0 + y1) / 2, (z0 + z1) / 2, y1 - y0, z1 - z0, USB_CUT_R)
    part.add(extrude([side_rect, usb], HW - WALL, HW, Frame((1, 0, 0)), to_top=True))

    # left wall (normal -x): a = -y. Vent slots.
    vents = [rrect(-y, sum(VENT_Z) / 2, VENT_W, VENT_Z[1] - VENT_Z[0], VENT_W / 2) for y in VENT_YS]
    part.add(extrude([side_rect] + vents, HW - WALL, HW, Frame((-1, 0, 0)), to_top=True))

    # rounded corners
    for sx, sy, a0 in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        cx, cy = sx * (HW - R_CORNER), sy * (HL - R_CORNER)
        part.add(extrude([arc_band(cx, cy, R_CORNER - WALL, R_CORNER, a0 - 2, a0 + 92)], 0, TOPFLAG, to_top=True))

    # lid screw bosses: tilted tube with the insert hole, on a vertical column
    for x, y in LID_SCREWS:
        a, b = lid2d(x, y)
        d_hole = -LID_T - INSERT_DEPTH
        part.add(tube(a, b, BOSS_D, INSERT_HOLE, d_hole, -LID_T, LID))
        part.add(tube(a, b, BOSS_D, None, d_hole - BOSS_CAP + EPS, d_hole + EPS, LID))
        cx, cy, cz = screw_axis(x, y, d_hole - BOSS_CAP / 2 + EPS / 2)
        part.add(tube(cx, cy, BOSS_D, None, FLOOR - EPS, cz))

    # Pi 4 and I/O board standoffs
    for hx, hy in PI_HOLES:
        part.add(tube(PI_X0 + hx, PI_Y0 + hy, STANDOFF_D, PI_PILOT, FLOOR - EPS, FLOOR + PI_STANDOFF))
    for x, y in io_holes():
        part.add(tube(x, y, STANDOFF_D, IO_BOARD["pilot"], FLOOR - EPS, FLOOR + IO_BOARD["standoff"]))
    return part


def io_holes():
    (x0, x1), (y0, y1), k = IO_BOARD["x"], IO_BOARD["y"], IO_BOARD["hole_inset"]
    return [(x0 + k, y0 + k), (x1 - k, y0 + k), (x0 + k, y1 - k), (x1 - k, y1 - k)]


# ========================================================= checks
def check_closed(part):
    """Every edge of every shell is used exactly twice, in opposite directions."""
    for i, (v, f) in enumerate(part.shells):
        e = np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
        fwd = {tuple(x) for x in e}
        if len(fwd) != len(e) or any((b, a) not in fwd for a, b in fwd):
            raise RuntimeError(f"{part.name}: shell {i} is not closed")
        tri = v[f]
        vol = np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() / 6
        if vol <= 0:
            raise RuntimeError(f"{part.name}: shell {i} is inside out")


def lid_part_box(name):
    """Corners (8, 3) of a lid-mounted part's envelope in world coordinates."""
    x, y, sa, sb, depth = LID_PARTS[name]
    a, b = lid2d(x, y)
    pts = [(a + i * sa / 2, b + j * sb / 2) for i in (-1, 1) for j in (-1, 1)]
    p2 = np.array(pts)
    return np.vstack([LID.to3d(p2, -LID_T), LID.to3d(p2, -LID_T - depth)])


def clearance_report():
    """Smallest vertical gap between each lid part and the floor parts below it."""
    lines = []
    for name, (x, y, sa, sb, depth) in LID_PARTS.items():
        a, b = lid2d(x, y)
        ga, gb = np.meshgrid(np.linspace(a - sa / 2, a + sa / 2, 15), np.linspace(b - sb / 2, b + sb / 2, 15))
        bottom = LID.to3d(np.c_[ga.ravel(), gb.ravel()], -LID_T - depth)
        best = (1e9, "floor")
        for fname, (x0, x1, y0, y1, z0, z1) in FLOOR_PARTS.items():
            m = (bottom[:, 0] > x0) & (bottom[:, 0] < x1) & (bottom[:, 1] > y0) & (bottom[:, 1] < y1)
            if m.any():
                gap = (bottom[m, 2] - z1).min()
                if gap < best[0]:
                    best = (gap, fname)
        if best[1] == "floor":
            best = ((bottom[:, 2] - FLOOR).min(), "floor")
        lines.append((name, best[0], best[1]))
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--preview", action="store_true", help="also write preview PNGs")
    ap.add_argument("--out", default=OUT_DIR)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    print(f"label font: {FONT.get_file()}")
    print(f"slope: {math.degrees(ALPHA):.1f} deg, {H_FRONT:.0f} -> {H_BACK:.0f} mm")
    parts = [(tray(), "melon-pedal-tray.stl"), (lid(), "melon-pedal-lid.stl")]
    for part, fname in parts:
        check_closed(part)
        n = part.write_stl(os.path.join(args.out, fname))
        print(f"{fname}: {len(part.shells)} shells, {n} triangles")
    print("clearance (lid part -> nearest part below):")
    for name, gap, below in clearance_report():
        flag = "  <-- TOO CLOSE" if gap < 2.0 else ""
        print(f"  {name:12s} {gap:5.1f} mm above {below}{flag}")
    if args.preview:
        from enclosure_preview import write_previews
        write_previews([p for p, _ in parts], args.out)


if __name__ == "__main__":
    main()

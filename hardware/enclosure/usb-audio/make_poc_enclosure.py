"""Generate the 3D-printable Melon Pedal PoC enclosure (USB audio interface) as STL files.

Variant: USB AUDIO PoC (docs: 04-poc-usb-interface.md). The audio interface sits outside
the box and plugs into the Pi's USB ports through the open back wall.

    python3 hardware/enclosure/usb-audio/make_poc_enclosure.py            # STLs next to this script
    python3 hardware/enclosure/usb-audio/make_poc_enclosure.py --preview  # + preview PNG

Needs numpy, scipy and matplotlib (no CAD program).

Outside size: 65 W x 120 D x 40 H mm (bottom plate included). Two parts:
  * melon-poc-shell.stl  top panel + four walls. Footswitch, LED, 2.0" LCD and 4 encoders
                         mount in the top. Print UPSIDE DOWN (top on the bed): the wall
                         cut-outs are open at the bottom, so nothing needs supports.
  * melon-poc-plate.stl  bottom plate with the Pi 4 standoffs and vents. Print flat.
The plate sits inside the walls, flush with their bottom edge. Fixing (all from below):
  * 2 x M3 x 8 into heat-set inserts in the two front corner columns
  * 2 x M2.5 x 16 through the plate, the rear standoffs and the Pi's rear holes into
    pillars that hang from the top panel
  * the Pi's front holes: 2 x M2.5 x 6 from above into the plate standoffs

Pi 4 placement: 85 mm side along the depth, USB/Ethernet at the back wall (open cut-out),
USB-C/micro-HDMI at the right wall (open cut-out), GPIO header along the left wall.

Every dimension is a parameter below. MEASURE YOUR PARTS before printing (LCD module,
LED bezel, encoders, footswitch) and adjust.

Coordinates (mm): x = width (player's left is -x), y = depth (front -y, back +y),
z = up from the underside of the bottom plate.
"""
import argparse
import math
import os
import struct

import numpy as np
from matplotlib.path import Path as MplPath
from scipy.spatial import Delaunay

HERE = os.path.dirname(os.path.abspath(__file__))

# =========================================================== PARAMETERS
W, L, H = 68.0, 120.0, 40.0      # outside width, depth, height (68: the 2.0" LCD board did not fit in 65, 2026-11-24)
HW, HL = W / 2, L / 2
R_CORNER = 4.0                   # vertical corner radius
WALL = 2.4                       # wall thickness (6 perimeters of 0.4)
TOP = 2.4                        # top panel thickness
PLATE = 3.0                      # bottom plate thickness
PLATE_GAP = 0.3                  # clearance between plate and walls (each side)
Z_TOP_UNDER = H - TOP            # underside of the top panel

# --- top panel (positions seen from above) ---------------------------------
FOOT_XY, FOOT_HOLE = (0.0, -45.0), 12.2      # soft-touch footswitch, 12 mm thread
FOOT_RING = (20.0, 3.0)                      # reinforcing ring under the top: outer diameter, depth
LED_XY, LED_HOLE = (0.0, -31.0), 6.0         # 3 mm LED chrome bezel (check yours)
LCD_C = (0.0, -5.0)                          # LCD window centre
LCD_WINDOW = (42.0, 32.0)                    # visible area (2.0" ST7789, landscape)
LCD_POCKET = (61.5, 35.5, 1.0)               # locating pocket under the top: module board w, h, depth (+3 mm, measured fit)
ENC_HOLE = 7.2                               # EC11 M7 bushing
ENCODERS = [(-14.0, 22.0), (14.0, 22.0), (-14.0, 42.0), (14.0, 42.0)]   # 1, 2 front row; 3, 4 back row

# --- Pi 4 ----------------------------------------------------------------
PI_W, PI_L = 56.0, 85.0
PI_X0 = -PI_W / 2 + (W - 65.0) / 2           # GPIO edge (left); shifted with the right wall so the ports keep their place
PI_Y0 = HL - WALL - 2.6 - PI_L               # SD-card end (front); USB/Ethernet end 2.6 mm from the back wall
STANDOFF_H, STANDOFF_D = 3.0, 6.0            # printed standoffs on the plate
PI_T = 1.4
Z_PI_TOP = PLATE + STANDOFF_H + PI_T
PI_FRONT_HOLES = [(PI_X0 + 3.5, PI_Y0 + 3.5), (PI_X0 + 52.5, PI_Y0 + 3.5)]
PI_REAR_HOLES = [(PI_X0 + 3.5, PI_Y0 + 61.5), (PI_X0 + 52.5, PI_Y0 + 61.5)]
M25_PILOT = 2.2                              # M2.5 self-tapping into PETG/ASA
M25_CLEAR = 2.8
M25_HEAD = (5.2, 1.6)                        # counterbore in the plate: diameter, depth
PILLAR_D = 5.5                               # pillars from the top down onto the Pi's rear holes

# --- front corner columns with M3 heat-set inserts -------------------------
COLUMN_D = 10.0
COLUMNS = [(-(HW - 7.0), -(HL - WALL) + 4.8), (HW - 7.0, -(HL - WALL) + 4.8)]
INSERT_HOLE, INSERT_DEPTH = 4.0, 6.0         # M3 x 5.7 brass inserts (check your kit: 4.0-4.2)
M3_CLEAR, M3_HEAD = 3.4, (6.6, 1.8)

# --- wall cut-outs (open at the bottom) -------------------------------------
BACK_CUT = (-27.5 + (W - 65.0) / 2, 27.5 + (W - 65.0) / 2, Z_PI_TOP + 16.0 + 1.6)   # x0, x1, top z: 4 x USB + Ethernet (follows the Pi)
RIGHT_CUT = (PI_Y0 + 3.0, PI_Y0 + 48.0, Z_PI_TOP + 6.0)  # y0, y1, top z: USB-C + 2 x micro-HDMI

# --- vents (vertical slots / plate slots) -----------------------------------
# Wall slots have 45-degree pointed ends (user's v2, 2026-11-22): with the shell upside down
# every edge is self-supporting, so no supports and no bridges (rounded ends need supports).
VENT_W = 2.6
LEFT_VENTS_Y = [-45.0 + 5.0 * i for i in range(13)]       # y = -45 .. 15
LEFT_VENT_Z = (12.0, 31.0)
RIGHT_VENTS_Y = [22.0 + 5.0 * i for i in range(6)]        # rear half, behind the port cut-out
RIGHT_VENT_Z = (16.0, 31.0)
PLATE_VENTS_X = [-15.0 + 5.0 * i for i in range(7)]
PLATE_VENT_Y = (PI_Y0 + 12.0, PI_Y0 + 45.0)               # under the SoC

SEG = 0.45                       # max segment length for circles/arcs
EPS = 0.2                        # overlap between shells of one part


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
    n = max(6, int(math.ceil(math.radians(a1 - a0) * r_out / SEG)))
    t = np.radians(np.linspace(a0, a1, n + 1))
    outer = np.c_[cx + r_out * np.cos(t), cy + r_out * np.sin(t)]
    inner = np.c_[cx + r_in * np.cos(t[::-1]), cy + r_in * np.sin(t[::-1])]
    return np.vstack([outer, inner])


def pointed_slot(a, b0, b1, w):
    """Vertical slot at a, from b0 to b1, width w, with 45-degree pointed ends (print without supports)."""
    h = w / 2
    return np.array([(a, b0), (a + h, b0 + h), (a + h, b1 - h), (a, b1), (a - h, b1 - h), (a - h, b0 + h)], float)


def notched(a0, a1, b1, notches):
    """Wall outline a0..a1 x 0..b1 with notches (n0, n1, top) open at the bottom edge."""
    pts = [(a0, 0.0)]
    for n0, n1, top in sorted(notches):
        pts += [(n0, 0.0), (n0, top), (n1, top), (n1, 0.0)]
    pts += [(a1, 0.0), (a1, b1), (a0, b1)]
    return np.array(pts, float)


# ------------------------------------------------- triangulation
def signed_area(p):
    x, y = p[:, 0], p[:, 1]
    return 0.5 * np.sum(x * np.roll(y, -1) - np.roll(x, -1) * y)


def _tri_area(pts, tri):
    a, b, c = pts[tri[:, 0]], pts[tri[:, 1]], pts[tri[:, 2]]
    return 0.5 * np.sum((b[:, 0] - a[:, 0]) * (c[:, 1] - a[:, 1]) - (b[:, 1] - a[:, 1]) * (c[:, 0] - a[:, 0]))


def triangulate(rings):
    """Even-odd region of rings (outline first, then holes): conforming Delaunay."""
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
    """2D sketch plane: point = o + a*u + b*v + d*n."""

    def __init__(self, n):
        self.n = np.asarray(n, float)
        if abs(self.n[2]) > 0.5:
            self.u, self.v = np.array([1.0, 0, 0]), np.array([0, 1.0, 0])
        else:                                     # wall seen from outside: u = right, v = up
            self.u = np.cross(-self.n, [0, 0, 1.0])
            self.v = np.array([0, 0, 1.0])

    def to3d(self, p2, d):
        return p2[:, :1] * self.u + p2[:, 1:2] * self.v + d * self.n


FLAT = Frame((0, 0, 1))


def extrude(rings, d0, d1, frame=FLAT):
    pts, tri, loops = triangulate(rings)
    n = len(pts)
    verts = np.vstack([frame.to3d(pts, d0), frame.to3d(pts, d1)])
    faces = [tri[:, ::-1], tri + n]
    for lp in loops:
        a = np.array(lp)
        b = np.roll(a, -1)
        faces.append(np.c_[a, b, b + n])
        faces.append(np.c_[a, b + n, a + n])
    return verts, np.vstack(faces)


def tube(cx, cy, d_out, d_in, z0, z1):
    rings = [circle(cx, cy, d_out)] + ([circle(cx, cy, d_in)] if d_in else [])
    return extrude(rings, z0, z1)


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
            f.write(f"Melon Pedal PoC {self.name}".encode().ljust(80, b" "))
            f.write(struct.pack("<I", len(tris)))
            rec = np.zeros(len(tris), dtype=[("n", "<f4", 3), ("v", "<f4", (3, 3)), ("a", "<u2")])
            rec["n"], rec["v"] = nrm, tris
            f.write(rec.tobytes())
        return len(tris)


def check_closed(part):
    for i, (v, f) in enumerate(part.shells):
        e = np.vstack([f[:, [0, 1]], f[:, [1, 2]], f[:, [2, 0]]])
        fwd = {tuple(x) for x in e}
        if len(fwd) != len(e) or any((b, a) not in fwd for a, b in fwd):
            raise RuntimeError(f"{part.name}: shell {i} is not closed")
        tri = v[f]
        if np.einsum("ij,ij->i", tri[:, 0], np.cross(tri[:, 1], tri[:, 2])).sum() <= 0:
            raise RuntimeError(f"{part.name}: shell {i} is inside out")


# ============================================================ parts
def shell():
    part = Part("shell")
    outline = rrect(0, 0, W, L, R_CORNER)

    # top panel: through holes, plus the LCD module pocket on the underside
    through = [circle(*FOOT_XY, FOOT_HOLE), circle(*LED_XY, LED_HOLE)] + [circle(x, y, ENC_HOLE) for x, y in ENCODERS]
    window = rrect(*LCD_C, *LCD_WINDOW, 1.0)
    pw, ph, pd = LCD_POCKET
    pocket = rrect(*LCD_C, pw, ph, 0.8)
    part.add(extrude([outline, pocket] + through, Z_TOP_UNDER, Z_TOP_UNDER + pd))
    part.add(extrude([outline, window] + through, Z_TOP_UNDER + pd - EPS / 2, H))

    zt = Z_TOP_UNDER + EPS                       # walls reach into the top panel
    # back wall (normal +y, a = -x): USB + Ethernet cut-out open at the bottom
    span_x = HW - R_CORNER + EPS
    x0, x1, ztop = BACK_CUT
    part.add(extrude([notched(-span_x, span_x, zt, [(-x1, -x0, ztop)])], HL - WALL, HL, Frame((0, 1, 0))))
    # front wall (normal -y, a = x)
    part.add(extrude([rect(-span_x, 0, span_x, zt)], HL - WALL, HL, Frame((0, -1, 0))))
    # right wall (normal +x, a = y): USB-C + HDMI cut-out, vents in the rear half
    span_y = HL - R_CORNER + EPS
    y0, y1, ztop = RIGHT_CUT
    vents = [pointed_slot(y, *RIGHT_VENT_Z, VENT_W) for y in RIGHT_VENTS_Y]
    part.add(extrude([notched(-span_y, span_y, zt, [(y0, y1, ztop)])] + vents, HW - WALL, HW, Frame((1, 0, 0))))
    # left wall (normal -x, a = -y): vents
    vents = [pointed_slot(-y, *LEFT_VENT_Z, VENT_W) for y in LEFT_VENTS_Y]
    part.add(extrude([rect(-span_y, 0, span_y, zt)] + vents, HW - WALL, HW, Frame((-1, 0, 0))))
    # rounded corners
    for sx, sy, a0 in ((1, 1, 0), (-1, 1, 90), (-1, -1, 180), (1, -1, 270)):
        cx, cy = sx * (HW - R_CORNER), sy * (HL - R_CORNER)
        part.add(extrude([arc_band(cx, cy, R_CORNER - WALL, R_CORNER, a0 - 2, a0 + 92)], 0, zt))

    # front corner columns: insert hole from below, solid above
    for x, y in COLUMNS:
        part.add(tube(x, y, COLUMN_D, INSERT_HOLE, PLATE, PLATE + INSERT_DEPTH))
        part.add(tube(x, y, COLUMN_D, None, PLATE + INSERT_DEPTH - EPS, zt))
    # pillars onto the Pi's rear holes (M2.5 screws from below self-tap into them)
    for x, y in PI_REAR_HOLES:
        part.add(tube(x, y, PILLAR_D, M25_PILOT, Z_PI_TOP, Z_TOP_UNDER - 3.0))
        part.add(tube(x, y, PILLAR_D, None, Z_TOP_UNDER - 3.0 - EPS, zt))
    # reinforcing ring around the footswitch
    part.add(tube(*FOOT_XY, FOOT_RING[0], FOOT_HOLE, Z_TOP_UNDER - FOOT_RING[1], zt))
    return part


def plate():
    part = Part("plate")
    w, l = W - 2 * (WALL + PLATE_GAP), L - 2 * (WALL + PLATE_GAP)
    outline = rrect(0, 0, w, l, max(0.5, R_CORNER - WALL))
    vents = [rrect(x, sum(PLATE_VENT_Y) / 2, VENT_W, PLATE_VENT_Y[1] - PLATE_VENT_Y[0], VENT_W / 2) for x in PLATE_VENTS_X]
    heads = [circle(x, y, M3_HEAD[0]) for x, y in COLUMNS] + [circle(x, y, M25_HEAD[0]) for x, y in PI_REAR_HOLES]
    shanks = [circle(x, y, M3_CLEAR) for x, y in COLUMNS] + [circle(x, y, M25_CLEAR) for x, y in PI_REAR_HOLES]
    pilots = [circle(x, y, M25_PILOT) for x, y in PI_FRONT_HOLES]
    hd = max(M3_HEAD[1], M25_HEAD[1])
    part.add(extrude([outline] + vents + heads + pilots, 0, hd))
    part.add(extrude([outline] + vents + shanks + pilots, hd - EPS / 2, PLATE))
    for x, y in PI_FRONT_HOLES:
        part.add(tube(x, y, STANDOFF_D, M25_PILOT, PLATE - EPS, PLATE + STANDOFF_H))
    for x, y in PI_REAR_HOLES:
        part.add(tube(x, y, STANDOFF_D, M25_CLEAR, PLATE - EPS, PLATE + STANDOFF_H))
    return part


def report():
    """Clearances worth knowing before printing."""
    enc_bottom = Z_TOP_UNDER - 12.0          # EC11 body + pins below the top panel (approx.)
    usb_top = Z_PI_TOP + 16.0
    lines = [
        f"inside: {W - 2 * WALL:.1f} x {L - 2 * WALL:.1f} x {Z_TOP_UNDER - PLATE:.1f} mm (w x d x h)",
        f"Pi 4: y {PI_Y0:.1f} .. {PI_Y0 + PI_L:.1f}, board top at z {Z_PI_TOP:.1f}",
        f"rear encoders over the USB ports: about {enc_bottom - usb_top:.1f} mm (trim/bend the pins, Kapton tape)",
        f"LCD pocket {LCD_POCKET[0]} mm in {W - 2 * WALL:.1f} mm inside width",
        f"gap LCD pocket -> front encoder row: {ENCODERS[0][1] - 6.5 - (LCD_C[1] + LCD_POCKET[1] / 2):.1f} mm",
    ]
    return lines


def main():
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--preview", action="store_true", help="also write preview PNG")
    ap.add_argument("--out", default=HERE)
    args = ap.parse_args()
    os.makedirs(args.out, exist_ok=True)
    parts = [(shell(), "melon-poc-shell.stl"), (plate(), "melon-poc-plate.stl")]
    for part, fname in parts:
        check_closed(part)
        n = part.write_stl(os.path.join(args.out, fname))
        print(f"{fname}: {len(part.shells)} shells, {n} triangles")
    for line in report():
        print("  " + line)
    if args.preview:
        write_preview([p for p, _ in parts], os.path.join(args.out, "preview-poc.png"))


def write_preview(parts, path):
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    from mpl_toolkits.mplot3d.art3d import Poly3DCollection

    fig = plt.figure(figsize=(12, 6), dpi=110)
    views = [("shell, from above", parts[0], 0, 30, -60), ("shell, from below (inside)", parts[0], 0, -35, -60),
             ("plate", parts[1], -15, 35, -60)]
    for i, (title, part, dz, elev, azim) in enumerate(views):
        ax = fig.add_subplot(1, 3, i + 1, projection="3d")
        tris = part.triangles()
        nrm = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
        nrm /= np.linalg.norm(nrm, axis=1, keepdims=True) + 1e-12
        light = np.clip(nrm @ np.array([0.3, -0.5, 0.8]) / np.linalg.norm([0.3, -0.5, 0.8]), 0, 1) * 0.6 + 0.35
        col = np.c_[0.12 + 0.3 * light, 0.23 + 0.5 * light, 0.17 + 0.3 * light]
        ax.add_collection3d(Poly3DCollection(tris, facecolors=col, edgecolor="none"))
        ax.set_xlim(-HL, HL), ax.set_ylim(-HL, HL), ax.set_zlim(-HL + 20, HL + 20)
        ax.view_init(elev, azim)
        ax.set_title(title, fontsize=10)
        ax.set_axis_off()
    fig.tight_layout()
    fig.savefig(path)
    print(f"preview: {path}")


if __name__ == "__main__":
    main()

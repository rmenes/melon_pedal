"""Polished concept render of the Melon Pedal (wedge enclosure v0.2).

A small signed-distance-field ray marcher in NumPy: soft shadows, ambient
occlusion, metal reflections, printed panel graphics and a lit LCD.
No 3D software needed, only numpy + Pillow.

    python3 hardware/enclosure/hifiberry-wedge/render_concept.py [--res 1600x1000] [--ss 2]

Coordinates are millimetres: x = width (player's left is -x), y = length
(front is -y, back/jacks are +y), z = up. The ground is z = 0.
"""
import argparse
import os
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

F = np.float32
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get("RENDER_OUT", HERE)
FONT_DIR = "/usr/share/fonts/opentype/inter/"
CREAM = (0xF4, 0xFB, 0xE9)        # brand cream
LABEL = (0x7F, 0xD6, 0x8A)        # brand light green


def font(style, size):
    for name in (f"Inter-{style}.otf", "Inter-Regular.otf"):
        path = os.path.join(FONT_DIR, name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


# ---------------------------------------------------------------- geometry
W, L = 100.0, 135.0               # enclosure footprint
H_FRONT, H_BACK = 40.0, 65.0      # wedge: height at the front and back edge
H = H_BACK
FEET = 3.0                        # rubber feet height
Z0 = FEET                         # enclosure bottom
ZB = Z0 + H_BACK                  # top of the back edge
HW, HL = W / 2, L / 2
SLOPE = (H_BACK - H_FRONT) / L
CA, SA = float(np.cos(np.arctan(SLOPE))), float(np.sin(np.arctan(SLOPE)))
LID_T = 3.0                       # the lid is a separate part: seam 3 mm below the top

# Lid features live in a "flat" frame: the world rotated about the x axis so
# the sloped top becomes the plane z = ZT. Positions there are (x, y / cos).
ZT = Z0 + (H_FRONT + H_BACK) / 2  # top height at y = 0 (pivot of the rotation)
HLF = HL / CA                     # half length of the top, measured along the slope


def flat(xy):
    return (xy[0], xy[1] / CA)


def to_flat(p):
    q = p.copy()
    dz = p[:, 2] - ZT
    q[:, 1] = p[:, 1] * CA + dz * SA
    q[:, 2] = -p[:, 1] * SA + dz * CA + ZT
    return q


KNOBS = [flat(k) for k in [(-30.0, -5.0), (30.0, -5.0), (-30.0, 38.0), (30.0, 38.0)]]
FOOT_XY = flat((0.0, -44.0))
LED_XY = flat((0.0, -24.0))
LCD_C = flat((0.0, 16.5))         # LCD window centre (flat frame)
LCD_HALF = (23.0, 18.0)           # bezel recess half size
WIN_HALF = (21.0, 16.0)           # window half size
GLASS_HALF = (20.4, 15.3)         # active screen half size
JZ = Z0 + 17.0                    # jack centre height
JACKS = [  # x, kind
    (-36.0, "big"), (-16.0, "dc"), (1.0, "mini"), (16.0, "mini"), (36.0, "big")]
USB_C = (HW, -8.0, Z0 + 18.2)     # USB cut-out centre on the right wall (both USB stacks)
USB_HALF = (3.0, 17.5, 10.2)
USB_STICK = (HW - 1.7, 1.0, Z0 + 14.4)   # boot drive in the lower blue USB 3 port
VENT_YS = [-20.0 + 5.0 * i for i in range(9)]

# material ids
M_GROUND, M_BODY, M_METAL, M_KNOB, M_GLASS, M_LED, M_HOLE, M_RUBBER, M_USB, M_BEZEL = range(10)
# material of each entry in scene(): ground, body, metal, knob, glass, led, holes, feet, usb, port shadow
MATS = [M_GROUND, M_BODY, M_METAL, M_KNOB, M_GLASS, M_LED, M_HOLE, M_RUBBER, M_USB, M_HOLE]


def length2(a, b):
    return np.sqrt(a * a + b * b)


def sd_round_box(p, c, h, r):
    qx = np.abs(p[:, 0] - c[0]) - (h[0] - r)
    qy = np.abs(p[:, 1] - c[1]) - (h[1] - r)
    qz = np.abs(p[:, 2] - c[2]) - (h[2] - r)
    out = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2 + np.maximum(qz, 0) ** 2)
    inn = np.minimum(np.maximum(np.maximum(qx, qy), qz), 0)
    return out + inn - r


def sd_cyl(p, c, axis, r, h, rr=0.0):
    """Cylinder starting at c, extending h along +axis (0=x,1=y,2=z)."""
    a = [0, 1, 2]
    a.remove(axis)
    u, v = p[:, a[0]] - c[a[0]], p[:, a[1]] - c[a[1]]
    w = p[:, axis] - (c[axis] + h / 2)
    dx = np.sqrt(u * u + v * v) - r + rr
    dy = np.abs(w) - h / 2 + rr
    return np.minimum(np.maximum(dx, dy), 0) + length2(np.maximum(dx, 0), np.maximum(dy, 0)) - rr


def sd_hex(p, c, axis, r, h):
    """Hex prism (nut), across-flats radius r, from c along +axis by h."""
    a = [0, 1, 2]
    a.remove(axis)
    u, v = np.abs(p[:, a[0]] - c[a[0]]), np.abs(p[:, a[1]] - c[a[1]])
    k = (-0.8660254, 0.5, 0.57735)
    dot = np.minimum(k[0] * u + k[1] * v, 0)
    u = u - 2 * dot * k[0]
    v = v - 2 * dot * k[1]
    cu = np.clip(u, -k[2] * r, k[2] * r)
    dx = length2(u - cu, v - r) * np.sign(v - r)
    w = p[:, axis] - (c[axis] + h / 2)
    dy = np.abs(w) - h / 2
    return np.minimum(np.maximum(dx, dy), 0) + length2(np.maximum(dx, 0), np.maximum(dy, 0))


def round_intersect(a, b, r):
    ua, ub = np.maximum(r + a, 0), np.maximum(r + b, 0)
    return np.minimum(-r, np.maximum(a, b)) + np.sqrt(ua * ua + ub * ub)


def body_sdf(p, pf):
    box = sd_round_box(p, (0, 0, Z0 + (H + 10) / 2), (HW, HL, (H + 10) / 2), 5.0)   # taller: the slope cuts the top
    d = round_intersect(box, pf[:, 2] - ZT, 1.5)          # sloped top, softly rounded edge
    # LCD bezel recess + window
    rec = sd_round_box(pf, (LCD_C[0], LCD_C[1], ZT), (LCD_HALF[0], LCD_HALF[1], 1.0), 1.5)
    win = sd_round_box(pf, (LCD_C[0], LCD_C[1], ZT), (WIN_HALF[0], WIN_HALF[1], 3.0), 0.8)
    d = np.maximum(d, -np.minimum(rec, win))
    # vertical vent slots on the left wall
    for y in VENT_YS:
        slot = sd_round_box(p, (-HW, y, Z0 + 25.0), (2.0, 1.3, 11.0), 1.2)
        d = np.maximum(d, -slot)
    # USB cut-out on the right wall
    pocket = sd_round_box(p, USB_C, USB_HALF, 2.0)
    d = np.maximum(d, -pocket)
    return d


def scene(p, want_mat=False):
    ds = []
    pf = to_flat(p)
    ds.append(p[:, 2])                                    # ground
    ds.append(body_sdf(p, pf))                            # body
    p_world, p = p, pf                                    # lid parts below use the flat frame
    # metal: washers, footswitch, LED bezel, jack nuts + bushings, USB metal
    metal = sd_hex(p, (FOOT_XY[0], FOOT_XY[1], ZT), 2, 8.5, 3.0)
    metal = np.minimum(metal, sd_cyl(p, (FOOT_XY[0], FOOT_XY[1], ZT + 2.5), 2, 6.0, 9.5, 2.2))
    metal = np.minimum(metal, sd_cyl(p, (LED_XY[0], LED_XY[1], ZT), 2, 3.4, 2.2, 0.6))
    for kx, ky in KNOBS:
        metal = np.minimum(metal, sd_cyl(p, (kx, ky, ZT), 2, 8.5, 1.2, 0.4))
    p = p_world
    hole = None
    for x, kind in JACKS:
        nut_r, bush_r, hole_r = {"big": (7.0, 4.8, 3.2), "dc": (6.0, 4.0, 2.9), "mini": (4.2, 3.0, 1.7)}[kind]
        metal = np.minimum(metal, sd_hex(p, (x, HL, JZ), 1, nut_r, 2.4))
        metal = np.minimum(metal, sd_cyl(p, (x, HL, JZ), 1, bush_r, 4.2, 0.4))
        hd = sd_cyl(p, (x, HL + 0.5, JZ), 1, hole_r, 6.0)
        hole = hd if hole is None else np.minimum(hole, hd)
    metal = np.maximum(metal, -hole)
    ds.append(metal)
    p = pf
    # knobs (black, knurled skirt)
    knob = None
    for kx, ky in KNOBS:
        u, v = p[:, 0] - kx, p[:, 1] - ky
        ang = np.arctan2(v, u)
        knurl = 0.22 * np.cos(30 * ang) * (p[:, 2] < ZT + 11.5)
        kd = sd_cyl(p, (kx, ky, ZT + 1.2), 2, 7.6, 14.0, 1.6) + knurl
        knob = kd if knob is None else np.minimum(knob, kd)
    ds.append(knob)
    # LCD glass (under the window, behind the 3 mm lid)
    ds.append(sd_round_box(p, (LCD_C[0], LCD_C[1], ZT - 3.3), (WIN_HALF[0] + 1.0, WIN_HALF[1] + 1.0, 0.3), 0.4))
    # LED dome
    led = np.sqrt((p[:, 0] - LED_XY[0]) ** 2 + (p[:, 1] - LED_XY[1]) ** 2 + (p[:, 2] - (ZT + 2.0)) ** 2) - 2.0
    ds.append(led)
    p = p_world
    # jack holes: dark material, placed as a thin disc deep in the hole
    hb = None
    for x, kind in JACKS:
        hole_r = {"big": 3.2, "dc": 2.9, "mini": 1.7}[kind]
        hd = sd_cyl(p, (x, HL + 0.2, JZ), 1, hole_r + 0.1, 0.6)
        hb = hd if hb is None else np.minimum(hb, hd)
    ds.append(hb)
    # rubber feet
    feet = None
    for fx in (-HW + 9, HW - 9):
        for fy in (-HL + 9, HL - 9):
            fd = sd_cyl(p, (fx, fy, 0.0), 2, 6.0, FEET + 0.5, 1.0)
            feet = fd if feet is None else np.minimum(feet, fd)
    ds.append(feet)
    # USB boot drive in the cut-out
    usb = sd_round_box(p, USB_STICK, (4.4, 7.9, 3.6), 1.2)
    ds.append(usb)
    # dark inside of the USB cut-out (the Pi's ports)
    ds.append(sd_round_box(p, (HW - 3.2, USB_C[1], USB_C[2]), (0.4, USB_HALF[1] - 0.3, USB_HALF[2] - 0.3), 0.3))
    D = np.stack(ds, axis=1)
    d = D.min(axis=1)
    if want_mat:
        return d, np.array(MATS)[D.argmin(axis=1)]
    return d


# ---------------------------------------------------------------- textures
TEX_PX = 12  # pixels per mm for panel graphics


def make_top_texture():
    w, h = int(W * TEX_PX), int(2 * HLF * TEX_PX)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)

    def xy(x, y):  # mm (flat frame) -> px; image top = back edge
        return (x + HW) * TEX_PX, (HLF - y) * TEX_PX

    cream = CREAM + (255,)
    # brand at the front strip
    f_big = font("Bold", int(7.0 * TEX_PX))
    f_small = font("Medium", int(2.6 * TEX_PX))
    cx, cy = xy(0, -58.0 / CA)
    dr.text((cx, cy), "MELON", font=f_big, fill=cream, anchor="mm")
    cx, cy = xy(0, -63.4 / CA)
    dr.text((cx, cy), "S T E R E O   ·   L V 2   ·   M I D I", font=f_small, fill=CREAM + (200,), anchor="mm")
    # knob numbers + tick arcs
    f_num = font("SemiBold", int(3.2 * TEX_PX))
    for i, (kx, ky) in enumerate(KNOBS):
        cx, cy = xy(kx, ky)
        r = 11.5 * TEX_PX
        for a in np.linspace(np.radians(-225), np.radians(45), 11):
            x0, y0 = cx + r * np.cos(a), cy + r * np.sin(a)
            x1, y1 = cx + (r + 1.6 * TEX_PX) * np.cos(a), cy + (r + 1.6 * TEX_PX) * np.sin(a)
            dr.line((x0, y0, x1, y1), fill=CREAM + (170,), width=int(0.45 * TEX_PX))
        tx, ty = xy(kx, ky - 14.5 / CA)
        dr.text((tx, ty), str(i + 1), font=f_num, fill=cream, anchor="mm")
    # footswitch ring
    cx, cy = xy(*FOOT_XY)
    r = 10.8 * TEX_PX
    dr.ellipse((cx - r, cy - r, cx + r, cy + r), outline=CREAM + (120,), width=int(0.4 * TEX_PX))
    # pinstripe border
    m = 2.4 * TEX_PX
    dr.rounded_rectangle((m, m, w - m, h - m), radius=int(3 * TEX_PX), outline=CREAM + (90,), width=int(0.35 * TEX_PX))
    return np.asarray(img.filter(ImageFilter.GaussianBlur(0.6))).astype(F) / 255


def make_back_texture():
    w, h = int(W * TEX_PX), int(H * TEX_PX)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    f = font("SemiBold", int(3.6 * TEX_PX))
    labels = {-36.0: "OUT", -16.0: "9V", 1.0: "OUT", 16.0: "IN", 36.0: "IN"}   # same as the STL engraving
    for x, kind in JACKS:
        # back face seen from behind: player's left (-x) appears on the right
        px = (HW - x) * TEX_PX
        py = (ZB - (Z0 + 29.0)) * TEX_PX
        dr.text((px, py), labels[x], font=f, fill=LABEL + (235,), anchor="mm")
    dr.text(((HW - 8.5) * TEX_PX, (ZB - (Z0 + 35.0)) * TEX_PX), "MIDI", font=f, fill=LABEL + (235,), anchor="mm")
    return np.asarray(img.filter(ImageFilter.GaussianBlur(0.6))).astype(F) / 255


def make_side_texture():
    w, h = int(L * TEX_PX), int(H * TEX_PX)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    f = font("SemiBold", int(2.6 * TEX_PX))
    # right wall seen from +x: front (-y) on the left
    px = (USB_C[1] + HL) * TEX_PX
    py = (ZB - (USB_C[2] + USB_HALF[2] + 4.0)) * TEX_PX
    dr.text((px, py), "USB · BOOT", font=f, fill=LABEL + (220,), anchor="mm")
    return np.asarray(img.filter(ImageFilter.GaussianBlur(0.6))).astype(F) / 255


def make_screen_texture():
    w, h = 480, 350
    img = Image.new("RGB", (w, h), (8, 12, 18))
    dr = ImageDraw.Draw(img)
    accent = (0x7F, 0xD6, 0x8A)   # brand light green
    dr.rectangle((0, 0, w, 52), fill=(22, 34, 44))
    dr.text((18, 26), "P01", font=font("Bold", 30), fill=accent, anchor="lm")
    dr.text((w - 18, 26), "48 kHz  ·  3.2 ms", font=font("Medium", 22), fill=(150, 170, 185), anchor="rm")
    dr.text((w / 2, 102), "Melon Drive", font=font("Bold", 50), fill=(235, 240, 245), anchor="mm")
    params = [("Gain", 0.62), ("Tone", 0.45), ("Mix", 0.30), ("Level", 0.75)]
    for i, (name, val) in enumerate(params):
        col, row = i % 2, i // 2
        x0, y0 = 22 + col * 230, 160 + row * 90
        dr.text((x0, y0), f"{i + 1}  {name}", font=font("SemiBold", 30), fill=(200, 210, 220), anchor="lm")
        dr.text((x0 + 210, y0), f"{int(val * 100)}", font=font("Bold", 26), fill=accent, anchor="rm")
        dr.rounded_rectangle((x0, y0 + 24, x0 + 210, y0 + 38), radius=7, fill=(35, 48, 58))
        dr.rounded_rectangle((x0, y0 + 24, x0 + int(210 * val), y0 + 38), radius=7, fill=accent)
    return np.asarray(img).astype(F) / 255


TOP_TEX = make_top_texture()
BACK_TEX = make_back_texture()
SIDE_TEX = make_side_texture()
SCREEN_TEX = make_screen_texture()


def sample(tex, u, v):
    """u, v in [0,1] (v = 0 at image top). Bilinear-free nearest lookup."""
    th, tw = tex.shape[:2]
    xi = np.clip((u * (tw - 1)).astype(np.int32), 0, tw - 1)
    yi = np.clip((v * (th - 1)).astype(np.int32), 0, th - 1)
    return tex[yi, xi]


# ---------------------------------------------------------------- rendering
BB_MIN = np.array([-HW - 6, -HL - 6, 0.0], F)
BB_MAX = np.array([HW + 6, HL + 10, ZB + 20], F)


def ray_box(ro, rd):
    inv = 1.0 / np.where(np.abs(rd) < 1e-8, 1e-8, rd)
    t0 = (BB_MIN - ro) * inv
    t1 = (BB_MAX - ro) * inv
    tmin = np.minimum(t0, t1).max(axis=1)
    tmax = np.maximum(t0, t1).min(axis=1)
    return np.maximum(tmin, 0), tmax


def march(ro, rd, max_steps=220):
    n = ro.shape[0]
    t_near, t_far = ray_box(ro, rd)
    inside = t_far > t_near
    # ground hit (analytic) for rays that miss the box or exit it
    t_ground = np.where(rd[:, 2] < -1e-6, -ro[:, 2] / np.where(rd[:, 2] < -1e-6, rd[:, 2], -1), np.inf).astype(F)
    t = np.where(inside, t_near, t_ground).astype(F)
    hit = np.zeros(n, bool)
    active = np.where(inside)[0]
    for _ in range(max_steps):
        if active.size == 0:
            break
        p = ro[active] + rd[active] * t[active, None]
        d = scene(p)
        t[active] += d * 0.9
        done = d < 0.004 * np.maximum(t[active], 1) * 0.05 + 0.002
        out = t[active] > t_far[active]
        hit[active[done]] = True
        t[active[out & ~done]] = t_ground[active[out & ~done]]
        active = active[~(done | out)]
    hit |= np.isfinite(t)
    return t, hit


def normals(p):
    e = 0.01
    k = np.array([[1, -1, -1], [-1, -1, 1], [-1, 1, -1], [1, 1, 1]], F)
    n = np.zeros_like(p)
    for v in k:
        n += v * scene(p + v * e)[:, None]
    return n / (np.linalg.norm(n, axis=1, keepdims=True) + 1e-9)


def soft_shadow(p, ld, k=10.0):
    res = np.ones(p.shape[0], F)
    t = np.full(p.shape[0], 0.3, F)
    active = np.arange(p.shape[0])
    _, t_far = ray_box(p, np.broadcast_to(ld, p.shape).astype(F))
    for _ in range(64):
        if active.size == 0:
            break
        q = p[active] + ld * t[active, None]
        d = scene(q)
        d = np.maximum(d, q[:, 2] * 0 + d)  # keep shape
        dd = np.where(q[:, 2] < 0.05, 1e3, d)  # ignore ground itself
        res[active] = np.minimum(res[active], np.clip(k * dd / t[active], 0, 1))
        t[active] += np.clip(dd, 0.15, 6.0)
        keep = (res[active] > 0.01) & (t[active] < t_far[active] + 5)
        active = active[keep]
    return res ** 1.3


def ambient_occ(p, n):
    occ = np.zeros(p.shape[0], F)
    sca = 1.0
    for i in range(1, 6):
        h = 0.6 * i
        d = scene(p + n * h)
        occ += (h - d) * sca
        sca *= 0.75
    return np.clip(1 - 0.12 * occ, 0, 1)


def sky(rd):
    up = np.clip(rd[:, 2], -1, 1)[:, None]
    horizon = np.array([0.93, 0.92, 0.90], F)
    zen = np.array([0.80, 0.84, 0.90], F)
    col = horizon + (zen - horizon) * np.clip(up, 0, 1)
    # big soft box light (studio) for reflections
    box = np.exp(-((rd[:, 0] + 0.45) ** 2 + (rd[:, 1] + 0.35) ** 2) * 9.0) * (rd[:, 2] > 0.3)
    return col + 1.2 * box[:, None]


def env_refl(rd):
    """Studio environment seen in reflections: dark floor/walls, bright softbox."""
    z = rd[:, 2:3]
    floor = np.array([0.20, 0.20, 0.21], F)
    wall = np.array([0.30, 0.31, 0.33], F)
    ceil = np.array([0.75, 0.78, 0.82], F)
    col = np.where(z < 0, floor, wall + (ceil - wall) * np.clip(z * 1.6, 0, 1))
    box = np.exp(-((rd[:, 0] + 0.45) ** 2 + (rd[:, 1] + 0.35) ** 2) * 7.0) * (rd[:, 2] > 0.25)
    rim = np.exp(-((rd[:, 0] - 0.8) ** 2 + (rd[:, 1] - 0.2) ** 2) * 10.0) * (rd[:, 2] > 0.0)
    return col + 2.0 * box[:, None] + 0.8 * rim[:, None]


KEY = np.array([-0.45, -0.38, 0.81], F)
KEY /= np.linalg.norm(KEY)
FILL = np.array([0.7, 0.3, 0.4], F)
FILL /= np.linalg.norm(FILL)


def shade(ro, rd, t, hit):
    n_px = ro.shape[0]
    col = np.zeros((n_px, 3), F)
    idx = np.where(hit)[0]
    p = ro[idx] + rd[idx] * t[idx, None]
    d, mat = scene(p, want_mat=True)
    nrm = normals(p)
    nrm[mat == M_GROUND] = (0, 0, 1)
    sh = soft_shadow(p + nrm * 0.05, KEY)
    ao = ambient_occ(p, nrm)
    v = -rd[idx]

    base = np.zeros((idx.size, 3), F)
    spec_k = np.zeros(idx.size, F)
    gloss = np.full(idx.size, 32.0, F)
    refl = np.zeros(idx.size, F)
    emis = np.zeros((idx.size, 3), F)

    g = mat == M_GROUND
    r = np.sqrt(p[g, 0] ** 2 + p[g, 1] ** 2)
    base[g] = np.array([0.80, 0.79, 0.77], F) * (1 - 0.15 * np.clip(r / 400, 0, 1))[:, None]
    spec_k[g] = 0.05

    b = mat == M_BODY
    body_col = (np.array([0x1E, 0x3A, 0x2B], F) / 255) ** 2.2 * 0.85   # brand deep green #1E3A2B
    base[b] = body_col
    spec_k[b] = 0.35
    gloss[b] = 60
    refl[b] = 0.06
    # printed graphics on faces
    pb = p[b]
    pbf = to_flat(pb)
    nb = nrm[b]
    gfx = np.zeros((pb.shape[0], 4), F)
    top = nb[:, 2] > 0.7
    if top.any():
        u = (pbf[top, 0] + HW) / W
        vv = (HLF - pbf[top, 1]) / (2 * HLF)
        gfx[top] = sample(TOP_TEX, u, vv)
    back = nb[:, 1] > 0.7
    if back.any():
        u = (HW - pb[back, 0]) / W
        vv = (ZB - pb[back, 2]) / H
        gfx[back] = sample(BACK_TEX, u, vv)
    side = nb[:, 0] > 0.7
    if side.any():
        u = (pb[side, 1] + HL) / L
        vv = (ZB - pb[side, 2]) / H
        gfx[side] = sample(SIDE_TEX, u, vv)
    a = gfx[:, 3:4]
    base[b] = base[b] * (1 - a) + gfx[:, :3] ** 2.2 * a
    # lid seam: the lid is a separate part, 3 mm thick
    seam = (np.abs(pbf[:, 2] - (ZT - LID_T)) < 0.22) & (nb[:, 2] < 0.7)
    base[np.where(b)[0][seam]] *= 0.35

    m = mat == M_METAL
    base[m] = np.array([0.18, 0.18, 0.19], F)
    spec_k[m] = 0.9
    gloss[m] = 120
    refl[m] = 0.75

    k = mat == M_KNOB
    pk = to_flat(p[k])
    base[k] = np.array([0.025, 0.025, 0.028], F)
    spec_k[k] = 0.45
    gloss[k] = 40
    refl[k] = 0.08
    # aluminium cap + white pointer on the knob tops
    topk = nrm[k, 2] > 0.85
    capc = np.zeros(pk.shape[0], bool)
    ptr = np.zeros(pk.shape[0], bool)
    for i, (kx, ky) in enumerate(KNOBS):
        dx, dy = pk[:, 0] - kx, pk[:, 1] - ky
        rr = np.sqrt(dx * dx + dy * dy)
        near = rr < 8
        capc |= near & topk & (rr < 5.2)
        ang = np.radians([-40, 25, 70, 140][i])
        along = dx * np.cos(ang) + dy * np.sin(ang)
        perp = -dx * np.sin(ang) + dy * np.cos(ang)
        ptr |= near & topk & (np.abs(perp) < 0.45) & (along > 1.5) & (along < 6.8)
    ki = np.where(k)[0]
    base[ki[capc]] = (0.30, 0.31, 0.33)
    refl[ki[capc]] = 0.35
    spec_k[ki[capc]] = 0.8
    base[ki[ptr]] = (0.85, 0.83, 0.78)

    gl = mat == M_GLASS
    pg = to_flat(p[gl])
    u = (pg[:, 0] - (LCD_C[0] - GLASS_HALF[0])) / (2 * GLASS_HALF[0])
    vv = ((LCD_C[1] + GLASS_HALF[1]) - pg[:, 1]) / (2 * GLASS_HALF[1])
    scr = sample(SCREEN_TEX, np.clip(u, 0, 1), np.clip(vv, 0, 1)) ** 2.2
    on = ((u > 0) & (u < 1) & (vv > 0) & (vv < 1))[:, None]   # black border around the active area
    emis[gl] = scr * 2.2 * on
    base[gl] = 0.01
    spec_k[gl] = 1.0
    gloss[gl] = 300
    refl[gl] = 0.10

    led = mat == M_LED
    base[led] = (0.4, 0.02, 0.02)
    emis[led] = (3.5, 0.25, 0.15)
    spec_k[led] = 1.0
    gloss[led] = 200

    hole = mat == M_HOLE
    base[hole] = 0.01
    rub = mat == M_RUBBER
    base[rub] = 0.02
    usb = mat == M_USB
    base[usb] = (0.05, 0.05, 0.06)
    spec_k[usb] = 0.6
    gloss[usb] = 80
    refl[usb] = 0.2
    bez = mat == M_BEZEL
    base[bez] = 0.008
    spec_k[bez] = 0.3

    # lighting
    ndl = np.clip((nrm * KEY).sum(1), 0, 1)
    ndf = np.clip((nrm * FILL).sum(1), 0, 1)
    hvec = KEY + v
    hvec /= np.linalg.norm(hvec, axis=1, keepdims=True)
    spec = np.clip((nrm * hvec).sum(1), 0, 1) ** gloss * spec_k * (gloss + 8) / 60
    amb = (0.55 + 0.45 * np.clip(nrm[:, 2], 0, 1)) * ao
    key_c = np.array([1.0, 0.97, 0.92], F) * 1.9
    fill_c = np.array([0.75, 0.82, 1.0], F) * 0.45
    amb_c = np.array([0.55, 0.58, 0.62], F)
    lit = base * (key_c * (ndl * sh)[:, None] + fill_c * ndf[:, None] + amb_c * amb[:, None])
    lit += key_c * (spec * sh)[:, None]
    # reflections of the studio environment (with Fresnel)
    rdir = rd[idx] - 2 * (rd[idx] * nrm).sum(1, keepdims=True) * nrm
    cosv = np.clip((nrm * v).sum(1), 0, 1)
    fres = refl + (1 - refl) * (1 - cosv) ** 5 * (refl > 0) * 0.6
    env = env_refl(rdir) * (0.35 + 0.65 * ao)[:, None]
    lit = lit * (1 - fres[:, None] * 0.5) + env * fres[:, None] * np.where(mat == M_METAL, 1.0, 0.6)[:, None]
    lit += emis
    # ground: fade to background, and contact shadow
    gi = np.where(g)[0]
    if gi.size:
        dist = np.sqrt(p[g, 0] ** 2 + p[g, 1] ** 2)
        fade = np.clip((dist - 180) / 220, 0, 1)[:, None]
        lit[gi] = lit[gi] * (1 - fade) + sky(rd[idx][g]) * 0.95 * fade
    col[idx] = lit
    miss = ~hit
    col[miss] = sky(rd[miss])
    return col


def camera_rays(res, ss, eye, target, fov):
    w, h = res[0] * ss, res[1] * ss
    eye = np.array(eye, F)
    fwd = np.array(target, F) - eye
    fwd /= np.linalg.norm(fwd)
    right = np.cross(fwd, [0, 0, 1]).astype(F)
    right /= np.linalg.norm(right)
    up = np.cross(right, fwd)
    tan = np.tan(np.radians(fov) / 2)
    xs = ((np.arange(w) + 0.5) / w * 2 - 1) * tan * (w / h)
    ys = (1 - (np.arange(h) + 0.5) / h * 2) * tan
    X, Y = np.meshgrid(xs, ys)
    rd = fwd + X[..., None] * right + Y[..., None] * up
    rd = rd.reshape(-1, 3).astype(F)
    rd /= np.linalg.norm(rd, axis=1, keepdims=True)
    ro = np.broadcast_to(eye, rd.shape).astype(F).copy()
    return ro, rd


def tonemap(c):
    a, b, cc, d, e = 2.51, 0.03, 2.43, 0.59, 0.14
    c = np.clip((c * (a * c + b)) / (c * (cc * c + d) + e), 0, 1)
    return c ** (1 / 2.2)


def render(name, res, ss, eye, target, fov, chunk=200_000):
    t0 = time.time()
    ro, rd = camera_rays(res, ss, eye, target, fov)
    out = np.zeros_like(rd)
    for s in range(0, rd.shape[0], chunk):
        sl = slice(s, s + chunk)
        t, hit = march(ro[sl], rd[sl])
        out[sl] = shade(ro[sl], rd[sl], t, hit)
    img = tonemap(out * 0.85).reshape(res[1] * ss, res[0] * ss, 3)
    im = Image.fromarray((img * 255).astype(np.uint8))
    if ss > 1:
        im = im.resize(res, Image.LANCZOS)
    path = os.path.join(OUT_DIR, name)
    im.save(path)
    print(f"{name}: {time.time() - t0:.0f} s")
    return path


if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", default="1600x1000")
    ap.add_argument("--ss", type=int, default=2)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    res = tuple(int(x) for x in a.res.split("x"))
    os.makedirs(OUT_DIR, exist_ok=True)
    views = {
        "render-hero.png": dict(eye=(165, -235, 190), target=(2, 10, 26), fov=28),
        "render-back.png": dict(eye=(-150, 250, 130), target=(-6, 22, 26), fov=27),
        "render-top.png": dict(eye=(0, -45, 380), target=(0, -3, 40), fov=29),
    }
    for name, v in views.items():
        if a.only and a.only not in name:
            continue
        render(name, res, a.ss, **v)

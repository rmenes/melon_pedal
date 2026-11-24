"""Concept render of the finished Melon Pedal PoC (USB audio interface version).

Same small NumPy ray marcher as hifiberry-wedge/render_concept.py: soft shadows, ambient
occlusion, metal reflections, printed panel graphics and a lit LCD showing the real
melon-display Play screen. No 3D software needed, only numpy + Pillow.

    python3 hardware/enclosure/usb-audio/render_poc.py [--res 1600x1000] [--ss 2] [--only hero]

Geometry follows make_poc_enclosure.py (72 x 120 x 40 mm). The external USB audio interface
next to the pedal is a generic stand-in, not a specific product.

Coordinates are millimetres: x = width (player's left is -x), y = depth (front is -y,
back is +y), z = up. The ground is z = 0.
"""
import argparse
import os
import time

import numpy as np
from PIL import Image, ImageDraw, ImageFilter, ImageFont

F = np.float32
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.environ.get("RENDER_OUT", HERE)
SCREEN_IMG = os.environ.get("MELON_SCREEN", os.path.join(HERE, "..", "..", "..", "software", "melon-display",
                                                         "preview", "chain.png"))
FONT_DIR = "/usr/share/fonts/opentype/inter/"
CREAM = (0xF4, 0xFB, 0xE9)        # brand cream
LABEL = (0x7F, 0xD6, 0x8A)        # brand light green


def font(style, size):
    for name in (f"Inter-{style}.otf", "Inter-Regular.otf"):
        path = os.path.join(FONT_DIR, name)
        if os.path.exists(path):
            return ImageFont.truetype(path, size)
    return ImageFont.load_default()


# ---------------------------------------------------------------- geometry (make_poc_enclosure.py)
W, L, H = 72.0, 120.0, 40.0
HW, HL = W / 2, L / 2
R_CORNER = 4.0
WALL = 2.4
FEET = 2.0                        # stick-on rubber feet
Z0 = FEET                         # enclosure bottom
ZT = Z0 + H                       # top surface
KNOBS = [(-14.0, 22.0), (14.0, 22.0), (-14.0, 42.0), (14.0, 42.0)]   # 1, 2 front row; 3, 4 back row
KNOB_R, KNOB_H = 6.2, 12.0
FOOT_XY = (0.0, -45.0)
LED_XY = (0.0, -31.0)
LCD_C = (0.0, -5.0)
WIN_HALF = (21.0, 16.0)           # window 42 x 32
GLASS_HALF = (20.4, 15.3)         # active area
Z_PI_TOP = Z0 + 3.0 + 3.0 + 1.4   # plate + standoff + board
BACK_CUT = (-27.5, 27.5, Z0 + 25.0)            # x0, x1, top z (Pi centred in the 72 mm box)
PI_RIGHT = 28.0                                # right edge of the Pi board
RIGHT_CUT = (-27.0, 18.0, Z0 + 14.9)           # y0, y1, top z
LEFT_VENTS_Y = [-45.0 + 5.0 * i for i in range(13)]
RIGHT_VENTS_Y = [22.0, 27.0, 32.0, 37.0, 52.0]   # gap at the rear wall boss
# Pi 4 ports seen from behind (GPIO on the left): Ethernet, USB 3 (blue), USB 2
ETH = (-17.75, 16.0, 13.5)         # x centre, width, height
USB3 = (1.0, 13.1, 16.0)
USB2 = (19.0, 13.1, 16.0)
PORT_FACE = HL - WALL              # front of the ports, flush with the inside of the back wall
# right-wall Pi connectors (y centres)
USBC_Y, HDMI_YS = -18.8, (-4.0, 9.5)
CONN_Z = Z_PI_TOP + 1.6

# external USB audio interface (generic stand-in) behind and to the right of the pedal
IFACE_C = (88.0, 70.0)             # centre x, y on the ground
IFACE_HALF = (34.0, 27.0, 21.0)
IFACE_KNOBS = [(74.0, 66.0), (100.0, 66.0)]

# cables: polylines (x, y, z) through which capsules are swept
USB_PLUG = (USB2[0], PORT_FACE + 7.0, Z_PI_TOP + 4.0)          # interface cable plug in the upper USB 2 port


def bezier(p0, p1, p2, p3, n=14):
    t = np.linspace(0, 1, n)[:, None]
    p0, p1, p2, p3 = (np.array(v, F) for v in (p0, p1, p2, p3))
    return ((1 - t) ** 3 * p0 + 3 * (1 - t) ** 2 * t * p1 + 3 * (1 - t) * t * t * p2 + t ** 3 * p3).astype(F)


CABLES = [
    # USB: pedal back -> interface left side
    (bezier((USB2[0], PORT_FACE + 14.0, Z_PI_TOP + 4.0), (USB2[0] + 2, PORT_FACE + 40.0, Z_PI_TOP + 4.0),
            (IFACE_C[0] - IFACE_HALF[0] - 30.0, IFACE_C[1] - 8.0, 2.5),
            (IFACE_C[0] - IFACE_HALF[0] - 12.0, IFACE_C[1] - 8.0, 12.0)), 1.9),
    # USB-C power: right wall -> off to the right
    (bezier((HW + 13.0, USBC_Y, CONN_Z), (HW + 30.0, USBC_Y - 4.0, 2.0), (HW + 70.0, -45.0, 1.7),
            (HW + 200.0, -60.0, 1.7)), 1.6),
    # guitar cable into the interface front, leaving to the right
    (bezier((IFACE_C[0] - 14.0, IFACE_C[1] - IFACE_HALF[1] - 16.0, 11.0), (IFACE_C[0] - 14.0, IFACE_C[1] - 48.0, 3.2),
            (IFACE_C[0] + 40.0, IFACE_C[1] - 50.0, 3.2), (IFACE_C[0] + 190.0, IFACE_C[1] - 40.0, 3.2)), 3.0),
]

# material ids
(M_GROUND, M_BODY, M_METAL, M_KNOB, M_GLASS, M_LED, M_DARK, M_RUBBER, M_PLASTIC, M_CABLE, M_IFACE,
 M_BLUE) = range(12)
MATS = [M_GROUND, M_BODY, M_METAL, M_KNOB, M_GLASS, M_LED, M_DARK, M_RUBBER, M_PLASTIC, M_CABLE, M_IFACE, M_BLUE]


def length2(a, b):
    return np.sqrt(a * a + b * b)


def sd_round_box(p, c, h, r):
    qx = np.abs(p[:, 0] - c[0]) - (h[0] - r)
    qy = np.abs(p[:, 1] - c[1]) - (h[1] - r)
    qz = np.abs(p[:, 2] - c[2]) - (h[2] - r)
    out = np.sqrt(np.maximum(qx, 0) ** 2 + np.maximum(qy, 0) ** 2 + np.maximum(qz, 0) ** 2)
    inn = np.minimum(np.maximum(np.maximum(qx, qy), qz), 0)
    return out + inn - r


def sd_box(p, lo, hi):
    c = [(a + b) / 2 for a, b in zip(lo, hi)]
    h = [(b - a) / 2 for a, b in zip(lo, hi)]
    return sd_round_box(p, c, h, 0.0)


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


def sd_rrect_prism(p, hx, hy, r, z0, z1, edge):
    """Box with vertical corners of radius r and all top/bottom edges rounded by `edge`."""
    qx = np.abs(p[:, 0]) - (hx - r)
    qy = np.abs(p[:, 1]) - (hy - r)
    d2 = length2(np.maximum(qx, 0), np.maximum(qy, 0)) + np.minimum(np.maximum(qx, qy), 0) - r
    dz = np.abs(p[:, 2] - (z0 + z1) / 2) - (z1 - z0) / 2
    return round_intersect(d2, dz, edge)


def sd_capsules(p, pts, r):
    d = None
    for a, b in zip(pts[:-1], pts[1:]):
        ba = b - a
        pa = p - a
        h = np.clip((pa @ ba) / (ba @ ba), 0, 1)
        dd = np.linalg.norm(pa - h[:, None] * ba, axis=1) - r
        d = dd if d is None else np.minimum(d, dd)
    return d


def round_intersect(a, b, r):
    ua, ub = np.maximum(r + a, 0), np.maximum(r + b, 0)
    return np.minimum(-r, np.maximum(a, b)) + np.sqrt(ua * ua + ub * ub)


def body_sdf(p):
    d = sd_rrect_prism(p, HW, HL, R_CORNER, Z0, ZT, 1.2)
    # LCD window through the top (the module sits under it)
    win = sd_round_box(p, (LCD_C[0], LCD_C[1], ZT), (WIN_HALF[0], WIN_HALF[1], 3.0), 0.8)
    d = np.maximum(d, -win)
    # vent slots
    for y in LEFT_VENTS_Y:
        d = np.maximum(d, -sd_round_box(p, (-HW, y, Z0 + 21.5), (3.0, 1.3, 9.5), 0.15))
    for y in RIGHT_VENTS_Y:
        d = np.maximum(d, -sd_round_box(p, (HW, y, Z0 + 23.5), (3.0, 1.3, 7.5), 0.15))
    # open cut-outs: back (ports) and right (power + HDMI), 8 mm deep pockets
    x0, x1, zt = BACK_CUT
    d = np.maximum(d, -sd_box(p, (x0, HL - 8.0, Z0 - 1.0), (x1, HL + 1.0, zt)))
    y0, y1, zt = RIGHT_CUT
    d = np.maximum(d, -sd_box(p, (HW - 8.0, y0, Z0 - 1.0), (HW + 1.0, y1, zt)))
    return d


def ports_sdf(p):
    """Metal shells of the Pi's connectors inside the cut-outs."""
    d = None
    for x, w, h in (ETH, USB3, USB2):
        dd = sd_box(p, (x - w / 2, PORT_FACE - 10.0, Z_PI_TOP), (x + w / 2, PORT_FACE, Z_PI_TOP + h))
        d = dd if d is None else np.minimum(d, dd)
    for y, w in [(USBC_Y, 9.0)] + [(yy, 7.0) for yy in HDMI_YS]:
        d = np.minimum(d, sd_round_box(p, (PI_RIGHT - 2.5, y, CONN_Z), (3.5, w / 2, 1.7), 0.8))
    return d


def port_holes_sdf(p):
    """Dark openings in the port faces and the back of the pockets."""
    d = sd_box(p, (-27.0, HL - 8.2, Z0), (27.0, HL - 7.6, BACK_CUT[2]))                 # pocket back
    d = np.minimum(d, sd_box(p, (HW - 8.2, -26.5, Z0), (HW - 7.6, 17.5, RIGHT_CUT[2])))  # right pocket back
    x, w, h = ETH
    d = np.minimum(d, sd_box(p, (x - 6.0, PORT_FACE - 6.0, Z_PI_TOP + 2.0), (x + 6.0, PORT_FACE + 0.3, Z_PI_TOP + 11.0)))
    for x, w, h in (USB3, USB2):
        for zc in (Z_PI_TOP + 4.0, Z_PI_TOP + 12.0):
            d = np.minimum(d, sd_box(p, (x - 6.0, PORT_FACE - 6.0, zc - 2.6), (x + 6.0, PORT_FACE + 0.3, zc + 2.6)))
    for y, w in [(USBC_Y, 9.0)] + [(yy, 7.0) for yy in HDMI_YS]:
        d = np.minimum(d, sd_box(p, (PI_RIGHT + 0.5, y - w / 2 + 1.2, CONN_Z - 0.9), (PI_RIGHT + 1.3, y + w / 2 - 1.2, CONN_Z + 0.9)))
    return d


def scene(p, want_mat=False):
    ds = [p[:, 2], body_sdf(p)]                                        # ground, body
    # metal: footswitch nut + bushing, LED bezel, encoder nuts, Pi port shells, interface jacks
    metal = sd_hex(p, (FOOT_XY[0], FOOT_XY[1], ZT), 2, 8.0, 2.6)
    metal = np.minimum(metal, sd_cyl(p, (FOOT_XY[0], FOOT_XY[1], ZT + 2.2), 2, 5.8, 9.5, 2.2))
    metal = np.minimum(metal, sd_cyl(p, (LED_XY[0], LED_XY[1], ZT), 2, 3.2, 2.0, 0.6))
    for kx, ky in KNOBS:
        metal = np.minimum(metal, sd_hex(p, (kx, ky, ZT), 2, 5.0, 1.2))
    metal = np.minimum(metal, np.maximum(ports_sdf(p), -port_holes_sdf(p) - 0.0))
    for jx in (IFACE_C[0] - 14.0, IFACE_C[0] + 8.0):
        metal = np.minimum(metal, sd_hex(p, (jx, IFACE_C[1] - IFACE_HALF[1] - 2.2, 11.0), 1, 7.0, 2.4))
    ds.append(metal)
    # knobs: pedal (black, knurled) + interface
    knob = None
    for kx, ky in KNOBS:
        ang = np.arctan2(p[:, 1] - ky, p[:, 0] - kx)
        knurl = 0.2 * np.cos(24 * ang) * (p[:, 2] < ZT + 9.5)
        kd = sd_cyl(p, (kx, ky, ZT + 1.2), 2, KNOB_R, KNOB_H, 1.4) + knurl
        knob = kd if knob is None else np.minimum(knob, kd)
    for kx, ky in IFACE_KNOBS:
        knob = np.minimum(knob, sd_cyl(p, (kx, ky, 2 * IFACE_HALF[2]), 2, 6.5, 9.0, 1.5))
    ds.append(knob)
    # LCD glass under the window
    ds.append(sd_round_box(p, (LCD_C[0], LCD_C[1], ZT - 2.6), (WIN_HALF[0] + 1.0, WIN_HALF[1] + 1.0, 0.35), 0.4))
    # LEDs: pedal + interface signal LED
    led = np.sqrt((p[:, 0] - LED_XY[0]) ** 2 + (p[:, 1] - LED_XY[1]) ** 2 + (p[:, 2] - (ZT + 1.8)) ** 2) - 1.9
    led = np.minimum(led, np.sqrt((p[:, 0] - (IFACE_C[0] - 2)) ** 2 + (p[:, 1] - (IFACE_C[1] - 18)) ** 2
                                  + (p[:, 2] - 2 * IFACE_HALF[2]) ** 2) - 1.4)
    ds.append(led)
    # dark: port openings, pocket backs, interface jack holes
    dark = port_holes_sdf(p)
    for jx in (IFACE_C[0] - 14.0, IFACE_C[0] + 8.0):
        dark = np.minimum(dark, sd_cyl(p, (jx, IFACE_C[1] - IFACE_HALF[1] - 2.6, 11.0), 1, 3.2, 1.0))
    ds.append(dark)
    # rubber feet
    feet = None
    for fx in (-HW + 7, HW - 7):
        for fy in (-HL + 8, HL - 8):
            fd = sd_cyl(p, (fx, fy, 0.0), 2, 5.0, FEET + 0.5, 1.0)
            feet = fd if feet is None else np.minimum(feet, fd)
    ds.append(feet)
    # plastic plugs + boot drive
    plastic = sd_round_box(p, (USB3[0], PORT_FACE + 9.0, Z_PI_TOP + 4.0), (6.2, 9.5, 2.6), 1.0)      # USB stick
    plastic = np.minimum(plastic, sd_round_box(p, (USB2[0], PORT_FACE + 8.0, Z_PI_TOP + 12.0 - 8.0),  # USB-A plug (lower port)
                                                (6.8, 8.5, 3.6), 1.4))
    plastic = np.minimum(plastic, sd_round_box(p, (HW + 5.0, USBC_Y, CONN_Z), (9.0, 4.6, 3.0), 1.4))  # USB-C plug
    plastic = np.minimum(plastic, sd_round_box(p, (IFACE_C[0] - IFACE_HALF[0] - 7.0, IFACE_C[1] - 8.0, 12.0),
                                               (7.0, 5.0, 3.2), 1.2))                                   # USB-B at interface
    plastic = np.minimum(plastic, sd_cyl(p, (IFACE_C[0] - 14.0, IFACE_C[1] - IFACE_HALF[1] - 18.0, 11.0), 1, 4.6, 15.5, 1.0))  # 1/4" plug
    ds.append(plastic)
    # cables
    cab = None
    for pts, r in CABLES:
        cd = sd_capsules(p, pts, r)
        cab = cd if cab is None else np.minimum(cab, cd)
    ds.append(cab)
    # interface body
    ds.append(sd_round_box(p, (IFACE_C[0], IFACE_C[1], IFACE_HALF[2]), IFACE_HALF, 4.0))
    # blue tongue of the USB 3 port (visible in the upper slot)
    ds.append(sd_box(p, (USB3[0] - 5.0, PORT_FACE - 5.0, Z_PI_TOP + 11.2), (USB3[0] + 5.0, PORT_FACE - 0.4, Z_PI_TOP + 12.4)))
    D = np.stack(ds, axis=1)
    d = D.min(axis=1)
    if want_mat:
        return d, np.array(MATS)[D.argmin(axis=1)]
    return d


# ---------------------------------------------------------------- textures
TEX_PX = 14


def make_top_texture():
    w, h = int(W * TEX_PX), int(L * TEX_PX)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)

    def xy(x, y):  # mm -> px; image top = back edge
        return (x + HW) * TEX_PX, (HL - y) * TEX_PX

    cream = CREAM + (255,)
    f_num = font("SemiBold", int(3.0 * TEX_PX))
    for i, (kx, ky) in enumerate(KNOBS):
        r = 8.4 * TEX_PX
        cx, cy = xy(kx, ky)
        for a in np.linspace(np.radians(-225), np.radians(45), 9):
            x0, y0 = cx + r * np.cos(a), cy + r * np.sin(a)
            x1, y1 = cx + (r + 1.2 * TEX_PX) * np.cos(a), cy + (r + 1.2 * TEX_PX) * np.sin(a)
            dr.line((x0, y0, x1, y1), fill=CREAM + (150,), width=int(0.4 * TEX_PX))
        side = -1 if kx < 0 else 1
        tx, ty = xy(kx + side * 12.3, ky)
        dr.text((tx, ty), str(i + 1), font=f_num, fill=cream, anchor="mm")
    cx, cy = xy(*FOOT_XY)
    r = 9.6 * TEX_PX
    dr.ellipse((cx - r, cy - r, cx + r, cy + r), outline=CREAM + (120,), width=int(0.4 * TEX_PX))
    f_s = font("Medium", int(2.2 * TEX_PX))
    tx, ty = xy(-16.5, -45.0)
    dr.text((tx, ty), "BYPASS", font=f_s, fill=CREAM + (170,), anchor="mm")
    tx, ty = xy(16.5, -45.0)
    dr.text((tx, ty), "HOLD:", font=f_s, fill=CREAM + (130,), anchor="mm")
    tx, ty = xy(16.5, -48.0)
    dr.text((tx, ty), "TUNER", font=f_s, fill=CREAM + (170,), anchor="mm")
    m = 2.2 * TEX_PX
    dr.rounded_rectangle((m, m, w - m, h - m), radius=int(2.5 * TEX_PX), outline=CREAM + (90,), width=int(0.3 * TEX_PX))
    return np.asarray(img.filter(ImageFilter.GaussianBlur(0.6))).astype(F) / 255


def make_front_texture():
    w, h = int(W * TEX_PX), int(H * TEX_PX)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    dr.text((w / 2, h * 0.42), "MELON", font=font("Bold", int(8.5 * TEX_PX)), fill=CREAM + (255,), anchor="mm")
    dr.text((w / 2, h * 0.70), "P O C   ·   L V 2   ·   U S B", font=font("Medium", int(2.4 * TEX_PX)),
            fill=CREAM + (200,), anchor="mm")
    return np.asarray(img.filter(ImageFilter.GaussianBlur(0.6))).astype(F) / 255


def make_side_texture():
    w, h = int(L * TEX_PX), int(H * TEX_PX)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    f = font("SemiBold", int(2.6 * TEX_PX))
    y0, y1, zt = RIGHT_CUT
    dr.text((((y0 + y1) / 2 + HL) * TEX_PX, (ZT - (zt + 4.5)) * TEX_PX), "5V  USB-C", font=f, fill=LABEL + (220,), anchor="mm")
    return np.asarray(img.filter(ImageFilter.GaussianBlur(0.6))).astype(F) / 255


def make_back_texture():
    w, h = int(W * TEX_PX), int(H * TEX_PX)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    f = font("SemiBold", int(2.6 * TEX_PX))
    dr.text((w / 2, (ZT - (BACK_CUT[2] + 5.0)) * TEX_PX), "USB AUDIO  ·  BOOT DRIVE", font=f,
            fill=LABEL + (220,), anchor="mm")
    return np.asarray(img.filter(ImageFilter.GaussianBlur(0.6))).astype(F) / 255


def make_iface_texture():
    w, h = int(2 * IFACE_HALF[0] * TEX_PX), int(2 * IFACE_HALF[1] * TEX_PX)
    img = Image.new("RGBA", (w, h), (0, 0, 0, 0))
    dr = ImageDraw.Draw(img)
    f = font("Medium", int(2.4 * TEX_PX))
    for (kx, ky), t in zip(IFACE_KNOBS, ("GAIN", "OUTPUT")):
        px, py = (kx - (IFACE_C[0] - IFACE_HALF[0])) * TEX_PX, ((IFACE_C[1] + IFACE_HALF[1]) - (ky - 10.5)) * TEX_PX
        dr.text((px, py), t, font=f, fill=(200, 200, 205, 200), anchor="mm")
    dr.text((w * 0.5, h * 0.12), "USB AUDIO INTERFACE", font=font("SemiBold", int(2.6 * TEX_PX)),
            fill=(220, 220, 225, 210), anchor="mm")
    return np.asarray(img.filter(ImageFilter.GaussianBlur(0.6))).astype(F) / 255


def make_screen_texture():
    if os.path.exists(SCREEN_IMG):
        return np.asarray(Image.open(SCREEN_IMG).convert("RGB")).astype(F) / 255
    img = Image.new("RGB", (320, 240), (13, 22, 16))
    ImageDraw.Draw(img).text((160, 120), "Melon Pedal", font=font("Bold", 34), fill=(166, 224, 122), anchor="mm")
    return np.asarray(img).astype(F) / 255


TOP_TEX = make_top_texture()
FRONT_TEX = make_front_texture()
SIDE_TEX = make_side_texture()
BACK_TEX = make_back_texture()
IFACE_TEX = make_iface_texture()
SCREEN_TEX = make_screen_texture()


def sample(tex, u, v):
    th, tw = tex.shape[:2]
    xi = np.clip((u * (tw - 1)).astype(np.int32), 0, tw - 1)
    yi = np.clip((v * (th - 1)).astype(np.int32), 0, th - 1)
    return tex[yi, xi]


# ---------------------------------------------------------------- rendering
BB_MIN = np.array([-HW - 6, -HL - 6, 0.0], F)
BB_MAX = np.array([HW + 6, HL + 6, ZT + 16], F)
# second box: interface + cables
BB2_MIN = np.array([-HW - 6, -230.0, 0.0], F)
BB2_MAX = np.array([HW + 200.0, IFACE_C[1] + IFACE_HALF[1] + 6, 2 * IFACE_HALF[2] + 12], F)


def ray_box(ro, rd, lo=None, hi=None):
    lo = np.minimum(BB_MIN, BB2_MIN) if lo is None else lo
    hi = np.maximum(BB_MAX, BB2_MAX) if hi is None else hi
    inv = 1.0 / np.where(np.abs(rd) < 1e-8, 1e-8, rd)
    t0 = (lo - ro) * inv
    t1 = (hi - ro) * inv
    tmin = np.minimum(t0, t1).max(axis=1)
    tmax = np.maximum(t0, t1).min(axis=1)
    return np.maximum(tmin, 0), tmax


def march(ro, rd, max_steps=260):
    n = ro.shape[0]
    t_near, t_far = ray_box(ro, rd)
    inside = t_far > t_near
    t_ground = np.where(rd[:, 2] < -1e-6, -ro[:, 2] / np.where(rd[:, 2] < -1e-6, rd[:, 2], -1), np.inf).astype(F)
    t = np.where(inside, t_near, t_ground).astype(F)
    hit = np.zeros(n, bool)
    active = np.where(inside)[0]
    for _ in range(max_steps):
        if active.size == 0:
            break
        p = ro[active] + rd[active] * t[active, None]
        d = scene(p)
        t[active] += d * 0.85
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
    for _ in range(72):
        if active.size == 0:
            break
        q = p[active] + ld * t[active, None]
        d = scene(q)
        dd = np.where(q[:, 2] < 0.05, 1e3, d)
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
    box = np.exp(-((rd[:, 0] + 0.45) ** 2 + (rd[:, 1] + 0.35) ** 2) * 9.0) * (rd[:, 2] > 0.3)
    return col + 1.2 * box[:, None]


def env_refl(rd):
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
    base[b] = (np.array([0x1E, 0x3A, 0x2B], F) / 255) ** 2.2 * 0.85      # brand deep green #1E3A2B
    spec_k[b] = 0.30
    gloss[b] = 50
    refl[b] = 0.05
    pb, nb = p[b], nrm[b]
    gfx = np.zeros((pb.shape[0], 4), F)
    top = nb[:, 2] > 0.7
    if top.any():
        gfx[top] = sample(TOP_TEX, (pb[top, 0] + HW) / W, (HL - pb[top, 1]) / L)
    front = nb[:, 1] < -0.7
    if front.any():
        gfx[front] = sample(FRONT_TEX, (pb[front, 0] + HW) / W, (ZT - pb[front, 2]) / H)
    back = (nb[:, 1] > 0.7) & (pb[:, 1] > HL - 0.5)
    if back.any():
        gfx[back] = sample(BACK_TEX, (HW - pb[back, 0]) / W, (ZT - pb[back, 2]) / H)
    side = (nb[:, 0] > 0.7) & (pb[:, 0] > HW - 0.5)
    if side.any():
        gfx[side] = sample(SIDE_TEX, (pb[side, 1] + HL) / L, (ZT - pb[side, 2]) / H)
    a = gfx[:, 3:4]
    base[b] = base[b] * (1 - a) + gfx[:, :3] ** 2.2 * a
    # faint 3D-print layer lines on the walls
    walls = np.abs(nb[:, 2]) < 0.3
    lines = 0.93 + 0.07 * (np.sin(pb[:, 2] * 2 * np.pi / 0.2) > 0)
    bi = np.where(b)[0]
    base[bi[walls]] *= lines[walls, None]

    m = mat == M_METAL
    base[m] = np.array([0.20, 0.20, 0.21], F)
    spec_k[m] = 0.9
    gloss[m] = 120
    refl[m] = 0.7

    k = mat == M_KNOB
    pk = p[k]
    base[k] = np.array([0.025, 0.025, 0.028], F)
    spec_k[k] = 0.45
    gloss[k] = 40
    refl[k] = 0.08
    topk = nrm[k, 2] > 0.85
    capc = np.zeros(pk.shape[0], bool)
    ptr = np.zeros(pk.shape[0], bool)
    for i, (kx, ky) in enumerate(KNOBS + IFACE_KNOBS):
        dx, dy = pk[:, 0] - kx, pk[:, 1] - ky
        rr = np.sqrt(dx * dx + dy * dy)
        near = rr < 7
        capc |= near & topk & (rr < 4.2)
        ang = np.radians([-40, 25, 70, 140, 120, 60][i])
        along = dx * np.cos(ang) + dy * np.sin(ang)
        perp = -dx * np.sin(ang) + dy * np.cos(ang)
        ptr |= near & topk & (np.abs(perp) < 0.4) & (along > 1.2) & (along < 5.6)
    ki = np.where(k)[0]
    base[ki[capc]] = (0.30, 0.31, 0.33)
    refl[ki[capc]] = 0.35
    spec_k[ki[capc]] = 0.8
    base[ki[ptr]] = (0.85, 0.83, 0.78)

    gl = mat == M_GLASS
    pg = p[gl]
    u = (pg[:, 0] - (LCD_C[0] - GLASS_HALF[0])) / (2 * GLASS_HALF[0])
    vv = ((LCD_C[1] + GLASS_HALF[1]) - pg[:, 1]) / (2 * GLASS_HALF[1])
    scr = sample(SCREEN_TEX, np.clip(u, 0, 1), np.clip(vv, 0, 1)) ** 2.2
    on = ((u > 0) & (u < 1) & (vv > 0) & (vv < 1))[:, None]
    emis[gl] = scr * 2.0 * on
    base[gl] = 0.01
    spec_k[gl] = 1.0
    gloss[gl] = 300
    refl[gl] = 0.10

    led = mat == M_LED
    base[led] = (0.05, 0.4, 0.05)
    emis[led] = (0.6, 3.2, 0.5)          # green: effect on
    spec_k[led] = 1.0
    gloss[led] = 200

    base[mat == M_DARK] = 0.008
    base[mat == M_RUBBER] = 0.02
    pl = mat == M_PLASTIC
    base[pl] = (0.035, 0.035, 0.04)
    spec_k[pl] = 0.5
    gloss[pl] = 60
    refl[pl] = 0.12
    cb = mat == M_CABLE
    base[cb] = (0.03, 0.03, 0.033)
    spec_k[cb] = 0.25
    gloss[cb] = 25
    ifc = mat == M_IFACE
    base[ifc] = (0.022, 0.022, 0.025)
    spec_k[ifc] = 0.5
    gloss[ifc] = 70
    refl[ifc] = 0.15
    pi_ = p[ifc]
    topi = nrm[ifc, 2] > 0.7
    if topi.any():
        gi = sample(IFACE_TEX, (pi_[topi, 0] - (IFACE_C[0] - IFACE_HALF[0])) / (2 * IFACE_HALF[0]),
                    ((IFACE_C[1] + IFACE_HALF[1]) - pi_[topi, 1]) / (2 * IFACE_HALF[1]))
        ii = np.where(ifc)[0][topi]
        base[ii] = base[ii] * (1 - gi[:, 3:4]) + gi[:, :3] ** 2.2 * gi[:, 3:4]
    bl = mat == M_BLUE
    base[bl] = (0.02, 0.10, 0.55)

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
    rdir = rd[idx] - 2 * (rd[idx] * nrm).sum(1, keepdims=True) * nrm
    cosv = np.clip((nrm * v).sum(1), 0, 1)
    fres = refl + (1 - refl) * (1 - cosv) ** 5 * (refl > 0) * 0.6
    env = env_refl(rdir) * (0.35 + 0.65 * ao)[:, None]
    lit = lit * (1 - fres[:, None] * 0.5) + env * fres[:, None] * np.where(mat == M_METAL, 1.0, 0.6)[:, None]
    lit += emis
    gi = np.where(g)[0]
    if gi.size:
        dist = np.sqrt(p[g, 0] ** 2 + p[g, 1] ** 2)
        fade = np.clip((dist - 200) / 240, 0, 1)[:, None]
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


def render(name, res, ss, eye, target, fov, chunk=150_000):
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


VIEWS = {
    "render-poc-hero.png": dict(eye=(150, -240, 175), target=(18, 5, 20), fov=34),
    "render-poc-back.png": dict(eye=(-120, 230, 120), target=(25, 35, 18), fov=36),
    "render-poc-top.png": dict(eye=(0, -40, 300), target=(0, -2, 40), fov=29),
}

if __name__ == "__main__":
    ap = argparse.ArgumentParser()
    ap.add_argument("--res", default="1600x1000")
    ap.add_argument("--ss", type=int, default=2)
    ap.add_argument("--only", default="")
    a = ap.parse_args()
    res = tuple(int(x) for x in a.res.split("x"))
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, v in VIEWS.items():
        if a.only and a.only not in name:
            continue
        render(name, res, a.ss, **v)

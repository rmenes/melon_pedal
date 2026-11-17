import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.collections import PolyCollection
from matplotlib.colors import to_rgb

W, L = 100, 135  # x width, y length (0 front, L back), z height
BODY, LID, DARK, METAL = "#3d6b4f", "#4f8a63", "#1c1c1c", "#b8b8b8"

UP, BACK, SIDE = np.array([0, 0, 1.]), np.array([0, 1., 0]), np.array([1., 0, 0])

# each item: dict(polys=[(verts(Nx3), color)], center, mount=normal of host face or None)
items = []


def box(x0, y0, z0, dx, dy, dz, color, mount=None, edge=True):
    x1, y1, z1 = x0 + dx, y0 + dy, z0 + dz
    v = np.array([[x0, y0, z0], [x1, y0, z0], [x1, y1, z0], [x0, y1, z0],
                  [x0, y0, z1], [x1, y0, z1], [x1, y1, z1], [x0, y1, z1]], float)
    f = [[0, 1, 2, 3], [4, 5, 6, 7], [0, 1, 5, 4], [2, 3, 7, 6], [1, 2, 6, 5], [0, 3, 7, 4]]
    items.append(dict(polys=[(v[i], color) for i in f], center=v.mean(0), mount=mount, edge=edge))


def cyl(c, axis, r, h, color, mount, n=36, edge=True):
    c = np.array(c, float); a = np.array(axis, float)
    u = np.cross(a, [1, 0, 0] if abs(a[0]) < 0.9 else [0, 1, 0]); u /= np.linalg.norm(u)
    w = np.cross(a, u)
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ring0 = np.array([c + r * (np.cos(q) * u + np.sin(q) * w) for q in t])
    ring1 = ring0 + a * h
    polys = []
    for i in range(n):
        j = (i + 1) % n
        polys.append((np.array([ring0[i], ring0[j], ring1[j], ring1[i]]), color))
    polys.append((ring1, color)); polys.append((ring0[::-1], color))
    items.append(dict(polys=polys, center=c + a * h / 2, mount=mount, edge=edge))


def disk(c, axis, r, color, mount, n=36):
    c = np.array(c, float); a = np.array(axis, float)
    u = np.cross(a, [1, 0, 0] if abs(a[0]) < 0.9 else [0, 1, 0]); u /= np.linalg.norm(u)
    w = np.cross(a, u)
    t = np.linspace(0, 2 * np.pi, n, endpoint=False)
    ring = np.array([c + r * (np.cos(q) * u + np.sin(q) * w) for q in t])
    items.append(dict(polys=[(ring, color)], center=c, mount=mount, edge=False, flat=a))


def build(H, KH):
    items.clear()
    top = H
    # ---------- model ----------
    top = H
    box(0, 0, 0, W, L, H - 4, BODY)                       # body
    box(0, 0, H - 4, W, L, 4, LID)                       # lid
    cyl((50, 20, top), UP, 8, 3, METAL, UP)               # footswitch nut
    cyl((50, 20, top + 3), UP, 5.5, 9, "#dcdcdc", UP)     # footswitch cap
    cyl((50, 38, top), UP, 2.4, 2.5, "#ff3b30", UP)       # LED
    box(29, 66, top, 42, 33, 1.0, DARK, UP)               # LCD bezel
    box(32, 69.5, top + 1.0, 36, 26, 0.3, "#2f6fd6", UP, edge=False)  # LCD screen
    for (x, y) in [(18, 60), (82, 60), (18, 105), (82, 105)]:
        cyl((x, y, top), UP, 8.5, 1.5, METAL, UP)
        cyl((x, y, top + 1.5), UP, 7, KH, DARK, UP)
        box(x - 0.6, y - 6.5, top + 1.5 + KH, 1.2, 5, 0.3, "#ffffff", UP, edge=False)  # pointer
    jz = 17
    for x, r_nut, r_hole in [(14, 7, 3.3), (34, 5, 3.0), (51, 4, 1.9), (66, 4, 1.9), (86, 7, 3.3)]:
        cyl((x, L, jz), BACK, r_nut, 2.5, METAL, BACK)
        disk((x, L + 2.6, jz), BACK, r_hole, DARK, BACK)
    for z in range(12, H - 18, 6):
        box(W, 45, z, 0.4, 55, 2.2, DARK, SIDE, edge=False)  # vents on right side
    for (x, y) in [(8, 8), (92, 8), (8, 127), (92, 127)]:
        cyl((x, y, -3), UP, 5, 3, "#111111", -UP)
    
    

# ---------- renderer ----------
def render(ax, elev, azim, labels=()):
    el, az = np.radians(elev), np.radians(azim)
    cam = np.array([np.cos(el) * np.cos(az), np.cos(el) * np.sin(az), np.sin(el)])  # towards viewer
    right = np.cross([0, 0, 1], cam); right /= np.linalg.norm(right)
    upv = np.cross(cam, right)
    light = np.array([0.4, -0.5, 0.9]); light /= np.linalg.norm(light)

    def proj(p):
        return np.c_[p @ right, p @ upv]

    order = sorted(range(len(items)), key=lambda i: (0 if i < 2 else 1, items[i]["center"] @ cam))
    polys2d, cols, edges = [], [], []
    for i in order:
        it = items[i]
        if it["mount"] is not None and it["mount"] @ cam <= 0:
            continue  # host face hidden
        ctr = it["center"]
        faces = []
        for v, col in it["polys"]:
            n = np.cross(v[1] - v[0], v[2] - v[0])
            if np.linalg.norm(n) < 1e-9:
                continue
            n /= np.linalg.norm(n)
            if n @ (v.mean(0) - ctr) < 0:
                n = -n
            if "flat" in it:
                n = it["flat"]
            if n @ cam <= 0:
                continue
            shade = 0.45 + 0.55 * max(0, n @ light)
            rgb = np.clip(np.array(to_rgb(col)) * shade, 0, 1)
            faces.append((v.mean(0) @ cam, proj(v), rgb))
        faces.sort(key=lambda f: f[0])
        for _, p2, rgb in faces:
            polys2d.append(p2); cols.append(rgb)
            edges.append("#151515" if it["edge"] else rgb)
    ax.add_collection(PolyCollection(polys2d, facecolors=cols, edgecolors=edges, linewidths=0.35))
    for pos, s in labels:
        p = proj(np.array([pos], float))[0]
        ax.annotate(s, p, fontsize=8, ha="center", va="bottom", color="#111",
                    bbox=dict(boxstyle="round,pad=0.2", fc="white", ec="#888", lw=0.5, alpha=0.9))
    ax.set_aspect("equal"); ax.autoscale_view(); ax.margins(0.08); ax.axis("off")



fig, (a1, a2) = plt.subplots(1, 2, figsize=(14, 7), dpi=150)
build(65, 15); render(a1, 20, -62)
a1.set_title("Current plan: 65 mm body + tall knobs = ~82 mm", fontsize=12)
build(47, 10); render(a2, 20, -62)
a2.set_title("Slim version: 47 mm body + low knobs = ~58 mm (Boss ~59 mm)", fontsize=12)
xl = (min(a1.get_xlim()[0], a2.get_xlim()[0]), max(a1.get_xlim()[1], a2.get_xlim()[1]))
yl = (min(a1.get_ylim()[0], a2.get_ylim()[0]), max(a1.get_ylim()[1], a2.get_ylim()[1]))
for a in (a1, a2): a.set_xlim(xl); a.set_ylim(yl)
fig.suptitle("Melon Effects Pedal: height comparison (same scale)", fontsize=14)
plt.tight_layout()
plt.savefig("docs/images/height-comparison.png", bbox_inches="tight", facecolor="white")
print("ok")

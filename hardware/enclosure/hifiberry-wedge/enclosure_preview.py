"""Preview images for make_enclosure.py: shaded views and slicer-style cross-sections.

Cross-sections are cut the way a slicer does it: every shell is cut by the
plane, the cut loops are filled (even-odd per shell) and all shells are drawn
on top of each other, which shows the merged solid. The side sections also
show the approximate envelopes of the parts inside (Pi, HiFiBerry, encoders...).
"""
import os

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.path import Path as MplPath
from matplotlib.patches import PathPatch, Polygon, Rectangle

import make_enclosure as me

TRAY_COL = np.array([0x1E, 0x3A, 0x2B]) / 255     # brand deep green
LID_COL = np.array([0x4C, 0xB3, 0x5A]) / 255      # brand rind green (only to tell the parts apart)


def cut_loops(verts, faces, axis, value):
    """Loops (list of (N,2) arrays) where plane coord[axis] == value cuts a closed shell."""
    other = [i for i in range(3) if i != axis]
    s = verts[:, axis] - value
    s = np.where(np.abs(s) < 1e-9, 1e-9, s)
    pos = s > 0
    nxt, pts = {}, {}
    for f in faces[(pos[faces].sum(axis=1) % 3) != 0]:
        k_in = k_out = None
        for a, b in ((f[0], f[1]), (f[1], f[2]), (f[2], f[0])):
            if pos[a] != pos[b]:
                k = (min(a, b), max(a, b))
                if k not in pts:
                    t = s[a] / (s[a] - s[b])
                    pts[k] = verts[a] + t * (verts[b] - verts[a])
                if pos[b]:
                    k_in = k
                else:
                    k_out = k
        nxt[k_in] = k_out
    loops, seen = [], set()
    for start in nxt:
        if start in seen:
            continue
        loop, k = [], start
        while k not in seen and k in nxt:
            seen.add(k)
            loop.append(pts[k][other])
            k = nxt[k]
        if len(loop) >= 3:
            loops.append(np.array(loop))
    return loops


def to_lid_frame(v):
    """World -> lid sketch coordinates (a, b, d)."""
    q = v - me.LID.o
    return np.c_[q @ me.LID.u, q @ me.LID.v, q @ me.LID.n]


def draw_cut(ax, part, axis, value, col, frame_fn=None):
    for v, f in part.shells:
        vv = frame_fn(v) if frame_fn else v
        loops = cut_loops(vv, f, axis, value)
        if not loops:
            continue
        verts = np.vstack([np.vstack([lp, lp[:1]]) for lp in loops])
        codes = np.concatenate([[MplPath.MOVETO] + [MplPath.LINETO] * (len(lp) - 1) + [MplPath.CLOSEPOLY]
                                for lp in loops])
        ax.add_patch(PathPatch(MplPath(verts, codes), facecolor=col, edgecolor="none"))


def draw_parts_x(ax, x):
    """Envelopes of the internal parts cut by the plane x = const, drawn in (y, z)."""
    for name, (x0, x1, y0, y1, z0, z1) in me.FLOOR_PARTS.items():
        if x0 < x < x1:
            ax.add_patch(Rectangle((y0, z0), y1 - y0, z1 - z0, fc=(1, 0.65, 0.2, 0.35), ec=(0.8, 0.4, 0), lw=0.8))
            ax.text((y0 + y1) / 2, (z0 + z1) / 2, name.split(" (")[0], fontsize=6, ha="center", va="center")
    for name, (px, py, sa, sb, depth) in me.LID_PARTS.items():
        if abs(x - px) < sa / 2:
            c = me.lid_part_box(name)
            quad = np.array([c[0], c[1], c[5], c[4]])[:, 1:]
            ax.add_patch(Polygon(quad, closed=True, fc=(0.2, 0.5, 1, 0.3), ec=(0.1, 0.3, 0.8), lw=0.8))
            ctr = quad.mean(axis=0)
            ax.text(ctr[0], ctr[1], name, fontsize=6, ha="center", va="center")


def finish(ax, title):
    ax.set_title(title, fontsize=9)
    ax.set_aspect("equal")
    ax.autoscale_view()
    ax.tick_params(labelsize=7)
    ax.grid(alpha=0.25, lw=0.5)


def shade(parts, colors, view_dir, up, size=(900, 700), light=(0.4, -0.5, 0.8), offsets=None):
    """Tiny z-buffer rasteriser (orthographic)."""
    d = np.asarray(view_dir, float)
    d /= np.linalg.norm(d)
    r = np.cross(d, up)
    r /= np.linalg.norm(r)
    u = np.cross(r, d)
    lt = np.asarray(light, float)
    lt /= np.linalg.norm(lt)
    tris, cols = [], []
    for i, (part, col) in enumerate(zip(parts, colors)):
        t = part.triangles()
        if offsets is not None:
            t = t + offsets[i]
        tris.append(t)
        cols.append(np.tile(col, (len(t), 1)))
    tris, cols = np.vstack(tris), np.vstack(cols)
    n = np.cross(tris[:, 1] - tris[:, 0], tris[:, 2] - tris[:, 0])
    n /= np.linalg.norm(n, axis=1, keepdims=True) + 1e-20
    vis = n @ d < 0
    tris, cols, n = tris[vis], cols[vis], n[vis]
    lum = 0.35 + 0.65 * np.clip(n @ lt, 0, 1)
    sx, sy, sz = tris @ r, tris @ u, tris @ (-d)
    W, H = size
    x0, x1, y0, y1 = sx.min(), sx.max(), sy.min(), sy.max()
    sc = 0.9 * min(W / (x1 - x0), H / (y1 - y0))
    px = (sx - (x0 + x1) / 2) * sc + W / 2
    py = H / 2 - (sy - (y0 + y1) / 2) * sc
    img = np.ones((H, W, 3)) * 0.96
    zb = np.full((H, W), -np.inf)
    for i in range(len(tris)):
        xa, ya, za = px[i], py[i], sz[i]
        bx0, bx1 = int(max(0, np.floor(xa.min()))), int(min(W - 1, np.ceil(xa.max())))
        by0, by1 = int(max(0, np.floor(ya.min()))), int(min(H - 1, np.ceil(ya.max())))
        if bx1 < bx0 or by1 < by0:
            continue
        den = (ya[1] - ya[2]) * (xa[0] - xa[2]) + (xa[2] - xa[1]) * (ya[0] - ya[2])
        if abs(den) < 1e-12:
            continue
        gx, gy = np.meshgrid(np.arange(bx0, bx1 + 1) + 0.5, np.arange(by0, by1 + 1) + 0.5)
        w0 = ((ya[1] - ya[2]) * (gx - xa[2]) + (xa[2] - xa[1]) * (gy - ya[2])) / den
        w1 = ((ya[2] - ya[0]) * (gx - xa[2]) + (xa[0] - xa[2]) * (gy - ya[2])) / den
        w2 = 1 - w0 - w1
        m = (w0 >= -1e-6) & (w1 >= -1e-6) & (w2 >= -1e-6)
        if not m.any():
            continue
        z = w0 * za[0] + w1 * za[1] + w2 * za[2]
        sub = zb[by0:by1 + 1, bx0:bx1 + 1]
        m &= z > sub
        sub[m] = z[m]
        img[by0:by1 + 1, bx0:bx1 + 1][m] = cols[i] * lum[i] + (1 - cols[i]) * 0.12 * lum[i]
    return img


def write_previews(parts, out_dir):
    tray, lid = parts
    tcol, lcol = TRAY_COL * 1.9, np.clip(TRAY_COL * 2.6, 0, 1)
    lift = me.LID.n * 30                      # exploded view: lid lifted along its normal
    views = [
        ("Assembled, from front-right", [tray, lid], (-0.55, 0.75, -0.55), (0, 0, 1), None),
        ("Exploded: lid lifted off the tray", [tray, lid], (-0.6, 0.7, -0.45), (0, 0, 1), [0 * lift, lift]),
        ("Back (jacks), from behind", [tray, lid], (-0.35, -0.9, -0.3), (0, 0, 1), None),
        ("Tray from above (Pi + I/O standoffs)", [tray], (0.2, 0.45, -0.85), (0, 1, 0), None),
        ("Lid underside (encoder + LCD pockets)", [lid], (0.15, 0.35, 0.9), (0, 1, 0), None),
        ("Right side (USB cut-out)", [tray, lid], (-0.95, 0.15, -0.25), (0, 0, 1), None),
    ]
    fig, axs = plt.subplots(2, 3, figsize=(15, 9.4))
    for ax, (title, ps, d, up, off) in zip(axs.flat, views):
        cols = [tcol if p is tray else lcol for p in ps]
        ax.imshow(shade(ps, cols, d, up, size=(800, 600), offsets=off))
        ax.set_title(title, fontsize=10)
        ax.axis("off")
    fig.tight_layout()
    p1 = os.path.join(out_dir, "preview-3d.png")
    fig.savefig(p1, dpi=110)
    plt.close(fig)

    fig, axs = plt.subplots(3, 3, figsize=(16, 13.5))
    axs = axs.flat
    # side sections with the parts inside
    for ax, x, title in ((axs[0], -30.0, "x = -30: knobs 1 + 3, Pi + HiFiBerry"),
                         (axs[1], 30.0, "x = +30: knobs 2 + 4, Pi USB ports, HAT jacks"),
                         (axs[2], 0.0, "x = 0: footswitch, LED, LCD")):
        draw_cut(ax, tray, 0, x, TRAY_COL)
        draw_cut(ax, lid, 0, x, LID_COL)
        draw_parts_x(ax, x)
        finish(ax, title)
    # lid sketch-plane sections (seen from above, along the slope)
    for ax, dep, title in ((axs[3], 0.3, "lid, 0.3 below top: engraving, bezel, screw heads"),
                           (axs[4], 1.8, "lid, 1.8 below top: LCD window, screws"),
                           (axs[5], 2.5, "lid, 2.5 below top: encoder pockets")):
        draw_cut(ax, lid, 2, -dep, LID_COL, frame_fn=to_lid_frame)
        finish(ax, title)
    draw_cut(axs[6], tray, 2, me.FLOOR + 2.0, TRAY_COL)
    finish(axs[6], f"z = {me.FLOOR + 2:.0f}: walls, bosses, standoffs, floor vents below")
    draw_cut(axs[7], tray, 1, me.HL - 1.0, TRAY_COL)
    axs[7].invert_xaxis()
    finish(axs[7], "back wall (seen from behind): jacks, pockets")
    draw_cut(axs[8], tray, 0, me.HW - 1.5, TRAY_COL)
    finish(axs[8], "right wall: USB cut-out, sloped top edge")
    fig.tight_layout()
    p2 = os.path.join(out_dir, "preview-sections.png")
    fig.savefig(p2, dpi=100)
    plt.close(fig)
    print("previews:", p1, p2)

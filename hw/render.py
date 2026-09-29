#!/usr/bin/env python3
"""Tiny software renderer: previews without a GPU or a display.

Face colours come from the mesh itself (mesh.visual.face_colors).
"""
import sys
import numpy as np
import trimesh
from PIL import Image

W, H = 1400, 1000
BG = np.array([245, 246, 248], float)
LIGHT = np.array([0.45, -0.35, 0.82])
LIGHT /= np.linalg.norm(LIGHT)


def rot(elev, azim):
    a, e = np.radians(azim), np.radians(elev)
    rz = np.array([[np.cos(a), -np.sin(a), 0], [np.sin(a), np.cos(a), 0], [0, 0, 1]])
    rx = np.array([[1, 0, 0], [0, np.cos(e), -np.sin(e)], [0, np.sin(e), np.cos(e)]])
    return rx @ rz


def render(mesh, elev=28.0, azim=-50.0, base=(0.29, 0.55, 0.72), face_colors=None):
    if face_colors is None and mesh.visual.kind == 'face':
        face_colors = mesh.visual.face_colors[:, :3] / 255.0
    R = rot(elev, azim)
    v = mesh.vertices @ R.T
    n = mesh.face_normals @ R.T
    lo, hi = v.min(0), v.max(0)
    span = max(hi[0] - lo[0], hi[2] - lo[2]) * 1.08
    s = min(W, H) / span
    px = (v[:, 0] - (lo[0] + hi[0]) / 2) * s + W / 2
    py = H / 2 - (v[:, 2] - (lo[2] + hi[2]) / 2) * s
    depth = v[:, 1]

    img = np.tile(BG, (H, W, 1))
    zbuf = np.full((H, W), np.inf)
    shade = np.clip(n @ LIGHT, 0, 1) * 0.72 + 0.28
    order = np.argsort(-mesh.triangles_center @ R.T @ np.array([0, 1, 0]))

    for f in order:
        i0, i1, i2 = mesh.faces[f]
        xs = np.array([px[i0], px[i1], px[i2]])
        ys = np.array([py[i0], py[i1], py[i2]])
        zs = np.array([depth[i0], depth[i1], depth[i2]])
        x0, x1 = int(max(np.floor(xs.min()), 0)), int(min(np.ceil(xs.max()) + 1, W))
        y0, y1 = int(max(np.floor(ys.min()), 0)), int(min(np.ceil(ys.max()) + 1, H))
        if x0 >= x1 or y0 >= y1:
            continue
        gx, gy = np.meshgrid(np.arange(x0, x1) + 0.5, np.arange(y0, y1) + 0.5)
        d = ((ys[1] - ys[2]) * (xs[0] - xs[2]) + (xs[2] - xs[1]) * (ys[0] - ys[2]))
        if abs(d) < 1e-9:
            continue
        w0 = ((ys[1] - ys[2]) * (gx - xs[2]) + (xs[2] - xs[1]) * (gy - ys[2])) / d
        w1 = ((ys[2] - ys[0]) * (gx - xs[2]) + (xs[0] - xs[2]) * (gy - ys[2])) / d
        w2 = 1 - w0 - w1
        inside = (w0 >= 0) & (w1 >= 0) & (w2 >= 0)
        if not inside.any():
            continue
        z = w0 * zs[0] + w1 * zs[1] + w2 * zs[2]
        sl = (slice(y0, y1), slice(x0, x1))
        win = inside & (z < zbuf[sl])
        zb = zbuf[sl]
        zb[win] = z[win]
        zbuf[sl] = zb
        col = np.array(base if face_colors is None else face_colors[f]) * shade[f] * 255
        tile = img[sl]
        tile[win] = col
        img[sl] = tile
    return Image.fromarray(img.astype(np.uint8))

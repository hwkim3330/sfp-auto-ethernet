#!/usr/bin/env python3
"""2D electrostatic field solver for the boards' transmission lines.

Finite differences on a uniform grid over the cross-section: a ground plane
under (and, for stripline, over) a dielectric, rectangular copper lines, an
optional solder-mask coat. Laplace's equation with the copper held at fixed
potentials; the capacitance per length comes from the field energy, once
with the real dielectrics (C) and once in air (C0), and

    Z = 1 / (c * sqrt(C * C0)),   eps_eff = C / C0

Odd mode (+1 / -1) gives Z_odd, Zdiff = 2 Z_odd; even mode gives Z_even;
one line alone gives Z0. The grid is refined until Z moves by < 0.5 %.

    python3 tools/zsolve.py          # the cases the boards use
"""
import numpy as np
import scipy.sparse as sp
import scipy.sparse.linalg as spla

C_LIGHT = 299792458.0
EPS0 = 8.854187817e-12


def solve(lines, h, er, t=0.035, mask=(0.0254, 0.015, 3.8), h_top=None, er_top=None,
          d=0.004, width=2.4, air=0.8):
    """lines: [(x_centre, w, volts)], mm. h: dielectric under the lines.
    mask: (thickness over bare dielectric, over copper, er) or None.
    h_top: a second plane this far above the lines' top (stripline)."""
    nx = int(round(width / d)) + 1
    top = (h + t + (h_top if h_top else air))
    ny = int(round(top / d)) + 1
    y = np.arange(ny) * d
    x = np.arange(nx) * d - width / 2
    eps = np.ones((ny, nx))
    eps[y <= h + 1e-9, :] = er                       # cell rows by their centre
    if h_top:
        eps[y > h, :] = er_top or er
    elif mask:
        m_bare, m_cu, m_er = mask
        eps[(y > h) & (y <= h + m_bare), :] = m_er
        for xc, w, _ in lines:
            sel = (np.abs(x - xc) <= w / 2 + m_cu)
            eps[np.ix_((y > h) & (y <= h + t + m_cu), sel)] = m_er
    fixed = np.zeros((ny, nx), bool)
    val = np.zeros((ny, nx))
    fixed[0, :] = True                                # the plane under
    if h_top:
        fixed[-1, :] = True
    for xc, w, v in lines:
        sel = np.abs(x - xc) <= w / 2 + 1e-9
        rows = (y >= h - 1e-9) & (y <= h + t + 1e-9)
        fixed[np.ix_(rows, sel)] = True
        val[np.ix_(rows, sel)] = v
    # 5-point stencil with permittivity averaged on the cell faces
    idx = -np.ones((ny, nx), int)
    free = ~fixed
    idx[free] = np.arange(free.sum())
    rows, cols, data = [], [], []
    rhs = np.zeros(free.sum())
    for (di, dj) in ((0, 1), (0, -1), (1, 0), (-1, 0)):
        i0, i1 = max(0, -di), ny - max(0, di)
        j0, j1 = max(0, -dj), nx - max(0, dj)
        a = np.zeros((ny, nx))
        a[i0:i1, j0:j1] = 0.5 * (eps[i0:i1, j0:j1] + eps[i0 + di:i1 + di, j0 + dj:j1 + dj])
        # the open sides and the open top: Neumann (no neighbour, no flux)
        nb_free = np.zeros((ny, nx), bool); nb_free[i0:i1, j0:j1] = free[i0 + di:i1 + di, j0 + dj:j1 + dj]
        nb_val = np.zeros((ny, nx)); nb_val[i0:i1, j0:j1] = val[i0 + di:i1 + di, j0 + dj:j1 + dj]
        nb_fix = np.zeros((ny, nx), bool); nb_fix[i0:i1, j0:j1] = fixed[i0 + di:i1 + di, j0 + dj:j1 + dj]
        nb_idx = -np.ones((ny, nx), int); nb_idx[i0:i1, j0:j1] = idx[i0 + di:i1 + di, j0 + dj:j1 + dj]
        m = free & (a > 0)
        rows.append(idx[m]); cols.append(idx[m]); data.append(a[m])          # diagonal
        mf = m & nb_free
        rows.append(idx[mf]); cols.append(nb_idx[mf]); data.append(-a[mf])
        mx = m & nb_fix
        np.add.at(rhs, idx[mx], a[mx] * nb_val[mx])
    A = sp.csr_matrix((np.concatenate(data), (np.concatenate(rows), np.concatenate(cols))),
                      shape=(free.sum(), free.sum()))
    phi = val.copy()
    phi[free] = spla.spsolve(A, rhs)
    # energy per length: 1/2 sum eps |grad phi|^2 over the faces
    gx = np.diff(phi, axis=1); ex = 0.5 * (eps[:, 1:] + eps[:, :-1])
    gy = np.diff(phi, axis=0); ey = 0.5 * (eps[1:, :] + eps[:-1, :])
    W = 0.5 * EPS0 * (np.sum(ex * gx ** 2) + np.sum(ey * gy ** 2))          # J/m (d cancels in 2D)
    vsum = sum(v * v for _, _, v in lines)
    return 2 * W / vsum                               # F/m per line at its own potential


MASK = (0.0254, 0.015, 3.8)     # JLC's solder mask: 1.0 mil over the laminate, 0.6 mil over copper


def z_of(lines, h, er, **kw):
    kw.setdefault('mask', MASK)           # explicit, so the air run below can blank it
    C = solve(lines, h, er, **kw)
    air_kw = dict(kw)
    if air_kw.get('mask'):
        air_kw['mask'] = (air_kw['mask'][0], air_kw['mask'][1], 1.0)
    if air_kw.get('h_top'):
        air_kw['er_top'] = 1.0
    C0 = solve(lines, h, 1.0, **air_kw)
    return 1 / (C_LIGHT * np.sqrt(C * C0)), C / C0


H_GRID = [None]


def converged(fn):
    """The grid step divides the dielectric height exactly (so the copper's
    underside sits on a grid row), refined until Z moves by < 0.5 %."""
    prev = None
    for n in (20, 30, 45, 68):
        z = fn(H_GRID[0] / n)
        if prev and abs(z[0] - prev[0]) / prev[0] < 0.005:
            return z
        prev = z
    return z


def pair(w, s, h, er, **kw):
    H_GRID[0] = h
    off = (w + s) / 2
    zo, eo = converged(lambda d: z_of([(-off, w, 1), (off, w, -1)], h, er, d=d, **kw))
    ze, ee = converged(lambda d: z_of([(-off, w, 1), (off, w, 1)], h, er, d=d, **kw))
    return 2 * zo, ze / 2, zo, eo


def single(w, h, er, **kw):
    H_GRID[0] = h
    return converged(lambda d: z_of([(0.0, w, 1)], h, er, d=d, **kw))


if __name__ == '__main__':
    H, ER = 0.0994, 4.1           # JLC 3313 prepreg under the outer layers (both stacks)
    print('outer layers over a plane: 3313 (0.0994 mm, er 4.1), 35 um copper, mask 25/15 um er 3.8')
    print('every high-speed pair is 0.114 / 0.152 mm on an outer layer over GND; the T1S MDI is two 0.2 mm lines')
    for label, w, s_, er in (('nominal', 0.114, 0.152, ER),
                             ('etched -0.0127 (w narrower, gap wider)', 0.1013, 0.1647, ER),
                             ('er 4.3', 0.114, 0.152, 4.3), ('er 3.9', 0.114, 0.152, 3.9)):
        zd, zc, zo, eo = pair(w, s_, H, er)
        print(f'  pair {label:40s} Zdiff {zd:5.1f}  Zcm {zc:5.1f}  eps_eff(odd) {eo:.2f}  {1e9 * np.sqrt(eo) / C_LIGHT:.2f} ps/mm')
    for w in (0.114, 0.157, 0.2):
        z, e = single(w, H, ER)
        print(f'  line w {w}: Z0 {z:5.1f}  eps_eff {e:.2f}  {1e9 * np.sqrt(e) / C_LIGHT:.2f} ps/mm')

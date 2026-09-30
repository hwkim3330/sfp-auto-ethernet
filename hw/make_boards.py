#!/usr/bin/env python3
"""SFP module PCBs, v0: outline, MSA edge connector, and part placement.

    python3 make_boards.py        (KiCad 7 pcbnew bindings)

Writes, for each variant (t1, rj45, t1s):
    <variant>/<variant>.kicad_pcb   outline + edge fingers + every part placed
    <variant>/<variant>_top.svg, _bottom.svg   previews (kicad-cli)
and, for all three:
    fp/sfp.pretty/SFP_Module_Edge.kicad_mod
    <variant>/<variant>_envelope.stl, img/envelope_<variant>.png
                                    parts against the MSA housing

v0 is mechanical: nothing is routed and no schematic exists yet. What it
settles is whether each variant's parts fit the SFP envelope, and where.

FRAME: x along the module from the edge-finger end (x = 0, the end that goes
into the host connector) towards the nose; y across, 0 on the centreline,
+y to the left when looking from the top with the nose pointing right.
KiCad's +y is down, so every point goes through V().
"""
import os
import subprocess
import sys

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
KFP = '/usr/share/kicad/footprints/'
FPLIB = os.path.join(HERE, 'fp', 'sfp.pretty')

# --------------------------------------------------------------------------
# SFP MSA, INF-8074i Appendix A. Table 1 letters in brackets.
PCB_T = 1.0            # (P) over the pads
TAB_W = 9.2            # (Q) width of the board where it enters the connector
BODY_W = 13.4          # (D) housing width, rear
BODY_H = 8.5           # (C) housing height, rear
PCB_Z = 2.25           # (N) PCB underside above the housing bottom
LATCH_TO_PCB_END = 41.8   # (U) latch shoulder to the finger end of the PCB
STOP = 2.5             # (V) latch shoulder to the positive stop outside the cage
WALL = 0.6             # our housing wall, each side (a printed/metal shell)
BODY_PCB_W = BODY_W - 2 * WALL - 0.4       # 11.8: PCB width behind the tab
TAB_L = 6.0            # length kept at 9.2 mm - the host connector's card slot
CAGE_FRONT = LATCH_TO_PCB_END + STOP       # x where the part outside the cage begins
TOP_ROOM = BODY_H - PCB_Z - PCB_T - WALL   # 4.65 above the PCB inside the cage
BOT_ROOM = PCB_Z - WALL                    # 1.65 below it

# Figure 2 / Figure 3: 20 pads, 0.8 pitch, 0.6 wide. Top side pins 11..20,
# pin 20 at +3.8 from the centreline and pin 11 at -3.4; bottom side pins
# 1..10 the mirror, pin 1 opposite pin 20 at +3.4, pin 10 at -3.8 (seen
# through the top). Pad fronts are staggered for mating order - ground 0.5,
# power 0.9, signal 1.3 mm from the edge - and all run back to 3.5 mm min.
PAD_W, PITCH, PAD_END = 0.6, 0.8, 3.8
PINS = {1: 'VeeT', 2: 'TX_FAULT', 3: 'TX_DISABLE', 4: 'SDA', 5: 'SCL', 6: 'MOD_ABS',
        7: 'RS0', 8: 'RX_LOS', 9: 'VeeR', 10: 'VeeR', 11: 'VeeR', 12: 'RD-', 13: 'RD+',
        14: 'VeeR', 15: 'VccR', 16: 'VccT', 17: 'VeeT', 18: 'TD+', 19: 'TD-', 20: 'VeeT'}
# pin 9 is VeeR in INF-8074i and RS1 in SFF-8419; it is drawn as a ground pad
# (first mate), which is safe for both - the module ties it to ground.


def pad_y(pin):
    if pin >= 11:
        return 3.8 - (20 - pin) * PITCH          # 20 -> +3.8 ... 11 -> -3.4
    return 3.4 - (pin - 1) * PITCH               # 1 -> +3.4 ... 10 -> -3.8


def pad_start(pin):
    n = PINS[pin]
    if n.startswith('Vee'):
        return 0.5
    if n.startswith('Vcc'):
        return 0.9
    return 1.3


# --------------------------------------------------------------------------
def MM(v):
    return pcbnew.FromMM(v)


ORG = (100.0, 100.0)


def V(x, y):
    return pcbnew.VECTOR2I(MM(ORG[0] + x), MM(ORG[1] - y))


def edge_footprint():
    """The module side of the SFP connector, as its own footprint."""
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID('sfp', 'SFP_Module_Edge'))
    fp.SetReference('J1')
    fp.SetValue('SFP_Module_Edge')
    fp.SetAttributes(pcbnew.FP_SMD)
    for pin in range(1, 21):
        top = pin >= 11
        x0 = pad_start(pin)
        p = pcbnew.PAD(fp)
        p.SetNumber(str(pin))
        p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetAttribute(pcbnew.PAD_ATTRIB_CONN)       # edge connector: no paste
        p.SetSize(pcbnew.VECTOR2I(MM(PAD_END - x0), MM(PAD_W)))
        p.SetPosition(pcbnew.VECTOR2I(MM((x0 + PAD_END) / 2), MM(-pad_y(pin))))
        p.SetPos0(p.GetPosition())             # footprint-relative, or it collapses to the origin
        ls = pcbnew.LSET()
        if top:
            ls.AddLayer(pcbnew.F_Cu); ls.AddLayer(pcbnew.F_Mask)
        else:
            ls.AddLayer(pcbnew.B_Cu); ls.AddLayer(pcbnew.B_Mask)
        p.SetLayerSet(ls)
        fp.Add(p)
    return fp


def write_edge_lib():
    os.makedirs(FPLIB, exist_ok=True)
    fp = edge_footprint()
    io = pcbnew.PCB_IO() if hasattr(pcbnew, 'PCB_IO') else pcbnew.PCB_PLUGIN()
    io.FootprintSave(FPLIB, fp)


# --------------------------------------------------------------------------
# Parts: (ref, value, library, footprint, x, y, rot, side, height)
# x, y are the part centre in the module frame above; side 'F' or 'B'.
# Heights are the package's own, for the envelope check. The nose connector
# is outside the cage (x > CAGE_FRONT) and may be taller than the housing.
COMMON = [
    ('U2', 'STM32G031F6P6 (I2C slave: EEPROM A0/A2 + MDIO bridge 0x56)',
     'Package_SO', 'TSSOP-20_4.4x6.5mm_P0.65mm', 30.5, 0.0, 90, 'F', 1.2),
    ('C1', '10uF VccT', 'Capacitor_SMD', 'C_0603_1608Metric', 5.6, 3.4, 0, 'F', 0.9),
    ('C2', '10uF VccR', 'Capacitor_SMD', 'C_0603_1608Metric', 5.6, -3.4, 0, 'F', 0.9),
    ('C3', '100nF TD+', 'Capacitor_SMD', 'C_0201_0603Metric', 5.6, 1.2, 0, 'F', 0.3),
    ('C4', '100nF TD-', 'Capacitor_SMD', 'C_0201_0603Metric', 5.6, 0.5, 0, 'F', 0.3),
    ('C5', '100nF RD+', 'Capacitor_SMD', 'C_0201_0603Metric', 5.6, -0.5, 0, 'F', 0.3),
    ('C6', '100nF RD-', 'Capacitor_SMD', 'C_0201_0603Metric', 5.6, -1.2, 0, 'F', 0.3),
    ('L1', 'ferrite VccT', 'Inductor_SMD', 'L_0603_1608Metric', 8.6, 3.4, 0, 'F', 0.9),
    ('L2', 'ferrite VccR', 'Inductor_SMD', 'L_0603_1608Metric', 8.6, -3.4, 0, 'F', 0.9),
]

VARIANTS = {
    # 100/1000BASE-T1. DP83TG720S-Q1 (1000) and DP83TC812S-Q1 (100) are
    # pin-to-pin in the same VQFN-36 6x6, so one board, two loadouts.
    't1': dict(length=58.0, title='SFP 100/1000BASE-T1', parts=COMMON + [
        ('U1', 'DP83TG720S-Q1 / DP83TC812S-Q1', 'Package_DFN_QFN',
         'QFN-36-1EP_6x6mm_P0.5mm_EP4.1x4.1mm', 18.0, 0.0, 0, 'F', 0.9),
        ('Y1', '25 MHz', 'Crystal', 'Crystal_SMD_2016-4Pin_2.0x1.6mm', 24.5, 3.8, 0, 'F', 0.5),
        ('U3', 'TPS62A01 3V3->1V0', 'Package_TO_SOT_SMD', 'SOT-563', 12.0, 2.6, 0, 'F', 0.6),
        ('L3', '1uH', 'Inductor_SMD', 'L_0805_2012Metric', 12.0, -0.3, 0, 'F', 1.0),
        ('L4', 'CMC (ACT1210 class)', 'Inductor_SMD', 'L_1210_3225Metric', 37.5, 0.0, 0, 'F', 2.5),
        ('D1', 'ESD, MDI', 'Package_TO_SOT_SMD', 'SOT-23', 42.0, 0.0, 90, 'F', 1.1),
        ('J2', 'H-MTD PCB header (Rosenberger E6A10A class) - placeholder',
         None, 'NOSE', 51.0, 0.0, 0, 'F', 10.0),
    ]),
    # 1000BASE-T. DP83869HM does SGMII to copper; VQFN-48 7x7.
    'rj45': dict(length=62.0, title='SFP 1000BASE-T (RJ45)', parts=COMMON + [
        ('U1', 'DP83869HM', 'Package_DFN_QFN',
         'QFN-48-1EP_7x7mm_P0.5mm_EP5.15x5.15mm', 18.4, 0.0, 0, 'F', 0.9),
        ('Y1', '25 MHz', 'Crystal', 'Crystal_SMD_2016-4Pin_2.0x1.6mm', 24.8, 4.2, 0, 'F', 0.5),
        ('U3', 'TPS62A01 3V3->1V1', 'Package_TO_SOT_SMD', 'SOT-563', 12.0, 2.6, 0, 'F', 0.6),
        ('U4', 'LDO 3V3->2V5', 'Package_TO_SOT_SMD', 'SOT-563', 12.0, -3.0, 0, 'F', 0.6),
        ('L3', '1uH', 'Inductor_SMD', 'L_0805_2012Metric', 12.0, -0.3, 0, 'F', 1.0),
        ('T1', '4-pair 1000BASE-T magnetics, low profile - placeholder', None, 'MAG',
         39.0, 0.0, 0, 'F', 4.0),
        ('J2', 'RJ45, low profile - placeholder', None, 'NOSE', 54.0, 0.0, 0, 'F', 13.5),
    ]),
    # 10BASE-T1S. No T1S PHY has SGMII, so a CrossLink-NX (SGMII CDR on
    # its I/O) bridges SGMII at 10 Mb/s to the LAN8670's MII and buffers the
    # half-duplex T1S side.
    't1s': dict(length=58.0, title='SFP 10BASE-T1S', parts=COMMON + [
        ('U1', 'LIFCL-17 CrossLink-NX csfBGA-121 6x6', 'Package_BGA',
         'ST_UFBGA-121_6x6mm_Layout11x11_P0.5mm', 18.0, 0.0, 0, 'F', 1.0),
        ('U5', 'LAN8670 (MII)', 'Package_DFN_QFN',
         'QFN-32-1EP_5x5mm_P0.5mm_EP3.45x3.45mm', 37.6, 0.0, 0, 'F', 0.9),
        ('U6', 'SPI flash (FPGA bitstream)', 'Package_SON', 'WSON-10-1EP_2x3mm_P0.5mm_EP0.84x2.4mm', 24.5, 3.4, 0, 'F', 0.6),
        ('Y1', '25 MHz', 'Crystal', 'Crystal_SMD_2016-4Pin_2.0x1.6mm', 24.5, -3.8, 0, 'F', 0.5),
        ('U3', 'TPS62A01 3V3->1V0', 'Package_TO_SOT_SMD', 'SOT-563', 12.0, 2.6, 0, 'F', 0.6),
        ('U4', 'LDO 3V3->1V8', 'Package_TO_SOT_SMD', 'SOT-563', 12.0, -3.0, 0, 'F', 0.6),
        ('L3', '1uH', 'Inductor_SMD', 'L_0805_2012Metric', 12.0, -0.3, 0, 'F', 1.0),
        ('J2', '2-pin T1S (JST PH placeholder)', 'Connector_JST',
         'JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal', 52.5, 1.0, 270, 'F', 6.0),
    ]),
}
# placeholders with no library footprint yet: (w, l) for the courtyard box
PLACEHOLDER = {'NOSE': None, 'MAG': (9.0, 8.0)}
NOSE_SIZE = {'t1': (11.0, 12.0), 'rj45': (13.6, 16.0), 't1s': (8.0, 7.0)}


# --------------------------------------------------------------------------
def seg(board, layer, a, b, w=0.1):
    s = pcbnew.PCB_SHAPE(board)
    s.SetShape(pcbnew.SHAPE_T_SEGMENT)
    s.SetStart(V(*a)); s.SetEnd(V(*b))
    s.SetLayer(layer); s.SetWidth(MM(w))
    board.Add(s)


def poly(board, layer, pts, w=0.1):
    for a, b in zip(pts, pts[1:] + pts[:1]):
        seg(board, layer, a, b, w)


def outline_pts(L):
    t, b = TAB_W / 2, BODY_PCB_W / 2
    return [(0, t), (TAB_L, t), (TAB_L + 1.0, b), (L, b),
            (L, -b), (TAB_L + 1.0, -b), (TAB_L, -t), (0, -t)]


def text(board, layer, s, x, y, h=0.8):
    t = pcbnew.PCB_TEXT(board)
    t.SetText(s); t.SetLayer(layer)
    t.SetPosition(V(x, y))
    t.SetTextSize(pcbnew.VECTOR2I(MM(h), MM(h)))
    t.SetTextThickness(MM(h * 0.15))
    if layer in (pcbnew.B_SilkS, pcbnew.B_Fab, pcbnew.B_Cu):
        t.SetMirrored(True)                 # reads right way round from underneath
    board.Add(t)


def build(name, spec, out_dir=None):
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    L = spec['length']
    poly(board, pcbnew.Edge_Cuts, outline_pts(L))
    # cage front and the room it leaves, drawn for whoever routes this next
    seg(board, pcbnew.Dwgs_User, (CAGE_FRONT, 7.5), (CAGE_FRONT, -7.5), 0.15)
    text(board, pcbnew.Dwgs_User, 'cage front', CAGE_FRONT, 8.4, 0.8)
    text(board, pcbnew.Dwgs_User, f'inside cage: top <= {TOP_ROOM:.2f} mm, bottom <= {BOT_ROOM:.2f} mm',
         20.0, -8.4, 0.7)
    text(board, pcbnew.F_SilkS, spec['title'], 30.0, 5.6, 0.7)
    ef = edge_footprint()
    ef.SetPosition(V(0, 0))
    board.Add(ef)
    for ref, val, lib, fpn, x, y, rot, side, h in spec['parts']:
        if lib:
            fp = pcbnew.FootprintLoad(KFP + lib + '.pretty', fpn)
        else:
            fp = pcbnew.FOOTPRINT(board)
            fp.SetFPID(pcbnew.LIB_ID('sfp', fpn))
        fp.SetReference(ref)
        fp.SetValue(val)
        fp.Value().SetVisible(False)
        fp.SetPosition(V(x, y))
        fp.SetOrientationDegrees(rot)
        if side == 'B':
            fp.Flip(fp.GetPosition(), False)
        board.Add(fp)
        if not lib:                                   # courtyard box stands in
            w, l = NOSE_SIZE[name.replace('_v0', '')] if fpn == 'NOSE' else PLACEHOLDER[fpn]
            poly(board, pcbnew.F_CrtYd, [(x - l / 2, w / 2), (x + l / 2, w / 2),
                                         (x + l / 2, -w / 2), (x - l / 2, -w / 2)], 0.05)
    out = os.path.join(HERE, out_dir or name)
    os.makedirs(out, exist_ok=True)
    path = os.path.join(out, f'{name}.kicad_pcb')
    board.Save(path)
    subprocess.run(['kicad-cli', 'pcb', 'export', 'svg', '--layers',
                    'Edge.Cuts,F.Cu,F.CrtYd,F.Fab,F.SilkS,Dwgs.User', '--page-size-mode', '2',
                    '--exclude-drawing-sheet', '-o', os.path.join(out, f'{name}_top.svg'), path],
                   capture_output=True)
    subprocess.run(['kicad-cli', 'pcb', 'export', 'svg', '--layers',
                    'Edge.Cuts,B.Cu,B.CrtYd,B.Fab', '--page-size-mode', '2', '--mirror',
                    '--exclude-drawing-sheet', '-o', os.path.join(out, f'{name}_bottom.svg'), path],
                   capture_output=True)
    return board


# --------------------------------------------------------------------------
# envelope check: every part's courtyard box and height against the housing
def courtyard(board, ref):
    for fp in board.GetFootprints():
        if fp.GetReference() == ref:
            bb = fp.GetCourtyard(pcbnew.F_CrtYd).BBox() if fp.GetCourtyard(pcbnew.F_CrtYd).OutlineCount() \
                else fp.GetBoundingBox(False, False)
            x0 = pcbnew.ToMM(bb.GetLeft()) - ORG[0]; x1 = pcbnew.ToMM(bb.GetRight()) - ORG[0]
            y0 = ORG[1] - pcbnew.ToMM(bb.GetBottom()); y1 = ORG[1] - pcbnew.ToMM(bb.GetTop())
            return x0, y0, x1, y1
    return None


def check(name, spec, board):
    ok = True
    rows = []
    boxes = []
    for ref, val, lib, fpn, x, y, rot, side, h in spec['parts']:
        if lib:
            r = courtyard(board, ref)
        else:
            w, l = NOSE_SIZE[name] if fpn == 'NOSE' else PLACEHOLDER[fpn]
            r = (x - l / 2, y - w / 2, x + l / 2, y + w / 2)
        boxes.append((ref, r, h, side))
        inside = r[0] < CAGE_FRONT
        room = (TOP_ROOM if side == 'F' else BOT_ROOM) if inside else None
        w_lim = BODY_PCB_W / 2 if r[0] > TAB_L + 1 else TAB_W / 2
        wide = max(abs(r[1]), abs(r[3]))
        fails = []
        if room is not None and h > room:
            fails.append(f'height {h} > {room:.2f}')
        if r[0] < 3.9 and side == 'F' and lib:            # clear of the fingers
            fails.append('on the edge fingers')
        if fpn != 'NOSE' and wide > w_lim + 0.01:
            fails.append(f'off the board ({wide:.2f} > {w_lim:.2f})')
        if fpn == 'NOSE' and (r[3] - r[1]) > 13.7 + 0.01:
            fails.append('nose wider than the 13.7 mm housing front')
        ok &= not fails
        rows.append((ref, val[:44], r, h, fails))
    # overlaps between parts on the same side
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if a[3] != b[3]:
                continue
            ra, rb = a[1], b[1]
            if ra[0] < rb[2] and rb[0] < ra[2] and ra[1] < rb[3] and rb[1] < ra[3]:
                ok = False
                rows.append((a[0], f'overlaps {b[0]}', ra, a[2], ['overlap']))
    print(f'\n{name}: {"OK" if ok else "FAIL"}   ({spec["title"]}, PCB {spec["length"]:.0f} mm, '
          f'cage front at {CAGE_FRONT:.1f})')
    for ref, val, r, h, fails in rows:
        print(f'   {ref:3s} {val:44s} x {r[0]:5.1f}..{r[2]:5.1f}  y {r[1]:5.1f}..{r[3]:5.1f}  h {h:4.1f}  '
              + (', '.join(fails) if fails else 'ok'))
    return ok, boxes


def envelope_mesh(name, spec, boxes):
    import numpy as np
    import trimesh
    parts = []

    def slab(x0, y0, z0, x1, y1, z1, c):
        m = trimesh.creation.box(extents=(x1 - x0, y1 - y0, z1 - z0))
        m.apply_translation(((x0 + x1) / 2, (y0 + y1) / 2, (z0 + z1) / 2))
        m.visual.face_colors = np.tile(np.array(list(c) + [255], np.uint8), (len(m.faces), 1))
        parts.append(m)
    L = spec['length']
    zp = PCB_Z
    slab(0, -TAB_W / 2, zp, TAB_L, TAB_W / 2, zp + PCB_T, (30, 105, 60))
    slab(TAB_L, -BODY_PCB_W / 2, zp, L, BODY_PCB_W / 2, zp + PCB_T, (30, 105, 60))
    for pin in range(1, 21):
        z = zp + PCB_T if pin >= 11 else zp - 0.03
        slab(pad_start(pin), pad_y(pin) - PAD_W / 2, z, PAD_END, pad_y(pin) + PAD_W / 2, z + 0.03,
             (225, 180, 60))
    for ref, (x0, y0, x1, y1), h, side in boxes:
        c = (235, 125, 35) if ref == 'J2' else (55, 57, 64)
        if side == 'F':
            slab(x0, y0, zp + PCB_T, x1, y1, zp + PCB_T + h, c)
        else:
            slab(x0, y0, zp - h, x1, y1, zp, c)
    # the housing envelope inside the cage, as a thin wireframe of its floor and roof
    for z in (0.0, BODY_H - 0.05):
        slab(-2, -BODY_W / 2, z, CAGE_FRONT, -BODY_W / 2 + 0.3, z + 0.05, (160, 190, 215))
        slab(-2, BODY_W / 2 - 0.3, z, CAGE_FRONT, BODY_W / 2, z + 0.05, (160, 190, 215))
    return trimesh.util.concatenate(parts)


def main():
    write_edge_lib()
    ok_all = True
    meshes = []
    for i, (name, spec) in enumerate(VARIANTS.items()):
        if os.path.exists(os.path.join(HERE, name, f'make_{name}.py')):
            # this variant has its own schematic + PCB generator; only the
            # v0 envelope check runs here, on a scratch board
            b = build(name + '_v0', spec, out_dir=name)
        else:
            b = build(name, spec)
        ok, boxes = check(name, spec, b)
        ok_all &= ok
        m = envelope_mesh(name, spec, boxes)
        m.export(os.path.join(HERE, name, f'{name}_envelope.stl'))
        if '--no-png' not in sys.argv:
            from render import render
            os.makedirs(os.path.join(HERE, 'img'), exist_ok=True)
            render(m, elev=32, azim=-30).save(os.path.join(HERE, 'img', f'envelope_{name}.png'))
    print('\n' + ('ALL VARIANTS FIT' if ok_all else 'SOMETHING DOES NOT FIT'))
    return 0 if ok_all else 1


if __name__ == '__main__':
    sys.exit(main())

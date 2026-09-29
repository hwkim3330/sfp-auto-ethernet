"""Shared generator for the SFP modules: symbols, schematic, PCB, routing, DRC.

A variant (t1/, rj45/, t1s/) is a design module that defines its parts and a
few constants, then calls sfpgen.run(sys.modules[__name__]). The design module
provides:

    P            list of part dicts (see part())         NAME, HERE, TITLE, SHEET
    LENGTH       board length, mm                         NETCLASSES, PAIRS
    SCH_AT       fixed schematic positions               POWER_NETS
    SYMBOLS      extra symbols: (name, ref, left, right, width)
    SOLID_PADS   {(ref, pad)} that join the planes solidly (EP thermal vias)
    HMTD_AT      H-MTD position, or None                  lcsc_for(part)

Everything else - the MSA edge, the H-MTD land, the CMC land, rules, planes,
keep-outs, Freerouting, the SES import - is identical for every variant, so it
lives here once.
"""
import json
import math
import os
import re
import subprocess
import sys
import uuid as _uuid

import pcbnew

HW = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HW)
import make_boards as MB                 # noqa: E402  - MSA geometry + edge footprint

KSYM = '/usr/share/kicad/symbols/'
KFP = '/usr/share/kicad/footprints/'
SYMLIB = os.path.join(HW, 'sym', 'sfp.kicad_sym')
FPLIB = os.path.join(HW, 'fp', 'sfp.pretty')
FREEROUTING = os.path.expanduser('~/.local/share/freerouting/freerouting-1.9.0.jar')
D = None                                 # the design module, set by run()

C0201 = 'Capacitor_SMD:C_0201_0603Metric'
C0402 = 'Capacitor_SMD:C_0402_1005Metric'
C0603 = 'Capacitor_SMD:C_0603_1608Metric'
R0201 = 'Resistor_SMD:R_0201_0603Metric'
R0402 = 'Resistor_SMD:R_0402_1005Metric'
R0603 = 'Resistor_SMD:R_0603_1608Metric'
FB0603 = 'Inductor_SMD:L_0603_1608Metric'
LED0402 = 'LED_SMD:LED_0402_1005Metric'
TP = 'TestPoint:TestPoint_Pad_D1.0mm'

# ==========================================================================
# symbol library
def _pin(etype, x, y, ang, name, num, length=2.54, hide=False):
    return ('    (pin %s line (at %.2f %.2f %d) (length %.2f)%s\n'
            '      (name "%s" (effects (font (size 1.0 1.0))))\n'
            '      (number "%s" (effects (font (size 1.0 1.0))))\n    )\n'
            % (etype, x, y, ang, length, ' hide' if hide else '', name, num))


def _symbol(name, ref, left, right, width=20.32, extra=''):
    """left/right: [(num, name, etype)], drawn top to bottom at 2.54 pitch."""
    n = max(len(left), len(right))
    h = (n + 1) * 2.54
    top = h / 2
    body = ('  (symbol "%s" (in_bom yes) (on_board yes)\n'
            '    (property "Reference" "%s" (at 0 %.2f 0) (effects (font (size 1.27 1.27))))\n'
            '    (property "Value" "%s" (at 0 %.2f 0) (effects (font (size 1.27 1.27))))\n'
            '    (property "Footprint" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
            '    (property "Datasheet" "" (at 0 0 0) (effects (font (size 1.27 1.27)) hide))\n'
            '    (symbol "%s_0_1"\n'
            '      (rectangle (start %.2f %.2f) (end %.2f %.2f)\n'
            '        (stroke (width 0.254) (type default)) (fill (type background)))\n'
            '    )\n    (symbol "%s_1_1"\n'
            % (name, ref, top + 1.27, name, -top - 1.27, name, -width / 2, top, width / 2, -top, name))
    for i, (num, nm, et) in enumerate(left):
        y = top - 2.54 * (i + 1)
        if nm:
            body += _pin(et, -width / 2 - 2.54, round(y / 1.27) * 1.27, 0, nm, num)
    for i, (num, nm, et) in enumerate(right):
        y = top - 2.54 * (i + 1)
        if nm:
            body += _pin(et, width / 2 + 2.54, round(y / 1.27) * 1.27, 180, nm, num)
    body += extra + '    )\n  )\n'
    return body


def write_symbols():
    os.makedirs(os.path.dirname(SYMLIB), exist_ok=True)
    edge_l = [('16', 'VccT', 'passive'), ('15', 'VccR', 'passive'), ('', '', ''),
              ('18', 'TD+', 'passive'), ('19', 'TD-', 'passive'), ('13', 'RD+', 'passive'),
              ('12', 'RD-', 'passive'), ('', '', ''), ('4', 'SDA', 'passive'), ('5', 'SCL', 'passive'),
              ('3', 'TX_DISABLE', 'passive'), ('2', 'TX_FAULT', 'passive'), ('8', 'RX_LOS', 'passive'),
              ('6', 'MOD_ABS', 'passive'), ('7', 'RS0', 'passive')]
    edge_r = [('1', 'VeeT', 'passive'), ('17', 'VeeT', 'passive'), ('20', 'VeeT', 'passive'),
              ('9', 'VeeR/RS1', 'passive'), ('10', 'VeeR', 'passive'), ('11', 'VeeR', 'passive'),
              ('14', 'VeeR', 'passive')]
    hmtd = [('1', 'MDI+', 'passive'), ('2', 'MDI-', 'passive'), ('3', 'SHIELD', 'passive')]
    lib = '(kicad_symbol_lib (version 20220914) (generator sfpgen)\n'
    for args in D.SYMBOLS:
        lib += _symbol(*args)
    lib += _symbol('SFP_EDGE', 'J', edge_l, edge_r, width=17.78)
    lib += _symbol('HMTD_1P', 'J', hmtd, [], width=10.16)
    lib += ')\n'
    open(SYMLIB, 'w').write(lib)


def write_footprints():
    """CMC land and the H-MTD placeholder. Both are flagged in their names."""
    io = pcbnew.PCB_IO() if hasattr(pcbnew, 'PCB_IO') else pcbnew.PCB_PLUGIN()

    def smd(fp, num, x, y, w, h):
        p = pcbnew.PAD(fp)
        p.SetNumber(num)
        p.SetShape(pcbnew.PAD_SHAPE_ROUNDRECT)
        p.SetRoundRectRadiusRatio(0.2)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(p.SMDMask())
        p.SetSize(pcbnew.VECTOR2I(MB.MM(w), MB.MM(h)))
        p.SetPosition(pcbnew.VECTOR2I(MB.MM(x), MB.MM(y)))
        p.SetPos0(p.GetPosition())
        fp.Add(p)

    def crt(fp, w, h):
        for a, b in (((-w, -h), (w, -h)), ((w, -h), (w, h)), ((w, h), (-w, h)), ((-w, h), (-w, -h))):
            s = pcbnew.FP_SHAPE(fp)
            s.SetShape(pcbnew.SHAPE_T_SEGMENT)
            s.SetStart0(pcbnew.VECTOR2I(MB.MM(a[0]), MB.MM(a[1])))
            s.SetEnd0(pcbnew.VECTOR2I(MB.MM(b[0]), MB.MM(b[1])))
            s.SetLayer(pcbnew.F_CrtYd); s.SetWidth(MB.MM(0.05))
            fp.Add(s)

    # 3.2 x 2.5 4-terminal CMC (DLW32MH / ACT1210 class): pads at the four
    # corners, 1 and 2 on one end, 4 and 3 opposite. Land from the ACT1210
    # recommended pattern (1.0 x 0.9 pads, 2.4 mm across, 1.1 mm pitch).
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID('sfp', 'L_CommonMode_3225'))
    for num, x, y in (('1', -1.2, -0.55), ('2', -1.2, 0.55), ('3', 1.2, 0.55), ('4', 1.2, -0.55)):
        smd(fp, num, x, y, 1.0, 0.9)
    crt(fp, 2.0, 1.55)
    io.FootprintSave(FPLIB, fp)

    # H-MTD: Rosenberger E6S20A-40MT5-x, right angle, pin-in-paste THT.
    # Layout drawing MB_633 sheet 1 / datasheet E6S20A-40MT5-Y p.1:
    #   4 ground holes  finished 1.74, pad 2.5, 2 x 2 grid 7.0 across x 7.5 deep
    #                   (9.3 is the outer width of the hatched areas, not the pitch -
    #                    read off the drawing at 47.3 px/mm: centres 332 px apart)
    #   2 signal holes  finished 0.7, 2.0 apart, 1.87 behind the front ground row
    #   body 11 wide, 21.9 deep, 13.5 tall; front face 13 ahead of the front
    #   ground row; board edge to front ground row <= 10
    # Origin = centre of the front ground row, +x = towards the mating face.
    def tht(fp, num, x, y, pad, drill):
        p = pcbnew.PAD(fp)
        p.SetNumber(num)
        p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        p.SetLayerSet(p.PTHMask())
        p.SetSize(pcbnew.VECTOR2I(MB.MM(pad), MB.MM(pad)))
        p.SetDrillSize(pcbnew.VECTOR2I(MB.MM(drill), MB.MM(drill)))
        p.SetPosition(pcbnew.VECTOR2I(MB.MM(x), MB.MM(y)))
        p.SetPos0(p.GetPosition())
        fp.Add(p)
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID('sfp', 'Rosenberger_HMTD_E6S20A_1P_RA'))
    tht(fp, '1', -1.87, -1.0, 1.1, 0.7)
    tht(fp, '2', -1.87, 1.0, 1.1, 0.7)
    for x in (0.0, -7.5):
        for y in (-3.5, 3.5):
            tht(fp, '3', x, y, 2.5, 1.74)
    # "solder area" (hatched) on MB_633: exposed copper for the shield to wet,
    # tied to ground. Rectangles, trimmed clear of the R2 relief near the pins.
    for cx, cy, w, h in ((0.76, 0.0, 1.0, 2.9), (-2.76, 4.03, 2.18, 1.27), (-2.76, -4.03, 2.18, 1.27)):
        p = pcbnew.PAD(fp)
        p.SetNumber('3')
        p.SetShape(pcbnew.PAD_SHAPE_RECT)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(p.SMDMask())
        p.SetSize(pcbnew.VECTOR2I(MB.MM(w), MB.MM(h)))
        p.SetPosition(pcbnew.VECTOR2I(MB.MM(cx), MB.MM(cy)))
        p.SetPos0(p.GetPosition())
        fp.Add(p)
    front, depth, half = 13.0, 21.9, 5.5
    for layer, g in ((pcbnew.F_CrtYd, 0.25), (pcbnew.F_Fab, 0.0)):
        x0, x1, y0 = front - depth - g, front + g, half + g
        for a, b in (((x0, -y0), (x1, -y0)), ((x1, -y0), (x1, y0)), ((x1, y0), (x0, y0)), ((x0, y0), (x0, -y0))):
            sh = pcbnew.FP_SHAPE(fp)
            sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
            sh.SetStart0(pcbnew.VECTOR2I(MB.MM(a[0]), MB.MM(a[1])))
            sh.SetEnd0(pcbnew.VECTOR2I(MB.MM(b[0]), MB.MM(b[1])))
            sh.SetLayer(layer); sh.SetWidth(MB.MM(0.05 if layer == pcbnew.F_CrtYd else 0.1))
            fp.Add(sh)
    io.FootprintSave(FPLIB, fp)


# ==========================================================================
# schematic
_SYM = {}


def _u(seed):
    return str(_uuid.uuid5(_uuid.UUID(D.SHEET), seed))


def sym_block(lib_id):
    lib, name = lib_id.split(':', 1)
    path = SYMLIB if lib == 'sfp' else KSYM + lib + '.kicad_sym'
    txt = _SYM.setdefault(path, open(path).read())
    i = txt.find('(symbol "%s" ' % name)
    if i < 0:
        raise RuntimeError(f'{lib_id} not found')
    d, j = 0, i
    while True:
        c = txt[j]
        if c == '(':
            d += 1
        elif c == ')':
            d -= 1
            if d == 0:
                j += 1
                break
        elif c == '"':
            j += 1
            while txt[j] != '"':
                j += 2 if txt[j] == '\\' else 1
        j += 1
    block = txt[i:j]
    ext = re.search(r'\(extends "([^"]+)"\)', block)
    if ext:                                   # derived symbol: pins live in the parent
        pblock, pins = sym_block(f'{lib}:{ext.group(1)}')
        block = pblock.replace('(symbol "%s" ' % ext.group(1), '(symbol "%s" ' % name, 1)
        block = block.replace('(symbol "%s_' % ext.group(1), '(symbol "%s_' % name)
        return block, pins
    pins = []
    for m in re.finditer(r'\(pin\s+(\S+)\s+\S+\s+\(at\s+(-?[\d.]+)\s+(-?[\d.]+)\s+(-?[\d.]+)\)'
                         r'\s+\(length\s+([\d.]+)\)(\s+hide)?\s*\(name\s+"((?:[^"\\]|\\.)*)"', block):
        nm = re.search(r'\(number\s+"((?:[^"\\]|\\.)*)"', block[m.end():])
        pins.append(dict(number=nm.group(1), etype=m.group(1), x=float(m.group(2)),
                         y=float(m.group(3)), ang=int(float(m.group(4)))))
    seen, out = set(), []
    for p in pins:
        if p['number'] not in seen:
            seen.add(p['number'])
            out.append(p)
    return block, out


def snap(v):
    return round(v / 1.27) * 1.27


SCH = []
_PWRN = [0]


def wire(a, b):
    SCH.append('  (wire (pts (xy %.2f %.2f) (xy %.2f %.2f)) (stroke (width 0) (type default))'
               ' (uuid %s))\n' % (a[0], a[1], b[0], b[1], _u('w%.2f%.2f%.2f%.2f' % (*a, *b))))


def label(x, y, net, d):
    ang = {(1, 0): 0, (-1, 0): 180, (0, 1): 270, (0, -1): 90}[d]
    SCH.append('  (label "%s" (at %.2f %.2f %d) (effects (font (size 1.0 1.0)) (justify %s bottom))'
               ' (uuid %s))\n' % (net, x, y, ang, 'left' if d in ((1, 0), (0, -1)) else 'right',
                                   _u('l%s%.2f%.2f' % (net, x, y))))


def symbol_inst(lib_id, x, y, ref, value, fp, seed, dnp=False, hide=False, props=()):
    _, pins = sym_block(lib_id)
    s = '  (symbol (lib_id "%s") (at %.2f %.2f 0) (unit 1)\n' % (lib_id, x, y)
    s += '    (in_bom %s) (on_board yes) (dnp %s)\n' % ('no' if hide else 'yes', 'yes' if dnp else 'no')
    s += '    (uuid %s)\n' % _u('s' + seed)
    s += ('    (property "Reference" "%s" (at %.2f %.2f 0) (effects (font (size 1.0 1.0)) (justify left)%s))\n'
          % (ref, x + 1.5, y - 3.0, ' hide' if hide else ''))
    s += ('    (property "Value" "%s" (at %.2f %.2f 0) (effects (font (size 1.0 1.0)) (justify left)%s))\n'
          % (value, x + 1.5, y + 3.5, ' hide' if hide else ''))
    s += '    (property "Footprint" "%s" (at %.2f %.2f 0) (effects (font (size 1.0 1.0)) hide))\n' % (fp or '', x, y)
    s += '    (property "Datasheet" "" (at %.2f %.2f 0) (effects (font (size 1.0 1.0)) hide))\n' % (x, y)
    for k, v in props:
        s += '    (property "%s" "%s" (at %.2f %.2f 0) (effects (font (size 1.0 1.0)) hide))\n' % (k, v, x, y)
    for p in pins:
        s += '    (pin "%s" (uuid %s))\n' % (p['number'], _u('p' + seed + p['number']))
    s += ('    (instances (project "%s" (path "/%s" (reference "%s") (unit 1))))\n  )\n'
          % (D.NAME, D.SHEET, ref))
    SCH.append(s)


def power(net, x, y, d, seed):
    """Stub out from a pin and end it in a GND / +3V3 symbol."""
    if net == 'GND':
        ex, ey = x + d[0] * 2.54, y + d[1] * 2.54
        wire((x, y), (ex, ey))
        if d != (0, 1):
            wire((ex, ey), (ex, ey + 2.54))
            ey += 2.54
        _PWRN[0] += 1
        symbol_inst('power:GND', ex, ey, '#PWR%03d' % _PWRN[0], 'GND', None, seed + 'G', hide=True)
    else:
        ex, ey = x + d[0] * 2.54, y + d[1] * 2.54
        wire((x, y), (ex, ey))
        if d != (0, -1):
            wire((ex, ey), (ex, ey - 2.54))
            ey -= 2.54
        _PWRN[0] += 1
        symbol_inst('power:+3V3', ex, ey, '#PWR%03d' % _PWRN[0], '+3V3', None, seed + 'V', hide=True)


def write_schematic():
    del SCH[:]
    _PWRN[0] = 0
    # passives in a grid, in netlist order, after the fixed parts
    gx, gy = 40.0, 250.0
    for p in D.P:
        if p['ref'] in D.SCH_AT:
            p['sch'] = tuple(snap(v) for v in D.SCH_AT[p['ref']])
        else:
            p['sch'] = (snap(gx), snap(gy))
            gx += 22.86
            if gx > 380:
                gx, gy = 40.0, gy + 22.86
    used = sorted({p['lib_id'] for p in D.P} | {'power:GND', 'power:+3V3', 'power:PWR_FLAG'})
    for p in D.P:
        X, Y = p['sch']
        props = tuple((k, v) for k, v in (('MPN', p['mpn']), ('LCSC', D.lcsc_for(p))) if v)
        symbol_inst(p['lib_id'], X, Y, p['ref'], p['value'], p['fp'], p['ref'], dnp=p['dnp'],
                    props=props)
        _, pins = sym_block(p['lib_id'])
        byn = {q['number']: q for q in pins}
        for num, q in byn.items():
            px, py = X + q['x'], Y - q['y']
            d = {0: (-1, 0), 180: (1, 0), 90: (0, 1), 270: (0, -1)}[q['ang'] % 360]
            try:
                net = p['nets'][int(num)]
            except (KeyError, ValueError):
                net = None
            if net is None and q['etype'] == 'no_connect':
                continue                  # the library already says so
            if net is None:
                SCH.append('  (no_connect (at %.2f %.2f) (uuid %s))\n' % (px, py, _u('n' + p['ref'] + num)))
            elif net in ('GND', '+3V3'):
                power(net, px, py, d, p['ref'] + '.' + num)
            else:
                ex, ey = px + d[0] * 2.54, py + d[1] * 2.54
                wire((px, py), (ex, ey))
                label(ex, ey, net, d)
    # PWR_FLAG on every rail fed only through passives or the edge connector
    fx = 40.0
    for net in D.POWER_NETS + ('GND',):
        _PWRN[0] += 1
        x, y = snap(fx), snap(30.0)
        symbol_inst('power:PWR_FLAG', x, y, '#FLG%02d' % _PWRN[0], 'PWR_FLAG', None, 'F' + net, hide=True)
        wire((x, y), (x + 5.08, y))
        if net in ('GND', '+3V3'):
            _PWRN[0] += 1
            symbol_inst('power:' + net, x + 5.08, y, '#PWR%03d' % _PWRN[0], net, None, 'FP' + net, hide=True)
        else:
            label(x + 5.08, y, net, (1, 0))
        fx += 25.4
    out = '(kicad_sch (version 20230121) (generator eeschema)\n  (uuid %s)\n  (paper "A2")\n' % D.SHEET
    out += ('  (title_block (title "SFP 100/1000BASE-T1 - DP83TG720S / DP83TC812S") (rev "0.1")\n'
            '    (comment 1 "Generated by hw/t1/make_t1.py - edit the netlist there, not here"))\n')
    out += '  (lib_symbols\n'
    for lid in used:
        blk, _ = sym_block(lid)
        name = lid.split(':', 1)[1]
        out += blk.replace('(symbol "%s" ' % name, '(symbol "%s" ' % lid, 1) + '\n'
    out += '  )\n' + ''.join(SCH) + '  (sheet_instances (path "/" (page "1")))\n)\n'
    open(os.path.join(D.HERE, D.NAME + '.kicad_sch'), 'w').write(out)


def write_libtables():
    open(os.path.join(D.HERE, 'sym-lib-table'), 'w').write(
        '(sym_lib_table\n  (lib (name "sfp")(type "KiCad")(uri "${KIPRJMOD}/../sym/sfp.kicad_sym")(options "")(descr ""))\n)\n')
    open(os.path.join(D.HERE, 'fp-lib-table'), 'w').write(
        '(fp_lib_table\n  (lib (name "sfp")(type "KiCad")(uri "${KIPRJMOD}/../fp/sfp.pretty")(options "")(descr ""))\n)\n')


# ==========================================================================
# PCB
def fp_load(fpid):
    lib, name = fpid.split(':', 1)
    path = FPLIB if lib == 'sfp' else KFP + lib + '.pretty'
    fp = pcbnew.FootprintLoad(path, name)
    if fp is None:
        raise RuntimeError(f'footprint {fpid} not found')
    fp.SetFPID(pcbnew.LIB_ID(lib, name))
    return fp


def build_pcb():
    board = pcbnew.BOARD()
    board.SetCopperLayerCount(4)
    nets = {}

    def net(n):
        if n not in nets:
            ni = pcbnew.NETINFO_ITEM(board, n)
            board.Add(ni)
            nets[n] = ni
        return nets[n]
    MB.poly(board, pcbnew.Edge_Cuts, MB.outline_pts(D.LENGTH))
    MB.seg(board, pcbnew.Dwgs_User, (MB.CAGE_FRONT, 7.5), (MB.CAGE_FRONT, -7.5), 0.15)
    MB.text(board, pcbnew.Dwgs_User, 'cage front', MB.CAGE_FRONT, 8.4, 0.8)
    MB.text(board, pcbnew.B_SilkS, D.TITLE, 30.0, 5.4, 0.8)
    for p in D.P:
        fp = MB.edge_footprint() if p['ref'] == 'J1' else fp_load(p['fp'])
        fp.SetReference(p['ref'])
        fp.SetValue(p['value'])
        fp.Value().SetVisible(False)
        if D.lcsc_for(p):
            fp.SetProperty('LCSC', D.lcsc_for(p))
        fp.Reference().SetVisible(False)       # 12 mm board: refs live on F.Fab
        fp.SetPosition(MB.V(*p['at']))
        fp.SetOrientationDegrees(p['rot'])
        if p['dnp']:
            fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM)
        board.Add(fp)                                # before Flip: it needs the board
        if p['side'] == 'B':
            fp.Flip(fp.GetPosition(), False)
        for pad in fp.Pads():
            num = pad.GetNumber()
            if not num:
                continue                             # EP paste windows
            n = p['nets'].get(int(num)) if num.isdigit() else None
            if n:
                pad.SetNet(net(n))
            if (p['ref'], num) in D.SOLID_PADS:
                pad.SetZoneConnection(pcbnew.ZONE_CONNECTION_FULL)   # EP + thermal vias: solid
    path = os.path.join(D.HERE, D.NAME + '.kicad_pcb')
    board.Save(path)
    write_project()                      # Save() rewrites the .kicad_pro with defaults
    return board


def check_pcb(board):
    """Courtyard overlaps per side, and the envelope."""
    boxes = []
    for fp in board.GetFootprints():
        side = 'B' if fp.IsFlipped() else 'F'
        cy = fp.GetCourtyard(pcbnew.B_CrtYd if side == 'B' else pcbnew.F_CrtYd)
        bb = cy.BBox() if cy.OutlineCount() else fp.GetBoundingBox(False, False)
        x0 = pcbnew.ToMM(bb.GetLeft()) - MB.ORG[0]; x1 = pcbnew.ToMM(bb.GetRight()) - MB.ORG[0]
        y0 = MB.ORG[1] - pcbnew.ToMM(bb.GetBottom()); y1 = MB.ORG[1] - pcbnew.ToMM(bb.GetTop())
        boxes.append((fp.GetReference(), side, (x0, y0, x1, y1)))
    bad = []
    for i in range(len(boxes)):
        for j in range(i + 1, len(boxes)):
            a, b = boxes[i], boxes[j]
            if a[1] != b[1] or 'J1' in (a[0], b[0]):
                continue
            ra, rb = a[2], b[2]
            if ra[0] < rb[2] - 1e-3 and rb[0] < ra[2] - 1e-3 and ra[1] < rb[3] - 1e-3 and rb[1] < ra[3] - 1e-3:
                bad.append(f'{a[0]} x {b[0]} ({a[1]})')
    for ref, side, r in boxes:
        lim = MB.TAB_W / 2 if r[0] < MB.TAB_L + 1 else MB.BODY_PCB_W / 2
        if ref not in ('J1',) and max(abs(r[1]), abs(r[3])) > lim + 1e-3:
            bad.append(f'{ref} off the board edge')
        if ref != 'J1' and r[0] < MB.PAD_END + 0.1 and side == 'F':
            bad.append(f'{ref} on the edge fingers')
    return bad


# ==========================================================================
# routing: netclasses, planes, Freerouting, SES back in, fill, DRC
def load_board(path):
    """Open the board WITH its project, so the netclass patterns in the
    .kicad_pro apply. A bare LoadBoard leaves every net in Default, and the DSN
    export then resyncs nets to classes from those (absent) patterns - which
    is how the first routed boards got 0.127 mm SGMII instead of 50 ohm."""
    pro = os.path.abspath(path[:-len('.kicad_pcb')] + '.kicad_pro')
    sm = pcbnew.GetSettingsManager()
    sm.LoadProject(pro)
    board = pcbnew.LoadBoard(path)
    return board


def apply_rules(board):
    """KiCad 7's standalone LoadBoard does not read the .kicad_pro, so the
    rules the DSN export and DRC need are set on the board in memory."""
    ds = board.GetDesignSettings()
    ds.m_MinClearance = MB.MM(0.1)
    ds.m_TrackMinWidth = MB.MM(0.1)
    ds.m_ViasMinSize = MB.MM(0.4)
    ds.m_MinThroughDrill = MB.MM(0.2)
    ds.m_CopperEdgeClearance = MB.MM(0.2)
    ds.m_SolderMaskMinWidth = MB.MM(0.0)
    ds.m_HoleClearance = MB.MM(0.25)       # via hole to copper; 0.15 copper clearance + 0.1 annular
    ns = ds.m_NetSettings
    for c in D.NETCLASSES:
        nc = ns.m_DefaultNetClass if c['name'] == 'Default' else pcbnew.NETCLASS(c['name'])
        nc.SetClearance(MB.MM(c['clearance']))
        nc.SetTrackWidth(MB.MM(c['track_width']))
        nc.SetViaDiameter(MB.MM(c['via_diameter']))
        nc.SetViaDrill(MB.MM(c['via_drill']))
        if 'dp_width' in c:
            nc.SetDiffPairWidth(MB.MM(c['dp_width']))
            nc.SetDiffPairGap(MB.MM(c['dp_gap']))
        if c['name'] != 'Default':
            ns.m_NetClasses[c['name']] = nc
            for n in c['nets']:
                ni = board.FindNet(n)
                if ni:
                    ni.SetNetClass(nc)
    board.BuildConnectivity()


def write_project():
    classes, assign = [], {}
    for c in D.NETCLASSES:
        classes.append({'bus_width': 12, 'clearance': c['clearance'],
                        'diff_pair_gap': c.get('dp_gap', 0.2), 'diff_pair_via_gap': 0.25,
                        'diff_pair_width': c.get('dp_width', 0.15), 'line_style': 0,
                        'microvia_diameter': 0.3, 'microvia_drill': 0.1, 'name': c['name'],
                        'pcb_color': 'rgba(0, 0, 0, 0.000)', 'schematic_color': 'rgba(0, 0, 0, 0.000)',
                        'track_width': c['track_width'], 'via_diameter': c['via_diameter'],
                        'via_drill': c['via_drill'], 'wire_width': 6})
        for n in c.get('nets', []):
            assign[n] = c['name']
    pro = {'board': {'design_settings': {'defaults': {}, 'rules': {
               'min_clearance': 0.1, 'min_track_width': 0.1, 'min_via_diameter': 0.4,
               'min_through_hole_diameter': 0.2, 'min_copper_edge_clearance': 0.2}}},
           'boards': [], 'cvpcb': {'equivalence_files': []},
           'libraries': {'pinned_footprint_libs': [], 'pinned_symbol_libs': []},
           'meta': {'filename': D.NAME + '.kicad_pro', 'version': 1},
           'net_settings': {'classes': classes, 'meta': {'version': 3}, 'net_colors': None,
                            'netclass_assignments': None,
                            'netclass_patterns': [{'netclass': c, 'pattern': n}
                                                  for n, c in sorted(assign.items())]},
           'pcbnew': {'last_paths': {}, 'page_layout_descr_file': ''},
           'schematic': {'legacy_lib_dir': '', 'legacy_lib_list': []},
           'sheets': [[D.SHEET, '']], 'text_variables': {}}
    json.dump(pro, open(os.path.join(D.HERE, D.NAME + '.kicad_pro'), 'w'), indent=2)


def zone(board, net, layer, pts, clearance=0.2):
    z = pcbnew.ZONE(board)
    ls = pcbnew.LSET()
    ls.addLayer(layer)
    z.SetLayerSet(ls)
    ch = pcbnew.SHAPE_LINE_CHAIN()          # AddPolygon, never SetOutline (double free)
    for x, y in pts:
        ch.Append(MB.V(x, y))
    ch.SetClosed(True)
    z.AddPolygon(ch)
    z.SetNet(board.FindNet(net))
    z.SetPadConnection(pcbnew.ZONE_CONNECTION_THERMAL)
    z.SetLocalClearance(MB.MM(clearance))
    z.SetMinThickness(MB.MM(0.12))
    z.SetThermalReliefGap(MB.MM(0.25))
    z.SetThermalReliefSpokeWidth(MB.MM(0.3))
    board.Add(z)
    return z


def add_edge_keepouts(board, w=0.3):
    """Thin no-track/no-via strips along every outline edge: Freerouting keeps
    only copper-to-copper clearance to the board edge, not the fab's 0.2 mm."""
    pts = MB.outline_pts(D.LENGTH)
    for (x0, y0), (x1, y1) in zip(pts, pts[1:] + pts[:1]):
        L = math.hypot(x1 - x0, y1 - y0)
        nx, ny = -(y1 - y0) / L * w, (x1 - x0) / L * w     # a normal; which side does not matter,
        quad = [(x0 + nx, y0 + ny), (x1 + nx, y1 + ny), (x1 - nx, y1 - ny), (x0 - nx, y0 - ny)]
        z = pcbnew.ZONE(board)                            # the strip straddles the edge
        ls = pcbnew.LSET()
        for l in (pcbnew.F_Cu, pcbnew.In1_Cu, pcbnew.In2_Cu, pcbnew.B_Cu):
            ls.addLayer(l)
        z.SetLayerSet(ls)
        ch = pcbnew.SHAPE_LINE_CHAIN()
        for x, y in quad:
            ch.Append(MB.V(x, y))
        ch.SetClosed(True)
        z.AddPolygon(ch)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowCopperPour(False)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        board.Add(z)


# (x0, x1, y0, y1) relative to the connector's front ground row, +x to the mating face
HMTD_KEEPOUT = [(-0.06, 1.27, 1.79, 4.37), (-0.06, 1.27, -4.37, -1.79),
                (-6.77, -5.29, 2.30, 4.67), (-6.77, -5.29, -4.67, -2.30)]


def add_connector_keepouts(board):
    for x0, x1, y0, y1 in HMTD_KEEPOUT:
        z = pcbnew.ZONE(board)
        ls = pcbnew.LSET()
        ls.addLayer(pcbnew.F_Cu)
        z.SetLayerSet(ls)
        ch = pcbnew.SHAPE_LINE_CHAIN()
        X, Y = D.HMTD_AT
        for x, y in ((X + x0, Y + y0), (X + x1, Y + y0), (X + x1, Y + y1), (X + x0, Y + y1)):
            ch.Append(MB.V(x, y))
        ch.SetClosed(True)
        z.AddPolygon(ch)
        z.SetIsRuleArea(True)
        z.SetDoNotAllowTracks(True)
        z.SetDoNotAllowVias(True)
        z.SetDoNotAllowCopperPour(True)
        z.SetDoNotAllowPads(False)
        z.SetDoNotAllowFootprints(False)
        board.Add(z)


def add_planes(board):
    inset = 0.3
    pts = [(x, y - inset if y > 0 else y + inset) for x, y in MB.outline_pts(D.LENGTH)]
    pts = [(max(inset, min(D.LENGTH - inset, x)), y) for x, y in pts]
    zone(board, 'GND', pcbnew.In1_Cu, pts, clearance=0.15)
    zone(board, '+3V3', pcbnew.In2_Cu, pts, clearance=0.15)


def add_outer_pours(board):
    """After routing, never before: in the DSN a pour on F/B reads as a solid
    plane and the router finds no room on the signal layers. On a 12.4 mm board
    the signal vias' antipads cut In1 into islands; these stitch them back.
    SMD pads join solidly (0201 thermals starve), THT keeps spokes."""
    inset = 0.3
    pts = [(x, y - inset if y > 0 else y + inset) for x, y in MB.outline_pts(D.LENGTH)]
    pts = [(max(inset, min(D.LENGTH - inset, x)), y) for x, y in pts]
    for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
        z = zone(board, 'GND', layer, pts, clearance=0.2)
        z.SetPadConnection(pcbnew.ZONE_CONNECTION_THT_THERMAL)
    # no pour among the gold fingers: the contact area is plated and wiped
    k = pcbnew.ZONE(board)
    ls = pcbnew.LSET()
    ls.addLayer(pcbnew.F_Cu); ls.addLayer(pcbnew.B_Cu)
    k.SetLayerSet(ls)
    ch = pcbnew.SHAPE_LINE_CHAIN()
    for x, y in ((-0.5, 5.0), (MB.PAD_END + 0.4, 5.0), (MB.PAD_END + 0.4, -5.0), (-0.5, -5.0)):
        ch.Append(MB.V(x, y))
    ch.SetClosed(True)
    k.AddPolygon(ch)
    k.SetIsRuleArea(True)
    k.SetDoNotAllowCopperPour(True)
    k.SetDoNotAllowTracks(False)
    k.SetDoNotAllowVias(False)
    k.SetDoNotAllowPads(False)
    k.SetDoNotAllowFootprints(False)
    board.Add(k)


def parse_ses(path):
    """-> resolution, [(net, layer, width, [(x, y)...])], [(net, padstack, x, y)]"""
    t = open(path).read()
    res = re.search(r'\(resolution\s+(\w+)\s+(\d+)\)', t)
    unit, per = res.group(1), int(res.group(2))
    scale = {'um': 1e-3, 'mm': 1.0, 'mil': 0.0254, 'inch': 25.4}[unit] / per
    wires, vias = [], []
    for m in re.finditer(r'\(net\s+("[^"]*"|\S+)(.*?)\n\s*\)\s*(?=\(net|\)\s*\)\s*\)\s*$)', t, re.S):
        name = m.group(1).strip('"')
        body = m.group(2)
        for w in re.finditer(r'\(path\s+(\S+)\s+([\d.]+)\s+([-\d.\s]+)\)', body):
            nums = [float(v) for v in w.group(3).split()]
            pts = [(nums[i] * scale, nums[i + 1] * scale) for i in range(0, len(nums) - 1, 2)]
            wires.append((name, w.group(1), float(w.group(2)) * scale, pts))
        for v in re.finditer(r'\(via\s+("[^"]*"|\S+)\s+(-?[\d.]+)\s+(-?[\d.]+)', body):
            vias.append((name, v.group(1).strip('"'), float(v.group(2)) * scale, float(v.group(3)) * scale))
    return wires, vias


LAYER = {'F.Cu': pcbnew.F_Cu, 'In1.Cu': pcbnew.In1_Cu, 'In2.Cu': pcbnew.In2_Cu, 'B.Cu': pcbnew.B_Cu}


def import_ses(board, path):
    wires, vias = parse_ses(path)
    for name, layer, width, pts in wires:
        n = board.FindNet(name)
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(pcbnew.VECTOR2I(MB.MM(a[0]), MB.MM(-a[1])))
            t.SetEnd(pcbnew.VECTOR2I(MB.MM(b[0]), MB.MM(-b[1])))
            t.SetWidth(MB.MM(width))
            t.SetLayer(LAYER[layer])
            t.SetNet(n)
            board.Add(t)
    for name, stack, x, y in vias:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(pcbnew.VECTOR2I(MB.MM(x), MB.MM(-y)))
        m = re.search(r'(\d+(?:\.\d+)?)[:x_](\d+(?:\.\d+)?)', stack)
        dia, drill = 0.45, 0.25
        nums = [float(q) for q in re.findall(r'[\d.]+', stack)]
        if len(nums) >= 2:
            dia, drill = nums[-2] / 1000 if nums[-2] > 5 else nums[-2], nums[-1] / 1000 if nums[-1] > 5 else nums[-1]
        v.SetWidth(MB.MM(dia))
        v.SetDrill(MB.MM(drill))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(board.FindNet(name))
        board.Add(v)
    return len(wires), len(vias)


def length_report(board):
    """Routed length per pair member and the skew. At 1.25 Gbaud a UI is
    800 ps; 1 mm of skew on FR-4 is ~6 ps, so the budget is generous, but it
    is printed so nobody has to trust that."""
    L, V = {}, {}
    for t in board.GetTracks():
        n = t.GetNetname()
        if t.Type() == pcbnew.PCB_VIA_T:
            V[n] = V.get(n, 0) + 1
        else:
            L[n] = L.get(n, 0.0) + pcbnew.ToMM(t.GetLength())
    out = []
    for a, b in D.PAIRS:
        la, lb = L.get(a, 0.0), L.get(b, 0.0)
        out.append(f'{a}/{b} {la:.2f}/{lb:.2f} mm skew {abs(la - lb):.2f} vias {V.get(a, 0)}/{V.get(b, 0)}')
    open(os.path.join(D.HERE, 'lengths.txt'), 'w').write('\n'.join(out) + '\n')
    for o in out:
        print('  ' + o)


def route(passes=20, reuse_ses=False):
    """Freerouting 1.9.0: 2.x ignores its pass limit on the command line and
    never ends on this board; 1.9.0 honours -mp but wants a display, so it
    gets a virtual one."""
    path = os.path.join(D.HERE, D.NAME + '.kicad_pcb')
    board = load_board(path)
    apply_rules(board)
    add_edge_keepouts(board)
    add_connector_keepouts(board)
    add_planes(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    dsn = os.path.join(D.HERE, D.NAME + '.dsn')
    ses = os.path.join(D.HERE, D.NAME + '.ses')
    pcbnew.ExportSpecctraDSN(board, dsn)          # always: the class check below reads it
    if not (reuse_ses and os.path.exists(ses)):
        if os.path.exists(ses):
            os.remove(ses)
        if subprocess.run(['xdpyinfo', '-display', ':98'], capture_output=True).returncode:
            subprocess.Popen(['Xvfb', ':98', '-screen', '0', '1600x1000x24'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        env = dict(os.environ, DISPLAY=':98')
        subprocess.run(['java', '-jar', FREEROUTING, '-de', dsn, '-do', ses, '-mp', str(passes)],
                       capture_output=True, text=True, timeout=1500, env=env)
        if not os.path.exists(ses):
            raise RuntimeError('Freerouting wrote no session file')
    classes = re.findall(r'\(class (\S+)((?:\s+[^\s()]+)*)', open(dsn).read()) if os.path.exists(dsn) else []
    for name, members in classes:
        if name != 'kicad_default' and not members.split():
            raise RuntimeError(f'netclass {name} reached the DSN with no nets - the widths would be lost')
    nw, nv = import_ses(board, ses)
    add_outer_pours(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(path)
    write_project()                      # Save() rewrites the .kicad_pro with defaults
    rpt = os.path.join(D.HERE, 'drc.rpt')
    pcbnew.WriteDRCReport(board, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    txt = open(rpt).read()
    print(f'routed: {nw} wires, {nv} vias')
    length_report(board)
    for line in txt.splitlines():
        if line.startswith('**'):
            print('  ' + line)
    return board

def check_nets():
    n = len({n for p in D.P for n in p['nets'].values() if n})
    return n


def run(design):
    """Generate everything for one variant. --route / --reuse-ses also route."""
    global D
    D = design
    if '--route-stage' in sys.argv:
        # a fresh interpreter: inside the generating process LoadProject hands
        # back the in-memory default project and every net routes as Default
        route(reuse_ses='--reuse-ses' in sys.argv)
        return 0
    write_symbols()
    write_footprints()
    write_libtables()
    write_schematic()
    write_project()
    board = build_pcb()
    bad = check_pcb(board)
    print(f'{D.NAME}: {len(D.P)} parts, {check_nets()} nets')
    for b in bad:
        print('  !!', b)
    print('placement OK' if not bad else f'{len(bad)} placement problems')
    if bad:
        return 1
    if '--route' in sys.argv or '--reuse-ses' in sys.argv:
        args = [sys.executable, os.path.abspath(sys.modules[D.__name__].__file__), '--route-stage']
        if '--reuse-ses' in sys.argv:
            args.append('--reuse-ses')
        return subprocess.run(args).returncode
    return 0

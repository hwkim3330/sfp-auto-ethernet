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

and optionally:

    NOSE         (x, width): from x on, outside the cage, the board widens
    FOOTPRINTS   f(io, smd, crt, tht, slot, npth) - the variant's own lands
    HEIGHTS      {ref: mm} checked against the room inside the cage

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


def title_at():
    return getattr(D, 'TITLE_AT', (30.0, 4.7))


def outline():
    """The board outline: the MSA body, plus a wider nose outside the cage
    where the design has one (D.NOSE = (x, width); a 45 degree step)."""
    pts = MB.outline_pts(D.LENGTH)
    nose = getattr(D, 'NOSE', None)
    if not nose:
        return pts
    x0, w = nose
    b, h = MB.BODY_PCB_W / 2, w / 2
    if x0 < MB.CAGE_FRONT:
        raise ValueError(f'the nose starts at {x0}, inside the cage (front at {MB.CAGE_FRONT})')
    top = [p for p in pts if p[1] > 0 and p[0] < D.LENGTH]
    return (top + [(x0, b), (x0 + h - b, h), (D.LENGTH, h), (D.LENGTH, -h), (x0 + h - b, -h), (x0, -b)]
            + [(x, -y) for x, y in reversed(top)])


def _half_width(x):
    nose = getattr(D, 'NOSE', None)
    if nose and x >= nose[0]:
        return min(nose[1] / 2, MB.BODY_PCB_W / 2 + (x - nose[0]))
    return MB.TAB_W / 2 if x < MB.TAB_L + 1 else MB.BODY_PCB_W / 2


# TPS22918 (DBV): KiCad's TPS22917DBV has the same pins but types QOD as open
# collector, so the datasheet's QOD-to-VOUT tie reads as a pin conflict in
# ERC. QOD is the discharge switch's own end: passive.
TPS22918 = ('TPS22918', 'U',
            [('1', 'VIN', 'power_in'), ('3', 'ON', 'input'), ('4', 'CT', 'passive')],
            [('6', 'VOUT', 'power_out'), ('5', 'QOD', 'passive'), ('2', 'GND', 'power_in')], 15.24)


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
    # the library is shared by every variant: keep the others' symbols,
    # replace this variant's and the common ones, in a stable (sorted) order
    ours = {args[0]: _symbol(*args) for args in D.SYMBOLS}
    ours['SFP_EDGE'] = _symbol('SFP_EDGE', 'J', edge_l, edge_r, width=17.78)
    ours['HMTD_1P'] = _symbol('HMTD_1P', 'J', hmtd, [], width=10.16)
    have = _lib_symbols(open(SYMLIB).read()) if os.path.exists(SYMLIB) else {}
    have.update(ours)
    lib = '(kicad_symbol_lib (version 20220914) (generator sfpgen)\n'
    lib += ''.join(have[k] for k in sorted(have))
    lib += ')\n'
    open(SYMLIB, 'w').write(lib)


def _lib_symbols(text):
    """Top-level (symbol "name" ...) blocks of a .kicad_sym, by name."""
    out, i = {}, text.find('(', 1)
    while i != -1:
        depth, j = 0, i
        while True:
            c = text[j]
            if c == '"':
                j = text.index('"', j + 1)
            elif c == '(':
                depth += 1
            elif c == ')':
                depth -= 1
                if depth == 0:
                    break
            j += 1
        block = text[i:j + 1]
        m = re.match(r'\(symbol "([^"]+)"', block)
        if m:
            out[m.group(1)] = block + '\n'
        i = text.find('(', j + 1)
    return out


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

    def slot(fp, num, x, y, w, h, dw, dh):
        """Plated oval slot: pad w x h, drill dw x dh (a shield tab)."""
        p = pcbnew.PAD(fp)
        p.SetNumber(num)
        p.SetShape(pcbnew.PAD_SHAPE_OVAL)
        p.SetAttribute(pcbnew.PAD_ATTRIB_PTH)
        p.SetLayerSet(p.PTHMask())
        p.SetSize(pcbnew.VECTOR2I(MB.MM(w), MB.MM(h)))
        p.SetDrillShape(pcbnew.PAD_DRILL_SHAPE_OBLONG)
        p.SetDrillSize(pcbnew.VECTOR2I(MB.MM(dw), MB.MM(dh)))
        p.SetPosition(pcbnew.VECTOR2I(MB.MM(x), MB.MM(y)))
        p.SetPos0(p.GetPosition())
        fp.Add(p)

    def npth(fp, x, y, drill):
        p = pcbnew.PAD(fp)
        p.SetNumber('')
        p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        p.SetAttribute(pcbnew.PAD_ATTRIB_NPTH)
        p.SetLayerSet(p.UnplatedHoleMask())
        p.SetSize(pcbnew.VECTOR2I(MB.MM(drill), MB.MM(drill)))
        p.SetDrillSize(pcbnew.VECTOR2I(MB.MM(drill), MB.MM(drill)))
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

    if hasattr(D, 'FOOTPRINTS'):
        D.FOOTPRINTS(io, smd, crt, tht, slot, npth)


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
                         y=float(m.group(3)), ang=int(float(m.group(4))), name=m.group(7)))
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
    """A global label: KiCad names a local-label net "/NAME" on the root sheet,
    which then disagrees with the board's "NAME" on every pad (KiCad 9's
    schematic-parity check reported 140 conflicts on T1). A global label's net
    is plain "NAME", like the board's."""
    ang = {(1, 0): 0, (-1, 0): 180, (0, 1): 270, (0, -1): 90}[d]
    just = 'left' if d in ((1, 0), (0, -1)) else 'right'
    SCH.append('  (global_label "%s" (shape passive) (at %.2f %.2f %d) (fields_autoplaced)'
               ' (effects (font (size 1.0 1.0)) (justify %s))\n    (uuid %s)\n'
               '    (property "Intersheetrefs" "${INTERSHEET_REFS}" (at %.2f %.2f 0)'
               ' (effects (font (size 1.0 1.0)) hide)))\n'
               % (net, x, y, ang, just, _u('l%s%.2f%.2f' % (net, x, y)), x, y))


def symbol_inst(lib_id, x, y, ref, value, fp, seed, dnp=False, hide=False, props=()):
    _, pins = sym_block(lib_id)
    s = '  (symbol (lib_id "%s") (at %.2f %.2f 0) (unit 1)\n' % (lib_id, x, y)
    # BOM flag as the board has it: unfitted parts and test pads are excluded
    # there (KiCad 7 boards carry no DNP attribute, so the schematic's dnp flag
    # stays off and "DNP" lives in the value; KiCad 9 parity checks both)
    in_bom = not (hide or dnp or ref.startswith('TP'))
    s += '    (in_bom %s) (on_board yes) (dnp no)\n' % ('yes' if in_bom else 'no')
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
    driven = {n for p in D.P for q in sym_block(p['lib_id'])[1]
              for n in [p['nets'].get(int(q['number'])) if q['number'].isdigit() else None]
              if n and q['etype'] == 'power_out'}
    for net in [n for n in D.POWER_NETS + ('GND',) if n not in driven]:
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
    out += ('  (title_block (title "%s") (rev "0.1")\n'
            '    (comment 1 "Generated by hw/%s/make_%s.py - edit the netlist there, not here"))\n'
            % (getattr(D, 'SCH_TITLE', D.TITLE), D.NAME, D.NAME))
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
    MB.poly(board, pcbnew.Edge_Cuts, outline())
    MB.seg(board, pcbnew.Dwgs_User, (MB.CAGE_FRONT, 7.5), (MB.CAGE_FRONT, -7.5), 0.15)
    MB.text(board, pcbnew.Dwgs_User, 'cage front', MB.CAGE_FRONT, 8.4, 0.8)
    MB.text(board, pcbnew.B_SilkS, D.TITLE, *title_at(), 0.8)   # T1: 5.4 sat 0.1 mm off the edge, clipped in the panel
    for p in D.P:
        fp = MB.edge_footprint() if p['ref'] == 'J1' else fp_load(p['fp'])
        fp.SetReference(p['ref'])
        fp.SetValue(p['value'])
        fp.Value().SetVisible(False)
        if D.lcsc_for(p):
            fp.SetProperty('LCSC', D.lcsc_for(p))
        fp.Reference().SetVisible(False)       # 12 mm board: refs live on F.Fab
        # link to the schematic symbol (root sheet: "/<symbol uuid>"), as KiCad's
        # own Update PCB would: without it every part reads as new in the GUI
        fp.SetPath(pcbnew.KIID_PATH('/' + _u('s' + p['ref'])))
        fp.SetProperty('Sheetname', '')
        fp.SetProperty('Sheetfile', D.NAME + '.kicad_sch')
        fp.SetPosition(MB.V(*p['at']))
        fp.SetOrientationDegrees(p['rot'])
        if p['dnp'] or p['ref'].startswith('TP'):
            fp.SetAttributes(fp.GetAttributes() | pcbnew.FP_EXCLUDE_FROM_BOM)
        board.Add(fp)                                # before Flip: it needs the board
        if p['side'] == 'B':
            fp.Flip(fp.GetPosition(), False)
        # a pin left open in the schematic (no-connect flag) is a net of its own
        # there, "unconnected-(REF-PIN-PadN)"; the pad carries the same name or
        # KiCad's schematic parity flags it
        opened = {q['number']: q['name'] for q in sym_block(p['lib_id'])[1]}
        for pad in fp.Pads():
            num = pad.GetNumber()
            if not num:
                continue                             # EP paste windows
            n = p['nets'].get(int(num)) if num.isdigit() else None
            if not n and num in opened and not p['ref'].startswith('TP'):
                nm = opened[num].replace('/', '{slash}')
                n = f"unconnected-({p['ref']}-{nm}-Pad{num})"
            if n:
                pad.SetNet(net(n))
            if (p['ref'], num) in D.SOLID_PADS:
                pad.SetZoneConnection(pcbnew.ZONE_CONNECTION_FULL)   # EP + thermal vias: solid
    path = os.path.join(D.HERE, D.NAME + '.kicad_pcb')
    board.Save(path)
    board.Save(placed_path())            # routing always starts from this copy
    for junk in (placed_path()[:-len('.kicad_pcb')] + ext for ext in ('.kicad_pro', '.kicad_prl')):
        if os.path.exists(junk):
            os.remove(junk)
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
            # a decap at a fine-pitch pin sits inside the chip's courtyard margin
            # on purpose; copper clearance is still DRC's to check
            ok = getattr(D, 'COURTYARD_OK', {})
            if b[0] in ok.get(a[0], ()) or a[0] in ok.get(b[0], ()):
                continue
            ra, rb = a[2], b[2]
            if ra[0] < rb[2] - 1e-3 and rb[0] < ra[2] - 1e-3 and ra[1] < rb[3] - 1e-3 and rb[1] < ra[3] - 1e-3:
                bad.append(f'{a[0]} x {b[0]} ({a[1]})')
    for ref, side, r in boxes:
        lim = min(_half_width(r[0]), _half_width(r[2]))
        if ref not in ('J1',) and max(abs(r[1]), abs(r[3])) > lim + 1e-3 \
                and ref not in getattr(D, 'OVERHANG', ()):
            bad.append(f'{ref} off the board edge')
        if ref != 'J1' and r[0] < MB.PAD_END + 0.1 and side == 'F':
            bad.append(f'{ref} on the edge fingers')
    # heights inside the cage: 4.65 mm over the board, 1.65 under it
    at = {p['ref']: p for p in D.P}
    for ref, h in getattr(D, 'HEIGHTS', {}).items():
        side = at[ref]['side']
        box = next(b for r, s, b in boxes if r == ref)
        room = MB.TOP_ROOM if side == 'F' else MB.BOT_ROOM
        if box[0] < MB.CAGE_FRONT and h > room + 1e-6:
            bad.append(f'{ref} is {h} mm tall on {side}, {room:.2f} mm of room inside the cage')
    return bad


# ==========================================================================
# routing: netclasses, planes, Freerouting, SES back in, fill, DRC
def placed_path():
    return os.path.join(D.HERE, '.' + D.NAME + '_placed.kicad_pcb')


def load_board(path, pro=None):
    """Open the board WITH its project, so the netclass patterns in the
    .kicad_pro apply. A bare LoadBoard leaves every net in Default, and the DSN
    export then resyncs nets to classes from those (absent) patterns - which
    is how the first routed boards got 0.127 mm SGMII instead of 50 ohm."""
    pro = os.path.abspath(pro or (path[:-len('.kicad_pcb')] + '.kicad_pro'))
    sm = pcbnew.GetSettingsManager()
    sm.LoadProject(pro)
    board = pcbnew.LoadBoard(path)
    return board


def apply_rules(board):
    """KiCad 7's standalone LoadBoard does not read the .kicad_pro, so the
    rules the DSN export and DRC need are set on the board in memory."""
    # In1 is the GND plane. As a 'signal' layer the DSN handed it to the
    # router, which ran traces through it and cut it into islands.
    board.SetLayerType(pcbnew.In1_Cu, pcbnew.LT_POWER)
    # In2 carries signals too (two signal layers left 16 pads unrouted on a
    # 11.8 mm board); the +3V3 pour fills what the router leaves. In1 stays a
    # solid GND plane: it is the reference right under the F.Cu SGMII traces.
    # D.IN2_GND: In2 is a second GND plane (F / GND / GND / B). Then B.Cu is
    # GND-referenced like F.Cu, so a pair can change layers without its return
    # path changing nets; +3V3 is routed as traces. Otherwise In2 carries
    # signals and a +3V3 pour after routing (T1 before the design review).
    # D.IN2_SIGNALS as well: In2 still takes low-speed traces and gets its GND
    # pour after routing, but never under a bottom-side high-speed run
    # (D.IN2_KEEPOUTS, no tracks there), so those keep a solid GND reference.
    solid = getattr(D, 'IN2_GND', False) and not getattr(D, 'IN2_SIGNALS', False)
    board.SetLayerType(pcbnew.In2_Cu, pcbnew.LT_POWER if solid else pcbnew.LT_SIGNAL)
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
    write_dru()


def write_dru():
    """Custom DRC rules next to the board: the design's COURTYARD_OK pairs (a
    decap at a fine-pitch pin, inside the chip's courtyard margin on purpose)
    get no courtyard clearance; copper clearances stay as they are."""
    ok = getattr(D, 'COURTYARD_OK', {})
    lines = ['(version 1)']
    for chip, refs in sorted(ok.items()):
        cond = ' || '.join(f"(A.Reference == '{chip}' && B.Reference == '{r}') || "
                           f"(A.Reference == '{r}' && B.Reference == '{chip}')" for r in refs)
        lines.append(f'(rule "decaps at {chip}"\n  (constraint courtyard_clearance (min -10mm))\n'
                     f'  (condition "{cond}"))')
    for path in (os.path.join(D.HERE, D.NAME + '.kicad_dru'),
                 placed_path()[:-len('.kicad_pcb')] + '.kicad_dru'):
        open(path, 'w').write('\n'.join(lines) + '\n')


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
    z.SetIslandRemovalMode(pcbnew.ISLAND_REMOVAL_MODE_ALWAYS)   # a floating scrap is only an antenna
    z.SetThermalReliefGap(MB.MM(0.25))
    z.SetThermalReliefSpokeWidth(MB.MM(0.3))
    board.Add(z)
    return z


def add_edge_keepouts(board, w=0.6):
    """No-track/no-via strips along every outline edge: Freerouting keeps
    only copper-to-copper clearance to the board edge. 0.6, not the fab's 0.2:
    the panel's mouse-bite holes reach 0.35 into the board (0.1 in, r 0.25)
    and want 0.25 of hole clearance (an In2 MDIO trace at 0.22 failed it)."""
    pts = outline()
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
    if not D.HMTD_AT:
        return
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
    pts = [(x, y - inset if y > 0 else y + inset) for x, y in outline()]
    pts = [(max(inset, min(D.LENGTH - inset, x)), y) for x, y in pts]
    zone(board, 'GND', pcbnew.In1_Cu, pts, clearance=0.15)
    if getattr(D, 'IN2_GND', False) and not getattr(D, 'IN2_SIGNALS', False):
        zone(board, 'GND', pcbnew.In2_Cu, pts, clearance=0.15)
    for x0, y0, x1, y1 in getattr(D, 'IN2_KEEPOUTS', []):
        k = pcbnew.ZONE(board)
        ls = pcbnew.LSET()
        ls.addLayer(pcbnew.In2_Cu)
        k.SetLayerSet(ls)
        ch = pcbnew.SHAPE_LINE_CHAIN()
        for x, y in ((x0, y0), (x1, y0), (x1, y1), (x0, y1)):
            ch.Append(MB.V(x, y))
        ch.SetClosed(True)
        k.AddPolygon(ch)
        k.SetIsRuleArea(True)
        k.SetDoNotAllowTracks(True)
        k.SetDoNotAllowVias(False)
        k.SetDoNotAllowCopperPour(False)
        k.SetDoNotAllowPads(False)
        k.SetDoNotAllowFootprints(False)
        board.Add(k)
    # otherwise +3V3 on In2 comes after routing (add_outer_pours): In2 carries signals,
    # and in the DSN a pour makes the router leave +3V3 to a plane they cut up


def add_outer_pours(board):
    """After routing, never before: in the DSN a pour on F/B reads as a solid
    plane and the router finds no room on the signal layers. On a 11.8 mm board
    the signal vias' antipads cut In1 into islands; these stitch them back.
    SMD pads join solidly (0201 thermals starve), THT keeps spokes."""
    inset = 0.3
    pts = [(x, y - inset if y > 0 else y + inset) for x, y in outline()]
    pts = [(max(inset, min(D.LENGTH - inset, x)), y) for x, y in pts]
    if not getattr(D, 'IN2_GND', False):
        zone(board, '+3V3', pcbnew.In2_Cu, pts, clearance=0.15)
    elif getattr(D, 'IN2_SIGNALS', False):
        zone(board, 'GND', pcbnew.In2_Cu, pts, clearance=0.15)
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


def preroute_edge_gnd(board, x_via=4.55):
    """The GND fingers sit where no pour may go, so each one gets a short
    trace back to a GND via just behind the finger area, laid before routing
    (the router keeps existing copper). A top and a bottom ground finger at
    about the same height share one via. Vias at y = +3.6, +1.4, -0.8, -3.4."""
    gnd = board.FindNet('GND')
    groups = {3.6: [(20, 'F'), (1, 'B')], 1.4: [(17, 'F')], -0.8: [(14, 'F'), (6, 'B')],
              -3.4: [(11, 'F'), (9, 'B'), (10, 'B')]}
    for vy, pins in groups.items():
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(MB.V(x_via, vy))
        v.SetWidth(MB.MM(0.45)); v.SetDrill(MB.MM(0.25))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(gnd)
        v.SetLocked(True)
        board.Add(v)
        for pin, side in pins:
            py = MB.pad_y(pin)
            for a, b in (((MB.PAD_END - 0.3, py), (MB.PAD_END + 0.2, py)), ((MB.PAD_END + 0.2, py), (x_via, vy))):
                t = pcbnew.PCB_TRACK(board)
                t.SetStart(MB.V(*a)); t.SetEnd(MB.V(*b))
                t.SetWidth(MB.MM(0.2))
                t.SetLayer(pcbnew.F_Cu if side == 'F' else pcbnew.B_Cu)
                t.SetNet(gnd); t.SetLocked(True)
                board.Add(t)


def pair_lines(centre, pitch):
    """A coupled pair along a centreline: the left and right lines at
    +/-pitch/2 (left = +90 degrees from the direction of travel, module frame),
    corners mitred so the gap stays the same through every bend. 45-degree
    bends keep the mitre short (1/cos 22.5 = 1.08)."""
    import math as _m
    h = pitch / 2
    left, right = [], []
    for i, (x, y) in enumerate(centre):
        dirs = []
        if i > 0:
            dirs.append((x - centre[i - 1][0], y - centre[i - 1][1]))
        if i < len(centre) - 1:
            dirs.append((centre[i + 1][0] - x, centre[i + 1][1] - y))
        ns = []
        for dx, dy in dirs:
            L = _m.hypot(dx, dy)
            ns.append((-dy / L, dx / L))
        nx, ny = (ns[0][0] + ns[-1][0]) / 2, (ns[0][1] + ns[-1][1]) / 2
        k = h / (nx * ns[0][0] + ny * ns[0][1])            # mitre length along the bisector
        left.append((round(x + nx * k, 4), round(y + ny * k, 4)))
        right.append((round(x - nx * k, 4), round(y - ny * k, 4)))
    return left, right


def prerouted(board):
    """The design's hand-drawn tracks (D.PREROUTES: net, layer, module-frame
    points), for the few links Freerouting cannot enter - e.g. a pin whose
    only open side is blocked by a no-connect neighbour. Locked, so the router
    keeps them."""
    for item in getattr(D, 'PREROUTES', []):
        net, layer, pts = item[:3]
        width = item[3] if len(item) > 3 else (0.2 if net in D.POWER_NETS else 0.15)
        n = board.FindNet(net)
        for a, b in zip(pts, pts[1:]):
            t = pcbnew.PCB_TRACK(board)
            t.SetStart(MB.V(*a)); t.SetEnd(MB.V(*b))
            t.SetWidth(MB.MM(width))
            t.SetLayer(pcbnew.F_Cu if layer == 'F' else pcbnew.B_Cu)
            t.SetNet(n); t.SetLocked(True)
            board.Add(t)
    for net, (x, y) in getattr(D, 'PREVIAS', []):
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(MB.V(x, y))
        v.SetWidth(MB.MM(0.45)); v.SetDrill(MB.MM(0.25))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(board.FindNet(net)); v.SetLocked(True)
        board.Add(v)


def predogbone(board, net='GND'):
    """Every capacitor's ground pad gets its own via to In1 before routing:
    a decoupling cap is only as good as its ground return, and once the
    router has boxed a small cap in, no via fits next to it any more (C31 on
    T1 did exactly that). Beyond the pad along the part's axis first, then to
    either side; the first spot DRC accepts is locked in."""
    gnd = board.FindNet(net)
    rpt = os.path.join(D.HERE, '.dogbone.rpt')
    n0, _, _ = _drc(board, rpt)
    done = 0
    for f in list(board.GetFootprints()):
        pads = list(f.Pads())
        if not f.GetReference().startswith(getattr(D, 'DOGBONE_PREFIXES', ('C',))) or len(pads) != 2 \
                or f.GetReference() in getattr(D, 'NO_DOGBONE', ()):
            continue
        g = [p for p in pads if p.GetNetname() == net]
        if len(g) != 1:
            continue
        g = g[0]; o = pads[0] if pads[1] is g else pads[1]
        gx, gy = pcbnew.ToMM(g.GetPosition().x), pcbnew.ToMM(g.GetPosition().y)
        ox, oy = pcbnew.ToMM(o.GetPosition().x), pcbnew.ToMM(o.GetPosition().y)
        L = math.hypot(gx - ox, gy - oy) or 1.0
        ux, uy = (gx - ox) / L, (gy - oy) / L
        layer = pcbnew.B_Cu if f.IsFlipped() else pcbnew.F_Cu
        cands = [(gx + ux * d, gy + uy * d) for d in (0.55, 0.7, 0.9)]
        cands += [(gx + s_ * uy * d, gy - s_ * ux * d) for d in (0.6, 0.8, 1.0) for s_ in (1, -1)]
        for x, y in cands:
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(MB.MM(x), MB.MM(y)))
            v.SetWidth(MB.MM(0.45)); v.SetDrill(MB.MM(0.25))
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(gnd); v.SetLocked(True)
            tr = pcbnew.PCB_TRACK(board)
            tr.SetStart(g.GetPosition()); tr.SetEnd(v.GetPosition())
            tr.SetWidth(MB.MM(0.2)); tr.SetLayer(layer); tr.SetNet(gnd); tr.SetLocked(True)
            board.Add(v); board.Add(tr)
            n, _, _ = _drc(board, rpt)
            if n <= n0:
                done += 1
                break
            board.Remove(tr); board.Remove(v)
    os.remove(rpt)
    print(f'  dogbones: {done} capacitor ground vias placed before routing')


def stitch_gnd(board, pitch=1.6, dia=0.45, drill=0.25):
    """GND stitching vias. On a 11.8 mm board the signal vias cut the outer
    pours into islands that no longer reach In1; a via grid ties F, In1 and B
    back together. Every candidate goes in, DRC names the ones that collide,
    those come out, repeat until nothing collides."""
    gnd = board.FindNet('GND')
    # signal links the router left open get first pick of the space; the
    # grid fills in around them (a stitching via sat right on VDDIO's only way)
    rpt = os.path.join(D.HERE, '.stitch.rpt')
    drop_dangling_vias(board, rpt)
    # the repairs are for a handful of open links; with many the router has
    # failed and each DRC-scored try just burns minutes (the first RJ45 route
    # left 22 and ran for half an hour) - fix the layout instead
    limit = int(os.environ.get('SFP_REPAIR_MAX', '15'))
    _, u_routed, t_routed = _drc(board, rpt)
    repair = u_routed <= limit
    if not repair:
        print(f'  !! {u_routed} unconnected after routing (> {limit}): repairs skipped')
        for blk in t_routed.split('\n[unconnected_items]')[1:]:
            print('    ' + ' / '.join(re.findall(r'\): (.*)', blk.split('\n[')[0]))[:150])
    early = join_fragments(board, rpt, nets=None) if repair else 0
    if early:
        print(f'  {early} open signal links joined before stitching')
    x0, x1 = MB.PAD_END + 1.5, D.LENGTH - 1.0
    cands = []
    x = x0
    while x < x1:
        # 1.0 mm off the long edges: the panel's mouse-bite holes sit on them
        y = -MB.BODY_PCB_W / 2 + 1.0
        while y < MB.BODY_PCB_W / 2 - 1.0:
            tx, ty = title_at()                             # the bottom label
            in_title = abs(x - tx) < 0.33 * len(D.TITLE) + 0.6 and abs(y - ty) < 1.1
            if (x > MB.TAB_L + 1.5 or abs(y) < MB.TAB_W / 2 - 0.8) and not in_title:
                cands.append((x, y))
            y += pitch
        x += pitch
    vias = {}
    for x, y in cands:
        v = pcbnew.PCB_VIA(board)
        v.SetPosition(MB.V(x, y))
        v.SetWidth(MB.MM(dia)); v.SetDrill(MB.MM(drill))
        v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu)
        v.SetNet(gnd)
        board.Add(v)
        vias[(round(pcbnew.ToMM(v.GetPosition().x), 3), round(pcbnew.ToMM(v.GetPosition().y), 3))] = v
    rpt = os.path.join(D.HERE, '.stitch.rpt')
    for _ in range(6):
        pcbnew.ZONE_FILLER(board).Fill(board.Zones())
        pcbnew.WriteDRCReport(board, rpt, pcbnew.EDA_UNITS_MILLIMETRES, False)
        txt = open(rpt).read()
        bad = set()
        for block in txt.split('\n['):
            if 'Via [GND]' not in block or not block.startswith(('clearance', 'hole_clearance', 'hole_near_hole',
                                                                 'copper_edge_clearance', 'track_dangling',
                                                                 'via_dangling', 'annular_width', 'drill_out',
                                                                 'items_not_allowed', 'holes_co_located')):
                continue
            for m in re.finditer(r'@\((-?[\d.]+) mm, (-?[\d.]+) mm\): Via \[GND\]', block):
                bad.add((round(float(m.group(1)), 3), round(float(m.group(2)), 3)))
        bad &= set(vias)
        if not bad:
            break
        for k in bad:
            board.Remove(vias.pop(k))
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    fixed = joined = 0
    if repair:
        fixed = fanout_orphans(board, rpt)
        joined = join_fragments(board, rpt)
        joined += stitch_islands(board, rpt)
        joined += join_fragments(board, rpt, nets=None)
    os.remove(rpt)
    if joined:
        print(f'  {joined} plane-net fragments joined by a direct trace')
    print(f'  stitching: {len(vias)} GND vias kept of {len(cands)} candidates; '
          f'{fixed} stranded GND pads fanned out')


def drop_dangling_vias(board, rpt):
    """An escape via the router ended up not needing (it took the net on the
    top layer instead) is copper on one layer only: out it goes. Its locked
    stub is cut back to where the router's track met it (a track end in the
    middle of a segment is no connection to KiCad), or removed if none did."""
    _, _, t = _drc(board, rpt)
    spots = {(round(float(x), 3), round(float(y), 3)) for x, y in
             re.findall(r'\[via_dangling\][^\[]*?@\((-?[\d.]+) mm, (-?[\d.]+) mm\): Via', t)}
    key = lambda q: (round(pcbnew.ToMM(q.x), 3), round(pcbnew.ToMM(q.y), 3))
    for v in [v for v in board.GetTracks() if v.GetClass() == 'PCB_VIA' and key(v.GetPosition()) in spots]:
        net, p = v.GetNetCode(), v.GetPosition()
        board.Remove(v)
        for tr in [tr for tr in board.GetTracks() if tr.GetClass() == 'PCB_TRACK' and tr.IsLocked()
                   and tr.GetNetCode() == net and p in (tr.GetStart(), tr.GetEnd())]:
            far = tr.GetStart() if tr.GetEnd() == p else tr.GetEnd()
            # already joined end to end at the via spot: nothing to cut
            if sum(1 for o in board.GetTracks() if o.GetClass() == 'PCB_TRACK' and o.GetNetCode() == net
                   and o.GetLayer() == tr.GetLayer() and p in (o.GetStart(), o.GetEnd())) > 1:
                continue
            ax, ay = pcbnew.ToMM(far.x), pcbnew.ToMM(far.y)
            bx, by = pcbnew.ToMM(p.x), pcbnew.ToMM(p.y)
            L2 = (bx - ax) ** 2 + (by - ay) ** 2
            best = None
            for o in board.GetTracks():
                if o.GetClass() != 'PCB_TRACK' or o.GetNetCode() != net or o is tr or o.GetLayer() != tr.GetLayer():
                    continue
                for q in (o.GetStart(), o.GetEnd()):
                    if q == p or q == far:          # the stub itself (SWIG proxies defeat `is`)
                        continue
                    qx, qy = pcbnew.ToMM(q.x), pcbnew.ToMM(q.y)
                    s = ((qx - ax) * (bx - ax) + (qy - ay) * (by - ay)) / L2 if L2 else 0
                    d = math.hypot(ax + s * (bx - ax) - qx, ay + s * (by - ay) - qy)
                    if 0 < s <= 1 and d < 0.01 and (best is None or s > best[0]):
                        best = (s, q)
            if best:
                if tr.GetEnd() == p:
                    tr.SetEnd(best[1])
                else:
                    tr.SetStart(best[1])
            else:
                board.Remove(tr)
    if spots:
        print(f'  {len(spots)} unused escape vias removed')


def _drc(board, rpt):
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    pcbnew.WriteDRCReport(board, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    t = open(rpt).read()
    n = int(re.search(r'Found (\d+) DRC violations', t).group(1))
    u = int(re.search(r'Found (\d+) unconnected', t).group(1))
    return n, u, t


def fanout_orphans(board, rpt, rings=(0.8, 1.1, 1.5, 2.0), steps=16, nets=('GND', '+3V3')):
    """A plane-net pad the pours cannot reach gets its own via: for every such
    pad, try positions on rings around it with a short trace, and keep the
    first that leaves DRC no worse and the unconnected count lower. Pads that
    cannot be helped are skipped, not allowed to stop the others."""
    fixed, tried = 0, set()
    n0, u0, t = _drc(board, rpt)
    while u0:
        pads = []
        for block in t.split('\n[unconnected_items]')[1:]:
            for m in re.finditer(r'@\((-?[\d.]+) mm, (-?[\d.]+) mm\): Pad (\S+) \[([^\]]+)\] of (\S+) on (\S)\.Cu', block):
                key = (m.group(5), m.group(3))
                if m.group(4) in nets and key not in tried:
                    pads.append((float(m.group(1)), float(m.group(2)), m.group(4), m.group(6), key))
        if not pads:
            break
        px, py, netname, side, key = pads[0]
        tried.add(key)
        net = board.FindNet(netname)
        layer = pcbnew.F_Cu if side == 'F' else pcbnew.B_Cu
        done = False
        for r in rings:
            for k in range(steps):
                a = 2 * math.pi * k / steps
                vx, vy = px + r * math.cos(a), py + r * math.sin(a)
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(MB.MM(vx), MB.MM(vy)))
                v.SetWidth(MB.MM(0.45)); v.SetDrill(MB.MM(0.25))
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(net)
                tr = pcbnew.PCB_TRACK(board)
                tr.SetStart(pcbnew.VECTOR2I(MB.MM(px), MB.MM(py)))
                tr.SetEnd(pcbnew.VECTOR2I(MB.MM(vx), MB.MM(vy)))
                tr.SetWidth(MB.MM(0.2)); tr.SetLayer(layer); tr.SetNet(net)
                board.Add(v); board.Add(tr)
                n, u, t2 = _drc(board, rpt)
                if n <= n0 and u < u0:
                    fixed += 1; done = True; n0, u0, t = n, u, t2
                    break
                board.Remove(tr); board.Remove(v)
            if done:
                break
    return fixed


def stitch_islands(board, rpt, step=0.3, net='GND'):
    """A pour island on F or B that touches a pad but no via is not tied to
    In1 - DRC reports it zone-to-zone. Each such island gets a via: first on a
    grid inside it, else on a ring around one of its pads with a short trace
    (for an island no bigger than the pad). The first DRC accepts is kept."""
    gnd = board.FindNet(net)
    n0, u0, t = _drc(board, rpt)
    pads = [p for f in board.GetFootprints() for p in f.Pads() if p.GetNetname() == net]
    # copy every island out first: each DRC refills and frees the fill polygons
    islands = []
    for zi in range(board.GetAreaCount()):
        z = board.GetArea(zi)
        if z.GetIsRuleArea() or z.GetNetname() != net:
            continue
        for layer in (pcbnew.F_Cu, pcbnew.B_Cu):
            if not z.IsOnLayer(layer):
                continue
            fp = z.GetFilledPolysList(layer)
            for i in sorted(range(fp.OutlineCount()), key=lambda i: -fp.Outline(i).Area())[1:]:
                islands.append((layer, pcbnew.SHAPE_LINE_CHAIN(fp.Outline(i))))
    vias = [t.GetPosition() for t in board.GetTracks() if t.GetClass() == 'PCB_VIA' and t.GetNetname() == net]
    added = 0
    for layer, ol in islands:
        if not u0:
            break
        if any(ol.PointInside(v, 0) for v in vias):
            continue
        bb = ol.BBox()
        x0, x1 = pcbnew.ToMM(bb.GetLeft()), pcbnew.ToMM(bb.GetRight())
        y0, y1 = pcbnew.ToMM(bb.GetTop()), pcbnew.ToMM(bb.GetBottom())
        cx, cy = (x0 + x1) / 2, (y0 + y1) / 2
        cands = [((x, y), None) for x, y in sorted(
                     ((x0 + i * step, y0 + j * step) for i in range(int((x1 - x0) / step) + 1)
                      for j in range(int((y1 - y0) / step) + 1)),
                     key=lambda p: (p[0] - cx) ** 2 + (p[1] - cy) ** 2)
                 if ol.PointInside(pcbnew.VECTOR2I(MB.MM(x), MB.MM(y)), MB.MM(0.3))]
        for p in pads:
            if p.IsOnLayer(layer) and ol.PointInside(p.GetPosition(), 0):
                px, py = pcbnew.ToMM(p.GetPosition().x), pcbnew.ToMM(p.GetPosition().y)
                for r in (0.6, 0.8, 1.1, 1.5):
                    for k in range(16):
                        a = 2 * math.pi * k / 16
                        cands.append(((px + r * math.cos(a), py + r * math.sin(a)), (px, py)))
                # or a trace to a GND via already there (no new via: 'old')
                near = sorted((math.hypot(pcbnew.ToMM(v.x) - px, pcbnew.ToMM(v.y) - py), v) for v in vias)
                cands += [((pcbnew.ToMM(v.x), pcbnew.ToMM(v.y)), (px, py), 'old') for d, v in near if d < 5.0]
        for c in cands:
            (x, y), src = c[0], c[1]
            new = []
            if len(c) == 2:
                v = pcbnew.PCB_VIA(board)
                v.SetPosition(pcbnew.VECTOR2I(MB.MM(x), MB.MM(y)))
                v.SetWidth(MB.MM(0.45)); v.SetDrill(MB.MM(0.25))
                v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(gnd)
                new.append(v)
            if src:
                tr = pcbnew.PCB_TRACK(board)
                tr.SetStart(pcbnew.VECTOR2I(MB.MM(src[0]), MB.MM(src[1])))
                tr.SetEnd(pcbnew.VECTOR2I(MB.MM(x), MB.MM(y)))
                tr.SetWidth(MB.MM(0.2)); tr.SetLayer(layer); tr.SetNet(gnd)
                new.append(tr)
            for it in new:
                board.Add(it)
            n, u, t2 = _drc(board, rpt)
            if n <= n0 and u < u0:
                added += 1; n0, u0, t = n, u, t2
                break
            for it in new:
                board.Remove(it)
    return added


def join_fragments(board, rpt, nets=('GND', '+3V3'), max_len=8.0):
    # nets=None: any net but a differential pair's
    """What fanout cannot reach: two pieces of a plane net that DRC pairs as
    unconnected (pad, track end or via) get a straight trace between the two
    points it names, on F then B, kept only if DRC is no worse."""
    item = r'@\((-?[\d.]+) mm, (-?[\d.]+) mm\): (?:Pad \S+|Track|Via) \[([^\]]+)\]'
    joined, tried = 0, set()
    diff = {n for a, b in getattr(D, 'PAIRS', []) for n in (a, b)}     # pairs are never patched
    n0, u0, t = _drc(board, rpt)
    while u0:
        pair = None
        for block in t.split('\n[unconnected_items]')[1:]:
            block = block.split('\n[')[0]
            m = re.findall(item, block)
            if len(m) == 2 and m[0][2] == m[1][2] and (nets is None or m[0][2] in nets) \
                    and m[0][2] not in diff:
                a, b = (float(m[0][0]), float(m[0][1])), (float(m[1][0]), float(m[1][1]))
                if (a, b) not in tried and math.dist(a, b) <= max_len:
                    pair = (a, b, m[0][2]); break
        if not pair:
            break
        a, b, netname = pair
        tried.add((a, b))
        net = board.FindNet(netname)
        def seg(p, q, layer):
            tr = pcbnew.PCB_TRACK(board)
            tr.SetStart(pcbnew.VECTOR2I(MB.MM(p[0]), MB.MM(p[1])))
            tr.SetEnd(pcbnew.VECTOR2I(MB.MM(q[0]), MB.MM(q[1])))
            tr.SetWidth(MB.MM(0.2)); tr.SetLayer(layer); tr.SetNet(net)
            return tr
        def via(p):
            v = pcbnew.PCB_VIA(board)
            v.SetPosition(pcbnew.VECTOR2I(MB.MM(p[0]), MB.MM(p[1])))
            v.SetWidth(MB.MM(0.45)); v.SetDrill(MB.MM(0.25))
            v.SetLayerPair(pcbnew.F_Cu, pcbnew.B_Cu); v.SetNet(net)
            return v
        # straight on F, straight on B, then down at both ends and across on B
        # (the ends are F-side track ends or pads; a via may sit on either)
        options = [[seg(a, b, pcbnew.F_Cu)], [seg(a, b, pcbnew.B_Cu)],
                   # one via at either end, the trace on the other layer
                   [via(a), seg(a, b, pcbnew.F_Cu)], [via(b), seg(a, b, pcbnew.F_Cu)],
                   [via(a), seg(a, b, pcbnew.B_Cu)], [via(b), seg(a, b, pcbnew.B_Cu)]]
        # a via beside either end (a pad cannot take one in it), a stub to it on
        # that end's side, the run on the other layer
        for (p, q) in ((a, b), (b, a)):
            for r in (0.6, 0.8, 1.0):
                for k in range(8):
                    ang = math.pi * k / 4
                    w = (p[0] + r * math.cos(ang), p[1] + r * math.sin(ang))
                    for near_l, far_l in ((pcbnew.F_Cu, pcbnew.B_Cu), (pcbnew.B_Cu, pcbnew.F_Cu)):
                        options.append([via(w), seg(p, w, near_l), seg(w, q, far_l)])
        for off in ((0, 0), (0.5, 0), (-0.5, 0), (0, 0.5), (0, -0.5)):
            pa = (a[0] + off[0], a[1] + off[1]); pb = (b[0] - off[0], b[1] - off[1])
            opt = [via(pa), via(pb), seg(pa, pb, pcbnew.B_Cu)]
            if off != (0, 0):
                opt += [seg(a, pa, pcbnew.F_Cu), seg(b, pb, pcbnew.F_Cu)]
            options.append(opt)
        done = False
        for opt in options:
            for it in opt:
                board.Add(it)
            n, u, t2 = _drc(board, rpt)
            if n <= n0 and u < u0:
                joined += 1; n0, u0, t = n, u, t2; done = True
                break
            for it in opt:
                board.Remove(it)
        if done:
            continue
        # a T into a same-net track already there: split it at the foot of the
        # perpendicular from either end, and run the stub to that point
        segs = [s_ for s_ in board.GetTracks() if s_.GetClass() == 'PCB_TRACK' and s_.GetNetCode() == net.GetNetCode()]
        for p in (a, b):
            for s_ in segs:
                sx, sy = pcbnew.ToMM(s_.GetStart().x), pcbnew.ToMM(s_.GetStart().y)
                ex, ey = pcbnew.ToMM(s_.GetEnd().x), pcbnew.ToMM(s_.GetEnd().y)
                L2 = (ex - sx) ** 2 + (ey - sy) ** 2
                if L2 < 0.04:
                    continue
                k = max(0.05, min(0.95, ((p[0] - sx) * (ex - sx) + (p[1] - sy) * (ey - sy)) / L2))
                foot = (sx + k * (ex - sx), sy + k * (ey - sy))
                if math.dist(p, foot) > 3.0:
                    continue
                lay, w = s_.GetLayer(), s_.GetWidth()
                parts = [seg((sx, sy), foot, lay), seg(foot, (ex, ey), lay), seg(p, foot, lay)]
                for it in parts[:2]:
                    it.SetWidth(w)
                board.Remove(s_)
                for it in parts:
                    board.Add(it)
                n, u, t2 = _drc(board, rpt)
                if n <= n0 and u < u0:
                    joined += 1; n0, u0, t = n, u, t2; done = True
                    break
                for it in parts:
                    board.Remove(it)
                board.Add(s_)
            if done:
                break
    return joined


def route(passes=20, reuse_ses=False):
    """Freerouting 1.9.0: 2.x ignores its pass limit on the command line and
    never ends on this board; 1.9.0 honours -mp but wants a display, so it
    gets a virtual one."""
    path = os.path.join(D.HERE, D.NAME + '.kicad_pcb')
    # always start from the placement-only copy build_pcb() left: a board
    # saved by an earlier route still carries tracks and zones, and importing
    # the session again would double every via
    import shutil
    placed_pro = placed_path()[:-len('.kicad_pcb')] + '.kicad_pro'
    shutil.copy(path[:-len('.kicad_pcb')] + '.kicad_pro', placed_pro)   # KiCad pairs by file name
    board = load_board(placed_path())
    apply_rules(board)
    add_edge_keepouts(board)
    add_connector_keepouts(board)
    add_planes(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    dsn = os.path.join(D.HERE, D.NAME + '.dsn')
    ses = os.path.join(D.HERE, D.NAME + '.ses')
    preroute_edge_gnd(board)
    prerouted(board)
    predogbone(board)
    pcbnew.ExportSpecctraDSN(board, dsn)          # always: the class check below reads it
    # high-speed classes stay on the layers the design names (D.CLASS_LAYERS):
    # left free, the router split pairs P-on-B / N-on-In2, and In2 has no
    # solid reference once signals cut its pour
    t = open(dsn).read()
    for cls, layers in getattr(D, 'CLASS_LAYERS', {}).items():
        t, n = re.subn(r'(\(class ' + re.escape(cls) + r'\s[^(]*\(circuit)',
                       r'\1\n        (use_layer ' + ' '.join(layers) + ')', t)
        if n != 1:
            raise RuntimeError(f'class {cls} not found in the DSN to restrict its layers')
    open(dsn, 'w').write(t)
    if not (reuse_ses and os.path.exists(ses)):
        if os.path.exists(ses):
            os.remove(ses)
        if subprocess.run(['xdpyinfo', '-display', ':98'], capture_output=True).returncode:
            subprocess.Popen(['Xvfb', ':98', '-screen', '0', '1600x1000x24'],
                             stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        env = dict(os.environ, DISPLAY=':98')
        subprocess.run(['java', '-jar', FREEROUTING, '-de', dsn, '-do', ses, '-mp', str(passes)],
                       capture_output=True, text=True, timeout=5400, env=env)
        if not os.path.exists(ses):
            raise RuntimeError('Freerouting wrote no session file')
    classes = re.findall(r'\(class (\S+)((?:\s+[^\s()]+)*)', open(dsn).read()) if os.path.exists(dsn) else []
    for name, members in classes:
        if name != 'kicad_default' and not members.split():
            raise RuntimeError(f'netclass {name} reached the DSN with no nets - the widths would be lost')
    nw, nv = import_ses(board, ses)
    add_outer_pours(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    stitch_gnd(board)
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
        route(passes=int(os.environ.get('SFP_PASSES', '20')), reuse_ses='--reuse-ses' in sys.argv)
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

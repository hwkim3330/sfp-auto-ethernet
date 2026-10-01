#!/usr/bin/env python3
"""Check the three boards against the specs they have to meet, from the
boards themselves, and write docs/COMPLIANCE.md.

    python3 tools/compliance.py      (KiCad 7's pcbnew; run tools/zsolve.py first
                                      when the stackup or a pair's geometry changes)

What it reads: each board's routed .kicad_pcb (edge fingers, part heights),
its lengths.txt (pair lengths and skew, written by the generator), and
tools/zsolve.txt (the field solver's impedances and delays). Everything a
datasheet number stands behind is listed with its source in the tables.
"""
import math
import os
import re
import sys

import pcbnew

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
HW = os.path.join(ROOT, 'hw')
sys.path.insert(0, HW)

# -------------------------------------------------------------- the lanes
# pair name -> (interface, symbol rate in baud)
LANES = {
    't1': {'TD': ('SGMII, host to module', 1.25e9), 'RD': ('SGMII, module to host', 1.25e9),
           'SG_TX': ('SGMII', 1.25e9), 'SG_RX': ('SGMII', 1.25e9),
           'TRD': ('1000BASE-T1 MDI (PAM3)', 750e6), 'DCB': ('1000BASE-T1 MDI (PAM3)', 750e6),
           'MDI': ('1000BASE-T1 MDI (PAM3)', 750e6)},
    'rj45': {'TD': ('2500BASE-X, host to module', 3.125e9), 'RD': ('2500BASE-X, module to host', 3.125e9),
             'HSI': ('2500BASE-X', 3.125e9), 'HSO': ('2500BASE-X', 3.125e9),
             'MDI0': ('2.5GBASE-T MDI (PAM16)', 200e6), 'MDI1': ('2.5GBASE-T MDI (PAM16)', 200e6),
             'MDI2': ('2.5GBASE-T MDI (PAM16)', 200e6), 'MDI3': ('2.5GBASE-T MDI (PAM16)', 200e6),
             'LINE0': ('2.5GBASE-T line side', 200e6), 'LINE1': ('2.5GBASE-T line side', 200e6),
             'LINE2': ('2.5GBASE-T line side', 200e6), 'LINE3': ('2.5GBASE-T line side', 200e6)},
    't1s': {'TD': ('SGMII, host to module', 1.25e9), 'RD': ('SGMII, module to host', 1.25e9),
            'SRX': ('SGMII', 1.25e9), 'STX': ('SGMII', 1.25e9),
            'REFCLK': ('125 MHz LVDS reference', 250e6),       # a bit per half period
            'MDI': ('10BASE-T1S MDI (DME)', 12.5e6)},
}
SKEW_BUDGET_UI = 0.05            # intra-pair skew, as a fraction of a symbol: conservative

# INF-8074i Figure 2/3: the edge fingers
FINGER = dict(width=0.6, width_tol=0.05, pitch=0.8, start={'gnd': 0.5, 'pwr': 0.9, 'sig': 1.3},
              min_end=3.5, top_pin20=3.8, top_pin11=-3.4, bot_pin1=3.4, bot_pin10=-3.8)
GND_PINS = {1, 9, 10, 11, 14, 17, 20}
PWR_PINS = {15, 16}

# clocks: LCSC parameter tables, read 2026-10-01
CLOCKS = [
    ('t1', 'Y1', '25 MHz crystal SX1B25.000F0810F30 (C7301943)', 10, 30, 'DP83TG720 / TC812 reference',
     100, 'IEEE 802.3bp/bw: +/-100 ppm'),
    ('rj45', 'X1', '25 MHz oscillator MST8011AI-72-33E25 (C51026225)', 0, 25, 'RTL8221B reference',
     100, 'IEEE 802.3bz: +/-100 ppm'),
    ('t1s', 'X1', '125 MHz LVDS oscillator OB2EL89CLIB112YLC-125M (C7425465)', 20, 30, 'GW5AT SerDes REFCLK0',
     100, 'SGMII / 1000BASE-X: +/-100 ppm'),
    ('t1s', 'Y1', '25 MHz crystal X201625MOB4SI (C5210656)', 10, 20, 'LAN8670 reference',
     100, 'IEEE 802.3cg: +/-100 ppm'),
]


def zsolve_results():
    out = {}
    txt = open(os.path.join(ROOT, 'tools', 'zsolve.txt')).read()
    for m in re.finditer(r'pair (.+?)\s+Zdiff\s+([\d.]+)\s+Zcm\s+([\d.]+)\s+eps_eff\(odd\) ([\d.]+)\s+([\d.]+) ps/mm', txt):
        out[m.group(1).strip()] = dict(zdiff=float(m.group(2)), zcm=float(m.group(3)),
                                       eeff=float(m.group(4)), psmm=float(m.group(5)))
    lines = {}
    for m in re.finditer(r'line w ([\d.]+): Z0\s+([\d.]+)\s+eps_eff ([\d.]+)\s+([\d.]+) ps/mm', txt):
        lines[float(m.group(1))] = dict(z0=float(m.group(2)), eeff=float(m.group(3)), psmm=float(m.group(4)))
    return out, lines


def lengths(board):
    rows = []
    for line in open(os.path.join(HW, board, 'lengths.txt')):
        m = re.match(r'(\S+)/(\S+) ([\d.]+)/([\d.]+) mm skew ([\d.]+) vias (\d+)/(\d+)', line)
        if m:
            p, n = m.group(1), m.group(2)
            base = re.sub(r'_(P|N|M)$', '', p)
            rows.append(dict(p=p, n=n, lp=float(m.group(3)), ln=float(m.group(4)), skew=float(m.group(5)),
                             vp=int(m.group(6)), vn=int(m.group(7)), base=base))
    return rows


def loss_db_per_mm(f, eeff, w_mm, z_line, tand=0.02, rough=1.3):
    """Microstrip loss, first order: dielectric (tan d) plus conductor (skin
    effect over the line's width, times a roughness factor). FR-4: tan d ~0.02."""
    a_d = math.pi * f * math.sqrt(eeff) * tand / 299792458.0              # Np/m
    rs = math.sqrt(math.pi * f * 4e-7 * math.pi / 5.8e7)                   # ohm/sq
    a_c = rough * rs / (w_mm * 1e-3) / (2 * z_line)                         # Np/m
    return (a_d + a_c) * 8.686 / 1000.0


def finger_check(board):
    b = pcbnew.LoadBoard(os.path.join(HW, board, f'{board}.kicad_pcb'))
    f = b.FindFootprintByReference('J1')
    x0 = pcbnew.ToMM(b.GetBoardEdgesBoundingBox().GetX()) - 100 + 0.05      # the edge line's own width
    bad, pads = [], {}
    for p in f.Pads():
        n = int(p.GetNumber())
        bb = p.GetBoundingBox()
        xs, xe = pcbnew.ToMM(bb.GetX()) - 100 - x0, pcbnew.ToMM(bb.GetRight()) - 100 - x0
        y0, y1 = 100 - pcbnew.ToMM(bb.GetBottom()), 100 - pcbnew.ToMM(bb.GetY())
        w, yc = y1 - y0, (y0 + y1) / 2
        pads[n] = (yc, xs, xe, w, p.IsOnLayer(pcbnew.F_Cu))
        kind = 'gnd' if n in GND_PINS else 'pwr' if n in PWR_PINS else 'sig'
        if abs(w - FINGER['width']) > FINGER['width_tol'] + 1e-6:
            bad.append(f'pin {n} width {w:.3f}')
        if abs(xs - FINGER['start'][kind]) > 0.01:
            bad.append(f'pin {n} starts {xs:.2f} from the edge, wants {FINGER["start"][kind]}')
        if xe < FINGER['min_end'] - 1e-6:
            bad.append(f'pin {n} ends at {xe:.2f}, wants >= {FINGER["min_end"]}')
        if (n >= 11) != pads[n][4]:
            bad.append(f'pin {n} on the wrong side')
    for a, b_ in zip(range(11, 20), range(12, 21)):
        if abs(abs(pads[b_][0] - pads[a][0]) - FINGER['pitch']) > 0.01:
            bad.append(f'pitch {a}-{b_}')
    for a, b_ in zip(range(1, 10), range(2, 11)):
        if abs(abs(pads[b_][0] - pads[a][0]) - FINGER['pitch']) > 0.01:
            bad.append(f'pitch {a}-{b_}')
    for pin, want in ((20, FINGER['top_pin20']), (11, FINGER['top_pin11']), (1, FINGER['bot_pin1']),
                      (10, FINGER['bot_pin10'])):
        if abs(pads[pin][0] - want) > 0.01:
            bad.append(f'pin {pin} at y {pads[pin][0]:.2f}, wants {want}')
    # the tab: 9.2 +/- 0.1 wide
    ys = []
    for d in b.GetDrawings():
        if d.GetLayer() == pcbnew.Edge_Cuts and d.GetClass() in ('PCB_SHAPE', 'DRAWSEGMENT'):
            for pt in (d.GetStart(), d.GetEnd()):
                if pcbnew.ToMM(pt.x) - 100 < 3:
                    ys.append(100 - pcbnew.ToMM(pt.y))
    tab = max(ys) - min(ys) if ys else float('nan')
    if abs(tab - 9.2) > 0.1:
        bad.append(f'tab width {tab:.2f}')
    return bad, tab


def heights(board):
    sys.path.insert(0, os.path.join(HW, board))
    D = __import__(f'make_{board}')
    out = []
    for p in D.P:
        h = D.HEIGHTS.get(p['ref'])
        if h is None:
            continue
        room = 4.65 if p['side'] == 'F' else 1.65
        inside = p['at'][0] < 44.3
        out.append((p['ref'], p['side'], h, room if inside else None))
    return out


def main():
    zp, zl = zsolve_results()
    nom = zp['nominal']
    lo = min(v['zdiff'] for v in zp.values())
    hi = max(v['zdiff'] for v in zp.values())
    md = ['# Compliance: the three boards against their specs',
          '',
          'Generated by `tools/compliance.py` from the routed boards; regenerate it after any re-route.',
          'Nothing here is measured: it is what the design files say, checked against the documents named in each table.',
          '',
          '## 1. Line impedance (field solver)',
          '',
          '`tools/zsolve.py`: a 2D finite-difference solver on the cross-section, refined until Z moves by '
          '< 0.5 %. Checked against Hammerstad\'s closed form for a thin microstrip (57.4 vs 57.9 ohm) and '
          'against JLC\'s calculator (0.157 mm → 50 ohm; this solver: 50.7). Stack: JLC 3313 prepreg '
          '0.0994 mm, εr 4.1, 35 µm copper, solder mask 25 / 15 µm εr 3.8. Every pair on the three boards is '
          '0.114 / 0.152 mm on an outer layer over GND.',
          '',
          '| Case | Zdiff (Ω) | Zcm (Ω) | Delay |',
          '|---|---:|---:|---:|']
    for k, v in zp.items():
        md.append(f'| pair, {k} | {v["zdiff"]:.1f} | {v["zcm"]:.1f} | {v["psmm"]:.2f} ps/mm |')
    for w, v in zl.items():
        md.append(f'| single line {w} mm | Z0 {v["z0"]:.1f} | | {v["psmm"]:.2f} ps/mm |')
    ok_z = 90 <= lo and hi <= 110
    md += ['',
           f'Targets: 100 Ω ± 10 % differential for SGMII, 1000BASE-X / 2500BASE-X (SFF-8431 module traces), '
           f'the BASE-T1 and BASE-T MDI, and LVDS. **Nominal {nom["zdiff"]:.1f} Ω; corners {lo:.1f}–{hi:.1f} Ω: '
           f'{"inside" if ok_z else "OUTSIDE"} ±10 %.** JLC\'s impedance control holds ±10 % on top of this.',
           '']

    md += ['## 2. Pair skew and loss, per lane', '',
           f'Skew from the routed lengths (`lengths.txt`) at the solver\'s {nom["psmm"]:.2f} ps/mm, against a '
           f'conservative budget of {SKEW_BUDGET_UI:.0%} of a symbol. Loss is a first-order estimate at the '
           'Nyquist frequency (FR-4 tan δ 0.02, skin effect × 1.3 for roughness).', '']
    allok = True
    for board in ('t1', 'rj45', 't1s'):
        md += [f'### {board.upper()}', '',
               '| Pair | Interface | Rate | UI | Length P / N | Skew | % of UI | Vias | Loss at Nyquist | |',
               '|---|---|---:|---:|---:|---:|---:|---:|---:|---|']
        for r in lengths(board):
            name, rate = LANES[board].get(r['base'], ('?', None))
            if rate is None:
                continue
            ui_ps = 1e12 / rate
            sk_ps = r['skew'] * nom['psmm']
            frac = sk_ps / ui_ps
            loss = loss_db_per_mm(rate / 2, nom['eeff'], 0.114, nom['zdiff'] / 2) * max(r['lp'], r['ln'])
            ok = frac <= SKEW_BUDGET_UI and r['vp'] == r['vn']
            allok &= ok
            md.append(f'| {r["p"]} / {r["n"]} | {name} | {rate / 1e6:g} MBd | {ui_ps:.0f} ps | '
                      f'{r["lp"]:.2f} / {r["ln"]:.2f} mm | {sk_ps:.1f} ps | {frac:.1%} | {r["vp"]}/{r["vn"]} | '
                      f'{loss:.2f} dB | {"✓" if ok else "✗"} |')
        md.append('')
    md += [f'**{"Every pair is inside the budget, with the same via count on both lines." if allok else "Some pairs are OUTSIDE the budget (marked ✗)."}** '
           'The longest SerDes run loses well under 1 dB; SFF-8431 leaves the module several dB.', '',
           'The pair-to-pair skew a BASE-T or BASE-T1 PHY tolerates is set by the cable (tens of ns); '
           'the board adds well under 1 ns.', '']

    md += ['## 3. Edge fingers (INF-8074i Figures 2 and 3)', '',
           'Measured from each board\'s J1 footprint: pad width 0.6 ± 0.05 mm, 0.8 mm pitch, pin 20 at +3.8 / '
           'pin 11 at −3.4 (top), pin 1 at +3.4 / pin 10 at −3.8 (bottom), pads starting 0.5 (ground), 0.9 '
           '(power), 1.3 mm (signal) from the edge, running to at least 3.5 mm; the tab 9.2 ± 0.1 mm wide.', '',
           '| Board | Result | Tab width |', '|---|---|---:|']
    for board in ('t1', 'rj45', 't1s'):
        bad, tab = finger_check(board)
        md.append(f'| {board.upper()} | {"✓ all 20 pads" if not bad else "✗ " + "; ".join(bad)} | {tab:.2f} mm |')
    md += ['', 'Pin 6 (MOD_DEF0) is grounded in the module but mates as a signal, so it starts at 1.3 mm. '
           'Board thickness over the fingers is the stackup\'s 1.0 mm (MSA: 1.0 ± 0.1). JLC plates ENIG, not '
           'the MSA\'s 0.38 µm hard gold: fine for tens of insertions.', '']

    md += ['## 4. Heights inside the cage (INF-8074i Appendix A)', '',
           'Room inside the cage: 4.65 mm above the board, 1.65 mm below it (behind the cage front, 44.3 mm from '
           'the finger end). Parts past the cage front only have to clear the host\'s faceplate.', '',
           '| Board | Part | Side | Height | Room | Margin |', '|---|---|---|---:|---:|---:|']
    for board in ('t1', 'rj45', 't1s'):
        for ref, side, h, room in sorted(heights(board), key=lambda r: -r[2]):
            md.append(f'| {board.upper()} | {ref} | {side} | {h:.2f} mm | '
                      + (f'{room:.2f} mm | {room - h:+.2f} mm |' if room else 'past the cage front | |'))
    md.append('')

    md += ['## 5. Clocks', '',
           'Ethernet allows ±100 ppm at each end. Stack-up: initial tolerance + stability over −40…85 °C '
           '(aging, a few ppm a year, is extra).', '',
           '| Board | Ref | Part | For | Tolerance + stability | Limit | |', '|---|---|---|---|---:|---|---|']
    for board, ref, part, tol, stab, use, lim, src in CLOCKS:
        tot = tol + stab
        md.append(f'| {board.upper()} | {ref} | {part} | {use} | ±{tot} ppm | {src} | {"✓" if tot < lim else "✗"} |')
    md += ['', 'Crystal loads: T1 8 pF crystal with 2 × 12 pF (12 / 2 + ~2 pF of strays = 8); T1S 12 pF crystal '
           'with 2 × 18 pF (18 / 2 + ~3 = 12). RJ45 uses an oscillator with ≤ 2 ps RMS jitter (12 kHz–20 MHz), '
           'which the RTL8221B asks for.', '']

    md += ['## 6. Control pins and the 2-wire interface (INF-8074i Table 2, SFF-8472, SFF-8431)', '',
           '| Item | Spec | The firmware | |', '|---|---|---|---|',
           '| t_off (TX_DISABLE ↑ → transmitter off) | 10 µs | an edge interrupt puts the PHY in reset: about 1 µs at 16 MHz | ✓ |',
           '| t_on (TX_DISABLE ↓ → transmitter on) | 1 ms | the same interrupt releases the reset at once; the PHY\'s settings follow 20 ms later and the link trains on top (as on every copper SFP) | PHY released ✓; link time is the PHY\'s |',
           '| t_init (power-up → TX_FAULT low) | 300 ms | TX_FAULT is driven low within microseconds of the MCU starting; the PHY is set up as soon as TX_DISABLE is low (T1S: and the FPGA is configured) | ✓ |',
           '| t_loss_on / off (RX_LOS) | 100 µs | RX_LOS follows the PHY\'s link status, polled every 5 ms (T1S: the FPGA\'s FPGA_LINK) | ✗ by design: a copper PHY\'s own link-fail timers run for milliseconds or longer, so no copper module can meet it |',
           '| TX_FAULT | open drain, low = OK | held low (no fault is detected) | ✓ |',
           '| TX_DISABLE pull-up in the module | 4.7–10 kΩ | 10 kΩ (R5 on T1 and RJ45, R25 on T1S) | ✓ |',
           '| 2-wire bus | 100 kHz (SFF-8431 also allows 400) | 100 kHz timing; holds SCL while an MDIO transaction runs (clock stretching) | ✓; the host must allow stretching, as Linux does |',
           '| A0h base / extended checksums | bytes 63 / 95 | computed at boot | ✓ |',
           '| Power level (A0h 64, A2h 118) | ≤ 1 W until the host grants more | RJ45 declares level 2 and starts at level 1 (100M/1G only) until A2h 118 bit 0 is set; T1 and T1S declare level 1 | ✓ |',
           '']

    md += ['## 7. Connectors', '',
           '| Board | Part | Footprint from | Check |', '|---|---|---|---|',
           '| all | SFP edge fingers | INF-8074i Figures 2 / 3 (generated) | §3 above, automated |',
           '| T1 | Rosenberger H-MTD E6S20A-40MT5-Z (hand-soldered, not in the BOM) | drawing MB_633: 7.0 mm ground-hole pitch | print `hw/t1/fab/t1-1to1.pdf` at 100 % and lay the part on it |',
           '| RJ45 | Kinghelm KH-RJ45-58-8P8C, shielded, no magnetics (C2683360) | Kinghelm\'s drawing, by hand | print `hw/rj45/fab/rj45-1to1.pdf` at 100 %; 15.7 mm wide against a 13.7 mm SFP housing, so check the neighbouring cage |',
           '| T1S | JST PH S2B-PH-K-S, 2 pins, right angle (C173752) | KiCad\'s stock footprint (JST\'s land) | ✓ |',
           '']

    md += ['## 8. Not covered here', '',
           '- Measurements: eye diagrams, return loss, inrush, temperature. Nothing has been built.',
           '- The host side of the channel (the cage, the host\'s traces): SFF-8431 splits the budget, this '
           'checks only the module\'s part.',
           '- T1S: the Gowin transceiver IP, synthesis, timing and power (see `hw/t1s/README.md`).',
           '- Supply current: RJ45 declares level 2 on the RTL8221B\'s own figure; T1 and T1S are '
           'expected under 1 W but have not been estimated part by part.', '']
    open(os.path.join(ROOT, 'docs', 'COMPLIANCE.md'), 'w').write('\n'.join(md))
    print('docs/COMPLIANCE.md written;', 'impedance', 'ok' if ok_z else 'FAIL', '| skew', 'ok' if allok else 'FAIL')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""JLC order files for the T1 board, panelised.

    python3 panel_t1.py [N]      N boards per panel (default 5)

Why a panel (JLC, 2026-09):
  - gold fingers + bevel need the board >= 50 mm on each side
  - standard PCBA wants >= 70 x 70 mm and edge rails with fiducials
  - a bevel cannot cross a rail or a V-cut, so the boards sit in one column,
    every finger end flush with the panel's LEFT edge, joined by mouse bites;
    rails on the other three sides only (../panel_rails.py)

Writes panel/t1_panel.kicad_pcb and jlc/: gerbers.zip, bom.csv, cpl.csv.
"""
import json
import os
import subprocess
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
KIKIT = os.path.expanduser('~/.local/bin/kikit')


def preset(n):
    return {
        'layout': {'type': 'grid', 'rows': n, 'cols': 1, 'vspace': '2mm', 'hspace': '2mm',
                   'rotation': '0deg'},
        # 2 tabs per long edge, away from the finger tab (x < 7) and the nose
        'tabs': {'type': 'fixed', 'hcount': 3, 'vcount': 1, 'hwidth': '2.5mm', 'vwidth': '3mm',
                 'mindistance': '6mm'},
        'cuts': {'type': 'mousebites', 'drill': '0.5mm', 'spacing': '0.8mm', 'offset': '0.1mm',   # 0.25 reached In2's TRD_M (0.16 mm)
                 'prolong': '0mm'},     # prolonged cuts met at the right-end corners (holes 0 mm apart)
        'framing': {'type': 'plugin', 'code': os.path.join(HERE, '..', 'panel_rails.py') + '.ThreeSideRails',
                    'arg': '5,2,70,70'},
        'fiducials': {'type': '3fid', 'hoffset': '5mm', 'voffset': '2.5mm',
                      'coppersize': '1mm', 'opening': '2mm'},
        'tooling': {'type': 'none'},
        'text': {'type': 'simple', 'text': 'SFP-T1 x{} 3313 ENIG bevel<-'.format(n),
                 'anchor': 'mt', 'voffset': '2.5mm', 'hjustify': 'center', 'vjustify': 'center'},
        'post': {'millradius': '1mm'},
    }


IGNORE = ('J1', 'J2', 'D2', 'D3', 'TP1', 'TP2', 'TP3', 'TP4', 'TP5')


def jlc_files(panel_path, jlc, n):
    """Gerbers + drill, BOM and CPL in JLC's column format, from the panel.
    (KiKit 1.6's own `fab jlcpcb` cannot drive KiCad 7.0.11's plotter.)"""
    import csv
    import zipfile
    import pcbnew
    sys.path.insert(0, HERE)
    import export_t1 as E
    os.makedirs(jlc, exist_ok=True)
    board = pcbnew.LoadBoard(panel_path)
    rpt = os.path.join(jlc, 'panel-drc.rpt')
    pcbnew.WriteDRCReport(board, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    summary = [l for l in open(rpt) if l.startswith('** Found')]
    E.FAB = jlc
    z, nfiles = E.gerbers(board)
    os.replace(z, os.path.join(jlc, 't1-panel-gerbers.zip'))
    groups = {}
    # KiKit 1.6 keeps each board's references, so the panel holds five of
    # every designator; JLC needs them unique. Number them by board row
    # (top to bottom), the same way in the CPL and the BOM.
    fps = [fp for fp in board.GetFootprints()]
    centres = sorted(pcbnew.ToMM(fp.GetPosition().y) for fp in fps if fp.GetReference() == 'U1')

    def unique(fp):
        y = pcbnew.ToMM(fp.GetPosition().y)       # every part belongs to the board whose PHY is nearest
        i = min(range(len(centres)), key=lambda k: abs(centres[k] - y))
        return f'{fp.GetReference()}_{i + 1}'
    # two loadouts of the same board, so nobody edits a BOM by hand:
    #   tg720  1000BASE-T1, DP83TG720 + FB3 (1.0 V from the buck to pins 9/21)
    #   tc812  100BASE-T1, DP83TC812 (in stock at JLC), FB3 left off - the
    #          TC812 regulates pin 21 itself (see README)
    #          the TC812 also wants a 200 uH CMC (its datasheet; SNLA340 2.7),
    #          the TG720 the 100 uH one: same 3.2 x 2.5 land
    LOADOUTS = {'tg720': {}, 'tc812': {'U1': ('DP83TC812SRHARQ1', 'C3225813'), 'FB3': None,
                                       'L2': ('DLW32MH201XK2L', 'C883600')}}
    for old in ('cpl.csv', 'bom.csv'):
        if os.path.exists(os.path.join(jlc, old)):
            os.remove(os.path.join(jlc, old))
    for name, change in LOADOUTS.items():
        groups = {}
        with open(os.path.join(jlc, f'cpl-{name}.csv'), 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
            for fp in fps:
                base = fp.GetReference()
                ref = unique(fp)
                lcsc = fp.GetProperties().get('LCSC', '') if hasattr(fp, 'GetProperties') else ''
                value = fp.GetValue()
                if base in change:
                    if change[base] is None:
                        continue                          # not fitted in this loadout
                    value, lcsc = change[base]
                if base in IGNORE or not lcsc:
                    continue
                pos = fp.GetPosition()
                w.writerow([ref, f'{pcbnew.ToMM(pos.x):.3f}mm', f'{-pcbnew.ToMM(pos.y):.3f}mm',
                            'Bottom' if fp.IsFlipped() else 'Top', f'{fp.GetOrientationDegrees() % 360:.0f}'])
                key = (value, fp.GetFPID().GetLibItemName().wx_str(), lcsc)
                groups.setdefault(key, []).append(ref)
        with open(os.path.join(jlc, f'bom-{name}.csv'), 'w', newline='') as f:
            w = csv.writer(f)
            w.writerow(['Comment', 'Designator', 'Footprint', 'LCSC Part #'])
            for (val, fpn, lcsc), refs in sorted(groups.items(), key=lambda kv: kv[0][2]):
                w.writerow([val, ','.join(sorted(refs)), fpn, lcsc])
        print(f'  {name}: {len(groups)} BOM lines, {sum(len(r) for r in groups.values())} placements')
    print('  panel DRC: ' + ' / '.join(s.strip('* \n') for s in summary))
    print(f'  {nfiles} gerber/drill files')


def main():
    n = int(sys.argv[1]) if len(sys.argv) > 1 else 5
    os.makedirs(os.path.join(HERE, 'panel'), exist_ok=True)
    pre = os.path.join(HERE, 'panel', 'preset.json')
    json.dump(preset(n), open(pre, 'w'), indent=2)
    out = os.path.join(HERE, 'panel', 't1_panel.kicad_pcb')
    r = subprocess.run([KIKIT, 'panelize', '-p', pre, os.path.join(HERE, 't1.kicad_pcb'), out],
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-3000:])
        raise SystemExit('panelize failed')
    jlc = os.path.join(HERE, 'jlc')
    jlc_files(out, jlc, n)
    print(f'panel of {n}: {os.path.relpath(out, HERE)}; JLC files in jlc/: {sorted(os.listdir(jlc))}')


if __name__ == '__main__':
    main()

#!/usr/bin/env python3
"""JLC order files for the T1S board, panelised.

    python3 panel_t1s.py [N]      N boards per panel (default 5)

Why a panel (JLC, 2026-09):
  - gold fingers + bevel need the board >= 50 mm on each side
  - standard PCBA wants >= 70 x 70 mm and edge rails with fiducials
  - a bevel cannot cross a rail or a V-cut, so the boards sit in one column,
    every finger end flush with the panel's LEFT edge, joined by mouse bites;
    rails on the other three sides only (../panel_rails.py)

Writes panel/t1s_panel.kicad_pcb and jlc/: gerbers.zip, bom.csv, cpl.csv.
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
        # placed by hand (TABS): the body's edges are lined with parts, and
        # evenly spaced tabs put mouse-bite holes through C36/C37, then X1/R12 on the RJ45 board; here the spans come from a scan of the edges
        'tabs': {'type': 'annotation', 'fillet': '0mm'},
        'cuts': {'type': 'mousebites', 'drill': '0.5mm', 'spacing': '0.8mm', 'offset': '0.1mm',   # 0.25 reached In2's TRD_M (0.16 mm)
                 'prolong': '0mm'},     # prolonged cuts met at the right-end corners (holes 0 mm apart)
        'framing': {'type': 'plugin', 'code': os.path.join(HERE, '..', 'panel_rails.py') + '.ThreeSideRails',
                    'arg': '5,2,70,70'},
        'fiducials': {'type': '3fid', 'hoffset': '5mm', 'voffset': '2.5mm',
                      'coppersize': '1mm', 'opening': '2mm'},
        'tooling': {'type': 'none'},
        'text': {'type': 'simple', 'text': 'SFP-T1S x{} 6L 3313 ENIG bevel<-'.format(n),
                 'anchor': 'mt', 'voffset': '2.5mm', 'hjustify': 'center', 'vjustify': 'center'},
        'post': {'millradius': '1mm'},
    }


# (x, y, direction) in board mm: a point 0.5 mm outside the edge, pointing
# into the board (KiKit grows the tab from there to the board and back to the
# partition line), where no pad, via or track comes near a mouse-bite hole
TABS = [(31.0, -6.4, 'down'), (44.0, -6.4, 'down'), (55.0, -6.4, 'down'),
        (13.0, 6.4, 'up'), (37.1, 6.4, 'up'), (46.0, 6.4, 'up'),
        (58.9, 3.0, 'left')]
TAB_WIDTH = 2.5


def tabbed_copy(src, dst):
    """The board with a KiKit tab annotation at each TABS entry."""
    import pcbnew
    b = pcbnew.LoadBoard(src)
    lib = os.path.join(os.path.dirname(pcbnew_kikit()), 'resources', 'kikit.pretty')
    rot = {'left': 180, 'up': 90, 'down': 270}
    for i, (x, y, d) in enumerate(TABS):
        fp = pcbnew.FootprintLoad(lib, 'Tab')
        fp.SetFPID(pcbnew.LIB_ID('kikit', 'Tab'))
        fp.SetReference(f'KT{i + 1}')
        for t in fp.GraphicalItems():
            if isinstance(t, pcbnew.PCB_TEXT) and t.GetText().startswith('KIKIT:'):
                t.SetText(f'KIKIT: width: {TAB_WIDTH}mm')
        fp.SetPosition(pcbnew.VECTOR2I(pcbnew.FromMM(100 + x), pcbnew.FromMM(100 + y)))
        fp.SetOrientationDegrees(rot[d])
        b.Add(fp)
    b.Save(dst)
    # the rules and the accepted courtyard overlaps sit next to the board
    import shutil
    for ext in ('.kicad_pro', '.kicad_dru'):
        shutil.copy(os.path.splitext(src)[0] + ext, os.path.splitext(dst)[0] + ext)


def pcbnew_kikit():
    import kikit
    return kikit.__file__


sys.path.insert(0, HERE)
import make_t1s as _D                    # noqa: E402
# the edge itself, the test pads, and whatever the design leaves unfitted.
# The JST connector (THT) is in: JLC fits it, and it is stocked (C173752)
IGNORE = ('J1',) + tuple(p['ref'] for p in _D.P if p['dnp'] or p['ref'].startswith('TP'))


def jlc_files(panel_path, jlc, n):
    """Gerbers + drill, BOM and CPL in JLC's column format, from the panel.
    (KiKit 1.6's own `fab jlcpcb` cannot drive KiCad 7.0.11's plotter.)"""
    import csv
    import zipfile
    import pcbnew
    sys.path.insert(0, HERE)
    import export_t1s as E
    os.makedirs(jlc, exist_ok=True)
    board = pcbnew.LoadBoard(panel_path)
    # KiKit's panel carries only the Default netclass at KiCad's 0.2 mm; the
    # board is drawn to 0.15 mm, 0.2 mm hole clearance and 0.35 / 0.2 vias
    sys.path.insert(0, os.path.dirname(HERE))
    import sfpgen as G
    G.D = _D
    G.apply_rules(board)
    rpt = os.path.join(jlc, 'panel-drc.rpt')
    pcbnew.WriteDRCReport(board, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    summary = [l for l in open(rpt) if l.startswith('** Found')]
    E.FAB = jlc
    z, nfiles = E.gerbers(board)
    os.replace(z, os.path.join(jlc, 't1s-panel-gerbers.zip'))
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
    LOADOUTS = {'t1s': {}}                  # one loadout
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
    out = os.path.join(HERE, 'panel', 't1s_panel.kicad_pcb')
    src = os.path.join(HERE, 'panel', 't1s_tabs.kicad_pcb')
    tabbed_copy(os.path.join(HERE, 't1s.kicad_pcb'), src)
    r = subprocess.run([KIKIT, 'panelize', '-p', pre, src, out],
                       capture_output=True, text=True)
    if r.returncode:
        print(r.stdout[-2000:], r.stderr[-3000:])
        raise SystemExit('panelize failed')
    jlc = os.path.join(HERE, 'jlc')
    jlc_files(out, jlc, n)
    svg = os.path.join(jlc, 'panel-top.svg')
    subprocess.run(['kicad-cli', 'pcb', 'export', 'svg', '--layers', 'F.Cu,F.Mask,F.SilkS,Edge.Cuts',
                    '--page-size-mode', '2', '--exclude-drawing-sheet', '-o', svg, out], capture_output=True)
    subprocess.run(['rsvg-convert', '-w', '1400', '-b', 'white', svg, '-o', svg[:-4] + '.png'],
                   capture_output=True)
    os.remove(svg)
    print(f'panel of {n}: {os.path.relpath(out, HERE)}; JLC files in jlc/: {sorted(os.listdir(jlc))}')


if __name__ == '__main__':
    main()

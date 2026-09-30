#!/usr/bin/env python3
"""Fab outputs for the routed T1S board: Gerbers + drill (zip), BOM, CPL, previews.

    python3 export_t1s.py       after make_t1s.py --route has left a clean DRC

Order notes (the full sheet is ORDER.md):
  6 layers (JLC06101H-3313), 1.0 mm finished (the SFP MSA edge: 1.0 +/- 0.1 over the pads),
  JLC06101H-3313 stackup with impedance control; the pairs are 0.114 mm lines
  with a 0.152 mm gap, about 100 ohm differential on that stackup.
  ENIG with gold fingers and a 45 degree bevel. JLC plates no hard gold, so
  the fingers are ENIG-grade, not the MSA's >= 0.38 um hard gold.
"""
import csv
import os
import subprocess
import sys
import zipfile

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, HERE)
import make_t1s as T                    # noqa: E402  - the netlist, for the BOM

PCB = os.path.join(HERE, 't1s.kicad_pcb')
FAB = os.path.join(HERE, 'fab')
LAYERS = [('F_Cu', pcbnew.F_Cu), ('In1_Cu', pcbnew.In1_Cu), ('In2_Cu', pcbnew.In2_Cu),
          ('In3_Cu', pcbnew.In3_Cu), ('In4_Cu', pcbnew.In4_Cu), ('B_Cu', pcbnew.B_Cu), ('F_Mask', pcbnew.F_Mask), ('B_Mask', pcbnew.B_Mask),
          ('F_Paste', pcbnew.F_Paste), ('B_Paste', pcbnew.B_Paste),
          ('F_Silkscreen', pcbnew.F_SilkS), ('B_Silkscreen', pcbnew.B_SilkS),
          ('Edge_Cuts', pcbnew.Edge_Cuts)]


def gerbers(board):
    gdir = os.path.join(FAB, 'gerber')
    os.makedirs(gdir, exist_ok=True)
    for f in os.listdir(gdir):
        os.remove(os.path.join(gdir, f))
    pc = pcbnew.PLOT_CONTROLLER(board)
    po = pc.GetPlotOptions()
    po.SetOutputDirectory(gdir)
    po.SetPlotFrameRef(False)
    po.SetUseGerberProtelExtensions(False)
    po.SetCreateGerberJobFile(False)
    po.SetSubtractMaskFromSilk(True)
    po.SetUseAuxOrigin(False)
    po.SetDrillMarksType(pcbnew.DRILL_MARKS_NO_DRILL_SHAPE)
    for name, layer in LAYERS:
        pc.SetLayer(layer)
        pc.OpenPlotfile(name, pcbnew.PLOT_FORMAT_GERBER, name)
        pc.PlotLayer()
    pc.ClosePlot()
    dw = pcbnew.EXCELLON_WRITER(board)
    dw.SetOptions(False, False, board.GetDesignSettings().GetAuxOrigin(), True)
    dw.SetFormat(True)
    dw.CreateDrillandMapFilesSet(gdir, True, False)
    z = os.path.join(FAB, 't1s-gerbers.zip')
    with zipfile.ZipFile(z, 'w', zipfile.ZIP_DEFLATED) as zf:
        for f in sorted(os.listdir(gdir)):
            info = zipfile.ZipInfo(f, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            zf.writestr(info, open(os.path.join(gdir, f), 'rb').read())
    return z, len(os.listdir(gdir))


def bom_cpl(board):
    rows = {}
    for p in T.P:
        if p['ref'].startswith('TP') or p['ref'] == 'J1':
            continue                                   # pads, and the edge itself
        key = (p['value'], p['fp'], p['mpn'], p['dnp'])
        rows.setdefault(key, []).append(p['ref'])
    with open(os.path.join(FAB, 't1s-bom.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Comment', 'Designator', 'Footprint', 'MPN', 'Qty', 'Fitted'])
        for (val, fp, mpn, dnp), refs in sorted(rows.items(), key=lambda kv: kv[1][0]):
            w.writerow([val, ','.join(refs), fp.split(':')[-1], mpn, len(refs), 'DNP' if dnp else 'yes'])
    with open(os.path.join(FAB, 't1s-cpl.csv'), 'w', newline='') as f:
        w = csv.writer(f)
        w.writerow(['Designator', 'Mid X', 'Mid Y', 'Layer', 'Rotation'])
        for fp in board.GetFootprints():
            ref = fp.GetReference()
            if ref.startswith('TP') or ref == 'J1':
                continue
            pos = fp.GetPosition()
            w.writerow([ref, f'{pcbnew.ToMM(pos.x) - 100:.3f}mm', f'{100 - pcbnew.ToMM(pos.y):.3f}mm',
                        'Bottom' if fp.IsFlipped() else 'Top', f'{fp.GetOrientationDegrees():.0f}'])
    return sum(len(r) for r in rows.values())


def previews():
    for side, layers, extra in (('top', 'F.Cu,F.Mask,F.SilkS,Edge.Cuts', []),
                                ('bottom', 'B.Cu,B.Mask,B.SilkS,Edge.Cuts', ['--mirror'])):
        svg = os.path.join(FAB, f't1s-{side}.svg')
        subprocess.run(['kicad-cli', 'pcb', 'export', 'svg', '--layers', layers, '--page-size-mode', '2',
                        '--exclude-drawing-sheet', *extra, '-o', svg, PCB], capture_output=True)
        subprocess.run(['rsvg-convert', '-w', '1800', '-b', 'white', svg, '-o', svg.replace('.svg', '.png')],
                       capture_output=True)



def print_1to1():
    """A PDF to print at 100 % and lay the real parts on: top copper, fab
    outlines and the board edge at 1:1 (the BGA's ball field and the JST
    land above all). The board is 53.0 mm long: measure it on the print
    before trusting the rest."""
    pdf = os.path.join(FAB, 't1s-1to1.pdf')
    subprocess.run(['kicad-cli', 'pcb', 'export', 'pdf', '--layers', 'F.Cu,F.Fab,Edge.Cuts,Dwgs.User',
                    '--include-border-title', '--drill-shape-opt', '2', '-o', pdf, PCB], capture_output=True)
    return pdf


def main():
    os.makedirs(FAB, exist_ok=True)
    board = pcbnew.LoadBoard(PCB)
    z, n = gerbers(board)
    parts = bom_cpl(board)
    previews()
    pdf = print_1to1()
    print(f'{os.path.relpath(z, HERE)}: {n} files;  BOM {parts} placements;  previews in fab/; '
          f'1:1 print {os.path.relpath(pdf, HERE)}')


if __name__ == '__main__':
    main()

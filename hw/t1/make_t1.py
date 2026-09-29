#!/usr/bin/env python3
"""SFP 100/1000BASE-T1 module: symbols, schematic, PCB (placed, nets assigned).

    python3 make_t1.py          (KiCad 7 pcbnew bindings)

One netlist below is the single source: the schematic draws it and the PCB
takes its pad nets from it, so the two cannot disagree.

Sources, and where each block of the netlist comes from:
  DP83TG720S-Q1 datasheet SNLS604G  pins (Table 4-1), straps (Tables 6-18..20),
                                    MDI network (Figure 8-1, Table 8-1),
                                    decoupling (Figure 8-3, Table 8-2)
  DP83TC812S-Q1 datasheet SNLS654D  the 100 Mb/s loadout: pin 9 to pin 21,
                                    2.2 uF + 0.1 uF on pin 21 (its own core
                                    regulator output) - so for it the 1.0 V
                                    buck's ferrite FB3 is left unfitted
  TPS6282x datasheet SLVSDV6C       buck: 470 nH, 4.7 uF in, 2 x 10 uF out,
                                    R2 100k / R1 66.5k -> 1.00 V, Cff 120 pF
  INF-8074i                         SFP edge pins, MOD_ABS grounded in the
                                    module, TX_DISABLE pulled up in the module,
                                    AC coupling of TD/RD inside the module

Straps are all left at their defaults: SGMII (RX_D[2:0] = 000 by internal
pull-downs), PHY address 0, autonomous, slave. The module links up with no
management at all; the MCU changes master/slave over MDIO.
"""
import json
import math
import os
import re
import subprocess
import sys
import uuid as _uuid

import pcbnew

HERE = os.path.dirname(os.path.abspath(__file__))
HW = os.path.dirname(HERE)
sys.path.insert(0, HW)
import make_boards as MB                 # noqa: E402  - MSA geometry + edge footprint

NAME = 't1'
KSYM = '/usr/share/kicad/symbols/'
KFP = '/usr/share/kicad/footprints/'
SYMLIB = os.path.join(HW, 'sym', 'sfp.kicad_sym')
FPLIB = os.path.join(HW, 'fp', 'sfp.pretty')

# --------------------------------------------------------------------------
# footprints
C0201 = 'Capacitor_SMD:C_0201_0603Metric'
C0402 = 'Capacitor_SMD:C_0402_1005Metric'
C0603 = 'Capacitor_SMD:C_0603_1608Metric'
R0201 = 'Resistor_SMD:R_0201_0603Metric'
R0402 = 'Resistor_SMD:R_0402_1005Metric'
R0603 = 'Resistor_SMD:R_0603_1608Metric'
FB0603 = 'Inductor_SMD:L_0603_1608Metric'
LED0402 = 'LED_SMD:LED_0402_1005Metric'
TP = 'TestPoint:TestPoint_Pad_D1.0mm'

P = []


def part(ref, lib_id, value, fp, nets, at, side='F', rot=0, dnp=False, mpn=''):
    """at = (x, y) in the module frame of make_boards (x from the finger end,
    y across, 0 on the centreline)."""
    P.append(dict(ref=ref, lib_id=lib_id, value=value, fp=fp, nets=nets, at=at,
                  side=side, rot=rot, dnp=dnp, mpn=mpn))


# ---------------------------------------------------------------- SFP edge
EDGE = {1: 'GND', 2: 'TX_FAULT', 3: 'TX_DISABLE', 4: 'SDA', 5: 'SCL', 6: 'GND',
        7: None, 8: 'RX_LOS', 9: 'GND', 10: 'GND', 11: 'GND', 12: 'RD_N', 13: 'RD_P',
        14: 'GND', 15: 'VCCR', 16: 'VCCT', 17: 'GND', 18: 'TD_P', 19: 'TD_N', 20: 'GND'}
part('J1', 'sfp:SFP_EDGE', 'SFP edge (INF-8074i)', 'sfp:SFP_Module_Edge', EDGE, (0, 0))

# host rails through a bead each into the module's +3V3
part('FB1', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'VCCT', 2: '+3V3'}, (8.9, 4.9), mpn='BLM18KG601SH1')
part('FB2', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'VCCR', 2: '+3V3'}, (8.9, -4.9), mpn='BLM18KG601SH1')
part('C1', 'Device:C_Small', '10uF', C0603, {1: '+3V3', 2: 'GND'}, (8.9, 3.2))
part('C2', 'Device:C_Small', '100nF', C0402, {1: '+3V3', 2: 'GND'}, (8.9, -3.2), side='B')

# SGMII AC coupling, inside the module (MSA). TD = host -> module.
part('C3', 'Device:C_Small', '100nF', C0201, {1: 'TD_P', 2: 'SG_TX_P'}, (5.2, 2.0))
part('C4', 'Device:C_Small', '100nF', C0201, {1: 'TD_N', 2: 'SG_TX_N'}, (5.2, 1.2))
part('C5', 'Device:C_Small', '100nF', C0201, {1: 'RD_P', 2: 'SG_RX_P'}, (5.2, -1.2))
part('C6', 'Device:C_Small', '100nF', C0201, {1: 'RD_N', 2: 'SG_RX_N'}, (5.2, -2.0))

# ---------------------------------------------------------------- PHY
PHY = {1: 'MDC', 2: 'PHY_INT_N', 3: 'PHY_RST_N', 4: 'XO', 5: 'XI', 6: None,
       7: 'VDDA', 8: None, 9: 'VDD1P0', 10: None, 11: 'VDDA', 12: 'TRD_P', 13: 'TRD_M',
       14: None, 15: None, 16: None, 17: None, 18: None, 19: None, 20: None,
       21: 'VDD1P0', 22: 'VDDIO', 23: 'SG_RX_N', 24: 'SG_RX_P', 25: None, 26: None,
       27: None, 28: None, 29: None, 30: None, 31: None, 32: 'SG_TX_P', 33: 'SG_TX_N',
       34: 'VDDIO', 35: 'LED0', 36: 'MDIO', 37: 'GND'}
# pin 7 VSLEEP tied to VDDA3P3 (sleep unused, Figure 8-3); pin 8 WAKE may float
part('U1', 'sfp:DP83TG720S', 'DP83TG720S-Q1 (or DP83TC812S-Q1)',
     'Package_DFN_QFN:QFN-36-1EP_6x6mm_P0.5mm_EP4.1x4.1mm_ThermalVias', PHY, (19.5, 0.0), rot=180,
     mpn='DP83TG720SWRHARQ1')

# supply islands, Figure 8-3 / Table 8-2
part('FB4', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: '+3V3', 2: 'VDDA'}, (14.0, 4.6), mpn='BLM18KG601SH1')
part('FB5', 'Device:FerriteBead_Small', 'BLM18HE102SN1', FB0603, {1: '+3V3', 2: 'VDDIO'}, (13.0, -4.6), side='B', mpn='BLM18HE102SN1')
part('FB3', 'Device:FerriteBead_Small', 'BLM18KG601SH1 (DNP for DP83TC812)', FB0603,
     {1: 'V1P0_BUCK', 2: 'VDD1P0'}, (14.0, -4.6), mpn='BLM18KG601SH1')
DECAP = [  # (pin, net, values) - each pin gets its 10 nF nearest
    ('11', 'VDDA', ('10nF', '100nF', '2.2uF')),
    ('7', 'VDDA', ('100nF',)),
    ('34', 'VDDIO', ('10nF', '100nF')),
    ('22', 'VDDIO', ('10nF', '100nF', '2.2uF')),
    ('9', 'VDD1P0', ('10nF', '100nF', '2.2uF')),
    ('21', 'VDD1P0', ('10nF', '100nF', '2.2uF')),
]
# decaps sit on the BOTTOM, in a ring under the PHY (U1 at 19.5, 0, turned
# 180 so its SGMII pins face the fingers and MDC/INT/RST face the MCU)
_slots = [  # (x, y, rot) in DECAP order
    (21.4, 3.2, 90), (20.4, 3.2, 90), (19.2, 3.4, 90),      # pin 11 VDDA
    (22.7, 1.2, 0),                                          # pin 7 VSLEEP
    (17.6, -3.2, 90), (18.6, -3.2, 90),                      # pin 34 VDDIO
    (16.3, 1.2, 0), (16.3, -1.2, 0), (16.3, -2.2, 0),        # pin 22 VDDIO
    (22.7, 2.2, 0), (22.7, -1.2, 0), (22.7, -2.2, 0),        # pin 9 VDD1P0
    (16.3, 2.2, 0), (17.6, 3.2, 90), (20.2, -3.4, 90),       # pin 21 VDD1P0
]
_n = 7
for pin, net, vals in DECAP:
    for v in vals:
        x, y, r = _slots.pop(0)
        fp = C0402 if v == '2.2uF' else C0201
        part(f'C{_n}', 'Device:C_Small', v, fp, {1: net, 2: 'GND'}, (x, y), side='B', rot=r)
        _n += 1

# 25 MHz crystal, CL 8 pF -> 2 x 12 pF (less ~2 pF of strays each)
part('Y1', 'Device:Crystal_GND24_Small', '25MHz CL8pF 2016', 'Crystal:Crystal_SMD_2016-4Pin_2.0x1.6mm',
     {1: 'XI', 2: 'GND', 3: 'XO', 4: 'GND'}, (25.4, -0.4))
part('C24', 'Device:C_Small', '12pF', C0201, {1: 'XI', 2: 'GND'}, (25.4, 1.6))
part('C25', 'Device:C_Small', '12pF', C0201, {1: 'XO', 2: 'GND'}, (25.4, -2.4))

part('R1', 'Device:R_Small', '2.2k', R0201, {1: 'VDDIO', 2: 'MDIO'}, (23.8, -4.4))
# LED_0 = link. Its path to ground is also the strap pull-down: MS = 0 (slave)
part('R2', 'Device:R_Small', '1k', R0402, {1: 'LED0', 2: 'LED0_K'}, (45.2, -4.0), side='B', rot=90)
part('D1', 'Device:LED_Small', 'green', LED0402, {1: 'GND', 2: 'LED0_K'}, (46.1, -4.6), rot=90)

# ---------------------------------------------------------------- 1.0 V buck
part('U3', 'Regulator_Switching:TPS62823DLC', 'TPS62821DLC',   # base symbol of the family; the value names the part
    
     'Package_DFN_QFN:Texas_VSON-HR-8_1.5x2mm_P0.5mm',
     {1: '+3V3', 2: 'BUCK_FB', 3: 'GND', 4: None, 5: 'GND', 6: 'BUCK_SW', 7: '+3V3', 8: None},
     (12.0, 1.2), mpn='TPS62821DLCR')
part('L1', 'Device:L_Small', '470nH DFE201610E-R47M', 'Inductor_SMD:L_Murata_DFE201610P',
     {1: 'BUCK_SW', 2: 'V1P0_BUCK'}, (12.0, -1.6), mpn='DFE201610E-R47M')
part('C26', 'Device:C_Small', '4.7uF', C0402, {1: '+3V3', 2: 'GND'}, (10.1, 1.2), rot=90)
part('C27', 'Device:C_Small', '10uF', C0603, {1: 'V1P0_BUCK', 2: 'GND'}, (9.4, -1.6), rot=90)
part('C28', 'Device:C_Small', '10uF', C0603, {1: 'V1P0_BUCK', 2: 'GND'}, (12.0, -1.9), side='B')
part('R3', 'Device:R_Small', '66.5k 1%', R0201, {1: 'V1P0_BUCK', 2: 'BUCK_FB'}, (14.3, 2.8))
part('R4', 'Device:R_Small', '100k 1%', R0201, {1: 'BUCK_FB', 2: 'GND'}, (14.3, 2.0))
part('C29', 'Device:C_Small', '120pF', C0201, {1: 'V1P0_BUCK', 2: 'BUCK_FB'}, (14.3, 1.2))

# ---------------------------------------------------------------- MCU
MCU = {1: 'SDA', 2: None, 3: None, 4: '+3V3', 5: 'GND', 6: 'NRST', 7: 'MDC', 8: 'MDIO',
       9: 'PHY_RST_N', 10: 'PHY_INT_N', 11: 'TX_DISABLE', 12: 'RX_LOS', 13: 'TX_FAULT',
       14: None, 15: None, 16: None, 17: None, 18: 'SWDIO', 19: 'SWCLK', 20: 'SCL'}
part('U2', 'MCU_ST_STM32G0:STM32G031F_4-6-8_Px',   # base symbol; value names the part
    
     'STM32G031F6P6', 'Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm', MCU, (31.5, 0.0), rot=90,
     mpn='STM32G031F6P6')
part('C30', 'Device:C_Small', '100nF', C0402, {1: '+3V3', 2: 'GND'}, (27.2, 3.6), rot=90)
part('C31', 'Device:C_Small', '1uF', C0402, {1: '+3V3', 2: 'GND'}, (27.2, -3.6), rot=90)
part('C32', 'Device:C_Small', '100nF', C0402, {1: 'NRST', 2: 'GND'}, (31.5, 0.0), side='B')
# TX_DISABLE: 4.7..10k pull-up inside the module (INF-8074i)
part('R5', 'Device:R_Small', '10k', R0402, {1: '+3V3', 2: 'TX_DISABLE'}, (35.9, 3.6), rot=90)
for i, (net, xy) in enumerate([('+3V3', (26.0, 3.3)), ('SWDIO', (26.0, 1.1)), ('SWCLK', (26.0, -1.1)),
                               ('NRST', (26.0, -3.3)), ('GND', (36.5, 0.0))]):
    part(f'TP{i + 1}', 'Connector:TestPoint', net, TP, {1: net}, xy, side='B')

# ---------------------------------------------------------------- MDI, Figure 8-1 / Table 8-1
part('C33', 'Device:C_Small', '100nF 1%', C0402, {1: 'TRD_P', 2: 'DCB_P'}, (38.3, 1.0))
part('C34', 'Device:C_Small', '100nF 1%', C0402, {1: 'TRD_M', 2: 'DCB_N'}, (38.3, -1.0))
# Murata DLW32MH101XT2 is the datasheet's CMC; land = the 3.2 x 2.5 TDK ACT1210
# class footprint, windings 1-4 and 2-3
part('L2', 'Device:L_Coupled_1423', 'DLW32MH101XT2', 'sfp:L_CommonMode_3225',
     {1: 'DCB_P', 4: 'MDI_P', 2: 'DCB_N', 3: 'MDI_N'}, (41.3, 0.0), rot=90, mpn='DLW32MH101XT2')
part('R6', 'Device:R_Small', '1k 1%', R0603, {1: 'MDI_P', 2: 'MDI_CT'}, (44.0, 3.4), rot=0)
part('R7', 'Device:R_Small', '1k 1%', R0603, {1: 'MDI_N', 2: 'MDI_CT'}, (44.0, -3.4), rot=0)
part('C35', 'Device:C_Small', '4.7nF', C0402, {1: 'MDI_CT', 2: 'GND'}, (41.3, 4.6), rot=0)
part('R8', 'Device:R_Small', '100k', R0402, {1: 'MDI_CT', 2: 'GND'}, (41.3, -4.6), rot=0)
part('D2', 'Device:D_TVS', 'ESD (DNP)', 'Diode_SMD:D_0402_1005Metric',
     {1: 'MDI_P', 2: 'GND'}, (44.0, 1.4), dnp=True)
part('D3', 'Device:D_TVS', 'ESD (DNP)', 'Diode_SMD:D_0402_1005Metric',
     {1: 'MDI_N', 2: 'GND'}, (44.0, -1.4), dnp=True)
part('J2', 'sfp:HMTD_1P', 'H-MTD 1-port PCB header - FOOTPRINT PLACEHOLDER', 'sfp:HMTD_1P_Placeholder',
     {1: 'MDI_P', 2: 'MDI_N', 3: 'GND'}, (53.0, 0.0))

LENGTH = 59.5


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
    phy_l = [('3', 'RESET_N', 'input'), ('1', 'MDC', 'input'), ('36', 'MDIO', 'bidirectional'),
             ('2', 'INT_N', 'open_collector'), ('', '', ''), ('5', 'XI', 'input'),
             ('4', 'XO', 'output'), ('', '', ''), ('32', 'TX_P/TX_D1', 'input'),
             ('33', 'TX_M/TX_D0', 'input'), ('24', 'RX_P/RX_D2', 'output'),
             ('23', 'RX_M/RX_D3', 'output'), ('', '', ''), ('25', 'RX_D1', 'output'),
             ('26', 'RX_D0', 'output'), ('27', 'RX_CLK', 'output'), ('28', 'TX_CLK', 'input'),
             ('29', 'TX_CTRL', 'input'), ('30', 'TX_D3', 'input'), ('31', 'TX_D2', 'input'),
             ('15', 'RX_CTRL', 'bidirectional')]
    phy_r = [('11', 'VDDA3P3', 'power_in'), ('7', 'VSLEEP', 'power_in'), ('22', 'VDDIO', 'power_in'),
             ('34', 'VDDIO', 'power_in'), ('9', 'VDD1P0', 'power_in'), ('21', 'VDD1P0', 'power_in'),
             ('', '', ''), ('12', 'TRD_P', 'bidirectional'), ('13', 'TRD_M', 'bidirectional'),
             ('', '', ''), ('35', 'LED_0/MS', 'bidirectional'), ('6', 'LED_1/AUTO', 'bidirectional'),
             ('16', 'CLKOUT', 'bidirectional'), ('14', 'STRP_1', 'input'), ('8', 'WAKE', 'input'),
             ('10', 'INH', 'open_collector'), ('17', 'DNC', 'no_connect'), ('18', 'DNC', 'no_connect'),
             ('19', 'DNC', 'no_connect'), ('20', 'DNC', 'no_connect'), ('37', 'GND(EP)', 'power_in')]
    edge_l = [('16', 'VccT', 'passive'), ('15', 'VccR', 'passive'), ('', '', ''),
              ('18', 'TD+', 'passive'), ('19', 'TD-', 'passive'), ('13', 'RD+', 'passive'),
              ('12', 'RD-', 'passive'), ('', '', ''), ('4', 'SDA', 'passive'), ('5', 'SCL', 'passive'),
              ('3', 'TX_DISABLE', 'passive'), ('2', 'TX_FAULT', 'passive'), ('8', 'RX_LOS', 'passive'),
              ('6', 'MOD_ABS', 'passive'), ('7', 'RS0', 'passive')]
    edge_r = [('1', 'VeeT', 'passive'), ('17', 'VeeT', 'passive'), ('20', 'VeeT', 'passive'),
              ('9', 'VeeR/RS1', 'passive'), ('10', 'VeeR', 'passive'), ('11', 'VeeR', 'passive'),
              ('14', 'VeeR', 'passive')]
    hmtd = [('1', 'MDI+', 'passive'), ('2', 'MDI-', 'passive'), ('3', 'SHIELD', 'passive')]
    lib = '(kicad_symbol_lib (version 20220914) (generator make_t1)\n'
    lib += _symbol('DP83TG720S', 'U', phy_l, phy_r, width=25.4)
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

    # H-MTD: NOT a real land. Two signal pads and four shield pegs in a 10 x 12
    # box so routing and the envelope check have something honest to work
    # with; replace from the connector's drawing before ordering.
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID('sfp', 'HMTD_1P_Placeholder'))
    for num, x, y in (('1', -3.5, -1.0), ('2', -3.5, 1.0)):
        smd(fp, num, x, y, 1.2, 0.7)
    for x, y in ((-4.5, -4.2), (-4.5, 4.2), (4.5, -4.2), (4.5, 4.2)):
        smd(fp, '3', x, y, 1.8, 1.4)
    crt(fp, 6.0, 5.5)
    io.FootprintSave(FPLIB, fp)


# ==========================================================================
# schematic
SHEET = '8a4b1f2e-6c7d-4e8f-9a0b-1c2d3e4f5061'
_SYM = {}


def _u(seed):
    return str(_uuid.uuid5(_uuid.UUID(SHEET), seed))


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
PWR = [0]


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
          % (NAME, SHEET, ref))
    SCH.append(s)


def power(net, x, y, d, seed):
    """Stub out from a pin and end it in a GND / +3V3 symbol."""
    if net == 'GND':
        ex, ey = x + d[0] * 2.54, y + d[1] * 2.54
        wire((x, y), (ex, ey))
        if d != (0, 1):
            wire((ex, ey), (ex, ey + 2.54))
            ey += 2.54
        PWR[0] += 1
        symbol_inst('power:GND', ex, ey, '#PWR%03d' % PWR[0], 'GND', None, seed + 'G', hide=True)
    else:
        ex, ey = x + d[0] * 2.54, y + d[1] * 2.54
        wire((x, y), (ex, ey))
        if d != (0, -1):
            wire((ex, ey), (ex, ey - 2.54))
            ey -= 2.54
        PWR[0] += 1
        symbol_inst('power:+3V3', ex, ey, '#PWR%03d' % PWR[0], '+3V3', None, seed + 'V', hide=True)


SCH_AT = {'J1': (40, 80), 'U1': (160, 110), 'U2': (160, 200), 'U3': (60, 190), 'J2': (330, 110),
          'Y1': (110, 60), 'L2': (270, 110)}
POWER_NETS = ('+3V3', 'VDDA', 'VDDIO', 'VDD1P0', 'V1P0_BUCK', 'VCCT', 'VCCR')


def write_schematic():
    del SCH[:]
    PWR[0] = 0
    # passives in a grid, in netlist order, after the fixed parts
    gx, gy = 40.0, 250.0
    for p in P:
        if p['ref'] in SCH_AT:
            p['sch'] = tuple(snap(v) for v in SCH_AT[p['ref']])
        else:
            p['sch'] = (snap(gx), snap(gy))
            gx += 22.86
            if gx > 380:
                gx, gy = 40.0, gy + 22.86
    used = sorted({p['lib_id'] for p in P} | {'power:GND', 'power:+3V3', 'power:PWR_FLAG'})
    for p in P:
        X, Y = p['sch']
        symbol_inst(p['lib_id'], X, Y, p['ref'], p['value'], p['fp'], p['ref'], dnp=p['dnp'],
                    props=(('MPN', p['mpn']),) if p['mpn'] else ())
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
    for net in POWER_NETS + ('GND',):
        PWR[0] += 1
        x, y = snap(fx), snap(30.0)
        symbol_inst('power:PWR_FLAG', x, y, '#FLG%02d' % PWR[0], 'PWR_FLAG', None, 'F' + net, hide=True)
        wire((x, y), (x + 5.08, y))
        if net in ('GND', '+3V3'):
            PWR[0] += 1
            symbol_inst('power:' + net, x + 5.08, y, '#PWR%03d' % PWR[0], net, None, 'FP' + net, hide=True)
        else:
            label(x + 5.08, y, net, (1, 0))
        fx += 25.4
    out = '(kicad_sch (version 20230121) (generator eeschema)\n  (uuid %s)\n  (paper "A2")\n' % SHEET
    out += ('  (title_block (title "SFP 100/1000BASE-T1 - DP83TG720S / DP83TC812S") (rev "0.1")\n'
            '    (comment 1 "Generated by hw/t1/make_t1.py - edit the netlist there, not here"))\n')
    out += '  (lib_symbols\n'
    for lid in used:
        blk, _ = sym_block(lid)
        name = lid.split(':', 1)[1]
        out += blk.replace('(symbol "%s" ' % name, '(symbol "%s" ' % lid, 1) + '\n'
    out += '  )\n' + ''.join(SCH) + '  (sheet_instances (path "/" (page "1")))\n)\n'
    open(os.path.join(HERE, NAME + '.kicad_sch'), 'w').write(out)


def write_libtables():
    open(os.path.join(HERE, 'sym-lib-table'), 'w').write(
        '(sym_lib_table\n  (lib (name "sfp")(type "KiCad")(uri "${KIPRJMOD}/../sym/sfp.kicad_sym")(options "")(descr ""))\n)\n')
    open(os.path.join(HERE, 'fp-lib-table'), 'w').write(
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
    MB.poly(board, pcbnew.Edge_Cuts, MB.outline_pts(LENGTH))
    MB.seg(board, pcbnew.Dwgs_User, (MB.CAGE_FRONT, 7.5), (MB.CAGE_FRONT, -7.5), 0.15)
    MB.text(board, pcbnew.Dwgs_User, 'cage front', MB.CAGE_FRONT, 8.4, 0.8)
    MB.text(board, pcbnew.F_SilkS, 'T1 SFP', 50.0, 5.4, 0.8)
    for p in P:
        fp = MB.edge_footprint() if p['ref'] == 'J1' else fp_load(p['fp'])
        fp.SetReference(p['ref'])
        fp.SetValue(p['value'])
        fp.Value().SetVisible(False)
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
            if p['ref'] == 'U1' and num == '37':
                pad.SetZoneConnection(pcbnew.ZONE_CONNECTION_FULL)   # EP + thermal vias: solid
    path = os.path.join(HERE, NAME + '.kicad_pcb')
    board.Save(path)
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
FREEROUTING = os.path.expanduser('~/.local/share/freerouting/freerouting-1.9.0.jar')
SGMII = ['TD_P', 'TD_N', 'RD_P', 'RD_N', 'SG_TX_P', 'SG_TX_N', 'SG_RX_P', 'SG_RX_N']
MDI = ['TRD_P', 'TRD_M', 'DCB_P', 'DCB_N', 'MDI_P', 'MDI_N']
PWR = ['+3V3', 'VDDA', 'VDDIO', 'VDD1P0', 'V1P0_BUCK', 'BUCK_SW', 'VCCT', 'VCCR']
# 4 layers: F signal / In1 GND / In2 +3V3 / B signal. Widths are for a thin
# outer dielectric (~0.1 mm, 1.0 mm board) and MUST be re-derived from the
# fab's own stackup and impedance calculator before ordering.
NETCLASSES = [
    dict(name='Default', clearance=0.15, track_width=0.127, via_diameter=0.45, via_drill=0.25),
    dict(name='SGMII', clearance=0.15, track_width=0.12, via_diameter=0.45, via_drill=0.25,
         dp_width=0.12, dp_gap=0.15, nets=SGMII),
    dict(name='MDI', clearance=0.2, track_width=0.2, via_diameter=0.45, via_drill=0.25,
         dp_width=0.2, dp_gap=0.2, nets=MDI),
    dict(name='Power', clearance=0.15, track_width=0.3, via_diameter=0.5, via_drill=0.3, nets=PWR),
]


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
    for c in NETCLASSES:
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
    for c in NETCLASSES:
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
           'meta': {'filename': NAME + '.kicad_pro', 'version': 1},
           'net_settings': {'classes': classes, 'meta': {'version': 3}, 'net_colors': None,
                            'netclass_assignments': assign, 'netclass_patterns': []},
           'pcbnew': {'last_paths': {}, 'page_layout_descr_file': ''},
           'schematic': {'legacy_lib_dir': '', 'legacy_lib_list': []},
           'sheets': [[SHEET, '']], 'text_variables': {}}
    json.dump(pro, open(os.path.join(HERE, NAME + '.kicad_pro'), 'w'), indent=2)


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
    pts = MB.outline_pts(LENGTH)
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


def add_planes(board):
    inset = 0.3
    pts = [(x, y - inset if y > 0 else y + inset) for x, y in MB.outline_pts(LENGTH)]
    pts = [(max(inset, min(LENGTH - inset, x)), y) for x, y in pts]
    zone(board, 'GND', pcbnew.In1_Cu, pts, clearance=0.15)
    zone(board, '+3V3', pcbnew.In2_Cu, pts, clearance=0.15)


def add_outer_pours(board):
    """After routing, never before: in the DSN a pour on F/B reads as a solid
    plane and the router finds no room on the signal layers. On a 12.4 mm board
    the signal vias' antipads cut In1 into islands; these stitch them back.
    SMD pads join solidly (0201 thermals starve), THT keeps spokes."""
    inset = 0.3
    pts = [(x, y - inset if y > 0 else y + inset) for x, y in MB.outline_pts(LENGTH)]
    pts = [(max(inset, min(LENGTH - inset, x)), y) for x, y in pts]
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


def route(passes=20, reuse_ses=False):
    """Freerouting 1.9.0: 2.x ignores its pass limit on the command line and
    never ends on this board; 1.9.0 honours -mp but wants a display, so it
    gets a virtual one."""
    path = os.path.join(HERE, NAME + '.kicad_pcb')
    board = pcbnew.LoadBoard(path)
    apply_rules(board)
    add_edge_keepouts(board)
    add_planes(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    dsn = os.path.join(HERE, NAME + '.dsn')
    ses = os.path.join(HERE, NAME + '.ses')
    if not (reuse_ses and os.path.exists(ses)):
        pcbnew.ExportSpecctraDSN(board, dsn)
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
    nw, nv = import_ses(board, ses)
    add_outer_pours(board)
    pcbnew.ZONE_FILLER(board).Fill(board.Zones())
    board.Save(path)
    rpt = os.path.join(HERE, 'drc.rpt')
    pcbnew.WriteDRCReport(board, rpt, pcbnew.EDA_UNITS_MILLIMETRES, True)
    txt = open(rpt).read()
    print(f'routed: {nw} wires, {nv} vias')
    for line in txt.splitlines():
        if line.startswith('**'):
            print('  ' + line)
    return board

def main():
    write_symbols()
    write_footprints()
    write_libtables()
    write_schematic()
    write_project()
    board = build_pcb()
    bad = check_pcb(board)
    n_nets = len({n for p in P for n in p['nets'].values() if n})
    print(f'{NAME}: {len(P)} parts, {n_nets} nets')
    for b in bad:
        print('  !!', b)
    print('placement OK' if not bad else f'{len(bad)} placement problems')
    if bad:
        return 1
    if '--route' in sys.argv or '--reuse-ses' in sys.argv:
        route(reuse_ses='--reuse-ses' in sys.argv)
    return 0


if __name__ == '__main__':
    sys.exit(main())

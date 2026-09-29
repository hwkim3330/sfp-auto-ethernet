#!/usr/bin/env python3
"""SFP 100M / 1G / 2.5GBASE-T (RJ45) module: symbols, schematic, PCB.

    python3 make_rj45.py [--route]

Sources:
  RTL8221B(I)-VB/VM datasheet Rev 1.0 (LCSC C5155988)  pins (section 6),
      power (6.8: 0.95 V core has NO internal regulator), SerDes caps
      (0402 0.1 uF, TX pair near the PHY), RSET 2.49k 1%, MDIO 1.5k pull-up,
      straps (PHYAD on LED0..2 -> default address 1; CFG_OPT0/1 pulled down:
      no CLKOUT, no MDI swap)
  LINK-PP LP72450ANL (C53281905)  2.5GBASE-T 4-pair magnetics: pinout sheet 1,
      recommended pad layout sheet 2 (2 x 12, 1.0 pitch, 0.60 x 1.35, rows
      8.0 apart inside / 10.70 outside)
  Amphenol 54602-908LF (C2847314)  plain RJ45, no magnetics (KiCad footprint
      RJ45_Amphenol_54602-x08_Horizontal)
  TPS6282x (SLVSDV6C)  the core buck, set to 0.95 V: R1 57.6k / R2 100k ->
      0.946 V (the datasheet allows 0.92 .. 0.98)

The jack sits on a nose outside the cage, wider than the SFP body - the way
commercial copper SFPs carry theirs (the housing there is the module's own).
Inside the cage everything stays under the 4.65 mm above the PCB; the
magnetics are 4.0 mm.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import sfpgen                            # noqa: E402
from sfpgen import (C0201, C0402, C0603, R0201, R0402, R0603, FB0603, LED0402,  # noqa: E402,F401
                    TP)

NAME = 'rj45'
TITLE = 'RJ45 2.5G SFP'
SHEET = '3c9d2e71-5a4b-4f60-8d1e-7b2c3a4d5e61'

P = []


def part(ref, lib_id, value, fp, nets, at, side='F', rot=0, dnp=False, mpn=''):
    P.append(dict(ref=ref, lib_id=lib_id, value=value, fp=fp, nets=nets, at=at,
                  side=side, rot=rot, dnp=dnp, mpn=mpn))


# ---------------------------------------------------------------- SFP edge
EDGE = {1: 'GND', 2: 'TX_FAULT', 3: 'TX_DISABLE', 4: 'SDA', 5: 'SCL', 6: 'GND',
        7: None, 8: 'RX_LOS', 9: 'GND', 10: 'GND', 11: 'GND', 12: 'RD_N', 13: 'RD_P',
        14: 'GND', 15: 'VCCR', 16: 'VCCT', 17: 'GND', 18: 'TD_P', 19: 'TD_N', 20: 'GND'}
part('J1', 'sfp:SFP_EDGE', 'SFP edge (INF-8074i)', 'sfp:SFP_Module_Edge', EDGE, (0, 0))
part('FB1', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'VCCT', 2: '+3V3'}, (8.9, 4.9), mpn='BLM18KG601SH1')
part('FB2', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'VCCR', 2: '+3V3'}, (8.9, -4.9), mpn='BLM18KG601SH1')
part('C1', 'Device:C_Small', '10uF', C0603, {1: '+3V3', 2: 'GND'}, (8.9, 3.2))
part('C2', 'Device:C_Small', '100nF', C0402, {1: '+3V3', 2: 'GND'}, (8.9, -3.2), side='B')

# host -> module (TD) coupling at the fingers; module -> host (RD) near the
# PHY's HSOP/HSON, as the datasheet asks for the PHY's TX pair
part('C3', 'Device:C_Small', '100nF', C0201, {1: 'TD_P', 2: 'HSI_P'}, (5.2, 2.2))
part('C4', 'Device:C_Small', '100nF', C0201, {1: 'TD_N', 2: 'HSI_N'}, (5.2, 3.0))
part('C5', 'Device:C_Small', '100nF', C0402, {1: 'HSO_P', 2: 'RD_P'}, (14.8, -1.9), rot=90)
part('C6', 'Device:C_Small', '100nF', C0402, {1: 'HSO_N', 2: 'RD_N'}, (14.8, -3.2), rot=90)

# ---------------------------------------------------------------- PHY
PHY = {1: 'PHY_RST_N', 2: 'MDC', 3: 'MDIO', 4: 'V0P95', 5: '+3V3', 6: None, 7: 'AVDD33',
       8: 'AVDD33', 9: 'XO', 10: 'XI', 11: 'AVDD09', 12: 'RSET', 13: 'MDI0_P', 14: 'MDI0_N',
       15: 'AVDD33', 16: 'AVDD09', 17: 'MDI1_P', 18: 'MDI1_N', 19: 'AVDD33', 20: 'MDI2_P',
       21: 'MDI2_N', 22: 'AVDD09', 23: 'MDI3_P', 24: 'MDI3_N', 25: None, 26: None, 27: None,
       28: 'V0P95', 29: 'CFG0', 30: 'CFG1', 31: '+3V3', 32: None, 33: None, 34: None, 35: None,
       36: 'V0P95', 37: 'HSO_N', 38: 'HSO_P', 39: 'GND', 40: 'HSI_P', 41: 'HSI_N', 42: '+3V3',
       43: 'V0P95', 44: None, 45: None, 46: None, 47: None, 48: 'PHY_INT_N', 49: 'GND'}
part('U1', 'sfp:RTL8221B', 'RTL8221B-VB-CG', 'Package_DFN_QFN:QFN-48-1EP_6x6mm_P0.4mm_EP4.3x4.3mm_ThermalVias',
     PHY, (20.0, 0.0), rot=0, mpn='RTL8221B-VB-CG')
part('R9', 'Device:R_Small', '2.49k 1%', R0201, {1: 'RSET', 2: 'GND'}, (24.2, -4.2))
part('R10', 'Device:R_Small', '1.5k', R0201, {1: '+3V3', 2: 'MDIO'}, (15.9, 4.5))
part('R11', 'Device:R_Small', '4.7k', R0201, {1: '+3V3', 2: 'PHY_INT_N'}, (15.9, 3.7))
part('R12', 'Device:R_Small', '4.7k', R0201, {1: 'CFG0', 2: 'GND'}, (24.2, 4.4))
part('R13', 'Device:R_Small', '4.7k', R0201, {1: 'CFG1', 2: 'GND'}, (24.2, 3.6))

# analog islands: ripple limit 15 mVpp on AVDD09 / AVDD33 (datasheet 9.6)
part('FB3', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'V0P95', 2: 'AVDD09'}, (15.3, -5.0), side='B', mpn='BLM18KG601SH1')
part('FB4', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: '+3V3', 2: 'AVDD33'}, (15.3, 5.0), side='B', mpn='BLM18KG601SH1')
DECAP = [('V0P95', ('100nF',) * 4 + ('10uF',)), ('AVDD09', ('100nF',) * 3 + ('10uF',)),
         ('AVDD33', ('100nF',) * 4 + ('10uF',)), ('+3V3', ('100nF',) * 3)]
_slots = [(16.4, 2.4, 0), (16.4, 1.4, 0), (16.4, -1.4, 0), (16.4, -2.4, 0),        # ring under the PHY
          (23.6, 2.4, 0), (23.6, 1.4, 0), (23.6, -1.4, 0), (23.6, -2.4, 0),
          (18.2, 3.6, 90), (19.2, 3.6, 90), (20.8, 3.6, 90), (21.8, 3.6, 90),
          (18.2, -3.6, 90), (19.2, -3.6, 90), (20.8, -3.6, 90)]
_bulk = [(12.6, -4.6, 0), (26.8, -4.4, 0), (12.6, 4.6, 0)]
_n = 7
for net, vals in DECAP:
    for v in vals:
        if v == '10uF':
            x, y, r = _bulk.pop(0)
            part(f'C{_n}', 'Device:C_Small', v, C0603, {1: net, 2: 'GND'}, (x, y), side='B', rot=r)
        else:
            x, y, r = _slots.pop(0)
            part(f'C{_n}', 'Device:C_Small', v, C0201, {1: net, 2: 'GND'}, (x, y), side='B', rot=r)
        _n += 1

# 25 MHz crystal: datasheet 27 pF load caps; the SL201625M20P (CL 20 pF)
part('Y1', 'Device:Crystal_GND24_Small', '25MHz CL20pF 2016', 'Crystal:Crystal_SMD_2016-4Pin_2.0x1.6mm',
     {1: 'XI', 2: 'GND', 3: 'XO', 4: 'GND'}, (16.2, -4.4), mpn='SL201625M20P')
part('C30', 'Device:C_Small', '27pF', C0201, {1: 'XI', 2: 'GND'}, (14.0, -4.9))
part('C31', 'Device:C_Small', '27pF', C0201, {1: 'XO', 2: 'GND'}, (18.3, -4.9))

# ---------------------------------------------------------------- 0.95 V buck
part('U3', 'Regulator_Switching:TPS62823DLC', 'TPS62822DLC', 'Package_DFN_QFN:Texas_VSON-HR-8_1.5x2mm_P0.5mm',
     {1: '+3V3', 2: 'BUCK_FB', 3: 'GND', 4: None, 5: 'GND', 6: 'BUCK_SW', 7: '+3V3', 8: None},
     (12.0, 1.2), mpn='TPS62822DLCR')
part('L1', 'Device:L_Small', '470nH DFE201610E-R47M', 'Inductor_SMD:L_Murata_DFE201610P',
     {1: 'BUCK_SW', 2: 'V0P95'}, (12.0, -1.6), mpn='DFE201610E-R47M')
part('C32', 'Device:C_Small', '4.7uF', C0402, {1: '+3V3', 2: 'GND'}, (10.1, 1.2), rot=90)
part('C33', 'Device:C_Small', '10uF', C0603, {1: 'V0P95', 2: 'GND'}, (9.4, -1.6), rot=90)
part('C34', 'Device:C_Small', '10uF', C0603, {1: 'V0P95', 2: 'GND'}, (12.0, -1.9), side='B')
part('R3', 'Device:R_Small', '57.6k 1%', R0201, {1: 'V0P95', 2: 'BUCK_FB'}, (14.3, 2.8))
part('R4', 'Device:R_Small', '100k 1%', R0201, {1: 'BUCK_FB', 2: 'GND'}, (14.3, 2.0))
part('C35', 'Device:C_Small', '120pF', C0201, {1: 'V0P95', 2: 'BUCK_FB'}, (14.3, 1.2))

# ---------------------------------------------------------------- magnetics
# chip side pins 1..12 on one long side, cable side 13..24 on the other
MAG = {2: 'MDI0_P', 3: 'MDI0_N', 1: 'TCT0', 5: 'MDI1_P', 6: 'MDI1_N', 4: 'TCT1',
       8: 'MDI2_P', 9: 'MDI2_N', 7: 'TCT2', 11: 'MDI3_P', 12: 'MDI3_N', 10: 'TCT3',
       23: 'LINE0_P', 22: 'LINE0_N', 24: 'CMT0', 20: 'LINE1_P', 19: 'LINE1_N', 21: 'CMT1',
       17: 'LINE2_P', 16: 'LINE2_N', 18: 'CMT2', 14: 'LINE3_P', 13: 'LINE3_N', 15: 'CMT3'}
part('T1', 'sfp:LP72450ANL', 'LP72450ANL', 'sfp:LINKPP_LP72450ANL', MAG, (36.0, 0.0), mpn='LP72450ANL')
for i in range(4):          # PHY-side centre taps to ground through 100 nF (voltage-mode driver)
    part(f'C{36 + i}', 'Device:C_Small', '100nF', C0402, {1: f'TCT{i}', 2: 'GND'},
         (29.8 + 2.6 * i, -5.6), rot=0)
for i in range(4):          # Bob Smith: 75 R from each line-side centre tap to a common node
    part(f'R{14 + i}', 'Device:R_Small', '75', R0402, {1: f'CMT{i}', 2: 'BOB'},
         (29.8 + 2.6 * i, 5.6), rot=0)
part('C40', 'Device:C_Small', '1nF 2kV', 'Capacitor_SMD:C_1206_3216Metric', {1: 'BOB', 2: 'GND'},
     (43.0, 4.4), rot=90, mpn='1nF 2kV X7R 1206')

# ---------------------------------------------------------------- RJ45
# T568: pair A on 1/2, B on 3/6, C on 4/5, D on 7/8. Shield tabs to ground.
RJ = {1: 'LINE0_P', 2: 'LINE0_N', 3: 'LINE1_P', 6: 'LINE1_N', 4: 'LINE2_P', 5: 'LINE2_N',
      7: 'LINE3_P', 8: 'LINE3_N'}
part('J2', 'sfp:RJ45_8P8C', 'Amphenol 54602-908LF', 'Connector_RJ:RJ45_Amphenol_54602-x08_Horizontal',
     RJ, (52.0, 4.445), rot=90, mpn='54602-908LF')

# ---------------------------------------------------------------- MCU
MCU = {1: 'SDA', 2: None, 3: None, 4: '+3V3', 5: 'GND', 6: 'NRST', 7: 'MDC', 8: 'MDIO',
       9: 'PHY_RST_N', 10: 'PHY_INT_N', 11: 'TX_DISABLE', 12: 'RX_LOS', 13: 'TX_FAULT',
       14: None, 15: None, 16: None, 17: None, 18: 'SWDIO', 19: 'SWCLK', 20: 'SCL'}
part('U2', 'MCU_ST_STM32G0:STM32G031F_4-6-8_Px', 'STM32G031F6P6', 'Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm',
     MCU, (36.0, 0.0), side='B', rot=90, mpn='STM32G031F6P6')
part('C41', 'Device:C_Small', '100nF', C0402, {1: '+3V3', 2: 'GND'}, (31.4, 3.6), side='B', rot=90)
part('C42', 'Device:C_Small', '1uF', C0402, {1: '+3V3', 2: 'GND'}, (31.4, -3.6), side='B', rot=90)
part('C43', 'Device:C_Small', '100nF', C0402, {1: 'NRST', 2: 'GND'}, (40.6, 3.6), side='B', rot=90)
part('R5', 'Device:R_Small', '10k', R0402, {1: '+3V3', 2: 'TX_DISABLE'}, (40.6, -3.6), side='B', rot=90)
for i, (net, xy) in enumerate([('+3V3', (27.0, 3.4)), ('SWDIO', (27.0, 1.2)), ('SWCLK', (27.0, -1.2)),
                               ('NRST', (27.0, -3.4)), ('GND', (43.2, 0.0))]):
    part(f'TP{i + 1}', 'Connector:TestPoint', net, TP, {1: net}, xy, side='B')

LENGTH = 68.0
NOSE_X, NOSE_W = 45.0, 16.0          # from x = 45 the board widens to 16 mm (outside the cage)


# ---------------------------------------------------------------- symbols
def _rtl_symbol():
    L = [('1', 'PHYRSTB', 'input'), ('2', 'MDC', 'input'), ('3', 'MDIO', 'bidirectional'),
         ('48', 'INTB/PMEB', 'open_collector'), ('', '', ''), ('10', 'CKXTAL1', 'input'),
         ('9', 'CKXTAL2', 'output'), ('6', 'CLKOUT', 'output'), ('12', 'RSET', 'passive'), ('', '', ''),
         ('40', 'HSIP', 'input'), ('41', 'HSIN', 'input'), ('38', 'HSOP', 'output'), ('37', 'HSON', 'output'),
         ('', '', ''), ('29', 'CFG_OPT0', 'bidirectional'), ('30', 'CFG_OPT1', 'bidirectional'),
         ('33', 'LED0/PHYAD0', 'bidirectional'), ('34', 'LED1/PHYAD1', 'bidirectional'),
         ('35', 'LED2/PHYAD2', 'bidirectional'), ('46', 'POW_EXT_SWR', 'output'),
         ('25', 'SPISO', 'input'), ('26', 'SPICSB', 'output'), ('27', 'SPISCK', 'output'), ('32', 'SPISI', 'output')]
    R = [('4', 'DVDD09', 'power_in'), ('28', 'DVDD09', 'power_in'), ('43', 'DVDD09', 'power_in'),
         ('36', 'EVDD09', 'power_in'), ('11', 'AVDD09', 'power_in'), ('16', 'AVDD09', 'power_in'),
         ('22', 'AVDD09', 'power_in'), ('7', 'AVDD33', 'power_in'), ('15', 'AVDD33', 'power_in'),
         ('19', 'AVDD33', 'power_in'), ('8', 'AVDD33_XTAL', 'power_in'), ('31', 'DVDD33', 'power_in'),
         ('42', 'DVDD33', 'power_in'), ('5', 'DVDD3318', 'power_in'), ('', '', ''),
         ('13', 'MDIP0', 'bidirectional'), ('14', 'MDIN0', 'bidirectional'), ('17', 'MDIP1', 'bidirectional'),
         ('18', 'MDIN1', 'bidirectional'), ('20', 'MDIP2', 'bidirectional'), ('21', 'MDIN2', 'bidirectional'),
         ('23', 'MDIP3', 'bidirectional'), ('24', 'MDIN3', 'bidirectional'), ('', '', ''),
         ('39', 'GND', 'power_in'), ('49', 'GND(EP)', 'power_in'), ('44', 'NC', 'no_connect'),
         ('45', 'NC', 'no_connect'), ('47', 'NC', 'no_connect')]
    return ('RTL8221B', 'U', L, R, 27.94)


def _mag_symbol():
    L = [('2', 'TD1+', 'passive'), ('1', 'TCT1', 'passive'), ('3', 'TD1-', 'passive'),
         ('5', 'TD2+', 'passive'), ('4', 'TCT2', 'passive'), ('6', 'TD2-', 'passive'),
         ('8', 'TD3+', 'passive'), ('7', 'TCT3', 'passive'), ('9', 'TD3-', 'passive'),
         ('11', 'TD4+', 'passive'), ('10', 'TCT4', 'passive'), ('12', 'TD4-', 'passive')]
    R = [('23', 'TX1+', 'passive'), ('24', 'CMT1', 'passive'), ('22', 'TX1-', 'passive'),
         ('20', 'TX2+', 'passive'), ('21', 'CMT2', 'passive'), ('19', 'TX2-', 'passive'),
         ('17', 'TX3+', 'passive'), ('18', 'CMT3', 'passive'), ('16', 'TX3-', 'passive'),
         ('14', 'TX4+', 'passive'), ('15', 'CMT4', 'passive'), ('13', 'TX4-', 'passive')]
    return ('LP72450ANL', 'T', L, R, 17.78)


def _rj_symbol():
    L = [(str(i), str(i), 'passive') for i in range(1, 9)] + [('SH', 'SHIELD', 'passive')]
    return ('RJ45_8P8C', 'J', L, [], 10.16)


SYMBOLS = [_rtl_symbol(), _mag_symbol(), _rj_symbol()]
SOLID_PADS = {('U1', '49')}
HMTD_AT = None


def FOOTPRINTS(io, smd, crt):
    """LINK-PP LP72450ANL, recommended pad layout (datasheet sheet 2):
    2 x 12 pads 0.60 x 1.35 at 1.0 pitch, 11.0 first to last; rows 8.0 apart
    inside and 10.70 outside -> pad centres at +/-4.675. Pin 1 at the
    bottom-left (chip side 1..12 left to right), 13..24 back along the top."""
    import pcbnew
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID('sfp', 'LINKPP_LP72450ANL'))
    for i in range(12):
        smd(fp, str(i + 1), -5.5 + i, 4.675, 0.60, 1.35)          # bottom row (KiCad +y is down)
        smd(fp, str(24 - i), -5.5 + i, -4.675, 0.60, 1.35)        # top row, 13..24 right to left
    crt(fp, 7.85, 5.6)
    io.FootprintSave(sfpgen.FPLIB, fp)


# ---------------------------------------------------------------- schematic / rules
SCH_AT = {'J1': (40, 80), 'U1': (170, 115), 'U2': (170, 215), 'U3': (60, 190), 'T1': (280, 115),
          'J2': (360, 115), 'Y1': (110, 60)}
POWER_NETS = ('+3V3', 'V0P95', 'AVDD09', 'AVDD33', 'VCCT', 'VCCR')
HS = ['TD_P', 'TD_N', 'RD_P', 'RD_N', 'HSI_P', 'HSI_N', 'HSO_P', 'HSO_N']
MDI = [f'MDI{i}_{s}' for i in range(4) for s in 'PN'] + [f'LINE{i}_{s}' for i in range(4) for s in 'PN']
PWR = ['+3V3', 'V0P95', 'AVDD09', 'AVDD33', 'BUCK_SW', 'VCCT', 'VCCR']
# JLC04101H-3313: 50 ohm single-ended = 0.157 mm on L1 over L2 (JLC SI9000)
NETCLASSES = [
    dict(name='Default', clearance=0.127, track_width=0.127, via_diameter=0.45, via_drill=0.25),
    dict(name='SGMII', clearance=0.15, track_width=0.157, via_diameter=0.45, via_drill=0.25,
         dp_width=0.114, dp_gap=0.152, nets=HS),
    dict(name='MDI', clearance=0.15, track_width=0.157, via_diameter=0.45, via_drill=0.25,
         dp_width=0.114, dp_gap=0.152, nets=MDI),
    dict(name='Power', clearance=0.15, track_width=0.2, via_diameter=0.5, via_drill=0.3, nets=PWR),
]
PAIRS = [('TD_P', 'TD_N'), ('HSI_P', 'HSI_N'), ('RD_P', 'RD_N'), ('HSO_P', 'HSO_N')] + \
        [(f'MDI{i}_P', f'MDI{i}_N') for i in range(4)] + [(f'LINE{i}_P', f'LINE{i}_N') for i in range(4)]

LCSC_BY_MPN = {'RTL8221B-VB-CG': 'C5155988', 'STM32G031F6P6': 'C529333', 'TPS62822DLCR': 'C473385',
               'DFE201610E-R47M': 'C269773', 'BLM18KG601SH1': 'C710379', 'LP72450ANL': 'C53281905',
               '54602-908LF': 'C2847314', 'SL201625M20P': 'C5155510'}
LCSC_BY_VALUE = {('100nF', C0201): 'C76928', ('100nF', C0402): 'C1525', ('10uF', C0603): 'C19702',
                 ('4.7uF', C0402): 'C23733', ('1uF', C0402): 'C52923', ('120pF', C0201): 'C161406',
                 ('10k', R0402): 'C25744', ('100k 1%', R0201): 'C106224'}
LCSC_TODO = {'2.49k 1%', '1.5k', '4.7k', '57.6k 1%', '75', '27pF', '1nF 2kV'}   # to look up before ordering


def lcsc_for(p):
    if p['dnp'] or p['ref'].startswith('TP') or p['ref'] == 'J1':
        return ''
    return LCSC_BY_MPN.get(p['mpn']) or LCSC_BY_VALUE.get((p['value'], p['fp']), '')


if __name__ == '__main__':
    sys.exit(sfpgen.run(sys.modules[__name__]))

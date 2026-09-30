#!/usr/bin/env python3
"""SFP 100M / 1G / 2.5GBASE-T (RJ45) module: symbols, schematic, PCB.

    python3 make_rj45.py [--route | --reuse-ses]

Sources (all in the order sheet; the datasheets are LCSC's copies):
  RTL8221B(I)-VB/VM datasheet Rev 1.0 (LCSC C5155988)
      pins section 6; power table 8 and 9.x: 0.95 V core has NO internal
      regulator, 88 mA @ 3.3 V + 364 mA @ 0.95 V typical (650 mA max);
      power sequence 8.8: 3.3 V rise 0.5..10 ms, 0.95 V rise 0.5..5 ms, and
      pin 46 POW_EXT_SWR should switch the 0.95 V converter; SerDes 6.3:
      0402 0.1 uF on HSOP/HSON next to the PHY, the HSI caps at the MAC end
      (the module's TD caps, as the SFP MSA puts them); RSET 2.49k 1%; MDIO
      1.5k pull-up; clock 9.5: an oscillator into CKXTAL1, CKXTAL2 open,
      <= 2 ps RMS jitter (10 kHz..20 MHz), +/-50 ppm;
      straps 6.5: PHYAD from the LED pins' internal pulls -> address 1,
      CFG_OPT0 down (no CLKOUT), CFG_OPT1 up (MDI swap, see below)
  LINK-PP LP72450ANL (C53281905)  2.5GBASE-T 4-channel magnetics, 15.2 x 7.1
      x 4.0 (+0.3) mm: pinout sheet 1, pad layout sheet 2
  Kinghelm KH-RJ45-58-8P8C (C2683360)  shielded jack, 15.7 wide x 13.2 tall
      x 18.2 deep, no magnetics, no LEDs
  MST8011AI-72-33E25 (C51026225)  2016 3.3 V oscillator, +/-25 ppm, RMS phase
      jitter 1.3 ps typ / 2.0 ps max (12 kHz..20 MHz) - meets the PHY's 2 ps,
      at its limit in the worst case. A crystal (two leads on opposite
      corners, a ground pad beside each) could not be routed out from under
      the PHY on an 11.8 mm board; the oscillator needs one line.
  TPS22918 (C131941)  load switch: the host's 3.3 V arrives in tens of us on
      hot plug, the PHY wants 0.5..10 ms and the MSA 30 mA of inrush at most
  TPS6282x (SLVSDV6C)  the core buck: 0.6 V x (1 + 57.6k/100k) = 0.946 V
      (the PHY allows 0.92..0.98); 1.25 ms soft start (0.5..5 ms asked for)

Board: the MSA body (11.8 mm) up to the cage front, then a nose 17 mm wide
for the jack, which sits entirely outside the cage. A jack is 15.7 wide, a
copper SFP's housing 13.7 (theirs is custom), so next to another module in
a ganged cage the jack may touch its neighbour.

Signal flow decided the orientation of U1:
  - SerDes. QFN pins run anticlockwise seen from the top, and the SFP edge
    runs TD-, TD+, RD+, RD- top to bottom: on the top side every rotation
    arrives mirrored (both pairs reversed and crossed). U1 is on the BOTTOM,
    turned 90, where pins 37..41 read HSIN, HSIP, HSOP, HSON top to bottom:
    straight across, no crossing. The PHY has no documented SerDes polarity
    swap, so this is the only way that does not need vias in the pairs.
  - MDI. Pins 13..24 then face the magnetics. Fanned into the chip-side row
    they land port 3 on channel 1 ... port 0 on channel 4, N before P. The
    PHY corrects polarity (7.24) and pair order for 1G/2.5G, and CFG_OPT1
    pulled up (MDI swap) maps port 3 -> channel A, port 2 -> B, so the
    100BASE-TX pairs still reach jack pins 1/2 and 3/6.
"""
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import sfpgen                            # noqa: E402
from sfpgen import (C0201, C0402, C0603, R0201, R0402, R0603, FB0603, LED0402,  # noqa: E402,F401
                    TP)

NAME = 'rj45'
TITLE = 'RJ45 SFP'
SCH_TITLE = 'SFP 100M/1G/2.5GBASE-T - RTL8221B'
TITLE_AT = (52.8, 0.0)          # bottom label under the jack, clear of every pad
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

# host rails through a bead each, then a slew-limited load switch: the
# module's own 3.3 V ramps in ~3.6 ms (CT 2.2 nF, TPS22918 table 2) and
# charges ~30 uF at ~28 mA
part('FB1', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'VCCT', 2: 'VIN_RAW'}, (8.9, 4.9), mpn='BLM18KG601SH1')
part('FB2', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'VCCR', 2: 'VIN_RAW'}, (8.9, -4.9), mpn='BLM18KG601SH1')
part('C1', 'Device:C_Small', '1uF', C0402, {1: 'VIN_RAW', 2: 'GND'}, (8.9, 3.3))
part('C2', 'Device:C_Small', '100nF', C0402, {1: 'VIN_RAW', 2: 'GND'}, (8.9, -4.9), side='B')
part('U4', 'Power_Management:TPS22917DBV', 'TPS22918DBVR', 'Package_TO_SOT_SMD:SOT-23-6',
     {1: 'VIN_RAW', 2: 'GND', 3: 'VIN_RAW', 4: 'SS_CT', 5: '+3V3', 6: '+3V3'}, (12.9, 3.8), mpn='TPS22918DBVR')
part('C44', 'Device:C_Small', '2.2nF', C0402, {1: 'SS_CT', 2: 'GND'}, (15.5, 3.0), rot=90)
part('C45', 'Device:C_Small', '10uF', C0603, {1: '+3V3', 2: 'GND'}, (16.5, 4.9))

# SerDes: host -> module (TD) coupled at the fingers, module -> host (RD)
# next to the PHY's HSOP/HSON (datasheet 6.3), on its side (the bottom)
part('C3', 'Device:C_Small', '100nF', C0201, {1: 'TD_P', 2: 'HSI_P'}, (5.2, 2.2))
part('C4', 'Device:C_Small', '100nF', C0201, {1: 'TD_N', 2: 'HSI_N'}, (5.2, 3.0))
part('C5', 'Device:C_Small', '100nF', C0402, {1: 'HSO_P', 2: 'RD_P'}, (15.0, -1.8), side='B', rot=180)
part('C6', 'Device:C_Small', '100nF', C0402, {1: 'HSO_N', 2: 'RD_N'}, (15.0, -2.75), side='B', rot=180)

# ---------------------------------------------------------------- PHY (bottom side)
PHY = {1: 'PHY_RST_N', 2: 'MDC', 3: 'MDIO', 4: 'V0P95', 5: '+3V3', 6: None, 7: 'AVDD33',
       8: 'AVDD33', 9: None, 10: 'XI', 11: 'AVDD09', 12: 'RSET', 13: 'MDI0_P', 14: 'MDI0_N',
       15: 'AVDD33', 16: 'AVDD09', 17: 'MDI1_P', 18: 'MDI1_N', 19: 'AVDD33', 20: 'MDI2_P',
       21: 'MDI2_N', 22: 'AVDD09', 23: 'MDI3_P', 24: 'MDI3_N', 25: None, 26: None, 27: None,
       28: 'V0P95', 29: 'CFG0', 30: 'CFG1', 31: '+3V3', 32: None, 33: None, 34: None, 35: None,
       36: 'V0P95', 37: 'HSO_N', 38: 'HSO_P', 39: 'GND', 40: 'HSI_P', 41: 'HSI_N', 42: '+3V3',
       43: 'V0P95', 44: None, 45: None, 46: 'BUCK_EN', 47: None, 48: 'PHY_INT_N', 49: 'GND'}
U1_AT = (19.5, 0.0)
part('U1', 'sfp:RTL8221B', 'RTL8221B-VB-CG', 'Package_DFN_QFN:QFN-48-1EP_6x6mm_P0.4mm_EP4.3x4.3mm_ThermalVias',
     PHY, U1_AT, side='B', rot=90, mpn='RTL8221B-VB-CG')


def u1_pin(n):
    """Where pin n of U1 lands (module frame). Bottom side, turned 90: seen
    from the top, pins 1..12 run left to right along the top edge, 13..24 down
    the right edge, 25..36 right to left along the bottom, 37..48 up the left."""
    x0, y0 = U1_AT
    k = (n - 1) % 12
    side = (n - 1) // 12
    return [(x0 - 2.2 + 0.4 * k, y0 + 2.95), (x0 + 2.95, y0 + 2.2 - 0.4 * k),
            (x0 + 2.2 - 0.4 * k, y0 - 2.95), (x0 - 2.95, y0 - 2.2 + 0.4 * k)][side]


# decoupling on the PHY's own side, one 100 nF at each power pin with a short
# stub from the pin, its ground end dogboned to In1. At 0.4 mm pitch no via
# fits between the pins, so a cap on the other side could not be reached.
#   (ref, pin, net, (x, y), rot)
DECAP = [('C7', 4, 'V0P95', (18.2, 4.25), 270), ('C8', 5, '+3V3', (19.0, 4.25), 270),
         ('C9', 7, 'AVDD33', (19.9, 4.25), 270), ('C10', 11, 'AVDD09', (21.6, 4.25), 270),
         ('C11', 15, 'AVDD33', (23.65, 1.5), 0), ('C12', 16, 'AVDD09', (25.1, 1.0), 0),
         ('C13', 19, 'AVDD33', (23.65, -0.2), 0), ('C14', 22, 'AVDD09', (23.65, -1.4), 0),
         ('C15', 28, 'V0P95', (20.5, -4.25), 90), ('C16', 31, '+3V3', (19.3, -4.25), 90),
         ('C17', 36, 'V0P95', (17.3, -4.25), 90),
         ('C18', 42, '+3V3', (15.35, -0.35), 180), ('C19', 43, 'V0P95', (14.3, 0.6), 180)]
for ref, pin, net, xy, r in DECAP:
    part(ref, 'Device:C_Small', '100nF', C0201, {1: net, 2: 'GND'}, xy, side='B', rot=r)
part('R9', 'Device:R_Small', '2.49k 1%', R0201, {1: 'RSET', 2: 'GND'}, (22.85, 3.95), side='B')
part('R10', 'Device:R_Small', '1.5k', R0201, {1: '+3V3', 2: 'MDIO'}, (16.3, 4.25), side='B', rot=90)
part('R11', 'Device:R_Small', '4.7k', R0201, {1: '+3V3', 2: 'PHY_INT_N'}, (15.2, 2.9), side='B')
# the straps are DC: out below the caps, the router takes CFG0/CFG1 between C16 and C15
part('R12', 'Device:R_Small', '4.7k', R0201, {1: 'CFG0', 2: 'GND'}, (21.9, -5.2), side='B')
part('R13', 'Device:R_Small', '4.7k', R0201, {1: '+3V3', 2: 'CFG1'}, (18.2, -5.3), side='B')

# analog islands: ripple limit 15 mVpp on AVDD09 / AVDD33 (datasheet 9.6);
# along the bottom edge on top, clear of the MDI lanes
part('FB3', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'V0P95', 2: 'AVDD09'}, (19.0, -4.6), mpn='BLM18KG601SH1')
part('C21', 'Device:C_Small', '10uF', C0603, {1: 'AVDD09', 2: 'GND'}, (22.0, -4.6))
part('FB4', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: '+3V3', 2: 'AVDD33'}, (25.0, -4.6), mpn='BLM18KG601SH1')
part('C22', 'Device:C_Small', '10uF', C0603, {1: 'AVDD33', 2: 'GND'}, (16.0, -4.6))

# 25 MHz oscillator on top, above the MDI lanes, fed by one line from pin 10
# (CKXTAL1) through a via; OE (pin 1) tied high, as its datasheet allows
X1_AT = (24.2, 4.7)
part('X1', 'Oscillator:ASE-xxxMHz', 'MST8011AI-72-33E25', 'sfp:Oscillator_SMD_MST_2016-4Pin',
     {1: '+3V3', 2: 'GND', 3: 'XI', 4: '+3V3'}, X1_AT, mpn='MST8011AI-72-33E25.000000')
part('C30', 'Device:C_Small', '100nF', C0201, {1: '+3V3', 2: 'GND'}, (26.1, 4.7), rot=90)

# ---------------------------------------------------------------- 0.95 V buck (bottom, left)
# the T1 module's buck, mirrored onto the bottom so the top stays clear for
# the SerDes pairs; EN from the PHY's POW_EXT_SWR (datasheet 8.8), held low
# until the PHY drives it
part('U3', 'Regulator_Switching:TPS62823DLC', 'TPS62822DLC', 'sfp:Texas_VSON-HR-8_1.5x2mm_P0.5mm',
     {1: 'BUCK_EN', 2: 'BUCK_FB', 3: 'GND', 4: None, 5: 'GND', 6: 'BUCK_SW', 7: '+3V3', 8: None},
     (11.8, 1.3), side='B', mpn='TPS62822DLCR')
part('R18', 'Device:R_Small', '100k', R0201, {1: 'BUCK_EN', 2: 'GND'}, (13.9, 3.6), side='B', rot=90)
part('L1', 'Device:L_Small', '470nH DFE201610E-R47M', 'Inductor_SMD:L_Murata_DFE201610P',
     {1: 'BUCK_SW', 2: 'V0P95'}, (11.8, -1.6), side='B', mpn='DFE201610E-R47M')
part('C32', 'Device:C_Small', '4.7uF', C0402, {1: '+3V3', 2: 'GND'}, (13.9, 1.9), side='B', rot=90)
part('C33', 'Device:C_Small', '10uF', C0603, {1: 'V0P95', 2: 'GND'}, (9.2, -1.8), side='B', rot=90)
part('C34', 'Device:C_Small', '10uF', C0603, {1: 'V0P95', 2: 'GND'}, (11.8, -3.8), side='B')
part('R3', 'Device:R_Small', '57.6k 1%', R0201, {1: 'V0P95', 2: 'BUCK_FB'}, (9.2, 0.2), side='B')
part('C35', 'Device:C_Small', '120pF', C0201, {1: 'V0P95', 2: 'BUCK_FB'}, (9.2, 0.9), side='B')
part('R4', 'Device:R_Small', '100k 1%', R0201, {1: 'BUCK_FB', 2: 'GND'}, (9.2, 1.6), side='B')

# ---------------------------------------------------------------- magnetics
# chip side pins 1..12 along the bottom row, cable side 13..24 back along the
# top. The PHY's ports land reversed (see the docstring): port 3 on channel 1.
MAG = {1: 'TCT0', 2: 'MDI3_N', 3: 'MDI3_P', 4: 'TCT1', 5: 'MDI2_N', 6: 'MDI2_P',
       7: 'TCT2', 8: 'MDI1_N', 9: 'MDI1_P', 10: 'TCT3', 11: 'MDI0_N', 12: 'MDI0_P',
       23: 'LINE0_P', 22: 'LINE0_N', 24: 'CMT0', 20: 'LINE1_P', 19: 'LINE1_N', 21: 'CMT1',
       17: 'LINE2_P', 16: 'LINE2_N', 18: 'CMT2', 14: 'LINE3_P', 13: 'LINE3_N', 15: 'CMT3'}
part('T1', 'sfp:LP72450ANL', 'LP72450ANL', 'sfp:LINKPP_LP72450ANL', MAG, (36.0, 0.0), mpn='LP72450ANL')
for i in range(4):          # chip-side centre taps: 100 nF to ground each (voltage-mode driver)
    part(f'C{36 + i}', 'Device:C_Small', '100nF', C0402, {1: f'TCT{i}', 2: 'GND'},
         (30.5 + 3.0 * i, -5.15), side='B')
for i in range(4):          # Bob Smith: 75 R from each cable-side centre tap to one node
    part(f'R{14 + i}', 'Device:R_Small', '75', R0402, {1: f'CMT{i}', 2: 'BOB'},
         (30.5 + 3.0 * i, 5.15), side='B')
part('C40', 'Device:C_Small', '1nF 2kV', 'Capacitor_SMD:C_1206_3216Metric', {1: 'BOB', 2: 'GND'},
     (42.6, 3.4), side='B', rot=90, mpn='1206B102K202NT')

# ---------------------------------------------------------------- RJ45
# T568: channel A on 1/2, B on 3/6, C on 4/5, D on 7/8; shield (9) to ground
RJ = {1: 'LINE0_P', 2: 'LINE0_N', 3: 'LINE1_P', 6: 'LINE1_N', 4: 'LINE2_P', 5: 'LINE2_N',
      7: 'LINE3_P', 8: 'LINE3_N', 9: 'GND'}
LENGTH = 63.2
part('J2', 'sfp:RJ45_8P8C', 'KH-RJ45-58-8P8C', 'sfp:RJ45_Kinghelm_KH-RJ45-58', RJ, (LENGTH, 0.0),
     mpn='KH-RJ45-58-8P8C')

# ---------------------------------------------------------------- MCU (bottom, under the magnetics)
MCU = {1: 'SDA', 2: None, 3: None, 4: '+3V3', 5: 'GND', 6: 'NRST', 7: 'MDC', 8: 'MDIO',
       9: 'PHY_RST_N', 10: 'PHY_INT_N', 11: 'TX_DISABLE', 12: 'RX_LOS', 13: 'TX_FAULT',
       14: None, 15: None, 16: None, 17: None, 18: 'SWDIO', 19: 'SWCLK', 20: 'SCL'}
part('U2', 'MCU_ST_STM32G0:STM32G031F_4-6-8_Px', 'STM32G031F6P6', 'Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm',
     MCU, (36.0, 0.0), side='B', rot=90, mpn='STM32G031F6P6')
part('C41', 'Device:C_Small', '100nF', C0402, {1: '+3V3', 2: 'GND'}, (31.4, 3.5), side='B', rot=90)
part('C42', 'Device:C_Small', '1uF', C0402, {1: '+3V3', 2: 'GND'}, (31.4, -3.5), side='B', rot=90)
part('C43', 'Device:C_Small', '100nF', C0402, {1: 'NRST', 2: 'GND'}, (40.6, 3.5), side='B', rot=90)
part('R5', 'Device:R_Small', '10k', R0402, {1: '+3V3', 2: 'TX_DISABLE'}, (40.6, -3.5), side='B', rot=90)
# SWD pads under the jack (bottom), clear of every lane; pogo-probe them
for i, (net, xy) in enumerate([('+3V3', (58.0, -3.0)), ('SWDIO', (58.0, -1.0)), ('SWCLK', (58.0, 1.0)),
                               ('NRST', (58.0, 3.0)), ('GND', (60.5, 0.0))]):
    part(f'TP{i + 1}', 'Connector:TestPoint', net, TP, {1: net}, xy, side='B')

COURTYARD_OK = {'U1': [r for r, *_ in DECAP] + ['R9', 'R10', 'C5', 'C6']}
NOSE = (44.6, 17.0)              # outside the cage the board widens for the jack's shield tabs
OVERHANG = ('J2',)               # the jack body hangs over the 45 degree step of the nose
HEIGHTS = {'X1': 0.8, 'T1': 4.3, 'U4': 1.45, 'L1': 1.0, 'U1': 1.0, 'U2': 1.2, 'C40': 1.35, 'U3': 1.0}


# ---------------------------------------------------------------- symbols
def _rtl_symbol():
    L = [('1', 'PHYRSTB', 'input'), ('2', 'MDC', 'input'), ('3', 'MDIO', 'bidirectional'),
         ('48', 'INTB/PMEB', 'open_collector'), ('46', 'POW_EXT_SWR', 'output'), ('', '', ''),
         ('10', 'CKXTAL1', 'input'), ('9', 'CKXTAL2', 'output'), ('6', 'CLKOUT', 'output'),
         ('12', 'RSET', 'passive'), ('', '', ''),
         ('40', 'HSIP', 'input'), ('41', 'HSIN', 'input'), ('38', 'HSOP', 'output'), ('37', 'HSON', 'output'),
         ('', '', ''), ('29', 'CFG_OPT0', 'bidirectional'), ('30', 'CFG_OPT1', 'bidirectional'),
         ('33', 'LED0/PHYAD0', 'bidirectional'), ('34', 'LED1/PHYAD1', 'bidirectional'),
         ('35', 'LED2/PHYAD2', 'bidirectional'),
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
    L = [(str(i), str(i), 'passive') for i in range(1, 9)] + [('9', 'SHIELD', 'passive')]
    return ('RJ45_8P8C', 'J', L, [], 10.16)


SYMBOLS = [_rtl_symbol(), _mag_symbol(), _rj_symbol()]
SOLID_PADS = {('U1', '49')}
HMTD_AT = None


def FOOTPRINTS(io, smd, crt, tht, slot, npth):
    import pcbnew
    # LINK-PP LP72450ANL, recommended pad layout (sheet 2): 2 x 12 pads
    # 0.60 x 1.35 at 1.0 pitch, 11.0 first to last; rows 8.0 apart inside and
    # 10.70 outside -> pad centres at +/-4.675. Pin 1 bottom-left, chip side
    # 1..12 left to right, 13..24 back along the top.
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID('sfp', 'LINKPP_LP72450ANL'))
    for i in range(12):
        smd(fp, str(i + 1), -5.5 + i, 4.675, 0.60, 1.35)          # bottom row (KiCad +y is down)
        smd(fp, str(24 - i), -5.5 + i, -4.675, 0.60, 1.35)        # top row, 13..24 right to left
    crt(fp, 7.85, 5.6)
    io.FootprintSave(sfpgen.FPLIB, fp)

    # MST8011 2.0 x 1.6 oscillator, recommended land (datasheet p.5): 4 pads
    # 0.9 x 0.8, centres 1.5 apart along the long side, 1.2 across. Laid long
    # side along x. From its bottom view, seen from the top: 1 OE lower-right
    # ... anticlockwise: 2 GND upper-right, 3 CLK upper-left, 4 VDD lower-left;
    # in the long-side-along-x land that puts 1 and 4 (both +3V3 here) on the
    # right, 3 (CLK) lower-left and 2 (GND) upper-left.
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID('sfp', 'Oscillator_SMD_MST_2016-4Pin'))
    for num, x, y in (('1', 0.75, -0.6), ('2', -0.75, -0.6), ('3', -0.75, 0.6), ('4', 0.75, 0.6)):
        smd(fp, num, x, y, 0.9, 0.8)                    # KiCad +y is down
    crt(fp, 1.45, 1.2)
    io.FootprintSave(sfpgen.FPLIB, fp)

    # Kinghelm KH-RJ45-58-8P8C, recommended PCB layout (top view), turned so
    # the opening faces +x. Origin = the front face on the centreline.
    #   pins 0.9 drill, 1.27 pitch across, rows 2.54 apart: 1,3,5,7 at 14.15
    #   behind the face, 2,4,6,8 at 16.69; pegs 3.2 NPTH 11.43 apart at 7.80;
    #   shield tabs 0.70 x 1.70 slots 15.13 apart at 4.95. Pin 1 to -y.
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID('sfp', 'RJ45_Kinghelm_KH-RJ45-58'))
    for k in range(1, 9):
        x = -14.15 if k % 2 else -16.69
        tht(fp, str(k), x, 4.445 - (k - 1) * 1.27, 1.5, 0.9)
    for s in (-1, 1):
        npth(fp, -7.80, s * 5.715, 3.2)
        slot(fp, '9', -4.95, s * 7.565, 2.3, 1.3, 1.70, 0.70)
    for layer, g in ((pcbnew.F_CrtYd, 0.25), (pcbnew.F_Fab, 0.0)):
        x0, x1, y0 = -18.2 - g, g, 7.85 + g
        for a, b in (((x0, -y0), (x1, -y0)), ((x1, -y0), (x1, y0)), ((x1, y0), (x0, y0)), ((x0, y0), (x0, -y0))):
            sh = pcbnew.FP_SHAPE(fp)
            sh.SetShape(pcbnew.SHAPE_T_SEGMENT)
            sh.SetStart0(pcbnew.VECTOR2I(sfpgen.MB.MM(a[0]), sfpgen.MB.MM(a[1])))
            sh.SetEnd0(pcbnew.VECTOR2I(sfpgen.MB.MM(b[0]), sfpgen.MB.MM(b[1])))
            sh.SetLayer(layer); sh.SetWidth(sfpgen.MB.MM(0.05 if layer == pcbnew.F_CrtYd else 0.1))
            fp.Add(sh)
    io.FootprintSave(sfpgen.FPLIB, fp)


# ---------------------------------------------------------------- schematic / rules
SCH_AT = {'J1': (40, 80), 'U1': (170, 115), 'U2': (170, 215), 'U3': (60, 190), 'T1': (280, 115),
          'J2': (360, 115), 'X1': (110, 60), 'U4': (60, 140)}
POWER_NETS = ('+3V3', 'V0P95', 'AVDD09', 'AVDD33', 'VCCT', 'VCCR', 'VIN_RAW')
HS = ['TD_P', 'TD_N', 'RD_P', 'RD_N', 'HSI_P', 'HSI_N', 'HSO_P', 'HSO_N']
MDI = [f'MDI{i}_{s}' for i in range(4) for s in 'PN'] + [f'LINE{i}_{s}' for i in range(4) for s in 'PN']
PWR = ['+3V3', 'V0P95', 'AVDD09', 'AVDD33', 'BUCK_SW', 'VCCT', 'VCCR', 'VIN_RAW']
# JLC04101H-3313: 50 ohm single-ended = 0.157 mm on the outer layers
NETCLASSES = [
    # 0.15: with the 0.1 via ring that is the board's 0.25 hole clearance (0.127 was not)
    dict(name='Default', clearance=0.15, track_width=0.127, via_diameter=0.45, via_drill=0.25),
    dict(name='SGMII', clearance=0.15, track_width=0.157, via_diameter=0.45, via_drill=0.25,
         dp_width=0.114, dp_gap=0.152, nets=HS),
    dict(name='MDI', clearance=0.15, track_width=0.157, via_diameter=0.45, via_drill=0.25,
         dp_width=0.114, dp_gap=0.152, nets=MDI),
    dict(name='Power', clearance=0.15, track_width=0.2, via_diameter=0.5, via_drill=0.3, nets=PWR),
]
CLASS_LAYERS = {'SGMII': ['F.Cu', 'B.Cu'], 'MDI': ['F.Cu', 'B.Cu']}
PAIRS = [('TD_P', 'TD_N'), ('HSI_P', 'HSI_N'), ('RD_P', 'RD_N'), ('HSO_P', 'HSO_N')] + \
        [(f'MDI{i}_P', f'MDI{i}_N') for i in range(4)] + [(f'LINE{i}_P', f'LINE{i}_N') for i in range(4)]


# ---------------------------------------------------------------- pre-routes
# At 0.4 mm pitch the router did not get the power pins out (a first route
# left 25 links open), so every pin-to-part stub is laid here: straight out of
# the pin past its pad, then to the part's pad. (net, layer, points[, width])
def _side(pin):
    return [(0, 1), (1, 0), (0, -1), (-1, 0)][(pin - 1) // 12]


def _pad(xy, rot, off, toward):
    x, y = xy
    cands = [(x - off, y), (x + off, y)] if rot % 180 == 0 else [(x, y - off), (x, y + off)]
    return min(cands, key=lambda p: (p[0] - toward[0]) ** 2 + (p[1] - toward[1]) ** 2)


def _stub(pin, net, xy, rot, off=0.32, width=None):
    px, py = u1_pin(pin)
    dx, dy = _side(pin)
    out = (round(px + 0.6 * dx, 3), round(py + 0.6 * dy, 3))
    pts = [(round(px, 3), round(py, 3)), out, _pad(xy, rot, off, out)]
    return (net, 'B', pts) if width is None else (net, 'B', pts, width)


PREROUTES = [_stub(pin, net, xy, r) for ref, pin, net, xy, r in DECAP]
PREROUTES += [_stub(8, 'AVDD33', (19.9, 4.25), 270),            # pin 8 shares C9 with pin 7
              _stub(38, 'HSO_P', (15.0, -1.8), 0, 0.48, 0.157),
              _stub(37, 'HSO_N', (15.0, -2.75), 0, 0.48, 0.157)]
# RSET: out of pin 12, right under C10's pad, into R9; R9's ground to a via
PREROUTES += [('RSET', 'B', [u1_pin(12), (21.7, 3.45), (22.15, 3.45), (22.53, 3.95)]),
              ('GND', 'B', [(23.17, 3.95), (23.6, 3.3)])]
# XI: straight up from pin 10 between C9 and C10, a via, then on top to X1 pin 3
XI_VIA = (20.9, 5.25)
PREROUTES += [('XI', 'B', [u1_pin(10), XI_VIA]),
              ('XI', 'F', [XI_VIA, (22.6, 4.1), (X1_AT[0] - 0.75, X1_AT[1] - 0.6)])]
PREVIAS = [('XI', XI_VIA), ('GND', (23.6, 3.3))]
DOGBONE_PREFIXES = ('C', 'R')   # resistors with a ground end too (CFG0, BUCK_EN, the divider)

# LCSC numbers, each checked against JLC's parts search on 2026-09-30
LCSC_BY_MPN = {'RTL8221B-VB-CG': 'C5155988', 'STM32G031F6P6': 'C529333', 'TPS62822DLCR': 'C473385',
               'DFE201610E-R47M': 'C269773', 'BLM18KG601SH1': 'C710379', 'LP72450ANL': 'C53281905',
               'KH-RJ45-58-8P8C': 'C2683360', 'SL201625M20P': 'C5155510', 'TPS22918DBVR': 'C131941',
               '1206B102K202NT': 'C9196', 'MST8011AI-72-33E25.000000': 'C51026225'}
LCSC_BY_VALUE = {('100nF', C0201): 'C76928', ('100nF', C0402): 'C1525', ('10uF', C0603): 'C19702',
                 ('4.7uF', C0402): 'C23733', ('1uF', C0402): 'C52923', ('120pF', C0201): 'C161406',
                 ('10k', R0402): 'C25744', ('100k 1%', R0201): 'C106224', ('100k', R0201): 'C106224',
                 ('2.49k 1%', R0201): 'C473476', ('1.5k', R0201): 'C270361', ('4.7k', R0201): 'C142008',
                 ('57.6k 1%', R0201): 'C423476', ('75', R0402): 'C25133', ('27pF', C0201): 'C85899',
                 ('2.2nF', C0402): 'C106861'}


def lcsc_for(p):
    if p['dnp'] or p['ref'].startswith('TP') or p['ref'] == 'J1':
        return ''
    return LCSC_BY_MPN.get(p['mpn']) or LCSC_BY_VALUE.get((p['value'], p['fp']), '')


if __name__ == '__main__':
    sys.exit(sfpgen.run(sys.modules[__name__]))

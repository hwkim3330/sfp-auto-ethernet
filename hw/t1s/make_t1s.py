#!/usr/bin/env python3
"""SFP 10BASE-T1S module: symbols, schematic, PCB.

    python3 make_t1s.py [--route | --reuse-ses]

No 10BASE-T1S PHY speaks SGMII, so an FPGA does (docs/PARTS.md): the host's
SGMII on a hard transceiver lane, our own PCS / rate adaptation / half-duplex
MAC in fabric (gw/), and MII to a LAN8670.

Sources:
  Gowin GW5AT-15 (LCSC C54067362, MG132: 8 x 8 mm, 0.5 mm pitch, 14 x 14
      grid with only the outer three rings populated; land 0.25 mm, UG983
      figure 4-8)
      ball map: UG1224E.xlsx "Pin List MG132" -> gw5at15_mg132.csv (as is)
      rails: DS981 table 3-8; UG984 (schematic manual) 2.4 / table 2-3: rails
      at one voltage may share a regulator through a ferrite bead each
      transceiver: DS981 3-46..3-49; refclk AC coupled, 100 nF at the FPGA
      (UG984 5.2), the kit (DK_EDP_GW5ART-LV15MG132P) drives it from a 3225
      LVDS oscillator with no other termination
      configuration: UG720 - MSPI (MODE[1:0] = 11, internal pull-ups plus
      4.7k: both balls on one 4.7k), flash >= 64 Mbit (the retry image lives
      at 0x800000)
  Microchip LAN8670 (C20901523, VQFN-32 5 x 5): DS60001573K pins table 3-1
      (pin 1 INH and 9 GPIO0 open, 32 WAKE_IN to VSS when unused, 25 VDDAU),
      exposed pad 3.4 nominal, land 3.5 (package C04-500), straps 3.5 (no
      internal resistors: 10k each), 25 MHz crystal 7.8,
      MDI and BIN: AN1718 figure 1-3 (CMC, 2 x 100 nF, end-node termination)
  YXC OB2EL89CLIB112YLC-125M (C7425465): 125 MHz LVDS, 3225-6P; pins 1 OE,
      2 NC, 3 GND, 4 OUT+, 5 OUT-, 6 VDD; land 0.9 x 1.1 at 1.2 pitch, rows
      +-0.8 (YSO230LR datasheet p.2)
  TPS62822 (core 0.946 V: 57.6k / 100k), TLV75518 / TLV75512 (SOT-23-5,
      1.8 V for VDDHAQ0, 1.2 V for VDD12M + VCCLDO), TPS22918 soft start

Six layers, because of the BGA: 0.5 mm pitch leaves no track between balls,
so every used ball inside the outer ring has a via in its pad (JLC fills and
caps those for free on 6+ layers), and five supply rails sit interleaved round
the ring. Stack:  F signals | In1 GND | In2 signals | In3 +3V3 | In4 GND, with
the 0.95 V core as an island under the FPGA and the buck | B signals. The SGMII
pairs run on F over In1 and on B over In4's GND.

SFP edge: SFF-8419 figure 7-2 (pin 11 at the top seen from above, card edge
on the left), so TD (pins 18/19) arrives at the bottom of the tab and RD
(12/13) leaves at the top, while all four of the FPGA's lane balls sit at its
top-left corner. RX therefore runs on top from the bottom fingers round the
west side of the ball field into A1/A2 from above; TX comes out of B3/C3
underneath to vias next to its caps. Both lanes keep their polarity, P to P:
RX by the way it turns, TX by M passing under P's via and taking the outer
one (gw/t1s_top.v inverts nothing).
"""
import csv
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import sfpgen                            # noqa: E402
from sfpgen import (C0201, C0402, C0603, R0201, R0402, R0603, FB0603, LED0402,  # noqa: E402,F401
                    TP)

NAME = 't1s'
TITLE = 'T1S SFP'
SCH_TITLE = 'SFP 10BASE-T1S - GW5AT-15 + LAN8670'
SHEET = '5e1f3a92-7b6c-4d8e-9f01-2a3b4c5d6e71'
LAYERS = 6
U4_AT = (8.7, -3.0)             # underneath, between SDA's and TX_DISABLE's In2 runs
C36_NETS, C36_AT = {1: 'SS_CT', 2: 'GND'}, (10.0, -3.9)   # on top, below the JTAG pads
C37_AT = (8.0, -4.1)            # on top, below the RX pair (0402: an 0603 would reach past the tab's width)
TITLE_AT = (16.0, -3.5)          # under the ball field: the only 5 mm of the bottom with no pad or via

P = []


def part(ref, lib_id, value, fp, nets, at, side='F', rot=0, dnp=False, mpn=''):
    P.append(dict(ref=ref, lib_id=lib_id, value=value, fp=fp, nets=nets, at=at,
                  side=side, rot=rot, dnp=dnp, mpn=mpn))


C0805 = 'Capacitor_SMD:C_0805_2012Metric'
R0805 = 'Resistor_SMD:R_0805_2012Metric'
R1206 = 'Resistor_SMD:R_1206_3216Metric'

# ---------------------------------------------------------------- SFP edge
EDGE = {1: 'GND', 2: 'TX_FAULT', 3: 'TX_DISABLE', 4: 'SDA', 5: 'SCL', 6: 'GND',
        7: None, 8: 'RX_LOS', 9: 'GND', 10: 'GND', 11: 'GND', 12: 'RD_N', 13: 'RD_P',
        14: 'GND', 15: 'VCCR', 16: 'VCCT', 17: 'GND', 18: 'TD_P', 19: 'TD_N', 20: 'GND'}
part('J1', 'sfp:SFP_EDGE', 'SFP edge (INF-8074i)', 'sfp:SFP_Module_Edge', EDGE, (0, 0))

# host rails, beads, soft-start load switch (as the T1 board). The beads sit
# on top between the fingers' VCCR (+0.2) and VCCT (-0.6) and the RX pair's
# run; VIN_RAW drops through a via to the load switch underneath, which sits
# between the slow lines' In2 runs (below)
part('FB1', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'VCCT', 2: 'VIN_RAW'}, (7.4, -0.75), mpn='BLM18KG601SH1')
part('FB2', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'VCCR', 2: 'VIN_RAW'}, (7.4, 0.9), mpn='BLM18KG601SH1')
part('C1', 'Device:C_Small', '1uF', C0402, {1: 'VIN_RAW', 2: 'GND'}, (7.3, 1.1), side='B')
part('C2', 'Device:C_Small', '100nF', C0402, {1: 'VIN_RAW', 2: 'GND'}, (9.2, 1.1), side='B')
part('U4', 'sfp:TPS22918', 'TPS22918DBVR', 'Package_TO_SOT_SMD:SOT-23-6',
     {1: 'VIN_RAW', 2: 'GND', 3: 'VIN_RAW', 4: 'SS_CT', 5: '+3V3', 6: '+3V3'}, U4_AT, side='B', rot=90,
     mpn='TPS22918DBVR')
part('C36', 'Device:C_Small', '2.2nF', C0402, C36_NETS, C36_AT)
part('C37', 'Device:C_Small', '10uF', C0402, {1: '+3V3', 2: 'GND'}, C37_AT, rot=180)

# SGMII AC coupling in the module (MSA): TD -> FPGA RX, FPGA TX -> RD, each
# cap straight behind its finger, P to P
part('C3', 'Device:C_Small', '100nF', C0201, {1: 'TD_P', 2: 'SRX_P'}, (5.2, -2.2))
part('C4', 'Device:C_Small', '100nF', C0201, {1: 'TD_N', 2: 'SRX_M'}, (5.2, -3.0))
part('C5', 'Device:C_Small', '100nF', C0201, {1: 'RD_P', 2: 'STX_P'}, (5.2, 1.8))
part('C6', 'Device:C_Small', '100nF', C0201, {1: 'RD_N', 2: 'STX_M'}, (5.2, 2.6))

# ---------------------------------------------------------------- FPGA
U1_AT = (15.25, 0.0)
ROWS = 'ABCDEFGHJKLMNP'


def ball_xy(ball):
    """Board position of a ball: A1 top-left seen from the top (row A along +y)."""
    r, c = ROWS.index(ball[0]), int(ball[1:])
    return (round(U1_AT[0] + (c - 7.5) * 0.5, 3), round(U1_AT[1] + (6.5 - r) * 0.5, 3))


def ring(ball):
    r, c = ROWS.index(ball[0]), int(ball[1:]) - 1
    return min(r, 13 - r, c, 13 - c) + 1


BALLS = list(csv.DictReader(open(os.path.join(HERE, 'gw5at15_mg132.csv'))))
FPGA = {}
for b in BALLS:
    n = b['pin_name']
    if n.startswith(('VSS', 'VEFUSE')):
        FPGA[b['ball']] = 'GND'                       # VEFUSE: GND when eFuse is not programmed (DS981)
    elif n.startswith(('VCCX', 'VCCIO', 'VDDXM')):
        FPGA[b['ball']] = '+3V3'
    elif n in ('VCC', 'VDDAM'):
        FPGA[b['ball']] = 'VCC_CORE'
    elif n in ('VDD12M', 'VCCLDO'):
        FPGA[b['ball']] = 'V1P2'
    elif n == 'VDDAQ0':
        FPGA[b['ball']] = 'VDDAQ'
    elif n == 'VDDTQ0':
        FPGA[b['ball']] = 'VDDTQ'
    elif n == 'VDDHAQ0':
        FPGA[b['ball']] = 'VDDHAQ'
FPGA.update({
    'A1': 'SRX_M', 'A2': 'SRX_P',                     # transceiver lane 0
    'B3': 'STX_P', 'C3': 'STX_M',
    'A7': 'REFCLK_M', 'A8': 'REFCLK_P',               # Q0 REFCLK0, 125 MHz
    # MII to the LAN8670: the right column straight across to its left side,
    # the bottom row round under it to its bottom and right sides
    'C14': 'COL', 'D14': 'TXD3', 'E14': 'TXD2', 'F14': 'TXD1', 'G14': 'TXD0', 'H14': 'TXEN',
    'J14': 'TXCLK',
    'P14': 'CRS', 'P13': 'RXD0', 'P12': 'RXCLK', 'P11': 'RXD1', 'P10': 'RXDV', 'P9': 'RXD2', 'P8': 'RXD3',
    # MSPI configuration flash (bank 2)
    'L14': 'F_CLK', 'L13': 'F_CS_N', 'M13': 'F_MOSI', 'K14': 'F_MISO',
    # MODE[1:0] = 11 (MSPI): both balls on one 4.7k pull-up (UG720 asks 4.7k;
    # the internal pull-ups alone were the old design's bet on MODE0)
    'N1': 'MODE', 'N2': 'MODE', 'M3': 'FPGA_RECONFIG_N',
    'L3': 'FPGA_DONE', 'M12': 'FPGA_READY',
    # CLKHOLD_N (K3) holds the flash's clock while it is low, and the ball is
    # pulled down during configuration (UG720, the pinout's term_during_config):
    # left open, the FPGA would never load. Tied high, straight onto +3V3
    'K3': '+3V3',
    'G2': 'JTAG_TCK', 'G3': 'JTAG_TMS', 'J3': 'JTAG_TDI', 'J2': 'JTAG_TDO',
    'P1': 'FPGA_LINK',                                # SGMII link up -> MCU (RX_LOS)
})
part('U1', 'sfp:GW5AT-15_MG132', 'GW5AT-LV15MG132C1/I0', 'sfp:Gowin_MBGA-132_8x8mm_P0.5mm', FPGA, U1_AT,
     mpn='GW5AT-LV15MG132C1/I0')


def needs_via(ball):
    """Every used ball gets a via in its pad, except the outer-ring signals,
    which leave on top."""
    net = FPGA.get(ball)
    if not net:
        return False
    return ring(ball) > 1 or net in ('GND', '+3V3', 'VCC_CORE', 'V1P2', 'VDDAQ', 'VDDTQ', 'VDDHAQ', 'F_MISO', 'F_CLK')


# 125 MHz LVDS reference, AC coupled at the FPGA
part('X1', 'sfp:OSC_LVDS', 'OB2EL89CLIB112YLC-125M', 'sfp:Oscillator_YXC_3225-6Pin_LVDS',
     {1: '+3V3', 2: None, 3: 'GND', 4: 'OSC_P', 5: 'OSC_N', 6: '+3V3'}, (23.0, 3.55), rot=90,
     mpn='OB2EL89CLIB112YLC-125M')
# the upper lane carries OUT+ to REFCLKM: the lanes would otherwise cross, and an
# inverted reference clock is still the same clock
part('C7', 'Device:C_Small', '100nF', C0201, {1: 'REFCLK_M', 2: 'OSC_P'}, (20.3, 4.55))
part('C8', 'Device:C_Small', '100nF', C0201, {1: 'REFCLK_P', 2: 'OSC_N'}, (20.3, 3.7))
part('C9', 'Device:C_Small', '100nF', C0201, {1: '+3V3', 2: 'GND'}, (25.2, 3.6), rot=90)

# configuration flash (MSPI), underneath beside the FPGA's bank-2 corner
# 128 Mbit, not 64: Gowin's MSPI retry (golden) image defaults to 0x800000,
# which is one past the end of a 64 Mbit part; same WSON-8 6x5 footprint
part('U2', 'sfp:GD25Q128_WSON8', 'GD25Q128EWIGR', 'Package_SON:WSON-8-1EP_6x5mm_P1.27mm_EP3.4x4.3mm',
     {1: 'F_CS_N', 2: 'F_MISO', 3: '+3V3', 4: 'GND', 5: 'F_MOSI', 6: 'F_CLK', 7: '+3V3', 8: '+3V3', 9: 'GND'},
     (23.6, -2.6), side='B', rot=180, mpn='GD25Q128EWIGR')      # WP#/HOLD# tied high: x1 SPI only
# straps and config pull-ups (UG984 3.5: 4.7k)
# (R5 READY and R6 flash CS sit in the decap grid under the FPGA, below)
# MODE beside N1, TCK's pull-down beside its escape; DONE's and
# RECONFIG_N's pull-ups sit at the MCU pins, the other end of those lines
part('R1', 'Device:R_Small', '4.7k', R0201, {1: '+3V3', 2: 'MODE'}, (11.1, -3.55), side='B', rot=270)
part('R7', 'Device:R_Small', '4.7k', R0201, {1: 'JTAG_TCK', 2: 'GND'}, (10.7, 0.25), side='B', rot=180)

# ---------------------------------------------------------------- FPGA supplies
# core 0.946 V: buck, then beads to the transceiver's analog and TX rails
BUCK = (22.4, 1.7)
part('U3', 'Regulator_Switching:TPS62823DLC', 'TPS62822DLC', 'sfp:Texas_VSON-HR-8_1.5x2mm_P0.5mm',
     {1: '+3V3', 2: 'BUCK_FB', 3: 'GND', 4: None, 5: 'GND', 6: 'BUCK_SW', 7: '+3V3', 8: None},
     BUCK, side='B', mpn='TPS62822DLCR')
# 1.0 uH, not the datasheet's usual 0.47 (both are in TPS6282x Table 3): the
# ripple halves, so the buck stays in PWM down to ~0.15 A instead of ~0.33 A
# and spends less time skipping pulses next to the SerDes rails it feeds
part('L1', 'Device:L_Small', '1uH DFE201610E-1R0M', 'Inductor_SMD:L_Murata_DFE201610P',
     {1: 'BUCK_SW', 2: 'VCC_CORE'}, (22.4, 4.2), side='B', mpn='DFE201610E-1R0M')
part('C11', 'Device:C_Small', '4.7uF', C0402, {1: '+3V3', 2: 'GND'}, (20.4, 1.7), side='B', rot=90)
part('C12', 'Device:C_Small', '10uF', C0603, {1: 'VCC_CORE', 2: 'GND'}, (24.6, 4.3), side='B', rot=90)
part('C13', 'Device:C_Small', '10uF', C0603, {1: 'VCC_CORE', 2: 'GND'}, (20.2, 4.3), side='B', rot=90)
part('R8', 'Device:R_Small', '57.6k 1%', R0201, {1: 'VCC_CORE', 2: 'BUCK_FB'}, (25.4, 1.0), side='B')   # 0.8 mm off U3: its VIN via between
part('C14', 'Device:C_Small', '120pF', C0201, {1: 'VCC_CORE', 2: 'BUCK_FB'}, (25.4, 1.9), side='B')
part('R9', 'Device:R_Small', '100k 1%', R0201, {1: 'BUCK_FB', 2: 'GND'}, (27.0, 1.4), side='B', rot=90)
part('FB3', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'VCC_CORE', 2: 'VDDAQ'}, (16.6, 4.95), side='B', mpn='BLM18KG601SH1')
part('FB4', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'VCC_CORE', 2: 'VDDTQ'}, (12.0, 4.95), side='B', mpn='BLM18KG601SH1')
# 1.8 V (VDDHAQ0) and 1.2 V (VDD12M, VCCLDO) LDOs from +3V3
part('U6', 'Regulator_Linear:TLV75518PDBV', 'TLV75518PDBVR', 'Package_TO_SOT_SMD:SOT-23-5',
     {1: '+3V3', 2: 'GND', 3: '+3V3', 4: None, 5: 'VDDHAQ'}, (45.6, 3.4), side='B', mpn='TLV75518PDBVR')
part('U7', 'Regulator_Linear:TLV75512PDBV', 'TLV75512PDBVR', 'Package_TO_SOT_SMD:SOT-23-5',
     {1: '+3V3', 2: 'GND', 3: '+3V3', 4: None, 5: 'V1P2'}, (45.6, -3.4), side='B', mpn='TLV75512PDBVR')
# the LDOs' output caps at their outputs (TLV755: 1 uF); the rails reach the
# FPGA on In2, where the 100 nF grid caps under the balls decouple them
part('C15', 'Device:C_Small', '1uF', C0402, {1: 'VDDHAQ', 2: 'GND'}, (46.74, 1.2), side='B')
part('C16', 'Device:C_Small', '1uF', C0402, {1: 'V1P2', 2: 'GND'}, (48.2, -3.9), side='B', rot=90)
part('C17', 'Device:C_Small', '1uF', C0402, {1: '+3V3', 2: 'GND'}, (15.9, -4.75), side='B')
part('C18', 'Device:C_Small', '4.7uF', C0402, {1: 'VDDAQ', 2: 'GND'}, (13.8, 4.8))   # on top, over row A's VDDAQ balls

# decoupling under the FPGA: a 3 x 4 grid of 0201s in the empty centre of the
# ball ring (bottom), 0.23 mm clear of the ring's vias; the bulk caps along
# the ring's outer edges. UG984 / the kit's sheet 9, scaled to one lane.
_cx, _cy = U1_AT
_GRID = [(_cx + dx, _cy + dy) for dy in (1.35, 0.45, -0.45, -1.35) for dx in (-1.05, 1.05)]   # a channel down the middle
_dec = [('VCC_CORE', '+3V3'), ('VCC_CORE', '+3V3'), ('VCC_CORE', '+3V3'), ('VDDAQ', 'VDDHAQ'), ('V1P2', None)]
# VDDAQ's balls are all in row A, the outer ring, under C18 on top: its grid
# cap had no way out to them, so the core takes a third one
_dec = ['VCC_CORE', '+3V3', 'VCC_CORE', '+3V3', 'VCC_CORE', 'VDDHAQ', 'V1P2']
for i, net in enumerate(_dec):
    part(f'C{50 + i}', 'Device:C_Small', '100nF', C0201, {1: net, 2: 'GND'}, _GRID[i], side='B')
part('R5', 'Device:R_Small', '4.7k', R0201, {1: '+3V3', 2: 'FPGA_READY'}, _GRID[7], side='B')
part('R6', 'Device:R_Small', '4.7k', R0201, {1: '+3V3', 2: 'F_CS_N'}, (19.4, 0.35), side='B', rot=90)
part('C59', 'Device:C_Small', '100nF', C0201, {1: 'VDDTQ', 2: 'GND'}, (14.3, 4.95), side='B')

# JTAG pads (TCK TMS TDI TDO) on top, beside the FPGA: the four balls
# escape west on In2 to vias at x 11.4 (see below)
for i, (net, xy) in enumerate([('JTAG_TCK', (10.35, 0.0)), ('JTAG_TMS', (10.35, 1.2)),
                               ('JTAG_TDI', (10.35, -2.4)), ('JTAG_TDO', (10.35, -1.2))]):
    part(f'TP{10 + i}', 'Connector:TestPoint', net, 'sfp:TestPoint_Pad_D1.0mm_NoSilk', {1: net}, xy)

# ---------------------------------------------------------------- PHY
PHY_AT = (31.0, 0.0)
PHY = {1: None, 2: 'COL', 3: 'TXD3', 4: 'TXD2', 5: 'TXD1', 6: 'TXD0', 7: 'TXEN', 8: '+3V3',
       9: None, 10: 'PHY_RST_N', 11: 'GND', 12: 'TXCLK', 13: 'MDC', 14: 'MDIO', 15: 'CRS', 16: 'RXD0',
       17: 'RXCLK', 18: '+3V3', 19: 'RXD1', 20: 'RXDV', 21: 'RXER', 22: 'PHY_INT_N', 23: 'RXD2',
       24: 'RXD3', 25: '+3V3', 26: 'RBIAS', 27: 'XTI', 28: 'XTO', 29: '+3V3', 30: 'TRXN', 31: 'TRXP',
       32: 'GND', 33: 'GND'}
part('U5', 'sfp:LAN8670', 'LAN8670C2-E/LMX', 'Package_DFN_QFN:VQFN-32-1EP_5x5mm_P0.5mm_EP3.5x3.5mm', PHY, PHY_AT,
     mpn='LAN8670C2-E/LMX')
# pins 30/31 carry the pair swapped: TRXP (31) is the outer lane to the upper
# cap and TRXN (30) the inner to the lower, so the two never cross. 10BASE-T1S
# is DME coded, which does not care which way round the pair is
# straps (DS 3.5, no internal resistors): MII + crystal = MODE 01, PHY address 0
# RXD1/RXDV/RXD2/RXD3 and CRS reach theirs through a via on the line (below);
# rot 270 puts pad 2 (the strap net) on top
for ref, net, up, at, rot in (('R10', 'RXD2', True, (34.6, 1.0), 270), ('R11', 'RXD3', False, (34.6, 2.6), 90),
                              ('R14', 'RXD1', False, (34.6, -1.95), 270), ('R15', 'RXDV', False, (34.6, -0.5), 270),
                              ('R16', 'RXER', False, (34.6, -4.05), 90), ('R12', 'CRS', False, (32.85, -3.75), 270),
                              ('R13', 'RXD0', False, (35.5, -3.75), 270), ('R17', 'TXEN', False, (28.6, -2.4), 270)):
    part(ref, 'Device:R_Small', '10k', R0201, {1: '+3V3' if up else 'GND', 2: net}, at, side='B', rot=rot)
part('R18', 'Device:R_Small', '10k', R0201, {1: '+3V3', 2: 'MDIO'}, (35.5, 2.25), side='B', rot=90)
part('R19', 'Device:R_Small', '10k', R0201, {1: '+3V3', 2: 'PHY_INT_N'}, (35.5, 0.75), side='B', rot=90)
part('R20', 'Device:R_Small', '10k', R0201, {1: '+3V3', 2: 'PHY_RST_N'}, (35.5, -0.75), side='B', rot=90)
part('R21', 'Device:R_Small', '12.4k 1%', R0402, {1: 'RBIAS', 2: 'GND'}, (28.1, 4.2), side='B', rot=90)
part('Y1', 'Device:Crystal_GND24_Small', '25MHz CL12pF 2016', 'Crystal:Crystal_SMD_2016-4Pin_2.0x1.6mm',
     {1: 'XTI', 2: 'GND', 3: 'XTO', 4: 'GND'}, (31.4, 4.0), side='B', rot=180)   # XTI east, XTO west, as pins 27 / 28
part('C30', 'Device:C_Small', '18pF', C0201, {1: 'XTO', 2: 'GND'}, (29.4, 4.0), side='B', rot=90)
part('C31', 'Device:C_Small', '18pF', C0201, {1: 'XTI', 2: 'GND'}, (33.5, 4.0), side='B', rot=90)
for i, (at, r) in enumerate((((29.7, 2.3), 180), ((32.45, 2.1), 180), ((30.2, -1.45), 0), ((35.5, 3.75), 90))):
    part(f'C{32 + i}', 'Device:C_Small', '100nF', C0201, {1: '+3V3', 2: 'GND'}, at, side='B', rot=r)
part('C60', 'Device:C_Small', '10uF', C0603, {1: '+3V3', 2: 'GND'}, (27.6, 4.5))   # on top: underneath, the south bus had it

# MDI / BIN (AN1718 figure 1-3): 100 nF series caps, CMC, end-node termination
part('C40', 'Device:C_Small', '100nF 100V', C0805, {1: 'TRXP', 2: 'MDI_CP'}, (37.2, 4.3))
part('C41', 'Device:C_Small', '100nF 100V', C0805, {1: 'TRXN', 2: 'MDI_CN'}, (37.2, 2.3))
part('L2', 'Device:L_Coupled_1423', 'ACT1210E-241-2P', 'sfp:L_CommonMode_3225',
     {1: 'MDI_CP', 4: 'MDI_P', 2: 'MDI_CN', 3: 'MDI_N'}, (41.1, 3.3), mpn='ACT1210E-241-2P-TL00')
# AN1718 Rev D wants the end-node pair at 1 W in 1206 and the centre cap at
# 100 V; no 1 W 1206 49.9 ohm is stocked, so Vishay's 0.75 W CRCW1206-HP
part('R22', 'Device:R_Small', '49.9 1% 0.75W', R1206, {1: 'MDI_P', 2: 'MDI_TERM'}, (45.5, 4.1), mpn='CRCW120649R9FKEAHP')
part('R23', 'Device:R_Small', '49.9 1% 0.75W', R1206, {1: 'MDI_N', 2: 'MDI_TERM'}, (45.5, 1.85), mpn='CRCW120649R9FKEAHP')
part('C42', 'Device:C_Small', '100nF 100V', C0805, {1: 'MDI_TERM', 2: 'GND'}, (45.5, -1.2))
part('R24', 'Device:R_Small', '100k', R0805, {1: 'MDI_TERM', 2: 'GND'}, (45.5, -3.4))
part('J2', 'Connector_Generic:Conn_01x02', 'S2B-PH-K-S', 'Connector_JST:JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal',
     {1: 'MDI_P', 2: 'MDI_N'}, (51.6, 1.0), rot=90, mpn='S2B-PH-K-S(LF)(SN)')

# ---------------------------------------------------------------- MCU
# the pin order follows the In2 buses (below), which follow the fingers'
# order (SFF-8419: RX_LOS +2.2, SCL -0.2, SDA -1.0, TX_DISABLE -1.8,
# TX_FAULT -2.6, underneath): RX_LOS and SCL go along the north edge to pins
# 3 / 1, SDA, TX_DISABLE and TX_FAULT along the south edge to the bottom row.
# I2C1 on PB8 (pin 1, SCL, AF6) and PA10 (pin 17 with the PA12->PA10 remap,
# SDA, AF6); RX_LOS on PC15, TX_FAULT PA4, TX_DISABLE PA6 (fw: VARIANT_T1S)
MCU = {1: 'SCL', 2: None, 3: 'RX_LOS', 4: '+3V3', 5: 'GND', 6: 'NRST', 7: 'MDC', 8: 'MDIO',
       9: 'PHY_RST_N', 10: 'PHY_INT_N', 11: 'TX_FAULT', 12: None, 13: 'TX_DISABLE',
       14: 'FPGA_LINK', 15: 'FPGA_RECONFIG_N', 16: 'FPGA_DONE', 17: 'SDA', 18: 'SWDIO', 19: 'SWCLK', 20: None}
part('U8', 'MCU_ST_STM32G0:STM32G031F_4-6-8_Px', 'STM32G031F6P6', 'Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm', MCU,
     (39.6, 0.0), side='B', rot=90, mpn='STM32G031F6P6')
part('C43', 'Device:C_Small', '100nF', C0402, {1: '+3V3', 2: 'GND'}, (37.6, 4.7), side='B')
part('C44', 'Device:C_Small', '1uF', C0402, {1: '+3V3', 2: 'GND'}, (39.6, 4.7), side='B')
part('C45', 'Device:C_Small', '100nF', C0402, {1: 'NRST', 2: 'GND'}, (41.6, 4.7), side='B')
# pull-ups under their pins, past the vias the lines arrive through:
# DONE's, RECONFIG_N's, FPGA_LINK's and TX_DISABLE's (the MSA's module
# pull-up), fed by one track to a +3V3 via past the south bus's end (rot 270:
# pad 2, the line, on top)
part('R25', 'Device:R_Small', '10k', R0201, {1: '+3V3', 2: 'TX_DISABLE'}, (41.55, -4.65), side='B', rot=270)
part('R4', 'Device:R_Small', '4.7k', R0201, {1: '+3V3', 2: 'FPGA_DONE'}, (39.2, -4.65), side='B', rot=270)
part('R3', 'Device:R_Small', '4.7k', R0201, {1: '+3V3', 2: 'FPGA_RECONFIG_N'}, (40.0, -4.65), side='B', rot=270)
# P1 is also SSPI_CS_N, pulled down while the FPGA configures; held low after
# an MSPI load it would select slave SPI (UG720), so FPGA_LINK is pulled up
part('R26', 'Device:R_Small', '4.7k', R0201, {1: '+3V3', 2: 'FPGA_LINK'}, (40.75, -4.65), side='B', rot=270)
for i, (net, xy) in enumerate([('+3V3', (54.8, 4.2)), ('SWDIO', (54.8, 2.1)), ('SWCLK', (54.8, 0.0)),
                               ('NRST', (54.8, -2.1)), ('GND', (54.8, -4.2))]):
    part(f'TP{i + 1}', 'Connector:TestPoint', net, TP, {1: net}, xy, side='B')

# LCSC part numbers, JLC API 2026-09-30
LCSC_BY_MPN = {
    'GW5AT-LV15MG132C1/I0': 'C54067362', 'LAN8670C2-E/LMX': 'C20901523',
    'OB2EL89CLIB112YLC-125M': 'C7425465', 'GD25Q128EWIGR': 'C2982923',
    'TPS62822DLCR': 'C473385', 'DFE201610E-1R0M': 'C161082', 'CRCW120649R9FKEAHP': 'C4014562', 'TLV75518PDBVR': 'C2877863',
    'TLV75512PDBVR': 'C2877864', 'TPS22918DBVR': 'C131941', 'BLM18KG601SH1': 'C710379',
    'STM32G031F6P6': 'C529333', 'ACT1210E-241-2P-TL00': 'C6114822', 'S2B-PH-K-S(LF)(SN)': 'C173752',
}
LCSC_BY_VALUE = {
    ('100nF', C0201): 'C76928', ('100nF', C0402): 'C1525', ('1uF', C0402): 'C52923',
    ('4.7uF', C0402): 'C23733', ('10uF', C0603): 'C19702', ('10uF', C0402): 'C15525', ('2.2nF', C0402): 'C106861',
    ('120pF', C0201): 'C161406', ('18pF', C0201): 'C62164', ('4.7k', R0201): 'C142008',
    ('10k', R0201): 'C106225', ('10k', R0402): 'C25744', ('57.6k 1%', R0201): 'C423476',
    ('100k 1%', R0201): 'C106224', ('12.4k 1%', R0402): 'C284314',
    ('100nF 100V', C0805): 'C28233', ('100nF 50V', C0805): 'C49678', ('49.9 1%', R1206): 'C18018',
    ('100k', R0805): 'C118847', ('25MHz CL12pF 2016', 'Crystal:Crystal_SMD_2016-4Pin_2.0x1.6mm'): 'C5210656',
}


def lcsc_for(p):
    if p['dnp'] or p['ref'].startswith('TP') or p['ref'] == 'J1':
        return ''
    return LCSC_BY_MPN.get(p['mpn']) or LCSC_BY_VALUE.get((p['value'], p['fp']), '')


LENGTH = 58.4        # the JST housing starts past the cage front (44.3)
SCH_AT = {'J1': (40, 80), 'U1': (170, 150), 'U5': (300, 120), 'U8': (300, 230), 'U3': (60, 200),
          'J2': (380, 110), 'U2': (60, 280), 'X1': (110, 60), 'L2': (350, 110)}
POWER_NETS = ('+3V3', 'VCC_CORE', 'VDDAQ', 'VDDTQ', 'VDDHAQ', 'V1P2', 'VCCT', 'VCCR', 'VIN_RAW')

# ---------------------------------------------------------------- symbols
_KIND = {'Power': 'power_in', 'GND': 'power_in'}


def _fpga_symbol():
    rows = []
    for b in BALLS:
        n = b['pin_name']
        et = 'power_in' if b['function'] in ('Power', 'GND') or n.startswith(('VSS', 'VCC', 'VDD', 'VEFUSE')) \
            else ('passive' if b['ball'] in FPGA else 'no_connect')
        rows.append((b['ball'], n.split('/')[0][:18], et))
    rows.sort(key=lambda r: (r[2] != 'power_in', r[0]))
    half = (len(rows) + 1) // 2
    return ('GW5AT-15_MG132', 'U', rows[:half], rows[half:], 40.64)


def _phy_symbol():
    L = [('2', 'COL', 'output'), ('3', 'TXD3', 'input'), ('4', 'TXD2', 'input'), ('5', 'TXD1', 'input'),
         ('6', 'TXD0', 'input'), ('7', 'TXEN', 'input'), ('11', 'TXER/ACMA/LINK', 'input'), ('12', 'TXCLK/RXPI', 'output'),
         ('', '', ''), ('17', 'RXCLK/SMCLK', 'output'), ('16', 'RXD0/PHYAD2', 'bidirectional'),
         ('19', 'RXD1/PHYAD3', 'bidirectional'), ('23', 'RXD2/MODE0', 'bidirectional'),
         ('24', 'RXD3/MODE1', 'bidirectional'), ('20', 'RXDV/CRSDV/PHYAD1', 'bidirectional'),
         ('21', 'RXER/PHYAD0', 'bidirectional'), ('15', 'CRS/PHYAD4', 'bidirectional'),
         ('', '', ''), ('13', 'MDC', 'input'), ('14', 'MDIO', 'bidirectional'),
         ('10', 'RESET_N', 'input'), ('22', 'IRQ_N', 'open_collector')]
    # DS60001573K table 3-1. INH (1) and GPIO0 (9) are left open, as the
    # datasheet allows when unused; WAKE_IN (32) goes to VSS when unused
    R = [('8', 'VDDP', 'power_in'), ('18', 'VDDP', 'power_in'), ('25', 'VDDAU', 'power_in'),
         ('29', 'VDDA', 'power_in'), ('', '', ''), ('30', 'TRXP', 'bidirectional'), ('31', 'TRXN', 'bidirectional'),
         ('', '', ''), ('27', 'XTI/REFCLKIN', 'input'), ('28', 'XTO', 'output'), ('26', 'RBIAS', 'passive'),
         ('', '', ''), ('1', 'INH', 'no_connect'), ('9', 'GPIO0', 'no_connect'),
         ('32', 'WAKE_IN', 'input'), ('33', 'EP (VSS)', 'power_in')]
    return ('LAN8670', 'U', L, R, 25.4)


def _osc_symbol():
    return ('OSC_LVDS', 'X', [('6', 'VDD', 'power_in'), ('1', 'OE', 'input'), ('2', 'NC', 'no_connect'),
                              ('3', 'GND', 'power_in')],
            [('4', 'OUT+', 'output'), ('5', 'OUT-', 'output')], 15.24)


def _flash_symbol():
    # GD25Q128E in x1 SPI: WP# and HOLD# are inputs held high (KiCad's W25Q32
    # symbol calls them IO2/IO3, bidirectional, which ERC flags against +3V3)
    return ('GD25Q128_WSON8', 'U', [('8', 'VCC', 'power_in'), ('1', 'CS#', 'input'), ('6', 'CLK', 'input'),
                                   ('5', 'DI', 'input'), ('3', 'WP#', 'input'), ('7', 'HOLD#', 'input')],
            [('2', 'DO', 'output'), ('4', 'GND', 'power_in'), ('9', 'EP', 'passive')], 15.24)


SYMBOLS = [_fpga_symbol(), _phy_symbol(), _osc_symbol(), _flash_symbol(), sfpgen.TPS22918]
SOLID_PADS = {('U5', '33')}


def FOOTPRINTS(io, smd, crt, tht, slot, npth):
    import pcbnew
    MB = sfpgen.MB
    # Gowin MBGA-132, 8 x 8 mm, 0.5 mm pitch, 14 x 14 grid, outer three rings:
    # 0.25 mm pads, Gowin's recommended land (UG983 figure 4-8); the filled
    # vias in them are 0.25 / 0.15 (MIN_VIA)
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID('sfp', 'Gowin_MBGA-132_8x8mm_P0.5mm'))
    for b in BALLS:
        r, c = ROWS.index(b['ball'][0]), int(b['ball'][1:])
        p = pcbnew.PAD(fp)
        p.SetNumber(b['ball'])
        p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(p.SMDMask())
        p.SetSize(pcbnew.VECTOR2I(MB.MM(0.25), MB.MM(0.25)))
        p.SetPosition(pcbnew.VECTOR2I(MB.MM((c - 7.5) * 0.5), MB.MM((r - 6.5) * 0.5)))
        p.SetPos0(p.GetPosition())
        fp.Add(p)
    crt(fp, 4.25, 4.25)
    io.FootprintSave(sfpgen.FPLIB, fp)
    # YXC 3225 LVDS oscillator land (YSO230LR p.2): pins 1-3 along the bottom
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID('sfp', 'Oscillator_YXC_3225-6Pin_LVDS'))
    for num, x, y in (('1', -1.2, 0.8), ('2', 0.0, 0.8), ('3', 1.2, 0.8),
                      ('4', 1.2, -0.8), ('5', 0.0, -0.8), ('6', -1.2, -0.8)):
        smd(fp, num, x, y, 0.9, 1.1)
    crt(fp, 1.95, 1.6)
    io.FootprintSave(sfpgen.FPLIB, fp)
    # the JTAG pads: a 1.0 mm round pad and nothing else. KiCad's test point
    # draws a 1.4 mm silk ring, which at a 1.2 mm pitch runs over its neighbours
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID('sfp', 'TestPoint_Pad_D1.0mm_NoSilk'))
    p = pcbnew.PAD(fp)
    p.SetNumber('1')
    p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
    p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
    p.SetLayerSet(p.SMDMask())
    p.SetSize(pcbnew.VECTOR2I(MB.MM(1.0), MB.MM(1.0)))
    fp.Add(p)
    crt(fp, 0.55, 0.55)
    io.FootprintSave(sfpgen.FPLIB, fp)


# ---------------------------------------------------------------- rules and planes
SGMII = ['TD_P', 'TD_N', 'RD_P', 'RD_N', 'SRX_P', 'SRX_M', 'STX_P', 'STX_M', 'REFCLK_P', 'REFCLK_M',
         'OSC_P', 'OSC_N']
MDI = ['TRXP', 'TRXN', 'MDI_CP', 'MDI_CN', 'MDI_P', 'MDI_N']
PWR = ['+3V3', 'VCC_CORE', 'VDDAQ', 'VDDTQ', 'VDDHAQ', 'V1P2', 'BUCK_SW', 'VCCT', 'VCCR', 'VIN_RAW']
NETCLASSES = [
    dict(name='Default', clearance=0.15, track_width=0.127, via_diameter=0.35, via_drill=0.2),   # 0.35 / 0.2: fits among 0.5 mm pins (no JLC surcharge at 0.2)
    dict(name='SGMII', clearance=0.15, track_width=0.114, via_diameter=0.45, via_drill=0.25,
         dp_width=0.114, dp_gap=0.152, nets=SGMII),
    dict(name='MDI', clearance=0.15, track_width=0.2, via_diameter=0.45, via_drill=0.25, nets=MDI),
    dict(name='Power', clearance=0.15, track_width=0.2, via_diameter=0.35, via_drill=0.2, nets=PWR),
]
CLASS_LAYERS = {'SGMII': ['F.Cu', 'B.Cu']}
PAIRS = [('TD_P', 'TD_N'), ('SRX_P', 'SRX_M'), ('RD_P', 'RD_N'), ('STX_P', 'STX_M'),
         ('REFCLK_P', 'REFCLK_M'), ('MDI_P', 'MDI_N')]
MIN_VIA = (0.25, 0.15)           # via-in-pad: fits the BGA's 0.25 lands (JLC: 0.15 hole, 0.25 pad)
# via hole to copper: a line out between two ball vias passes their holes at
# 0.229 mm; 0.2 is inside JLC's multilayer BGA fan-out rules (check the DFM)
HOLE_CLEARANCE = 0.2
# inner layers: In1 / In4 GND (sfpgen), In2 signals, In3 +3V3 - whole
# planes, so the router leaves these nets to them (every pad gets a via)
PLANES = [('In3.Cu', '+3V3')]
# the core rail is an island of In4 (GND elsewhere) under the FPGA and the
# buck. On In2 it cut every line out of the ball field off: the small rails
# (VDDHAQ, V1P2, VDDAQ) and the inner-ring signals had no way out. In4 is
# under B, where the ball field carries only its stubs and decaps. The TX
# pair crosses it only on its last 0.75 mm into the balls (x > 11.75)
# (up to y 5.5: the buck's output pads and the beads sit along the top edge)
# one outline: the ball field, the buck east of it, and a tab west for FB4's
# core pad (above the TX pair's run)
ISLANDS = [('In4.Cu', 'VCC_CORE', [(11.75, -3.6), (18.8, -3.6), (18.8, 0.4), (26.0, 0.4), (26.0, 5.5),
                                   (10.7, 5.5), (10.7, 4.3), (11.75, 4.3)])]
PLANE_DOGBONE = ('VCC_CORE', '+3V3')
DP_W, DP_PITCH = 0.114, 0.266
# the JTAG pads sit 1.2 mm apart, beside the ball field: their courtyards
# are a probe's keep-out, and the pads keep 0.2 mm and more
COURTYARD_OK = {'U1': ['TP10', 'TP11', 'TP12', 'TP13'], 'TP10': ['TP11', 'TP13'], 'TP12': ['TP13']}
HEIGHTS = {'U1': 1.35, 'U5': 1.0, 'X1': 1.2, 'U8': 1.2, 'U2': 0.8, 'J2': 6.0, 'L2': 2.5, 'U3': 1.0,
           'U6': 1.45, 'U7': 1.45, 'U4': 1.45}
OVERHANG = ('J2',)

# ---------------------------------------------------------------- hand-laid copper
from sfpgen import pair_lines                    # noqa: E402

PREROUTES, PREVIAS = [], []


def _pair(left_net, right_net, layer, left_head, right_head, centre, left_tail, right_tail):
    ll, rl = pair_lines(centre, DP_PITCH)
    return [(left_net, layer, left_head + ll + left_tail, DP_W), (right_net, layer, right_head + rl + right_tail, DP_W)]


# the ball vias (filled, capped: in the pads)
for b in BALLS:
    if needs_via(b['ball']):
        PREVIAS.append((FPGA[b['ball']], ball_xy(b['ball']), MIN_VIA))

# SGMII RX (host TD -> FPGA lane 0 RX), on top: the fingers are at the bottom
# of the tab (TD+ -2.2, TD- -3.0), the lane at the FPGA's top-left corner. From
# the caps east, then north up the ball field's west side (west of the JTAG
# pads) and east again above row A: heading east at the end the P line is the
# upper one, so the lower (M) drops into A1 (RXM) and P runs on into A2 (RXP)
_a1, _a2 = ball_xy('A1'), ball_xy('A2')
PREROUTES += _pair('SRX_P', 'SRX_M', 'F', [(5.52, -2.2)], [(5.52, -3.0)],
                   [(5.92, -2.6), (8.9, -2.6), (9.4, -2.1), (9.4, 3.4), (9.9, 3.9), (_a1[0] - 0.25, 3.9)],
                   [(_a2[0], 3.9 + 0.133), (_a2[0], _a2[1])], [(_a1[0], 3.9 - 0.133), (_a1[0], _a1[1])])
# refclk: A7/A8 up above row A, east to the caps and the oscillator's outputs
_a7, _a8 = ball_xy('A7'), ball_xy('A8')
PREROUTES += [('REFCLK_M', 'F', [_a7, (_a7[0], 4.4), (19.6, 4.4), (19.75, 4.55), (19.98, 4.55)], DP_W),
              ('REFCLK_P', 'F', [_a8, (_a8[0], 3.8), (19.6, 3.8), (19.7, 3.7), (19.98, 3.7)], DP_W),
              ('OSC_P', 'F', [(20.62, 4.55), (21.8, 4.55)], DP_W),
              ('OSC_N', 'F', [(20.62, 3.7), (21.3, 3.7), (21.45, 3.55), (21.8, 3.55)], DP_W)]
# SGMII TX (FPGA -> host RD), underneath: out of B3 / C3's vias between their
# neighbours' vias (P up into A2's site, M down into D2's), coupled west at
# y 2.2 with P the upper line, to vias by the RD caps. RD+ (pin 13, +1.8) is
# below RD- (pin 12, +2.6), so the order has to turn over once: P stops at its
# via (8.3, 2.6) while M runs on underneath it to a via 1.2 mm further west;
# on top P's line then passes under M's via to the lower cap. No pair crosses
# itself and neither lane is inverted.
_b3, _c3 = ball_xy('B3'), ball_xy('C3')
STX_VIA = {'STX_P': (8.3, 2.6), 'STX_M': (7.1, 2.6)}
PREROUTES += [('STX_P', 'B', [_b3, (_b3[0] - 0.5, _b3[1] + 0.5)], 0.1),     # 0.1 between the ball vias
              ('STX_M', 'B', [_c3, (_c3[0] - 0.5, _c3[1] - 0.5)], 0.1),
              ('STX_P', 'B', [(_b3[0] - 0.5, _b3[1] + 0.5), (11.55, 3.25), (10.633, 2.333), (8.567, 2.333),
                              STX_VIA['STX_P']], DP_W),
              ('STX_M', 'B', [(_c3[0] - 0.5, _c3[1] - 0.5), (11.65, 1.75), (11.333, 2.067), (7.633, 2.067),
                              STX_VIA['STX_M']], DP_W),
              ('STX_P', 'F', [STX_VIA['STX_P'], (7.5, 1.8), (5.52, 1.8)], DP_W),
              ('STX_M', 'F', [STX_VIA['STX_M'], (5.52, 2.6)], DP_W)]
PREVIAS += [(n, xy) for n, xy in STX_VIA.items()] + [('GND', (7.7, 3.35)), ('GND', (8.5, 3.35))]

# MII, on top. TX: the FPGA's right column straight across to the PHY's left
# side, each line one pitch down on the way. RX: the bottom row down into
# seven lanes along the bottom edge, to the PHY's bottom pins and round its
# corner up to its right side; TXCLK above them to pin 12. The PHY pins the
# lanes pass (right side 18/21/22, bottom 10/11/13/14) take a via in the pad.
_MW = 0.1                       # 0.25 mm pitch lanes: 0.1 lines, 0.15 gaps
_px = lambda pin: [p for p in _PHY_PADS if p[0] == pin][0][1:]
_PHY_PADS = [(k, round(PHY_AT[0] - 2.45, 3), round(1.75 - 0.5 * (k - 1), 3)) for k in range(1, 9)] + \
            [(k, round(PHY_AT[0] - 1.75 + 0.5 * (k - 9), 3), -2.45) for k in range(9, 17)] + \
            [(k, round(PHY_AT[0] + 2.45, 3), round(-1.75 + 0.5 * (k - 17), 3)) for k in range(17, 25)]
for ball, pin in (('C14', 2), ('D14', 3), ('E14', 4), ('F14', 5), ('G14', 6), ('H14', 7)):
    bx, by = ball_xy(ball)
    px, py = _px(pin)
    PREROUTES.append((FPGA[ball], 'F', [(bx, by), (bx + 0.7, by), (bx + 1.7, py), (px, py)], _MW))
_j = ball_xy('J14')
PREROUTES.append(('TXCLK', 'F', [_j, (_j[0] + 0.6, _j[1]), (_j[0] + 0.6, -3.35), (_px(12)[0], -3.35), _px(12)], _MW))
_RX = [('P14', 'CRS', -3.6, 15, None), ('P13', 'RXD0', -3.85, 16, None), ('P12', 'RXCLK', -4.1, 17, 34.2),
       ('P11', 'RXD1', -4.35, 19, 34.45), ('P10', 'RXDV', -4.6, 20, 34.7), ('P9', 'RXD2', -4.85, 23, 34.95),
       ('P8', 'RXD3', -5.1, 24, 35.2)]
for ball, net, lane, pin, up in _RX:
    bx, by = ball_xy(ball)
    px, py = _px(pin)
    path = [(bx, by), (bx, lane)]
    path += [(px, lane), (px, py)] if up is None else [(up, lane), (up, py), (px, py)]
    PREROUTES.append((net, 'F', path, _MW))
for pin in (18, 21, 22, 10, 11, 13, 14):
    px, py = _px(pin)
    at = (round(px + (0.21 if pin >= 17 else 0.0), 3), round(py - (0.21 if pin < 17 else 0.0), 3))
    PREVIAS.append((PHY[pin], at, MIN_VIA))

# the ball field underneath: only used balls carry a via, so the unused sites
# and the outer ring's F-only balls are the way out. Each diagonal passes
# between two ball vias 0.354 mm off each (0.1 lines: 0.15 to their pads,
# 0.23 to their holes).
_BW = 0.1
_bxy = ball_xy
# left side. In2 inside the ball field has room only on the diagonals
# between four vias (0.354 mm off each), or through rows and columns with no
# via. JTAG leaves west on In2 to vias at x 11.4, then on top to its pads;
# TCK's pull-down R7 sits under its via
_DV = (0.35, 0.2)
_JT = [('JTAG_TMS', [_bxy('G3'), _bxy('F2'), (11.4, 0.75)], (10.6, 1.1)),
       ('JTAG_TCK', [_bxy('G2'), (11.4, 0.25)], (10.6, 0.05)),
       ('JTAG_TDO', [_bxy('J2'), (11.4, -0.75)], (10.6, -1.1)),
       ('JTAG_TDI', [_bxy('J3'), _bxy('K2'), (11.4, -1.25)], (10.7, -2.2))]
for net, path, tp in _JT:
    PREROUTES.append((net, 'In2', path, _BW))
    PREVIAS.append((net, path[-1], _DV))
    top = [path[-1], (11.4, -1.8), tp] if net == 'JTAG_TDI' else [path[-1], tp]
    PREROUTES.append((net, 'F', top, _BW))
PREROUTES.append(('JTAG_TCK', 'B', [(11.4, 0.25), (11.02, 0.25)], _BW))
# DONE, RECONFIG_N and the 1.2 V rail (M7) straight down out of the field on
# In2 (rows N and P carry no vias but N2's, MODE0), where the south bus takes
# them (below); DONE goes round N2's via through N1's site (a pad on top only)
PREROUTES += [('FPGA_DONE', 'In2', [_bxy('L3'), _bxy('M2'), _bxy('N1'), (_bxy('N1')[0], -3.25)], _BW),
              ('FPGA_RECONFIG_N', 'In2', [_bxy('M3'), (13.0, -2.9)], _BW),
              ('V1P2', 'In2', [_bxy('M7'), (15.0, -2.9)], _BW)]
R1_PAD = {'MODE': (11.1, -3.23), '+3V3': (11.1, -3.87)}      # R1, rot 90 underneath
# MODE1 (N1) and FPGA_LINK (P1) are outer-ring balls, on top only; MODE0 (N2)
# has its via in the pad and joins MODE1's via underneath, through N1's site
PREROUTES += [('MODE', 'F', [_bxy('N1'), (11.45, -2.75)], _BW),
              ('MODE', 'B', [(11.45, -2.75), (11.1, -3.1), R1_PAD['MODE']], _BW),
              ('MODE', 'B', [_bxy('N2'), (11.45, -2.75)], _BW),
              ('FPGA_LINK', 'F', [_bxy('P1'), (12.25, -3.5), (12.25, -4.45)], _BW)]   # past P2's pad, down to its bus lane
PREVIAS += [('MODE', (11.45, -2.75), _DV), ('FPGA_LINK', (12.25, -4.45), _DV)]
# FPGA_READY (M12) to its pull-up R5 in the grid, underneath between L12 and M11
PREROUTES.append(('FPGA_READY', 'B', [_bxy('M12'), (17.25, -2.0), (17.0, -1.75), (16.62, -1.37)], _BW))
# the grid caps of the small rails take a via in their pad
PREVIAS += [('VDDHAQ', (15.98, -0.45), MIN_VIA), ('V1P2', (13.88, -1.35), MIN_VIA)]

# PHY straps: a via on each line's last stretch into its pin, then under to
# the strap below it (R10/R11/R14/R15 next to the right side, R12 under CRS)
PREVIAS += [('RXD3', (34.0, 1.75), _DV), ('RXD2', (34.0, 1.25), _DV), ('RXDV', (34.0, -0.25), _DV),
            ('RXD1', (34.0, -0.75), _DV),
            # CRS, RXD0 (bottom side) and TXEN (left side): a via in the pad, as pins 10-14
            ('CRS', (32.25, -2.66), MIN_VIA), ('RXD0', (32.75, -2.66), MIN_VIA), ('TXEN', (28.34, -1.25), MIN_VIA)]
PREROUTES += [('RXD3', 'B', [(34.0, 1.75), (34.25, 2.0), (34.6, 2.28)], _BW),
              ('RXD2', 'B', [(34.0, 1.25), (34.6, 1.32)], _BW),
              ('RXDV', 'B', [(34.0, -0.25), (34.6, -0.18)], _BW),
              ('RXD1', 'B', [(34.0, -0.75), (34.1, -0.9), (34.1, -1.3), (34.35, -1.63), (34.6, -1.63)], _BW),
              ('CRS', 'B', [(32.25, -2.66), (32.85, -3.25), (32.85, -3.43)], _BW),
              ('RXD0', 'B', [(32.75, -2.66), (33.3, -3.2), (35.2, -3.2), (35.5, -3.43)], _BW),
              ('TXEN', 'B', [(28.34, -1.25), (28.6, -1.5), (28.6, -2.08)], _BW)]
# XTI (pin 27): a via in the pad, then underneath between the crystal's pads 3 and 4
PREVIAS += [('XTI', (31.75, 2.75), MIN_VIA), ('XTO', (31.25, 2.66), MIN_VIA)]
PREROUTES += [('XTI', 'B', [(31.75, 2.75), (32.0, 3.0), (32.0, 3.1)], _BW),
              ('XTO', 'B', [(31.25, 2.66), (31.35, 2.8), (31.35, 4.0), (31.0, 4.3)], _BW)]

# the MCU's lines to the fingers and the FPGA: a via beside each pin (bottom
# row under its pad, the top row's over theirs) and one beside each finger
_MCU_VIA = {'SDA': 38.625, 'FPGA_DONE': 39.275, 'FPGA_RECONFIG_N': 39.925, 'FPGA_LINK': 40.575,
            'TX_DISABLE': 41.225, 'TX_FAULT': 42.525}
for net, x in _MCU_VIA.items():
    PREVIAS.append((net, (x, -4.0), _DV))
    PREROUTES.append((net, 'B', [(x, -3.3), (x, -4.0)], _BW))
# and the four pull-ups from the pins' inner ends
PREROUTES += [('+3V3', 'B', [(39.2, -4.97), (39.2, -5.15), (40.0, -5.15), (40.75, -5.15), (41.55, -5.15), (42.4, -5.15),
                             (42.6, -4.95)], 0.15),
              ('+3V3', 'B', [(40.0, -4.97), (40.0, -5.15)], 0.15),
              ('+3V3', 'B', [(40.75, -4.97), (40.75, -5.15)], 0.15),
              ('+3V3', 'B', [(41.55, -4.97), (41.55, -5.15)], 0.15),
              ('TX_DISABLE', 'B', [(41.225, -4.0), (41.55, -4.33)], _BW)]
PREVIAS.append(('+3V3', (42.6, -4.95), _DV))
# the top row's two: vias under the MCU (the MDI caps fill the top above
# pins 1-3)
for net, x in (('SCL', 36.675), ('RX_LOS', 37.975)):
    PREVIAS.append((net, (x, 1.2), _DV))
    PREROUTES.append((net, 'B', [(x, 2.5), (x, 1.2)], _BW))

# the fingers (SFF-8419 figure 7-2): the host pairs straight in to their caps
# on top, VCCT (-0.6) and VCCR (+0.2) straight to the beads, which join on
# top and drop VIN_RAW to the load switch underneath. The slow lines leave
# their fingers underneath to vias as close as the pairs and the ground vias
# (x 4.55, sfpgen.preroute_edge_gnd) let them, then run on In2: RX_LOS between
# the RD lines' run to its cap, TX_FAULT between the TD lines', SCL between
# the beads, SDA and TX_DISABLE below FB1
PREROUTES += [('TD_P', 'F', [(3.6, -2.2), (4.88, -2.2)], DP_W), ('TD_N', 'F', [(3.6, -3.0), (4.88, -3.0)], DP_W),
              ('RD_P', 'F', [(3.6, 1.8), (4.88, 1.8)], DP_W), ('RD_N', 'F', [(3.6, 2.6), (4.88, 2.6)], DP_W),
              ('VCCT', 'F', [(3.6, -0.6), (5.3, -0.6), (5.45, -0.75), (6.61, -0.75)], 0.3),
              ('VCCR', 'F', [(3.6, 0.2), (5.2, 0.2), (5.9, 0.9), (6.61, 0.9)], 0.3),
              ('VIN_RAW', 'F', [(8.45, -0.75), (8.45, 0.9)], 0.3)]
PREVIAS.append(('VIN_RAW', (8.45, 0.075), _DV))
_EDGE_VIA = {'RX_LOS': [(3.6, 2.2), (6.1, 2.2)],
             'SCL': [(3.6, -0.2), (7.1, -0.2), (7.4, 0.075)],
             'SDA': [(3.6, -1.0), (4.0, -0.9), (6.4, -0.9), (6.9, -1.4), (6.9, -1.7)],
             'TX_DISABLE': [(3.6, -1.8), (4.0, -1.85), (5.95, -1.85), (6.1, -1.75)],
             'TX_FAULT': [(3.6, -2.6), (4.2, -2.6)]}
for net, path in _EDGE_VIA.items():
    PREVIAS.append((net, path[-1], _DV))
    PREROUTES.append((net, 'B', path, _BW))
# the LDO outputs: a via between each LDO's pin rows, out to pin 5
PREVIAS += [('VDDHAQ', (45.6, 2.45), _DV), ('V1P2', (45.6, -4.35), _DV)]
PREROUTES += [('VDDHAQ', 'B', [(45.6, 2.45), (46.3, 2.45)], 0.2),
              ('V1P2', 'B', [(45.6, -4.35), (46.3, -4.35)], 0.2)]
# the local links Freerouting left open around them
PREVIAS += [('VCC_CORE', (15.812, 4.85), MIN_VIA), ('VCC_CORE', (11.213, 4.85), MIN_VIA),   # in FB3/FB4's core pads
            ('VCC_CORE', (25.45, 4.95), _DV),                                             # buck output, beside C12
            ('+3V3', (30.75, 2.66), MIN_VIA), ('+3V3', (32.75, 2.66), MIN_VIA),        # PHY pins 29 / 25
            ('+3V3', (11.1, -4.35), _DV),                                                 # R1 (MODE)
            ('+3V3', (24.2, 1.7), _DV)]                                                   # the buck's VIN, between U3 and R8/C14
PREROUTES += [('VDDAQ', 'B', [(17.388, 4.6), (17.5, 4.3), (17.5, 3.25)], 0.15),         # FB3 to ball A12
              ('VDDTQ', 'B', [(12.787, 4.6), (13.5, 3.9), (13.5, 2.75)], 0.15),         # FB4 to ball B4
              ('VDDTQ', 'B', [(13.225, 4.95), (13.75, 4.95)], 0.15),                    # and C59
              ('VCC_CORE', 'B', [(23.125, 4.9), (23.4, 5.075), (24.3, 5.075)], 0.2),   # L1 to C12
              ('VCC_CORE', 'B', [(25.075, 5.0), (25.45, 4.95)], 0.2),
              ('+3V3', 'B', [(30.75, 2.66), (30.3, 2.35), (30.02, 2.3)], 0.15),        # pin 29 to C32
              ('+3V3', 'B', [(32.75, 2.66), (32.77, 2.3)], 0.15),                      # pin 25 to C33
              ('+3V3', 'B', [(38.625, 3.4), (38.625, 3.85), (38.85, 4.0), (39.12, 4.5)], 0.15),   # its via: plane_dogbones
              ('+3V3', 'B', [(38.85, 4.0), (37.5, 4.0), (37.12, 4.4)], 0.15),            # C43
              ('+3V3', 'B', [(15.42, -4.44), (15.42, -4.2), (16.0, -3.0), (16.0, -2.25)], 0.15),   # C17 to ball M9
              ('+3V3', 'B', [R1_PAD['+3V3'], (11.1, -4.35)], 0.15),
              ('+3V3', 'B', [(23.525, 1.45), (24.0, 1.45), (24.2, 1.7)], 0.15),         # U3 VIN
              # the feedback: out of pin 2 west, round under U3 and east to R8
              ('BUCK_FB', 'B', [(21.35, 1.45), (21.0, 1.45), (21.0, 0.4), (25.5, 0.4), (25.72, 0.62),
                                (25.72, 1.9)], _BW)]

# the long runs on In2 between those vias. Found once by a maze search over
# this board before its dogbones went in (8-way, 0.025 mm grid, 0.15 mm
# clearance), with each line held to its lane along the south edge so the
# lanes stack in the order the MCU's pins take them: V1P2, RECONFIG_N, DONE,
# SDA above the pins' via row, FPGA_LINK, TX_DISABLE and TX_FAULT below it.
# Along the north edge SCL and RX_LOS; VDDHAQ leaves the ball field through
# row C and runs under the MCU; MISO crosses over the flash. Since the SFP
# edge fix (2026-10) the west ends are laid by hand from the fingers' vias:
# the fingers' order (RX_LOS, SCL | SDA, TX_DISABLE, TX_FAULT, top to bottom)
# is the lanes' order, so nothing crosses
IN2_BUS = [
    ('SCL', 0.1, [(7.4, 0.075), (8.7, 1.375), (9.2, 1.375), (9.2, 2.3), (10.525, 3.625), (35.175, 3.625),
                  (36.675, 2.125), (36.675, 1.2)]),
    ('RX_LOS', 0.1, [(6.1, 2.2), (6.5, 2.6), (6.5, 3.6), (7.05, 4.15), (35.4, 4.15), (37.975, 1.575),
                     (37.975, 1.2)]),
    ('VDDHAQ', 0.15, [(17.0, 2.25), (16.6, 1.85), (15.975, 1.85), (15.4, 1.85), (15.0, 2.25)]),
    ('VDDHAQ', 0.15, [(15.975, 1.85), (15.98, -0.45)]),
    ('VDDHAQ', 0.15, [(17.0, 2.25), (35.05, 2.25), (36.5, 0.8), (43.95, 0.8), (45.6, 2.45)]),
    ('F_MISO', 0.1, [(18.5, -1.25), (18.975, -1.725), (27.05, -1.72)]),
    ('V1P2', 0.15, [(15.0, -2.9), (15.0, -1.975), (17.1, 0.125), (17.1, 0.4), (17.45, 0.75), (17.5, 0.75)]),
    ('V1P2', 0.15, [(15.0, -1.975), (14.375, -1.35), (13.88, -1.35)]),
    ('V1P2', 0.15, [(15.0, -2.9), (15.15, -3.05), (44.3, -3.05), (45.6, -4.35)]),
    ('FPGA_RECONFIG_N', 0.1, [(13.0, -2.9), (13.425, -3.325), (39.325, -3.325), (39.925, -3.925), (39.925, -4.0)]),
    ('FPGA_DONE', 0.1, [(12.0, -3.25), (12.35, -3.6), (38.95, -3.6), (39.275, -3.925), (39.275, -4.0)]),
    # SDA between the JTAG and MODE vias, then under DONE's start
    ('SDA', 0.1, [(6.9, -1.7), (10.4, -1.7), (10.9, -2.2), (10.9, -2.9), (11.875, -3.875), (38.5, -3.875),
                  (38.625, -4.0)]),
    ('FPGA_LINK', 0.1, [(12.25, -4.45), (12.25, -4.45), (40.2, -4.425), (40.575, -4.05), (40.575, -4.0)]),
    ('TX_DISABLE', 0.1, [(6.1, -1.75), (9.225, -4.875), (40.4, -4.875), (41.225, -4.05), (41.225, -4.0)]),
    ('TX_FAULT', 0.1, [(4.2, -2.6), (5.3, -2.6), (7.825, -5.125), (41.65, -5.125), (42.525, -4.25), (42.525, -4.0)]),
]
for net, w, path in IN2_BUS:
    PREROUTES.append((net, 'In2', path, w))
# the flash (bank 2 corner), turned 180 degrees so CLK and MOSI (pins 6/5)
# face the ball field: both straight across underneath. CS (pin 1) runs over
# the flash's top edge underneath, with its pull-up R6 on the way; MISO
# (pin 2) crosses on In2 (the bus, below). WP# (pin 3) takes +3V3 from a via
# above the south bus, HOLD# and VCC (pins 7/8) theirs beside the ball field
PREROUTES += [('F_CLK', 'B', [_bxy('L14'), (19.0, -2.25), (19.0, -3.0), (19.235, -3.235), (20.9, -3.235)], _BW),
              ('F_MOSI', 'B', [_bxy('M13'), (18.5, -2.75), (18.5, -3.5), (19.5, -4.505), (20.9, -4.505)], _BW),
              ('F_CS_N', 'B', [_bxy('L13'), (18.0, -0.75), (18.4, -0.35), (18.65, -0.1), (19.4, -0.1),
                               (26.0, -0.1), (26.3, -0.4), (26.3, -0.6)], _BW),
              ('F_CS_N', 'B', [(19.4, -0.1), (19.4, 0.03)], _BW),
              ('F_MISO', 'B', [(27.05, -1.72), (26.5, -1.965)], _BW),
              ('+3V3', 'B', [(26.3, -3.235), (26.8, -3.0), (27.0, -2.8), (27.0, -2.55)], 0.15)]
PREVIAS += [('F_MISO', (27.05, -1.72), _DV), ('+3V3', (27.0, -2.55), _DV)]
# the PHY's exposed pad: 2 x 2 thermal vias to the GND planes
PREVIAS += [('GND', (round(PHY_AT[0] + dx, 3), dy)) for dx in (-0.7, 0.7) for dy in (-0.7, 0.7)]

# AN1718: no copper under the CMC on any layer, and no ground flood round
# the MDI parts on their layer
NO_POUR = [(39.1, 1.75, 43.1, 4.85, ('F', 'In1', 'In2', 'In3', 'In4', 'B')),
           (35.5, 0.73, 47.8, 5.3, ('F',))]


IN2_GND = False                   # this board's inner layers are set by PLANES


if __name__ == '__main__':
    sys.exit(sfpgen.run(sys.modules[__name__]))

#!/usr/bin/env python3
"""SFP 10BASE-T1S module: symbols, schematic, PCB.

    python3 make_t1s.py [--route | --reuse-ses]

No 10BASE-T1S PHY speaks SGMII, so an FPGA does (docs/PARTS.md): the host's
SGMII on a hard transceiver lane, our own PCS / rate adaptation / half-duplex
MAC in fabric (gw/), and MII to a LAN8670.

Sources:
  Gowin GW5AT-15 (LCSC C54067362, MG132: 8 x 8 mm, 0.5 mm pitch, 14 x 14
      grid with only the outer three rings populated)
      ball map: UG1224E.xlsx "Pin List MG132" -> gw5at15_mg132.csv (as is)
      rails: DS981 table 3-8; UG984 (schematic manual) 2.4 / table 2-3: rails
      at one voltage may share a regulator through a ferrite bead each
      transceiver: DS981 3-46..3-49; refclk AC coupled, 100 nF at the FPGA
      (UG984 5.2), the kit (DK_EDP_GW5ART-LV15MG132P) drives it from a 3225
      LVDS oscillator with no other termination
      configuration: UG720 - MSPI (MODE[1:0] = 11, internal pull-ups plus
      4.7k), flash >= 64 Mbit (the retry image lives at 0x800000)
  Microchip LAN8670 (C20901523, VQFN-32 5 x 5): DS60001573C pins table 3-1,
      straps 3.5 (no internal resistors: 10k each), 25 MHz crystal 7.8,
      MDI and BIN: AN1718 figure 1-3 (CMC, 2 x 100 nF, end-node termination)
  YXC OB2EL89CLIB112YLC-125M (C7425465): 125 MHz LVDS, 3225-6P; pins 1 OE,
      2 NC, 3 GND, 4 OUT+, 5 OUT-, 6 VDD; land 0.9 x 1.1 at 1.2 pitch, rows
      +-0.8 (YSO230LR datasheet p.2)
  TPS62822 (core 0.946 V: 57.6k / 100k), TLV75518 / TLV75512 (SOT-23-5,
      1.8 V for VDDHAQ0, 1.2 V for VDD12M + VCCLDO), TPS22918 soft start

Six layers, because of the BGA: 0.5 mm pitch leaves no track between balls,
so every used ball inside the outer ring has a via in its pad (JLC fills and
caps those for free on 6+ layers), and five supply rails sit interleaved round
the ring. Stack:  F signals | In1 GND | In2 core 0.95 V | In3 +3V3 | In4 GND |
B signals. The SGMII pairs run on F over In1 and on B over In4.

SerDes polarity: both lanes are laid straight, which leaves RX inverted
(TD+ lands on RXM) and TX as it comes; the gateware inverts the 10-bit words
(gw/t1s_top.v, RX_INVERT), so no pair crosses itself.
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
TITLE_AT = (49.2, -4.7)

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

# host rails, beads, soft-start load switch (as the T1 board)
part('FB1', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'VCCT', 2: 'VIN_RAW'}, (8.9, 4.9), mpn='BLM18KG601SH1')
part('FB2', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'VCCR', 2: 'VIN_RAW'}, (8.9, -4.9), mpn='BLM18KG601SH1')
part('C1', 'Device:C_Small', '1uF', C0402, {1: 'VIN_RAW', 2: 'GND'}, (9.0, -4.4), side='B', rot=90)
part('C2', 'Device:C_Small', '100nF', C0402, {1: 'VIN_RAW', 2: 'GND'}, (10.3, -4.4), side='B', rot=90)
part('U4', 'sfp:TPS22918', 'TPS22918DBVR', 'Package_TO_SOT_SMD:SOT-23-6',
     {1: 'VIN_RAW', 2: 'GND', 3: 'VIN_RAW', 4: 'SS_CT', 5: '+3V3', 6: '+3V3'}, (7.0, 2.6), side='B',
     mpn='TPS22918DBVR')      # inside the tab's 9.2 mm, above the TX pair's path underneath
part('C36', 'Device:C_Small', '2.2nF', C0402, {1: 'SS_CT', 2: 'GND'}, (8.6, 0.3), side='B')
part('C37', 'Device:C_Small', '10uF', C0603, {1: '+3V3', 2: 'GND'}, (6.2, -0.8), side='B')

# SGMII AC coupling in the module (MSA): TD -> FPGA RX, FPGA TX -> RD
part('C3', 'Device:C_Small', '100nF', C0201, {1: 'TD_P', 2: 'SRX_M'}, (5.2, 2.2))   # straight: TD+ reaches RXM (inverted in gateware)
part('C4', 'Device:C_Small', '100nF', C0201, {1: 'TD_N', 2: 'SRX_P'}, (5.2, 3.0))
part('C5', 'Device:C_Small', '100nF', C0201, {1: 'RD_P', 2: 'STX_P'}, (5.2, -1.8))
part('C6', 'Device:C_Small', '100nF', C0201, {1: 'RD_N', 2: 'STX_M'}, (5.2, -2.6))

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
    'N1': 'MODE1', 'M3': 'FPGA_RECONFIG_N',          # MODE0 (N2): its internal pull-up (MSPI = 11) 'L3': 'FPGA_DONE', 'M12': 'FPGA_READY',
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
part('U2', 'Memory_Flash:W25Q32JVZP', 'GD25Q64CWIGR', 'Package_SON:WSON-8-1EP_6x5mm_P1.27mm_EP3.4x4.3mm',
     {1: 'F_CS_N', 2: 'F_MISO', 3: '+3V3', 4: 'GND', 5: 'F_MOSI', 6: 'F_CLK', 7: '+3V3', 8: '+3V3', 9: 'GND'},
     (23.6, -2.6), side='B', mpn='GD25Q64CWIGR')      # WP#/HOLD# tied high: x1 SPI only
# straps and config pull-ups (UG984 3.5: 4.7k)
# (R5 READY and R6 flash CS sit in the decap grid under the FPGA, below)
for ref, net, at in (('R1', 'MODE1', (10.7, -2.7)),
                     ('R3', 'FPGA_RECONFIG_N', (10.7, -0.9)), ('R4', 'FPGA_DONE', (10.7, 0.0))):
    part(ref, 'Device:R_Small', '4.7k', R0201, {1: '+3V3', 2: net}, at, side='B')
part('R7', 'Device:R_Small', '4.7k', R0201, {1: 'JTAG_TCK', 2: 'GND'}, (10.7, 0.9), side='B')

# ---------------------------------------------------------------- FPGA supplies
# core 0.946 V: buck, then beads to the transceiver's analog and TX rails
BUCK = (22.4, 1.7)
part('U3', 'Regulator_Switching:TPS62823DLC', 'TPS62822DLC', 'sfp:Texas_VSON-HR-8_1.5x2mm_P0.5mm',
     {1: '+3V3', 2: 'BUCK_FB', 3: 'GND', 4: None, 5: 'GND', 6: 'BUCK_SW', 7: '+3V3', 8: None},
     BUCK, side='B', mpn='TPS62822DLCR')
part('L1', 'Device:L_Small', '470nH DFE201610E-R47M', 'Inductor_SMD:L_Murata_DFE201610P',
     {1: 'BUCK_SW', 2: 'VCC_CORE'}, (22.4, 4.2), side='B', mpn='DFE201610E-R47M')
part('C11', 'Device:C_Small', '4.7uF', C0402, {1: '+3V3', 2: 'GND'}, (20.4, 1.7), side='B', rot=90)
part('C12', 'Device:C_Small', '10uF', C0603, {1: 'VCC_CORE', 2: 'GND'}, (24.6, 4.3), side='B', rot=90)
part('C13', 'Device:C_Small', '10uF', C0603, {1: 'VCC_CORE', 2: 'GND'}, (20.2, 4.3), side='B', rot=90)
part('R8', 'Device:R_Small', '57.6k 1%', R0201, {1: 'VCC_CORE', 2: 'BUCK_FB'}, (24.6, 1.0), side='B')
part('C14', 'Device:C_Small', '120pF', C0201, {1: 'VCC_CORE', 2: 'BUCK_FB'}, (24.6, 1.9), side='B')
part('R9', 'Device:R_Small', '100k 1%', R0201, {1: 'BUCK_FB', 2: 'GND'}, (26.2, 1.4), side='B', rot=90)
part('FB3', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'VCC_CORE', 2: 'VDDAQ'}, (16.6, 4.95), side='B', mpn='BLM18KG601SH1')
part('FB4', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'VCC_CORE', 2: 'VDDTQ'}, (12.0, 4.95), side='B', mpn='BLM18KG601SH1')
# 1.8 V (VDDHAQ0) and 1.2 V (VDD12M, VCCLDO) LDOs from +3V3
part('U6', 'Regulator_Linear:TLV75518PDBV', 'TLV75518PDBVR', 'Package_TO_SOT_SMD:SOT-23-5',
     {1: '+3V3', 2: 'GND', 3: '+3V3', 4: None, 5: 'VDDHAQ'}, (45.6, 3.4), side='B', mpn='TLV75518PDBVR')
part('U7', 'Regulator_Linear:TLV75512PDBV', 'TLV75512PDBVR', 'Package_TO_SOT_SMD:SOT-23-5',
     {1: '+3V3', 2: 'GND', 3: '+3V3', 4: None, 5: 'V1P2'}, (45.6, -3.4), side='B', mpn='TLV75512PDBVR')
part('C15', 'Device:C_Small', '1uF', C0402, {1: 'VDDHAQ', 2: 'GND'}, (11.9, -4.75), side='B')
part('C16', 'Device:C_Small', '1uF', C0402, {1: 'V1P2', 2: 'GND'}, (13.9, -4.75), side='B')
part('C17', 'Device:C_Small', '1uF', C0402, {1: '+3V3', 2: 'GND'}, (15.9, -4.75), side='B')
part('C18', 'Device:C_Small', '4.7uF', C0402, {1: 'VDDAQ', 2: 'GND'}, (13.8, 4.8))   # on top, over row A's VDDAQ balls

# decoupling under the FPGA: a 3 x 4 grid of 0201s in the empty centre of the
# ball ring (bottom), 0.23 mm clear of the ring's vias; the bulk caps along
# the ring's outer edges. UG984 / the kit's sheet 9, scaled to one lane.
_cx, _cy = U1_AT
_GRID = [(_cx + dx, _cy + dy) for dy in (1.35, 0.45, -0.45, -1.35) for dx in (-1.05, 1.05)]   # a channel down the middle
_dec = [('VCC_CORE', '+3V3'), ('VCC_CORE', '+3V3'), ('VCC_CORE', '+3V3'), ('VDDAQ', 'VDDHAQ'), ('V1P2', None)]
_dec = ['VCC_CORE', '+3V3', 'VCC_CORE', '+3V3', 'VDDAQ', 'VDDHAQ', 'V1P2']
for i, net in enumerate(_dec):
    part(f'C{50 + i}', 'Device:C_Small', '100nF', C0201, {1: net, 2: 'GND'}, _GRID[i], side='B')
part('R5', 'Device:R_Small', '4.7k', R0201, {1: '+3V3', 2: 'FPGA_READY'}, _GRID[7], side='B')
part('R6', 'Device:R_Small', '4.7k', R0201, {1: '+3V3', 2: 'F_CS_N'}, (18.9, -5.0), side='B')
part('C59', 'Device:C_Small', '100nF', C0201, {1: 'VDDTQ', 2: 'GND'}, (14.3, 4.95), side='B')

# JTAG pads (TCK TMS TDI TDO), underneath at the front
for i, (net, xy) in enumerate([('JTAG_TCK', (56.9, 3.15)), ('JTAG_TMS', (56.9, 1.05)),
                               ('JTAG_TDI', (56.9, -1.05)), ('JTAG_TDO', (56.9, -3.15))]):
    part(f'TP{10 + i}', 'Connector:TestPoint', net, TP, {1: net}, xy, side='B')

# ---------------------------------------------------------------- PHY
PHY_AT = (31.0, 0.0)
PHY = {1: None, 2: 'COL', 3: 'TXD3', 4: 'TXD2', 5: 'TXD1', 6: 'TXD0', 7: 'TXEN', 8: '+3V3',
       9: None, 10: 'PHY_RST_N', 11: 'GND', 12: 'TXCLK', 13: 'MDC', 14: 'MDIO', 15: 'CRS', 16: 'RXD0',
       17: 'RXCLK', 18: '+3V3', 19: 'RXD1', 20: 'RXDV', 21: 'RXER', 22: 'PHY_INT_N', 23: 'RXD2',
       24: 'RXD3', 25: '+3V3', 26: 'RBIAS', 27: 'XTI', 28: 'XTO', 29: '+3V3', 30: 'TRXP', 31: 'TRXN',
       32: 'GND', 33: 'GND'}
part('U5', 'sfp:LAN8670', 'LAN8670C2-E/LMX', 'Package_DFN_QFN:VQFN-32-1EP_5x5mm_P0.5mm_EP3.1x3.1mm', PHY, PHY_AT,
     mpn='LAN8670C2-E/LMX')
# straps (DS 3.5, no internal resistors): MII + crystal = MODE 01, PHY address 0
for ref, net, up, at in (('R10', 'RXD2', True, (34.6, 1.95)), ('R11', 'RXD3', False, (34.6, 0.45)),
                         ('R14', 'RXD1', False, (34.6, -1.05)), ('R15', 'RXDV', False, (34.6, -2.55)),
                         ('R16', 'RXER', False, (34.6, -4.05)), ('R12', 'CRS', False, (35.5, -2.25)),
                         ('R13', 'RXD0', False, (35.5, -3.75)), ('R17', 'TXEN', False, (28.6, -3.9))):
    part(ref, 'Device:R_Small', '10k', R0201, {1: '+3V3' if up else 'GND', 2: net}, at, side='B', rot=90)
part('R18', 'Device:R_Small', '10k', R0201, {1: '+3V3', 2: 'MDIO'}, (35.5, 2.25), side='B', rot=90)
part('R19', 'Device:R_Small', '10k', R0201, {1: '+3V3', 2: 'PHY_INT_N'}, (35.5, 0.75), side='B', rot=90)
part('R20', 'Device:R_Small', '10k', R0201, {1: '+3V3', 2: 'PHY_RST_N'}, (35.5, -0.75), side='B', rot=90)
part('R21', 'Device:R_Small', '12.4k 1%', R0402, {1: 'RBIAS', 2: 'GND'}, (28.1, 4.2), side='B', rot=90)
part('Y1', 'Device:Crystal_GND24_Small', '25MHz CL12pF 2016', 'Crystal:Crystal_SMD_2016-4Pin_2.0x1.6mm',
     {1: 'XTI', 2: 'GND', 3: 'XTO', 4: 'GND'}, (31.4, 4.0), side='B')
part('C30', 'Device:C_Small', '18pF', C0201, {1: 'XTI', 2: 'GND'}, (29.4, 4.0), side='B', rot=90)
part('C31', 'Device:C_Small', '18pF', C0201, {1: 'XTO', 2: 'GND'}, (33.5, 4.0), side='B', rot=90)
for i, (at, r) in enumerate((((29.7, 2.3), 0), ((32.3, 2.3), 0), ((30.2, -1.45), 0), ((35.5, 3.75), 90))):
    part(f'C{32 + i}', 'Device:C_Small', '100nF', C0201, {1: '+3V3', 2: 'GND'}, at, side='B', rot=r)
part('C36A', 'Device:C_Small', '10uF', C0603, {1: '+3V3', 2: 'GND'}, (31.0, -4.6), side='B')

# MDI / BIN (AN1718 figure 1-3): 100 nF series caps, CMC, end-node termination
part('C40', 'Device:C_Small', '100nF 100V', C0805, {1: 'TRXP', 2: 'MDI_CP'}, (37.2, 4.3))
part('C41', 'Device:C_Small', '100nF 100V', C0805, {1: 'TRXN', 2: 'MDI_CN'}, (37.2, 2.3))
part('L2', 'Device:L_Coupled_1423', 'ACT1210E-241-2P', 'sfp:L_CommonMode_3225',
     {1: 'MDI_CP', 4: 'MDI_P', 2: 'MDI_CN', 3: 'MDI_N'}, (41.1, 3.3), mpn='ACT1210E-241-2P-TL00')
part('R22', 'Device:R_Small', '49.9 1%', R1206, {1: 'MDI_P', 2: 'MDI_TERM'}, (45.5, 4.1))
part('R23', 'Device:R_Small', '49.9 1%', R1206, {1: 'MDI_N', 2: 'MDI_TERM'}, (45.5, 1.85))
part('C42', 'Device:C_Small', '100nF 50V', C0805, {1: 'MDI_TERM', 2: 'GND'}, (45.5, -1.2))
part('R24', 'Device:R_Small', '100k', R0805, {1: 'MDI_TERM', 2: 'GND'}, (45.5, -3.4))
part('J2', 'Connector_Generic:Conn_01x02', 'S2B-PH-K-S', 'Connector_JST:JST_PH_S2B-PH-K_1x02_P2.00mm_Horizontal',
     {1: 'MDI_P', 2: 'MDI_N'}, (51.6, 1.0), rot=90, mpn='S2B-PH-K-S(LF)(SN)')

# ---------------------------------------------------------------- MCU
MCU = {1: 'SDA', 2: None, 3: None, 4: '+3V3', 5: 'GND', 6: 'NRST', 7: 'MDC', 8: 'MDIO',
       9: 'PHY_RST_N', 10: 'PHY_INT_N', 11: 'TX_DISABLE', 12: 'RX_LOS', 13: 'TX_FAULT',
       14: 'FPGA_LINK', 15: 'FPGA_RECONFIG_N', 16: 'FPGA_DONE', 17: None, 18: 'SWDIO', 19: 'SWCLK', 20: 'SCL'}
part('U8', 'MCU_ST_STM32G0:STM32G031F_4-6-8_Px', 'STM32G031F6P6', 'Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm', MCU,
     (39.6, 0.0), side='B', rot=90, mpn='STM32G031F6P6')
part('C43', 'Device:C_Small', '100nF', C0402, {1: '+3V3', 2: 'GND'}, (37.6, 4.7), side='B')
part('C44', 'Device:C_Small', '1uF', C0402, {1: '+3V3', 2: 'GND'}, (39.6, 4.7), side='B')
part('C45', 'Device:C_Small', '100nF', C0402, {1: 'NRST', 2: 'GND'}, (41.6, 4.7), side='B')
part('R25', 'Device:R_Small', '10k', R0402, {1: '+3V3', 2: 'TX_DISABLE'}, (39.6, -4.7), side='B')
for i, (net, xy) in enumerate([('+3V3', (54.8, 4.2)), ('SWDIO', (54.8, 2.1)), ('SWCLK', (54.8, 0.0)),
                               ('NRST', (54.8, -2.1)), ('GND', (54.8, -4.2))]):
    part(f'TP{i + 1}', 'Connector:TestPoint', net, TP, {1: net}, xy, side='B')

# LCSC part numbers, JLC API 2026-09-30
LCSC_BY_MPN = {
    'GW5AT-LV15MG132C1/I0': 'C54067362', 'LAN8670C2-E/LMX': 'C20901523',
    'OB2EL89CLIB112YLC-125M': 'C7425465', 'GD25Q64CWIGR': 'C395511',
    'TPS62822DLCR': 'C473385', 'DFE201610E-R47M': 'C269773', 'TLV75518PDBVR': 'C2877863',
    'TLV75512PDBVR': 'C2877864', 'TPS22918DBVR': 'C131941', 'BLM18KG601SH1': 'C710379',
    'STM32G031F6P6': 'C529333', 'ACT1210E-241-2P-TL00': 'C6114822', 'S2B-PH-K-S(LF)(SN)': 'C173752',
}
LCSC_BY_VALUE = {
    ('100nF', C0201): 'C76928', ('100nF', C0402): 'C1525', ('1uF', C0402): 'C52923',
    ('4.7uF', C0402): 'C23733', ('10uF', C0603): 'C19702', ('2.2nF', C0402): 'C106861',
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
         ('6', 'TXD0', 'input'), ('7', 'TXEN', 'input'), ('11', 'TXER', 'input'), ('12', 'TXCLK', 'output'),
         ('', '', ''), ('17', 'RXCLK', 'output'), ('16', 'RXD0/PHYAD2', 'bidirectional'),
         ('19', 'RXD1/PHYAD3', 'bidirectional'), ('23', 'RXD2/MODE0', 'bidirectional'),
         ('24', 'RXD3/MODE1', 'bidirectional'), ('20', 'RXDV/PHYAD1', 'bidirectional'),
         ('21', 'RXER/PHYAD0', 'bidirectional'), ('15', 'CRS/PHYAD4', 'bidirectional'),
         ('', '', ''), ('13', 'MDC', 'input'), ('14', 'MDIO', 'bidirectional'),
         ('10', 'RESET_N', 'input'), ('22', 'IRQ_N', 'open_collector')]
    R = [('8', 'VDDP', 'power_in'), ('18', 'VDDP', 'power_in'), ('25', 'VDDA', 'power_in'),
         ('29', 'VDDA', 'power_in'), ('', '', ''), ('30', 'TRXP', 'bidirectional'), ('31', 'TRXN', 'bidirectional'),
         ('', '', ''), ('27', 'XTI', 'input'), ('28', 'XTO', 'output'), ('26', 'RBIAS', 'passive'),
         ('', '', ''), ('1', 'DNC', 'no_connect'), ('9', 'DNC', 'no_connect'),
         ('32', 'VSS', 'power_in'), ('33', 'EP', 'power_in')]
    return ('LAN8670', 'U', L, R, 25.4)


def _osc_symbol():
    return ('OSC_LVDS', 'X', [('6', 'VDD', 'power_in'), ('1', 'OE', 'input'), ('2', 'NC', 'no_connect'),
                              ('3', 'GND', 'power_in')],
            [('4', 'OUT+', 'output'), ('5', 'OUT-', 'output')], 15.24)


SYMBOLS = [_fpga_symbol(), _phy_symbol(), _osc_symbol(), sfpgen.TPS22918]
SOLID_PADS = {('U5', '33')}


def FOOTPRINTS(io, smd, crt, tht, slot, npth):
    import pcbnew
    MB = sfpgen.MB
    # Gowin MBGA-132, 8 x 8 mm, 0.5 mm pitch, 14 x 14 grid, outer three rings:
    # 0.3 mm NSMD pads (0.25 ball land + 0.05; a filled via fits inside)
    fp = pcbnew.FOOTPRINT(None)
    fp.SetFPID(pcbnew.LIB_ID('sfp', 'Gowin_MBGA-132_8x8mm_P0.5mm'))
    for b in BALLS:
        r, c = ROWS.index(b['ball'][0]), int(b['ball'][1:])
        p = pcbnew.PAD(fp)
        p.SetNumber(b['ball'])
        p.SetShape(pcbnew.PAD_SHAPE_CIRCLE)
        p.SetAttribute(pcbnew.PAD_ATTRIB_SMD)
        p.SetLayerSet(p.SMDMask())
        p.SetSize(pcbnew.VECTOR2I(MB.MM(0.3), MB.MM(0.3)))
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
MIN_VIA = (0.3, 0.15)            # the via-in-pad under the BGA
# via hole to copper: a line out between two ball vias passes their holes at
# 0.229 mm; 0.2 is inside JLC's multilayer BGA fan-out rules (check the DFM)
HOLE_CLEARANCE = 0.2
# inner layers: In1 / In4 GND (sfpgen), In2 the core rail, In3 +3V3 - whole
# planes, so the router leaves these nets to them (every pad gets a via)
PLANES = [('In3.Cu', '+3V3')]
# In2 routes signals, with the core rail as an island under the FPGA and the buck
# only as tall as the ball ring: In2 keeps a corridor along each long edge for
# the lines leaving the FPGA's left side, and stays free under the flash
IN2_ISLANDS = [('VCC_CORE', (10.9, -3.6, 18.8, 3.6)), ('VCC_CORE', (18.8, 0.4, 26.0, 3.6))]
PLANE_DOGBONE = ('VCC_CORE', '+3V3')
DP_W, DP_PITCH = 0.114, 0.266
COURTYARD_OK = {}
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

# SGMII RX (host TD -> FPGA lane 0 RX), on top: from the caps up above row A
# and east, the lower line (TD+, C3's) down into A1 (RXM), the upper into A2
_a1, _a2 = ball_xy('A1'), ball_xy('A2')
PREROUTES += _pair('SRX_P', 'SRX_M', 'F', [(5.52, 3.0), (5.9, 3.0)], [(5.52, 2.2), (5.9, 2.2)],
                   [(6.4, 2.6), (6.8, 2.6), (8.15, 3.95), (_a1[0] - 0.2, 3.95)],
                   [(_a2[0], 3.95 + 0.133), (_a2[0], _a2[1])], [(_a1[0], 3.95 - 0.133), (_a1[0], _a1[1])])
# refclk: A7/A8 up above row A, east to the caps and the oscillator's outputs
_a7, _a8 = ball_xy('A7'), ball_xy('A8')
PREROUTES += [('REFCLK_M', 'F', [_a7, (_a7[0], 4.4), (19.6, 4.4), (19.75, 4.55), (19.98, 4.55)], DP_W),
              ('REFCLK_P', 'F', [_a8, (_a8[0], 3.8), (19.6, 3.8), (19.7, 3.7), (19.98, 3.7)], DP_W),
              ('OSC_P', 'F', [(20.62, 4.55), (21.8, 4.55)], DP_W),
              ('OSC_N', 'F', [(20.62, 3.7), (21.3, 3.7), (21.45, 3.55), (21.8, 3.55)], DP_W)]
# SGMII TX (FPGA -> host RD), underneath: out of B3 / C3's vias between their
# neighbours' vias, then west and down to the caps at the fingers
_b3, _c3 = ball_xy('B3'), ball_xy('C3')
PREROUTES += [('STX_P', 'B', [_b3, (_b3[0] - 0.5, _b3[1] + 0.5)], 0.1),     # 0.1 between the ball vias
              ('STX_M', 'B', [_c3, (_c3[0] - 0.5, _c3[1] - 0.5)], 0.1),
              # then coupled: down the front of the FPGA (P west, M east), a staggered
              # 45 degree turn, west to the caps, splitting into a via each
              ('STX_P', 'B', [(_b3[0] - 0.5, _b3[1] + 0.5), (_b3[0] - 0.5, 3.55), (10.6, 3.55), (9.6, 2.55),
                              (9.6, -1.667), (9.2, -2.067), (6.9, -2.067), (6.633, -1.8), (6.2, -1.8)], DP_W),
              ('STX_M', 'B', [(_c3[0] - 0.5, _c3[1] - 0.5), (11.4, 1.75), (10.3, 1.75), (9.866, 1.316),
                              (9.866, -1.8), (9.333, -2.333), (6.9, -2.333), (6.633, -2.6), (6.2, -2.6)], DP_W),
              ('STX_P', 'F', [(6.2, -1.8), (5.52, -1.8)], DP_W),
              ('STX_M', 'F', [(6.2, -2.6), (5.52, -2.6)], DP_W)]
PREVIAS += [('STX_P', (6.2, -1.8)), ('STX_M', (6.2, -2.6)), ('GND', (7.0, -1.0)), ('GND', (7.0, -3.3))]

# MII, on top. TX: the FPGA's right column straight across to the PHY's left
# side, each line one pitch down on the way. RX: the bottom row down into
# seven lanes along the bottom edge, to the PHY's bottom pins and round its
# corner up to its right side; TXCLK above them to pin 12. The PHY pins the
# lanes pass (right side 18/21/22, bottom 10/11/13/14) take a via in the pad.
_MW = 0.1                       # 0.25 mm pitch lanes: 0.1 lines, 0.15 gaps
_px = lambda pin: [p for p in _PHY_PADS if p[0] == pin][0][1:]
_PHY_PADS = [(k, round(PHY_AT[0] - 2.438, 3), round(1.75 - 0.5 * (k - 1), 3)) for k in range(1, 9)] + \
            [(k, round(PHY_AT[0] - 1.75 + 0.5 * (k - 9), 3), -2.438) for k in range(9, 17)] + \
            [(k, round(PHY_AT[0] + 2.438, 3), round(-1.75 + 0.5 * (k - 17), 3)) for k in range(17, 25)]
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
# left side: JTAG, DONE, RECONFIG out to x 11.55, the router takes them on
PREROUTES += [('JTAG_TCK', 'B', [_bxy('G2'), (11.55, _bxy('G2')[1])], _BW),
              ('JTAG_TDO', 'B', [_bxy('J2'), (11.55, _bxy('J2')[1])], _BW),
              ('JTAG_TMS', 'B', [_bxy('G3'), _bxy('F2'), (11.55, _bxy('F2')[1])], _BW),
              ('JTAG_TDI', 'B', [_bxy('J3'), _bxy('K2'), (11.55, _bxy('K2')[1])], _BW),
              ('FPGA_DONE', 'B', [_bxy('L3'), _bxy('M2'), (11.55, _bxy('M2')[1])], _BW),
              ('FPGA_RECONFIG_N', 'B', [_bxy('M3'), _bxy('P3'), (13.0, -3.75), (11.55, -3.75)], _BW)]
# the flash (bank 2 corner): CS and MISO straight to its near column; CLK and
# MOSI down to In2 beside the ring, north past the flash's top, and back up
# on two lanes over it to its far column
_SV = MIN_VIA
PREROUTES += [('F_CS_N', 'B', [_bxy('L13'), _bxy('M14'), (19.85, -2.25), (19.85, -4.2), (20.155, -4.505), (20.9, -4.505)], _BW),
              ('F_MISO', 'B', [_bxy('K14'), (20.2, -1.25), (20.2, -2.95), (20.485, -3.235), (20.9, -3.235)], _BW),
              ('F_CLK', 'B', [_bxy('L14'), (19.45, -1.75)], _BW),
              ('F_MOSI', 'B', [_bxy('M13'), _bxy('N14'), (19.45, -2.75)], _BW),
              # under the flash on In2 (TXCLK runs down x 19.1 on top: the vias keep 0.15)
              ('F_CLK', 'In2', [(19.45, -1.75), (26.95, -1.75), (27.15, -1.95), (27.15, -1.965)], _BW),
              ('F_MOSI', 'In2', [(19.45, -2.75), (27.6, -2.75), (27.6, -1.6)], _BW),   # below the TX lines on top
              ('F_CLK', 'B', [(27.15, -1.965), (26.3, -1.965)], _BW),
              ('F_MOSI', 'B', [(27.6, -1.6), (27.0, -1.0), (26.705, -0.695), (26.3, -0.695)], _BW)]
PREVIAS += [('F_CLK', (19.45, -1.75), _SV), ('F_MOSI', (19.45, -2.75), _SV),
            ('F_CLK', (27.15, -1.965), _SV), ('F_MOSI', (27.6, -1.6), _SV)]

# the PHY's exposed pad: 2 x 2 thermal vias to the GND planes
PREVIAS += [('GND', (round(PHY_AT[0] + dx, 3), dy)) for dx in (-0.7, 0.7) for dy in (-0.7, 0.7)]

IN2_GND = False                   # this board's inner layers are set by PLANES


if __name__ == '__main__':
    sys.exit(sfpgen.run(sys.modules[__name__]))

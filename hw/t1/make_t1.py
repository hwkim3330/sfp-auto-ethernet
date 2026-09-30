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
import os
import sys

HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.dirname(HERE))
import sfpgen                            # noqa: E402
from sfpgen import (C0201, C0402, C0603, R0201, R0402, R0603, FB0603, LED0402,  # noqa: E402,F401
                    TP)

NAME = 't1'
TITLE = 'T1 SFP'
SCH_TITLE = 'SFP 100/1000BASE-T1 - DP83TG720S / DP83TC812S'

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

# host rails through a bead each, then a slew-limited load switch (design
# review): the host's filter brings 3.3 V up in tens of us on hot plug, and
# the MSA allows 30 mA of inrush over steady state. CT 2.2 nF -> ~3.6 ms
# rise (TPS22918 table 2), ~20 uF downstream charges at ~20 mA.
part('FB1', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'VCCT', 2: 'VIN_RAW'}, (8.9, 4.9), mpn='BLM18KG601SH1')
part('FB2', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: 'VCCR', 2: 'VIN_RAW'}, (8.9, -4.9), mpn='BLM18KG601SH1')
part('C1', 'Device:C_Small', '1uF', C0402, {1: 'VIN_RAW', 2: 'GND'}, (8.2, 3.4), side='B')
part('C2', 'Device:C_Small', '100nF', C0402, {1: 'VIN_RAW', 2: 'GND'}, (8.9, -3.2), side='B')
part('U4', 'sfp:TPS22918', 'TPS22918DBVR', 'Package_TO_SOT_SMD:SOT-23-6',
     {1: 'VIN_RAW', 2: 'GND', 3: 'VIN_RAW', 4: 'SS_CT', 5: '+3V3', 6: '+3V3'}, (11.8, 4.1), side='B', mpn='TPS22918DBVR')
part('C36', 'Device:C_Small', '2.2nF', C0402, {1: 'SS_CT', 2: 'GND'}, (14.8, 4.9), side='B')
part('C37', 'Device:C_Small', '10uF', C0603, {1: '+3V3', 2: 'GND'}, (11.9, 4.6))

# SGMII AC coupling, inside the module (MSA). TD = host -> module.
# Both lanes are wired straight, which inverts both: the PHY's SGMII pins come
# out mirrored against the SFP edge, and crossing each pair would cost it two
# vias on one line. The swap happens across these caps (TD+ -> TX_M ...), and
# the firmware sets SGMII_CTRL_1 (0x608) bits 7 and 8, tx/rx polarity invert,
# which both the DP83TG720 and the DP83TC812 have. Inverting both means it
# does not matter which lane TI calls "RX".
part('C3', 'Device:C_Small', '100nF', C0201, {1: 'TD_P', 2: 'SG_TX_N'}, (5.2, 2.2))
part('C4', 'Device:C_Small', '100nF', C0201, {1: 'TD_N', 2: 'SG_TX_P'}, (5.2, 3.0))
part('C5', 'Device:C_Small', '100nF', C0201, {1: 'RD_P', 2: 'SG_RX_N'}, (5.2, -1.8))
part('C6', 'Device:C_Small', '100nF', C0201, {1: 'RD_N', 2: 'SG_RX_P'}, (5.2, -2.6))

# ---------------------------------------------------------------- PHY
PHY = {1: 'MDC', 2: 'PHY_INT_N', 3: 'PHY_RST_N', 4: 'XO', 5: 'XI', 6: None,
       # 12/13 cross over on purpose: pin 12 (TRD_P) drives the line's M side. They
       # leave the package M-over-P and the CMC takes P-over-M; the PHY corrects
       # MDI polarity itself and that cannot be turned off (datasheet 6.4.7.2)
       7: 'VDDA', 8: None, 9: 'VDD1P0', 10: None, 11: 'VDDA', 12: 'TRD_M', 13: 'TRD_P',
       14: None, 15: None, 16: None, 17: None, 18: None, 19: None, 20: None,
       21: 'VDD1P0', 22: 'VDDIO', 23: 'SG_RX_N', 24: 'SG_RX_P', 25: None, 26: None,
       27: None, 28: None, 29: None, 30: None, 31: None, 32: 'SG_TX_P', 33: 'SG_TX_N',
       34: 'VDDIO', 35: 'LED0', 36: 'MDIO', 37: 'GND'}
# pin 7 VSLEEP tied to VDDA3P3 (sleep unused, Figure 8-3); pin 8 WAKE may float
part('U1', 'sfp:DP83TG720S', 'DP83TG720S-Q1 (or DP83TC812S-Q1)',
     'Package_DFN_QFN:QFN-36-1EP_6x6mm_P0.5mm_EP4.1x4.1mm_ThermalVias', PHY, (19.5, 0.0), rot=180,
     mpn='DP83TG720SWRHARQ1')

# supply islands, Figure 8-3 / Table 8-2
part('FB4', 'Device:FerriteBead_Small', 'BLM18KG601SH1', FB0603, {1: '+3V3', 2: 'VDDA'}, (14.9, 4.6), mpn='BLM18KG601SH1')
part('FB5', 'Device:FerriteBead_Small', 'BLM18HE102SN1', FB0603, {1: '+3V3', 2: 'VDDIO'}, (13.0, -4.6), side='B', mpn='BLM18HE102SN1')
part('FB3', 'Device:FerriteBead_Small', 'BLM18KG601SH1 (DNP for DP83TC812)', FB0603,
     {1: 'V1P0_BUCK', 2: 'VDD1P0'}, (24.6, -3.6), rot=90, mpn='BLM18KG601SH1')
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
     {1: 'XI', 2: 'GND', 3: 'XO', 4: 'GND'}, (25.4, -0.4), rot=180)   # 180: XI/XO face U1's pins 5/4 uncrossed
# load caps underneath: on top they closed the lane MDC/INT/RST take past the crystal
part('C24', 'Device:C_Small', '12pF', C0201, {1: 'XI', 2: 'GND'}, (26.3, -0.4), side='B', rot=90)
part('C25', 'Device:C_Small', '12pF', C0201, {1: 'XO', 2: 'GND'}, (24.1, -0.4), side='B', rot=90)

part('R1', 'Device:R_Small', '2.2k', R0201, {1: 'VDDIO', 2: 'MDIO'}, (25.6, -3.2), side='B', rot=90)
# LED_0 = link. Its path to ground is also the strap pull-down: MS = 0 (slave)
part('R2', 'Device:R_Small', '1k', R0402, {1: 'LED0', 2: 'LED0_K'}, (49.3, -3.2), side='B', rot=90)
part('D1', 'Device:LED_Small', 'green', LED0402, {1: 'GND', 2: 'LED0_K'}, (50.5, -3.2), side='B', rot=90)

# ---------------------------------------------------------------- 1.0 V buck
# in the middle, where the MCU used to be: at the fingers it sat across the
# SGMII corridor (design review)
BUCK = (30.0, 0.9)
part('U3', 'Regulator_Switching:TPS62823DLC', 'TPS62822DLC',   # base symbol; TPS62822 (2 A) because the 1 A TPS62821 is out of stock at LCSC - same package, pins, divider
     'sfp:Texas_VSON-HR-8_1.5x2mm_P0.5mm',
     {1: '+3V3', 2: 'BUCK_FB', 3: 'GND', 4: None, 5: 'GND', 6: 'BUCK_SW', 7: '+3V3', 8: None},
     BUCK, mpn='TPS62822DLCR')
part('L1', 'Device:L_Small', '470nH DFE201610E-R47M', 'Inductor_SMD:L_Murata_DFE201610P',
     {1: 'BUCK_SW', 2: 'V1P0_BUCK'}, (30.0, -1.9), mpn='DFE201610E-R47M')
part('C26', 'Device:C_Small', '4.7uF', C0402, {1: '+3V3', 2: 'GND'}, (32.5, 0.5), rot=90)
part('C27', 'Device:C_Small', '10uF', C0603, {1: 'V1P0_BUCK', 2: 'GND'}, (27.6, -1.9), rot=90)
part('C28', 'Device:C_Small', '10uF', C0603, {1: 'V1P0_BUCK', 2: 'GND'}, (32.4, -1.9), rot=90)
# divider on the FB (pin 2) side
part('R3', 'Device:R_Small', '66.5k 1%', R0201, {1: 'V1P0_BUCK', 2: 'BUCK_FB'}, (27.6, 0.3), rot=90)
part('C29', 'Device:C_Small', '120pF', C0201, {1: 'V1P0_BUCK', 2: 'BUCK_FB'}, (27.6, 1.7), rot=90)
part('R4', 'Device:R_Small', '100k 1%', R0201, {1: 'BUCK_FB', 2: 'GND'}, (27.6, 3.1), rot=90)

# ---------------------------------------------------------------- MCU
MCU = {1: 'SDA', 2: None, 3: None, 4: '+3V3', 5: 'GND', 6: 'NRST', 7: 'MDC', 8: 'MDIO',
       9: 'PHY_RST_N', 10: 'PHY_INT_N', 11: 'TX_DISABLE', 12: 'RX_LOS', 13: 'TX_FAULT',
       14: None, 15: None, 16: None, 17: None, 18: 'SWDIO', 19: 'SWCLK', 20: 'SCL'}
part('U2', 'MCU_ST_STM32G0:STM32G031F_4-6-8_Px',   # base symbol; value names the part
    
     'STM32G031F6P6', 'Package_SO:TSSOP-20_4.4x6.5mm_P0.65mm', MCU, (31.5, 0.0), side='B', rot=90,
     mpn='STM32G031F6P6')     # underneath: on top it sat between the PHY and the whole MDI chain
part('C30', 'Device:C_Small', '100nF', C0402, {1: '+3V3', 2: 'GND'}, (27.3, 2.6), side='B', rot=90)
part('C31', 'Device:C_Small', '1uF', C0402, {1: '+3V3', 2: 'GND'}, (27.3, -2.6), side='B', rot=90)
part('C32', 'Device:C_Small', '100nF', C0402, {1: 'NRST', 2: 'GND'}, (35.8, -2.6), side='B', rot=90)
# TX_DISABLE: 4.7..10k pull-up inside the module (INF-8074i)
part('R5', 'Device:R_Small', '10k', R0402, {1: '+3V3', 2: 'TX_DISABLE'}, (35.8, 2.6), side='B', rot=90)
for i, (net, xy) in enumerate([('+3V3', (37.6, 3.2)), ('SWDIO', (37.6, 1.1)), ('SWCLK', (37.6, -1.1)),
                               ('NRST', (37.6, -3.2)), ('GND', (44.0, -3.5))]):
    part(f'TP{i + 1}', 'Connector:TestPoint', net, TP, {1: net}, xy, side='B')

# ---------------------------------------------------------------- MDI, Figure 8-1 / Table 8-1
# one straight line along the top: U1 pins 13/12 -> DC block -> CMC -> CM
# termination -> H-MTD, P above N the whole way (design review: the pair
# was split over two layers before)
TRD_Y = 4.433                                   # pair centre along the top
part('C33', 'Device:C_Small', '100nF', C0402, {1: 'TRD_P', 2: 'DCB_P'}, (34.0, 2.3))
part('C34', 'Device:C_Small', '100nF', C0402, {1: 'TRD_M', 2: 'DCB_N'}, (34.0, 1.35))
# Murata DLW32MH101XT2 is the datasheet's CMC; land = the 3.2 x 2.5 TDK ACT1210
# class footprint, windings 1-4 and 2-3; at 0 degrees 1/2 face the caps, 4/3 the connector
part('L2', 'Device:L_Coupled_1423', 'DLW32MH101XT2', 'sfp:L_CommonMode_3225',
     {1: 'DCB_P', 4: 'MDI_P', 2: 'DCB_N', 3: 'MDI_N'}, (37.0, 1.25), mpn='DLW32MH101XT2')
# CM termination right after the CMC, where its pins keep the lines 1.1 mm
# apart: a tap's 0402 pad (0.62 tall) cannot sit on one line of a coupled
# pair without reaching the other. 1k from each line to a node, the node to
# ground through 4.7 nF || 100k (underneath). ESD (unfitted) likewise.
part('R6', 'Device:R_Small', '1k 1%', R0402, {1: 'MDI_P', 2: 'MDI_CT'}, (39.5, 2.28), rot=90)
part('R7', 'Device:R_Small', '1k 1%', R0402, {1: 'MDI_N', 2: 'MDI_CT'}, (39.5, 0.22), rot=270)
part('C35', 'Device:C_Small', '4.7nF', C0402, {1: 'MDI_CT', 2: 'GND'}, (40.6, 1.25), side='B', rot=90)
part('R8', 'Device:R_Small', '100k', R0402, {1: 'MDI_CT', 2: 'GND'}, (41.6, 1.25), side='B', rot=90)
part('D2', 'Device:D_TVS', 'ESD (DNP)', 'Diode_SMD:D_0402_1005Metric',
     {1: 'MDI_P', 2: 'GND'}, (40.6, 2.28), rot=90, dnp=True)
part('D3', 'Device:D_TVS', 'ESD (DNP)', 'Diode_SMD:D_0402_1005Metric',
     {1: 'MDI_N', 2: 'GND'}, (40.9, 0.22), rot=270, dnp=True)
part('J2', 'sfp:HMTD_1P', 'Rosenberger E6S20A-40MT5-Z (H-MTD, coding Z)', 'sfp:Rosenberger_HMTD_E6S20A_1P_RA',
     {1: 'MDI_P', 2: 'MDI_N', 3: 'GND'}, (54.0, 0.0), mpn='E6S20A-40MT5-Z')   # = HMTD_AT
# polarity of pins 1/2 is unverified - irrelevant: the PHY corrects MDI polarity itself (6.4.7.2)

# LCSC part numbers (JLC assembly). Checked against the LCSC / JLC parts API
# 2026-09-29; "ext" = extended part (loading fee), everything 0201 is extended.
LCSC_BY_MPN = {
    'DP83TG720SWRHARQ1': 'C2921292',   # only 3 in stock - see README (TC812 C3225813 has 18)
    'STM32G031F6P6': 'C529333', 'TPS62822DLCR': 'C473385', 'DFE201610E-R47M': 'C269773',
    'DLW32MH101XT2': 'C2935101', 'BLM18KG601SH1': 'C710379', 'BLM18HE102SN1': 'C85828',
    'TPS22918DBVR': 'C131941',
}
LCSC_BY_VALUE = {   # (value, footprint) -> C-number
    ('100nF', C0201): 'C76928', ('10nF', C0201): 'C285010', ('12pF', C0201): 'C50391',
    ('120pF', C0201): 'C161406', ('2.2uF', C0402): 'C12530', ('4.7uF', C0402): 'C23733',
    ('1uF', C0402): 'C52923', ('100nF', C0402): 'C1525', ('10uF', C0603): 'C19702',
    ('4.7nF', C0402): 'C1538', ('2.2k', R0201): 'C142018', ('66.5k 1%', R0201): 'C62193',
    ('100k 1%', R0201): 'C106224', ('1k', R0402): 'C11702', ('10k', R0402): 'C25744',
    ('1k 1%', R0603): 'C21190', ('1k 1%', R0402): 'C11702', ('2.2nF', C0402): 'C106861', ('100k', R0402): 'C25741', ('green', LED0402): 'C965793',
    ('25MHz CL8pF 2016', 'Crystal:Crystal_SMD_2016-4Pin_2.0x1.6mm'): 'C7301943',
}


def lcsc_for(p):
    if p['dnp'] or p['ref'].startswith('TP') or p['ref'] in ('J1', 'J2'):
        return ''                      # J2 (H-MTD) is hand-soldered: LCSC has none in stock
    return LCSC_BY_MPN.get(p['mpn']) or LCSC_BY_VALUE.get((p['value'], p['fp']), '')


LENGTH = 63.5      # H-MTD front ground row 9.5 from the edge -> 3.5 mm overhang;
                   # its body then starts at 45.1, past the cage front (44.3)



SHEET = '8a4b1f2e-6c7d-4e8f-9a0b-1c2d3e4f5061'
SCH_AT = {'J1': (40, 80), 'U1': (160, 110), 'U2': (160, 200), 'U3': (60, 190), 'J2': (330, 110),
          'Y1': (110, 60), 'L2': (270, 110)}
POWER_NETS = ('+3V3', 'VDDA', 'VDDIO', 'VDD1P0', 'V1P0_BUCK', 'VCCT', 'VCCR', 'VIN_RAW')

def _phy_symbol():
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
    return ('DP83TG720S', 'U', phy_l, phy_r, 25.4)


SYMBOLS = [_phy_symbol(), sfpgen.TPS22918]
SOLID_PADS = {('U1', '37'), ('J2', '3')}   # EP thermal vias, H-MTD shield pins

SGMII = ['TD_P', 'TD_N', 'RD_P', 'RD_N', 'SG_TX_P', 'SG_TX_N', 'SG_RX_P', 'SG_RX_N']
MDI = ['TRD_P', 'TRD_M', 'DCB_P', 'DCB_N', 'MDI_P', 'MDI_N']
PWR = ['+3V3', 'VDDA', 'VDDIO', 'VDD1P0', 'V1P0_BUCK', 'BUCK_SW', 'VCCT', 'VCCR', 'VIN_RAW']
# 4 layers: F signal / In1 GND / In2 GND / B signal, on JLC04101H-3313 (1.0 mm;
# L1-L2 and L3-L4 3313 prepreg 0.0994 mm, Dk 4.1). Every high-speed pair is
# laid by hand below as a coupled 100 ohm pair: 0.114 mm lines, 0.152 mm gap
# (Wadell: ~57 ohm each, ~102 ohm differential; JLC's SI9000 gives 50 ohm
# single-ended at 0.157). F and B both sit over a GND plane, so the one pair
# that changes layer (RX, to get under TX) keeps a GND return; ground vias
# stand next to its vias.
CLASS_LAYERS = {'SGMII': ['F.Cu', 'B.Cu'], 'MDI': ['F.Cu', 'B.Cu']}

NETCLASSES = [
    dict(name='Default', clearance=0.15, track_width=0.127, via_diameter=0.45, via_drill=0.25),
    dict(name='SGMII', clearance=0.15, track_width=0.157,   # 0.15: the 0201 AC caps' own pads are 0.18 apart
         via_diameter=0.45, via_drill=0.25,
         dp_width=0.114, dp_gap=0.152, nets=SGMII),
    dict(name='MDI', clearance=0.15, track_width=0.157,
         via_diameter=0.45, via_drill=0.25,
         dp_width=0.114, dp_gap=0.152, nets=MDI),
    # 0.2, not 0.3: a 0.3 trace cannot leave the buck's 0.24 mm VIN pad or a 0.5-pitch QFN pin;
    # 0.2 mm of 1 oz carries the 260 mA core rail easily and +3V3 has its own plane
    dict(name='Power', clearance=0.15, track_width=0.2, via_diameter=0.5, via_drill=0.3, nets=PWR),
]

DP_W, DP_PITCH = 0.114, 0.266                  # coupled pair: 0.114 lines, 0.152 gap

PAIRS = [('TD_P', 'TD_N'), ('SG_TX_P', 'SG_TX_N'), ('RD_P', 'RD_N'), ('SG_RX_P', 'SG_RX_N'),
         ('TRD_P', 'TRD_M'), ('DCB_P', 'DCB_N'), ('MDI_P', 'MDI_N')]

HMTD_AT = (54.0, 0.0)
# In2 is a second GND plane: every pair, on F or B, references GND (design review)
IN2_GND = True
# ...which also takes the MCU's slow lines (two routing layers left six of them
# open), except under the RX pair's bottom-side run, where it stays solid
IN2_SIGNALS = True
IN2_KEEPOUTS = [(5.8, -3.1, 15.9, 0.7)]

from sfpgen import pair_lines                    # noqa: E402


def _pair(p_net, n_net, layer, p_head, n_head, centre, p_tail, n_tail):
    """A hand-laid coupled pair: pad -> neck -> centreline offsets -> neck -> pad.
    P runs on the left of the direction of travel."""
    pl, nl = pair_lines(centre, DP_PITCH)
    return [(p_net, layer, p_head + pl + p_tail, DP_W), (n_net, layer, n_head + nl + n_tail, DP_W)]


# SGMII TX (host -> PHY), on top: from the caps east, down the left of U1 and
# under its bottom row into pins 32/33 (P = SG_TX_P = C4's line, the upper one)
PREROUTES = _pair('SG_TX_P', 'SG_TX_N', 'F', [(5.52, 3.0), (5.9, 3.0)], [(5.52, 2.2), (5.9, 2.2)],
                  [(6.4, 2.6), (13.2, 2.6), (13.6, 2.2), (13.6, -3.8), (14.0, -4.2), (19.35, -4.2),
                   (19.75, -3.8), (19.75, -3.6)],
                  [(19.5, -3.45), (19.5, -2.838)], [(20.0, -3.45), (20.0, -2.838)])
# SGMII RX (PHY -> host): under TX on the bottom, a via on each line at each
# end, ground vias beside them; N (C5's line) is the upper one
RX_VIAS = {'SG_RX_N': [(6.2, -1.8), (14.467, 0.2)], 'SG_RX_P': [(6.2, -2.6), (15.25, -0.9)]}
PREROUTES += [('SG_RX_N', 'F', [(5.52, -1.8), (6.2, -1.8)], DP_W), ('SG_RX_P', 'F', [(5.52, -2.6), (6.2, -2.6)], DP_W)]
PREROUTES += _pair('SG_RX_N', 'SG_RX_P', 'B', [(6.2, -1.8)], [(6.2, -2.6)],
                   [(6.9, -2.2), (14.2, -2.2), (14.6, -1.8), (14.6, -1.3)],
                   [(14.467, 0.2)], [(15.25, -0.9)])
PREROUTES += [('SG_RX_N', 'F', [(14.467, 0.2), (14.8, 0.0), (16.662, 0.0)], DP_W),
              ('SG_RX_P', 'F', [(15.25, -0.9), (15.65, -0.5), (16.662, -0.5)], DP_W)]
# MDI, all on top: U1 pins 13 (P) / 12 (M) up, east along the edge, down past
# the buck into the DC block, the CMC, the taps while its pins keep the lines
# apart, then coupled again into the H-MTD
PREROUTES += _pair('TRD_P', 'TRD_M', 'F', [(20.0, 2.838), (20.0, 3.4)], [(20.5, 2.838), (20.5, 3.4)],
                   [(20.25, 3.5), (20.25, TRD_Y - 0.4), (20.65, TRD_Y), (29.9, TRD_Y),
                    (29.9 + TRD_Y - 1.825, 1.825), (32.7, 1.825)],
                   [(33.05, 2.3), (33.52, 2.3)], [(33.05, 1.35), (33.52, 1.35)])
PREROUTES += [('DCB_P', 'F', [(34.48, 2.3), (35.2, 1.8), (35.8, 1.8)], DP_W),
              ('DCB_N', 'F', [(34.48, 1.35), (35.2, 0.7), (35.8, 0.7)], DP_W)]
PREROUTES += _pair('MDI_P', 'MDI_N', 'F', [(38.2, 1.8), (41.0, 1.8)], [(38.2, 0.7), (41.0, 0.7)],
                   [(41.4, 1.25), (41.8, 1.25), (43.05, 0.0), (49.6, 0.0)],
                   [(50.467, 1.0), (52.13, 1.0)], [(50.467, -1.0), (52.13, -1.0)])
# termination centre node: R6/R7's far ends down to a trace underneath, where
# the 4.7 nF and 100k sit
PREROUTES += [('MDI_CT', 'F', [(39.5, 2.76), (39.5, 3.55)]),
              ('MDI_CT', 'F', [(39.5, -0.26), (39.5, -1.05)]),
              ('MDI_CT', 'B', [(39.5, 3.55), (39.5, -1.05)]),
              ('MDI_CT', 'B', [(39.5, 1.73), (41.6, 1.73)])]
PREVIAS = [(n, xy) for n, vs in RX_VIAS.items() for xy in vs]
PREVIAS += [('GND', (7.0, -1.1)), ('GND', (7.0, -3.3)), ('GND', (14.9, 0.9)),
            ('MDI_CT', (39.5, 3.55)), ('MDI_CT', (39.5, -1.05))]
# U3's EN (pin 1) to VIN (pin 7): diagonal across the package with the
# no-connect PG (pin 8) between; the router will not go round it, so under it
_bx, _by = BUCK
PREROUTES += [('+3V3', 'F', [(_bx - 0.725, _by + 0.75), (_bx - 1.55, _by + 0.75)]),
              ('+3V3', 'F', [(_bx + 0.725, _by + 0.25), (_bx + 1.55, _by + 0.25)]),
              ('+3V3', 'B', [(_bx - 1.55, _by + 0.75), (_bx + 1.55, _by + 0.25)])]
PREVIAS += [('+3V3', (_bx - 1.55, _by + 0.75)), ('+3V3', (_bx + 1.55, _by + 0.25))]
# its ground pins (AGND 3, PGND 5) each straight out to a via: boxed in by the
# EN/VIN bridge above, the pour never reached AGND
PREROUTES += [('GND', 'F', [(_bx - 0.725, _by - 0.25), (_bx - 1.55, _by - 0.25)]),
              ('GND', 'F', [(_bx + 0.725, _by - 0.75), (_bx + 1.55, _by - 0.75)])]
PREVIAS += [('GND', (_bx - 1.55, _by - 0.25)), ('GND', (_bx + 1.55, _by - 0.75))]
# short links the router left open on one run or another, laid here:
# U4's ON (pin 3) round its GND pin to VIN (pin 1), underneath
PREROUTES += [('VIN_RAW', 'B', [(10.662, 5.05), (9.7, 5.05), (9.7, 3.15), (10.662, 3.15)])]
# MDC (U1 pin 1) straight to a via for the MCU underneath
PREROUTES += [('MDC', 'F', [(22.338, -2.0), (22.95, -2.0), (23.4, -2.45), (23.4, -2.95)])]
PREVIAS += [('MDC', (23.4, -2.95))]
# VDD1P0 at U1 pin 21: left of the decap column underneath, then to C19
PREROUTES += [('VDD1P0', 'F', [(16.662, 1.0), (16.05, 1.0), (15.2, 1.95)]),
              ('VDD1P0', 'B', [(15.2, 1.95), (15.98, 2.2)])]
PREVIAS += [('VDD1P0', (15.2, 1.95))]
# the MCU's GND (pin 5, underneath) sits in a pour island the TRD pair crosses
# above, so no stitching via lands there: a stub out to a via past the pair
PREROUTES += [('GND', 'B', [(31.175, 3.2), (31.175, 3.95), (31.6, 4.4), (33.0, 4.4)])]
PREVIAS += [('GND', (33.0, 4.4))]
PREROUTES += [
             # C10/C16 under U1's VDDA/VDD1P0 pins: the router rings their ground pads
             # with those rails, so they share one via between them, laid first
             ('GND', 'B', [(23.02, 1.2), (23.45, 1.7), (23.02, 2.2)]),
             # the pin 11/21 decap row: ground pads face U1's bottom EP pad, and
             # the router's rails cut the pour between them, so each gets a spoke
             ('GND', 'B', [(19.2, 2.92), (19.2, 1.0)]), ('GND', 'B', [(20.4, 2.88), (20.4, 1.0)]),
             ('GND', 'B', [(21.4, 2.88), (20.7, 1.0)]), ('GND', 'B', [(17.6, 2.88), (18.4, 1.0)]),
             ('GND', 'B', [(16.62, 2.2), (18.35, 0.6)])]
PREVIAS += [('GND', (23.45, 1.7))]
# XO: U1 pin 4 to the crystal on top, and a via under it to the load cap
# underneath (the router left C25 stranded once the 0.6 edge strip went in)
PREROUTES += [('XO', 'F', [(22.338, -0.5), (23.2, -0.5), (23.65, -0.95), (24.7, -0.95)]),
              ('XO', 'B', [(23.2, -0.5), (23.62, -0.08), (24.1, -0.08)])]
PREVIAS += [('XO', (23.2, -0.5))]
# INT and RST share MDC's lane past the crystal: an escape via each, staggered
# south-east of their pins, so the router only has to take them on underneath
PREROUTES += [('PHY_INT_N', 'F', [(22.338, -1.5), (22.9, -1.5), (23.35, -1.95), (25.4, -1.95)]),   # between Y1 and FB3
              ('PHY_RST_N', 'F', [(22.338, -1.0), (22.9, -1.0), (23.4, -1.5), (23.85, -1.5)])]
PREVIAS += [('PHY_INT_N', (25.4, -1.95)), ('PHY_RST_N', (23.85, -1.5))]
# the crystal's load caps sit right under its lanes to U1: a ground via there
# closes XO off (it did). The bottom pour takes their ground instead.
NO_DOGBONE = ('C24', 'C25', 'C21', 'C7', 'C8', 'C9', 'C19', 'C20')   # C21's sat on VDDIO's only way to U1 pin 34


if __name__ == '__main__':
    sys.exit(sfpgen.run(sys.modules[__name__]))

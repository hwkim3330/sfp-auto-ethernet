# T1S SFP: 10BASE-T1S

No 10BASE-T1S PHY speaks SGMII (they are all MII/RMII or SPI MAC-PHYs; see [../../docs/PARTS.md](../../docs/PARTS.md)).
So an FPGA sits between the two:
- the host's SGMII on a hard transceiver lane;
- our own PCS, ×100 rate adaptation, frame FIFOs and half-duplex MAC in fabric ([gw/](gw/));
- MII to a Microchip LAN8670.

**This is the board with the most unverified pieces.** See [What is not verified](#what-is-not-verified).

Schematic, 6-layer PCB (routed), fab outputs and a JLC panel are in place; the order sheet is [ORDER.md](ORDER.md). Nothing has been built.

**Re-laid 2026-10-08 on the corrected SFP edge** (SFF-8419 figure 7-2; until then the fingers were drawn mirrored, which would have put VccT on a ground contact). Do not order before the Gowin transceiver IP, synthesis and timing exist (below).

| Top | Bottom |
|---|---|
| ![](fab/t1s-top.png) | ![](fab/t1s-bottom.png) |

## Status

| | Result | How it was checked |
|---|---|---|
| Schematic | **ERC 0 errors** ([erc.rpt](erc.rpt)); 2 warnings, both "symbol differs from the library copy" (the two LDOs) | eeschema's own ERC (`run_erc.sh`) |
| Placement | 92 parts, no overlaps; housing height limits met | `make_t1s.py` |
| SFP edge | **all 20 fingers where SFF-8419 figure 7-2 puts them, with the right nets** | `tools/compliance.py` (positions written out independently of the generator) |
| Routing | **DRC 0 violations, 0 unconnected** ([drc.rpt](drc.rpt)) | hand-laid pairs, escapes and In2 buses, Freerouting 1.9.0 for the rest ([t1s.ses](t1s.ses), rebuilt with `--reuse-ses`), then KiCad DRC |
| KiCad 9 | **DRC 0 errors, 0 unconnected, schematic parity clean, ERC 0 errors** ([kicad9-drc.rpt](kicad9-drc.rpt), [kicad9-erc.rpt](kicad9-erc.rpt)) | `sh ../check_kicad9.sh t1s`. Only warnings are "differs from the library copy" |
| Fab | Gerbers + drill ([fab/t1s-gerbers.zip](fab/t1s-gerbers.zip)), [BOM](fab/t1s-bom.csv), [CPL](fab/t1s-cpl.csv), [1:1 print](fab/t1s-1to1.pdf) | `export_t1s.py` |
| Panel | 5 boards, 70.1 × 81.1 mm, **DRC 0 errors, 0 unconnected** with the board's rules ([jlc/panel-drc.rpt](jlc/panel-drc.rpt)) | `panel_t1s.py` (KiKit) |
| Gateware | `tb_bridge`, `tb_top` pass (`tb_top` with both lanes straight; an RX-inverting instance must fail) | Icarus Verilog, CI |
| Firmware | builds, 0 warnings | `make VARIANT=t1s`, CI |

## Parts

| | Part | LCSC | Why |
|---|---|---|---|
| FPGA | Gowin **GW5AT-LV15MG132C1/I0** | C54067362 | The only FPGA with real transceivers that fits the width (8 × 8 mm) and is in JLC stock |
| PHY | Microchip **LAN8670C2-E/LMX** | C20901523 | MII + PLCA, 5 × 5 VQFN (B1/C1 variants have no stock) |
| Reference | YXC OB2EL89CLIB112YLC-125M, 125 MHz LVDS 3225 | C7425465 | As the Gowin kit: LVDS, AC coupled at the FPGA |
| Configuration | GD25Q128EWIGR, 128 Mbit SPI NOR, WSON-8 6 × 5 | C2982923 | 128 Mbit so Gowin's default golden (retry) address 0x800000 is inside the part: main image at 0x000000, golden at 0x800000 |
| Core 0.946 V | TPS62822 buck | C473385 | Same circuit as the RJ45 board (57.6k / 100k) |
| 1.8 V, 1.2 V | TLV75518 / TLV75512, SOT-23-5 | C2877863 / C2877864 | VDDHAQ0; VDD12M + VCCLDO |
| MDI | ACT1210E-241 CMC, 2 × 100 nF 100 V, 49.9 Ω end-node termination | C6114822 … | Microchip AN1718 "BIN" |
| Connector | JST PH S2B-PH-K-S, 2 pins, right angle | C173752 | Wire to board, outside the cage |
| MCU | STM32G031F6P6 | C529333 | As the other boards: EEPROM, PHY bridge, TX_DISABLE / RX_LOS |

## Board

- 58.4 × 11.8 mm. The JST housing sits entirely past the cage front (44.3 mm).
- **Six layers:**

  | Layer | Use |
  |---|---|
  | F | FPGA balls, SGMII RX and the reference clock, MII, the beads, the MDI network, JTAG pads |
  | In1 | GND |
  | In2 | signals: the long buses (below), the ball field's escapes |
  | In3 | +3V3 plane |
  | In4 | GND, with the 0.95 V core as an island under the FPGA and the buck |
  | B | the TX pair, decaps, load switch, flash, buck, PHY straps, MCU, LDOs, test pads |

- **Why six:** 0.5 mm ball pitch leaves no room for a track between balls. So every used ball inside the outer ring has a **via in its pad** (0.25 / 0.15 mm in Gowin's 0.25 mm land, UG983 figure 4-8; filled and capped), and five supply rails sit interleaved around the ring. On six layers JLC fills and caps via-in-pad at no extra charge, and +3V3 and the core rail become planes the router doesn't have to route.
- **The core island is on In4, not In2.** On In2 it covered the ball field, so the small rails (VDDHAQ, V1P2) and the inner-ring signals had no way out. Under B only the field's stubs and decaps sit on it; the TX pair crosses it only on its last 0.75 mm into the balls.
- **Two In2 buses, laid by hand** (`IN2_BUS` in `make_t1s.py`; the long runs were found once by a maze search over the board before its dogbones went in, the west ends re-laid by hand in 2026-10). The slow fingers underneath read RX_LOS, SCL | SDA, TX_DISABLE, TX_FAULT from top to bottom, and the buses keep that order, so nothing crosses:
  - along the north edge, RX_LOS and SCL from the fingers to MCU pins 3 and 1;
  - along the south edge, from the ball field and the fingers to the MCU's bottom row, one lane each, stacked in the order the pins take them: V1P2 (to its LDO), RECONFIG_N, DONE, SDA above the pins' via row, FPGA_LINK, TX_DISABLE and TX_FAULT below it;
  - VDDHAQ leaves the ball field through row C and runs under the MCU to its LDO; MISO crosses over the flash.
  The MCU's pins follow the buses: I²C1 on PB8 (SCL, pin 1) and PA10 (SDA, pin 17, PA12's pad remapped), RX_LOS on PC15, TX_FAULT on PA4, TX_DISABLE on PA6 (`fw`, `VARIANT_T1S`).
- **Around the ball field:** JTAG leaves west on In2 to four pads on top beside the FPGA; the flash is turned 180° so CLK and MOSI reach it underneath; CRS, RXD0 and TXEN reach their straps through vias in the PHY's pads.
- **Configuration pins, from Gowin's pinout and UG720** (see [../../docs/REFERENCES.md](../../docs/REFERENCES.md)): CLKHOLD_N (K3) is pulled down during configuration and would hold the flash clock, so it is tied to +3V3; P1 doubles as SSPI_CS_N and is pulled up (R26) so the FPGA cannot select slave SPI after loading; MODE0 (N2) and MODE1 (N1) share one 4.7 kΩ pull-up (R1) for MSPI.
- **MDI network as AN1718 Rev D:** 100 nF 100 V series caps, 2 × 49.9 Ω end-node termination (0.75 W 1206, the closest stocked to AN1718's 1 W), 100 nF 100 V ‖ 100 kΩ to ground, ACT1210E-241 CMC; no copper under the CMC on any layer and no ground flood round the network on top.
- **SGMII pairs** (0.114 / 0.152 mm, coupled; [lengths.txt](lengths.txt)):
  - The fingers put TD (host → module) at the bottom of the tab and RD at the top, while all of lane 0's balls sit at the FPGA's top-left corner.
  - RX on F over In1: from its caps east, north up the ball field's west side (west of the JTAG pads), east above row A and down into A1 / A2. 13.8 / 13.0 mm, no vias.
  - TX on B over In4: out of B3 / C3's via-in-pads with 0.1 mm necks between the neighbouring ball vias, west to two vias by the RD caps, then on top to the caps. 8.5 / 8.0 mm, 2 / 2 vias, GND vias beside them.
- **Polarity: both lanes P to P, nothing inverted.** RX keeps its order by the way it turns. On TX, RD+ (pin 13) sits below RD− (pin 12), so the order has to turn over once: P stops at its via and M runs on underneath it to a via 1.2 mm further west; on top P's line then passes under M's via to the lower cap. No pair crosses itself. (Until 2026-10 the mirrored edge left RX inverted and the gateware undid it with `RX_INVERT`.) The reference clock is laid inverted so its two lines to the oscillator don't cross; for a clock that changes nothing.
- **LAN8670 land:** KiCad's VQFN-32 5 × 5 with a 3.5 × 3.5 exposed pad, the centre pad of Microchip's recommended land (package C04-500; EP 3.4 nominal). Symbol pin names follow DS60001573K (INH and GPIO0 left open, WAKE_IN on GND, as the datasheet says for unused pins).

## Regenerating

```bash
python3 make_t1s.py            # symbols, footprints, schematic, placed PCB
python3 make_t1s.py --route    # planes, dogbones, Freerouting, pours, repairs, DRC -> drc.rpt
sh ../check_kicad9.sh t1s      # the same board in KiCad 9
python3 export_t1s.py          # gerbers (6 copper layers), BOM, CPL, previews, 1:1 PDF
python3 panel_t1s.py           # 5-board panel + JLC files -> jlc/
```

## What is not verified

- **Hardware:** nothing has been built.
- **Gowin toolchain:**
  - The transceiver is Gowin's *Customized PHY* IP. It is generated in Gowin EDA with the settings in `gw/serdes_lane.v`, plus a small shim of ports. Neither exists yet.
  - Synthesis and timing have not been run.
- **Refclk choice:** 125 MHz for 1.25 Gb/s is the usual choice, but it has not been checked in Gowin's IP generator.
- **MIPI rails:** Gowin does not say whether they may stay unpowered, so they are powered (VDD12M 1.2 V, VDDAM on the core rail, VDDXM on 3.3 V).
- **Firmware** (`fw/`, `VARIANT=t1s`) builds but has never run: FPGA DONE / RECONFIG_N handling, the LAN8670's AN1699 set-up and PLCA over MDIO, RX_LOS from `FPGA_LINK` ([../../fw/README.md](../../fw/README.md)).
- **MDI polarity:** the pair leaves the PHY swapped (pins 30/31) so it does not cross itself on the way to its caps. 10BASE-T1S is DME coded, which is polarity-insensitive; check it on a real segment.
- **Fab limits:**
  - via-in-pad 0.15 mm drill, 0.25 mm pad (74 of them: the ball field, a few PHY pads);
  - 0.1 mm lines between ball vias;
  - 0.2 mm hole-to-copper.

  Confirm all three against JLC's 6-layer DFM before ordering.

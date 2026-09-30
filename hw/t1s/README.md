# T1S SFP: 10BASE-T1S

No 10BASE-T1S PHY speaks SGMII (they are all MII/RMII or SPI MAC-PHYs; see [../../docs/PARTS.md](../../docs/PARTS.md)).
So an FPGA sits between the two:
- the host's SGMII on a hard transceiver lane;
- our own PCS, ×100 rate adaptation, frame FIFOs and half-duplex MAC in fabric ([gw/](gw/));
- MII to a Microchip LAN8670.

**This is the board with the most unverified pieces.** See [What is not verified](#what-is-not-verified).

## Parts

| | Part | LCSC | Why |
|---|---|---|---|
| FPGA | Gowin **GW5AT-LV15MG132C1/I0** | C54067362 | The only FPGA with real transceivers that fits the width (8 × 8 mm) and is in JLC stock |
| PHY | Microchip **LAN8670C2-E/LMX** | C20901523 | MII + PLCA, 5 × 5 VQFN (B1/C1 variants have no stock) |
| Reference | YXC OB2EL89CLIB112YLC-125M, 125 MHz LVDS 3225 | C7425465 | As the Gowin kit: LVDS, AC coupled at the FPGA |
| Configuration | GD25Q64CWIGR, 64 Mbit SPI NOR, WSON-8 | C395511 | Gowin wants ≥ 64 Mbit (its retry image sits at 0x800000) |
| Core 0.946 V | TPS62822 buck | C473385 | Same circuit as the RJ45 board (57.6k / 100k) |
| 1.8 V, 1.2 V | TLV75518 / TLV75512, SOT-23-5 | C2877863 / C2877864 | VDDHAQ0; VDD12M + VCCLDO |
| MDI | ACT1210E-241 CMC, 2 × 100 nF 100 V, 49.9 Ω end-node termination | C6114822 … | Microchip AN1718 "BIN" |
| Connector | JST PH S2B-PH-K-S, 2 pins, right angle | C173752 | Wire to board, outside the cage |
| MCU | STM32G031F6P6 | C529333 | As the other boards: EEPROM, PHY bridge, TX_DISABLE / RX_LOS |

## Board

- 53.0 × 11.8 mm. The JST housing sits entirely past the cage front (44.3 mm).
- **Six layers:**

  | Layer | Use |
  |---|---|
  | F | FPGA balls, SGMII RX and the reference clock, MII, the MDI network |
  | In1 | GND |
  | In2 | signals, plus a 0.95 V core island under the FPGA and the buck |
  | In3 | +3V3 plane |
  | In4 | GND |
  | B | the TX pair, config/JTAG lines, decaps, flash, buck, PHY straps, MCU, LDOs, test pads |

- **Why six:** 0.5 mm ball pitch leaves no room for a track between balls. So every used ball inside the outer ring has a **via in its pad** (0.3 / 0.15 mm, filled and capped), and five supply rails sit interleaved around the ring. On six layers JLC fills and caps via-in-pad at no extra charge, and +3V3 and the core rail become planes the router doesn't have to route.
- **SGMII pairs** (0.114 / 0.152 mm, coupled):
  - RX on F over In1.
  - TX on B over In4. It leaves the ball field through its two via-in-pads, with 0.1 mm necks between the neighbouring ball vias.
- **Polarity:** both pairs are laid straight. That leaves RX inverted (TD+ lands on RXM), and the gateware inverts the words (`gw/t1s_top.v`, `RX_INVERT`; `tb_top` checks it). The reference clock is also inverted, so the two lanes to the oscillator don't cross. That changes nothing.

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
- **LAN8670 land:** the exposed pad uses KiCad's VQFN-32 5 × 5 land with a 3.1 mm EP. Check it against the LMX package drawing before ordering.
- **Firmware:** the MCU firmware for this variant still needs:
  - the LAN8670's PLCA setup over MDIO;
  - RX_LOS from `FPGA_LINK`;
  - FPGA reload through RECONFIG_N.
- **Fab limits:**
  - via-in-pad 0.15 mm drill;
  - 0.1 mm lines between ball vias;
  - 0.2 mm hole-to-copper.

  Confirm all three against JLC's 6-layer DFM before ordering.

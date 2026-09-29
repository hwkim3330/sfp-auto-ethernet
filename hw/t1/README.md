# T1 SFP: 100/1000BASE-T1

Schematic, PCB (4 layers, routed), fab outputs and firmware are all in place.
**Two things must still be settled before ordering**: see "Before ordering" below.

| Top | Bottom |
|---|---|
| ![](fab/t1-top.png) | ![](fab/t1-bottom.png) |

## Status

| | Result | How it was checked |
|---|---|---|
| Schematic | **ERC 0 errors, 0 warnings** ([erc.rpt](erc.rpt)) | eeschema's own ERC (`run_erc.sh`) |
| Schematic ↔ netlist | 175 pins, 0 mismatches | Netlist exported with `kicad-cli sch export netlist`, compared against the netlist in `make_t1.py` |
| Placement | 62 parts, no overlaps; housing height limits met | `make_t1.py` |
| Routing | **DRC 0 violations, 0 unconnected** ([drc.rpt](drc.rpt)) | Freerouting 1.9.0, then KiCad DRC |
| Fab | Gerbers + drill ([fab/t1-gerbers.zip](fab/t1-gerbers.zip)), [BOM](fab/t1-bom.csv), [CPL](fab/t1-cpl.csv) | `export_t1.py` |
| Firmware | Builds: 1.7 KB flash / 280 B RAM, 0 warnings ([../../fw](../../fw)) | `make` |

## Circuit (every block is from its datasheet)

- **PHY:** DP83TG720S-Q1 (1000BASE-T1).
  - The **DP83TC812S-Q1 (100BASE-T1) fits the same footprint**. For the 100 Mb loadout, leave **FB3** unfitted (the 1.0 V buck → pins 9/21 ferrite); the TC812 regulates pin 21 itself.
  - The straps are all left at their defaults: SGMII, PHY address 0, autonomous, slave. The module links up with no MCU at all.
- **SGMII:** SFP TD/RD → 100 nF AC coupling inside the module (as the MSA requires) → PHY TX_P/M (32/33) and RX_P/M (24/23).
- **MDI (Figure 8-1 / Table 8-1):** TRD → 100 nF DC-block → DLW32MH101XT2 CMC → H-MTD. CM termination is 2 × 1 kΩ to a node, then 4.7 nF + 100 kΩ from the node to GND. ESD is optional and left unfitted.
- **Power (Figure 8-3 / Table 8-2):**
  - VDDA, VDDIO and VDD1P0 each get their own ferrite island.
  - Every power pin gets 10 nF + 100 nF; some also get 2.2 µF.
  - The decaps sit on the **bottom side**, in a ring under the PHY.
  - 1.0 V comes from a **TPS62821 buck**: 470 nH, 66.5 k / 100 k divider, 120 pF Cff.
  - Estimated module power **~0.7 W**, inside the SFP's 1.0 W power-up limit.
- **MCU:** STM32G031. It answers the host's I²C as the EEPROM (0x50) and the PHY bridge (0x56), and handles MDIO, TX_DISABLE and RX_LOS. See [`../../fw/`](../../fw/).

## Board

- 59.5 × 12.4 mm. The tab is 9.2 mm wide.
- Edge connector is the INF-8074i pattern (`../fp/sfp.pretty/SFP_Module_Edge`).
- 4 layers:

  | Layer | Use |
  |---|---|
  | F | signals + GND pour |
  | In1 | GND |
  | In2 | +3V3 |
  | B | signals + GND pour |

- No pour among the edge fingers.
- The PHY's exposed pad gets 3 × 3 thermal vias to the planes.

## Before ordering

1. **H-MTD connector footprint (J2)**
   - `HMTD_1P_Placeholder` is **not a real land pattern**. Its two signal pads and four shield pads sit inside a box sized for the part, only so the router had something to work with.
   - Pick a single-port PCB header (Rosenberger H-MTD family), redraw the footprint from its drawing, then reroute.
2. **Stackup and impedance**
   - SGMII (SG_*/TD_*/RD_*) needs 100 Ω differential. The 0.12 mm wide / 0.15 mm gap in `make_t1.py` is a placeholder for a ~0.1 mm outer dielectric.
   - Choose the fab's **1.0 mm 4-layer** stackup, get the numbers from its impedance calculator, and put them in `NETCLASSES`.
   - The autorouter **routes the pairs uncoupled**. The runs are short (≈ 10 mm from finger to PHY), but they need **a hand re-route as coupled pairs**.
3. **Order options**
   - 1.0 mm, 4 layers, ENIG
   - **Hard gold on the edge fingers + bevel**
   - Impedance control

## Regenerating

```bash
python3 make_t1.py            # symbols, footprints, schematic, placed PCB (with nets)
sh run_erc.sh                 # eeschema ERC -> erc.rpt (headless, Xvfb)
python3 make_t1.py --route    # + planes, Freerouting, SES in, pours, DRC -> drc.rpt
python3 make_t1.py --reuse-ses  # reuse t1.ses (Freerouting results vary from run to run)
python3 export_t1.py          # gerbers, drill, BOM, CPL, previews -> fab/
```

- The router is **Freerouting 1.9.0**, at `~/.local/share/freerouting/freerouting-1.9.0.jar`.
  - 2.x ignores the pass limit on the command line and never finishes on this board.
  - 1.9.0 needs a display, so it gets Xvfb `:98`.
- Freerouting's result changes on every run. **`t1.ses` in this repo is the run that came out DRC-clean.**
- KiCad 7 quirks, recorded in the code:
  - Standalone `LoadBoard` does not read `.kicad_pro`, so the rules are set in memory (`apply_rules`).
  - A footprint must be added to the board before `Flip`, or it segfaults.
  - A pad's `SetPos0` is required, or every pad collapses to the footprint origin.

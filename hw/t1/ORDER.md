# T1 SFP order sheet (JLCPCB, budget under 500,000 KRW)

Upload the files in `jlc/` as they are (`python3 panel_t1.py` makes them).

| File | What it is |
|---|---|
| `jlc/t1-panel-gerbers.zip` | 5-board panel, **70.6 × 81.1 mm**. Gerbers (4 copper layers, masks, silks, paste, outline) + drill |
| `jlc/bom-tg720.csv`, `jlc/cpl-tg720.csv` | **1000BASE-T1** loadout (DP83TG720 + FB3): BOM 29 lines, CPL **280 placements** (designators `R4_1…R4_5`) |
| `jlc/bom-tc812.csv`, `jlc/cpl-tc812.csv` | **100BASE-T1** loadout (DP83TC812, FB3 left off, L2 = the 200 µH DLW32MH201XK2L the TC812 needs): BOM 28 lines, CPL **275 placements** |
| `jlc/panel-drc.rpt` | Panel DRC: **0 errors, 0 unconnected**; all 86 findings are warnings: "library not in this project" for the placed footprints and KiKit's mouse-bite holes; they don't reach the gerbers |
| `jlc/panel-top.png` | Panel preview. The gold fingers sit on the left edge |

![panel](jlc/panel-top.png)

## PCB options (JLC order form)

| Field | Value | Why |
|---|---|---|
| Layers | 4 | |
| Dimensions | panel (in the gerbers) | a single board is below the gold-finger minimum (50 mm per side) and the PCBA minimum (70 × 70) |
| Thickness | **1.0 mm** | SFP MSA: 1.0 ± 0.1 over the fingers |
| Stackup | **JLC04101H-3313** | the pairs are calculated for this stackup: 0.114 lines / 0.152 gap ≈ 100 Ω differential (50 Ω single-ended = 0.157) |
| Impedance control | **yes** | free |
| Surface finish | **ENIG** | required for gold fingers |
| Gold fingers | **yes**, bevel **45°**, **the panel's left edge** | every board's fingers sit on that edge |
| Min via | 0.25 drill / 0.45 pad | |
| PCB quantity | 5 panels (25 boards' worth of PCB) | |
| Panel by JLC | no (we supply the panel) | |

JLC offers **no electroplated hard gold**, so the fingers get ENIG-grade gold, not the MSA's hard gold (≥ 0.38 µm). Good for tens of insertions: enough for prototypes on a bench. For modules that get plugged often, order the PCB from a fab that plates hard gold (e.g. PCBWay) and have only the assembly done at JLC.

## Assembly options

| Field | Value |
|---|---|
| Type | **Standard** (Economic can't do 0201 or gold fingers) |
| Sides | **both** (the decaps are on the bottom, under the PHY) |
| Quantity | 2 panels (the minimum) |
| Files | `jlc/bom-tg720.csv` + `jlc/cpl-tg720.csv`, **or** `jlc/bom-tc812.csv` + `jlc/cpl-tc812.csv` |

**Check part rotations in JLC's 3D preview.** Some QFN/TSSOP footprints have a different zero angle in KiCad and in JLC's library. Rotate on the preview screen if needed.

## The PHY: the only stock problem

| | Part | LCSC | Stock (2026-09-29) | Price |
|---|---|---|---|---|
| 1000BASE-T1 | DP83TG720SWRHARQ1 | C2921292 | **3** | $12.3 |
| (same part, different reel) | DP83TG720SWRHATQ1 | C3225809 | 3 | $10.0 |
| 100BASE-T1 | DP83TC812SRHARQ1 | C3225813 | 18 | $4.05 |

A 5-board panel × 2 panels = **10 PHYs needed**. Pick one:

1. **1000BASE-T1, parts from JLC Global Sourcing.** Add 10 × DP83TG720SWRHARQ1 via "Order Parts" from DigiKey/Mouser (TI has plenty), wait for them to reach your parts library, then place the PCBA order. Adds about 1–2 weeks.
2. **100BASE-T1 first run (in stock now).**
   - Upload `bom-tc812.csv` + `cpl-tc812.csv`: U1 is already C3225813, FB3 is already left out (the TC812 regulates its own core), and the CMC L2 is already the 200 µH DLW32MH201XK2L (C883600) the TC812 datasheet asks for. Nothing to edit by hand.
   - Same board, same firmware.
   - Cheapest, and it proves the design end to end.
3. **Smaller panel:** `python3 panel_t1.py 3` gives 3 boards × 2 panels = 6 boards. But one BOM can list only one C-number and each reel has only 3, so this still needs global sourcing.

## Estimated cost (10 boards, estimate)

| Item | USD |
|---|---|
| PCB: 5 panels, 4L 1.0 mm ENIG + gold fingers + bevel | 40–80 |
| PCBA setup (two-sided) + stencil | 51 + 16 |
| Part loading fees (~29 BOM lines, most extended, × $1.53) | ~45 |
| X-ray (QFN), solder joints | ~20 |
| Parts: 10 boards, **TG720** / **TC812** | ~180 / ~120 |
| Shipping (DHL) | ~20–25 |
| **Total** | **~370–410 / ~310–350** |

At about 1,370 KRW/USD:
- **1000BASE-T1: about 510–560k KRW (slightly over budget)**
- **100BASE-T1: about 425–480k KRW (within budget)**

Separately: the H-MTD connector (Rosenberger E6S20A-40MT5-Z, from Mouser) costs a few thousand KRW each × 10. It is soldered by hand after depaneling.

To get the gigabit run under 500k:
- change some 0201 caps to basic 0402 parts (cuts the loading fees),
- or order 1 panel + have 1 panel assembled, if JLC's minimum allows it.

## Before you order

- [ ] Check the pair geometry in JLC's impedance calculator: **100 Ω differential, 0.114 mm lines / 0.152 mm gap** on 3313, outer layers over In1/In2 GND. If JLC's number differs, change `DP_W` / `DP_PITCH` in `make_t1.py` and rebuild
- [ ] H-MTD J2: print [`fab/t1-1to1.pdf`](fab/t1-1to1.pdf) at **100 %** (check the 64.5 mm board length on paper) and set a real E6S20A on it
- [ ] Load switch: after assembly, scope the 3.3 V rise on the first board (expect ≈3.6 ms)
- [ ] Rotations in JLC's assembly preview
- [ ] Flash the firmware (`fw/`) through SWD on TP1–TP5 after assembly
- [ ] On the Gerbers, before paying: top side seen from above with the card edge on the left, **pin 11 (ground, long pad) at the top and pin 20 at the bottom**, VccR (15) above VccT (16) (SFF-8419 Figure 7-2; the edge was mirrored until 2026-10)

## First board: bring-up order

Not in a host first.
1. **Bench supply, current-limited** to about 300 mA, into VccT/VccR and ground (the fingers or TP1/TP5). Scope +3V3 (U4 output), the input current (shunt or probe), and PHY_RST_N together. Expect a ≈3.6 ms rise and an inrush in the tens of mA, with no step at hot-plug.
2. Flash the firmware over SWD and read it back over I²C from a USB–I²C adapter:
   - A0h at 0x50, then A2h at 0x51;
   - the PHY bridge at 0x56, then PHYIDR1/2 over it (0x2000 / 0xA28x for the DP83TG720, 0xA27x for the DP83TC812).
3. Then one known host only: the D10 (`docs/D10.md`) or the LAN9692 EVB. Do not count on any SFP cage running SGMII; some are 1000BASE-X only. Check in this order:
   - SGMII lock;
   - the BASE-T1 link against a known partner (a TI EVM, or a second module);
   - traffic.

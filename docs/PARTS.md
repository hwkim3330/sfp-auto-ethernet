# Part selection

The rule is that **the datasheet must be public**, meaning downloadable without an NDA. A module whose PHY cannot be read cannot be designed or maintained.

## T1: 100/1000BASE-T1 — TI DP83TG720S-Q1 / DP83TC812S-Q1

| | DP83TG720S-Q1 | DP83TC812S-Q1 |
|---|---|---|
| Speed | 1000BASE-T1 | 100BASE-T1 |
| MAC interface | RGMII, **SGMII** | RGMII, **SGMII** |
| Package | VQFN-36, 6 × 6 | VQFN-36, 6 × 6, **pin-to-pin with the DP83TG720** |
| Supplies | VDDA3P3 3.3 V, VDD1P0 1.0 V, VDDIO 1.8/2.5/3.3 V, VSLEEP 3.3 V | (datasheet) |
| Linux | `dp83tg720.c` (Clause 22 ID 0x2000a284) | `dp83tc811.c` family (DP83TC812 support **unverified**) |

**One PCB with two loadouts** gives either 100 or 1000.

Sources:
- [DP83TG720S-Q1 datasheet](https://www.ti.com/lit/ds/symlink/dp83tg720s-q1.pdf)
- [DP83TC812S-Q1 datasheet](https://www.ti.com/lit/ds/symlink/dp83tc812s-q1.pdf)
- [DP83TC812S-Q1 product page](https://www.ti.com/product/DP83TC812S-Q1), which states the pin-to-pin compatibility with the DP83TG720

The bench's LAN9692 EVB MATEnet ports use LAN8870. It runs 100 and 1000, so one module can link to it at either speed.

**Parts not chosen, and why:**

| Part | Why not |
|---|---|
| Marvell 88Q2112 | Does 100 and 1000 over SGMII, and a full datasheet copy is on DigiKey ([link](https://mm.digikey.com/Volume0/opasdata/d220001/medias/docus/8899/88Q2112-A2-NYD2A000.pdf)). But Technica says its register settings need a Marvell NDA ([manual](https://www.manualslib.com/manual/1861226/Technica-Engineering-1000base-T1.html)). It is what Intrepid and Technica use |
| Microchip LAN8870 | 100/1000, SGMII, 7 × 7. Only the product brief is confirmed public ([PB](https://ww1.microchip.com/downloads/aemDocuments/documents/UNG/ProductDocuments/ProductBrief/LAN8870-LAN8871-LAN8872-Product-Brief-DS00004469.pdf)). **If the full datasheet turns out to be public, this is the first alternative**, because it is the same PHY as the bench |
| NXP TJA1120B | SGMII but 1000 only, and the datasheet is behind a login. Linux also drives it through Clause 45, which the SFP PHY probe does not use |

## RJ45: 100M / 1G / 2.5G: Realtek RTL8221B-VB-CG (replaces the DP83869)

| | |
|---|---|
| Speeds | 2.5GBASE-T / 1000BASE-T / 100BASE-TX |
| Host side | 2500BASE-X + SGMII (switching with link speed; MMD30 0x697A = 0), or 2500BASE-X only with rate adaptation (= 2). **Default is HiSGMII (3), and there is no strap**, so the MCU must write this register |
| Package | QFN-48 **6 × 6**, 0.4 mm pitch |
| Power | 3.3 V + **an external 0.95 V** (no internal regulator). 88 mA + 364 mA typical, ≈0.64 W typical, ≈0.95 W max |
| Linux | `realtek_main.c` "RTL8221B-VB-CG" (C45 ID 0x001cc849); EEPROM byte 36 = 0x1E makes it probe C45 at 0x56 |
| LCSC | **C5155988**, 4,564 in stock, $3.53 |
| Also used by | FS SFP-2.5G-T / OEM SFP-2.5G-T (same chip) |

**Exception to the rule:** the datasheet LCSC serves is stamped "CONFIDENTIAL: Development Partners Only". It is public in the sense that anyone can download it, and there is no public-datasheet part that does 2.5G. The other candidates: YT8821C has only a 3-page brief, GPY211C has 0 stock, 88E2110 is BGA with 0 stock.

- One chip covers 100M, 1G and 2.5G, so the **DP83869HM is dropped**.
- Magnetics: LINK-PP **LP72450ANL** (C53281905, 2.5G, −40–85 °C, 15.2 × 7.1 × 4.0 mm, fits under the 4.65 mm above the PCB inside the cage) or JASN V24P05S (C2827281, $0.69).
- **Mechanical risk: the RJ45 jack.** The narrowest found is HCTL HC-RJ45-055-6 (C3000212) at **13.8 mm**, just over the 13.7 limit, and it is a sink-mount type. Commercial modules build the RJ45 into the housing (MikroTik S-RJ01 teardown). **Still unresolved.**

## T1S: 10BASE-T1S — Lattice CrossLink-NX + Microchip LAN8670

- **No 10BASE-T1S PHY with SGMII has been found.** All of them are MII/RMII, OA-SPI MAC-PHY, or PMD-only:
  - LAN8670/1/2 ([datasheet](https://docs.rs-online.com/99eb/A700000009056932.pdf))
  - DP83TD555J ([datasheet](https://www.ti.com/lit/ds/symlink/dp83td555j-q1.pdf))
  - TJA1410
  - NCN26000/26010
  - ADIN1140
- **A switch chip doesn't fit.** Every part with SGMII + MII/RMII (LAN9373, KSZ8567/9477, YT9215) is a 128-TQFP, 14 × 14 mm. The one single-chip exception, RTL8364NB (QFN-88 10 × 10), has a confidential datasheet and is barely wide enough.
- **Wiring two PHYs back to back doesn't work either.** The LAN867x needs a CSMA/CD MAC (DS60001573 §4.9), so the bridge has to store frames and honour CRS/COL.
- **So an FPGA bridge is needed:**
  - **Lattice CrossLink-NX LIFCL-17:** **SGMII is only on csfBGA-121 (6 × 6)**. The datasheet says it is not supported on the 72-pin packages (QFN/WLCSP). Lattice's SGMII PCS IP is **licensed** (without a licence it runs for 4 hours), and the open toolchain (prjoxide) doesn't support this block. LCSC stock is only 3–6.
  - **Gowin GW5AT-15 (MG132, 8 × 8):** hard transceivers, public datasheet, **LCSC C54067362, 348 in stock, $31**. LiteEth's PMA only supports the 138B for now, so it needs porting.
  - Gateware (LiteEth `pcs.py` as the starting point): a **PHY-side** SGMII PCS (auto-negotiation words for 10M full duplex), ×100 symbol replication, a frame FIFO, and a half-duplex MII MAC that defers and retries.
  - PHY: LAN8670 (MII/RMII, 5 × 5, **C20901523, stock 14**) or LAN8671 (RMII only, 4 × 4, C22394443, 99 in stock).
  - This is the most work and the most expensive (FPGA ~$31 + PHY ~$7).
- Evidence it can be done: Intrepid sells an "MC8670" 10BASE-T1S SFP ([link](https://intrepidcs.com/products/automotive-ethernet-tools/automotive-ethernet-sfp-modules/)). Its bridging method is not published.

## Common: MCU as the host's I²C slave

**ST STM32G031** (TSSOP-20). Its I²C peripheral has two own-address registers (OA1 and OA2 with a mask), so a single peripheral can answer:

| Address | Role |
|---|---|
| 0x50 | A0h EEPROM, emulated |
| 0x51 | A2h diagnostics |
| 0x56 | PHY bridge: Clause 22, 16-bit big-endian (see [LINUX.md](LINUX.md)) → MDIO bit-bang to the PHY |

It also:
- drives TX_DISABLE, RX_LOS and the master/slave choice (T1),
- has an SWD pad for firmware.

Power: 3.3 V → 1.0/1.1 V is a TPS62A01 buck in SOT-563 (an LDO would burn 2.3 V × I and break the 1 W budget). 2.5 V and 1.8 V come from small LDOs.

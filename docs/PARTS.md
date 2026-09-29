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

## RJ45: 1000BASE-T — TI DP83869HM

- Has **"SGMII (Copper Only)"** as a MAC mode, so SGMII ↔ 1000BASE-T is direct.
- VQFN-48, 7 × 7 mm.
- Supplies: VDDA2P5 2.5 V, VDD1P1 1.1 V, VDDIO.
- **Under 500 mW at 1000BASE-T.**
- Linux: `dp83869.c`.
- Source: [DP83869HM datasheet](https://www.ti.com/lit/ds/symlink/dp83869hm.pdf)
- Not chosen: VSC8541 has no SGMII ([datasheet](https://ww1.microchip.com/downloads/aemDocuments/documents/OTH/ProductDocuments/DataSheets/VMDS-10496.pdf)). RTL8211FS has only unofficial datasheet copies.
- **Mechanical risk:** a standard RJ45 jack is ~16 mm wide, over the housing's 13.7. Commercial copper SFPs use a dedicated low-profile jack. v0 places a 13.6 mm placeholder; the actual part is still to be found.

## T1S: 10BASE-T1S — Lattice CrossLink-NX + Microchip LAN8670

- **No 10BASE-T1S PHY with SGMII has been found.** All of them are MII/RMII, OA-SPI MAC-PHY, or PMD-only:
  - LAN8670/1/2 ([datasheet](https://docs.rs-online.com/99eb/A700000009056932.pdf))
  - DP83TD555J ([datasheet](https://www.ti.com/lit/ds/symlink/dp83td555j-q1.pdf))
  - TJA1410
  - NCN26000/26010
  - ADIN1140
- **So a bridge is needed:**
  - **Lattice CrossLink-NX (LIFCL-17)** has "2x SGMII CDR at up to 1.25 Gbps" on its I/O, in a 6 × 6 csfBGA-121 ([datasheet](https://datasheet.octopart.com/LIFCL-40-7SG72I-Lattice-Semiconductor-datasheet-180556959.pdf)).
  - It does the SGMII PCS and 10 Mb/s rate adaptation (symbol replication), and connects to the LAN8670 over MII.
  - T1S is half-duplex, so it buffers frames and presents full duplex to the host.
  - This needs gateware, which makes this variant the most work.
  - Whether the CDR pins are bonded out in the smaller packages (QFN-72, WLCSP-72) is **unverified**.
- Not chosen: a KSZ9477 switch has SGMII + MII but 7 ports, too big for an SFP.
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

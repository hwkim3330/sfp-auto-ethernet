# References, and the design checked against them

Every link was opened on 2026-10-01. "Ours" is what the board or firmware does; ✓ agrees, **fixed** was changed after this check, ⚠ is a known difference with its reason.

## Standards

| Document | What we take from it |
|---|---|
| [INF-8074i Rev 1.0](https://members.snia.org/document/dl/26184) | SFP pinout, edge fingers, housing, low-speed timing (t_off 10 µs, t_init 300 ms), AC coupling inside the module, inrush |
| [SFF-8419 Rev 2.0a](https://members.snia.org/document/dl/25880) | power classes (Table 6-2: class 1 = 1.0 W, 289 mA steady), "power up at ≤ 1 W" |
| [SFF-8472 Rev 12.5a](https://members.snia.org/document/dl/25916) | A0h/A2h maps, byte 64 power level, A2h byte 118 power-level control, byte 94 compliance |
| [SFF-8024 Rev 4.14](https://members.snia.org/document/dl/26423) | code tables: extended compliance 0x1E = 2.5GBASE-T, connector 0x22 = RJ45 |
| [SFF-8431 Rev 4.1](https://www.gigalight.com/downloads/standards/sff-8431.pdf) (archived) | 2-wire interface, module channel |
| [SFF-8432 Rev 5.2a](https://members.snia.org/document/dl/25892) | module and cage mechanics |
| [Cisco SGMII ENG-46158 Rev 1.8](https://archive.org/details/sgmii) | 10/100 by byte replication (×100 / ×10), link timer 1.6 ms, tx_config_Reg |

## Linux (torvalds/linux master)

| File | What it settles |
|---|---|
| [drivers/net/phy/sfp.c](https://elixir.bootlin.com/linux/latest/source/drivers/net/phy/sfp.c) | byte 6 bit 3 (1000BASE-T) → C22 PHY probe at 0x56; byte 36 = 0x1E (2.5GBASE-T) → C45; probe retried ~1.25 s; power level: byte 64 read only if byte 94 ≥ Rev 10.2, and with A2h present a host under 1.5 W warns and leaves level 1 |
| [drivers/net/mdio/mdio-i2c.c](https://elixir.bootlin.com/linux/latest/source/drivers/net/mdio/mdio-i2c.c) | the 0x56 framing: C22 `[reg]` + 2-byte read, `[reg,hi,lo]` write; C45 read `[0x20\|devad, reg_hi, reg_lo]`, write `[devad, reg_hi, reg_lo, hi, lo]` |
| [drivers/net/phy/dp83tg720.c](https://elixir.bootlin.com/linux/latest/source/drivers/net/phy/dp83tg720.c) | ID 0x2000a284; MMD access through REGCR/ADDAR works over C22 |
| [drivers/net/phy/realtek/realtek_main.c](https://elixir.bootlin.com/linux/latest/source/drivers/net/phy/realtek/realtek_main.c) | RTL8221B-VB-CG ID 0x001cc849; the driver switches 2500BASE-X / SGMII with copper speed |
| [drivers/net/phy/microchip_t1s.c](https://elixir.bootlin.com/linux/latest/source/drivers/net/phy/microchip_t1s.c) | LAN867x Rev C1/C2 set-up, the order our firmware follows |

Our firmware is the 0x56 / mdio-i2c convention. None of the commercial T1 modules found uses it (Intrepid: 0x40 bridge; STAR FL3X: "STAR tunnel" at 0x40; APAC's RTL8221B module: a private 0x51 scheme), so those need vendor software and ours binds to the mainline drivers.

## T1 (DP83TG720S-Q1 / DP83TC812S-Q1)

- [DP83TG720S-Q1 datasheet SNLS604G](https://www.ti.com/lit/ds/symlink/dp83tg720s-q1.pdf): Table 8-1 (MDI), Table 8-2 (power), 6.5.1 (straps), 6.4 (SGMII layout), 8.5 (layout)
- [SNLA371B, Open Alliance compliance](https://www.ti.com/lit/pdf/SNLA371), [SNLA340 hardware rollover 812 ↔ 720](https://www.ti.com/lit/pdf/SNLA340), [SNLA473 SGMII troubleshooting](https://www.ti.com/lit/pdf/SNLA473)
- [DP83TC812S-Q1 datasheet SNLS654D](https://www.ti.com/lit/ds/symlink/dp83tc812s-q1.pdf)
- [DP83TG720EVM-MC user guide SNLU289](https://www.ti.com/lit/ug/snlu289/snlu289.pdf) (a media converter over RGMII, with an H-MTD option)
- Rosenberger H-MTD: [E6S20A datasheet](https://products.rosenberger.com/_ocassets/db/E6S20A-40MT5-Y.pdf), [PCB layout MB_633](https://products.rosenberger.com/_ocassets/mb/MB_633.pdf)
- [TPS22918 datasheet](https://www.ti.com/lit/ds/symlink/tps22918.pdf): rise time vs CT (2.2 nF → 3.58 ms at 3.3 V)
- Commercial modules: [Intrepid 88Q2112 SFP](https://intrepidcs.com/products/automotive-ethernet-tools/88q2112-1000base-t1-sfp/) ([I²C map](https://guide.intrepidcs.com/docs/1000BASE-T1-SFP/A-Tour-of-1G-SFP-Hardware.html)), [STAR FL3X](https://flex-product.com/products/fl3x-sfp-1000base-t1) (350 mA typical), [Technica TE-1437](https://www.nextgigsystems.com/technica-engineering/1000base-t1-sfp-module/)

| Item | TI | Ours | |
|---|---|---|---|
| MDI DC block | 0.1 µF, 100 V (371: 1 %) | 100 nF **100 V** X5R ±10 % 0402 (GRM155R62A104KE14D, C162178) | **fixed**: it was the 16 V decap (C1525), only the value had been checked; ⚠ ±10 %, no 1 % 100 V part exists in 0402 (at 100 nF the coupling corner stays under 2 kHz either way). JLC stocks no SMD 100 nF 100 V at 1 % (only a leaded C0G, out of stock) and no 0402 X7R at 100 V, so this is X5R (85 °C) |
| CMC | DLW32MH101XT2 (100 µH) for the TG720; **200 µH** for the TC812 | DLW32MH101XT2; **the TC812 loadout now fits DLW32MH201XK2L (C883600)** | **fixed** |
| CM termination | 2 × 1 kΩ 1 % 0.75 W 2010 (SNLA371B OA configuration) | **2 × 1 kΩ 1 % 0.75 W 2010** (Yageo RC2010FK-071KL, C723477), along the board either side of the pair between the CMC and the H-MTD; 4.7 nF ‖ 100 kΩ to ground | **fixed** (was 0402: 62.5 mW, then 0.2 W). The H-MTD moved 1 mm back for the room. The two unfitted 0402 ESD footprints are gone: they are not in TI's configuration |
| CM to GND | 4.7 nF (EVM: 1 kV 1206) ‖ 100 kΩ | 4.7 nF 0402 ‖ 100 kΩ 0402 | ⚠ the same; the 1 kV part is for ESD robustness tests |
| Copper under the CMC | none, top and at least one layer below (8.5) | **no pour on F and In1 under L2** | **fixed** |
| SGMII AC coupling | 0.1 µF ×4 | 100 nF 0201 ×4, all in the module as INF-8074i asks | ✓ |
| Decoupling per pin | 10 nF + 100 nF + 2.2 µF (VDDA, VDDIO 22, VDD1P0 9/21), 10 nF + 100 nF (VDDIO 34) | the same, pin by pin | ✓ |
| VSLEEP | ≥ 1 µF if sleep is used, else tie to VDDA | tied to VDDA, 100 nF | ✓ |
| Crystal | 25 MHz, ±100 ppm total, ESR ≤ 100 Ω | ±40 ppm, ESR 80 Ω, CL 8 pF | ✓ |
| MDIO pull-up | 2.2 kΩ | 2.2 kΩ | ✓ |
| First MDIO access | ≥ 65 ms after power-up | **70 ms after reset release; the 0x56 bridge answers 0xFFFF until then** | **fixed** (was 20 ms) |
| Power | IDD1P0 200/260 mA, IDDA3P3 95/100 mA | 1.0 V from a buck (not an LDO), so ~0.65 W max at the PHY | ✓ class 1 |

## RJ45 (RTL8221B-VB-CG)

- [RTL8221B-VB-CG datasheet Rev 1.0](https://datasheet.lcsc.com/datasheet/pdf/83dc4178a800722cd862733fb481cd16.pdf?productCode=C5155988) (stamped confidential, served by LCSC); [Realtek product page](https://www.realtek.com/Product/Index?id=4072&cate_id=786)
- [TPS6282x datasheet SLVSDV6C](https://www.ti.com/lit/ds/symlink/tps62823.pdf): PSM below half the ripple current; L 0.47 or 1.0 µH (Table 3)
- [LINK-PP LP72450ANL](https://datasheet.lcsc.com/datasheet/pdf/a7affa0214ecd2a29b90763168dc23ec.pdf?productCode=C53281905): 4.0 mm tall, 1500 Vrms
- [Kinghelm KH-RJ45-58](https://datasheet.lcsc.com/datasheet/pdf/d824c9bfca930abdd55793abf5fd3114.pdf?productCode=C2683360): 15.70 × 13.20 × 18.20 mm
- Commercial RTL8221B modules: [FS SFP-2.5G-T](https://img-en.fs.com/file/datasheet/2.5g--t-transceiver-datesheet.pdf) (RollBall, "< 2 W", 450 mA max), [APAC ASFPT-T5F/T6F](https://www.apacoe.com.tw/files/ASFPT-T5_6_F_-I__V1.0.pdf) (0.83 W typ / 1.11 W max: the only measured figure found), [Starview SV-SFP-T2.5A](https://starviewtech.net/wp-content/uploads/2022/05/w_Datasheet-SFP-2.5G-Base-T-Transceiver-100m-SV-SFP-T2.5A-version-5.0.pdf)
- Kernel history: [RollBall + multigig (2022)](https://patchwork.kernel.org/project/netdevbpf/cover/20240409073016.367771-1-ericwouds@gmail.com/), [OEM SFP-2.5G-T quirk](https://github.com/torvalds/linux/commit/50e96acbe11667b6fe9d99e1348c6c224b2f11dd), [FS SFP-2.5G-T as RollBall](https://lore.kernel.org/r/20240423085039.26957-2-kabel@kernel.org)

| Item | Realtek / references | Ours | |
|---|---|---|---|
| 0.95 V core | 0.92–0.98 V, 364 mA typ / 650 mA max; a switcher must run **PWM/CCM, > 1 MHz, no pulse skipping** | TPS62822 at 0.946 V, 2.2 MHz. It has no forced-PWM pin and skips below half its ripple: ~0.33 A with 0.47 µH. **L1 now 1.0 µH (DFE201610E-1R0M, C161082): ~0.15 A** | **fixed**; ⚠ still skips below ~0.15 A (link down) |
| Core enable | POW_EXT_SWR (pin 46) drives the regulator's EN | pin 46 → TPS62822 EN | ✓ |
| Clock | oscillator ±50 ppm, ≤ 2 ps RMS (10 kHz–20 MHz) | MST8011AI ±25 ppm, 2.0 ps max | ✓ |
| RSET / MDIO | 2.49 kΩ 1 % / 1.5 kΩ pull-up | 2.49 kΩ 1 % / 1.5 kΩ | ✓ |
| SerDes coupling | 0.1 µF on each pair | 100 nF, both lanes inside the module | ✓ |
| MDI | internal termination, CFG_OPT1 can swap pair order | no external MDI resistors | ✓ |
| First MDIO access | core ready ≤ 55 ms after power-up | 70 ms after reset release | ✓ |
| Power level | PHY 0.64 W typ / ~1.0 W worst; commercial modules all declare level 1 | declares level 2 with the A2h 118 handshake (level 1 = 100M/1G only) | ⚠ standards-correct but stricter than the market: on a 1 W host the link comes up at 1G |
| Linux | byte 36 = 0x1E + C45 at 0x56 needs no quirk; copying FS/OEM vendor strings would pull in RollBall or autoneg-off quirks | byte 36 = 0x1E, own vendor string | ✓ |
| Jack | 15.70 wide × 13.20 tall | outside the cage, on the nose | ⚠ taller and wider than an SFP housing: check the neighbouring and stacked cage ports |

## T1S (GW5AT-15 + LAN8670)

- Gowin: [DS981 datasheet](https://cdn.gowinsemi.com.cn/DS981E.pdf), [UG1224 GW5AT-15 pinout](https://cdn.gowinsemi.com.cn/UG1224E.pdf), [UG984 schematic manual](https://cdn.gowinsemi.com.cn/UG984E.pdf), [UG720 configuration](https://cdn.gowinsemi.com.cn/UG720E.pdf), [IPUG1024 Customized PHY](https://cdn.gowinsemi.com.cn/IPUG1024E.pdf), [IPUG1021 1G serial Ethernet IP](https://cdn.gowinsemi.com.cn/IPUG1021E.pdf) (an SGMII PHY-side mode: a fallback for our own PCS)
- Gowin's board with our exact device: [DK_EDP_GW5AT-LV15MG132 schematic](https://www.gowinsemi.com/upload/database_doc/3051/document_ja/68a8c684dd802.pdf) ([page](https://www.gowinsemi.com/ja/support/devkits_detail/64/))
- Open tools: [apicula](https://github.com/YosysHQ/apicula) has no GW5AT-15 and no SerDes: Gowin EDA is needed
- Microchip: [LAN8670 datasheet DS60001573K](https://ww1.microchip.com/downloads/aemDocuments/documents/AIS/ProductDocuments/DataSheets/LAN8670-1-2-Data-Sheet-60001573.pdf), [AN1699 configuration Rev G](https://ww1.microchip.com/downloads/aemDocuments/documents/AIS/ApplicationNotes/ApplicationNotes/LAN8670-1-2-Configuration-Appnote-60001699.pdf), [AN1718 BIN reference design Rev D](https://ww1.microchip.com/downloads/aemDocuments/documents/AIS/ApplicationNotes/ApplicationNotes/LAN86xx-BIN-Ref-Design-Application-Note-60001718.pdf), [LAN86xx layout guide](https://ww1.microchip.com/downloads/aemDocuments/documents/AIS/ApplicationNotes/ApplicationNotes/LAN86xx-10BASE-T1S-Layout-Guide-Appnote-00006174.pdf), [EVB-LAN8670-RMII user guide](https://ww1.microchip.com/downloads/aemDocuments/documents/AIS/ProductDocuments/UserGuides/EVB-LAN8670-RMII-Users-Guide-60001708.pdf)
- Open PCS cores to compare our gateware with: [LiteEth](https://github.com/enjoy-digital/liteeth) (`phy/serial/basex/pcs.py`, byte repetition 99/9), [LambdaEth](https://github.com/key2/lambdaeth) (LiteEth ported to Amaranth, proven at 1G on Gowin GTR12), [taxi](https://github.com/fpganinja/taxi) (successor of verilog-ethernet), [AMD PG047](https://docs.amd.com/r/en-US/pg047-gig-eth-pcs-pma)
- No commercial 10BASE-T1S SFP was found.

| Item | Reference | Ours | |
|---|---|---|---|
| CLKHOLD_N (K3) | must be high during MSPI (UG720); the ball is pulled **down** during configuration (pinout `term_during_config`) | **tied to +3V3** | **fixed** (open, the FPGA would never have loaded) |
| SSPI_CS_N (P1) | pull up if SSPI is unused, else the FPGA may select slave SPI after an MSPI load (UG720); pulled down during configuration | P1 is FPGA_LINK; **R26 4.7 kΩ pull-up at the MCU**, the MCU's own pull-down removed | **fixed** |
| DONE, READY | open drain, 4.7 kΩ pull-ups | R4, R5 4.7 kΩ | ✓ |
| RECONFIG_N | high until 1 ms after power is stable; pulses ≥ 25 ns | R3 4.7 kΩ; MCU pulses 1 ms | ✓ |
| MODE[1:0] | 11 = MSPI; 4.7 kΩ pull-up / 1 kΩ pull-down | MODE1 4.7 kΩ up, MODE0 its internal pull-up | ⚠ an external MODE0 pull-up would be belt-and-braces |
| Flash | ≥ 64 Mbit, 03h/0Bh read; MSPI retry (golden) image at 0x800000 by default | **GD25Q128E (128 Mbit, C2982923)**, same WSON-8 6 × 5 | **fixed**: a 64 Mbit part ends at 0x7FFFFF, so the default golden address fell off the end; now the main image sits at 0x000000 and the golden at 0x800000, each with 8 MiB |
| REFCLK | 20–800 MHz, 40–60 % duty; 0.1 µF series near the FPGA (UG984 5.2); the dev board uses a 3.3 V LVDS oscillator the same way | 125 MHz LVDS, 100 nF series at the FPGA, A8/A7 | ✓ |
| SerDes rails | VDDAQ0 / VDDTQ0 0.87–1.03 V, VDDHAQ0 1.8 V; low-noise LDOs, VDDTQ kept apart (UG984 Table 2-3); the dev board has separate LDOs | VDDAQ / VDDTQ each through its own ferrite from the 0.946 V buck (now 1 µH, see RJ45); VDDHAQ from an LDO | ⚠ beads, not LDOs, on the 0.95 V SerDes rails |
| Sequencing | VCCX before VCC recommended | VCCX on +3V3, VCC from a buck enabled off it | ✓ |
| LAN8670 set-up | AN1699 Rev G: C2 Tables 3-1/3-2; D0 Table 2-1 | **picked by PHY_ID2 revision** (was C2 only) | **fixed** |
| PLCA collision detection | C2: CDEN off while PLCA runs, on in CSMA/CD fallback; D0: CDAD | **both, C2 following PST** | **fixed** |
| MDI series caps | 0.1 µF 100 V 0805 | 100 nF 100 V 0805 | ✓ |
| End-node termination | 2 × 49.9 Ω 1 % **1 W 1206** | **2 × 49.9 Ω 1 % 0.75 W 1206 (CRCW1206-HP, C4014562)**; no 1 W 1206 is stocked | **fixed** from 0.25 W; ⚠ 0.75 W, not 1 W |
| Centre cap / shunt | 0.1 µF 100 V 0805 ‖ 100 kΩ 0805 | **100 nF 100 V** (was 50 V) ‖ 100 kΩ 0805 | **fixed** |
| CMC | ACT1210E-241 (240 µH) | ACT1210E-241-2P | ✓ |
| Copper under the CMC / round the BIN | none under the CMC on any layer; no ground flood round the BIN | **no pour under L2 on all six layers, none on F round the BIN** | **fixed** |
| MDI traces | 50 Ω single-ended, spaced ≥ 3 w, differential C ≤ 15 pF | 0.2 mm (44.8 Ω), not coupled | ⚠ at 12.5 MBd over ~15 mm the capacitance matters, not the impedance; ~1–2 pF |
| Crystal | 25 MHz ±100 ppm, CL 10–22 pF, ESR ≤ 100 Ω | ±30 ppm, CL 12 pF, ESR 100 Ω | ✓ |
| Straps | MII + crystal = MODE 01, 10 kΩ each (no internal pulls) | 10 kΩ each | ✓ |

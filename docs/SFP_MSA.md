# SFP MSA: what the module has to be

This page collects only the numbers the board depends on.

Sources:
- [INF-8074i](https://members.snia.org/document/dl/26184) (SFP MSA, 2000): Appendix A for mechanics, Appendix B for electrical
- [SFF-8419](https://members.snia.org/document/dl/25880) Rev 2.0a (power classes)
- [SFF-8472](https://members.snia.org/document/dl/25916) (EEPROM map)

## Pinout (module side; INF-8074i Appendix B Table 1)

Mating order: 1 = mates first.

| Pin | Signal | Direction · mating | Module does |
|---|---|---|---|
| 1, 17, 20 | VeeT | ground · 1 | ground |
| 9, 10, 11, 14 | VeeR | ground · 1 | ground. Pin 9 became RS1 in SFF-8419; tying it to ground is safe with both specs |
| 2 | TX_FAULT | open-drain out · 3 | may be tied to its negated state if there is no safety circuit |
| 3 | TX_DISABLE | in · 3 | 4.7–10 kΩ pull-up in the module; high or open = disabled |
| 4 / 5 | SDA / SCL (MOD-DEF2/1) | I/O · 3 | I²C, 100 kHz. The host pulls up |
| 6 | MOD_ABS (MOD-DEF0) | — · 3 | **tied to ground in the module** |
| 7 | RS0 | in · 3 | not used (> 30 kΩ pull-down if fitted) |
| 8 | RX_LOS | open-drain out · 3 | we drive it from link down |
| 12 / 13 | RD− / RD+ | CML out · 3 | module → host. **AC-coupled in the module**, 370–2000 mVppd |
| 18 / 19 | TD+ / TD− | CML in · 3 | host → module. **AC-coupled in the module, 100 Ω differential termination**, 500–2400 mVppd |
| 15 / 16 | VccR / VccT | 3.3 V · 2 | power |

## Edge connector (INF-8074i Figure 2 and Figure 3)

- PCB thickness **1.0 ± 0.1 mm** over the pads, with a 0.3 × 45° chamfer at the edge.
- The tab is **9.2 ± 0.1 mm** wide. The host's card slot is 9.4.
- 10 pads per side at **0.8 mm pitch**, each 0.6 ± 0.05 mm wide.
- Which way round (SFF-8419 Figure 7-2; INF-8074i Figure 2 draws the same with the edge on the right): look at the top side from above with the card edge on the **left**.
  - Top side, pins 11–20: **pin 11 at the top**, 3.4 mm above the centreline; pin 20 at the bottom, 3.8 mm below it.
  - Bottom side, pins 1–10, seen through the board: **pin 10 at the top**, 3.8 mm above; pin 1 at the bottom, 3.4 mm below, under pin 20. The bottom row is offset 0.4 mm from the top row.
  - Until 2026-10 this repo had it mirrored (pin 20 at the top). Every host contact would then have landed between two pads, VccT against ground.
- Where each pad starts, measured from the edge: **ground 0.5**, **power 0.9**, **signal 1.3** mm. That staggering sets the mating order. All pads run back to at least 3.5 mm.
- Plating: 0.38 µm hard gold minimum over 1.27 µm nickel. Order the board with **hard gold edge fingers and a bevel**.

`hw/fp/sfp.pretty/SFP_Module_Edge.kicad_mod` is generated from exactly these numbers (`hw/make_boards.py`).

## Housing (INF-8074i Appendix A Table 1)

| | mm | |
|---|---:|---|
| Width, front / rear (A / D) | 13.7 / 13.4 | |
| Height, front / rear (B / C) | 8.6 / 8.5 | |
| PCB underside above the housing floor (N) | 2.25 | so **above the PCB inside the cage: ~4.65**, below it ~1.65 (with our 0.6 mm wall) |
| Latch shoulder → PCB finger end (U) | 41.8 | |
| Latch shoulder → the stop outside the cage (V) | 2.5 | so the cage front sits **44.3 mm** from the finger end |
| Overall length (K) | 56.5 | the nose may be longer. Intrepid's T1 SFP is 76.5 × 13.5 × 20.5 |

## Power (SFF-8419 Tables 6-1 and 6-2)

- 3.3 V ± 5 %.
- Every module must **power up at 1.0 W or less**.

| Class | Power | Instantaneous peak (≤ 50 µs) | Sustained peak | Steady state |
|---|---|---:|---:|---:|
| 1 | 1.0 W | 400 mA | 330 mA | 289 mA |
| 2 | 1.5 W | 600 mA | 495 mA | 433 mA |
| 3 | 2.0 W | 800 mA | 660 mA | 577 mA |

- Inrush (INF-8074i): at most 30 mA above steady state.

## Timing (INF-8074i Appendix B Table 2)

| Parameter | Value |
|---|---|
| t_init (power-on to TX_FAULT cleared) | 300 ms max (SFF-8419 allows 500 ms) |
| t_off | 10 µs |
| t_on | 1 ms |
| t_loss_on / t_loss_off | 100 µs |

## EEPROM identity (SFF-8472, SFF-8024)

- **1000BASE-T is byte 6, bit 3.** That is the bit that makes Linux look for a PHY (see [LINUX.md](LINUX.md)).
- SFF-8024 Rev 4.13.2 has a code for 10BASE-T1L (extended code 0Eh) but **none for 100/1000BASE-T1 or 10BASE-T1S**. Our T1 and T1S modules therefore declare themselves as 1000BASE-T copper, and state what they really are in the vendor-specific area.

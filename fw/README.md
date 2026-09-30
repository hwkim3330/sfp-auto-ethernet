# SFP module controller firmware (STM32G031F6P6)

Bare metal, no HAL, **1.8–2.4 KB**. All three boards use it (`make VARIANT=t1|rj45|t1s`); the variants differ in their PHY setup and, on T1S, in minding the FPGA.

## What the host sees (SFP I²C, 100 kHz)

| Address | Content |
|---|---|
| **0x50** (A0h) | SFF-8472 ID EEPROM, emulated. Byte 6 = `0x08` (1000BASE-T): this is what makes Linux probe the PHY. Checksums CC_BASE/CC_EXT are computed at boot. **Bytes 96–127 are writable**, and byte 96 bit 0 = T1 **master** |
| 0x51 (A2h) | No diagnostics. Byte 92 = 0, so the host doesn't read it. Reads return 0 |
| **0x56** | PHY bridge, in the protocol Linux `mdio-i2c` expects. Write 1 byte = register, then read 2 bytes big-endian (auto-incrementing). Write 3 bytes = register + value. Clause 22. On the MDIO side the PHY is at the strapped address 0 |

A single I²C peripheral covers all three:
- **OA2 = 0x50, OA2MSK = 3** matches 0x50–0x57.
- ADDCODE tells which address was hit.
- While an MDIO transaction runs, SCL is held (clock stretching). So everything can run in the main loop, with no interrupts.

## What it does

- **TX_DISABLE high or open → the PHY is held in reset.** When TX_DISABLE goes low, it releases reset and applies the master/slave setting (MMD1 0x0834 bit 14, the IEEE 1.2100 register, identical on the DP83TG720 and DP83TC812).
- Every 50 ms it reads BMSR bit 2 (twice, because the link bit latches low). On link it drives RX_LOS low; with no link it releases RX_LOS.
- TX_FAULT is always held low (no fault).
- If byte 96 changes, it reapplies master/slave immediately.

To set master from Linux: write byte 96 = 1 into A0h. You can do this through `ethtool -m`'s EEPROM write, or with `i2cset`.

## RJ45 (`VARIANT=rj45`)

- RTL8221B at MDIO address 1, native Clause 45. EEPROM byte 36 = `0x1E` (2.5GBASE-T), so Linux probes C45 at 0x56 and binds its realtek driver.
- On release from reset it sets the SerDes mode (MMD30 0x697A): 2500BASE-X + SGMII by link speed for Linux, 2500BASE-X only for `HOST=d10`.

## T1S (`VARIANT=t1s`)

- **The FPGA first.** The PHY stays in reset until the FPGA's DONE (PA11) goes high. If DONE hasn't come 1.5 s after boot, the MCU pulses RECONFIG_N (PB0) low and waits again, three times at most.
- **LAN8670 set-up** on every release from reset: the Rev C1/C2 configuration from Microchip AN1699 Rev E, including the two per-part trim offsets read back through the CFGPARAM window. The order is the one Linux's `microchip_t1s` driver uses.
- **PLCA** from the writable vendor area of A0h. The host can change it at any time:

  | Byte | Meaning | Default |
  |---|---|---|
  | 120 bit 0 | PLCA on (off = plain CSMA/CD) | off |
  | 121 | local node ID (0 = coordinator) | 0 |
  | 122 | node count | 8 |
  | 123 | max burst count | 0 |

  It writes the OPEN Alliance PLCA registers (MMD31 0xCA01/0xCA02/0xCA05). With Linux, `ethtool --set-plca-cfg` on the PHY behind 0x56 works too.
- **RX_LOS follows FPGA_LINK** (PA7): SGMII word sync plus auto-negotiation done. 10BASE-T1S itself has no link status.
- `HOST=d10` is refused at build time. The host lane is SGMII at 10 Mb/s, so the module has no 1000BASE-X personality.

## Builds per host

- `make` (default, HOST=linux): advertises 1000BASE-T and serves the PHY bridge at 0x56. For Linux phylink hosts.
- `make HOST=d10`: advertises 1000BASE-SX and turns SGMII auto-negotiation off. For switches like the **Kontron D10** that manage Cu SFPs by part number. Set the port to speed 1000 FDX by hand; see [../docs/D10.md](../docs/D10.md).

## Build and flash

```bash
make                 # the arm-zephyr-eabi-gcc from a Zephyr SDK is found automatically; otherwise arm-none-eabi-
make flash           # openocd + ST-Link, through the board's TP1..TP5 (3V3, SWDIO, SWCLK, NRST, GND)
```

Headers come from ST's STM32CubeG0 and ARM's CMSIS. By default the Makefile uses the copies in a Zephyr workspace (`~/zephyrproject/modules/hal/...`); override with `CMSIS_DEVICE=` / `CMSIS_CORE=`.

## Not verified yet

- **Not run on real hardware yet** (no board exists).
- T1S: whether a Linux host's phylink accepts a 10BASE-T1S PHY behind an SGMII SFP (it needs the MAC to allow 10 Mb/s half duplex on SGMII).
- The MDIO bit-bang timing (~1 µs half-period, sampled while MDC is low) needs a scope.
- Timing: Linux's sfp driver waits 300 ms after power-up before probing the PHY. The firmware answers on I²C within a few ms of boot, but it doesn't release the PHY until TX_DISABLE goes low.

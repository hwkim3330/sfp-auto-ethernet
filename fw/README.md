# SFP module controller firmware (STM32G031F6P6)

Bare metal, no HAL, **1.7 KB**. All three variants use it; only the strings change (`make VARIANT=t1|rj45|t1s`).

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

## Build and flash

```bash
make                 # the arm-zephyr-eabi-gcc from a Zephyr SDK is found automatically; otherwise arm-none-eabi-
make flash           # openocd + ST-Link, through the board's TP1..TP5 (3V3, SWDIO, SWCLK, NRST, GND)
```

Headers come from ST's STM32CubeG0 and ARM's CMSIS. By default the Makefile uses the copies in a Zephyr workspace (`~/zephyrproject/modules/hal/...`); override with `CMSIS_DEVICE=` / `CMSIS_CORE=`.

## Not verified yet

- **Not run on real hardware yet** (no board exists).
- The MDIO bit-bang timing (~1 µs half-period, sampled while MDC is low) needs a scope.
- Timing: Linux's sfp driver waits 300 ms after power-up before probing the PHY. The firmware answers on I²C within a few ms of boot, but it doesn't release the PHY until TX_DISABLE goes low.

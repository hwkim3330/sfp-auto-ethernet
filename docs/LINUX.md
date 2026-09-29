# How Linux sees a copper SFP

Sources: [`drivers/net/mdio/mdio-i2c.c`](https://github.com/torvalds/linux/blob/master/drivers/net/mdio/mdio-i2c.c), `drivers/net/phy/sfp.c`, `drivers/net/phy/sfp-bus.c`.

- **The PHY appears at I²C address 0x40 + its MDIO address.** `SFP_PHY_ADDR` is 22, so the PHY is at **0x56**. Addresses 0x50 and 0x51 are refused, because they are the EEPROM.
- **Clause 22 frame:** write a 1-byte register address, then read or write **16-bit big-endian** data.
- **Clause 45** is also supported, but the two directions use different frames:
  - read: write `[0x20|devad, reg_hi, reg_lo]`, then read 2 bytes
  - write: a **single 5-byte message** `[devad, reg_hi, reg_lo, val_hi, val_lo]`, **without the 0x20 bit** (see `mdio-i2c.c`)
  - Linux only uses C45 for modules whose EEPROM byte 36 (extended compliance) is 10G/5G/**2.5GBASE-T (0x1E)**.
  - Rollball (0x51, page 3) is used only through vendor-name quirks (FS "SFP-2.5G-T" and others).
  - The firmware handles C22 and both C45 frames (`fw/main.c`).
- **When the PHY is probed:** if EEPROM byte 6 bit 3 (1000BASE-T) is set, Linux probes Clause 22 at address 22. Otherwise it does not probe at all.
  - So our modules set that bit.
  - The MCU bridges I²C 0x56 → MDIO.
  - The PHY drivers for the DP83TG720 (`dp83tg720.c`) and DP83869 (`dp83869.c`) have Clause 22 IDs, so they can match.
- **Interface:** `e1000_base_t` means 1000baseT, and **SGMII is picked ahead of 1000BASE-X**.
- **Timing:**
  - T_WAIT 50 ms
  - T_START_UP 300 ms
  - PHY probe: 25 retries at 50 ms
  - TX fault: 5 retries
  - The MCU must be up and answering on I²C well within 300 ms.
- **Quirks** are matched on vendor and part strings. For example, "OEM"/"SFP-GE-T" is set to ignore TX_FAULT.

## The T1 speed problem

The Linux PHY driver for a T1 part expects to manage a T1 link: master/slave, 100 or 1000. The host-side SFP layer, however, only knows this module as "1000BASE-T". So there are two paths:

1. **MCU-managed (default):** the MCU brings the link up itself, taking master/slave from a DIP switch or the EEPROM vendor area. Linux sees a plain SGMII link. No PHY probe is needed.
2. **Linux-managed:** answer on 0x56 so the `dp83tg720` driver binds, then set master/slave with `ethtool`.

The Intel X710/X722 is not Linux phylink; its firmware handles modules itself, so **host compatibility has to be tested card by card** (Technica says the same).

The first test host is the **LAN9692 EVB's own SFP+ cages**, on the bench. Whether those ports take a 1 Gb/s SGMII module still has to be checked in the VelocityDRIVE configuration; that is **unverified**.

/*
 * SFP module controller - STM32G031F6P6, bare metal, 16 MHz HSI.
 *
 * What the host sees on the SFP I2C bus (SCL/SDA, 100 kHz, host pull-ups):
 *   0x50  A0h: 256-byte ID EEPROM, emulated (SFF-8472 base + extended ID).
 *              Bytes 96..127 are writable: byte 96 bit 0 = T1 master.
 *   0x51  A2h: no diagnostics (A0h byte 92 = 0). Only byte 118, the power
 *              level control, is implemented; it acts on RJ45, the one
 *              variant that declares level 2. Every other byte reads 0x00.
 *   0x56  the PHY, in the protocol Linux's mdio-i2c speaks
 *         (drivers/net/mdio/mdio-i2c.c), both clauses:
 *           C22 read   write [reg]                         then read 2 bytes BE
 *           C22 write  write [reg, val_hi, val_lo]
 *           C45 read   write [0x20|devad, reg_hi, reg_lo]  then read 2 bytes BE
 *           C45 write  write [devad, reg_hi, reg_lo, val_hi, val_lo]   (no 0x20)
 *         Byte 0 < 0x20 and a 1- or 3-byte message is C22; the host's PHY
 *         address (22) is mapped onto the strapped one (PHYAD).
 *         C45 reaches the PHY natively (MDIO_C45_NATIVE, the RTL8221B) or
 *         through REGCR/ADDAR (the TI T1 parts, which are C22 devices).
 * One I2C peripheral answers all of them: OA2 = 0x50 with OA2MSK = 3 matches
 * 0x50..0x57 and ADDCODE says which was addressed. The unused addresses read
 * 0xFF.
 *
 * Everything runs in the main loop; SCL is clock-stretched while an MDIO
 * transaction runs, so there is no interrupt and no shared state to guard.
 *
 * Pins (TSSOP-20, see hw/t1/make_t1.py MCU map):
 *   PB7 SDA   PB6 SCL   (AF6, open drain)
 *   PA0 MDC   PA1 MDIO  (bit-banged; MDIO open drain, 2.2k to VDDIO on the board)
 *   (RJ45: PA0 MDIO, PA1 MDC, PA4 TX_FAULT, PA5 TX_DISABLE, PA6 RX_LOS)
 *   PA2 PHY_RST_N out   PA3 PHY_INT_N in
 *   PA4 TX_DISABLE in (pulled up on the board: high/open = disabled)
 *   PA5 RX_LOS out, open drain (high = no link)
 *   PA6 TX_FAULT out, open drain, held low (no fault)
 *   (T1S: PB8 SCL, PA10 SDA (pin 17, PA12 remapped), PC15 RX_LOS,
 *    PA4 TX_FAULT, PA6 TX_DISABLE - see hw/t1s/make_t1s.py)
 *
 * Register references: DP83TG720S-Q1 SNLS604G - BMSR (0x01) bit 2 link;
 * REGCR 0x0D / ADDAR 0x0E indirect access; PMA_PMD_CONTROL MMD1 0x0834
 * bit 14 = master. The same IEEE 1.2100 register sets master/slave on the
 * DP83TC812S (100BASE-T1) loadout.
 */
#include <stdint.h>
#include "stm32g031xx.h"

#ifndef VARIANT_PN
#define VARIANT_PN   "T1-1000"
#endif
/* HOST_FIBER: present as a 1000BASE-X optical SFP (no PHY behind 0x56 is
 * probed) and turn the PHY's SGMII auto-negotiation off, so the host sees a
 * plain 1000BASE-X lane. For hosts whose firmware manages "Cu SFP" PHYs by
 * part - Kontron's KSwitch D10 AN002 lists its 1000BASE-T modules as
 * Finisar/Methode (Marvell 88E1111) - rather than by the generic mdio-i2c
 * path Linux uses. On the D10 the port is then set to speed 1000 full
 * duplex by hand, as for any 1000BASE-X SFP there. */
#ifndef HOST_FIBER
#define HOST_FIBER 0
#endif
/* VARIANT_RJ45: RTL8221B-VB-CG (100M/1G/2.5G). PHY address 1 (its LED
 * straps default to 1), native Clause 45, EEPROM byte 36 = 0x1E (2.5GBASE-T)
 * which makes Linux probe C45 at 0x56 and bind the realtek driver. */
#ifndef VARIANT_RJ45
#define VARIANT_RJ45 0
#endif
#if VARIANT_RJ45
#undef PHYAD
#define PHYAD 1
#define MDIO_C45_NATIVE 1
#endif
/* VARIANT_T1S: LAN8670 (10BASE-T1S) behind the FPGA's SGMII bridge
 * (hw/t1s). PHY address 0 (strapped), a Clause 22 part with MMD access
 * through REGCR/ADDAR. The MCU also minds the FPGA: it holds the PHY in
 * reset until the FPGA reports DONE, retries the configuration through
 * RECONFIG_N, and reports RX_LOS from the FPGA's FPGA_LINK (SGMII sync and
 * auto-negotiation done; 10BASE-T1S itself has no link status). */
#ifndef VARIANT_T1S
#define VARIANT_T1S 0
#endif
#if VARIANT_T1S && HOST_FIBER
#error "T1S: the host lane is SGMII at 10 Mb/s (the FPGA replicates each byte 100 times); it has no 1000BASE-X personality"
#endif
#ifndef VARIANT_TEXT
#define VARIANT_TEXT "100/1000BASE-T1 SGMII"
#endif

/* ------------------------------------------------------------------ time */
static volatile uint32_t ms;
void SysTick_Handler(void) { ms++; }

__attribute__((unused)) static void delay_ms(uint32_t n) { uint32_t t = ms; while (ms - t < n) { } }   /* T1S only now */

/* ------------------------------------------------------------------ GPIO */
#define PIN(n)   (1u << (n))
#if VARIANT_RJ45                /* hw/rj45/make_rj45.py MCU map: placed for its In2 bus's lane order */
#define MDC      1
#define MDIO     0
#define PHY_RST  2
#define PHY_INT  3
#define TX_DIS   5
#define RX_LOS   6
#define TX_FAULT 4
#else
#define MDC      0
#define MDIO     1
#define PHY_RST  2
#define PHY_INT  3
#define TX_DIS   4
#define RX_LOS   5
#define TX_FAULT 6
#endif
/* where TX_DISABLE, TX_FAULT and RX_LOS are. On T1S the MCU's pins follow
 * the SFP fingers' order along the board's two In2 buses: RX_LOS and SCL go
 * along the north edge (PC15, pin 3; PB8, pin 1), SDA, TX_DISABLE and
 * TX_FAULT along the south edge (PA10 on pin 17, PA6, PA4) */
#if VARIANT_T1S
#define TXDIS_PORT  GPIOA
#define TXDIS_PIN   6
#define TXF_PORT    GPIOA
#define TXF_PIN     4
#define RXLOS_PORT  GPIOC
#define RXLOS_PIN   15
#else
#define TXDIS_PORT  GPIOA
#define TXDIS_PIN   TX_DIS
#define TXF_PORT    GPIOA
#define TXF_PIN     TX_FAULT
#define RXLOS_PORT  GPIOA
#define RXLOS_PIN   RX_LOS
#endif
#define los_set() (RXLOS_PORT->BSRR = PIN(RXLOS_PIN))     /* released: loss of signal */
#define los_clr() (RXLOS_PORT->BRR = PIN(RXLOS_PIN))
#if VARIANT_T1S                /* hw/t1s/make_t1s.py MCU map */
#define FPGA_LINK 7            /* PA7 (pin 14) in: SGMII up, from the FPGA */
#define FPGA_DONE 11           /* PA11 (pin 16) in: configuration done (4.7k pull-up) */
#define FPGA_RECONF 0          /* PB0 (pin 15) out, open drain: low = reload (4.7k pull-up).
                                  PB1, PB2 and PA8 share the pin and stay analog */
#endif

static void gpio_mode(GPIO_TypeDef *g, int pin, uint32_t mode, int od, uint32_t pull)
{
    g->MODER = (g->MODER & ~(3u << (2 * pin))) | (mode << (2 * pin));
    g->OTYPER = (g->OTYPER & ~PIN(pin)) | ((od ? 1u : 0u) << pin);
    g->PUPDR = (g->PUPDR & ~(3u << (2 * pin))) | (pull << (2 * pin));
    g->OSPEEDR |= 3u << (2 * pin);
}

static inline void pa_set(int p) { GPIOA->BSRR = PIN(p); }
static inline void pa_clr(int p) { GPIOA->BRR = PIN(p); }
static inline int pa_get(int p) { return (GPIOA->IDR >> p) & 1; }

/* ------------------------------------------------------------------ MDIO */
static void mdio_delay(void) { for (volatile int i = 0; i < 4; i++) { } }   /* ~1 us half period */

static void mdc_pulse(void)
{
    pa_set(MDC); mdio_delay();
    pa_clr(MDC); mdio_delay();
}

static void mdio_out(uint32_t v, int bits)
{
    for (int i = bits - 1; i >= 0; i--) {
        if ((v >> i) & 1) pa_set(MDIO); else pa_clr(MDIO);   /* open drain: set = release */
        mdio_delay();
        mdc_pulse();
    }
}

static uint16_t mdio_read(uint8_t phy, uint8_t reg)
{
    mdio_out(0xFFFFFFFFu, 32);                                   /* preamble */
    mdio_out((0x1u << 12) | (0x2u << 10) | ((phy & 31u) << 5) | (reg & 31u), 14);
    pa_set(MDIO);                                                /* release: turnaround */
    mdc_pulse(); mdc_pulse();              /* TA: Z, then the PHY drives 0 */
    uint16_t v = 0;
    for (int i = 0; i < 16; i++) {         /* the PHY changes MDIO after a rising edge,
                                              so sample in the low half, then clock */
        v = (uint16_t)((v << 1) | (uint16_t)pa_get(MDIO));
        mdc_pulse();
    }
    mdc_pulse();                           /* idle */
    return v;
}

static void mdio_write(uint8_t phy, uint8_t reg, uint16_t val)
{
    mdio_out(0xFFFFFFFFu, 32);
    mdio_out((0x1u << 30) | (0x1u << 28) | ((uint32_t)(phy & 31u) << 23) |
             ((uint32_t)(reg & 31u) << 18) | (0x2u << 16) | val, 32);
    pa_set(MDIO);
}

#ifndef PHYAD
#define PHYAD 0
#endif
#ifndef MDIO_C45_NATIVE
#define MDIO_C45_NATIVE 0
#endif

/* Clause 45 frames: ST = 00, then an ADDRESS frame and a READ/WRITE frame */
static void c45_frame(uint32_t op, uint8_t devad, uint16_t data)
{
    mdio_out(0xFFFFFFFFu, 32);
    mdio_out((0x0u << 30) | (op << 28) | ((uint32_t)(PHYAD & 31u) << 23) |
             ((uint32_t)(devad & 31u) << 18) | (0x2u << 16) | data, 32);
    pa_set(MDIO);
}

static uint16_t c45_read(uint8_t devad, uint16_t reg)
{
    c45_frame(0x0u, devad, reg);                      /* address */
    mdio_out(0xFFFFFFFFu, 32);
    mdio_out((0x0u << 12) | (0x3u << 10) | ((PHYAD & 31u) << 5) | (devad & 31u), 14);
    pa_set(MDIO);
    mdc_pulse(); mdc_pulse();
    uint16_t v = 0;
    for (int i = 0; i < 16; i++) { v = (uint16_t)((v << 1) | (uint16_t)pa_get(MDIO)); mdc_pulse(); }
    mdc_pulse();
    return v;
}

static void c45_write(uint8_t devad, uint16_t reg, uint16_t val)
{
    c45_frame(0x0u, devad, reg);                      /* address */
    c45_frame(0x1u, devad, val);                      /* write */
}
static void mmd_write(uint8_t devad, uint16_t reg, uint16_t val)
{
    if (MDIO_C45_NATIVE) { c45_write(devad, reg, val); return; }
    mdio_write(PHYAD, 0x0D, devad);
    mdio_write(PHYAD, 0x0E, reg);
    mdio_write(PHYAD, 0x0D, (uint16_t)(0x4000u | devad));
    mdio_write(PHYAD, 0x0E, val);
}

static uint16_t mmd_read(uint8_t devad, uint16_t reg)
{
    if (MDIO_C45_NATIVE) return c45_read(devad, reg);
    mdio_write(PHYAD, 0x0D, devad);
    mdio_write(PHYAD, 0x0E, reg);
    mdio_write(PHYAD, 0x0D, (uint16_t)(0x4000u | devad));
    return mdio_read(PHYAD, 0x0E);
}

/* ------------------------------------------------------------------ A0h */
static uint8_t a0[256];

static void put_str(int at, int len, const char *s)
{
    for (int i = 0; i < len; i++) a0[at + i] = (uint8_t)(*s ? *s++ : ' ');
}

static void a0_checksums(void)
{
    uint8_t c = 0;
    for (int i = 0; i < 63; i++) c += a0[i];
    a0[63] = c;
    c = 0;
    for (int i = 64; i < 95; i++) c += a0[i];
    a0[95] = c;
}

static void a0_init(void)
{
    a0[0] = 0x03;            /* SFP */
    a0[1] = 0x04;            /* serial ID via two-wire */
    a0[2] = 0x80;            /* connector: vendor specific (H-MTD) */
    /* SFF-8024 has no code for 100/1000BASE-T1, so the module borrows one:
     * 1000BASE-T makes Linux probe the PHY; 1000BASE-SX makes a switch treat
     * it as a plain 1000BASE-X lane */
    a0[6] = HOST_FIBER ? 0x01 : 0x08;
#if VARIANT_RJ45
    /* like FS SFP-2.5G-T on a switch (all codes 0, BR 2.5G); like a Linux
     * 2.5GBASE-T module otherwise (byte 36 = 0x1E -> C45 PHY probe) */
    a0[6] = HOST_FIBER ? 0x00 : 0x08;
    a0[36] = HOST_FIBER ? 0x00 : 0x1E;
    /* power level 2 (up to 1.5 W): the PHY alone peaks near 1 W at 2.5G.
     * Linux reads byte 64 only from a module claiming SFF-8472 Rev 10.2 or
     * later (byte 94), and then grants the level through A2h byte 118 */
    a0[64] = 0x02;
    a0[94] = 0x03;           /* SFF-8472 Rev 10.2: A2h byte 118 is implemented */
#endif
#if VARIANT_T1S
    a0[2] = 0x80;            /* connector: vendor specific (2-pin JST PH) */
    a0[18] = 25;             /* a 10BASE-T1S mixing segment: 25 m */
#endif
    a0[11] = 0x01;           /* 8B/10B */
    /* nominal signalling rate, units of 100 MBd: the host lane's line rate */
    a0[12] = VARIANT_RJ45 ? 31 : 13;   /* 3.125 GBd (2500BASE-X) / 1.25 GBd (SGMII) */
    if (!VARIANT_T1S) a0[18] = 15;             /* copper length, m */
    put_str(20, 16, "SFP-AUTO-ETH");
    put_str(40, 16, VARIANT_PN);
    put_str(56, 4, "0.1");
    a0[65] = 0x12;           /* TX_DISABLE implemented, RX_LOS implemented */
    put_str(68, 16, "0001");
    put_str(84, 8, "260929");
    a0[92] = 0x00;           /* no digital diagnostics: host leaves A2h alone */
    a0[96] = 0x00;           /* vendor area: bit 0 = T1 master */
#if VARIANT_T1S
    /* PLCA, in the vendor area the host may write (read at every 50 ms tick):
     *   120 bit 0 = PLCA on (off: plain CSMA/CD, which works on any segment)
     *   121 = local node ID (0 = the coordinator)   122 = node count
     *   123 = max burst count (0 = one frame per transmit opportunity)
     * Linux's microchip_t1s driver binds to the PHY behind 0x56 as well, and
     * `ethtool --set-plca-cfg` there overrides these. */
    put_str(97, 23, VARIANT_TEXT);
    a0[120] = 0x00; a0[121] = 0; a0[122] = 8; a0[123] = 0;
#else
    put_str(97, 31, VARIANT_TEXT);
#endif
    a0_checksums();
}

/* ------------------------------------------------------------------ A2h */
/* No diagnostics (A0h byte 92 = 0); only byte 118, the power level control
 * of SFF-8472 / SFF-8419: bit 0 the host's select (1 = level 2 allowed),
 * bit 1 the level the module runs at. Every other byte reads 0. */
static uint8_t a2_118;

/* ------------------------------------------------------------------ PHY */
static int master_applied = -1;

#if VARIANT_RJ45
/* RTL8221B SerDes (datasheet 8.6.1, MMD30 0x697A[5:0]): 0 = 2500BASE-X +
 * SGMII switching with link speed, 2 = 2500BASE-X only (rate adaptor, pause).
 * The part powers up in HiSGMII (3) and has no strap, so the MCU sets it.
 * The four writes around it are the ones Linux's realtek driver makes in
 * rtl822xb_config_init (drivers/net/phy/realtek/realtek_main.c), MMD30. */
static void rtl8221b_serdes(uint16_t mode)
{
    mmd_write(30, 0x75F3, 0x0000);
    uint16_t v = mmd_read(30, 0x697A);
    mmd_write(30, 0x697A, (uint16_t)((v & ~0x003Fu) | mode));
    mmd_write(30, 0x6A04, 0x0503);
    mmd_write(30, 0x6F10, 0xD455);
    mmd_write(30, 0x6F11, 0x8020);
}
#endif

#if VARIANT_T1S
/* LAN8670/1/2 configuration: Microchip AN1699 Rev G (DS60001699G, Oct 2025).
 * Which table applies follows the silicon revision in PHY_ID2[3:0]
 * (AN1699 Table 1): 0101 = C2 (the LAN8670C2 the BOM orders), 0110 = D0 and
 * later. All writes in MMD 31.
 * C2 (Tables 3-1, 3-2; the same writes as Linux's microchip_t1s.c
 * lan867x_revc_config_init): two values carry per-part trim offsets read
 * back through the CFGPARAM window (0xD8 address, 0xDA control, 0xD9 data).
 * D0 (Table 2-1): fixed values; LSCTL (0x0012) = 0x1001 keeps C2's
 * behaviour, link status always up and no pin output. */
static int lan867x_rev;

static int8_t cfg_offset(uint16_t addr)
{
    mmd_write(31, 0x00D8, addr);
    mmd_write(31, 0x00DA, 0x0002);                  /* read enable */
    uint16_t v = mmd_read(31, 0x00D9) & 0x1Fu;      /* 5-bit signed */
    return (int8_t)((v & 0x10u) ? (v | 0xE0u) : v);
}

static void lan867x_init(void)
{
    for (int i = 0; i < 20 && !(mmd_read(31, 0x0019) & 0x0800u); i++) delay_ms(1);   /* STS2 reset complete */
    lan867x_rev = mdio_read(PHYAD, 0x03) & 0x000F;
    if (lan867x_rev >= 6) {                         /* D0 and later */
        static const uint16_t reg[9] = { 0x0037, 0x008A, 0x0118, 0x00D6, 0x0082, 0x00FD, 0x00FD, 0x0091, 0x0012 };
        static const uint16_t val[9] = { 0x0800, 0xBFC0, 0x029C, 0x1001, 0x001C, 0x0C0B, 0x8C07, 0x9660, 0x1001 };
        for (int i = 0; i < 9; i++) mmd_write(31, reg[i], val[i]);
        return;
    }
    static const uint16_t reg[9] = { 0x00D0, 0x00E0, 0x00E9, 0x00F5, 0x00F4, 0x00F8, 0x00F9, 0x0081, 0x0091 };
    static const uint16_t val[9] = { 0x3F31, 0xC000, 0x9E50, 0x1CF8, 0xC020, 0xB900, 0x4E53, 0x0080, 0x9660 };
    static const uint16_t sqi[12] = { 0x0103, 0x0910, 0x1D26, 0x002A, 0x0103, 0x070D,
                                      0x1720, 0x0027, 0x0509, 0x0E13, 0x1C25, 0x002B };
    int o0 = cfg_offset(0x0004), o1 = cfg_offset(0x0008);
    for (int i = 0; i < 9; i++) {
        mmd_write(31, reg[i], val[i]);
        if (i == 1) {
            mmd_write(31, 0x0084, (uint16_t)((((9 + o0) & 0x3F) << 10) | (((14 + o0) & 0x3F) << 4) | 0x03));
            mmd_write(31, 0x008A, (uint16_t)(((40 + o1) & 0x3F) << 10));
        }
    }
    mmd_write(31, 0x00AD, (uint16_t)((((5 + o0) & 0x3F) << 8) | ((9 + o0) & 0x3F)));
    mmd_write(31, 0x00AE, (uint16_t)((((9 + o0) & 0x3F) << 8) | ((14 + o0) & 0x3F)));
    mmd_write(31, 0x00AF, (uint16_t)((((17 + o0) & 0x3F) << 8) | ((22 + o0) & 0x3F)));
    for (int i = 0; i < 12; i++) mmd_write(31, (uint16_t)(0x00B0 + i), sqi[i]);
}

/* OPEN Alliance TC14 PLCA registers, MMD 31: CTRL0 0xCA01 (bit 15 enable),
 * CTRL1 0xCA02 (the coordinator, node ID 0, writes the node count in 15:8;
 * a follower its ID in 7:0: AN1699 2.2 / 3.4), STS 0xCA03 (bit 15 PST,
 * PLCA running), BURST 0xCA05 (max burst count 15:8, burst timer 7:0 =
 * 0x80 bit times, its reset value).
 * Collision detection, CDCTL0 0x0087 (read-modify-write, reserved fields):
 *   D0: CDAD (bit 9) lets the PHY turn it off while PLCA runs and back on
 *       when it falls back to CSMA/CD;
 *   C2: CDEN (bit 15) off while PLCA runs, on in CSMA/CD - including when
 *       the beacon is lost and the PHY falls back on its own, which
 *       plca_watch() catches through PST. */
static uint8_t plca_applied[4] = { 0xFF, 0xFF, 0xFF, 0xFF };
static int plca_running = -1;

static void cdctl0(uint16_t set, uint16_t clear)
{
    uint16_t v = mmd_read(31, 0x0087);
    mmd_write(31, 0x0087, (uint16_t)((v | set) & ~clear));
}

static void plca_apply(void)
{
    mmd_write(31, 0xCA01, 0x0000);                  /* off while it changes */
    mmd_write(31, 0xCA02, (uint16_t)(a0[121] == 0 ? (a0[122] << 8) : a0[121]));
    mmd_write(31, 0xCA05, (uint16_t)((a0[123] << 8) | 0x80u));
    if (a0[120] & 1) {
        mmd_write(31, 0xCA01, 0x8000);
        if (lan867x_rev >= 6) cdctl0(0x0200, 0);
        else cdctl0(0, 0x8000);
    } else {
        cdctl0(lan867x_rev >= 6 ? 0x0200 : 0x8000, 0);   /* AN1699 Table 2-3 / CDEN back on */
    }
    plca_running = (a0[120] & 1) ? 1 : 0;
    for (int i = 0; i < 4; i++) plca_applied[i] = a0[120 + i];
}

/* C2 only: follow PST, so collision detection is back on whenever the PHY
 * has fallen back to CSMA/CD (no beacon), and off again once PLCA runs */
static void plca_watch(void)
{
    if (lan867x_rev >= 6 || !(a0[120] & 1)) return;
    int pst = (mmd_read(31, 0xCA03) & 0x8000u) != 0;
    if (pst == plca_running) return;
    if (pst) cdctl0(0, 0x8000); else cdctl0(0x8000, 0);
    plca_running = pst;
}

static int plca_changed(void)
{
    for (int i = 0; i < 4; i++) if (plca_applied[i] != a0[120 + i]) return 1;
    return 0;
}
#endif

#if VARIANT_RJ45
/* Power level 1 (<= 1 W) until the host grants level 2: advertise 100M/1G
 * only, then 2.5GBASE-T as well (MMD7 0x0020 bit 7, the MultiGBASE-T AN
 * control register), restarting auto-negotiation (MMD7 0x0000 bits 12/9).
 * On a fibre-personality host (HOST_FIBER: the D10, which links 2.5G
 * modules only at a fixed 2500 and never writes A2h) the module starts at
 * level 2. A host PHY driver that rewrites the advertisement overrides this. */
static int pl2_applied = -1;

static void rtl8221b_power_level(int pl2)
{
    uint16_t v = mmd_read(7, 0x0020);
    v = (uint16_t)(pl2 ? (v | 0x0080u) : (v & ~0x0080u));
    mmd_write(7, 0x0020, v);
    mmd_write(7, 0x0000, (uint16_t)(mmd_read(7, 0x0000) | 0x1200u));
    pl2_applied = pl2;
    a2_118 = (uint8_t)((a2_118 & ~0x02u) | (pl2 ? 0x02u : 0x00u));
}

static int pl2_wanted(void) { return HOST_FIBER || (a2_118 & 1); }
#endif

static void phy_apply_config(void)
{
#if VARIANT_T1S
    lan867x_init();
    plca_apply();
    master_applied = a0[96] & 1;                    /* T1S has no master/slave */
    return;
#endif
#if VARIANT_RJ45
    /* on a switch the host lane is fixed at 2500BASE-X (the D10 links FS's
     * module only at speed 2500); on Linux, switch with speed and let the
     * driver take over when it binds */
    rtl8221b_serdes(HOST_FIBER ? 2 : 0);
    rtl8221b_power_level(pl2_wanted());
    master_applied = a0[96] & 1;
    return;
#endif
    int want = a0[96] & 1;
    /* SGMII_CTRL_1 (MMD1F 0x0608), same on the DP83TG720 and DP83TC812.
     * Bits 7/8 (tx/rx polarity invert) stay at their reset 0: the T1 board
     * runs both lanes straight, P to P. (Until 2026-10 the SFP edge was drawn
     * mirrored and both lanes came out inverted; these bits undid that.)
     * Bit 0 is SGMII AN, off for a fibre-personality host (HOST_FIBER), and
     * off on the DP83TC812 (PHYIDR2 model 0x27): it only runs 100 Mb/s and
     * SNLS654D 7.4.12.4 says SGMII AN is disabled by clearing bit 0. The
     * DP83TG720 is model 0x28. */
    {
        int tc812 = ((mdio_read(PHYAD, 0x03) >> 4) & 0x3Fu) == 0x27u;
        uint16_t c = mmd_read(0x1F, 0x0608);
        c &= (uint16_t)~0x0180u;
        if (HOST_FIBER || tc812) c &= (uint16_t)~1u;
        mmd_write(0x1F, 0x0608, c);
    }
    uint16_t v = mmd_read(1, 0x0834);
    v = (uint16_t)(want ? (v | 0x4000u) : (v & ~0x4000u));
    mmd_write(1, 0x0834, v);
    master_applied = want;
}

/* TX_DISABLE: INF-8074i wants the transmitter off within 10 us of it rising
 * (t_off) and back within 1 ms of it falling (t_on). The pin interrupts on
 * both edges and the handler moves the PHY's reset at once; the settings that
 * need MDIO follow from the main loop 70 ms after release: the DP83TG720
 * wants 65 ms before its first MDIO frame, the RTL8221B 55 ms. Until then the
 * 0x56 bridge answers 0xFFFF (Linux retries its PHY probe for ~1.25 s). The PHY's own link training comes on top of
 * t_on, as on every copper SFP. The main loop's poll stays as a backstop. */
static volatile int phy_held = 1;  /* 1 while TX_DISABLE (or, on T1S, no FPGA) holds the PHY in reset */
static volatile uint32_t cfg_due;   /* ms tick to apply the PHY settings at, 0 = none */

static int txdis_high(void) { return (int)((TXDIS_PORT->IDR >> TXDIS_PIN) & 1); }
static int phy_ready(void) { return !phy_held && !cfg_due; }

static void phy_hold(int hold)
{
    __disable_irq();
    if (hold && !phy_held) {
        pa_clr(PHY_RST);
        phy_held = 1;
        cfg_due = 0;
    } else if (!hold && phy_held) {
        pa_set(PHY_RST);
        phy_held = 0;
        cfg_due = (ms + 70u) | 1u;     /* never 0 */
    }
    __enable_irq();
}

/* T1S: the PHY's MII means nothing until the FPGA is configured */
static int phy_may_run(void)
{
#if VARIANT_T1S
    return pa_get(FPGA_DONE);
#else
    return 1;
#endif
}

void EXTI4_15_IRQHandler(void)
{
    EXTI->RPR1 = PIN(TXDIS_PIN);
    EXTI->FPR1 = PIN(TXDIS_PIN);
    if (txdis_high()) {
        pa_clr(PHY_RST);
        phy_held = 1;
        cfg_due = 0;
    } else if (phy_held && phy_may_run()) {
        pa_set(PHY_RST);
        phy_held = 0;
        cfg_due = (ms + 70u) | 1u;
    }
}

/* ------------------------------------------------------------------ I2C slave */
enum { DEV_A0 = 0x50, DEV_A2 = 0x51, DEV_PHY = 0x56 };
static uint8_t dev, off, nwr, phy_reg, phy_buf[2], phy_wr[5];
static int nrd;

static void i2c_init(void)
{
    RCC->APBENR1 |= RCC_APBENR1_I2C1EN;
    I2C1->CR1 = 0;
    I2C1->TIMINGR = 0x00303D5Bu;                 /* 100 kHz at 16 MHz (CubeMX) */
    I2C1->OAR1 = 0;
    I2C1->OAR2 = I2C_OAR2_OA2EN | (DEV_A0 << 1) | (3u << I2C_OAR2_OA2MSK_Pos);   /* 0x50..0x57 */
    I2C1->CR1 = I2C_CR1_PE;                      /* stretching on (NOSTRETCH = 0) */
}

static uint8_t next_tx(void)
{
    switch (dev) {
    case DEV_A0:  return a0[off++];
    case DEV_A2:  return off++ == 118 ? a2_118 : 0x00;
    case DEV_PHY:
        if (nrd == 2) {                          /* mdio-i2c auto-increments */
            uint16_t v = phy_ready() ? mdio_read(PHYAD, ++phy_reg) : 0xFFFFu;
            phy_buf[0] = (uint8_t)(v >> 8); phy_buf[1] = (uint8_t)v; nrd = 0;
        }
        return phy_buf[nrd++];
    default:      return 0xFF;
    }
}

static void i2c_poll(void)
{
    uint32_t isr = I2C1->ISR;
    if (isr & I2C_ISR_ADDR) {
        uint8_t code = (uint8_t)((isr & I2C_ISR_ADDCODE) >> I2C_ISR_ADDCODE_Pos);
        int read = (isr & I2C_ISR_DIR) != 0;
        dev = code;
        if (read) {
            if (dev == DEV_PHY) {                /* SCL is stretched while this runs */
                uint16_t v = !phy_ready() ? 0xFFFFu
                    : (nwr == 3 && (phy_wr[0] & 0x20))
                    ? mmd_read(phy_wr[0] & 31u, (uint16_t)((phy_wr[1] << 8) | phy_wr[2]))
                    : mdio_read(PHYAD, phy_reg);
                phy_buf[0] = (uint8_t)(v >> 8); phy_buf[1] = (uint8_t)v; nrd = 0;
            }
            I2C1->ISR |= I2C_ISR_TXE;            /* flush, so TXIS asks for fresh data */
        } else {
            nwr = 0;
        }
        I2C1->ICR = I2C_ICR_ADDRCF;
    }
    if (isr & I2C_ISR_RXNE) {
        uint8_t b = (uint8_t)I2C1->RXDR;
        if (dev == DEV_PHY) {
            if (nwr < 5) phy_wr[nwr] = b;
            if (nwr == 0) phy_reg = b & 31u;
        } else if (nwr == 0) {
            off = b;
        } else {
            if (dev == DEV_A0 && off >= 96 && off < 128) a0[off] = b;   /* vendor area only */
            if (dev == DEV_A2 && off == 118) a2_118 = (uint8_t)((a2_118 & ~1u) | (b & 1u));   /* power level select */
            off++;
        }
        nwr++;
    }
    if (isr & I2C_ISR_TXIS) I2C1->TXDR = next_tx();
    if (isr & I2C_ISR_NACKF) I2C1->ICR = I2C_ICR_NACKCF;
    if (isr & I2C_ISR_STOPF) {
        I2C1->ICR = I2C_ICR_STOPCF;
        if (dev == DEV_PHY && !phy_ready())
            ;                                                         /* not up yet: dropped */
        else if (dev == DEV_PHY && nwr == 3 && phy_wr[0] < 0x20)          /* C22 write */
            mdio_write(PHYAD, phy_wr[0] & 31u, (uint16_t)((phy_wr[1] << 8) | phy_wr[2]));
        else if (dev == DEV_PHY && nwr == 5)                          /* C45 write */
            mmd_write(phy_wr[0] & 31u, (uint16_t)((phy_wr[1] << 8) | phy_wr[2]),
                      (uint16_t)((phy_wr[3] << 8) | phy_wr[4]));
    }
}

/* ------------------------------------------------------------------ main */
int main(void)
{
    RCC->IOPENR |= RCC_IOPENR_GPIOAEN | RCC_IOPENR_GPIOBEN | RCC_IOPENR_GPIOCEN;
    SysTick->LOAD = 16000 - 1;                   /* 1 ms */
    SysTick->VAL = 0;
    SysTick->CTRL = SysTick_CTRL_CLKSOURCE_Msk | SysTick_CTRL_TICKINT_Msk | SysTick_CTRL_ENABLE_Msk;

    pa_clr(PHY_RST);
    gpio_mode(GPIOA, PHY_RST, 1, 0, 0);          /* PHY held in reset first */
    pa_clr(MDC);
    gpio_mode(GPIOA, MDC, 1, 0, 0);
    pa_set(MDIO);
    gpio_mode(GPIOA, MDIO, 1, 1, 0);             /* open drain, board pull-up */
    gpio_mode(GPIOA, PHY_INT, 0, 0, 1);
    gpio_mode(TXDIS_PORT, TXDIS_PIN, 0, 0, 0);
    /* EXTI on both edges of TX_DISABLE (EXTICR: port A = 0, C = 2) */
    RCC->APBENR2 |= RCC_APBENR2_SYSCFGEN;
    EXTI->EXTICR[TXDIS_PIN >> 2] = (EXTI->EXTICR[TXDIS_PIN >> 2] & ~(0xFFu << (8 * (TXDIS_PIN & 3)))) |
                                   ((TXDIS_PORT == GPIOC ? 2u : 0u) << (8 * (TXDIS_PIN & 3)));
    EXTI->RTSR1 |= PIN(TXDIS_PIN);
    EXTI->FTSR1 |= PIN(TXDIS_PIN);
    EXTI->IMR1 |= PIN(TXDIS_PIN);
    los_set();
    gpio_mode(RXLOS_PORT, RXLOS_PIN, 1, 1, 0);   /* released = LOS (no link yet) */
    TXF_PORT->BRR = PIN(TXF_PIN);
    gpio_mode(TXF_PORT, TXF_PIN, 1, 1, 0);       /* held low: no fault */
#if VARIANT_T1S
    gpio_mode(GPIOA, FPGA_LINK, 0, 0, 0);        /* in; R26 pulls it up (it is also the FPGA's SSPI_CS_N) */
    gpio_mode(GPIOA, FPGA_DONE, 0, 0, 0);
    GPIOB->BSRR = PIN(FPGA_RECONF);
    gpio_mode(GPIOB, FPGA_RECONF, 1, 1, 0);      /* released */
#endif
#if VARIANT_T1S
    /* PB8 SCL (pin 1, which PB7 shares: PB7 stays analog) and PA10 SDA (pin
     * 17, PA12's pad remapped to PA10), both AF6 I2C1, open drain */
    SYSCFG->CFGR1 |= SYSCFG_CFGR1_PA12_RMP;
    gpio_mode(GPIOB, 8, 2, 1, 0);
    GPIOB->AFR[1] = (GPIOB->AFR[1] & ~(0xFu << (4 * (8 - 8)))) | (6u << (4 * (8 - 8)));
    gpio_mode(GPIOA, 10, 2, 1, 0);
    GPIOA->AFR[1] = (GPIOA->AFR[1] & ~(0xFu << (4 * (10 - 8)))) | (6u << (4 * (10 - 8)));
#else
    for (int p = 6; p <= 7; p++) {               /* PB6 SCL, PB7 SDA: AF6, open drain */
        gpio_mode(GPIOB, p, 2, 1, 0);
        GPIOB->AFR[0] = (GPIOB->AFR[0] & ~(0xFu << (4 * p))) | (6u << (4 * p));
    }
#endif
    a0_init();
    i2c_init();
    NVIC_EnableIRQ(EXTI4_15_IRQn);               /* TX_DISABLE edges, from here on */

    uint32_t last = 0;
#if VARIANT_T1S
    uint32_t cfg_start = 0;                      /* the FPGA loads from its flash at power-up */
    int reloads = 0;
#endif
    for (;;) {
        i2c_poll();
        /* every 5 ms: RX_LOS follows the link within a tick (INF-8074i asks
         * 100 us, which a copper PHY's own link-fail timers exceed anyway) */
        if (ms - last < 5) continue;
        last = ms;
#if VARIANT_T1S
        /* the FPGA must be configured before the PHY's MII means anything.
         * GW5AT MSPI boot takes well under a second; if DONE has not come
         * after 1.5 s, pulse RECONFIG_N (Gowin: low >= 25 ns) and try again,
         * three times at most - a blank flash never will */
        int done = pa_get(FPGA_DONE);
        if (!done && reloads < 3 && ms - cfg_start > 1500) {
            GPIOB->BRR = PIN(FPGA_RECONF);
            delay_ms(1);
            GPIOB->BSRR = PIN(FPGA_RECONF);
            cfg_start = ms;
            reloads++;
        }
        phy_hold(txdis_high() || !done);
        if (phy_held) { los_set(); continue; }
        if (cfg_due) {                           /* released 70 ms ago? set the PHY up */
            if ((int32_t)(ms - cfg_due) < 0) continue;
            cfg_due = 0;
            phy_apply_config();
        }
        if (plca_changed()) plca_apply();
        if ((ms % 50u) < 5u) plca_watch();       /* every ~50 ms */
        if (pa_get(FPGA_LINK)) los_clr(); else los_set();
        continue;
#endif
        phy_hold(txdis_high());                  /* TX_DISABLE high/open: PHY in reset */
        if (phy_held) { los_set(); continue; }
        if (cfg_due) {                           /* released 70 ms ago? set the PHY up */
            if ((int32_t)(ms - cfg_due) < 0) continue;
            cfg_due = 0;
            phy_apply_config();
        }
        if ((a0[96] & 1) != master_applied) phy_apply_config();
#if VARIANT_RJ45
        if (pl2_wanted() != pl2_applied) rtl8221b_power_level(pl2_wanted());   /* the host wrote A2h 118 */
#endif
        (void)mdio_read(PHYAD, 0x01);            /* BMSR link bit latches low: read twice */
        if (mdio_read(PHYAD, 0x01) & 0x0004u) los_clr(); else los_set();
    }
}

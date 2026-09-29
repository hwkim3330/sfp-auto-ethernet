/*
 * SFP module controller - STM32G031F6P6, bare metal, 16 MHz HSI.
 *
 * What the host sees on the SFP I2C bus (SCL/SDA, 100 kHz, host pull-ups):
 *   0x50  A0h: 256-byte ID EEPROM, emulated (SFF-8472 base + extended ID).
 *              Bytes 96..127 are writable: byte 96 bit 0 = T1 master.
 *   0x51  A2h: diagnostics page - not implemented, reads as 0x00
 *              (byte 92 = 0 tells the host there is none).
 *   0x56  the PHY, in the protocol Linux's mdio-i2c speaks: write 1 byte =
 *         register, then read 2 bytes big-endian; or write 3 bytes =
 *         register + value. Clause 22, PHY address 22 on the host side,
 *         strapped address 0 on the MDIO side.
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
 *   PA2 PHY_RST_N out   PA3 PHY_INT_N in
 *   PA4 TX_DISABLE in (pulled up on the board: high/open = disabled)
 *   PA5 RX_LOS out, open drain (high = no link)
 *   PA6 TX_FAULT out, open drain, held low (no fault)
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
#ifndef VARIANT_TEXT
#define VARIANT_TEXT "100/1000BASE-T1 SGMII"
#endif

/* ------------------------------------------------------------------ time */
static volatile uint32_t ms;
void SysTick_Handler(void) { ms++; }

static void delay_ms(uint32_t n) { uint32_t t = ms; while (ms - t < n) { } }

/* ------------------------------------------------------------------ GPIO */
#define PIN(n)   (1u << (n))
#define MDC      0
#define MDIO     1
#define PHY_RST  2
#define PHY_INT  3
#define TX_DIS   4
#define RX_LOS   5
#define TX_FAULT 6

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

#define PHYAD 0
static void mmd_write(uint8_t devad, uint16_t reg, uint16_t val)
{
    mdio_write(PHYAD, 0x0D, devad);
    mdio_write(PHYAD, 0x0E, reg);
    mdio_write(PHYAD, 0x0D, (uint16_t)(0x4000u | devad));
    mdio_write(PHYAD, 0x0E, val);
}

static uint16_t mmd_read(uint8_t devad, uint16_t reg)
{
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
    a0[6] = 0x08;            /* 1000BASE-T: the bit that makes Linux probe the PHY
                                (SFF-8024 has no code for 100/1000BASE-T1) */
    a0[11] = 0x01;           /* 8B/10B */
    a0[12] = 13;             /* 1.3 GBd nominal, units of 100 MBd */
    a0[18] = 15;             /* copper length, m */
    put_str(20, 16, "SFP-AUTO-ETH");
    put_str(40, 16, VARIANT_PN);
    put_str(56, 4, "0.1");
    a0[65] = 0x12;           /* TX_DISABLE implemented, RX_LOS implemented */
    put_str(68, 16, "0001");
    put_str(84, 8, "260929");
    a0[92] = 0x00;           /* no digital diagnostics: host leaves A2h alone */
    a0[96] = 0x00;           /* vendor area: bit 0 = T1 master */
    put_str(97, 31, VARIANT_TEXT);
    a0_checksums();
}

/* ------------------------------------------------------------------ PHY */
static int master_applied = -1;

static void phy_apply_config(void)
{
    int want = a0[96] & 1;
    uint16_t v = mmd_read(1, 0x0834);
    v = (uint16_t)(want ? (v | 0x4000u) : (v & ~0x4000u));
    mmd_write(1, 0x0834, v);
    master_applied = want;
}

static int phy_held;           /* 1 while TX_DISABLE holds the PHY in reset */

static void phy_hold(int hold)
{
    if (hold == phy_held) return;
    phy_held = hold;
    if (hold) {
        pa_clr(PHY_RST);
    } else {
        pa_set(PHY_RST);
        delay_ms(20);          /* straps resample on reset release */
        phy_apply_config();
    }
}

/* ------------------------------------------------------------------ I2C slave */
enum { DEV_A0 = 0x50, DEV_A2 = 0x51, DEV_PHY = 0x56 };
static uint8_t dev, off, nwr, phy_reg, phy_buf[2], phy_wr[3];
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
    case DEV_A2:  off++; return 0x00;
    case DEV_PHY:
        if (nrd == 2) {                          /* mdio-i2c auto-increments */
            uint16_t v = mdio_read(PHYAD, ++phy_reg);
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
                uint16_t v = mdio_read(PHYAD, phy_reg);
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
            if (nwr < 3) phy_wr[nwr] = b;
            if (nwr == 0) phy_reg = b & 31u;
        } else if (nwr == 0) {
            off = b;
        } else {
            if (dev == DEV_A0 && off >= 96 && off < 128) a0[off] = b;   /* vendor area only */
            off++;
        }
        nwr++;
    }
    if (isr & I2C_ISR_TXIS) I2C1->TXDR = next_tx();
    if (isr & I2C_ISR_NACKF) I2C1->ICR = I2C_ICR_NACKCF;
    if (isr & I2C_ISR_STOPF) {
        I2C1->ICR = I2C_ICR_STOPCF;
        if (dev == DEV_PHY && nwr == 3)
            mdio_write(PHYAD, phy_wr[0] & 31u, (uint16_t)((phy_wr[1] << 8) | phy_wr[2]));
    }
}

/* ------------------------------------------------------------------ main */
int main(void)
{
    RCC->IOPENR |= RCC_IOPENR_GPIOAEN | RCC_IOPENR_GPIOBEN;
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
    gpio_mode(GPIOA, TX_DIS, 0, 0, 0);
    pa_set(RX_LOS);
    gpio_mode(GPIOA, RX_LOS, 1, 1, 0);           /* released = LOS (no link yet) */
    pa_clr(TX_FAULT);
    gpio_mode(GPIOA, TX_FAULT, 1, 1, 0);         /* held low: no fault */
    for (int p = 6; p <= 7; p++) {               /* PB6 SCL, PB7 SDA: AF6, open drain */
        gpio_mode(GPIOB, p, 2, 1, 0);
        GPIOB->AFR[0] = (GPIOB->AFR[0] & ~(0xFu << (4 * p))) | (6u << (4 * p));
    }
    a0_init();
    i2c_init();
    phy_held = 1;

    uint32_t last = 0;
    for (;;) {
        i2c_poll();
        if (ms - last < 50) continue;
        last = ms;
        phy_hold(pa_get(TX_DIS));                /* TX_DISABLE high/open: PHY in reset */
        if (phy_held) { pa_set(RX_LOS); continue; }
        if ((a0[96] & 1) != master_applied) phy_apply_config();
        (void)mdio_read(PHYAD, 0x01);            /* BMSR link bit latches low: read twice */
        if (mdio_read(PHYAD, 0x01) & 0x0004u) pa_clr(RX_LOS); else pa_set(RX_LOS);
    }
}

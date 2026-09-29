/* Vector table and reset handler for the STM32G031 (Cortex-M0+). */
#include <stdint.h>

extern uint32_t _sidata, _sdata, _edata, _sbss, _ebss, _estack;
int main(void);
void SysTick_Handler(void);

void Reset_Handler(void)
{
    uint32_t *s = &_sidata, *d = &_sdata;
    while (d < &_edata) *d++ = *s++;
    for (d = &_sbss; d < &_ebss; d++) *d = 0;
    main();
    for (;;) { }
}

static void Default_Handler(void) { for (;;) { } }

__attribute__((section(".isr_vector"), used))
void (*const vectors[16 + 32])(void) = {
    (void (*)(void))&_estack, Reset_Handler,
    Default_Handler,            /* NMI */
    Default_Handler,            /* HardFault */
    0, 0, 0, 0, 0, 0, 0,
    Default_Handler,            /* SVC */
    0, 0,
    Default_Handler,            /* PendSV */
    SysTick_Handler,
};

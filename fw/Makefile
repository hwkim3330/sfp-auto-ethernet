# SFP module controller firmware (STM32G031F6P6).
#
#   make                 -> build/sfp_ctrl.elf / .bin
#   make VARIANT=rj45    -> the RJ45 module's strings
#   make HOST=d10        -> for Kontron KSwitch D10: 1000BASE-X personality
#   make flash           -> openocd over SWD (TP1..TP5 on the board)
#
# Device and core headers come from ST's STM32CubeG0 and ARM's CMSIS; point
# CMSIS_DEVICE and CMSIS_CORE at any checkout of them (a Zephyr workspace has
# both under modules/hal).
ZGCC         := $(firstword $(wildcard $(HOME)/zephyr-sdk-*/arm-zephyr-eabi/bin/arm-zephyr-eabi-gcc))
CROSS        ?= $(if $(ZGCC),$(ZGCC:gcc=),arm-none-eabi-)
CMSIS_DEVICE ?= $(HOME)/zephyrproject/modules/hal/stm32/stm32cube/stm32g0xx/soc
CMSIS_CORE   ?= $(HOME)/zephyrproject/modules/hal/cmsis/CMSIS/Core/Include
VARIANT      ?= t1
HOST         ?= linux      # linux: 1000BASE-T + PHY at 0x56 | d10: 1000BASE-X, SGMII AN off

ifeq ($(VARIANT),rj45)
  DEFS = -DVARIANT_RJ45=1 -DVARIANT_PN='"RJ45-2500"' -DVARIANT_TEXT='"100M/1G/2.5GBASE-T 2500BASE-X"'
else ifeq ($(VARIANT),t1s)
  DEFS = -DVARIANT_PN='"T1S-10"' -DVARIANT_TEXT='"10BASE-T1S SGMII"'
else
  DEFS = -DVARIANT_PN='"T1-1000"' -DVARIANT_TEXT='"100/1000BASE-T1 SGMII"'
endif

ifeq ($(strip $(HOST)),d10)
  DEFS += -DHOST_FIBER=1
endif

CFLAGS = -mcpu=cortex-m0plus -mthumb -Os -g -Wall -Wextra -ffunction-sections -fdata-sections -ffreestanding -fno-tree-loop-distribute-patterns \
         -DSTM32G031xx -I$(CMSIS_DEVICE) -I$(CMSIS_CORE) $(DEFS)
LDFLAGS = -T stm32g031f6.ld -nostartfiles -nostdlib -Wl,--gc-sections -Wl,-Map=build/sfp_ctrl.map -lgcc

build/sfp_ctrl.elf: main.c startup.c stm32g031f6.ld | build
	$(CROSS)gcc $(CFLAGS) main.c startup.c $(LDFLAGS) -o $@
	$(CROSS)objcopy -O binary $@ build/sfp_ctrl.bin
	$(CROSS)size $@

build:
	mkdir -p build

flash: build/sfp_ctrl.elf
	openocd -f interface/stlink.cfg -f target/stm32g0x.cfg -c "program $< verify reset exit"

clean:
	rm -rf build

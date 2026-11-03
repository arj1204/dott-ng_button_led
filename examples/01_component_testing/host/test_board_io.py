from typing import List

from dottmi.breakpoint import HaltPoint, InterceptPoint, InterceptPointCmds
from dottmi.dott import DottConf, dott
from dottmi.target_mem import TypedPtr, TargetMemScoped
from dottmi.utils import DottConvert, log, DOTT_LABEL
import pytest   
import time
# + the same dott import lines as in test_example_functions.py

GPIOA_ODR  = 0x48000014
GPIOA_IDR  = 0x48000010
GPIOC_IDR  = 0x48000810
EXTI_SWIER = 0x40010410

def reg(addr):
    return int(dott().target.eval(f'*(volatile unsigned int *){addr:#x}'))

def reg_write(addr, value):
    dott().target.eval(f'*(volatile unsigned int *){addr:#x} = {value:#x}')

def reg_set_bits(addr, mask):
    dott().target.eval(f'*(volatile unsigned int *){addr:#x} |= {mask:#x}')

def reg_clear_bits(addr, mask):
    dott().target.eval(f'*(volatile unsigned int *){addr:#x} &= ~{mask:#x}')

class TestBoardIO:

    @pytest.mark.hw
    def test_init_configures_pins(self, target_load, target_reset):
        dt = dott().target
        dt.eval('board_io_init()')
        moder_a = reg(0x48000000)
        assert (moder_a >> 10) & 3 == 1, 'PA5 not configured as output'

    @pytest.mark.hw
    def test_led_on_off(self, target_load, target_reset):
        dt = dott().target
        dt.eval('board_io_init()')
        dt.eval('led_set(1)')
        assert (reg(GPIOA_ODR) >> 5) & 1 == 1
        assert (reg(GPIOA_IDR) >> 5) & 1 == 1    # real pin is high, not just the latch
        dt.eval('led_set(0)')
        assert (reg(GPIOA_IDR) >> 5) & 1 == 0

    @pytest.mark.hw
    def test_button_idle_reads_released(self, target_load, target_reset):
        dott().target.eval('board_io_init()')
        assert (reg(GPIOC_IDR) >> 13) & 1 == 1    # pulled up = not pressed
        assert int(dott().target.eval('button_read()')) == 0

    @pytest.mark.hw
    def test_led_via_register(self, target_load, target_reset):
        dott().target.eval('board_io_init()')
        reg_write(0x48000018, 1 << 5)          # BSRR: set PA5
        assert (reg(0x48000010) >> 5) & 1 == 1 # IDR: pin is high
        time.sleep(2)  # wait a bit to see the LED on   
        reg_write(0x48000028, 1 << 5)          # BRR: reset PA5
        assert (reg(0x48000010) >> 5) & 1 == 0


    @pytest.mark.hw
    def test_irq_diagnostics(self, target_load, target_reset):
        dt = dott().target
        dt.eval('board_io_init()')
        dt.eval('*(volatile unsigned int *)0x40010410 = (1 << 13)')   # EXTI_SWIER

        print('\nEXTI_PR  bit13 :', (reg(0x40010414) >> 13) & 1)       # 1 = edge latched
        print('NVIC_ISER bit7 :', (reg(0xE000E100) >> 7) & 1)          # 1 = EXTI4_15 enabled
        print('NVIC_ISPR bit7 :', (reg(0xE000E200) >> 7) & 1)          # 1 = pending in NVIC
        print('PRIMASK        :', dt.eval('$primask'))                 # 1 = all IRQs masked
        print('Vector entry   :', hex(reg(0x0800005C)))                # slot 16+7
        print('Handler addr   :', dt.eval('&EXTI4_15_IRQHandler'))

    @pytest.mark.hw
    def test_button_interrupt_toggles_led(self, target_load, target_reset):
        dt = dott().target
        dt.eval('board_io_init()')
        dt.eval('g_button_press_count = 0')
        dt.eval('led_set(0)')
        dt.eval(f'*(volatile unsigned int *){EXTI_SWIER:#x} = (1 << 13)')  # fake a press
        # The ISR only runs while the CPU runs; see note below
        assert int(dt.eval('g_button_press_count')) == 1
        assert int(dt.eval('led_get()')) == 1
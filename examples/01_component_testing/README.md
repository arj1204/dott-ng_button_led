# DOTT-ng on NUCLEO-F072RB: Test Selection, Custom Firmware Functions & Hardware Tests

Notes from working through the [DOTT-ng](https://tw-ghub.github.io/dott-ng_docu/) component-testing example (`examples/01_component_testing`) on an **STM32F072RB Nucleo-64** board with ST-LINK converted to J-Link.

DOTT-ng runs on **pytest**, so standard pytest features (selection, markers, fixtures) all apply.

---

## Contents

1. [Running only selected tests](#1-running-only-selected-tests)
2. [Registering custom markers in `pytest.ini`](#2-registering-custom-markers-in-pytestini)
3. [Adding a new firmware function and testing it](#3-adding-a-new-firmware-function-and-testing-it)
4. [Hardware-level test: user button and LED](#4-hardware-level-test-user-button-and-led)
5. [Debugging the interrupt test](#5-debugging-the-interrupt-test)
6. [Reading and writing registers from pytest](#6-reading-and-writing-registers-from-pytest)
7. [Troubleshooting summary](#7-troubleshooting-summary)

---

## 1. Running only selected tests

Run all commands from the example's host folder:

```powershell
cd examples\01_component_testing\host
```

| Method | Command |
|---|---|
| Exact test IDs (most precise) | `pytest "test_example_functions.py::TestExampleFunctions::test_example_ManyArgs" "test_example_functions.py::TestExampleFunctions::test_global_data_access"` |
| Name filter | `pytest -k "test_example_ManyArgs or test_global_data_access"` |
| Marker | `pytest -m smoke` |
| List all test IDs | `pytest --collect-only -q` |

> ⚠️ `-k` matches **substrings**. `-k test_example_Addition` selects about 10 tests (`AdditionPtr`, `AdditionStruct`, …). Narrow it with `and not`:
> ```powershell
> pytest -k "test_example_Addition and not Ptr and not Struct and not Subcalls"
> ```

Add `-v` to see each test name as it runs.

---

## 2. Registering custom markers in `pytest.ini`

pytest uses the **first config file it finds walking up from the run directory**. In this setup that's `DOTT-NG\examples\pytest.ini`. The run header shows which one is active:

```
rootdir: C:\Users\Employee\Documents\DOTT-NG\examples
configfile: pytest.ini
```

Add markers under the existing `[pytest]` section. Don't create a second `pytest.ini`.

```ini
[pytest]
markers =
    smoke: quick subset of component tests
    hw: hardware-level GPIO / interrupt tests
    manual: tests that need a human (e.g. press a button)
```

Mark the tests:

```python
import pytest          # required, or you get: NameError: name 'pytest' is not defined

class TestExampleFunctions(object):

    @pytest.mark.smoke
    def test_example_ManyArgs(self, target_load, target_reset):
        ...
```

Run and check:

```powershell
pytest -m smoke -v          # run marked tests
pytest -m "not smoke"       # run everything else
pytest --markers            # confirm the marker is registered
```

---

## 3. Adding a new firmware function and testing it

### 3.1 Firmware (`target/testexamples.c`)

```c
uint32_t __attribute__((used)) example_Multiply(uint32_t a, uint32_t b)
{
    return a * b;
}
```

- `__attribute__((used))` stops the compiler/linker from removing a function the firmware never calls itself.
- Sub-functions you want to intercept also need `DOTT_NO_OPTIMIZE`.

### 3.2 Rebuild

Requires the **Arm GNU toolchain** and **GNU Make** on `PATH`.

```powershell
cd examples\01_component_testing\target
make            # check the Makefile for the exact target name
```

Confirm both ELF files have new timestamps, since DOTT loads them:

- `target/build/dott_example_01/dott_example_01.bin.elf` (flashed)
- `target/build/dott_example_01/dott_example_01.elf` (symbols)

### 3.3 Test (`host/test_example_functions.py`)

```python
    @pytest.mark.smoke
    def test_example_Multiply(self, target_load, target_reset):
        res = dott().target.eval('example_Multiply(6, 7)')
        assert res == 42, f'expected 42, got {res}'
```

- `target_load`: flashes the firmware. `target_reset`: resets the target.
- `dott().target.eval('...')` executes C code on the target via the debugger.
- Pointer arguments: allocate target memory first:
  ```python
  dt = dott().target
  p_a = dt.mem.alloc_type('uint32_t', val=6)
  res = dt.eval(f'example_MultiplyPtr({p_a}, ...)')
  ```

```powershell
pytest -k test_example_Multiply -v
```

---

## 4. Hardware-level test: user button and LED

### 4.1 Board resources (NUCLEO-F072RB, verify against UM1724)

| Resource | Pin | Notes |
|---|---|---|
| User button **B1** | **PC13** | Reads `0` when pressed |
| User LED **LD2** | **PA5** | High = on |

### 4.2 Firmware (`target/board_io.c`, add it to the Makefile)

```c
#include "stm32f0xx.h"
#include <stdint.h>

volatile uint32_t g_button_press_count = 0;

void __attribute__((used)) board_io_init(void)
{
    RCC->AHBENR |= RCC_AHBENR_GPIOAEN | RCC_AHBENR_GPIOCEN;

    /* PA5 output, LED off */
    GPIOA->MODER = (GPIOA->MODER & ~(3u << (5 * 2))) | (1u << (5 * 2));
    GPIOA->BRR   = (1u << 5);

    /* PC13 input, pull-up */
    GPIOC->MODER &= ~(3u << (13 * 2));
    GPIOC->PUPDR  = (GPIOC->PUPDR & ~(3u << (13 * 2))) | (1u << (13 * 2));

    /* EXTI13 <- PC13, falling edge */
    RCC->APB2ENR |= RCC_APB2ENR_SYSCFGCOMPEN;
    SYSCFG->EXTICR[3] = (SYSCFG->EXTICR[3] & ~(0xFu << 4)) | (0x2u << 4);
    EXTI->FTSR |= (1u << 13);
    EXTI->IMR  |= (1u << 13);
    NVIC_EnableIRQ(EXTI4_15_IRQn);
}

void     __attribute__((used)) led_set(uint32_t on) { if (on) GPIOA->BSRR = (1u << 5); else GPIOA->BRR = (1u << 5); }
uint32_t __attribute__((used)) led_get(void)        { return (GPIOA->ODR >> 5) & 1u; }
uint32_t __attribute__((used)) button_read(void)    { return ((GPIOC->IDR >> 13) & 1u) ? 0u : 1u; } /* 1 = pressed */

void EXTI4_15_IRQHandler(void)   /* name must match the startup file's vector table */
{
    if (EXTI->PR & (1u << 13)) {
        EXTI->PR = (1u << 13);   /* write-1-to-clear */
        g_button_press_count++;
        GPIOA->ODR ^= (1u << 5);
    }
}

#ifdef DOTT_TEST
/* Test helper: raise EXTI13 in software and let the CPU run so the ISR executes. */
uint32_t __attribute__((used)) test_trigger_button_irq(void)
{
    uint32_t before = g_button_press_count;
    __enable_irq();
    EXTI->SWIER = (1u << 13);
    __DSB(); __ISB();
    for (volatile uint32_t i = 0; i < 10000u && g_button_press_count == before; i++) { }
    return g_button_press_count - before;   /* 1 = ISR ran once */
}
#endif
```

Call `board_io_init()` in `main()` before the DOTT test hook. The tests also call it themselves, because `target_reset` resets the chip.

### 4.3 Register addresses used by the tests

| Register | Address | Bit |
|---|---|---|
| `GPIOA_MODER` | `0x48000000` | [11:10] = PA5 mode |
| `GPIOA_IDR` (actual PA5 level) | `0x48000010` | 5 |
| `GPIOA_ODR` (LED latch) | `0x48000014` | 5 |
| `GPIOA_BSRR` (set) | `0x48000018` | 5 |
| `GPIOA_BRR` (reset) | `0x48000028` | 5 |
| `GPIOC_IDR` (button) | `0x48000810` | 13 |
| `EXTI_SWIER` (SW trigger) | `0x40010410` | 13 |
| `EXTI_PR` (pending, W1C) | `0x40010414` | 13 |
| `NVIC_ISER` | `0xE000E100` | 7 (EXTI4_15) |
| `NVIC_ISPR` | `0xE000E200` | 7 |
| Vector slot EXTI4_15 | `0x0800005C` | — |

### 4.4 Tests (`host/test_board_io.py`)

```python
import pytest
# + the same dott import lines as test_example_functions.py

GPIOA_IDR, GPIOA_ODR = 0x48000010, 0x48000014
GPIOC_IDR, EXTI_PR   = 0x48000810, 0x40010414

def reg(addr):
    return int(dott().target.eval(f'*(volatile unsigned int *){addr:#x}'))

class TestBoardIO:

    @pytest.mark.hw
    def test_init_configures_pins(self, target_load, target_reset):
        dott().target.eval('board_io_init()')
        assert (reg(0x48000000) >> 10) & 3 == 1, 'PA5 not configured as output'

    @pytest.mark.hw
    def test_led_on_off(self, target_load, target_reset):
        dt = dott().target
        dt.eval('board_io_init()')
        dt.eval('led_set(1)')
        assert (reg(GPIOA_ODR) >> 5) & 1 == 1
        assert (reg(GPIOA_IDR) >> 5) & 1 == 1    # real pin level, not just the latch
        dt.eval('led_set(0)')
        assert (reg(GPIOA_IDR) >> 5) & 1 == 0

    @pytest.mark.hw
    def test_button_idle_reads_released(self, target_load, target_reset):
        dott().target.eval('board_io_init()')
        assert (reg(GPIOC_IDR) >> 13) & 1 == 1
        assert int(dott().target.eval('button_read()')) == 0

    @pytest.mark.hw
    def test_button_interrupt_toggles_led(self, target_load, target_reset):
        dt = dott().target
        dt.eval('board_io_init()')
        dt.eval('g_button_press_count = 0')
        dt.eval('led_set(0)')
        fired = int(dt.eval('test_trigger_button_irq()'))
        assert fired == 1, 'EXTI13 ISR did not run'
        assert int(dt.eval('led_get()')) == 1
        assert (reg(EXTI_PR) >> 13) & 1 == 0

    @pytest.mark.manual
    def test_physical_button_press(self, target_load, target_reset):
        import time
        dott().target.eval('board_io_init()')
        print('\n>>> Press the USER button within 10 s')
        deadline = time.time() + 10
        while time.time() < deadline:
            if int(dott().target.eval('button_read()')) == 1:
                return
            time.sleep(0.05)
        pytest.fail('Button press not detected')
```

```powershell
pytest -m hw -v          # automated hardware tests
pytest -m manual -s      # -s so the "press the button" prompt is shown
```

---

## 5. Debugging the interrupt test

**Symptom:** the first version wrote `EXTI_SWIER` directly from the test and then checked the counter:

```
FAILED test_board_io.py::TestBoardIO::test_button_interrupt_toggles_led - AssertionError: assert 0 == 1
```

**Cause:** DOTT keeps the CPU **halted at the test hook** between `eval` calls. A register write can make the interrupt pending, but the ISR only runs while the CPU is executing.

**Fix:** the `test_trigger_button_irq()` firmware helper (section 4.2). The CPU runs while the debugger executes that function, so the ISR can fire during the call.

**Diagnostic test**, if the ISR still doesn't run:

```python
    @pytest.mark.hw
    def test_irq_diagnostics(self, target_load, target_reset):
        dt = dott().target
        dt.eval('board_io_init()')
        dt.eval('*(volatile unsigned int *)0x40010410 = (1 << 13)')
        print('\nEXTI_PR  bit13 :', (reg(0x40010414) >> 13) & 1)
        print('NVIC_ISER bit7 :', (reg(0xE000E100) >> 7) & 1)
        print('NVIC_ISPR bit7 :', (reg(0xE000E200) >> 7) & 1)
        print('PRIMASK        :', dt.eval('$primask'))
        print('Vector entry   :', hex(reg(0x0800005C)))
        print('Handler addr   :', dt.eval('&EXTI4_15_IRQHandler'))
```

| Result | Meaning |
|---|---|
| PR=1, ISER=1, ISPR=1, PRIMASK=0 | Setup OK; the CPU just didn't run → use the helper |
| PRIMASK=1 | IRQs masked at the test hook → the helper's `__enable_irq()` handles it |
| ISER=0 | `NVIC_EnableIRQ` didn't take effect |
| PR=0 | SWIER didn't latch → check `EXTI_IMR` and the SYSCFG clock |
| Vector ≠ handler (ignoring the +1 Thumb bit) | ISR name doesn't match the startup file |

---

## 6. Reading and writing registers from pytest

### Peripheral (memory-mapped) registers

```python
dt = dott().target
dt.eval('*(volatile unsigned int *)0x48000018 = (1 << 5)')    # write
dt.eval('*(volatile unsigned int *)0x48000014 |= (1 << 5)')   # set bit
dt.eval('*(volatile unsigned int *)0x48000014 &= ~(1 << 5)')  # clear bit
dt.mem.write(0x48000018, (1 << 5).to_bytes(4, 'little'))      # raw bytes
```

Helpers:

```python
def reg_write(addr, value):
    dott().target.eval(f'*(volatile unsigned int *){addr:#x} = {value:#x}')

def reg_set_bits(addr, mask):
    dott().target.eval(f'*(volatile unsigned int *){addr:#x} |= {mask:#x}')

def reg_clear_bits(addr, mask):
    dott().target.eval(f'*(volatile unsigned int *){addr:#x} &= ~{mask:#x}')
```

### CPU core registers (GDB `$` variables)

```python
dt.eval('$r0 = 0x1234')
dt.eval('$primask = 0')
print(dt.eval('$pc'))
```

> ⚠️ Avoid writing `$pc`, `$sp` or `$lr` at the test hook. It can break DOTT's control of the target.

### Register behaviour to watch for

| Type | Example | Rule |
|---|---|---|
| Write-1-to-clear | `EXTI_PR` | Use `= (1 << n)`, never `\|=` |
| Write-only / set-reset | `GPIOx_BSRR`, `BRR` | Read back as 0. Use `=` |
| Read-only | `GPIOx_IDR` | Writes ignored |
| Clock-gated | any peripheral | Writes ignored until its RCC clock is enabled |

Peripheral writes take effect **immediately, even while halted** (e.g. the LED turns on). Interrupt handlers still need the CPU to run.

---

## 7. Troubleshooting summary

| Error / symptom | Fix |
|---|---|
| `NameError: name 'pytest' is not defined` | Add `import pytest` at the top of the test file |
| `PytestUnknownMarkWarning` | Register the marker in the active `pytest.ini` (see `configfile:` in the run header) |
| `-k` runs too many tests | Use exact node IDs or add `and not ...` |
| `No symbol "..." in current context` | Board has old firmware (rebuild, check ELF timestamps) or function optimized out (add `__attribute__((used))`) |
| ISR doesn't run (`assert 0 == 1`) | CPU halted at test hook. Trigger the IRQ from a firmware helper (section 5) |
| Wrong return values | Use fixed-width types (`uint32_t`, `int32_t`) |
| `print()` output not shown | Run with `-s` |

---

### References

- [DOTT-ng documentation](https://tw-ghub.github.io/dott-ng_docu/)
- [Setup and target requirements](https://tw-ghub.github.io/dott-ng_docu/SetupAndTarget.html)
- [Component testing](https://tw-ghub.github.io/dott-ng_docu/ComponentTesting.html)
- [DOTT-ng releases (examples zip)](https://github.com/tw-ghub/dott-ng/releases)
- STMicroelectronics UM1724 (Nucleo-64 user manual), RM0091 (STM32F0x1/x2/x8 reference manual)

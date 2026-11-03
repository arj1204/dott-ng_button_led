#include "stm32f0xx.h"   // CMSIS device header; check which header the example's Makefile uses
#include <stdint.h>

volatile uint32_t g_button_press_count = 0;   // global, so tests can read it

void __attribute__((used)) board_io_init(void)
{
    // Clocks for GPIOA (LED) and GPIOC (button)
    RCC->AHBENR |= RCC_AHBENR_GPIOAEN | RCC_AHBENR_GPIOCEN;

    // PA5 = push-pull output, LED off
    GPIOA->MODER = (GPIOA->MODER & ~(3u << (5 * 2))) | (1u << (5 * 2));
    GPIOA->BRR   = (1u << 5);

    // PC13 = input with pull-up
    GPIOC->MODER &= ~(3u << (13 * 2));
    GPIOC->PUPDR  = (GPIOC->PUPDR & ~(3u << (13 * 2))) | (1u << (13 * 2));

    // EXTI13 on PC13, falling edge (press)
    RCC->APB2ENR |= RCC_APB2ENR_SYSCFGCOMPEN;
    SYSCFG->EXTICR[3] = (SYSCFG->EXTICR[3] & ~(0xFu << 4)) | (0x2u << 4); // port C
    EXTI->FTSR |= (1u << 13);
    EXTI->IMR  |= (1u << 13);
    NVIC_EnableIRQ(EXTI4_15_IRQn);
}

void __attribute__((used)) led_set(uint32_t on)
{
    if (on) GPIOA->BSRR = (1u << 5);
    else    GPIOA->BRR  = (1u << 5);
}

uint32_t __attribute__((used)) led_get(void)    { return (GPIOA->ODR >> 5) & 1u; }
uint32_t __attribute__((used)) button_read(void) { return ((GPIOC->IDR >> 13) & 1u) ? 0u : 1u; } // 1 = pressed

// Application logic: each press toggles the LED
void EXTI4_15_IRQHandler(void)
{
    if (EXTI->PR & (1u << 13)) {
        EXTI->PR = (1u << 13);          // clear pending
        g_button_press_count++;
        GPIOA->ODR ^= (1u << 5);
    }
}
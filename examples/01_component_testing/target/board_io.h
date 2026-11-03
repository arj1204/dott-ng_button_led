#ifndef __BOARD_IO_H__
#define __BOARD_IO_H__

void __attribute__((used)) board_io_init(void);
void __attribute__((used)) led_set(uint32_t on);
uint32_t __attribute__((used)) led_get(void) ;
uint32_t __attribute__((used)) button_read(void);

#endif // __BOARD_IO_H__
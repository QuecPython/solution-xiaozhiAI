from machine import LCD 
import test.lvgl as lv
import utime as time

def pm_init():
    init_data = (
            0, 0, 0x11,
            2, 0, 120,
            0, 1, 0x36,
            1, 1, 0x00,
            0, 1, 0x3A,
            1, 1, 0x05,
            0, 5, 0xB2,
            1, 1, 0x05,
            1, 1, 0x05,
            1, 1, 0x00,
            1, 1, 0x33,
            1, 1, 0x33,
            0, 1, 0xB7,
            1, 1, 0x75,
            0, 1, 0xBB,
            1, 1, 0x22,
            0, 1, 0xC0,
            1, 1, 0x2C,
            0, 1, 0xC2,
            1, 1, 0x01,
            0, 1, 0xC3,
            1, 1, 0x13,
            0, 1, 0xC4,
            1, 1, 0x20,
            0, 1, 0xC6,
            1, 1, 0x11,
            0, 2, 0xD0,
            1, 1, 0xA4,
            1, 1, 0xA1,
            0, 1, 0xD6,
            1, 1, 0xA1,
            0, 14, 0xE0,
            1, 1, 0xD0,
            1, 1, 0x05,
            1, 1, 0x0A,
            1, 1, 0x09,
            1, 1, 0x08,
            1, 1, 0x05,
            1, 1, 0x2E,
            1, 1, 0x44,
            1, 1, 0x45,
            1, 1, 0x0F,
            1, 1, 0x17,
            1, 1, 0x16,
            1, 1, 0x2B,
            1, 1, 0x33,
            0, 14, 0xE1,
            1, 1, 0xD0,
            1, 1, 0x05,
            1, 1, 0x0A,
            1, 1, 0x09,
            1, 1, 0x08,
            1, 1, 0x05,
            1, 1, 0x2E,
            1, 1, 0x43,
            1, 1, 0x45,
            1, 1, 0x0F,
            1, 1, 0x16,
            1, 1, 0x16,
            1, 1, 0x2B,
            1, 1, 0x33,
            0, 0, 0x29,
            0, 0, 0x21)

    display_on_data = (
                0, 0, 0x28,
                2, 0, 120,
                0, 0, 0x10,
    )
    display_off_data =(
                0, 0, 0x11,
                2, 0, 20,
                0, 0, 0x29,
    )
    # 设置区域参数
    XSTART_H = 0xf0
    XSTART_L = 0xf1
    YSTART_H = 0xf2
    YSTART_L = 0xf3
    XEND_H = 0xE0
    XEND_L = 0xE1
    YEND_H = 0xE2
    YEND_L = 0xE3
    invalid_data = (
        0, 4, 0x2a,
        1, 1, XSTART_H,
        1, 1, XSTART_L,
        1, 1, XEND_H,
        1, 1, XEND_L,
        0, 4, 0x2b,
        1, 1, YSTART_H,
        1, 1, YSTART_L,
        1, 1, YEND_H,
        1, 1, YEND_L,
        0, 0, 0x2c,
    )
    
    def init_lcd():
        pm_init()
        lcd = LCD()
        init_list = bytearray(init_data)
        display_on_list = bytearray(display_on_data)
        display_off_list = bytearray(display_off_data)
        invalid_list = bytearray(invalid_data)
        
        lcd.lcd_init(init_list, 240, 320, 13000, 1, 4, 0, invalid_list, display_on_list, display_off_list, None)
        lcd.lcd_clear(0xffff)
        return lcd


  

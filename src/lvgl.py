# lvgl_init.py

import test.lvgl as lv

def init_lvgl(lcd):
    lv.init()

    LCD_SIZE_W = 240
    LCD_SIZE_H = 320

    disp_buf1 = lv.disp_draw_buf_t()
    buf1_1 = bytearray(LCD_SIZE_W * LCD_SIZE_H * 2)
    disp_buf1.init(buf1_1, None, len(buf1_1))

    disp_drv = lv.disp_drv_t()
    disp_drv.init()
    disp_drv.draw_buf = disp_buf1
    disp_drv.flush_cb = lcd.lcd_write
    disp_drv.hor_res = LCD_SIZE_W
    disp_drv.ver_res = LCD_SIZE_H
    disp_drv.register()

    lv.tick_inc(5)
    lv.task_handler()
    
    
# font_manager.py

global_font_cache = {}

def test_font(font_family, font_size):
    global global_font_cache
    if font_family + str(font_size) in global_font_cache:
        return global_font_cache[font_family + str(font_size)]
    
    if font_size % 2:
        candidates = [
            (font_family, font_size),
            (font_family, font_size - font_size % 2),
            (font_family, font_size + font_size % 2),
            ("montserrat", font_size - font_size % 2),
            ("montserrat", font_size + font_size % 2),
            ("montserrat", 16),
        ]
    else:
        candidates = [
            (font_family, font_size),
            ("montserrat", font_size),
            ("montserrat", 16),
        ]

    for (family, size) in candidates:
        try:
            font = eval(f"lv.font_{family}_{size}")
            global_font_cache[font_family + str(font_size)] = font
            if family != font_family or size != font_size:
                print(f"WARNING: lv.font_{family}_{size} is used!")
            return font
        except AttributeError:
            try:
                load_font = lv.font_load(f"U:/lv_font_{family}_{size}.fnt")
                global_font_cache[font_family + str(font_size)] = load_font
                return load_font
            except:
                if family == font_family and size == font_size:
                    print(f"WARNING: lv.font_{family}_{size} is NOT supported!")
                    


def datetext_event_handler(e, obj):
    code = e.get_code()
    target = e.get_target()
    if code == lv.EVENT.FOCUSED:
        if obj is None:
            bg = lv.layer_top()
            bg.add_flag(lv.obj.FLAG.CLICKABLE)
            obj = lv.calendar(bg)
            scr = target.get_screen()
            scr_height = scr.get_height()
            scr_width = scr.get_width()
            obj.set_size(int(scr_width * 0.8), int(scr_height * 0.8))
            datestring = target.get_text()
            year, month, day = map(int, datestring.split('/'))
            obj.set_showed_date(year, month)
            highlighted_days = [lv.calendar_date_t({'year': year, 'month': month, 'day': day})]
            obj.set_highlighted_dates(highlighted_days, 1)
            obj.align(lv.ALIGN.CENTER, 0, 0)
            lv.calendar_header_arrow(obj)
            obj.add_event_cb(lambda e: datetext_calendar_event_handler(e, target), lv.EVENT.ALL, None)
            scr.update_layout()

def datetext_calendar_event_handler(e, obj):
    code = e.get_code()
    target = e.get_current_target()
    if code == lv.EVENT.VALUE_CHANGED:
        date = lv.calendar_date_t()
        if target.get_pressed_date(date) == lv.RES.OK:
            obj.set_text(f"{date.year}/{date.month}/{date.day}")
            bg = lv.layer_top()
            bg.clear_flag(lv.obj.FLAG.CLICKABLE)
            bg.set_style_bg_opa(lv.OPA.TRANSP, 0)
            target.delete()
    
def datetext_event_handler(e, obj):
    code = e.get_code()
    target = e.get_target()
    if code == lv.EVENT.FOCUSED:
        if obj is None:
            bg = lv.layer_top()
            bg.add_flag(lv.obj.FLAG.CLICKABLE)
            obj = lv.calendar(bg)
            scr = target.get_screen()
            scr_height = scr.get_height()
            scr_width = scr.get_width()
            obj.set_size(int(scr_width * 0.8), int(scr_height * 0.8))
            datestring = target.get_text()
            year, month, day = map(int, datestring.split('/'))
            obj.set_showed_date(year, month)
            highlighted_days = [lv.calendar_date_t({'year': year, 'month': month, 'day': day})]
            obj.set_highlighted_dates(highlighted_days, 1)
            obj.align(lv.ALIGN.CENTER, 0, 0)
            lv.calendar_header_arrow(obj)
            obj.add_event_cb(lambda e: datetext_calendar_event_handler(e, target), lv.EVENT.ALL, None)
            scr.update_layout()

def datetext_calendar_event_handler(e, obj):
    code = e.get_code()
    target = e.get_current_target()
    if code == lv.EVENT.VALUE_CHANGED:
        date = lv.calendar_date_t()
        if target.get_pressed_date(date) == lv.RES.OK:
            obj.set_text(f"{date.year}/{date.month}/{date.day}")
            bg = lv.layer_top()
            bg.clear_flag(lv.obj.FLAG.CLICKABLE)
            bg.set_style_bg_opa(lv.OPA.TRANSP, 0)
            target.delete()
            
# ui_components

def create_ui(screen,str,x,y):
    # Create screen_label_1
    screen_label_1 = lv.label(screen)
    screen_label_1.set_text(str)
    screen_label_1.set_long_mode(lv.label.LONG.WRAP)
    screen_label_1.set_width(lv.pct(100))
    screen_label_1.set_pos(x, y)
    screen_label_1.set_size(125, 100)
    screen_label_1.set_style_border_width(0, lv.PART.MAIN | lv.STATE.DEFAULT)
    screen_label_1.set_style_radius(0, lv.PART.MAIN | lv.STATE.DEFAULT)
    screen_label_1.set_style_text_color(lv.color_hex(0x000000), lv.PART.MAIN | lv.STATE.DEFAULT)
    screen_label_1.set_style_text_font(test_font("ArchitectsDaughter", 20), lv.PART.MAIN | lv.STATE.DEFAULT)
    screen_label_1.set_style_text_opa(255, lv.PART.MAIN | lv.STATE.DEFAULT)
    screen_label_1.set_style_text_letter_space(2, lv.PART.MAIN | lv.STATE.DEFAULT)
    screen_label_1.set_style_text_line_space(0, lv.PART.MAIN | lv.STATE.DEFAULT)
    screen_label_1.set_style_text_align(lv.TEXT_ALIGN.CENTER, lv.PART.MAIN | lv.STATE.DEFAULT)
    screen_label_1.set_style_bg_opa(0, lv.PART.MAIN | lv.STATE.DEFAULT)
def create_ui(screen,img,x,y):
# Create screen_img_1
    screen_img_1 = lv.img(screen)
    screen_img_1.set_src(img)#图片路径
    screen_img_1.add_flag(lv.obj.FLAG.CLICKABLE) 
    screen_img_1.set_pivot(50, 50)#旋转中心点
    screen_img_1.set_angle(0)#旋转角度
    screen_img_1.set_pos(x, y)#img位置
    screen_img_1.set_size(240, 320)
    screen_img_1.set_style_img_opa(255, lv.PART.MAIN | lv.STATE.DEFAULT)
    screen_img_1.set_style_radius(0, lv.PART.MAIN | lv.STATE.DEFAULT)
    screen_img_1.set_style_clip_corner(True, lv.PART.MAIN | lv.STATE.DEFAULT)
    screen.update_layout()
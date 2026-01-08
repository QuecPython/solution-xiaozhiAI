"""
提高 CPU 主频: AT+LOG=17,5
"""
import utime
import gc
from machine import ExtInt,Pin
from misc import PowerKey, Power
from usr.protocol import WebSocketClient
from usr.utils import ChargeManager, AudioManager, NetManager, TaskManager, name, Button
from usr.threading import Thread, Event, Condition
from usr.logging import getLogger
import sys_bus
import _thread
import ujson as json
from misc import USB
# from usr import UI


logger = getLogger(__name__)



class Led(object):

    def __init__(self, GPIOn):
        self.__led = Pin(
            getattr(Pin, 'GPIO{}'.format(GPIOn)),
            Pin.OUT,
            Pin.PULL_PD,
            0
        )
        self.__off_period = 1000
        self.__on_period = 1000
        self.__count = 0
        self.__running_cond = Condition()
        self.__blink_thread = None
        self.off()

    @property
    def status(self):
        with self.__running_cond:
            return self.__led.read()

    def on(self):
        with self.__running_cond:
            self.__count = 0
            return self.__led.write(0)

    def off(self):
        with self.__running_cond:
            self.__count = 0
            return self.__led.write(1)

    def blink(self, on_period=50, off_period=50, count=None):
        if not isinstance(count, (int, type(None))):
            raise TypeError('count must be int or None type')
        with self.__running_cond:
            if self.__blink_thread is None:
                self.__blink_thread = Thread(target=self.__blink_thread_worker)
                self.__blink_thread.start()
            self.__on_period = on_period
            self.__off_period = off_period
            self.__count = count
            self.__running_cond.notify_all()

    def __blink_thread_worker(self):
        while True:
            with self.__running_cond:
                if self.__count is not None:
                    self.__running_cond.wait_for(lambda: self.__count is None or self.__count > 0)
                status = self.__led.read()
                self.__led.write(1 - status)
                utime.sleep_ms(self.__on_period if status else self.__off_period)
                self.__led.write(status)
                utime.sleep_ms(self.__on_period if status else self.__off_period)
                if self.__count is not None:
                    self.__count -= 1

enable_flag=0

class Application(object):

    def __init__(self):
        
        # 初始化 led; write(1) 灭； write(0) 亮
        self.wifi_red_led = Led(33)
        self.wifi_green_led = Led(32) #ai
        self.power_red_led = Led(39) 
        self.power_green_led = Led(38) #power
        self.lte_red_led = Led(23)
        self.lte_green_led = Led(24)#chat
        self.led_power_pin = Pin(Pin.GPIO27, Pin.OUT, Pin.PULL_DISABLE, 1)
        self.prev_emoj = None
        # self.power_green_led.blink(500, 500)
        self.power_key = PowerKey()
        self.power_key.powerKeyEventRegister(lambda status: None)
        
        
        # 初始化充电管理
        self.charge_manager = ChargeManager()

        # 初始化音频管理
        self.audio_manager = AudioManager()
        self.audio_manager.set_kws_cb(self.on_keyword_spotting)
        self.audio_manager.set_vad_cb(self.on_voice_activity_detection)

        # 初始化网络管理
        self.net_manager = NetManager()

        # 初始化任务调度器
        self.task_manager = TaskManager()

        # 初始化协议
        self.__protocol = WebSocketClient()
        self.__protocol.set_callback(
            audio_message_handler=self.on_audio_message,
            json_message_handler=self.on_json_message
        )

        self.__working_thread = None
        self.__record_thread = None
        self.__record_thread_stop_event = Event()
        self.__voice_activity_event = Event()
        self.__keyword_spotting_event = Event()
        
        # self.gpio_pin = Pin(Pin.GPIO41, Pin.OUT, Pin.PULL_PD,0)
        
        # 初始化唤醒按键
        self.volumedown = ExtInt(ExtInt.GPIO20, ExtInt.IRQ_RISING, ExtInt.PULL_PU, self.setvolumedown, 200)
        # self.power_down = ExtInt(ExtInt.GPIO41, ExtInt.IRQ_RISING, ExtInt.PULL_PU, self.power_down_handle, 200)
        self.volumeup = ExtInt(ExtInt.GPIO47, ExtInt.IRQ_RISING, ExtInt.PULL_PU, self.setvolumeup, 200)
        # self.wakeup_key = Button(41, delay=3000, long_press_callback=self.power_down_handle, short_press_callback= self.on_talk_key_click)


    def __record_thread_handler(self):
        """纯粹是为了kws&vad能识别才起的线程持续读音频"""
        logger.debug("record thread handler enter")
        while not self.__record_thread_stop_event.is_set():
            self.audio_manager.opus_read()
            utime.sleep_ms(5)
        logger.debug("record thread handler exit")
        
    def on_led(self):
        self.wifi_green_led.on()
        self.lte_green_led.on()
        self.power_green_led.on()
        
    def off_led(self):
        self.wifi_green_led.off()
        self.lte_green_led.off()
        self.power_green_led.off()
        
    def start_kws(self):
        self.audio_manager.start_kws()
        self.__record_thread_stop_event.clear()
        self.__record_thread = Thread(target=self.__record_thread_handler)
        self.__record_thread.start(stack_size=64)
        
    def setvolumeup(self,args):
        volume=self.audio_manager.setvolume_up()
        print("setvolumeup:", volume)
    def setvolumedown(self,args):
        volume=self.audio_manager.setvolume_down()
        print("setvolumedown:", volume)
        
    def power_down_handle(self):
        logger.info("power down")
        Power.powerDown()
        
        
    def stop_kws(self):
        self.__record_thread_stop_event.set()
        self.__record_thread.join()
        # self.audio_manager.stop_kws()
        
    def start_vad(self):
        self.audio_manager.start_vad()
    
    def stop_vad(self):
        self.audio_manager.stop_vad()

    def __working_thread_handler(self):
        t = Thread(target=self.__chat_process)
        t.start(stack_size=64)
        self.__keyword_spotting_event.wait()
        self.stop_kws()
        t.join()
        # self.start_kws()

    def __chat_process(self):
        global name
        self.__protocol.connect_flag = True
        self.power_green_led.on()
        self.start_vad()
        try:
            with self.__protocol:
                self.__protocol.hello()
                self.__protocol.wakeword_detected(name)
                is_listen_flag = False
                buffer = []  # 用于缓存最近5帧
                while True:
                    data = self.audio_manager.opus_read()
                    buffer.append(data)
                    if len(buffer) > 7:
                        buffer.pop(0)
                    if self.__voice_activity_event.is_set():
                        # 有人声
                        if not is_listen_flag:
                            self.__protocol.abort()
                            self.__protocol.listen("start")
                            is_listen_flag = True
                            for frame in buffer[:6]:  # 发送缓存的前6帧
                                self.__protocol.send(frame)
                        self.__protocol.send(data)
                        # logger.debug("send opus data to server")
                    else:
                        if is_listen_flag:
                            self.__protocol.listen("stop")
                            is_listen_flag = False
                    if not self.__protocol.is_state_ok or self.__protocol.connect_flag == False:
                        print("连接断开，退出聊天流程",self.__protocol.connect_flag)
                        break
                    utime.sleep_ms(5)
                    # logger.debug("read opus data length: {}".format(len(data)))
        except Exception as e:
            logger.debug("working thread handler got Exception: {}".format(repr(e)))
        finally:
            print("__chat_process exit")
            self.lte_green_led.off()
            self.wifi_green_led.off()
            self.power_green_led.blink(500, 500)
            self.__working_thread = None
            self.stop_vad()
            self.start_kws()

    def on_talk_key_click(self):
        # logger.info("on_talk_key_click: ", args)
        if self.__working_thread is not None and self.__working_thread.is_running():
            return
        self.__working_thread = Thread(target=self.__working_thread_handler)
        self.__working_thread.start()
        self.__keyword_spotting_event.set()
        
    def on_keyword_spotting(self, state):
        logger.info("on_keyword_spotting: {}".format(state))
        if state[0] == 0:
            if state[1] != 0:
                # 唤醒词触发
                if self.__working_thread is not None and self.__working_thread.is_running():
                    return
                self.__working_thread = Thread(target=self.__working_thread_handler)
                self.__working_thread.start()
                self.__keyword_spotting_event.set()
            else:
                self.__keyword_spotting_event.clear()
            
    def on_voice_activity_detection(self, state):
        logger.info("on_voice_activity_detection: {}".format(state))
        if state == 1:
            self.__voice_activity_event.set()  # 有人声
            self.lte_green_led.on()
        else:
            self.__voice_activity_event.clear()  # 无人声
            self.lte_green_led.off()

    def on_audio_message(self, raw):
        # raise NotImplementedError("on_audio_message not implemented")
        self.audio_manager.opus_write(raw)

    def on_json_message(self, msg):
        return getattr(self, "handle_{}_message".format(msg["type"]))(msg)

    def handle_stt_message(data, msg):
        # pass
        raise NotImplementedError("handle_stt_message not implemented")

    def handle_tts_message(self, msg):
        state = msg["state"]
        if state == "start":
            self.wifi_green_led.blink(250, 250)
        elif state == "stop":
            self.wifi_green_led.off()
        else:
            pass
        raise NotImplementedError("handle_tts_message not implemented")

#"happy" "cool"  "angry"  "think"
# ... existing code ...
    def handle_llm_message(data, msg):
        raise NotImplementedError("handle_llm_message not implemented")
    
    def handle_mcp_message(self, msg):
        print("msg: ", msg)
        data=msg.to_bytes()

        # 解析JSON字符串为字典
        data_dict = json.loads(data)
        id=1
        # 提取method内容
        method = data_dict['payload']['method']
        # arguments = data_dict['payload']["arguments"]
        if 'id' in data_dict['payload']:
            id=data_dict['payload']['id']
        print("MCP请求: ",method)
        if method == "initialize":
            self.__protocol.mcp_initialize()
        elif method == "tools/list":
            self.__protocol.mcp_tools_list()
        elif method =="tools/call":
            handle =data_dict['payload']['params']['name']
            
            if handle == "self.setvolume_down()":     
                print("当前音量大小",self.audio_manager.setvolume_down())
            elif handle == "self.setvolume_up()":
                print("当前音量大小",self.audio_manager.setvolume_up())
            elif handle == "self.setvolume_close()":
                print("当前音量大小",self.audio_manager.setvolume_close())
            elif handle == "self.setvolume()":
                arguments = data_dict['payload']["params"]["arguments"]["volume"]
                print("当前音量大小",arguments,self.audio_manager.setvolume(arguments))
            elif handle == "self.new_name()":
                arguments = data_dict['payload']["params"]["arguments"]["name"]
                print("neme:",self.audio_manager.new_name(arguments))
            self.__protocol.mcp_tools_call(tool_name=handle,req_id=id)
        # raise NotImplementedError("handle_mcp_message not implemented")
        
    def handle_iot_message(data, msg):
        pass
        # raise NotImplementedError("handle_iot_message not implemented")
    
    def handle_error_message(data, msg):
        pass
        # raise NotImplementedError("handle_error_message not implemented")

    def run(self):
        global enable_flag
        self.charge_manager.disable_charge()
        self.audio_manager.open_opus()
        self.volumedown.enable()
        self.volumeup.enable()
        self.power_green_led.blink(500, 500)
        self.wakeup_key = Button(41, delay=3000, long_press_callback=self.power_down_handle, short_press_callback= self.on_talk_key_click)
        enable_flag = 1
        self.start_kws()
        
    


def usb_callback(conn_status):
    status = conn_status
    if not enable_flag:
        if status == 0:
            app.off_led()
            Power.powerDown()
            # enable_flag=1
            print('USB is disconnected.')
        elif status == 1:
            app.on_led()
            # enable_flag=0
            
            print('USB is connected.')
     
def power_open_handle():
    if enable_flag: 
        app.off_led()
        app.run()  
        print("power_open_handle")
            


if __name__ == "__main__":    
    usb = USB()
    app = Application()
    usb.setCallback(usb_callback)
    # 检查 USB 连接状态
    if usb.getStatus():  # 假设 getStatus() 返回 True 表示 USB 已连接
        app.on_led()
        print("USB 已连接，仅启用充电业务")
        app.charge_manager.enable_charge()  # 只启用充电业务
        # Button(41, delay=3000, long_press_callback=power_open_handle, short_press_callback= None)

    else:
        print("USB 未连接，启动主业务")
        app.run()
"""
提高 CPU 主频: AT+LOG=17,5
"""
import utime
from machine import ExtInt, Pin
from usr.protocol import WebSocketClient
from usr.utils import ChargeManager, AudioManager, NetManager, TaskManager
from usr.threading import Thread, Event, Condition
from usr.logging import getLogger
import ujson as json


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



class Application(object):

    def __init__(self):
        # 初始化唤醒按键
        self.gpio19 =Pin(Pin.GPIO19, Pin.OUT, Pin.PULL_DISABLE, 1)
        self.upsetvolume = ExtInt(ExtInt.GPIO47, ExtInt.IRQ_FALLING , ExtInt.PULL_PU, self.setvolumeup, 50)
        self.downsetvolume = ExtInt(ExtInt.GPIO20, ExtInt.IRQ_FALLING , ExtInt.PULL_PU, self.setvolumedown, 50)     
        self.talk_key = ExtInt(ExtInt.GPIO19, ExtInt.IRQ_RISING_FALLING, ExtInt.PULL_PU, self.on_talk_key_click, 50)
        
        # 初始化 led; write(1) 灭； write(0) 亮
        self.wifi_red_led = Led(33)
        self.wifi_green_led = Led(32)
        self.power_red_led = Led(39)
        self.power_green_led = Led(38)
        self.lte_red_led = Led(23)
        self.lte_green_led = Led(24)
        self.led_power_pin = Pin(Pin.GPIO27, Pin.OUT, Pin.PULL_DISABLE, 0)

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
        
    def setvolumedown(self,args):
        print("setvolumedown")
        return self.audio_manager.setvolume_down()
    
    def setvolumeup(self,args):
        print("setvolumeup")
        return self.audio_manager.setvolume_up()

    def __record_thread_handler(self):
        """纯粹是为了kws&vad能识别才起的线程持续读音频"""
        logger.debug("record thread handler enter")
        while not self.__record_thread_stop_event.is_set():
            self.audio_manager.opus_read()
            utime.sleep_ms(5)
        logger.debug("record thread handler exit")

    def start_kws(self):
        self.audio_manager.start_kws()
        self.__record_thread_stop_event.clear()
        self.__record_thread = Thread(target=self.__record_thread_handler)
        self.__record_thread.start(stack_size=64)
    
    def stop_kws(self):
        self.__record_thread_stop_event.set()
        self.__record_thread.join()
        self.audio_manager.stop_kws()

    def start_vad(self):
        self.audio_manager.start_vad()
    
    def stop_vad(self):
        self.audio_manager.stop_vad()

    def __working_thread_handler(self):
        t = Thread(target=self.__chat_process)
        t.start(stack_size=64)
        t.join()

    def test_audio_play(self):
        """just for test"""
        global audio_data, audio_data_length_list
        total = 0
        for _ in range(10000 // 60):
            data = self.audio_manager.opus_read()
            audio_data += data
            audio_data_length_list.append(len(data))
        for count in audio_data_length_list:
            self.audio_manager.opus_write(audio_data[total:total+count])
            total += count

    def __chat_process(self):
        logger.debug("chat process enter.")
        # self.start_vad()
        try:
            with self.__protocol:
                self.power_red_led.on()
                self.__protocol.hello()
                self.__protocol.wakeword_detected("小智")
                is_listen_flag = False
                while True:
                    if self.__voice_activity_event.is_set():
                        data = self.audio_manager.opus_read()
                        # 有人声
                        if not is_listen_flag:
                            self.__protocol.abort()
                            self.__protocol.listen("start")
                            is_listen_flag = True
                        self.__protocol.send(data)
                        # logger.debug("send opus data to server")
                    else:
                        if is_listen_flag:
                            self.__protocol.listen("stop")
                            is_listen_flag = False
                    # logger.debug("read opus data length: {}".format(len(data)))
                    if not self.__protocol.is_state_ok():
                        break
                    utime.sleep_ms(1)
        except Exception as e:
            logger.debug("working thread handler got Exception: {}".format(repr(e)))
        finally:
            # self.stop_vad()
            self.power_red_led.blink(250, 250)
        logger.debug("chat process exit.")

    def on_talk_key_click(self, args):
        args[1]=self.gpio19.read()
        logger.info("on_talk_key_click: ", args)
        if args[1] == 0:
            # 按键按下
            self.lte_green_led.on()
            self.__voice_activity_event.set()  # 有人声
        else:
            # 按键抬起
            self.lte_green_led.off()
            self.__voice_activity_event.clear()  # 无人声
        if self.__working_thread is not None and self.__working_thread.is_running():
            return
        self.__working_thread = Thread(target=self.__working_thread_handler)
        self.__working_thread.start()
        
    def on_keyword_spotting(self, state):
        logger.info("on_keyword_spotting: {}".format(state))
        if state == 0:
            # 唤醒词触发
            if self.__working_thread is not None and self.__working_thread.is_running():
                return
            self.__working_thread = Thread(target=self.__working_thread_handler)
            self.__working_thread.start()
            self.__keyword_spotting_event.clear()
        else:
            self.__keyword_spotting_event.set()

    def on_voice_activity_detection(self, state):
        logger.info("on_voice_activity_detection: {}".format(state))
        if state == 1:
            self.__voice_activity_event.set()  # 有人声
        else:
            self.__voice_activity_event.clear()  # 无人声

    def on_audio_message(self, raw):
        self.audio_manager.opus_write(raw)

    def on_json_message(self, msg):
        return getattr(self, "handle_{}_message".format(msg["type"]))(msg)

    def handle_stt_message(self, msg):
        logger.debug("handle_stt_message: {}".format(msg))

    def handle_tts_message(self, msg):
        state = msg["state"]
        if state == "start":
            self.wifi_green_led.blink(250, 250)
        elif state == "stop":
            self.wifi_green_led.off()
        else:
            pass

    def handle_llm_message(self, msg):
        logger.debug("handle_llm_message: {}".format(msg))
    
    def handle_iot_message(self, msg):
        logger.debug("handle_iot_message: {}".format(msg))
        
    def handle_mcp_message(self, msg):
        # print("msg: ", msg)
        data=msg.to_bytes()

        # 解析JSON字符串为字典
        data_dict = json.loads(data)
        id=1
        # 提取method内容
        method = data_dict['payload']['method']
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
            self.__protocol.mcp_tools_call(tool_name=handle,req_id=id)
        # raise NotImplementedError("handle_mcp_message not implemented")

    def run(self):
        self.charge_manager.enable_charge()
        self.audio_manager.open_opus()
        self.talk_key.enable()
        self.upsetvolume.enable()
        self.downsetvolume.enable()
        self.led_power_pin.write(1)
        self.power_red_led.blink(250, 250)


if __name__ == "__main__":
    app = Application()
    app.run()

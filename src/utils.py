import sim
import net
import Opus
import audio
import utime
import dataCall
import checkNet
import sys_bus
from machine import Pin
from usr.threading import PriorityQueue, Thread
from usr.logging import getLogger


logger = getLogger(__name__)
volume = 7

# ==================== 音频管理 ====================


class AudioManager(object):

    def __init__(self, channel=0, volume=10, pa_number=29):
        self.aud = audio.Audio(channel)  # 初始化音频播放通道
        self.aud.set_pa(pa_number)
        self.aud.setVolume(volume)  # 设置音量
        self.aud.setCallback(self.audio_cb)
        self.rec = audio.Record(channel)
        self.rec.gain_set(3,9)
        self.__skip = 0
        
    def setvolume_down(self):
        global volume
        volume -= 1
        if volume < 0: volume = 0
        self.aud.setVolume(volume)
        return volume
        
    def setvolume_up(self):
        global volume
        volume += 1
        if volume > 11: volume = 11
        self.aud.setVolume(volume)
        return volume
    
    def setvolume_close(self):
        self.aud.setVolume(0)
        volume = 0
        return volume

    # ========== 音频文件 ====================

    def audio_cb(self, event):
        if event == 0:
            # logger.info('audio play start.')
            pass
        elif event == 7:
            # logger.info('audio play finish.')
            pass
        else:
            pass

    def play(self, file):
        self.aud.play(0, 1, file)
        
    def stop(self):
        self.aud.stopAll()

    # ========= opus ====================

    def open_opus(self):
        self.pcm = audio.Audio.PCM(0, 1, 16000, 2, 1, 15)  # 5 -> 25
        self.opus = Opus(self.pcm, 0, 6000)  # 6000 ~ 128000
    
    def close_opus(self):
        self.opus.close()
        self.pcm.close()
        del self.opus
        del self.pcm
    
    def opus_read(self):
        return self.opus.read(60)

    def opus_write(self, data):
        return self.opus.write(data)

    # ========= vad & kws ====================

    def set_kws_cb(self, cb):
        self.rec.ovkws_set_callback(cb)
            
    def set_vad_cb(self, cb):
        def wrapper(state):
            # if self.__skip != 2:
            #     self.__skip += 1
            #     return
            return cb(state)
        self._callable = wrapper
        self.rec.vad_set_callback(self._callable)

    def end_cb(self, para):
        if(para[0] == "stream"):
            if(para[2] == 1):
                pass
            elif (para[2] == 3):
                pass
            else:
                pass
        else:
            pass
    
    def start_kws(self):
        list=["_xiao_zhi_xiao_zhi","_xiao_tian_xiao_tian","_xiao_zi_xiao_zi","_xiao_shi_xiao_shi","_xiao_si_xiao_si","_xiao_zhi_xiao_zi","_xiao_zi_xiao_zhi"]
        self.rec.ovkws_start(list, 0.7)

    def stop_kws(self):
        self.rec.ovkws_stop()
    
    def start_vad(self):
        self.__skip = 0
        self.rec.vad_start()
    
    def stop_vad(self):
        self.rec.vad_stop()


# ==================== 充电管理 ====================


class ChargeManager(object):

    def __init__(self, GPIOn=3):
        self.charge_pin = Pin(getattr(Pin, "GPIO{}".format(GPIOn)), Pin.OUT, Pin.PULL_PU)
    
    def enable_charge(self):
        self.charge_pin.write(1)
    
    def disable_charge(self):
        self.charge_pin.write(0)


# ==================== 网络管理 ====================


class NetManager(object):
    
    def __init__(self):
        # 注册网络回调
        dataCall.setCallback(self.__net_callback)

    def __net_callback(self, args):
        if args[1] == 0:
            sys_bus.publish("NET_STATE_CHANGE", dict(state="net_disconnect"))
            Thread(target=self.wait_network_ready).start()
        else:
            sys_bus.publish("NET_STATE_CHANGE", dict(state="net_connected"))

    @staticmethod
    def make_cfun():
        net.setModemFun(0, 0)
        utime.sleep_ms(200)
        net.setModemFun(1, 0)

    def wait_network_ready(self):
        while True:
            if sim.getStatus() != 1:
                logger.debug('no sim card.')
                sys_bus.publish("NET_STATE_CHANGE", dict(state="no_sim_card"))
            else:
                logger.debug('sim card ready.')
                sys_bus.publish("NET_STATE_CHANGE", dict(state="net_connecting"))
            code = checkNet.waitNetworkReady(10)
            if code == (3, 1):
                logger.info('network ready.')
                break
            else:
                if net.csqQueryPoll() < 18:
                    sys_bus.publish("NET_STATE_CHANGE", dict(state="no_signal"))
                logger.debug('make cfun.')
                self.make_cfun()


# ==================== 任务调度 ====================


class _Task(object):

    def __init__(self, target, args=(), kwargs={}, priority=0, sync=True, title="anon"):
        self.__target = target
        self.args = args
        self.kwargs = kwargs
        self.priority = priority
        self.sync = sync
        self.title = title
    
    def __str__(self):
        return "<Task: {}>".format(self.title)
        
    def __lt__(self, other):
        # 小顶堆优先级排序
        return self.priority < other.priority
    
    def __gt__(self, other):
        return self.priority > other.priority
    
    def __eq__(self, other):
        return self.priority == other.priority
        
    def run(self):
        if self.sync:
            self.__target(*self.args, **self.kwargs)
        else:
            Thread(target=self.__target, args=self.args, kwargs=self.kwargs).start()


class TaskManager(object):

    def __init__(self):
        self.__q = PriorityQueue()
        self.__main_thread = Thread(target=self.__main_loop)
        
    def __main_loop(self):
        while True:
            task = self.__q.get()
            try:
                task.run()
            except Exception as e:
                logger.error("{} run failed, Exception details: {}".format(task, repr(e)))
            else:
                pass
    
    def run_forever(self):
        logger.info('task manager run forever.')
        self.__main_thread.start()

    def submit(self, func, args=(), kwargs={}, priority=0, title="anon"):
        self.__q.put(_Task(target=func, args=args, kwargs=kwargs, priority=priority, title=title))

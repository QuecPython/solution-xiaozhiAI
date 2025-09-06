import modem
import ujson as json
from usr import uuid
import uwebsocket as ws
from usr.threading import Thread, Condition
from usr.logging import getLogger
import sys_bus
from usr.OTA_test import OTA



logger = getLogger(__name__)


WSS_DEBUG = True
WSS_HOST = "wss://api.tenclass.net/xiaozhi/v1/"
ACCESS_TOKEN = "test-token"
PROTOCOL_VERSION = "1"


class JsonMessage(object):

    def __init__(self, kwargs):
        self.kwargs = kwargs
    
    def __str__(self):
        return str(self.kwargs)
    
    def to_bytes(self):
        return json.dumps(self.kwargs)
    
    @classmethod
    def from_bytes(cls, data):
        return cls(json.loads(data))

    def __getitem__(self, key):
        return self.kwargs[key]


class RespHelper(Condition):

    def __init__(self):
        self.__ack_items = {}
        super().__init__()

    def get(self, request, timeout=None):
        """accept a request and return response matched or none"""
        self.__ack_items[request] = None
        self.wait_for(lambda: self.__ack_items[request] is not None, timeout=timeout)
        return self.__ack_items.pop(request)

    def put(self, response):
        """accept a response and match it with request if possible"""
        for request in self.__ack_items.keys():
            if not self.validate(request, response):
                continue
            self.__ack_items[request] = response
            self.notify_all()
            break

    @staticmethod
    def validate(request, response):
        return request["type"] == response["type"]


class WebSocketClient(object):

    def __init__(self, host=WSS_HOST, debug=WSS_DEBUG):
        self.debug = debug
        self.host = host
        self.__resp_helper = RespHelper()
        self.__recv_thread = None
        self.__audio_message_handler = None
        self.__json_message_handler = None
        self.__last_text_value = None
        self.ota = OTA(mac=self.get_mac_address())
    def __str__(self):
        return "{}(host=\"{}\")".format(type(self).__name__, self.host)

    def __enter__(self):
        self.connect()
        return self
    
    def __exit__(self, *args, **kwargs):
        return self.disconnect()

    def set_callback(self, audio_message_handler=None, json_message_handler=None):
        if audio_message_handler is not None and callable(audio_message_handler):
            self.__audio_message_handler = audio_message_handler
        else:
            raise TypeError("audio_message_handler must be callable")
        
        if json_message_handler is not None and callable(json_message_handler):
            self.__json_message_handler = json_message_handler
        else:
            raise TypeError("json_message_handler must be callable")
        
    @staticmethod
    def get_mac_address():
        # mac = str(uuid.UUID(int=int(modem.getDevImei())))[-12:]
        # return ":".join([mac[i:i + 2] for i in range(0, 12, 2)])
        return "64:e8:33:48:ec:c2"

    @staticmethod
    def generate_uuid() -> str:
        return str(uuid.uuid4())

    @property
    def cli(self):
        __client__ = getattr(self, "__client__", None)
        if __client__ is None:
            raise RuntimeError("{} not connected".format(self))
        return __client__

    def is_state_ok(self):
        return self.cli.sock.getsocketsta() == 4
    
    def disconnect(self):
        """disconnect websocket"""
        __client__ = getattr(self, "__client__", None)
        if __client__ is not None:
            __client__.close()
            del self.__client__
        if self.__recv_thread is not None:
            self.__recv_thread.join()
            self.__recv_thread = None

    def connect(self):
        """connect websocket"""
        __client__ = ws.Client.connect(
            self.host, 
            headers={
                "Authorization": "Bearer {}".format(ACCESS_TOKEN),
                "Protocol-Version": PROTOCOL_VERSION,
                "Device-Id": self.get_mac_address(),
                "Client-Id": self.generate_uuid()
            }, 
            debug=self.debug
        )

        try:

            self.__recv_thread = Thread(target=self.__recv_thread_worker)
            self.__recv_thread.start(stack_size=64)
        except Exception as e:
            __client__.close()
            logger.error("{} connect failed, Exception details: {}".format(self, repr(e)))
        else:
            setattr(self, "__client__", __client__)
            return __client__

    def __recv_thread_worker(self):
        while True:
            try:
                raw = self.recv()
            except Exception as e:
                logger.info("{} recv thread break, Exception details: {}".format(self, repr(e)))
                break
            
            if raw is None or raw == "":
                logger.info("{} recv thread break, Exception details: read none bytes, websocket disconnect".format(self))
                break
            
            try:
                m = JsonMessage.from_bytes(raw)
            except Exception as e:
                self.__handle_audio_message(raw)
            else:
                if m["type"] == "hello":
                    with self.__resp_helper:
                        self.__resp_helper.put(m)
                else:
                    self.__handle_json_message(m)

    def __handle_audio_message(self, raw):
        if self.__audio_message_handler is None:
            logger.warn("audio message handler is None, did you forget to set it?")
            return
        try:
            self.__audio_message_handler(raw)
        except Exception as e:
            logger.error("{} handle audio message failed, Exception details: {}".format(self, repr(e)))
    
    def __handle_json_message(self, msg):
        if self.__json_message_handler is None:
            logger.warn("json message handler is None, did you forget to set it?")
            return
        try:
            self.__json_message_handler(msg)
        except Exception as e:
            logger.debug("{} handle json message failed, Exception details: {}".format(self, repr(e)))
            
    # def topic(text_value):
        
            
    def send(self, data):
        """send data to server"""
        # logger.debug("send data: ", data)
        self.cli.send(data)

    def recv(self):
        """receive data from server, return None or "" means disconnection"""
        data = self.cli.recv()
        if type(data) == str:
            data_dict = json.loads(data)
            text_value = data_dict.get("text")
            
            # 对比 text_value 和上次的值是否相同
            if text_value != self.__last_text_value and text_value is not None:
                print(text_value)  # 仅在不同时打印
                self.__last_text_value = text_value  # 更新为最新的 text_value
        # logger.debug("recv data: ", data)
        return data



    def hello(self):
        req = JsonMessage(
            {
                "type": "hello",
                "version": 1,
                "transport": "websocket",
                "audio_params": {
                    "format": "opus",
                    "sample_rate": 16000,
                    "channels": 1,
                    "frame_duration": 100
                },
                "features": {
                    "consistent_sample_rate": True
                }
            }
        )
        with self.__resp_helper:
            self.send(req.to_bytes())
            resp = self.__resp_helper.get(req, timeout=10)
            # {'transport': 'websocket', 'type': 'hello', 'session_id': 'd2091edb', 'audio_params': {'frame_duration': 60, 'channels': 1, 'format': 'opus', 'sample_rate': 24000}, 'version': 1}
            # logger.debug("hello resp: ", resp)
            return resp

    def listen(self, state, mode="auto", session_id=""):
        with self.__resp_helper:
            self.send(
                JsonMessage(
                    {
                        "session_id": session_id,  # Websocket协议不返回 session_id，所以消息中的会话ID可设置为空
                        "type": "listen",
                        "state": state,  # "start": 开始识别; "stop": 停止识别; "detect": 唤醒词检测
                        "mode": mode  # "auto": 自动停止; "manual": 手动停止; "realtime": 持续监听
                    }
                ).to_bytes()
            )
    
    def wakeword_detected(self, wakeword, session_id=""):
        with self.__resp_helper:
            self.send(
                JsonMessage(
                    {
                        "session_id": session_id,
                        "type": "listen",
                        "state": "detect",
                        "text": wakeword  # 唤醒词
                    }
                ).to_bytes()
            )
    
    def abort(self, session_id="", reason=""):
        with self.__resp_helper:
            self.send(
                JsonMessage(
                    {
                        "session_id": session_id,
                        "type": "abort",
                        "reason": reason
                    }
                ).to_bytes()
            )

    def report_iot_descriptors(self, descriptors, session_id=""):
        with self.__resp_helper:
            self.send(
                JsonMessage(
                    {
                        "session_id": session_id,
                        "type": "iot",
                        "descriptors": descriptors
                    }
                ).to_bytes()
            )

    def report_iot_states(self, states, session_id=""):
        with self.__resp_helper:
            self.send(
                JsonMessage(
                    {
                        "session_id": session_id,
                        "type": "iot",
                        "states": states
                    }
                ).to_bytes()
            )


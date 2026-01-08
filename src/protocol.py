import modem
import ujson as json
from usr import uuid
import uwebsocket as ws
from usr.threading import Thread, Condition
from usr.logging import getLogger
import sys_bus
from usr.OTA_test import OTA
import gc



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
        global WSS_HOST
        self.ota = OTA(mac=self.get_mac_address())
        self.debug = debug
        WSS_HOST = self.ota.run()
        self.host = WSS_HOST['websocket']["url"]
        self.__resp_helper = RespHelper()
        self.__recv_thread = None
        self.__audio_message_handler = None
        self.__json_message_handler = None
        self.__last_text_value = None
        logger.info("OTA:{}".format(WSS_HOST))
        

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
        mac = str(uuid.UUID(int=int(modem.getDevImei())))[-12:]
        return ":".join([mac[i:i + 2] for i in range(0, 12, 2)])
        # return "64:e8:33:48:ec:c9"

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
                "Authorization": "Bearer {}".format(WSS_HOST["websocket"]["token"]),
                "Protocol-Version": WSS_HOST["firmware"]["version"],
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
                # print("内存：",gc.mem_free())
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
                    "consistent_sample_rate": True,
                    "mcp": True
                }
            }
        )
        try:
            with self.__resp_helper:
                self.send(req.to_bytes())
                resp = self.__resp_helper.get(req, timeout=10)
                return resp
        except TimeoutError as e:
            # 记录日志并返回默认值或抛出自定义异常
            logger.error("Request timed out: {}",e)
            return None

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

# ...existing code...

    def send_mcp(self, payload, session_id=""):
        """
        发送标准MCP消息,payload为JSON-RPC 2.0格式字典
        """
        with self.__resp_helper:
            self.send(
                JsonMessage(
                    {
                        "session_id": session_id,
                        "type": "mcp",
                        "payload": payload
                    }
                ).to_bytes()        
            )

    def mcp_initialize(self, capabilities=None, session_id="", req_id=1):
        """
        发送MCP initialize响应
        """
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2025-9-03",
                "capabilities": {
                    "tools":{},
                    "notifications": {}
                },
                "serverInfo": {
                "name": 'xiaozhi-mqtt-client',
                "version": "1.0.0"
            }
        }
        }  
        self.send_mcp(payload, session_id)
    
    def mcp_tools_list(self,session_id="", req_id=2):
        """
        发送MCP tools/list响应请求
        """
        payload = {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                {
                    "name": "self.setvolume_down()",
                    "description": "只通过调用setvolume_down方法来控制音量变小,接收到回应后会播报当前音量大小",
                    "inputSchema": {}
                },
                {
                    "name": "self.setvolume_up()",
                    "description": "只通过调用setvolume_up方法来控制音量变大,接收到回应后会播报当前音量大小",
                    "inputSchema": {}
                },
                {
                    "name": "self.setvolume_close()",
                    "description": "只通过调用setvolume_close方法来静音,接收到回应后会播报当前音量大小",
                    "inputSchema": {}
                },
                {
                    "name": "self.setvolume()",
                    "description": "设置音量大小,接收到回应后会播报当前音量大小,volume范围是0-11",
                    "inputSchema": {
                        "volume": {
                            "type": "int",
                            "minimum": 0,
                            "maximum": 11
                        }
                    },
                    "required": ["volume"]
                },               
                {
                    "name": "self.new_name()",
                    "description": "当需要改唤醒词时就调用该new_name方法来设置新的唤醒词,接收到回应后会播报当前唤醒词,输入的参数名是name且内容只能是拼音，每个拼音之间用'_'连接起来，例如我说唤醒词改成'小智小智'则传入参数为'_xiao_zhi_xiao_zhi'，不可以传入汉字",
                    "parameters": {
                    "name": {
                        "type": "text",
                    }
                },
                    "required": ["name"]
                }
                ],
            }
            }
        
        self.send_mcp(payload, session_id)
        
    def mcp_tools_call(self, session_id="", req_id="", error=None, tool_name="",args=None):
        """
        发送MCP tools/call响应
        :param error: 如果为None则返回成功响应,否则返回错误响应(字典,包含code和message)
        """
        if error is None:
            if tool_name == "self.setvolume_down()":
                payload = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            { "type": "text", "text": "音量已调小 "}
                        ],
                        "isError": False
                    }
                }
            elif tool_name == "self.setvolume_up()":
                payload = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            { "type": "text", "text": "音量已调大" }
                        ],
                        "isError": False
                    }
                }
            elif tool_name == "self.setvolume_close()":
                payload = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            { "type": "text", "text": "已静音" }
                        ],
                        "isError": False
                    }
                }
            elif tool_name == "self.setvolume()":
                payload = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            { "type": "text", "text": "音量已设置为{}".format(args)}
                        ],
                        "isError": False
                    }
                }
            elif tool_name == "self.new_name()":
                payload = {
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            { "type": "text", "text": "唤醒词已更改为{}".format(args)}
                        ],
                        "isError": False
                    }
                }
        else:
            payload = {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {
                    "code": error.get("code", -32601),
                    "message": error.get("message", "Unknown error")
                }
            }
        
        self.send_mcp(payload, session_id)
        
    def mcp_notify(self, method, params, session_id=""):
        """
        设备主动发送MCP通知  
        """
        payload = {
            "jsonrpc": "2.0",
            "method":  "notifications/state_changed",
            "params": {
                "newState": "idle",
                "oldState": "connecting"
                    }
        }
        self.send_mcp(payload, session_id)

# ...existing code...  
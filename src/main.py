# coding=utf-8
"""
语音聊天助手 - Voice Chat Assistant

功能：
1. 持续接受用户文字输入
2. 调用大模型生成文字回复
3. 将回复转为克隆语音播放

依赖安装：
- Windows: python -m pip install pyaudio
- Mac: brew install portaudio && pip install pyaudio
- Linux: sudo apt-get install python3-pyaudio
"""

import pyaudio
import os
import requests
import base64
import pathlib
import threading
import dashscope
from dashscope import Generation
from dashscope.audio.qwen_tts_realtime import (
    QwenTtsRealtime,
    QwenTtsRealtimeCallback,
    AudioFormat,
)

# ======= 常量配置 =======
TTS_MODEL = "qwen3-tts-vc-realtime-2026-01-15"  # TTS 模型
LLM_MODEL = "qwen-turbo"  # 大模型，可选: qwen-turbo, qwen-plus, qwen-max
DEFAULT_PREFERRED_NAME = "inory"
DEFAULT_AUDIO_MIME_TYPE = "audio/mpeg"
VOICE_FILE_PATH = r"data\inputs\inory.MP3"  # 用于声音复刻的音频文件
VOICE_ID = "qwen-tts-vc-inory-voice-20260224230321214-1dcf"

SYSTEM_PROMPT = """你罪恶王冠女主角楪祈。现在需要你回复你的好友的一些对话。
回复要求：
- 使用自然的口语表达
- 贴近原作设定语气
"""


# ======= 声音复刻 =======
def create_voice(
    file_path: str,
    target_model: str = TTS_MODEL,
    preferred_name: str = DEFAULT_PREFERRED_NAME,
    audio_mime_type: str = DEFAULT_AUDIO_MIME_TYPE,
) -> str:
    """从音频文件创建专属音色"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("请设置环境变量 DASHSCOPE_API_KEY")

    file_path_obj = pathlib.Path(file_path)
    if not file_path_obj.exists():
        raise FileNotFoundError(f"音频文件不存在: {file_path}")

    base64_str = base64.b64encode(file_path_obj.read_bytes()).decode()
    data_uri = f"data:{audio_mime_type};base64,{base64_str}"

    url = "https://dashscope.aliyuncs.com/api/v1/services/audio/tts/customization"
    payload = {
        "model": "qwen-voice-enrollment",
        "input": {
            "action": "create",
            "target_model": target_model,
            "preferred_name": preferred_name,
            "audio": {"data": data_uri},
        },
    }
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }

    resp = requests.post(url, json=payload, headers=headers)
    if resp.status_code != 200:
        raise RuntimeError(f"创建音色失败: {resp.status_code}, {resp.text}")

    try:
        voice_id = resp.json()["output"]["voice"]
        print(f"[声音复刻] 音色创建成功: {voice_id}")
        return voice_id
    except (KeyError, ValueError) as e:
        raise RuntimeError(f"解析响应失败: {e}")


def init_dashscope():
    """初始化 DashScope API Key"""
    api_key = os.getenv("DASHSCOPE_API_KEY")
    if not api_key:
        raise RuntimeError("请设置环境变量 DASHSCOPE_API_KEY")
    dashscope.api_key = api_key


# ======= 大模型对话 =======
class ChatBot:
    """大模型对话管理器"""

    def __init__(self, model: str = LLM_MODEL, system_prompt: str = SYSTEM_PROMPT):
        self.model = model
        self.messages = [{"role": "system", "content": system_prompt}]

    def chat(self, user_input: str) -> str:
        """发送消息并获取回复（非流式）"""
        self.messages.append({"role": "user", "content": user_input})

        response = Generation.call(
            model=self.model,
            messages=self.messages,
            result_format="message",
        )

        if response.status_code != 200:
            raise RuntimeError(f"LLM 调用失败: {response.code}, {response.message}")

        assistant_msg = response.output.choices[0].message.content
        self.messages.append({"role": "assistant", "content": assistant_msg})
        return assistant_msg

    def chat_stream(self, user_input: str):
        """发送消息并流式获取回复（生成器）"""
        self.messages.append({"role": "user", "content": user_input})

        responses = Generation.call(
            model=self.model,
            messages=self.messages,
            result_format="message",
            stream=True,
            incremental_output=True,
        )

        full_response = ""
        for response in responses:
            if response.status_code != 200:
                raise RuntimeError(f"LLM 调用失败: {response.code}, {response.message}")
            chunk = response.output.choices[0].message.content
            full_response += chunk
            yield chunk

        self.messages.append({"role": "assistant", "content": full_response})

    def clear_history(self):
        """清空对话历史（保留系统提示）"""
        self.messages = [self.messages[0]]


# ======= TTS 回调类 =======
class TTSCallback(QwenTtsRealtimeCallback):
    """TTS 流式回调，实时播放音频"""

    def __init__(self):
        self.complete_event = threading.Event()
        self._player = pyaudio.PyAudio()
        self._stream = self._player.open(
            format=pyaudio.paInt16, channels=1, rate=24000, output=True
        )
        self._tts_client = None  # 将在外部设置

    def set_tts_client(self, client):
        self._tts_client = client

    def on_open(self) -> None:
        pass  # 静默处理

    def on_close(self, close_status_code, close_msg) -> None:
        self._stream.stop_stream()
        self._stream.close()
        self._player.terminate()

    def on_event(self, response: dict) -> None:
        try:
            event_type = response.get("type", "")
            if event_type == "response.audio.delta":
                audio_data = base64.b64decode(response["delta"])
                self._stream.write(audio_data)
            elif event_type == "session.finished":
                self.complete_event.set()
        except Exception as e:
            print(f"[错误] TTS 回调异常: {e}")

    def wait_for_finished(self):
        self.complete_event.wait()

    def reset(self):
        """重置完成事件，准备下一次播放"""
        self.complete_event.clear()


# ======= 语音聊天助手 =======
class VoiceChatAssistant:
    """语音聊天助手主类"""

    def __init__(self, voice_file: str = VOICE_FILE_PATH):
        print("[系统] 正在初始化语音聊天助手...")
        init_dashscope()

        # 初始化大模型
        self.chatbot = ChatBot()
        print("[系统] 大模型初始化完成")

        # 使用已有音色或创建新音色
        if VOICE_ID:
            print(f"[系统] 使用已有音色: {VOICE_ID}")
            self.voice_id = VOICE_ID
        else:
            print("[系统] 正在创建专属音色...")
            self.voice_id = create_voice(voice_file)

        # 初始化 TTS
        self.callback = TTSCallback()
        self.tts_client = QwenTtsRealtime(
            model=TTS_MODEL,
            callback=self.callback,
            url="wss://dashscope.aliyuncs.com/api-ws/v1/realtime",
        )
        self.callback.set_tts_client(self.tts_client)

        print("[系统] 初始化完成！输入文字开始对话，输入 'quit' 退出，输入 'clear' 清空历史\n")

    def speak(self, text: str):
        """将文本转为语音并播放"""
        self.callback.reset()
        self.tts_client.connect()

        self.tts_client.update_session(
            voice=self.voice_id,
            response_format=AudioFormat.PCM_24000HZ_MONO_16BIT,
            mode="server_commit",
        )

        # 发送文本
        self.tts_client.append_text(text)
        self.tts_client.finish()

        # 等待播放完成
        self.callback.wait_for_finished()

    def chat(self, user_input: str) -> str:
        """处理用户输入，返回并播放回复"""
        print(f"\n[用户] {user_input}")

        # 获取大模型回复
        print("[助手] ", end="", flush=True)
        response = self.chatbot.chat(user_input)
        print(response)

        # 语音播放
        print("[语音] 正在播放...")
        self.speak(response)
        print("[语音] 播放完成\n")

        return response

    def run(self):
        """运行交互式对话循环"""
        print("=" * 50)
        print("欢迎使用语音聊天助手！")
        print("- 输入文字与我对话")
        print("- 输入 'quit' 或 'exit' 退出")
        print("- 输入 'clear' 清空对话历史")
        print("=" * 50 + "\n")

        while True:
            try:
                user_input = input("[请输入] > ").strip()

                if not user_input:
                    continue

                if user_input.lower() in ("quit", "exit", "q"):
                    print("\n[系统] 再见！")
                    break

                if user_input.lower() == "clear":
                    self.chatbot.clear_history()
                    print("[系统] 对话历史已清空\n")
                    continue

                self.chat(user_input)

            except KeyboardInterrupt:
                print("\n\n[系统] 检测到中断，正在退出...")
                break
            except Exception as e:
                print(f"\n[错误] {e}\n")


# ======= 主入口 =======
def main():
    """程序主入口"""
    assistant = VoiceChatAssistant()
    assistant.run()


if __name__ == "__main__":
    main()
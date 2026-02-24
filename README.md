# Voice Clone - 语音聊天助手

基于阿里云 DashScope 的语音聊天助手，支持声音克隆 + 大模型对话 + 实时语音合成。

## 功能特性

- **声音克隆**：从音频样本创建专属音色
- **大模型对话**：接入 Qwen 大模型进行智能对话
- **实时语音合成**：将文字回复转为克隆语音实时播放
- **持续交互**：支持多轮对话，保留上下文

## 架构流程

```
用户输入 → Qwen LLM → 文字回复 → Qwen TTS (声音克隆) → 实时播放
```

## 环境要求

- Python >= 3.13
- 阿里云 DashScope API Key

## 安装

```bash
# 克隆项目
git clone <repo-url>
cd voiceclone

# 安装依赖 (使用 uv)
uv sync

# 或使用 pip
pip install -e .
```

### PyAudio 安装

```bash
# Windows
python -m pip install pyaudio

# macOS
brew install portaudio && pip install pyaudio

# Linux (Debian/Ubuntu)
sudo apt-get install python3-pyaudio
```

## 配置

设置环境变量：

```bash
# Windows PowerShell
$env:DASHSCOPE_API_KEY = "sk-xxx"

# Linux/macOS
export DASHSCOPE_API_KEY="sk-xxx"
```

## 使用

```bash
uv run python src/main.py
```

### 交互命令

| 命令 | 说明 |
|------|------|
| 直接输入文字 | 与助手对话 |
| `clear` | 清空对话历史 |
| `quit` / `exit` / `q` | 退出程序 |

## 自定义配置

编辑 `src/main.py` 顶部的常量：

```python
TTS_MODEL = "qwen3-tts-vc-realtime-2026-01-15"  # TTS 模型
LLM_MODEL = "qwen-turbo"  # 大模型: qwen-turbo, qwen-plus, qwen-max
VOICE_FILE_PATH = r"data\inputs\inory.MP3"  # 声音样本文件
VOICE_ID = ""  # 已有音色ID，留空则自动创建
SYSTEM_PROMPT = "..."  # 助手人设提示词
```

## 项目结构

```
voiceclone/
├── src/
│   └── main.py          # 主程序
├── data/
│   ├── inputs/          # 声音样本
│   ├── outputs/         # 输出文件
│   └── temp/            # 临时文件
├── pyproject.toml       # 项目配置
└── README.md
```

## License

MIT
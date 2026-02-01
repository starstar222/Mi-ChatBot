# 轻量级 TTS 组件

这是一个从 dashscope-sdk-python 中提取的轻量级 CosyVoice TTS 组件，去除了所有重量级依赖，只保留核心的语音合成功能。

## 特点

- **轻量级**: 只依赖 `websocket-client`，无需安装完整的 dashscope SDK
- **功能完整**: 支持流式和非流式语音合成
- **兼容性好**: API 接口与原 dashscope TTS 完全兼容
- **易于集成**: 可以直接替换原有的 dashscope TTS 导入

## 安装依赖

```bash
pip install websocket-client>=1.0.0
```

## 使用方法

### 基本使用

```python
from lightweight_tts import SpeechSynthesizer, AudioFormat, ResultCallback

# 设置 API 密钥
import os
os.environ['DASHSCOPE_API_KEY'] = 'your-api-key'

# 创建合成器
synthesizer = SpeechSynthesizer(
    model="cosyvoice-v2",
    voice="longhua_v2",
    format=AudioFormat.PCM_16000HZ_MONO_16BIT
)

# 流式合成
synthesizer.streaming_call("你好，这是一个测试。")
synthesizer.streaming_complete()
```

### 使用回调处理音频数据

```python
class MyCallback(ResultCallback):
    def on_data(self, data: bytes):
        # 处理音频数据
        print(f"接收到音频数据: {len(data)} 字节")
    
    def on_complete(self):
        print("合成完成")

callback = MyCallback()
synthesizer = SpeechSynthesizer(
    model="cosyvoice-v2",
    voice="longhua_v2",
    format=AudioFormat.PCM_16000HZ_MONO_16BIT,
    callback=callback
)

synthesizer.streaming_call("你好，这是一个测试。")
synthesizer.streaming_complete()
```

## 替换原有代码

如果你之前使用的是：
```python
from dashscope.audio.tts_v2 import *
```

现在可以直接替换为：
```python
from lightweight_tts import *
```

API 接口完全兼容，无需修改其他代码。

## 支持的音频格式

- PCM: 8kHz-48kHz, 16bit, mono
- WAV: 8kHz-48kHz, 16bit, mono  
- MP3: 8kHz-48kHz, mono, 128-256kbps
- OGG Opus: 8kHz-48kHz, mono, 16-64kbps

## 环境变量

- `DASHSCOPE_API_KEY`: DashScope API 密钥（必需）

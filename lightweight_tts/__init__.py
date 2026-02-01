# Lightweight TTS Component
# 独立的 CosyVoice TTS 组件，无需完整的 dashscope 依赖

from .speech_synthesizer import SpeechSynthesizer, AudioFormat, ResultCallback

__version__ = "1.0.0"
__all__ = ["SpeechSynthesizer", "AudioFormat", "ResultCallback"]

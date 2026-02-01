"""
CosyVoice流式语音合成播放器
基于阿里云CosyVoice-v2模型的流式TTS接口封装
"""

import asyncio
import os
import subprocess
import threading
import time
import wave
from collections import deque
from contextlib import contextmanager
from dataclasses import dataclass
from typing import (
    AsyncGenerator, 
    Awaitable, 
    Callable, 
    Generator, 
    Optional, 
    Union,
    Any,
    Dict
)

from lightweight_tts import SpeechSynthesizer, AudioFormat, ResultCallback
from typing_extensions import Annotated


@dataclass
class PlaybackMetrics:
    """播放性能指标"""
    request_id: Optional[str] = None
    first_audio_delay: Optional[float] = None
    total_duration: Optional[float] = None
    audio_bytes: int = 0


class Logger:
    """默认日志器"""
    def debug(self, msg: str) -> None: print(f"[DEBUG] {msg}")
    def info(self, msg: str) -> None: print(f"[INFO] {msg}")
    def warning(self, msg: str) -> None: print(f"[WARNING] {msg}")
    def error(self, msg: str) -> None: print(f"[ERROR] {msg}")


class AudioPlayer:
    """音频播放器封装"""
    
    def __init__(self, logger: Any):
        self.logger = logger
        self.sox_process: Optional[subprocess.Popen] = None
        self._lock = threading.RLock()
        
    def initialize(self) -> bool:
        """初始化sox播放器进程"""
        try:
            sox_cmd = [
                'sox', '-t', 'raw', '-r', '16000', '-c', '1', 
                '-e', 'signed-integer', '-b', '16', '-', '-d', '-V1'
            ]
            
            self.sox_process = subprocess.Popen(
                sox_cmd,
                stdin=subprocess.PIPE,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=False
            )
            self.logger.info("Sox播放器已初始化")
            return True
        except Exception as e:
            self.logger.error(f"初始化sox播放器失败: {e}")
            self.sox_process = None
            return False
    
    def write_audio(self, data: bytes) -> bool:
        """写入音频数据"""
        with self._lock:
            if self.sox_process and self.sox_process.poll() is None:
                try:
                    self.sox_process.stdin.write(data)
                    self.sox_process.stdin.flush()
                    return True
                except Exception as e:
                    self.logger.error(f"写入音频数据失败: {e}")
                    return False
        return False
    
    def reset(self) -> None:
        """重置播放器"""
        with self._lock:
            if self.sox_process and self.sox_process.poll() is None:
                try:
                    self.sox_process.terminate()
                    self.sox_process.wait(timeout=1.0)
                except Exception:
                    try:
                        self.sox_process.kill()
                    except Exception:
                        pass
            self.initialize()
    
    def close(self) -> None:
        """关闭播放器"""
        with self._lock:
            if self.sox_process:
                try:
                    self.sox_process.stdin.close()
                    self.sox_process.wait(timeout=3.0)
                except subprocess.TimeoutExpired:
                    self.sox_process.terminate()
                    try:
                        self.sox_process.wait(timeout=1.0)
                    except subprocess.TimeoutExpired:
                        self.sox_process.kill()
                except Exception as e:
                    self.logger.error(f"关闭sox进程时出错: {e}")
                finally:
                    self.sox_process = None


class VolumeController:
    """音量控制器"""
    
    def __init__(self, logger: Any):
        self.logger = logger
        self._volume = 50
        
    def set_volume(self, volume_percent: int) -> bool:
        """设置系统音量"""
        volume_percent = max(0, min(100, volume_percent))
        system_volume = round(volume_percent * 20 / 100)
        
        try:
            result = subprocess.run(
                ['termux-volume', 'system', str(system_volume)],
                capture_output=True,
                text=True,
                timeout=3
            )
            
            if result.returncode == 0:
                self._volume = volume_percent
                self.logger.info(f"音量已设置为: {volume_percent}% (系统音量: {system_volume}/20)")
                return True
            else:
                self.logger.warning(f"设置系统音量失败: {result.stderr}")
                return False
                
        except subprocess.TimeoutExpired:
            self.logger.warning("设置系统音量超时")
        except FileNotFoundError:
            self.logger.warning("termux-volume命令未找到，请安装termux-api包")
        except Exception as e:
            self.logger.error(f"设置系统音量出错: {e}")
        return False
    
    def get_volume(self) -> int:
        """获取当前音量"""
        return self._volume
    
    def change_volume(self, change: int) -> str:
        """调整音量"""
        original_volume = self._volume
        new_volume = self._volume + change
        
        if new_volume < 5:
            new_volume = 5
            result_text = f"音量已调至最小{new_volume}"
        elif new_volume > 35:
            new_volume = 35
            result_text = f"音量已调至最大{new_volume}"
        else:
            result_text = f"音量已由{original_volume}调整为{new_volume}"
            
        if self.set_volume(new_volume):
            return result_text
        else:
            return "音量设置失败"


class StreamingCallback(ResultCallback):
    """CosyVoice流式回调处理"""
    
    def __init__(self, player: 'CosyVoiceStreamingPlayer'):
        super().__init__()
        self.player = player
        self.logger = player.logger
        self.audio_data: list[bytes] = []
        self.total_audio_bytes = 0
        
    def on_open(self) -> None:
        """连接建立时的处理"""
        # 确保播放器已初始化
        if self.player.enable_audio_playback and not self.player.audio_player.sox_process:
            self.player.audio_player.initialize()
            
        # 重置状态
        self.audio_data = []
        self.total_audio_bytes = 0
        
    def on_data(self, data: bytes) -> None:
        """接收到音频数据时的处理"""
        if self.player._interrupt_event.is_set():
            return
            
        # 记录首次音频时间
        if self.player.metrics.first_audio_delay is None and self.player._start_time:
            self.player.metrics.first_audio_delay = (time.time() - self.player._start_time) * 1000
            
        # 播放音频
        if self.player.enable_audio_playback:
            if not self.player.audio_player.write_audio(data):
                # 尝试重新初始化
                if not self.player._interrupt_event.is_set():
                    self.player.audio_player.reset()
                    
        # 保存音频数据
        if self.player.save_audio and not self.player._interrupt_event.is_set():
            self.audio_data.append(data)
            
        # 更新统计
        if not self.player._interrupt_event.is_set():
            self.total_audio_bytes += len(data)
            self.player.metrics.audio_bytes += len(data)
            
    def on_complete(self) -> None:
        """合成完成时的处理"""
        pass
        
    def on_error(self, message: str) -> None:
        """出错时的处理"""
        self.logger.error(f"CosyVoice语音合成出错: {message}")
        
    def on_close(self) -> None:
        """连接关闭时的处理"""
        # 保存音频文件
        if self.player.save_audio and self.audio_data:
            self._save_audio_file()
            
        # 发送结束标记
        if self.player.enable_audio_playback:
            end_silence = b'\x00' * 4800  # 0.15秒静音
            self.player.audio_player.write_audio(end_silence)
            
        # 清除会话状态
        self.player._session_event.clear()
        
    def _save_audio_file(self) -> None:
        """保存音频文件"""
        timestamp = time.strftime("%Y%m%d_%H%M%S")
        save_dir = self.player.audio_file_path or 'output'
        os.makedirs(save_dir, exist_ok=True)
        
        filename = os.path.join(save_dir, f'cosyvoice_audio_{timestamp}.wav')
        
        with wave.open(filename, 'wb') as wav_file:
            wav_file.setnchannels(1)
            wav_file.setsampwidth(2)
            wav_file.setframerate(16000)
            wav_file.writeframes(b''.join(self.audio_data))
            
        self.logger.info(f"音频已保存到: {filename}")
        
    def on_event(self, message: Any) -> None:
        """接收到事件消息时的处理"""
        pass


class CosyVoiceStreamingPlayer:
    """CosyVoice流式语音合成播放器"""
    
    def __init__(self, 
                 api_key: Optional[str] = None,
                 model: str = "cosyvoice-v2",
                 voice: str = "longhua_v2",
                 save_audio: bool = False,
                 audio_file_path: Optional[str] = None,
                 enable_audio_playback: bool = True,
                 volume: int = 50,
                 logger: Optional[Any] = None):
        """
        初始化CosyVoice播放器
        
        Args:
            api_key: DashScope API密钥
            model: 模型名称
            voice: 音色名称
            save_audio: 是否保存音频文件
            audio_file_path: 音频保存路径
            enable_audio_playback: 是否启用实时音频播放
            volume: 初始音量
            logger: 日志器实例
        """
        # API配置
        self.api_key = self._get_api_key(api_key)
        self.model = model
        self.voice = voice
        
        # 功能配置
        self.save_audio = save_audio
        self.audio_file_path = audio_file_path
        self.enable_audio_playback = enable_audio_playback
        self.initial_volume = volume
        
        # 组件初始化
        self.logger = logger or Logger()
        self.audio_player = AudioPlayer(self.logger)
        self.volume_controller = VolumeController(self.logger)
        self.synthesizer: Optional[SpeechSynthesizer] = None
        self.callback: Optional[StreamingCallback] = None
        
        # 状态管理
        self._session_event = threading.Event()
        self._interrupt_event = threading.Event()
        self._start_time: Optional[float] = None
        self.metrics = PlaybackMetrics()
        
        # 队列管理
        self._async_queue: Optional[asyncio.Queue] = None
        self._async_queue_task: Optional[asyncio.Task] = None
        self._async_queue_lock = asyncio.Lock()
        self._post_play_callback: Optional[Callable[[float], Awaitable[None]]] = None
        
        self._sync_queue = deque(maxlen=10)
        self._sync_queue_lock = threading.Lock()
        self._sync_consumer_thread: Optional[threading.Thread] = None
        self._sync_consumer_running = False
        
        # 初始化
        self._initialize()
        
    def _get_api_key(self, api_key: Optional[str]) -> str:
        """获取API密钥"""
        if api_key:
            return api_key
        elif 'DASHSCOPE_API_KEY' in os.environ:
            return os.environ['DASHSCOPE_API_KEY']
        else:
            raise ValueError("请提供API密钥或设置DASHSCOPE_API_KEY环境变量")
    
    def _initialize(self) -> None:
        """初始化播放器"""
        if self.enable_audio_playback:
            self.audio_player.initialize()
            self.volume_controller.set_volume(self.initial_volume)
            
        self.callback = StreamingCallback(self)
        self._start_sync_consumer()
        self.logger.info("CosyVoice播放器已初始化")
    
    # 音量控制
    def set_volume(self, volume_percent: int) -> None:
        """设置播放器音量"""
        self.volume_controller.set_volume(volume_percent)
        
    def get_volume(self) -> int:
        """获取当前音量"""
        return self.volume_controller.get_volume()
    
    def volume_change(self, change: Annotated[int, "音量更改值，范围(-40~+40，step=10)"]) -> str:
        """调整音量"""
        return self.volume_controller.change_volume(change)
    
    # 会话管理
    def start_session(self) -> bool:
        """开始新的TTS会话"""
        if self._session_event.is_set():
            self.logger.warning("TTS stream已占用，无法开始新会话")
            return False
            
        self._session_event.set()
        self._interrupt_event.clear()
        self._start_time = None
        self.metrics = PlaybackMetrics()
        
        self.synthesizer = SpeechSynthesizer(
            model=self.model,
            voice=self.voice,
            api_key=self.api_key,
            format=AudioFormat.PCM_16000HZ_MONO_16BIT,
            callback=self.callback
        )
        
        self.logger.info(f"CosyVoice会话已启动，音色: {self.voice}")
        return True
    
    def send_text(self, text: str) -> None:
        """发送文本到TTS"""
        if not self._session_event.is_set():
            raise RuntimeError("请先调用start_session()开始会话")
        if self._interrupt_event.is_set():
            return
            
        if self._start_time is None:
            self._start_time = time.time()
            
        self.synthesizer.streaming_call(text)
    
    def finish_session(self) -> None:
        """结束TTS会话"""
        if not self._session_event.is_set():
            self.logger.warning("TTS会话未激活，无法结束会话")
            return
            
        try:
            self.synthesizer.streaming_complete()
        except Exception as e:
            self.logger.error(f"结束会话时出错: {e}")
    
    async def async_finish_session(self, wait_for_completion: bool = True) -> None:
        """异步结束TTS会话"""
        if not self._session_event.is_set():
            self.logger.warning("TTS会话未激活，无法结束会话")
            return
            
        try:
            self.synthesizer.async_streaming_complete()
            if wait_for_completion:
                while self._session_event.is_set():
                    await asyncio.sleep(0.1)
        except Exception as e:
            self.logger.error(f"结束会话时出错: {e}")
    
    def interrupt(self) -> str:
        """打断当前语音播放，被要求停止说话时调用"""
        if not self._session_event.is_set():
            self.logger.warning("TTS会话未激活，无法打断播放")
            return "没有正在播放的语音"
            
        # 取消TTS合成
        if self.synthesizer:
            try:
                self.synthesizer.streaming_cancel()
            except Exception as e:
                self.logger.error(f"取消TTS合成时出错: {e}")
                
        # 设置中断标志
        self._interrupt_event.set()
        
        # 重置播放器
        if self.enable_audio_playback:
            self.audio_player.reset()
            
        # 清空音频缓冲
        if self.callback:
            self.callback.audio_data = []
            
        self._session_event.clear()
        self.logger.info("CosyVoice播放已被打断")
        return "语音输出已打断"
    
    # 状态查询
    def is_busy(self) -> bool:
        """查询忙碌状态"""
        return self._session_event.is_set() and not self._interrupt_event.is_set()
    
    def is_finish(self) -> bool:
        """判断是否播放完成"""
        session_finished = not self._session_event.is_set()
        sync_queue_empty = len(self._sync_queue) == 0
        async_queue_empty = self._async_queue is None or self._async_queue.qsize() == 0
        return session_finished and sync_queue_empty and async_queue_empty
    
    def get_metrics(self) -> Dict[str, Any]:
        """获取性能指标"""
        metrics = {
            "request_id": self.metrics.request_id,
            "first_audio_delay": self.metrics.first_audio_delay,
            "audio_bytes": self.metrics.audio_bytes
        }
        
        if self.synthesizer:
            try:
                metrics["request_id"] = self.synthesizer.get_last_request_id()
                metrics["first_audio_delay"] = self.synthesizer.get_first_package_delay()
            except Exception:
                pass
                
        return metrics
    
    # 同步TTS接口
    def tts(self, text: str) -> bool:
        """直接调用TTS"""
        if not self.start_session():
            return False
        self.send_text(text)
        self.finish_session()
        return True
    
    def tts_with_queue(self, text: str, timeout: Optional[float] = None) -> bool:
        """带队列的TTS调用"""
        # 尝试直接调用
        if self.tts(text):
            return True
            
        # 加入同步队列
        with self._sync_queue_lock:
            self._sync_queue.append((time.time(), text, timeout))
            self.logger.info(f"TTS被占用，将文本加入同步队列 (队列长度: {len(self._sync_queue)})")
        return True
    
    # 异步TTS接口
    async def tts_stream(self, text_generator: Union[AsyncGenerator[str, None], Generator[str, None, None]]) -> bool:
        """异步处理文本生成器并进行TTS"""
        if not self.start_session():
            return False
            
        try:
            if hasattr(text_generator, '__aiter__'):
                async for text_chunk in text_generator:
                    if self._interrupt_event.is_set():
                        break
                    if text_chunk:
                        self.send_text(text_chunk)
            else:
                for text_chunk in text_generator:
                    if self._interrupt_event.is_set():
                        break
                    if text_chunk:
                        self.send_text(text_chunk)
                        
            await self.async_finish_session()
            return True
        except Exception as e:
            self.logger.error(f"TTS播放异常: {e}")
            self._session_event.clear()
            return False
    
    # 队列管理
    def set_post_play_callback(self, callback: Optional[Callable[[float], Awaitable[None]]]) -> None:
        """设置播放完成回调"""
        self._post_play_callback = callback
    
    async def start_queue(self, maxsize: int = 1) -> None:
        """启动异步播放队列"""
        async with self._async_queue_lock:
            if self._async_queue is None:
                self._async_queue = asyncio.Queue(maxsize=maxsize)
            if self._async_queue_task is None or self._async_queue_task.done():
                self._async_queue_task = asyncio.create_task(self._async_queue_loop())
                self.logger.info("异步播放队列已启动")
    
    async def stop_queue(self) -> None:
        """停止异步播放队列"""
        async with self._async_queue_lock:
            if self._async_queue_task and not self._async_queue_task.done():
                self._async_queue_task.cancel()
            self._async_queue_task = None
            self._async_queue = None
            self.logger.info("异步播放队列已停止")
    
    async def enqueue_text(self, text: str) -> None:
        """将文本加入异步队列"""
        await self.start_queue()
        if self._async_queue is None:
            return
            
        # 队列满时丢弃最旧项
        while self._async_queue.full():
            try:
                self._async_queue.get_nowait()
            except asyncio.QueueEmpty:
                break
                
        await self._async_queue.put((time.time(), text))
    
    async def enqueue_text_stream(self, text_generator: Union[AsyncGenerator[str, None], Generator[str, None, None]]) -> None:
        """将文本生成器加入异步队列"""
        await self.start_queue()
        if self._async_queue is None:
            return
            
        # 如果忙碌，先收集文本
        if self.is_busy() or (self._async_queue.qsize() > 0):
            if hasattr(text_generator, '__aiter__'):
                async def collect_and_enqueue():
                    collected = []
                    try:
                        async for chunk in text_generator:
                            if chunk:
                                collected.append(chunk)
                    except Exception:
                        return
                    full_text = ''.join(collected)
                    await self.enqueue_text(full_text)
                asyncio.create_task(collect_and_enqueue())
            else:
                # 同步生成器转为文本
                full_text = ''.join(chunk for chunk in text_generator if chunk)
                await self.enqueue_text(full_text)
        else:
            # 直接入队
            while self._async_queue.full():
                try:
                    self._async_queue.get_nowait()
                except asyncio.QueueEmpty:
                    break
            await self._async_queue.put((time.time(), text_generator))
    
    async def _async_queue_loop(self) -> None:
        """异步队列消费循环"""
        try:
            while True:
                if self._async_queue is None:
                    await asyncio.sleep(0.05)
                    continue
                    
                timestamp, payload = await self._async_queue.get()
                
                # TTL检查
                if (time.time() - timestamp) > 3.0:
                    self.logger.warning("队列数据过期，丢弃")
                    continue
                    
                # 转换为生成器
                if isinstance(payload, str):
                    async def single_text_gen():
                        if payload:
                            yield payload
                    gen = single_text_gen()
                else:
                    gen = payload
                    
                await self.tts_stream(gen)
                
                # 触发回调
                if self._post_play_callback:
                    try:
                        delay = self.metrics.first_audio_delay or 0
                        await self._post_play_callback(delay)
                    except Exception as e:
                        self.logger.error(f"播放完成回调执行异常: {e}")
        except asyncio.CancelledError:
            return
    
    def _start_sync_consumer(self) -> None:
        """启动同步队列消费者"""
        if self._sync_consumer_thread is None or not self._sync_consumer_thread.is_alive():
            self._sync_consumer_running = True
            self._sync_consumer_thread = threading.Thread(
                target=self._sync_consumer_loop, 
                daemon=True
            )
            self._sync_consumer_thread.start()
            self.logger.info("同步队列消费者已启动")
    
    def _sync_consumer_loop(self) -> None:
        """同步队列消费循环"""
        while self._sync_consumer_running:
            item = None
            
            with self._sync_queue_lock:
                if self._sync_queue:
                    item = self._sync_queue.popleft()
                    
            if item:
                timestamp, text, timeout = item
                timeout_at = None if timeout is None else (timestamp + timeout)
                
                # 等待直到可用或超时
                while True:
                    if timeout_at and time.time() > timeout_at:
                        self.logger.warning(f"同步队列数据超时，丢弃: {text[:20]}...")
                        break
                        
                    if self.tts(text):
                        elapsed = time.time() - timestamp
                        self.logger.info(f"同步队列播放完成 (等待时间: {elapsed:.1f}秒)")
                        break
                        
                    time.sleep(0.1)
            else:
                time.sleep(0.1)
    
    def close(self) -> None:
        """关闭播放器并清理资源"""
        # 停止消费者线程
        self._sync_consumer_running = False
        if self._sync_consumer_thread:
            self._sync_consumer_thread.join(timeout=1.0)
            
        # 关闭音频播放器
        if self.audio_player:
            self.audio_player.close()
            
        self._session_event.clear()
        self.logger.info("CosyVoice播放器已关闭")
    
    def __enter__(self) -> 'CosyVoiceStreamingPlayer':
        """上下文管理器入口"""
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        """上下文管理器出口"""
        self.close()

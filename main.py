import argparse
import os
import sys
import threading
import time
# import subprocess
from typing import Optional, Callable
from service import MiVpmClientSrv
from query_extractor import QueryExtractorService, start_global_query_extractor, stop_global_query_extractor

import asyncio
from typing import Annotated
from dotenv import load_dotenv
from queue import Queue
# from async_agent import create_async_agent
from atomagent import create_async_agent
from cosyvoice_stream_player import CosyVoiceStreamingPlayer
from tools import (
    get_current_time, calculate, get_weather
)

# 加载环境变量
load_dotenv()

base_url = os.getenv("BASE_URL")
model_name = os.getenv("MODEL_NAME")
api_key = os.getenv("API_KEY")
tts_api_key = os.getenv("DASHSCOPE_API_KEY")

class AIChatManager:
    """
    AI聊天管理器类
    
    负责管理MiVpmClient服务和Query提取服务的整个生命周期
    """
    
    def __init__(self, 
                 asr_timeout: int = 5000,
                 status_check_interval: int = 5):
        """
        初始化AI聊天管理器
        
        参数:
        - asr_timeout: ASR超时时间（毫秒）
        - status_check_interval: 状态检查间隔（秒）
        """
        self.asr_timeout = asr_timeout
        self.status_check_interval = status_check_interval
        
        # 创建服务实例
        self.service = MiVpmClientSrv()
        self.query_extractor = QueryExtractorService()
        self.player = CosyVoiceStreamingPlayer(
            api_key=tts_api_key,
            model="cosyvoice-v2",
            voice="longhua_v2",
            volume=20,
            # save_audio=True,
            # audio_file_path="./output"
        )
        # 播放完成回调
        # self.player.set_post_play_callback(self._post_play_callback)
        
        # 创建查询队列和AI处理线程
        self.query_queue = Queue()
        self.ai_thread = None
        self.ai_loop = None
        self.ai_thread_running = False
        self.stop_speak_flag = False

        # 创建异步Agent
        self.agent = create_async_agent(
            name="小爱助手",
            system_prompt="""你是小爱语音助手，有话少聪明的性格。回复之前先确认是否需要调用工具，如果调用了工具要说明，请用简洁、口语化的回答，输出的内容适合语音播报，不要带有括号里的“动作提示”或“语气说明”。""",
            base_url=base_url,
            api_key=api_key,
            model=model_name,
            temperature=0.9,
            verbose=True,  # 减少日志输出以突出流式效果
            max_concurrent_tools=3
        )
        
        # 注册工具函数
        self._register_tools()
        
        # 运行状态
        self._running = False
        self._stop_event = threading.Event()
        
        # 异步事件循环
        self._loop = None
        self._loop_thread = None
        
        # 回调函数列表
        self._query_callbacks = []
        
        # 设置默认的query处理回调
        self.query_extractor.add_callback(self._on_query_received)
    
    def _start_async_loop(self):
        """在单独的线程中启动异步事件循环"""
        def run_loop():
            self._loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self._loop)
            self._loop.run_forever()
        
        self._loop_thread = threading.Thread(target=run_loop, daemon=True)
        self._loop_thread.start()
    
    def _start_ai_thread(self):
        """启动AI处理线程"""
        def ai_thread_worker():
            # 创建新的异步事件循环
            self.ai_loop = asyncio.new_event_loop()
            asyncio.set_event_loop(self.ai_loop)
            
            self.ai_thread_running = True
            print("🤖 AI处理线程已启动")
            
            try:
                # 运行AI处理循环
                self.ai_loop.run_until_complete(self._ai_processing_loop())
            except Exception as e:
                print(f"AI处理线程出错: {e}")
            finally:
                self.ai_thread_running = False
                print("🤖 AI处理线程已停止")
        
        self.ai_thread = threading.Thread(target=ai_thread_worker, daemon=True)
        self.ai_thread.start()
    
    async def _ai_processing_loop(self):
        """AI处理循环，从队列中获取查询并处理"""
        while self.ai_thread_running:
            try:
                # 非阻塞地检查队列
                if not self.query_queue.empty():
                    query = self.query_queue.get_nowait()
                    # print(f"🧠 开始处理查询: {query}")
                    
                    # 处理AI对话
                    await self._process_ai_chat(query)
                    
                    # 标记任务完成
                    self.query_queue.task_done()
                else:
                    # 队列为空，短暂休眠
                    await asyncio.sleep(0.1)
                    
            except Exception as e:
                print(f"AI处理循环出错: {e}")
                await asyncio.sleep(1)  # 出错后等待1秒再继续
    
    async def _process_ai_chat(self, query: str):
        """处理单个AI对话查询"""
        try:
            print(f"🤖 开始AI对话处理: {query}")
            
            # 使用流式输出，同时打印和送入TTS播放器
            llm_text_generator = self.agent.chat_stream(query)
            
            # 创建一个包装器来同时处理打印和TTS
            async def text_stream_with_print():
                print("助手: ", end="")
                async for chunk in llm_text_generator:
                    print(chunk, end="", flush=True)
                    yield chunk
                print()  # 换行
            
            await self.player.enqueue_text_stream(text_stream_with_print())
            # 等待播放完成
            # while not self.player.is_finish():
            #     await asyncio.sleep(0.1)
            
            
        except Exception as e:
            print(f"❌ AI对话处理失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 等待事件循环启动
        time.sleep(0.1)
    
    def _register_tools(self):
        """注册所有工具函数"""
        # 时间相关
        self.agent.register_tool(get_current_time, name="获取当前时间")
     
        # 计算和娱乐
        self.agent.register_tool(calculate, name="计算器")
        
        # 实用功能
        # self.agent.register_tool(get_weather, name="查询天气")
        
        # 音量控制
        self.agent.register_tool(self.player.volume_change, name="调整音量")
        self.agent.register_tool(self.player.interrupt, name="打断播放")
        
        print(f"✅ 已注册 {len(self.agent._tools)} 个工具函数")

    async def _post_play_callback(self, delay: float):
        """播放完成后的回调"""
        print(f"播放完成，延迟: {delay:.1f}ms")
        # if self.stop_speak_flag:
        #     self.stop_speak_flag = False
        #     return
        try:
            if self.service.is_running():
                self.service.send_command("wakeup")
        except Exception as e:
            print(f"发送wakeup命令失败: {e}")

    # def stop_speak(self):
    #     """打断当前语音输出，要求停止说话时调用"""
    #     self.stop_speak_flag = True
    #     self.player.interrupt()
    
    def add_query_callback(self, callback: Callable[[str], None]):
        """
        添加query处理回调函数
        
        参数:
        - callback: 当收到新query时调用的回调函数
        """
        self._query_callbacks.append(callback)
    
    def remove_query_callback(self, callback: Callable[[str], None]):
        """移除query处理回调函数"""
        if callback in self._query_callbacks:
            self._query_callbacks.remove(callback)
    
    def _on_query_received(self, query: str):
        """内部query处理回调"""
        # print(f"🎤 收到新的语音识别结果: {query}")
        
        # 每次识别后自动触发下一次唤醒, 改为播放完成在唤醒避免回声问题
        try:
            if self.service.is_running():
                self.service.send_command("wakeup")
        except Exception as e:
            print(f"发送wakeup命令失败: {e}")

        # 将查询放入队列供AI处理线程处理
        try:
            self.query_queue.put_nowait(query)
            # print(f"📝 查询已加入处理队列，当前队列长度: {self.query_queue.qsize()}")
        except Exception as e:
            print(f"❌ 加入查询队列失败: {e}")
        
        # 调用用户注册的回调函数
        for callback in self._query_callbacks:
            try:
                callback(query)
            except Exception as e:
                print(f"用户回调函数执行出错: {e}")
    
    def start(self):
        """启动所有服务"""
        if self._running:
            print("AIChatManager 已经在运行")
            return
        
        # 启动异步事件循环
        self._start_async_loop()
        
        # 启动AI处理线程
        self._start_ai_thread()
        
        try:
            # 启动MiVpmClient服务
            self.service.start()
            # print("MiVpmClient 已启动。")
            
            # 启动Query提取服务
            self.query_extractor.start()
            # print("Query提取服务已启动。")
            
            # 配置ASR超时时间
            self.service.send_command(f"asrtimeout,{self.asr_timeout}")
            print(f"ASR超时时间设置为: {self.asr_timeout}ms")
            
            self._running = True
            self._stop_event.clear()
            
            print("\n=== 大模型对话服务已启动 ===")
            print("\n按 Ctrl+C 停止所有服务\n")
            
        except Exception as e:
            print(f"启动服务时发生错误: {e}")
            self.stop()
            raise
    
    def stop(self):
        """停止所有服务"""
        if not self._running:
            return
        
        print("正在停止所有服务...")
        self._running = False
        self._stop_event.set()

        # 停止AI处理线程
        self.ai_thread_running = False
        if self.ai_loop and not self.ai_loop.is_closed():
            self.ai_loop.call_soon_threadsafe(self.ai_loop.stop)
        if self.ai_thread and self.ai_thread.is_alive():
            self.ai_thread.join(timeout=3)
            print("AI处理线程已停止")
        
        # 关闭TTS播放器
        try:
            self.player.close()
            print("TTS播放器已关闭")
        except Exception as e:
            print(f"关闭TTS播放器时出错: {e}")
        
        # 关闭异步agent
        if self._loop and not self._loop.is_closed():
            asyncio.run_coroutine_threadsafe(self.agent.close(), self._loop)
        
        # 停止异步事件循环
        if self._loop and not self._loop.is_closed():
            self._loop.call_soon_threadsafe(self._loop.stop)
            if self._loop_thread and self._loop_thread.is_alive():
                self._loop_thread.join(timeout=2)
        
        # 停止Query提取服务
        try:
            self.query_extractor.stop()
        except Exception as e:
            print(f"停止Query提取服务时出错: {e}")
        
        # 停止MiVpmClient服务
        try:
            self.service.stop()
            print("MiVpmClient服务已停止")
        except Exception as e:
            print(f"停止MiVpmClient服务时出错: {e}")
        
        print("所有服务已停止。")
    
    def is_running(self) -> bool:
        """检查管理器是否正在运行"""
        return (self._running and 
                self.service.is_running() and 
                self.query_extractor.is_running())
    
    def run(self):
        """运行主循环（阻塞）"""
        if not self._running:
            self.start()
        
        try:
            last_check_time = time.time()
            
            while not self._stop_event.is_set():
                # 定期状态检查
                # current_time = time.time()
                # if current_time - last_check_time >= self.status_check_interval:
                #     self._status_check()
                #     last_check_time = current_time
                
                # 检查服务状态
                if not self.service.is_running():
                    print("⚠️  MiVpmClient 进程已退出。")
                    break
                    
                if not self.query_extractor.is_running():
                    print("⚠️  Query提取服务已停止。")
                    break
                
                time.sleep(0.5)
                
        except KeyboardInterrupt:
            print("\n收到中断信号，正在停止服务...")
        finally:
            self.stop()
    
    def _status_check(self):
        """定期状态检查"""
        latest_query = self.query_extractor.get_latest_query()
        queue_size = self.query_extractor.get_queue_size()
        
        if latest_query:
            print(f"📊 状态检查 - 最新query: '{latest_query}', 队列大小: {queue_size}")
        else:
            print(f"📊 状态检查 - 暂无query数据, 队列大小: {queue_size}")
    
    def send_command(self, command: str):
        """向MiVpmClient发送命令"""
        if self.service.is_running():
            self.service.send_command(command)
        else:
            print("MiVpmClient服务未运行，无法发送命令")
    
    def get_latest_query(self) -> Optional[str]:
        """获取最新的query"""
        return self.query_extractor.get_latest_query()
    
    def get_query_queue_size(self) -> int:
        """获取query队列大小"""
        return self.query_extractor.get_queue_size()


def main():
    """主函数 - 使用AIChatManager类"""
    # 创建管理器实例
    chat_manager = AIChatManager()
    
    # 添加自定义的query处理回调（可选）
    def custom_query_handler(query: str):
        """自定义query处理逻辑"""
        # 在这里可以添加更多的处理逻辑，比如：
        # - 保存到数据库
        # - 触发其他服务
        # - 发送通知等
        pass
    
    chat_manager.add_query_callback(custom_query_handler)
    
    # 运行管理器
    chat_manager.run()


def demo_query_usage():
    """演示如何使用Query提取服务的各种功能"""
    print("=== Query提取服务使用演示 ===")
    
    # 使用全局单例
    extractor = start_global_query_extractor()
    
    def demo_callback(query: str):
        print(f"Demo回调收到: {query}")
    
    extractor.add_callback(demo_callback)
    
    try:
        print("演示运行中，等待query数据...")
        
        for i in range(30):  # 运行30秒
            time.sleep(1)
            
            # 演示不同的获取方式
            if i % 5 == 0:
                # 获取最新query
                latest = extractor.get_latest_query()
                print(f"[{i}s] 最新query: {latest}")
                
            if i % 10 == 0:
                # 获取所有待处理的query
                all_queries = extractor.get_all_queries()
                if all_queries:
                    print(f"[{i}s] 获取到 {len(all_queries)} 个待处理query: {all_queries}")
                    
    except KeyboardInterrupt:
        print("\n演示被中断")
    finally:
        stop_global_query_extractor()
        print("演示结束")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AI Chat 主程序")
    parser.add_argument("--demo", action="store_true", help="运行Query提取服务演示")
    parser.add_argument("--asr-timeout", type=int, default=5000, help="ASR超时时间（毫秒）")
    parser.add_argument("--status-interval", type=int, default=5, help="状态检查间隔（秒）")
    
    args = parser.parse_args()
    
    if args.demo:
        demo_query_usage()
    else:
        # 创建管理器实例（使用命令行参数）
        chat_manager = AIChatManager(
            asr_timeout=args.asr_timeout,
            status_check_interval=args.status_interval
        )
        
        # 添加自定义的query处理回调（可选）
        def custom_query_handler(query: str):
            """自定义query处理逻辑"""
            # 在这里可以添加更多的处理逻辑，比如：
            # - 保存到数据库
            # - 触发其他服务
            # - 发送通知等
            pass
        
        chat_manager.add_query_callback(custom_query_handler)
        
        # 运行管理器
        chat_manager.run()


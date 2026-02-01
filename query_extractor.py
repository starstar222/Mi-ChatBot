import os
import time
import threading
import queue
from typing import Optional, Callable
import io
import json


def follow(thefile: io.TextIOWrapper, sleep_sec: float = 0.1):
    """
    持续跟随文件末尾，按行返回新增内容（类似 `tail -f`）。

    参数:
    - thefile: 已打开的文本文件对象（以只读模式打开）。
    - sleep_sec: 无新内容时的睡眠时间，单位秒。
    """
    # 跳到文件末尾
    thefile.seek(0, os.SEEK_END)

    while True:
        line = thefile.readline()
        if not line:
            # 没有新内容，稍等后继续
            time.sleep(sleep_sec)
            continue
        yield line


def parse_json_from_line(raw: str):
    """
    从日志行中提取并解析 JSON。

    - 优先提取第一个 "{" 到最后一个 "}" 之间的子串作为 JSON。
    - 若无法定位子串，则尝试把整行当作 JSON 解析。
    - 解析失败返回 None。
    """
    try:
        start = raw.find("{")
        end = raw.rfind("}")
        if start != -1 and end != -1 and end > start:
            json_str = raw[start:end + 1]
            return json.loads(json_str)
        # 否则尝试整行解析
        return json.loads(raw)
    except Exception:
        return None


def extract_query(parsed) -> str | None:
    """
    从解析后的对象中提取 query 字段：
    - 优先尝试顶层 parsed["query"]
    - 其次尝试 parsed["response"]["queries"][0]["query"]
    返回字符串或 None。
    """
    try:
        if isinstance(parsed, dict):
            # 顶层 query
            if "query" in parsed and isinstance(parsed["query"], (str, int, float)):
                return str(parsed["query"]) if not isinstance(parsed["query"], str) else parsed["query"]

            # 嵌套 response.queries[0].query
            resp = parsed.get("response")
            if isinstance(resp, dict):
                queries = resp.get("queries")
                if isinstance(queries, list) and len(queries) > 0 and isinstance(queries[0], dict):
                    q = queries[0].get("query")
                    if isinstance(q, (str, int, float)):
                        return str(q) if not isinstance(q, str) else q
    except Exception:
        return None
    return None

class QueryExtractorService:
    """
    基于monitor_log函数实现的实时query字段提取服务。
    在后台持续监控日志文件，提取query字段并提供实时访问接口。
    """
    
    def __init__(self, 
                 file_path: str = "/sdcard/vpm/vpm_debug.log", 
                 keyword: str = "rejectionRespNumReceived\":1}}",
                 max_queue_size: int = 100):
        """
        初始化Query提取服务
        
        参数:
        - file_path: 要监控的日志文件路径
        - keyword: 需要匹配的关键字子串
        - max_queue_size: query队列的最大长度
        """
        self.file_path = file_path
        self.keyword = keyword
        self.max_queue_size = max_queue_size
        
        # 线程安全的query队列
        self.query_queue = queue.Queue(maxsize=max_queue_size)
        
        # 最新的query缓存
        self._latest_query = None
        self._latest_query_lock = threading.Lock()
        
        # 监控线程相关
        self._monitor_thread = None
        self._stop_event = threading.Event()
        self._running = False
        
        # 回调函数列表
        self._callbacks = []
        
    def add_callback(self, callback: Callable[[str], None]):
        """
        添加query更新回调函数
        
        参数:
        - callback: 当有新query时调用的回调函数，接收query字符串参数
        """
        self._callbacks.append(callback)
        
    def remove_callback(self, callback: Callable[[str], None]):
        """移除回调函数"""
        if callback in self._callbacks:
            self._callbacks.remove(callback)
    
    def _notify_callbacks(self, query: str):
        """通知所有回调函数"""
        for callback in self._callbacks:
            try:
                callback(query)
            except Exception as e:
                print(f"回调函数执行出错: {e}")
    
    def _monitor_log_worker(self):
        """
        后台监控日志文件的工作线程
        """
        # print(f"开始监控日志文件: {self.file_path}")
        # print(f"匹配关键字: {self.keyword}")
        
        while not self._stop_event.is_set():
            try:
                # 检查文件是否存在
                if not os.path.exists(self.file_path):
                    print(f"等待日志文件创建: {self.file_path}")
                    time.sleep(1)
                    continue
                # 如果文件存在，先清空里面内容
                try:
                    with open(self.file_path, "w", encoding="utf-8") as clear_file:
                        clear_file.write("")  # 清空文件内容
                    # print(f"已清空日志文件: {self.file_path}")
                except Exception as e:
                    print(f"清空文件失败: {e}")
                
                
                # 以 UTF-8 打开，忽略无法解码的字符
                with open(self.file_path, "r", encoding="utf-8", errors="ignore") as f:
                    for line in follow(f, sleep_sec=0.1):
                        if self._stop_event.is_set():
                            break
                            
                        if self.keyword in line:
                            # 解析JSON并提取query字段
                            raw = line.rstrip("\n")
                            parsed = parse_json_from_line(raw)
                            query = extract_query(parsed)
                            
                            if query is not None:
                                # 更新最新query
                                with self._latest_query_lock:
                                    self._latest_query = query
                                
                                # 添加到队列（如果队列满了，移除最旧的）
                                try:
                                    self.query_queue.put_nowait(query)
                                except queue.Full:
                                    try:
                                        # 移除最旧的query
                                        self.query_queue.get_nowait()
                                        self.query_queue.put_nowait(query)
                                    except queue.Empty:
                                        pass
                                
                                # 通知回调函数
                                self._notify_callbacks(query)
                                
                                # print(f"[QueryExtractor] 提取到query: {query}")
                            else:
                                print(f"[QueryExtractor] 匹配到关键字但未找到query字段")
                                
            except FileNotFoundError:
                if not self._stop_event.is_set():
                    print(f"日志文件不存在，等待创建: {self.file_path}")
                    time.sleep(1)
            except Exception as e:
                if not self._stop_event.is_set():
                    print(f"[QueryExtractor] 监控过程中发生错误: {e}")
                    time.sleep(1)
    
    def start(self):
        """启动query提取服务"""
        if self._running:
            print("QueryExtractor服务已经在运行")
            return
            
        self._stop_event.clear()
        self._running = True
        
        # 启动监控线程
        self._monitor_thread = threading.Thread(
            target=self._monitor_log_worker, 
            daemon=True,
            name="QueryExtractorMonitor"
        )
        self._monitor_thread.start()
        
        print("QueryExtractor服务已启动")
    
    def stop(self):
        """停止query提取服务"""
        if not self._running:
            return
            
        self._stop_event.set()
        self._running = False
        
        if self._monitor_thread and self._monitor_thread.is_alive():
            self._monitor_thread.join(timeout=2.0)
            
        print("QueryExtractor服务已停止")
    
    def is_running(self) -> bool:
        """检查服务是否正在运行"""
        return self._running and not self._stop_event.is_set()
    
    def get_latest_query(self) -> Optional[str]:
        """
        获取最新的query字段
        
        返回:
        - 最新的query字符串，如果没有则返回None
        """
        with self._latest_query_lock:
            return self._latest_query
    
    def get_query_nowait(self) -> Optional[str]:
        """
        非阻塞方式获取一个query（从队列中取出）
        
        返回:
        - query字符串，如果队列为空则返回None
        """
        try:
            return self.query_queue.get_nowait()
        except queue.Empty:
            return None
    
    def get_query_timeout(self, timeout: float = 1.0) -> Optional[str]:
        """
        带超时的方式获取一个query
        
        参数:
        - timeout: 超时时间（秒）
        
        返回:
        - query字符串，如果超时则返回None
        """
        try:
            return self.query_queue.get(timeout=timeout)
        except queue.Empty:
            return None
    
    def get_all_queries(self) -> list[str]:
        """
        获取队列中的所有query（清空队列）
        
        返回:
        - query字符串列表
        """
        queries = []
        while True:
            try:
                query = self.query_queue.get_nowait()
                queries.append(query)
            except queue.Empty:
                break
        return queries
    
    def get_queue_size(self) -> int:
        """获取当前队列中query的数量"""
        return self.query_queue.qsize()
    
    def clear_queue(self):
        """清空query队列"""
        while True:
            try:
                self.query_queue.get_nowait()
            except queue.Empty:
                break


# 全局单例实例
_global_query_extractor = None


def get_global_query_extractor() -> QueryExtractorService:
    """
    获取全局的QueryExtractor实例（单例模式）
    """
    global _global_query_extractor
    if _global_query_extractor is None:
        _global_query_extractor = QueryExtractorService()
    return _global_query_extractor


def start_global_query_extractor():
    """启动全局QueryExtractor服务"""
    extractor = get_global_query_extractor()
    extractor.start()
    return extractor


def stop_global_query_extractor():
    """停止全局QueryExtractor服务"""
    global _global_query_extractor
    if _global_query_extractor:
        _global_query_extractor.stop()


if __name__ == "__main__":
    # 测试代码
    def on_query_received(query: str):
        print(f"收到新query: {query}")
    
    # 创建服务实例
    extractor = QueryExtractorService()
    extractor.add_callback(on_query_received)
    
    try:
        # 启动服务
        extractor.start()
        
        print("QueryExtractor测试运行中，按Ctrl+C停止...")
        
        # 定期检查最新query
        while True:
            time.sleep(2)
            latest = extractor.get_latest_query()
            queue_size = extractor.get_queue_size()
            print(f"最新query: {latest}, 队列大小: {queue_size}")
            
    except KeyboardInterrupt:
        print("\n正在停止服务...")
    finally:
        extractor.stop()
        print("测试结束")

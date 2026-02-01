import argparse
import os
import sys
import threading
import time
import subprocess
from typing import Optional, TextIO


class MiVpmClientSrv:
    """
    管理 MiVpmClient 进程：启动、发送命令、停止，并异步读取 stdout/stderr。
    """

    def __init__(self, workdir: Optional[str] = None, logfile: Optional[str] = None):
        self.MI_VPM_BIN = "/system/bin/MiVpmClient"
        self.workdir = workdir
        self.logfile = logfile
        self.proc: Optional[subprocess.Popen] = None
        self._stdout_thread: Optional[threading.Thread] = None
        self._stderr_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._log_fp: Optional[TextIO] = None
        self._wakeup_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        if not os.path.exists(self.MI_VPM_BIN) or not os.access(self.MI_VPM_BIN, os.X_OK):
            raise FileNotFoundError(f"可执行文件不可用: {self.MI_VPM_BIN}")

        if self.logfile:
            os.makedirs(os.path.dirname(os.path.abspath(self.logfile)), exist_ok=True)
            self._log_fp = open(self.logfile, "a", encoding="utf-8", buffering=1)

        # text=True 开启文本模式；bufsize=1 行缓冲；使用环境变量继承
        cmd = ["sudo", self.MI_VPM_BIN]
        self.proc = subprocess.Popen(
            cmd,
            cwd=self.workdir or None,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1,
            universal_newlines=True,
        )

        self._stop_event.clear()
        # 启动读取线程
        self._stdout_thread = threading.Thread(target=self._pump_stream, args=(self.proc.stdout, "STDOUT"), daemon=True)
        self._stderr_thread = threading.Thread(target=self._pump_stream, args=(self.proc.stderr, "STDERR"), daemon=True)
        self._stdout_thread.start()
        self._stderr_thread.start()

        # self.send_command("wakeup")
        # 周期性发送 wakeup
        self._wakeup_thread = threading.Thread(target=self._wakeup_loop, daemon=True)
        # self._wakeup_thread.start()

    def _pump_stream(self, stream: Optional[TextIO], tag: str) -> None:
        if stream is None:
            return
        for line in iter(stream.readline, ""):
            if line == "" or self._stop_event.is_set():
                break
            text = line.rstrip("\n")
            msg = f"[{tag}] {text}"
            # 不打印cmd回显
            if tag != "STDERR":
                print(msg, flush=True)
            if self._log_fp:
                try:
                    self._log_fp.write(msg + "\n")
                except Exception:
                    pass
        # 读取结束
        try:
            stream.close()
        except Exception:
            pass

    def _wakeup_loop(self) -> None:
        """每 5 秒向 MiVpmClient 发送一次 wakeup 命令，直到停止。"""
        try:
            while not self._stop_event.is_set():
                if self.is_running():
                    try:
                        self.send_command("wakeup")
                    except Exception:
                        pass
                # 每 5 秒发送一次
                for _ in range(20):
                    if self._stop_event.is_set():
                        break
                    time.sleep(0.1)
        except Exception:
            pass

    def is_running(self) -> bool:
        return self.proc is not None and self.proc.poll() is None

    def send_command(self, cmd: str) -> None:
        if not self.is_running() or self.proc is None or self.proc.stdin is None:
            raise RuntimeError("进程未启动或 stdin 不可用")
        # 确保每条命令以换行结束
        self.proc.stdin.write(cmd.strip() + "\n")
        self.proc.stdin.flush()

    def stop(self, graceful_timeout: float = 3.0) -> None:
        # 尝试优雅退出：发送 exit
        if self.is_running():
            try:
                self.send_command("exit")
            except Exception:
                pass

        # 等待优雅退出
        start = time.time()
        while self.is_running() and (time.time() - start) < graceful_timeout:
            time.sleep(0.1)

        # 超时则终止
        if self.is_running() and self.proc is not None:
            try:
                self.proc.terminate()
            except Exception:
                pass

        # 再次等待少许时间
        if self.is_running():
            try:
                self.proc.kill()
            except Exception:
                pass

        # 通知线程结束
        self._stop_event.set()
        if self._stdout_thread and self._stdout_thread.is_alive():
            self._stdout_thread.join(timeout=1.0)
        if self._stderr_thread and self._stderr_thread.is_alive():
            self._stderr_thread.join(timeout=1.0)
        if self._wakeup_thread and self._wakeup_thread.is_alive():
            self._wakeup_thread.join(timeout=1.0)

        # 关闭日志
        if self._log_fp:
            try:
                self._log_fp.close()
            except Exception:
                pass
            self._log_fp = None


def run_repl(service: MiVpmClientSrv):
    print("进入 REPL 模式，输入命令后回车发送到 MiVpmClient。Ctrl+C 或输入 'exit' 退出。")
    print("可用命令示例: start|stop|wakeup|unwakeup|disvad|envad|diswuw|enwuw|pause|resume|")
    print("以及: asrtimeout,ms|vadtimeout,ms|playmusic,file|stopmusic|envoip|disvoip|log|exit")
    try:
        while True:
            line = input(">> ").strip()
            if not line:
                continue
            if line.lower() in {"exit", "quit"}:
                # 将 exit 同步传递给后端，便于优雅退出
                try:
                    service.send_command("exit")
                except Exception:
                    pass
                break
            service.send_command(line)
    except KeyboardInterrupt:
        print("\nREPL 结束。")


def main():
    parser = argparse.ArgumentParser(description="MiVpmClient 后台服务管理器")
    parser.add_argument("--workdir", default=None, help="作为工作目录启动（可选）")
    parser.add_argument("--logfile", default=None, help="将输出同时写入该日志文件（可选）")
    parser.add_argument("--cmd", action="append", default=None, help="启动后立即发送的命令（可多次）")
    parser.add_argument("--repl", action="store_true", help="进入交互式 REPL，向服务发送命令")

    args = parser.parse_args()

    service = MiVpmClientSrv(workdir=args.workdir, logfile=args.logfile)
    try:
        service.start()
        print("MiVpmClient 已启动。")

        # 启动后立即发送的命令（可多条）
        if args.cmd:
            for c in args.cmd:
                service.send_command(c)

        # 交互式 REPL
        if args.repl:
            run_repl(service)
        else:
            # 若未进入 REPL，则保持前台驻留，直到 Ctrl+C
            print("按 Ctrl+C 停止服务，或使用 --repl 进入交互模式。")
            while True:
                if not service.is_running():
                    print("MiVpmClient 进程已退出。")
                    break
                time.sleep(0.5)
    except KeyboardInterrupt:
        print("\n收到中断，准备停止服务...")
    finally:
        service.stop()
        print("服务已停止。")


if __name__ == "__main__":
    # 示例：
    # python3 ai_chat/main.py --repl
    # python3 ai_chat/main.py --cmd start --cmd log
    main()


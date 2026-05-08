"""
螺栓拧紧上位机系统 — 应用日志系统
双输出：文件（RotatingFileHandler）+ 内存环形缓冲（供 UI 消费）
"""

import logging
import logging.handlers
import os
from collections import deque
from datetime import datetime
from typing import Deque, Optional


_LOG_RECORD_FIELDS = [
    "created", "levelname", "levelno", "message", "name", "pathname",
    "lineno", "funcName", "threadName", "process",
]

MAX_BUFFER = 2000


class LogEntry:
    """单条日志的纯数据对象，方便 UI 层消费。"""

    __slots__ = _LOG_RECORD_FIELDS + ["created_dt"]

    def __init__(self, record: logging.LogRecord):
        for f in _LOG_RECORD_FIELDS:
            setattr(self, f, getattr(record, f, None))
        self.created_dt = datetime.fromtimestamp(record.created)

    @property
    def timestamp_str(self) -> str:
        return self.created_dt.strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]

    @property
    def brief(self) -> str:
        """返回单行摘要，用于列表展示。"""
        return f"{self.timestamp_str} [{self.levelname}] {self.message}"

    def full(self) -> str:
        """返回带调用位置的详情，用于展开查看。"""
        return (
            f"{self.timestamp_str} [{self.levelname}] {self.message}\n"
            f"  {self.pathname}:{self.lineno}  {self.funcName}  "
            f"thread={self.threadName}  pid={self.process}"
        )


class _MemoryHandler(logging.Handler):
    """将日志写入内存 deque，并触发可选的用户回调。"""

    def __init__(self, maxlen: int = MAX_BUFFER):
        super().__init__()
        self.buffer: Deque[LogEntry] = deque(maxlen=maxlen)
        self._callback = None  # callable(LogEntry) | None

    def set_callback(self, cb):
        self._callback = cb

    def emit(self, record: logging.LogRecord):
        entry = LogEntry(record)
        self.buffer.append(entry)
        if self._callback is not None:
            try:
                self._callback(entry)
            except Exception:
                pass

    def recent(self, count: int = 100, *, levelno: Optional[int] = None):
        level = logging.NOTSET if levelno is None else levelno
        result = []
        for e in self.buffer:
            if e.levelno >= level:
                result.append(e)
        return result[-count:]

    def clear(self):
        self.buffer.clear()


class AppLogger:
    """应用日志单例。

    - 文件：logs/ 目录下按日期滚动（RotatingFileHandler）
    - 内存：deque 环形缓冲，最大 MAX_BUFFER 条
    - 回调：可注册 callback(LogEntry)，用于桥接 Qt signal
    """

    def __init__(self, name: str = "bolt"):
        self._logger = logging.getLogger(name)
        self._logger.setLevel(logging.DEBUG)
        self._logger.propagate = False
        self._memory_handler = _MemoryHandler()
        self._memory_handler.setLevel(logging.DEBUG)
        self._logger.addHandler(self._memory_handler)  # 始终生效
        self._file_handler: Optional[logging.handlers.RotatingFileHandler] = None
        self._started = False

    # ---- public -------------------------------------------------------------

    def start(self, log_dir: str = "logs", *,
              max_bytes: int = 2 * 1024 * 1024,
              backup_count: int = 5,
              level: int = logging.DEBUG):
        """启用文件日志。调用前仅内存缓冲生效。"""
        if self._started:
            return
        os.makedirs(log_dir, exist_ok=True)
        path = os.path.join(log_dir, "app.log")
        fh = logging.handlers.RotatingFileHandler(
            path, maxBytes=max_bytes, backupCount=backup_count,
            encoding="utf-8",
        )
        fh.setLevel(level)
        fh.setFormatter(logging.Formatter(
            "%(asctime)s.%(msecs)03d | %(levelname)-8s | "
            "%(threadName)-12s | %(name)s:%(funcName)s:%(lineno)d | %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        ))
        self._logger.addHandler(fh)
        self._file_handler = fh
        self._started = True

    def set_level(self, level: int):
        self._logger.setLevel(level)
        self._memory_handler.setLevel(level)
        if self._file_handler:
            self._file_handler.setLevel(level)

    def set_callback(self, cb):
        """注册回调 cb(LogEntry)，用于 UI 实时展示。"""
        self._memory_handler.set_callback(cb)

    # ---- buffer access ------------------------------------------------------

    @property
    def buffer(self) -> Deque[LogEntry]:
        return self._memory_handler.buffer

    def recent(self, count: int = 100, *, levelno: Optional[int] = None):
        return self._memory_handler.recent(count, levelno=levelno)

    # ---- logging shortcuts --------------------------------------------------

    def debug(self, msg, *args):
        self._logger.debug(msg, *args)

    def info(self, msg, *args):
        self._logger.info(msg, *args)

    def warning(self, msg, *args):
        self._logger.warning(msg, *args)

    def error(self, msg, *args):
        self._logger.error(msg, *args)

    def critical(self, msg, *args):
        self._logger.critical(msg, *args)

    def exception(self, msg, *args):
        self._logger.exception(msg, *args)


# 模块级单例 — 项目内统一通过 app_logger 引用
app_logger = AppLogger()

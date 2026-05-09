"""状态指示灯 — 圆形色点，用于指示连接/运行/故障状态。"""

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QLabel

from src.ui.styles import STATUS_COLORS, TEXT_SECONDARY


class StatusIndicator(QLabel):
    """圆形状态指示灯。

    Usage:
        ind = StatusIndicator("online")        # 绿色
        ind.set_status("error")               # 红色
    """

    _STATES = ("online", "offline", "error", "warning", "running", "idle")

    def __init__(self, status: str = "offline", size: int = 10, parent=None):
        super().__init__(parent)
        self._size = size
        self._status = ""
        self.setFixedSize(size, size)
        self.set_status(status)

    def set_status(self, status: str):
        if status == self._status:
            return
        self._status = status
        color = STATUS_COLORS.get(status, TEXT_SECONDARY)
        self.setStyleSheet(
            f"background-color: {color};"
            f"border-radius: {self._size // 2}px;"
            f"min-width: {self._size}px;"
            f"min-height: {self._size}px;"
        )

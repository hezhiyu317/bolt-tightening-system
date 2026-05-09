"""全局应用状态 — 唯一真源，pyqtSignal 变化通知。

单例，Service 层写入，UI 层订阅。写操作在主线程（通过 signal slot），
读操作任意线程安全（CPython GIL 保护简单属性读取）。
"""

from collections import deque
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Deque, Dict, List, Optional

from PyQt5.QtCore import QObject, pyqtSignal


@dataclass
class MotorState:
    """单电机运行时状态。每个轮询周期更新。"""

    name: str
    is_powered: bool = False
    is_homed: bool = False
    is_moving: bool = False
    is_alarmed: bool = False
    position: float = 0.0
    velocity: float = 0.0
    torque: float = 0.0
    status_word: int = 0
    error_word: int = 0


@dataclass
class PclResult:
    """一次点云处理流水线的结果。"""

    success: bool = False
    center_x: float = 0.0
    center_y: float = 0.0
    center_z: float = 0.0
    radius: float = 0.0
    cluster_count: int = 0
    error_message: str = ""


class AppState(QObject):
    """全局应用状态单例。

    Usage:
        from src.models.app_state import app_state

        # UI 订阅
        app_state.plc_online_changed.connect(self.on_plc_changed)

        # Service 更新
        app_state.plc_online = True
        app_state.update_motor("Z_motor", is_powered=True, position=12.5)
    """

    # ---- signals ----
    plc_online_changed = pyqtSignal(bool)
    camera_online_changed = pyqtSignal(bool)
    user_changed = pyqtSignal(str, str)          # username, role
    operation_mode_changed = pyqtSignal(str)
    estop_changed = pyqtSignal(bool)
    motor_state_updated = pyqtSignal(str)         # motor_name
    motor_position_updated = pyqtSignal(str, float)  # motor_name, position
    gantry_geared_changed = pyqtSignal(str, bool)    # gantry("small"/"big"), is_geared
    alarm_added = pyqtSignal(str, str)            # level, message
    alarms_cleared = pyqtSignal()
    pcl_status_changed = pyqtSignal(str)          # idle/processing/done/error
    relay_state_changed = pyqtSignal(str, bool)   # relay_name, state

    OPERATION_MODES = ("stopped", "manual", "auto", "homing", "calibration", "estop")
    ALARM_LEVELS = ("info", "warning", "error", "critical")

    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self._plc_online = False
        self._camera_online = False
        self._username = ""
        self._role = ""
        self._operation_mode = "stopped"
        self._estop = False
        self._motor_states: Dict[str, MotorState] = {}
        self._small_gantry_geared = False
        self._big_gantry_geared = False
        self._alarms: Deque[Dict[str, str]] = deque(maxlen=200)
        self._relay_states: Dict[str, bool] = {}
        self._sensor_states: Dict[str, bool] = {}
        self._pcl_status = "idle"
        self._last_pcl_result: Optional[PclResult] = None

    # ---- motor init ----------------------------------------------------------

    def init_motors(self, motor_names: List[str]):
        """用配置中的电机名填充状态字典。启动时调用一次。"""
        for name in motor_names:
            if name not in self._motor_states:
                self._motor_states[name] = MotorState(name=name)

    # ---- connection -----------------------------------------------------------

    @property
    def plc_online(self) -> bool:
        return self._plc_online

    @plc_online.setter
    def plc_online(self, value: bool):
        if self._plc_online != value:
            self._plc_online = value
            self.plc_online_changed.emit(value)

    @property
    def camera_online(self) -> bool:
        return self._camera_online

    @camera_online.setter
    def camera_online(self, value: bool):
        if self._camera_online != value:
            self._camera_online = value
            self.camera_online_changed.emit(value)

    # ---- user -----------------------------------------------------------------

    @property
    def username(self) -> str:
        return self._username

    @property
    def role(self) -> str:
        return self._role

    @property
    def is_developer(self) -> bool:
        return self._role == "developer"

    @property
    def is_logged_in(self) -> bool:
        return bool(self._username)

    def login(self, username: str, role: str):
        self._username = username
        self._role = role
        self.user_changed.emit(username, role)

    def logout(self):
        self._username = ""
        self._role = ""
        self.user_changed.emit("", "")

    # ---- operation mode -------------------------------------------------------

    @property
    def operation_mode(self) -> str:
        return self._operation_mode

    @operation_mode.setter
    def operation_mode(self, value: str):
        if value not in self.OPERATION_MODES:
            raise ValueError(f"无效操作模式: {value}，有效值: {self.OPERATION_MODES}")
        if self._operation_mode != value:
            self._operation_mode = value
            self.operation_mode_changed.emit(value)

    # ---- estop ----------------------------------------------------------------

    @property
    def is_estop(self) -> bool:
        return self._estop

    @is_estop.setter
    def is_estop(self, value: bool):
        if self._estop != value:
            self._estop = value
            self.estop_changed.emit(value)
            if value:
                self._operation_mode = "estop"
                self.operation_mode_changed.emit("estop")

    # ---- motor state ----------------------------------------------------------

    def motor_state(self, name: str) -> Optional[MotorState]:
        return self._motor_states.get(name)

    def all_motor_states(self) -> Dict[str, MotorState]:
        return dict(self._motor_states)

    def update_motor(self, name: str, **kwargs: Any):
        """更新电机状态字段并发射 motor_state_updated 信号。

        Usage: app_state.update_motor("Z_motor", is_powered=True, position=12.5)
        """
        ms = self._motor_states.get(name)
        if ms is None:
            return
        for key, value in kwargs.items():
            if hasattr(ms, key):
                setattr(ms, key, value)
        self.motor_state_updated.emit(name)

    def update_motor_position(self, name: str, position: float):
        """轻量位置更新（高频调用，每轮询周期）。"""
        ms = self._motor_states.get(name)
        if ms is not None:
            ms.position = position
            self.motor_position_updated.emit(name, position)

    # ---- gantry sync ----------------------------------------------------------

    @property
    def small_gantry_geared(self) -> bool:
        return self._small_gantry_geared

    @small_gantry_geared.setter
    def small_gantry_geared(self, value: bool):
        if self._small_gantry_geared != value:
            self._small_gantry_geared = value
            self.gantry_geared_changed.emit("small", value)

    @property
    def big_gantry_geared(self) -> bool:
        return self._big_gantry_geared

    @big_gantry_geared.setter
    def big_gantry_geared(self, value: bool):
        if self._big_gantry_geared != value:
            self._big_gantry_geared = value
            self.gantry_geared_changed.emit("big", value)

    # ---- alarms ---------------------------------------------------------------

    @property
    def alarms(self) -> Deque[Dict[str, str]]:
        return self._alarms

    @property
    def latest_alarm(self) -> Optional[Dict[str, str]]:
        return self._alarms[-1] if self._alarms else None

    def add_alarm(self, level: str, message: str):
        if level not in self.ALARM_LEVELS:
            level = "warning"
        self._alarms.append({
            "level": level,
            "message": message,
            "time": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        })
        self.alarm_added.emit(level, message)

    def clear_alarms(self):
        self._alarms.clear()
        self.alarms_cleared.emit()

    # ---- relays ---------------------------------------------------------------

    def relay_state(self, name: str) -> bool:
        return self._relay_states.get(name, False)

    def all_relay_states(self) -> Dict[str, bool]:
        return dict(self._relay_states)

    def set_relay(self, name: str, state: bool):
        if self._relay_states.get(name) != state:
            self._relay_states[name] = state
            self.relay_state_changed.emit(name, state)

    # ---- sensors --------------------------------------------------------------

    def sensor_state(self, name: str) -> bool:
        return self._sensor_states.get(name, False)

    def set_sensor(self, name: str, state: bool):
        self._sensor_states[name] = state

    # ---- pcl ------------------------------------------------------------------

    @property
    def pcl_status(self) -> str:
        return self._pcl_status

    @pcl_status.setter
    def pcl_status(self, value: str):
        if self._pcl_status != value:
            self._pcl_status = value
            self.pcl_status_changed.emit(value)

    @property
    def last_pcl_result(self) -> Optional[PclResult]:
        return self._last_pcl_result

    @last_pcl_result.setter
    def last_pcl_result(self, value: PclResult):
        self._last_pcl_result = value

    # ---- convenience properties -----------------------------------------------

    @property
    def system_ready(self) -> bool:
        """系统就绪（PLC 在线且无急停）。"""
        return self._plc_online and not self._estop

    @property
    def powered_motors(self) -> List[str]:
        """当前已上电的电机名列表。"""
        return [n for n, s in self._motor_states.items() if s.is_powered]

    @property
    def alarmed_motors(self) -> List[str]:
        """当前报警状态的电机名列表。"""
        return [n for n, s in self._motor_states.items() if s.is_alarmed]

    # ---- reset ----------------------------------------------------------------

    def reset(self):
        """重置所有状态到初始值（不发射信号）。"""
        self._plc_online = False
        self._camera_online = False
        self._username = ""
        self._role = ""
        self._operation_mode = "stopped"
        self._estop = False
        self._motor_states.clear()
        self._small_gantry_geared = False
        self._big_gantry_geared = False
        self._alarms.clear()
        self._relay_states.clear()
        self._sensor_states.clear()
        self._pcl_status = "idle"
        self._last_pcl_result = None


app_state = AppState()

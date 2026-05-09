"""Modbus TCP 通讯服务 — 后台线程轮询 PLC，读写寄存器。

重构自 test_total/test_total/plc_worker.py。
通过 pyqtSignal 与 UI 层通信，通过 MotorConfig 计算寄存器地址。
"""

import threading
import time
from collections import deque
from typing import Any, Deque, Dict, List, Optional, Tuple

from PyQt5.QtCore import QObject, pyqtSignal
from pymodbus.client.sync import ModbusTcpClient
from pymodbus.payload import BinaryPayloadBuilder, BinaryPayloadDecoder
from pymodbus.constants import Endian

from src.utils.config_manager import config
from src.utils.app_logger import app_logger
from src.models.motor_config import MotorConfig, create_motor_configs
from src.models.app_state import app_state

# 电机反馈量偏移键名（32-bit float，各两个 16-bit 寄存器）
_FEEDBACK_FLOAT_KEYS = ("actl_pos", "actl_vel", "actl_tor")
# 状态字偏移键名
_STATUS_OFFSET_KEY = "status_word_offset"
# 上电位在状态字中的位置
_IS_POWERED_BIT = 1


class PlcService(QObject):
    """PLC Modbus TCP 通讯服务。

    后台 daemon 线程轮询：先清写队列，再读全局/电机寄存器，
    解析后通过 data_updated 信号发送，并更新 app_state。
    """

    data_updated = pyqtSignal(dict, dict)       # (parsed_motors, parsed_global)
    connection_status = pyqtSignal(bool, str)   # (connected, message)
    error_occurred = pyqtSignal(str)            # error description

    # 读寄存器分块 — 12 台电机 base 100~452，每台 32 寄存器，经验值
    _READ_RANGES: List[Tuple[int, int]] = [
        (100, 100), (200, 100), (300, 100), (400, 85),
    ]

    def __init__(
        self,
        motor_configs: Dict[str, MotorConfig] = None,
        ip: str = None,
        port: int = None,
        parent: QObject = None,
    ):
        super().__init__(parent)
        self.ip = ip or config.plc_ip
        self.port = port or config.plc_port
        self._client: Optional[ModbusTcpClient] = None
        self._running = False
        self._write_queue: Deque[Dict[str, Any]] = deque()
        self._lock = threading.Lock()
        self._motor_configs: Dict[str, MotorConfig] = motor_configs or {}

    # ---- public API -----------------------------------------------------------

    def connect_plc(self):
        """连接 PLC 并启动后台轮询。"""
        if self._running:
            return

        # 确保电机配置已加载
        if not self._motor_configs:
            config.load("motors")
            self._motor_configs = create_motor_configs()
        if not self._motor_configs:
            app_logger.warning("电机配置为空，请检查 motors.yaml")

        try:
            self._client = ModbusTcpClient(self.ip, port=self.port)
            if self._client.connect():
                self._running = True
                self.connection_status.emit(True, "PLC 连接成功")
                app_logger.info(f"PLC 已连接: {self.ip}:{self.port}")
                app_state.plc_online = True
                threading.Thread(target=self._polling_loop, daemon=True).start()
            else:
                self.connection_status.emit(False, "PLC 连接失败: 握手被拒绝")
        except Exception as e:
            msg = f"PLC 连接异常: {e}"
            self.connection_status.emit(False, msg)
            self.error_occurred.emit(msg)
            app_logger.exception(msg)

    def disconnect_plc(self):
        """断开 PLC 连接并停止轮询。"""
        self._running = False
        if self._client:
            try:
                self._client.close()
            except Exception:
                pass
            self._client = None
        self.connection_status.emit(False, "PLC 已断开")
        app_logger.info("PLC 已断开")
        app_state.plc_online = False

    def add_write_task(
        self,
        task_type: str,
        address: int,
        value: Any,
        bit: int = None,
    ):
        """将写操作加入 FIFO 队列，轮询线程按序执行。

        Args:
            task_type: "coil" | "float" | "int16" | "register_bit"
            address: Modbus 绝对地址
            value: 写入值
            bit: 位索引（仅 register_bit 类型需要）
        """
        with self._lock:
            self._write_queue.append({
                "type": task_type,
                "addr": address,
                "val": value,
                "bit": bit,
            })

    # ---- polling loop ---------------------------------------------------------

    def _polling_loop(self):
        """后台轮询主循环。先清写队列，再读寄存器，最后解析发射。"""
        last_success = time.time()
        interval = config.poll_interval_ms / 1000.0

        while self._running:
            self._drain_write_queue()

            try:
                # 全局寄存器 (地址 0-9)
                g_rr = self._client.read_holding_registers(0, 10)
                if g_rr.isError():
                    raise RuntimeError("全局寄存器读取失败")

                # 电机寄存器分块读取
                motor_regs: Dict[int, int] = {}
                for start, count in self._READ_RANGES:
                    rr = self._client.read_holding_registers(start, count)
                    if not rr.isError():
                        for i, val in enumerate(rr.registers):
                            motor_regs[start + i] = val

                # X1 传感器离散输入
                x1_status = False
                try:
                    x1_addr = config.x1_sensor_addr
                    x1_rr = self._client.read_discrete_inputs(x1_addr, 1)
                    if not x1_rr.isError():
                        x1_status = x1_rr.bits[0]
                except Exception:
                    pass

                last_success = time.time()
                self._parse_and_emit(g_rr.registers, motor_regs, x1_status)

            except Exception as e:
                if time.time() - last_success > 5.0:
                    msg = f"PLC 通讯超时 (5s): {e}"
                    self.connection_status.emit(False, msg)
                    self.error_occurred.emit(msg)
                    app_logger.error(msg)
                    self._running = False
                    app_state.plc_online = False
                    break

            time.sleep(interval)

    def _drain_write_queue(self):
        """处理写队列中所有待发任务（写优先于读）。"""
        while self._write_queue:
            task = None
            with self._lock:
                if self._write_queue:
                    task = self._write_queue.popleft()
            if task is not None:
                try:
                    self._process_write(task)
                except Exception as e:
                    app_logger.error(f"写操作失败: {task['type']} "
                                    f"addr={task['addr']} — {e}")

    def _process_write(self, task: Dict[str, Any]):
        """执行单个 Modbus 写操作。"""
        t = task["type"]
        if t == "coil":
            self._client.write_coil(task["addr"], task["val"])
        elif t == "float":
            builder = BinaryPayloadBuilder(
                byteorder=Endian.Big, wordorder=Endian.Little,
            )
            builder.add_32bit_float(float(task["val"]))
            self._client.write_registers(
                task["addr"], builder.build(), skip_encode=True,
            )
        elif t == "int16":
            self._client.write_register(task["addr"], int(task["val"]))
        elif t == "register_bit":
            rr = self._client.read_holding_registers(task["addr"], 1)
            if not rr.isError():
                current = rr.registers[0]
                mask = 1 << task["bit"]
                new_val = (current | mask) if task["val"] else (current & ~mask)
                self._client.write_register(task["addr"], int(new_val))

    # ---- data parsing ---------------------------------------------------------

    def _parse_and_emit(
        self,
        global_regs: List[int],
        motor_regs: Dict[int, int],
        x1_status: bool,
    ):
        """解析原始寄存器为结构化数据，通过 data_updated 发射。"""
        parsed_motors: Dict[str, Dict[str, Any]] = {}
        parsed_global: Dict[str, Any] = {}

        # 全局状态
        d1 = global_regs[1] if len(global_regs) > 1 else 0
        parsed_global["sync_done"] = bool((d1 >> 0) & 1 and (d1 >> 4) & 1)
        parsed_global["x1_status"] = x1_status

        # 各电机反馈
        for name, mc in self._motor_configs.items():
            m_data: Dict[str, Any] = {}

            # 32-bit float 反馈量
            for key in _FEEDBACK_FLOAT_KEYS:
                addr = mc.register_addr(key)
                if addr is not None:
                    m_data[key] = self._read_float(motor_regs, addr)

            # 状态字
            status_addr = mc.register_addr(_STATUS_OFFSET_KEY)
            if status_addr is not None:
                sw = motor_regs.get(status_addr, 0)
                m_data["status_word"] = sw
                m_data["is_powered"] = bool((sw >> _IS_POWERED_BIT) & 1)

            parsed_motors[name] = m_data

        self.data_updated.emit(parsed_motors, parsed_global)

    @staticmethod
    def _read_float(regs: Dict[int, int], addr: int) -> float:
        """从两个连续 16-bit 寄存器解码 32-bit float。"""
        r1 = regs.get(addr, 0)
        r2 = regs.get(addr + 1, 0)
        decoder = BinaryPayloadDecoder.fromRegisters(
            [r1, r2], byteorder=Endian.Big, wordorder=Endian.Little,
        )
        return round(decoder.decode_32bit_float(), 6)

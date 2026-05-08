"""YAML 配置读写 — 单例，支持多级键路径和默认值回退。"""

import os
from typing import Any, Optional

import yaml

from src.utils.app_logger import app_logger


class ConfigManager:
    """加载 config/ 下的 system.yaml、motors.yaml、users.yaml。"""

    def __init__(self, config_dir: str = "config"):
        self._config_dir = config_dir
        self._data: dict[str, dict] = {}
        self._paths: dict[str, str] = {
            "system": os.path.join(config_dir, "system.yaml"),
            "motors": os.path.join(config_dir, "motors.yaml"),
            "users": os.path.join(config_dir, "users.yaml"),
        }

    def load(self, section: Optional[str] = None):
        """加载指定或全部 YAML 文件。"""
        sections = [section] if section else list(self._paths)
        for sec in sections:
            path = self._paths.get(sec)
            if not path:
                app_logger.warning(f"未知配置段: {sec}")
                continue
            try:
                with open(path, "r", encoding="utf-8") as f:
                    self._data[sec] = yaml.safe_load(f) or {}
                app_logger.info(f"配置已加载: {path}")
            except FileNotFoundError:
                app_logger.warning(f"配置文件不存在: {path}，使用空配置")
                self._data[sec] = {}
            except yaml.YAMLError as e:
                app_logger.error(f"YAML 解析失败: {path} — {e}")
                self._data[sec] = {}

    def save(self, section: str):
        """保存指定段到 YAML 文件。"""
        path = self._paths.get(section)
        if not path:
            app_logger.warning(f"无法保存未知段: {section}")
            return
        try:
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                yaml.safe_dump(
                    self._data.get(section, {}), f,
                    allow_unicode=True, default_flow_style=False, sort_keys=False,
                )
            app_logger.info(f"配置已保存: {path}")
        except OSError as e:
            app_logger.error(f"保存配置失败: {path} — {e}")

    # ---- generic get/set ----------------------------------------------------

    def get(self, path: str, default: Any = None) -> Any:
        """多级键路径取值: get('system.plc.default_ip')。"""
        keys = path.split(".")
        node = self._data
        for k in keys:
            if isinstance(node, dict) and k in node:
                node = node[k]
            else:
                return default
        return node

    def set(self, path: str, value: Any):
        """多级键路径设值并保存: set('system.plc.default_ip', '192.168.1.100')。"""
        keys = path.split(".")
        section = keys[0]
        if section not in self._paths:
            app_logger.warning(f"set 失败: 未知段 {section}")
            return
        node = self._data.setdefault(section, {})
        for k in keys[1:-1]:
            if not isinstance(node, dict):
                node = {}
            node = node.setdefault(k, {})
        node[keys[-1]] = value
        self.save(section)

    # ---- all-data access ----------------------------------------------------

    @property
    def data(self) -> dict:
        return self._data

    def all_motors(self) -> list:
        return self.get("motors.motors", [])

    def all_users(self) -> list:
        return self.get("users.users", [])

    # ---- shortcuts ----------------------------------------------------------

    @property
    def plc_ip(self) -> str:
        return self.get("system.plc.default_ip", "192.168.1.88")

    @property
    def plc_port(self) -> int:
        return self.get("system.plc.port", 502)

    @property
    def poll_interval_ms(self) -> int:
        return self.get("system.plc.poll_interval_ms", 100)

    @property
    def pcl_params(self) -> dict:
        return self.get("system.pcl.default_params", {})

    @property
    def camera_config(self) -> dict:
        return self.get("system.camera", {})

    @property
    def x1_sensor_addr(self) -> int:
        return self.get("motors.system_registers.sensors.x1_discrete_input_addr", 20)

    @property
    def gantry_mapping(self) -> dict:
        return self.get("motors.gantry", {})

    @property
    def offsets(self) -> dict:
        return self.get("motors.offsets", {})

    @property
    def system_registers(self) -> dict:
        return self.get("motors.system_registers", {})

    @property
    def gear_registers(self) -> dict:
        return self.get("motors.system_registers.gear", {})

    @property
    def gun_registers(self) -> dict:
        return self.get("motors.system_registers.gun", {})

    @property
    def relay_registers(self) -> dict:
        return self.get("motors.system_registers.relays", {})

    @property
    def position_cmd_registers(self) -> dict:
        return self.get("motors.system_registers.position_cmds", {})


# 模块级单例
config = ConfigManager()

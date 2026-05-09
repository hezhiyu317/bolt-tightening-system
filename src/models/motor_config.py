"""电机配置数据模型 — 将 motors.yaml 的字典封装为结构化对象。

提供 MotorConfig 类和工厂函数 create_motor_configs()。
使用前需先加载配置: config.load("motors")。
"""

from typing import Dict, List, Optional, Tuple

from src.utils.config_manager import config


class MotorConfig:
    """单台电机的静态配置（从 motors.yaml 加载后不变）。

    核心能力：通过偏移名直接计算 Modbus 绝对地址。
        motor.register_addr("abs_cmd")   → 107
        motor.register_addr("actl_pos")  → 123
    """

    __slots__ = (
        "name", "base", "enable_m", "group",
        "_offsets", "_gantry_size", "_gantry_axis",
    )

    def __init__(
        self,
        name: str,
        base: int,
        enable_m: int,
        group: str,
        offsets: Dict[str, object],
        gantry_size: str = "",
        gantry_axis: str = "",
    ):
        self.name = name
        self.base = base
        self.enable_m = enable_m
        self.group = group
        self._offsets = offsets
        self._gantry_size = gantry_size
        self._gantry_axis = gantry_axis

    # ---- register address ----------------------------------------------------

    def register_addr(self, key: str) -> Optional[int]:
        """通过偏移名计算 Modbus 绝对地址。

        Args:
            key: 偏移名，如 "abs_cmd", "actl_pos", "status_word_offset"。

        Returns:
            绝对地址 = base + offset，若偏移值未知则返回 None。
        """
        offset = self._offsets.get(key)
        if offset is None or not isinstance(offset, int):
            return None
        return self.base + offset

    def all_register_map(self) -> Dict[str, Optional[int]]:
        """返回该电机所有已知寄存器的 {偏移名: 绝对地址} 映射。

        值为 None 表示地址待确认。
        """
        result: Dict[str, Optional[int]] = {}
        for key, offset in self._offsets.items():
            if isinstance(offset, int):
                result[key] = self.base + offset
            else:
                result[key] = None
        return result

    # ---- gantry --------------------------------------------------------------

    @property
    def gantry_size(self) -> str:
        """龙门规格 "small" / "big" / ""（非龙门电机为空）。"""
        return self._gantry_size

    @property
    def gantry_axis(self) -> str:
        """龙门三坐标轴名 "X" / "Y_left" / "Y_right" / "Z" / ""。"""
        return self._gantry_axis

    # ---- group checks --------------------------------------------------------

    @property
    def is_small_gantry(self) -> bool:
        return self.group == "Small Gantry"

    @property
    def is_big_gantry(self) -> bool:
        return self.group == "Big Gantry"

    @property
    def is_rotary(self) -> bool:
        return self.group == "Rotary"

    # ---- repr -----------------------------------------------------------------

    def __repr__(self) -> str:
        return (
            f"MotorConfig(name={self.name!r}, base={self.base}, "
            f"group={self.group!r}, enable_m={self.enable_m})"
        )


def create_motor_configs() -> Dict[str, "MotorConfig"]:
    """从 YAML 配置创建全部 12 台电机的 MotorConfig 字典。

    config.load("motors") 必须先被调用，否则返回空字典。

    Returns:
        {motor_name: MotorConfig} — 以电机名为 key。
    """
    motors = config.all_motors()
    offsets = config.offsets
    gantry = config.gantry_mapping

    motor_to_gantry: Dict[str, Tuple[str, str]] = {}
    for size in ("small", "big"):
        for axis, motor_name in gantry.get(size, {}).items():
            motor_to_gantry[motor_name] = (size, axis)

    configs: Dict[str, MotorConfig] = {}
    for m in motors:
        g_size, g_axis = motor_to_gantry.get(m["name"], ("", ""))
        configs[m["name"]] = MotorConfig(
            name=m["name"],
            base=m["base"],
            enable_m=m["enable_m"],
            group=m["group"],
            offsets=offsets,
            gantry_size=g_size,
            gantry_axis=g_axis,
        )
    return configs


def get_motor_names_by_group(group: str) -> List[str]:
    """获取指定分组的电机名列表。

    Args:
        group: "Small Gantry", "Big Gantry", "Rotary"

    Returns:
        电机名列表（按定义顺序）。
    """
    return [m["name"] for m in config.all_motors() if m.get("group") == group]

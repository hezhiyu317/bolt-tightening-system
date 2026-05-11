"""单电机控制卡片 — 显示 + 参数 + 运动控制。

仿照 test_total/ui_widgets.py MotorWidget 布局。
"""

from PyQt5.QtCore import QTimer, pyqtSignal
from PyQt5.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from src.models.motor_config import MotorConfig
from src.ui.styles import (
    BG_PANEL,
    BLUE_FUNC,
    BORDER_CARD,
    CARD_RADIUS,
    FONT_FAMILY,
    FONT_MONO,
    FONT_SIZE_SM,
    GREEN_STATUS,
    RED_ALERT,
    TEXT_DIM,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)


class MotorWidget(QGroupBox):
    """单电机控制卡片。

    信号 write_requested 发出写任务，由上层转发给 PlcService。
    """

    write_requested = pyqtSignal(dict)  # {type, addr, val, bit}

    def __init__(self, motor_config: MotorConfig, parent=None):
        super().__init__(motor_config.name, parent)
        self._mc = motor_config
        self._is_y_axis = motor_config.gantry_axis in ("Y_left", "Y_right")
        self._gantry_synced = False
        self._inputs: dict = {}
        self._setup_ui()
        self.set_enabled_all(False)

    @property
    def inputs(self) -> dict:
        """暴露输入框引用给上层，用于全局参数同步。"""
        return self._inputs

    # ---- UI ----------------------------------------------------------------

    def _setup_ui(self):
        self.setStyleSheet(self._card_style())
        main = QVBoxLayout(self)
        main.setSpacing(6)

        # 1. 显示区
        main.addLayout(self._build_display())

        # 2. 参数区（无 acc/dec，无同步按钮）
        main.addLayout(self._build_params())

        # 3. 运动控制按钮
        main.addLayout(self._build_motion())

        # 4. 状态按钮
        main.addLayout(self._build_state())

    def _build_display(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(4)

        self._lbl_pos = self._value_label("0.00")
        self._lbl_vel = self._value_label("0.00")
        self._lbl_tor = self._value_label("0.00")
        self._lbl_state = QLabel("离线")
        self._lbl_state.setStyleSheet(
            f"color: {TEXT_DIM}; font-family: {FONT_FAMILY};")

        grid.addWidget(QLabel("位置:"), 0, 0)
        grid.addWidget(self._lbl_pos, 0, 1)
        grid.addWidget(QLabel("速度:"), 0, 2)
        grid.addWidget(self._lbl_vel, 0, 3)
        grid.addWidget(QLabel("力矩:"), 1, 0)
        grid.addWidget(self._lbl_tor, 1, 1)
        grid.addWidget(QLabel("状态:"), 1, 2)
        grid.addWidget(self._lbl_state, 1, 3)
        return grid

    def _build_params(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(3)

        param_config = [
            ("点动速度", "jog_vel_set"),
            ("相对速度", "rel_vel_set"),
            ("绝对速度", "abs_vel_set"),
            ("相对距离", "rel_pos_set"),
            ("绝对坐标", "abs_pos_set"),
        ]
        for i, (label_text, key) in enumerate(param_config):
            lbl = QLabel(label_text)
            lbl.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;")
            inp = QLineEdit("0.0")
            inp.setStyleSheet(self._input_style())
            inp.setFixedWidth(80)
            self._inputs[key] = inp
            grid.addWidget(lbl, i, 0)
            grid.addWidget(inp, i, 1)

        return grid

    def _build_motion(self) -> QGridLayout:
        grid = QGridLayout()
        grid.setSpacing(4)

        self._btn_jog_neg = QPushButton("点动 -")
        self._btn_jog_pos = QPushButton("点动 +")
        self._btn_rel = QPushButton("相对运动")
        self._btn_abs = QPushButton("绝对运动")

        for b in (self._btn_jog_neg, self._btn_jog_pos,
                   self._btn_rel, self._btn_abs):
            b.setStyleSheet(self._motion_btn_style())

        self._btn_jog_neg.pressed.connect(
            lambda: self._set_cmd_bit("jog_b_cmd", 1))
        self._btn_jog_neg.released.connect(
            lambda: self._set_cmd_bit("jog_b_cmd", 0))
        self._btn_jog_pos.pressed.connect(
            lambda: self._set_cmd_bit("jog_f_cmd", 1))
        self._btn_jog_pos.released.connect(
            lambda: self._set_cmd_bit("jog_f_cmd", 0))
        self._btn_rel.clicked.connect(
            lambda: self._trigger_cmd("rel_cmd"))
        self._btn_abs.clicked.connect(
            lambda: self._trigger_cmd("abs_cmd"))

        grid.addWidget(self._btn_jog_neg, 0, 0)
        grid.addWidget(self._btn_jog_pos, 0, 1)
        grid.addWidget(self._btn_rel, 1, 0)
        grid.addWidget(self._btn_abs, 1, 1)
        return grid

    def _build_state(self) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)

        self._btn_enable = QPushButton("使能")
        self._btn_enable.setStyleSheet(self._enable_btn_style(False))
        self._btn_enable.clicked.connect(self._on_enable)

        self._btn_reset = QPushButton("复位")
        self._btn_reset.setStyleSheet(self._state_btn_style())
        self._btn_reset.clicked.connect(
            lambda: self._trigger_cmd("reset_cmd"))

        self._btn_home = QPushButton("寻零")
        self._btn_home.setStyleSheet(self._state_btn_style())
        self._btn_home.clicked.connect(
            lambda: self._trigger_cmd("home_cmd"))

        self._btn_stop = QPushButton("急停")
        self._btn_stop.setStyleSheet(
            f"background-color: {RED_ALERT}; color: #FFFFFF;"
            f"font-weight: bold; border: none; border-radius: 3px;"
            f"padding: 4px 10px;"
        )
        self._btn_stop.clicked.connect(
            lambda: self._trigger_cmd("stop_cmd"))

        row.addWidget(self._btn_enable)
        row.addWidget(self._btn_reset)
        row.addWidget(self._btn_home)
        row.addWidget(self._btn_stop)
        return row

    # ---- public API -------------------------------------------------------

    def update_display(self, data: dict, is_synced: bool):
        self._lbl_pos.setText(f"{data.get('actl_pos', 0):.2f}")
        self._lbl_vel.setText(f"{data.get('actl_vel', 0):.2f}")
        self._lbl_tor.setText(f"{data.get('actl_tor', 0):.2f}")
        powered = data.get("is_powered", False)
        self._lbl_state.setText("在线" if powered else "离线")
        self._lbl_state.setStyleSheet(
            f"color: {GREEN_STATUS if powered else TEXT_DIM};"
            f"font-family: {FONT_FAMILY};"
        )
        # 同步使能按钮样式
        was_green = GREEN_STATUS in (self._btn_enable.styleSheet() or "")
        if powered and not was_green:
            self._set_enable_style(True)
        elif not powered and was_green:
            self._set_enable_style(False)
        self._gantry_synced = is_synced

    def set_enabled_all(self, enabled: bool):
        for child in self.findChildren(QLineEdit):
            child.setEnabled(enabled)
        if self._btn_stop:
            self._btn_stop.setEnabled(enabled)

    # ---- internal ---------------------------------------------------------

    def _set_cmd_bit(self, offset_key: str, val: int):
        motion_keys = ("jog_f_cmd", "jog_b_cmd", "rel_cmd", "abs_cmd")
        if offset_key in motion_keys and val == 1:
            if self._is_y_axis and not self._gantry_synced:
                QMessageBox.warning(
                    self, "禁止操作", "龙门未同步！禁止操作 Y 轴电机。")
                return
        addr = self._mc.base
        offset = self._mc.offset_of(offset_key)
        if offset is not None:
            self.write_requested.emit({
                "type": "register_bit", "addr": addr,
                "val": val, "bit": offset,
            })

    def _trigger_cmd(self, offset_key: str):
        self._set_cmd_bit(offset_key, 1)
        QTimer.singleShot(200, lambda: self._set_cmd_bit(offset_key, 0))

    def _on_enable(self):
        was_green = GREEN_STATUS in (self._btn_enable.styleSheet() or "")
        target = not was_green
        self._set_enable_style(target)
        self.write_requested.emit({
            "type": "coil", "addr": self._mc.enable_m,
            "val": target, "bit": None,
        })

    def _set_enable_style(self, powered: bool):
        if powered:
            self._btn_enable.setText("已使能")
        else:
            self._btn_enable.setText("使能")
        self._btn_enable.setStyleSheet(self._enable_btn_style(powered))

    # ---- style helpers ----------------------------------------------------

    def _value_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-family: {FONT_MONO};"
            f"font-size: 14px; font-weight: bold;"
        )
        return lbl

    def _motion_btn_style(self) -> str:
        """运动按钮 — 仿 test_total 简洁风格。"""
        return (
            f"QPushButton {{"
            f"  background-color: #FFFFFF; color: {TEXT_PRIMARY};"
            f"  border: 1px solid {BORDER_CARD}; border-radius: 3px;"
            f"  padding: 4px 8px; font-size: {FONT_SIZE_SM}px;"
            f"}}"
            f"QPushButton:hover {{ border-color: {BLUE_FUNC}; }}"
            f"QPushButton:pressed {{ background-color: #F0F2F5; }}"
        )

    def _state_btn_style(self) -> str:
        """状态按钮（复位/寻零）— 仿 test_total 简洁风格。"""
        return (
            f"QPushButton {{"
            f"  background-color: #FFFFFF; color: {TEXT_PRIMARY};"
            f"  border: 1px solid {BORDER_CARD}; border-radius: 3px;"
            f"  padding: 4px 10px; font-size: {FONT_SIZE_SM}px;"
            f"}}"
            f"QPushButton:hover {{ border-color: {BLUE_FUNC}; }}"
            f"QPushButton:pressed {{ background-color: #F0F2F5; }}"
        )

    def _enable_btn_style(self, powered: bool) -> str:
        if powered:
            return (
                f"QPushButton {{"
                f"  background-color: {GREEN_STATUS}; color: #FFFFFF;"
                f"  font-weight: bold; border: none; border-radius: 3px;"
                f"  padding: 4px 10px; font-size: {FONT_SIZE_SM}px;"
                f"}}"
            )
        else:
            return (
                f"QPushButton {{"
                f"  background-color: #FFFFFF; color: {TEXT_PRIMARY};"
                f"  border: 1px solid {BORDER_CARD}; border-radius: 3px;"
                f"  padding: 4px 10px; font-size: {FONT_SIZE_SM}px;"
                f"}}"
                f"QPushButton:hover {{ border-color: {BLUE_FUNC}; }}"
            )

    def _input_style(self) -> str:
        return (
            f"QLineEdit {{"
            f"  background-color: #FFFFFF; color: {TEXT_PRIMARY};"
            f"  border: 1px solid {BORDER_CARD}; border-radius: 3px;"
            f"  padding: 3px 6px; font-family: {FONT_MONO};"
            f"  font-size: {FONT_SIZE_SM}px;"
            f"}}"
            f"QLineEdit:focus {{ border-color: {BLUE_FUNC}; }}"
        )

    def _card_style(self) -> str:
        return (
            f"QGroupBox {{"
            f"  background-color: {BG_PANEL};"
            f"  border: 1px solid {BORDER_CARD};"
            f"  border-radius: {CARD_RADIUS}px;"
            f"  margin-top: 12px; padding-top: 8px;"
            f"  font-family: {FONT_FAMILY};"
            f"  font-size: {FONT_SIZE_SM}px; color: {BLUE_FUNC};"
            f"}}"
            f"QGroupBox::title {{"
            f"  subcontrol-origin: margin; left: 10px; padding: 0 4px;"
            f"}}"
        )

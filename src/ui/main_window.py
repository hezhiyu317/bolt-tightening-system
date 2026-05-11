"""主窗口框架 — 四区布局（顶栏 / 左侧菜单 / 中央内容 / 右侧面板 / 底栏）。"""

from datetime import datetime

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.models.app_state import app_state
from src.services.camera_service import CameraService
from src.services.pcl_service import PclService
from src.services.plc_service import PlcService
from src.ui.pages.data_recording_page import DataRecordingPage
from src.ui.pages.motor_control_page import MotorControlPage
from src.ui.pages.vision_page import VisionPage
from src.ui.styles import (
    BG_BASE,
    BG_DARK,
    BG_FOOTER,
    BG_HEADER,
    BG_SIDEBAR,
    BLUE_FUNC,
    BORDER_CARD,
    FONT_FAMILY,
    FONT_MONO,
    FONT_SIZE_SM,
    FONT_SIZE_BASE,
    GREEN_STATUS,
    HEADER_HEIGHT,
    FOOTER_HEIGHT,
    ORANGE_WARN,
    QSS_DANGER_BUTTON,
    QSS_PRIMARY_BUTTON,
    QSS_SECONDARY_BUTTON,
    RED_ALERT,
    SIDEBAR_WIDTH,
    TEXT_DIM,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from src.ui.widgets.right_panel import RightPanel
from src.ui.widgets.status_indicator import StatusIndicator


class MainWindow(QWidget):
    """应用主窗口。"""

    def __init__(
        self,
        camera_service: CameraService = None,
        pcl_service: PclService = None,
        plc_service: PlcService = None,
        motor_configs: dict = None,
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self._camera = camera_service
        self._pcl = pcl_service
        self._plc = plc_service
        self._motor_configs = motor_configs or {}

        self.setWindowTitle("过盈螺桩选配机器人控制系统 — HARBIN INSTITUTE OF TECHNOLOGY")
        self.resize(1400, 900)
        self.setMinimumSize(1100, 700)

        self._nav_buttons = []
        self._all_enabled = False

        # 初始化 app_state 中所有电机的状态槽位
        app_state.init_motors(list(self._motor_configs.keys()))

        self._setup_ui()
        self._wire_plc_signals()
        self._start_clock()

    # ---- UI construction -----------------------------------------------------

    def _setup_ui(self):
        self.setStyleSheet(
            f"QWidget {{"
            f"  background-color: {BG_BASE};"
            f"  color: {TEXT_PRIMARY};"
            f"  font-family: {FONT_FAMILY};"
            f"  font-size: {FONT_SIZE_BASE}px;"
            f"}}"
        )

        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        # ---- 顶部栏 ----
        root.addWidget(self._build_header())

        # ---- 中间三栏 ----
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(0)
        body.addWidget(self._build_sidebar())
        body.addWidget(self._build_central(), stretch=1)
        body.addWidget(self._build_right_panel())
        root.addLayout(body, stretch=1)

        # ---- 底部栏 ----
        root.addWidget(self._build_footer())

    def _build_header(self) -> QWidget:
        container = QWidget()
        vbox = QVBoxLayout(container)
        vbox.setContentsMargins(0, 0, 0, 0)
        vbox.setSpacing(0)

        # ---- Row 1: title + nav + clock ----
        row1 = QWidget()
        row1.setFixedHeight(HEADER_HEIGHT)
        row1.setStyleSheet(
            f"background-color: {BG_HEADER};"
            f"border-bottom: 1px solid {BORDER_CARD};"
        )
        r1_layout = QHBoxLayout(row1)
        r1_layout.setContentsMargins(12, 0, 12, 0)

        title = QLabel("⚙ 过盈螺桩选配机器人控制系统")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {TEXT_PRIMARY};"
            f"font-family: {FONT_FAMILY};"
        )
        r1_layout.addWidget(title)

        r1_layout.addStretch()

        tabs = ["\U0001f4cb 工作流", "◉ 视觉定位", "⌂ 三坐标平台",
                "\U0001f4ca 数据记录", "⚠ 故障处理", "\U0001f6e1 安全模式"]
        for i, tab in enumerate(tabs):
            btn = QPushButton(tab)
            btn.setFlat(True)
            btn.clicked.connect(lambda checked, idx=i: self._on_nav_clicked(idx))
            self._nav_buttons.append(btn)
            r1_layout.addWidget(btn)

        self._set_active_nav(0)

        r1_layout.addStretch()

        self._clock_label = QLabel()
        self._clock_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-family: {FONT_MONO};"
            f"font-size: {FONT_SIZE_SM}px;"
        )
        r1_layout.addWidget(self._clock_label)

        r1_layout.addSpacing(16)

        user_lbl = QLabel("\U0001f464 管理员")
        user_lbl.setStyleSheet(
            f"color: {BLUE_FUNC}; font-size: {FONT_SIZE_SM}px;"
        )
        r1_layout.addWidget(user_lbl)

        vbox.addWidget(row1)

        # ---- Row 2: PLC comm | motion control ----
        row2 = QWidget()
        row2.setFixedHeight(40)
        row2.setStyleSheet(
            f"background-color: {BG_HEADER};"
            f"border-bottom: 1px solid {BORDER_CARD};"
        )
        r2_layout = QHBoxLayout(row2)
        r2_layout.setContentsMargins(12, 4, 12, 4)
        r2_layout.setSpacing(8)

        # -- 通信设置组 --
        r2_layout.addWidget(QLabel("\U0001f4e1 PLC IP:"))
        self._txt_ip = QLineEdit(self._plc.ip if self._plc else "192.168.1.88")
        self._txt_ip.setFixedWidth(110)
        self._txt_ip.setStyleSheet(self._input_style())
        r2_layout.addWidget(self._txt_ip)

        self._btn_plc_connect = QPushButton("连接 PLC")
        self._btn_plc_connect.setFixedHeight(28)
        self._btn_plc_connect.setStyleSheet(QSS_PRIMARY_BUTTON)
        self._btn_plc_connect.clicked.connect(self._on_plc_toggle)
        r2_layout.addWidget(self._btn_plc_connect)

        # 分隔线
        sep = QLabel()
        sep.setFixedWidth(1)
        sep.setFixedHeight(24)
        sep.setStyleSheet(f"background-color: {BORDER_CARD};")
        r2_layout.addWidget(sep)

        r2_layout.addSpacing(8)

        # -- 运动控制组 --
        self._btn_sync = QPushButton("⇅ 龙门同步")
        self._btn_sync.setFixedHeight(28)
        self._btn_sync.setStyleSheet(QSS_PRIMARY_BUTTON)
        self._btn_sync.clicked.connect(self._on_gantry_sync)
        self._btn_sync.setEnabled(False)
        r2_layout.addWidget(self._btn_sync)

        # 同步状态指示灯
        self._sync_indicator = StatusIndicator("offline", size=8)
        r2_layout.addWidget(self._sync_indicator)
        self._lbl_sync_status = QLabel("未同步")
        self._lbl_sync_status.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: {FONT_SIZE_SM}px;"
        )
        r2_layout.addWidget(self._lbl_sync_status)

        r2_layout.addSpacing(12)

        self._btn_global_enable = QPushButton("⚡ 全轴使能")
        self._btn_global_enable.setFixedHeight(28)
        self._btn_global_enable.setStyleSheet(QSS_SECONDARY_BUTTON)
        self._btn_global_enable.clicked.connect(self._on_toggle_all_enable)
        self._btn_global_enable.setEnabled(False)
        r2_layout.addWidget(self._btn_global_enable)

        self._btn_brake = QPushButton("\U0001f512 锁紧抱闸")
        self._btn_brake.setFixedHeight(28)
        self._btn_brake.setCheckable(True)
        self._btn_brake.setStyleSheet(QSS_SECONDARY_BUTTON)
        self._btn_brake.clicked.connect(self._on_brake_toggle)
        self._btn_brake.setEnabled(False)
        r2_layout.addWidget(self._btn_brake)

        r2_layout.addStretch()

        vbox.addWidget(row2)
        return container

    def _build_sidebar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedWidth(SIDEBAR_WIDTH)
        bar.setStyleSheet(f"background-color: {BG_SIDEBAR};")

        layout = QVBoxLayout(bar)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(4)

        icons = ["\U0001f4cb", "\U0001f4c8", "\U0001f4be", "⚠", "\U0001f514", "\U0001f6e1", "⚙"]
        labels = ["工作", "监控", "记录", "故障", "报警", "安全", "设置"]
        for i, name in enumerate(labels):
            btn = QPushButton(f"{icons[i]}\n{name}")
            btn.setFlat(True)
            btn.setFixedSize(48, 48)
            active = i == 0
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  color: {BLUE_FUNC if active else TEXT_SECONDARY};"
                f"  font-size: 10px;"
                f"  border: none;"
                f"  border-left: 3px solid {BLUE_FUNC if active else 'transparent'};"
                f"  background-color: {'#E6F7FF' if active else 'transparent'};"
                f"}}"
                f"QPushButton:hover {{"
                f"  background-color: #E6F7FF;"
                f"}}"
            )
            layout.addWidget(btn, alignment=Qt.AlignHCenter)

        layout.addStretch()
        return bar

    def _build_central(self) -> QStackedWidget:
        """中央内容区 — 各页面通过顶部导航切换。"""
        self._central_stack = QStackedWidget()

        # 页面索引与顶部 nav 按钮一一对应
        self._central_stack.addWidget(self._build_placeholder("工作流"))
        self._central_stack.addWidget(self._build_vision_page())
        self._central_stack.addWidget(self._build_motor_page())
        self._central_stack.addWidget(self._build_data_recording_page())
        self._central_stack.addWidget(self._build_placeholder("故障处理"))
        self._central_stack.addWidget(self._build_placeholder("安全模式"))

        return self._central_stack

    def _build_motor_page(self) -> MotorControlPage:
        """三坐标平台页面。"""
        return MotorControlPage(
            plc_service=self._plc,
            motor_configs=self._motor_configs,
            parent=self,
        )

    def _build_vision_page(self) -> VisionPage:
        """视觉定位页面。"""
        return VisionPage(
            camera_service=self._camera,
            pcl_service=self._pcl,
            parent=self,
        )

    def _build_data_recording_page(self) -> DataRecordingPage:
        """数据记录页面 — 实时力矩图表。"""
        torque_motors = ["SPF_motor", "SPT_motor", "SPM_motor", "SPC_motor"]
        return DataRecordingPage(
            plc_service=self._plc,
            torque_motor_names=torque_motors,
            parent=self,
        )

    def _build_placeholder(self, name: str) -> QWidget:
        """占位页面。"""
        w = QWidget()
        w.setStyleSheet(f"background-color: {BG_BASE};")
        layout = QVBoxLayout(w)
        lbl = QLabel(f"{name}\n\n（待开发）")
        lbl.setAlignment(Qt.AlignCenter)
        lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 20px;")
        layout.addWidget(lbl)
        return w

    def _build_right_panel(self) -> RightPanel:
        panel = RightPanel(
            camera_service=self._camera,
            pcl_service=self._pcl,
        )
        return panel

    def _build_footer(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(FOOTER_HEIGHT)
        bar.setStyleSheet(
            f"background-color: {BG_FOOTER};"
            f"border-top: 1px solid {BORDER_CARD};"
        )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)
        layout.setSpacing(24)

        self._footer_labels = {}
        infos = [
            ("network", "网络", "未连接", TEXT_DIM),
            ("plc", "PLC", "未连接", TEXT_DIM),
            ("version", "版本", "v1.0.0", TEXT_SECONDARY),
        ]
        for key, label, value, color in infos:
            lbl = QLabel(f"{label}: {value}")
            lbl.setStyleSheet(
                f"color: {color}; font-size: {FONT_SIZE_SM}px;"
            )
            layout.addWidget(lbl)
            self._footer_labels[key] = lbl

        layout.addStretch()

        self._footer_hint = QLabel("系统就绪")
        self._footer_hint.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;")
        layout.addWidget(self._footer_hint)

        # 连接 app_state 更新底栏
        self._connect_footer_signals()

        return bar

    # ---- navigation ----------------------------------------------------------

    def _on_nav_clicked(self, index: int):
        self._central_stack.setCurrentIndex(index)
        self._set_active_nav(index)

    def _set_active_nav(self, active_idx: int):
        for i, btn in enumerate(self._nav_buttons):
            if i == active_idx:
                btn.setStyleSheet(
                    f"color: {BLUE_FUNC}; font-size: {FONT_SIZE_SM}px;"
                    f"border-bottom: 2px solid {BLUE_FUNC}; padding: 4px 10px;"
                )
            else:
                btn.setStyleSheet(
                    f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;"
                    f"border-bottom: 2px solid transparent; padding: 4px 10px;"
                )

    # ---- PLC signal wiring ---------------------------------------------------

    def _wire_plc_signals(self):
        if not self._plc:
            return
        self._plc.connection_status.connect(self._on_plc_connection)
        self._plc.data_updated.connect(self._on_plc_data)

    # ---- PLC connection ------------------------------------------------------

    def _on_plc_toggle(self):
        if not self._plc:
            return
        if not self._plc._running:
            self._plc.ip = self._txt_ip.text()
            self._btn_plc_connect.setText("连接中...")
            self._btn_plc_connect.setEnabled(False)
            self._plc.connect_plc()
        else:
            self._btn_plc_connect.setText("断开中...")
            self._btn_plc_connect.setEnabled(False)
            self._plc.disconnect_plc()

    def _on_plc_connection(self, connected: bool, msg: str):
        self._btn_plc_connect.setEnabled(True)
        if connected:
            self._btn_plc_connect.setText("断开 PLC")
            self._btn_plc_connect.setStyleSheet(QSS_DANGER_BUTTON)
            self._enable_top_controls(True)
        else:
            self._btn_plc_connect.setText("连接 PLC")
            self._btn_plc_connect.setStyleSheet(QSS_PRIMARY_BUTTON)
            self._enable_top_controls(False)

    def _on_plc_data(self, motors_data: dict, global_data: dict):
        synced = global_data.get("sync_done", False)
        if synced:
            self._sync_indicator.set_status("online")
            self._lbl_sync_status.setText("已同步")
            self._lbl_sync_status.setStyleSheet(
                f"color: {GREEN_STATUS}; font-size: {FONT_SIZE_SM}px;"
            )
        else:
            self._sync_indicator.set_status("offline")
            self._lbl_sync_status.setText("未同步")
            self._lbl_sync_status.setStyleSheet(
                f"color: {TEXT_DIM}; font-size: {FONT_SIZE_SM}px;"
            )

        # 同步写入 app_state，驱动右侧面板坐标显示
        for name, data in motors_data.items():
            app_state.update_motor(
                name,
                is_powered=data.get("is_powered", False),
                position=data.get("actl_pos", 0.0),
                velocity=data.get("actl_vel", 0.0),
                torque=data.get("actl_tor", 0.0),
                status_word=data.get("status_word", 0),
            )

    # ---- gantry sync ---------------------------------------------------------

    def _on_gantry_sync(self):
        if not self._plc:
            return
        # 触发龙门同步（地址 0，位 0）
        self._plc.add_write_task("register_bit", 0, 1, bit=0)
        QTimer.singleShot(200, lambda: self._plc.add_write_task(
            "register_bit", 0, 0, bit=0))

    # ---- global estop (wired from right panel) -------------------------------

    def _on_app_estop_changed(self, active: bool):
        """右面板急停按钮触发的全局急停 — 发送停止位到所有电机。"""
        if not self._plc or not active:
            return
        for mc in self._motor_configs.values():
            stop_bit = mc.offset_of("stop_cmd")
            if stop_bit is not None:
                self._plc.add_write_task(
                    "register_bit", mc.base, 1, bit=stop_bit)
                QTimer.singleShot(
                    200,
                    lambda b=mc.base, sb=stop_bit: self._plc.add_write_task(
                        "register_bit", b, 0, bit=sb))

    # ---- brake ---------------------------------------------------------------

    def _on_brake_toggle(self, checked: bool):
        if not self._plc:
            return
        if checked:
            self._btn_brake.setText("\U0001f513 松开抱闸")
        else:
            self._btn_brake.setText("\U0001f512 锁紧抱闸")
        self._plc.add_write_task("coil", 18, checked)

    # ---- all-axis enable -----------------------------------------------------

    def _on_toggle_all_enable(self):
        if not self._plc:
            return
        self._all_enabled = not self._all_enabled
        if self._all_enabled:
            self._btn_global_enable.setText("⚡ 全轴失能")
            self._btn_global_enable.setStyleSheet(
                f"QPushButton {{"
                f"  background-color: {GREEN_STATUS}; color: #FFFFFF; font-weight: bold;"
                f"  border: none; border-radius: 4px;"
                f"  padding: 6px 16px;"
                f"}}"
            )
        else:
            self._btn_global_enable.setText("⚡ 全轴使能")
            self._btn_global_enable.setStyleSheet(QSS_SECONDARY_BUTTON)
        for mc in self._motor_configs.values():
            self._plc.add_write_task("coil", mc.enable_m, self._all_enabled)
        # 同步更新 MotorControlPage 中控件的使能状态
        motor_page = self._central_stack.widget(2)  # 索引 2 = 三坐标平台
        if hasattr(motor_page, "set_controls_enabled"):
            motor_page.set_controls_enabled(self._all_enabled)

    # ---- top-row controls enable/disable -------------------------------------

    def _enable_top_controls(self, enabled: bool):
        self._btn_sync.setEnabled(enabled)
        self._btn_brake.setEnabled(enabled)
        self._btn_global_enable.setEnabled(enabled)
        # 同步更新 MotorControlPage 中的电机控件
        motor_page = self._central_stack.widget(2)
        if hasattr(motor_page, "set_controls_enabled"):
            motor_page.set_controls_enabled(enabled and self._all_enabled)

    # ---- footer signals ------------------------------------------------------

    def _connect_footer_signals(self):
        app_state.plc_online_changed.connect(self._on_footer_plc)
        app_state.camera_online_changed.connect(self._on_footer_network)
        app_state.estop_changed.connect(self._on_app_estop_changed)

    def _on_footer_plc(self, online: bool):
        lbl = self._footer_labels.get("plc")
        if lbl:
            lbl.setText(f"PLC: {'在线' if online else '离线'}")
            lbl.setStyleSheet(
                f"color: {GREEN_STATUS if online else TEXT_DIM};"
                f"font-size: {FONT_SIZE_SM}px;"
            )

    def _on_footer_network(self, online: bool):
        lbl = self._footer_labels.get("network")
        if lbl:
            lbl.setText(f"网络: {'已连接' if online else '未连接'}")
            lbl.setStyleSheet(
                f"color: {GREEN_STATUS if online else TEXT_DIM};"
                f"font-size: {FONT_SIZE_SM}px;"
            )

    # ---- style helpers -------------------------------------------------------

    @staticmethod
    def _input_style() -> str:
        return (
            f"QLineEdit {{"
            f"  background-color: #FFFFFF; color: {TEXT_PRIMARY};"
            f"  border: 1px solid {BORDER_CARD}; border-radius: 3px;"
            f"  padding: 2px 6px; font-family: {FONT_MONO};"
            f"  font-size: {FONT_SIZE_SM}px;"
            f"}}"
            f"QLineEdit:focus {{ border-color: {BLUE_FUNC}; }}"
        )

    # ---- clock ----------------------------------------------------------------

    def _start_clock(self):
        self._tick()
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(1000)

    def _tick(self):
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        self._clock_label.setText(now)

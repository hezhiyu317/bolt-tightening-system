"""主窗口框架 — 四区布局（顶栏 / 左侧菜单 / 中央内容 / 右侧面板 / 底栏）。"""

from datetime import datetime

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.models.app_state import app_state
from src.services.camera_service import CameraService
from src.services.pcl_service import PclService
from src.services.plc_service import PlcService
from src.ui.pages.motor_control_page import MotorControlPage
from src.ui.pages.vision_page import VisionPage
from src.ui.styles import (
    BG_HEADER,
    BG_DARK,
    BG_FOOTER,
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
    RED_ALERT,
    SIDEBAR_WIDTH,
    TEXT_DIM,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from src.ui.widgets.right_panel import RightPanel


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
        self._setup_ui()
        self._start_clock()

    # ---- UI construction -----------------------------------------------------

    def _setup_ui(self):
        self.setStyleSheet(
            f"QWidget {{"
            f"  background-color: {BG_DARK};"
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
        bar = QWidget()
        bar.setFixedHeight(HEADER_HEIGHT)
        bar.setStyleSheet(
            f"background-color: {BG_HEADER};"
            f"border-bottom: 1px solid {BORDER_CARD};"
        )

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(12, 0, 12, 0)

        # 标题
        title = QLabel("过盈螺桩选配机器人控制系统")
        title.setStyleSheet(
            f"font-size: 18px; font-weight: bold; color: {TEXT_PRIMARY};"
            f"font-family: {FONT_FAMILY};"
        )
        layout.addWidget(title)

        layout.addStretch()

        # 可点击导航标签
        tabs = ["工作流", "视觉定位", "三坐标平台", "数据记录", "故障处理", "安全模式"]
        for i, tab in enumerate(tabs):
            btn = QPushButton(tab)
            btn.setFlat(True)
            btn.clicked.connect(lambda checked, idx=i: self._on_nav_clicked(idx))
            self._nav_buttons.append(btn)
            layout.addWidget(btn)

        self._set_active_nav(0)

        layout.addStretch()

        # 时间 + 用户
        self._clock_label = QLabel()
        self._clock_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-family: {FONT_MONO};"
            f"font-size: {FONT_SIZE_SM}px;"
        )
        layout.addWidget(self._clock_label)

        layout.addSpacing(16)

        user_lbl = QLabel("管理员")
        user_lbl.setStyleSheet(
            f"color: {BLUE_FUNC}; font-size: {FONT_SIZE_SM}px;"
        )
        layout.addWidget(user_lbl)

        return bar

    def _build_sidebar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedWidth(SIDEBAR_WIDTH)
        bar.setStyleSheet(f"background-color: {BG_SIDEBAR};")

        layout = QVBoxLayout(bar)
        layout.setContentsMargins(0, 8, 0, 8)
        layout.setSpacing(4)

        icons = ["工作", "监控", "记录", "故障", "报警", "安全", "设置"]
        for i, name in enumerate(icons):
            btn = QPushButton(name)
            btn.setFlat(True)
            btn.setFixedSize(48, 48)
            active = i == 0
            btn.setStyleSheet(
                f"QPushButton {{"
                f"  color: {BLUE_FUNC if active else TEXT_SECONDARY};"
                f"  font-size: 10px;"
                f"  border: none;"
                f"  border-left: 3px solid {BLUE_FUNC if active else 'transparent'};"
                f"  background-color: {'#12273D' if active else 'transparent'};"
                f"}}"
                f"QPushButton:hover {{"
                f"  background-color: #12273D;"
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
        self._central_stack.addWidget(self._build_placeholder("数据记录"))
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

    def _build_placeholder(self, name: str) -> QWidget:
        """占位页面。"""
        w = QWidget()
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

    # ---- footer signals ------------------------------------------------------

    def _connect_footer_signals(self):
        app_state.plc_online_changed.connect(self._on_footer_plc)
        app_state.camera_online_changed.connect(self._on_footer_network)

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

    # ---- clock ----------------------------------------------------------------

    def _start_clock(self):
        self._tick()
        timer = QTimer(self)
        timer.timeout.connect(self._tick)
        timer.start(1000)

    def _tick(self):
        now = datetime.now().strftime("%Y/%m/%d %H:%M:%S")
        self._clock_label.setText(now)

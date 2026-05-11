"""视觉定位页面 — 相机参数配置 + 点云采集 + 孔心检测结果。

根据 Camera_Parameters_Specification.txt 设计参数面板。
"""

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import (
    QCheckBox,
    QComboBox,
    QDoubleSpinBox,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QScrollArea,
    QSlider,
    QSpinBox,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.services.camera_service import (
    PARAM_2D_EXPOSURE_MODE,
    PARAM_2D_EXPOSURE_TIME,
    PARAM_2D_FAST_HDR,
    PARAM_2D_GAIN,
    PARAM_2D_GAMMA,
    PARAM_2D_GRAY_LOWER,
    PARAM_2D_GRAY_UPPER,
    PARAM_3D_DECODE_THRESHOLD,
    PARAM_3D_DENOISE,
    PARAM_3D_DEPTH_LOWER,
    PARAM_3D_DEPTH_UPPER,
    PARAM_3D_EDGE_PROTECTION,
    PARAM_3D_ENHANCE,
    PARAM_3D_EXPOSURE_ARRAY,
    PARAM_3D_FILTER_MODE,
    PARAM_3D_GAIN,
    PARAM_3D_HOLE_FILLING,
)
from src.services.camera_service import CameraService
from src.services.pcl_service import PclService
from src.ui.styles import (
    BG_BASE,
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
    QSS_PRIMARY_BUTTON,
    QSS_DANGER_BUTTON,
    QSS_SECONDARY_BUTTON,
)
from src.ui.widgets.status_indicator import StatusIndicator


# ---- reusable property row --------------------------------------------------

class _PropertyRow(QWidget):
    """参数行: label | value widget | unit label。"""

    def __init__(
        self,
        label: str,
        widget: QWidget,
        unit: str = "",
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 1, 0, 1)
        layout.setSpacing(6)

        lbl = QLabel(label)
        lbl.setFixedWidth(120)
        lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;"
            f"font-family: {FONT_FAMILY};"
        )
        layout.addWidget(lbl)

        layout.addWidget(widget, stretch=1)

        if unit:
            unit_lbl = QLabel(unit)
            unit_lbl.setFixedWidth(36)
            unit_lbl.setStyleSheet(
                f"color: {TEXT_DIM}; font-size: {FONT_SIZE_SM}px;"
                f"font-family: {FONT_MONO};"
            )
            layout.addWidget(unit_lbl)
        else:
            layout.addStretch()


# ---- 2D parameters widget ---------------------------------------------------

class _TwoDParamsWidget(QWidget):
    """2D 参数面板 — 曝光模式、曝光时间、增益、Gamma 等。"""

    EXPOSURE_MODES = ["FLASH", "IMMUTABLE", "IN_SCAN", "IN_SCAN_HDR"]

    def __init__(self, camera: CameraService, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._camera = camera
        self._rows: dict = {}
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # 图像分辨率（只读）
        res_row = QHBoxLayout()
        res_row.setContentsMargins(0, 1, 0, 1)
        res_row.setSpacing(6)
        res_label = QLabel("图像分辨率")
        res_label.setFixedWidth(120)
        res_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;"
        )
        res_row.addWidget(res_label)
        res_value = QLabel("1920 × 1200")
        res_value.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-family: {FONT_MONO};"
            f"font-size: {FONT_SIZE_SM}px;"
        )
        res_row.addWidget(res_value)
        res_row.addStretch()
        layout.addLayout(res_row)

        # 曝光模式
        mode_combo = QComboBox()
        mode_combo.addItems(self.EXPOSURE_MODES)
        mode_combo.setStyleSheet(self._combo_style())
        mode_combo.currentTextChanged.connect(self._on_mode_changed)
        row = _PropertyRow("曝光模式", mode_combo)
        layout.addWidget(row)
        self._rows["exposure_mode"] = mode_combo

        # 曝光时间
        exp_spin = QSpinBox()
        exp_spin.setRange(2000, 40000)
        exp_spin.setSingleStep(100)
        exp_spin.setStyleSheet(self._spin_style())
        exp_spin.valueChanged.connect(self._on_exposure_time_changed)
        row = _PropertyRow("曝光时间", exp_spin, "us")
        layout.addWidget(row)
        self._rows["exposure_time"] = exp_spin

        # 增益
        gain_spin = QSpinBox()
        gain_spin.setRange(1, 100)
        gain_spin.setStyleSheet(self._spin_style())
        gain_spin.valueChanged.connect(
            lambda v: self._camera.write_int_param(PARAM_2D_GAIN, v)
        )
        row = _PropertyRow("增益 (Gain)", gain_spin, "dB")
        layout.addWidget(row)
        self._rows["gain"] = gain_spin

        # Gamma
        gamma_spin = QDoubleSpinBox()
        gamma_spin.setRange(0.10, 5.00)
        gamma_spin.setSingleStep(0.05)
        gamma_spin.setDecimals(2)
        gamma_spin.setStyleSheet(self._spin_style())
        gamma_spin.valueChanged.connect(
            lambda v: self._camera.write_float_param(PARAM_2D_GAMMA, v)
        )
        row = _PropertyRow("Gamma", gamma_spin)
        layout.addWidget(row)
        self._rows["gamma"] = gamma_spin

        # 灰度范围
        gray_lower = QSpinBox()
        gray_lower.setRange(0, 254)
        gray_lower.setStyleSheet(self._spin_style())
        gray_lower.valueChanged.connect(
            lambda v: self._camera.write_int_param(PARAM_2D_GRAY_LOWER, v)
        )
        gray_upper = QSpinBox()
        gray_upper.setRange(1, 255)
        gray_upper.setValue(255)
        gray_upper.setStyleSheet(self._spin_style())
        gray_upper.valueChanged.connect(
            lambda v: self._camera.write_int_param(PARAM_2D_GRAY_UPPER, v)
        )
        gray_row = QHBoxLayout()
        gray_row.setContentsMargins(120, 1, 0, 1)
        gray_row.setSpacing(4)
        gray_label = QLabel("灰度范围")
        gray_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;"
        )
        gray_row.addWidget(gray_label)
        gray_row.addWidget(gray_lower)
        sep = QLabel("—")
        sep.setFixedWidth(20)
        sep.setAlignment(Qt.AlignCenter)
        sep.setStyleSheet(f"color: {TEXT_DIM};")
        gray_row.addWidget(sep)
        gray_row.addWidget(gray_upper)
        gray_row.addStretch()
        layout.addLayout(gray_row)
        self._rows["gray_lower"] = gray_lower
        self._rows["gray_upper"] = gray_upper

        # 快速 HDR
        hdr_check = QCheckBox()
        hdr_check.setStyleSheet(self._check_style())
        hdr_check.toggled.connect(
            lambda v: self._camera.write_bool_param(PARAM_2D_FAST_HDR, v)
        )
        row = _PropertyRow("快速 HDR", hdr_check)
        layout.addWidget(row)
        self._rows["fast_hdr"] = hdr_check

        layout.addStretch()

    def _on_mode_changed(self, text: str):
        self._camera.write_enum_param(PARAM_2D_EXPOSURE_MODE, text)

    def _on_exposure_time_changed(self, value: int):
        self._camera.write_int_param(PARAM_2D_EXPOSURE_TIME, value)

    # ---- style helpers -------------------------------------------------------

    @staticmethod
    def _combo_style() -> str:
        return (
            f"QComboBox {{"
            f"  background-color: #FAFBFC;"
            f"  color: {TEXT_PRIMARY};"
            f"  border: 1px solid {BORDER_CARD};"
            f"  border-radius: 3px;"
            f"  padding: 2px 6px;"
            f"  font-family: {FONT_MONO};"
            f"  font-size: {FONT_SIZE_SM}px;"
            f"}}"
            f"QComboBox:hover {{ border-color: {BLUE_FUNC}; }}"
            f"QComboBox QAbstractItemView {{"
            f"  background-color: #FAFBFC;"
            f"  color: {TEXT_PRIMARY};"
            f"  selection-background-color: {BLUE_FUNC};"
            f"}}"
        )

    @staticmethod
    def _spin_style() -> str:
        return (
            f"QSpinBox, QDoubleSpinBox {{"
            f"  background-color: #FAFBFC;"
            f"  color: {TEXT_PRIMARY};"
            f"  border: 1px solid {BORDER_CARD};"
            f"  border-radius: 3px;"
            f"  padding: 2px 4px;"
            f"  font-family: {FONT_MONO};"
            f"  font-size: {FONT_SIZE_SM}px;"
            f"}}"
            f"QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {BLUE_FUNC}; }}"
            f"QSpinBox:focus, QDoubleSpinBox:focus {{ border-color: {BLUE_FUNC}; }}"
        )

    @staticmethod
    def _check_style() -> str:
        return (
            f"QCheckBox {{"
            f"  spacing: 0px;"
            f"}}"
            f"QCheckBox::indicator {{"
            f"  width: 16px; height: 16px;"
            f"  border: 1px solid {BORDER_CARD};"
            f"  border-radius: 3px;"
            f"  background-color: #FAFBFC;"
            f"}}"
            f"QCheckBox::indicator:checked {{"
            f"  background-color: {BLUE_FUNC};"
            f"  border-color: {BLUE_FUNC};"
            f"}}"
        )


# ---- 3D parameters widget ---------------------------------------------------

class _ThreeDParamsWidget(QWidget):
    """3D 参数面板 — 多重曝光、增益、增强、去噪、孔洞填充、滤波、深度范围等。"""

    FILTER_MODES = ["OFF", "LOW", "MEDIUM", "HIGH", "EXTREMELY_HIGH"]

    def __init__(self, camera: CameraService, parent: Optional[QWidget] = None):
        super().__init__(parent)
        self._camera = camera
        self._rows: dict = {}
        self._exposure_container: Optional[QVBoxLayout] = None
        self._setup_ui()

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(8, 8, 8, 8)
        layout.setSpacing(4)

        # ---- 多重曝光 ----
        exp_label = QLabel("多重曝光时间")
        exp_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;"
            f"font-weight: bold; margin-top: 4px;"
        )
        layout.addWidget(exp_label)

        self._exposure_container = QVBoxLayout()
        self._exposure_container.setContentsMargins(0, 0, 0, 0)
        self._exposure_container.setSpacing(2)
        layout.addLayout(self._exposure_container)

        # 两个固定曝光时间输入口（从 config 读取默认值）
        try:
            from src.utils.config_manager import config as cfg
            exp_vals = cfg.get("system.camera.default_parameters.3d.exposure_time_array", [20000, 6000])
        except Exception:
            exp_vals = [20000, 6000]
        self._rows["exp0"] = self._build_exposure_row(0, exp_vals[0] if len(exp_vals) > 0 else 20000)
        self._rows["exp1"] = self._build_exposure_row(1, exp_vals[1] if len(exp_vals) > 1 else 6000)

        # ---- 增益 ----
        gain_spin = QSpinBox()
        gain_spin.setRange(1, 36)
        gain_spin.setStyleSheet(_TwoDParamsWidget._spin_style())
        gain_spin.valueChanged.connect(
            lambda v: self._camera.write_int_param(PARAM_3D_GAIN, v)
        )
        row = _PropertyRow("增益 (Gain)", gain_spin, "dB")
        layout.addWidget(row)
        self._rows["gain"] = gain_spin

        # ---- 增强模式 ----
        enhance_check = QCheckBox()
        enhance_check.setStyleSheet(_TwoDParamsWidget._check_style())
        enhance_check.toggled.connect(
            lambda v: self._camera.write_bool_param(PARAM_3D_ENHANCE, v)
        )
        row = _PropertyRow("增强模式", enhance_check)
        layout.addWidget(row)
        self._rows["enhance_mode"] = enhance_check

        # ---- 点云去噪 ----
        denoise_check = QCheckBox()
        denoise_check.setStyleSheet(_TwoDParamsWidget._check_style())
        denoise_check.toggled.connect(
            lambda v: self._camera.write_bool_param(PARAM_3D_DENOISE, v)
        )
        row = _PropertyRow("点云去噪", denoise_check)
        layout.addWidget(row)
        self._rows["denoise_mode"] = denoise_check

        # ---- 孔洞填充 ----
        hole_layout = QHBoxLayout()
        hole_layout.setContentsMargins(0, 1, 0, 1)
        hole_layout.setSpacing(6)
        hole_label = QLabel("孔洞填充")
        hole_label.setFixedWidth(120)
        hole_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;"
        )
        hole_layout.addWidget(hole_label)

        hole_slider = QSlider(Qt.Horizontal)
        hole_slider.setRange(0, 10)
        hole_slider.setStyleSheet(self._slider_style())
        hole_slider.valueChanged.connect(self._on_hole_filling_slider)
        hole_layout.addWidget(hole_slider, stretch=1)

        hole_spin = QSpinBox()
        hole_spin.setRange(0, 10)
        hole_spin.setFixedWidth(48)
        hole_spin.setStyleSheet(_TwoDParamsWidget._spin_style())
        hole_spin.valueChanged.connect(self._on_hole_filling_spin)
        hole_layout.addWidget(hole_spin)

        layout.addLayout(hole_layout)
        self._rows["hole_slider"] = hole_slider
        self._rows["hole_spin"] = hole_spin

        # ---- 滤波模式 ----
        filter_combo = QComboBox()
        filter_combo.addItems(self.FILTER_MODES)
        filter_combo.setStyleSheet(_TwoDParamsWidget._combo_style())
        filter_combo.currentTextChanged.connect(
            lambda v: self._camera.write_enum_param(PARAM_3D_FILTER_MODE, v)
        )
        row = _PropertyRow("滤波模式", filter_combo)
        layout.addWidget(row)
        self._rows["filter_mode"] = filter_combo

        # ---- 边缘保护 ----
        edge_check = QCheckBox()
        edge_check.setStyleSheet(_TwoDParamsWidget._check_style())
        edge_check.toggled.connect(
            lambda v: self._camera.write_bool_param(PARAM_3D_EDGE_PROTECTION, v)
        )
        row = _PropertyRow("边缘保护", edge_check)
        layout.addWidget(row)
        self._rows["edge_protection"] = edge_check

        # ---- 解码阈值 ----
        decode_spin = QSpinBox()
        decode_spin.setRange(1, 32)
        decode_spin.setStyleSheet(_TwoDParamsWidget._spin_style())
        decode_spin.valueChanged.connect(
            lambda v: self._camera.write_int_param(PARAM_3D_DECODE_THRESHOLD, v)
        )
        row = _PropertyRow("解码阈值", decode_spin)
        layout.addWidget(row)
        self._rows["decode_threshold"] = decode_spin

        # ---- 深度测量范围 ----
        depth_label = QLabel("深度测量范围")
        depth_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;"
            f"font-weight: bold; margin-top: 6px;"
        )
        layout.addWidget(depth_label)

        depth_row = QHBoxLayout()
        depth_row.setContentsMargins(0, 1, 0, 1)
        depth_row.setSpacing(6)

        depth_lower_spin = QSpinBox()
        depth_lower_spin.setRange(50, 349)
        depth_lower_spin.setValue(200)
        depth_lower_spin.setSuffix(" mm")
        depth_lower_spin.setStyleSheet(_TwoDParamsWidget._spin_style())
        depth_lower_spin.valueChanged.connect(self._on_depth_lower_changed)
        depth_row.addWidget(QLabel("下限"))
        depth_row.addWidget(depth_lower_spin)

        depth_upper_spin = QSpinBox()
        depth_upper_spin.setRange(251, 1000)
        depth_upper_spin.setValue(300)
        depth_upper_spin.setSuffix(" mm")
        depth_upper_spin.setStyleSheet(_TwoDParamsWidget._spin_style())
        depth_upper_spin.valueChanged.connect(self._on_depth_upper_changed)
        depth_row.addWidget(QLabel("上限"))
        depth_row.addWidget(depth_upper_spin)
        depth_row.addStretch()

        layout.addLayout(depth_row)
        self._rows["depth_lower"] = depth_lower_spin
        self._rows["depth_upper"] = depth_upper_spin

        layout.addStretch()

    # ---- multi-exposure (2-fixed) --------------------------------------------

    def _build_exposure_row(self, index: int, value: int):
        """构建单个曝光时间输入行。"""
        row_layout = QHBoxLayout()
        row_layout.setSpacing(4)

        idx_label = QLabel(f"第{index + 1}重")
        idx_label.setFixedWidth(50)
        idx_label.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: {FONT_SIZE_SM}px;"
        )
        row_layout.addWidget(idx_label)

        spin = QSpinBox()
        spin.setRange(1000, 100000)
        spin.setSingleStep(1000)
        spin.setValue(value)
        spin.setStyleSheet(_TwoDParamsWidget._spin_style())
        spin.valueChanged.connect(
            lambda v, idx=index: self._camera.write_int_param(
                f"{PARAM_3D_EXPOSURE_ARRAY}[{idx}]", v)
        )
        row_layout.addWidget(spin, stretch=1)

        unit = QLabel("us")
        unit.setStyleSheet(f"color: {TEXT_DIM}; font-size: {FONT_SIZE_SM}px;")
        row_layout.addWidget(unit)

        self._exposure_container.addLayout(row_layout)
        return spin

    # ---- hole filling sync ---------------------------------------------------

    def _on_hole_filling_slider(self, value: int):
        spin = self._rows.get("hole_spin")
        if spin:
            spin.blockSignals(True)
            spin.setValue(value)
            spin.blockSignals(False)
        self._camera.write_int_param(PARAM_3D_HOLE_FILLING, value)

    def _on_hole_filling_spin(self, value: int):
        slider = self._rows.get("hole_slider")
        if slider:
            slider.blockSignals(True)
            slider.setValue(value)
            slider.blockSignals(False)
        self._camera.write_int_param(PARAM_3D_HOLE_FILLING, value)

    # ---- depth range sync ----------------------------------------------------

    def _on_depth_lower_changed(self, value: int):
        upper = self._rows.get("depth_upper")
        if upper and value >= upper.value():
            upper.blockSignals(True)
            upper.setValue(value + 1)
            upper.blockSignals(False)
        self._camera.write_int_param(PARAM_3D_DEPTH_LOWER, value)

    def _on_depth_upper_changed(self, value: int):
        lower = self._rows.get("depth_lower")
        if lower and value <= lower.value():
            lower.blockSignals(True)
            lower.setValue(value - 1)
            lower.blockSignals(False)
        self._camera.write_int_param(PARAM_3D_DEPTH_UPPER, value)

    # ---- style helpers -------------------------------------------------------

    @staticmethod
    def _slider_style() -> str:
        return (
            f"QSlider::groove:horizontal {{"
            f"  height: 6px;"
            f"  background-color: #FAFBFC;"
            f"  border: 1px solid {BORDER_CARD};"
            f"  border-radius: 3px;"
            f"}}"
            f"QSlider::handle:horizontal {{"
            f"  width: 14px;"
            f"  margin: -4px 0;"
            f"  background-color: {BLUE_FUNC};"
            f"  border-radius: 7px;"
            f"}}"
        )


# ---- main vision page -------------------------------------------------------

class VisionPage(QWidget):
    """视觉定位页面 — 参数配置 + 采集控制 + 孔心检测结果。"""

    def __init__(
        self,
        camera_service: CameraService,
        pcl_service: Optional[PclService] = None,
        parent: Optional[QWidget] = None,
    ):
        super().__init__(parent)
        self._camera = camera_service
        self._pcl = pcl_service

        self._status_indicator: Optional[StatusIndicator] = None
        self._ip_label: Optional[QLabel] = None
        self._btn_connect: Optional[QPushButton] = None
        self._btn_capture: Optional[QPushButton] = None
        self._result_table: Optional[QTableWidget] = None
        self._status_label: Optional[QLabel] = None
        self._tab_2d: Optional[_TwoDParamsWidget] = None
        self._tab_3d: Optional[_ThreeDParamsWidget] = None
        self._hint_label: Optional[QLabel] = None
        self._scroll_2d: Optional[QScrollArea] = None
        self._scroll_3d: Optional[QScrollArea] = None

        self._setup_ui()
        self._wire_signals()
        self._set_controls_enabled(self._camera.is_connected)

    # ---- UI construction -----------------------------------------------------

    def _setup_ui(self):
        root = QVBoxLayout(self)
        root.setContentsMargins(12, 8, 12, 8)
        root.setSpacing(8)

        # ---- 状态栏 ----
        root.addWidget(self._build_status_bar())

        # ---- 主内容 ----
        body = QHBoxLayout()
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(8)

        # 左侧: 参数配置
        body.addWidget(self._build_params_panel(), stretch=3)

        # 右侧: 采集与结果
        body.addWidget(self._build_result_panel(), stretch=1)

        root.addLayout(body, stretch=1)

    def _build_status_bar(self) -> QWidget:
        bar = QWidget()
        bar.setFixedHeight(40)
        bar.setStyleSheet(self._bar_style())

        layout = QHBoxLayout(bar)
        layout.setContentsMargins(8, 0, 8, 0)
        layout.setSpacing(8)

        self._status_indicator = StatusIndicator("offline", size=8)
        layout.addWidget(self._status_indicator)

        self._ip_label = QLabel("相机未连接")
        self._ip_label.setStyleSheet(
            f"color: {TEXT_DIM}; font-family: {FONT_MONO};"
            f"font-size: {FONT_SIZE_SM}px;"
        )
        layout.addWidget(self._ip_label)

        layout.addStretch()

        btn_discover = QPushButton("发现相机")
        btn_discover.setStyleSheet(QSS_SECONDARY_BUTTON)
        btn_discover.clicked.connect(self._on_discover)
        layout.addWidget(btn_discover)

        self._btn_connect = QPushButton("连接相机")
        self._btn_connect.setStyleSheet(QSS_PRIMARY_BUTTON)
        self._btn_connect.clicked.connect(self._on_connect)
        layout.addWidget(self._btn_connect)

        btn_reset = QPushButton("加载默认参数")
        btn_reset.setStyleSheet(QSS_SECONDARY_BUTTON)
        btn_reset.clicked.connect(self._on_reset_defaults)
        layout.addWidget(btn_reset)

        return bar

    def _build_params_panel(self) -> QWidget:
        group = QGroupBox("参数配置")
        group.setStyleSheet(self._card_style())

        layout = QVBoxLayout(group)
        layout.setContentsMargins(4, 12, 4, 4)
        layout.setSpacing(0)

        # 未连接提示
        self._hint_label = QLabel("相机未连接 — 请先点击「连接相机」以解锁参数")
        self._hint_label.setAlignment(Qt.AlignCenter)
        self._hint_label.setStyleSheet(
            f"color: {TEXT_DIM}; font-size: {FONT_SIZE_SM}px;"
            f"padding: 8px; border: 1px dashed {BORDER_CARD};"
            f"border-radius: 4px; margin-bottom: 4px;"
        )
        self._hint_label.setVisible(True)
        layout.addWidget(self._hint_label)

        self._params_tabs = QTabWidget()
        self._params_tabs.setStyleSheet(self._tab_style())

        # 2D 参数 tab
        scroll_2d = QScrollArea()
        scroll_2d.setWidgetResizable(True)
        scroll_2d.setStyleSheet(
            f"QScrollArea {{ border: none; background-color: transparent; }}"
        )
        self._scroll_2d = scroll_2d
        self._tab_2d = _TwoDParamsWidget(self._camera)
        scroll_2d.setWidget(self._tab_2d)
        self._params_tabs.addTab(scroll_2d, "2D 参数")

        # 3D 参数 tab
        scroll_3d = QScrollArea()
        scroll_3d.setWidgetResizable(True)
        scroll_3d.setStyleSheet(
            f"QScrollArea {{ border: none; background-color: transparent; }}"
        )
        self._scroll_3d = scroll_3d
        self._tab_3d = _ThreeDParamsWidget(self._camera)
        scroll_3d.setWidget(self._tab_3d)
        self._params_tabs.addTab(scroll_3d, "3D 参数")

        layout.addWidget(self._params_tabs)
        return group

    def _build_result_panel(self) -> QWidget:
        group = QGroupBox("采集与结果")
        group.setStyleSheet(self._card_style())
        group.setFixedWidth(320)

        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(8)

        self._btn_capture = QPushButton("单次采集点云")
        self._btn_capture.setStyleSheet(QSS_PRIMARY_BUTTON)
        self._btn_capture.clicked.connect(self._on_capture)
        layout.addWidget(self._btn_capture)

        self._status_label = QLabel("点云状态: 就绪")
        self._status_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;"
        )
        layout.addWidget(self._status_label)

        # 孔心检测结果表格
        table_label = QLabel("孔心检测结果")
        table_label.setStyleSheet(
            f"color: {BLUE_FUNC}; font-size: {FONT_SIZE_SM}px;"
            f"font-weight: bold; margin-top: 4px;"
        )
        layout.addWidget(table_label)

        self._result_table = QTableWidget(0, 4)
        self._result_table.setHorizontalHeaderLabels(["X (mm)", "Y (mm)", "Z (mm)", "R (mm)"])
        self._result_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.Stretch
        )
        self._result_table.setEditTriggers(
            QTableWidget.NoEditTriggers
        )
        self._result_table.setSelectionBehavior(
            QTableWidget.SelectRows
        )
        self._result_table.setStyleSheet(
            f"QTableWidget {{"
            f"  background-color: #FFFFFF;"
            f"  color: {TEXT_PRIMARY};"
            f"  border: 1px solid {BORDER_CARD};"
            f"  border-radius: 4px;"
            f"  gridline-color: {BORDER_CARD};"
            f"  font-family: {FONT_MONO};"
            f"  font-size: {FONT_SIZE_SM}px;"
            f"}}"
            f"QTableWidget::item {{ padding: 4px; }}"
            f"QHeaderView::section {{"
            f"  background-color: {BG_PANEL};"
            f"  color: {TEXT_SECONDARY};"
            f"  border: none;"
            f"  padding: 4px;"
            f"  font-family: {FONT_FAMILY};"
            f"}}"
        )
        layout.addWidget(self._result_table)

        layout.addStretch()
        return group

    # ---- signal wiring -------------------------------------------------------

    def _wire_signals(self):
        self._camera.connection_status.connect(self._on_connection_changed)
        self._camera.camera_discovered.connect(self._on_camera_discovered)
        self._camera.camera_params_changed.connect(self._on_param_changed)
        self._camera.point_cloud_grabbed.connect(self._on_point_cloud_ready)
        self._camera.error_occurred.connect(self._on_camera_error)
        self._camera.client_disconnected.connect(self._on_client_disconnected)

        if self._pcl:
            self._pcl.processing_finished.connect(self._on_pcl_result)
            self._pcl.processing_error.connect(self._on_pcl_error)

    # ---- slot callbacks ------------------------------------------------------

    def _on_connection_changed(self, connected: bool, msg: str):
        self._status_indicator.set_status("online" if connected else "offline")
        self._set_controls_enabled(connected)
        if connected:
            self._btn_connect.setText("断开相机")
            self._btn_connect.setStyleSheet(QSS_DANGER_BUTTON)
            self._ip_label.setText(self._camera.camera_ip)
            self._ip_label.setStyleSheet(
                f"color: {GREEN_STATUS}; font-family: {FONT_MONO};"
                f"font-size: {FONT_SIZE_SM}px;"
            )
            self._btn_capture.setEnabled(True)
            self._btn_capture.setStyleSheet(QSS_PRIMARY_BUTTON)
            # 加载默认值到 UI
            self._load_defaults_to_ui()
        else:
            self._btn_connect.setText("连接相机")
            self._btn_connect.setStyleSheet(QSS_PRIMARY_BUTTON)
            self._ip_label.setText(msg if msg else "相机未连接")
            self._ip_label.setStyleSheet(
                f"color: {TEXT_DIM}; font-family: {FONT_MONO};"
                f"font-size: {FONT_SIZE_SM}px;"
            )
            self._btn_capture.setEnabled(False)
            self._btn_capture.setStyleSheet(QSS_SECONDARY_BUTTON)

    def _on_camera_discovered(self, server_list: list):
        if server_list:
            info = server_list[0]
            self._ip_label.setText(f"发现设备: {info.get('ip', '?')}")
            self._ip_label.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-family: {FONT_MONO};"
                f"font-size: {FONT_SIZE_SM}px;"
            )

    def _on_param_changed(self, path: str, value: object):
        # 参数变更反馈（日志/状态），UI 已由控件自身更新
        pass

    def _on_point_cloud_ready(self, path: str):
        self._status_label.setText(f"点云已采集: {path}")
        self._status_label.setStyleSheet(
            f"color: {GREEN_STATUS}; font-size: {FONT_SIZE_SM}px;"
        )

    def _on_camera_error(self, msg: str):
        self._status_label.setText(f"错误: {msg}")
        self._status_label.setStyleSheet(
            f"color: {RED_ALERT}; font-size: {FONT_SIZE_SM}px;"
        )

    def _on_client_disconnected(self, reason: str):
        self._status_indicator.set_status("offline")
        self._ip_label.setText(reason)
        self._ip_label.setStyleSheet(
            f"color: {RED_ALERT}; font-family: {FONT_MONO};"
            f"font-size: {FONT_SIZE_SM}px;"
        )
        self._set_controls_enabled(False)

    def _on_pcl_result(self, result: dict):
        centers = result.get("centers", [])
        self._result_table.setRowCount(0)
        if not centers:
            self._status_label.setText("未检测到孔心 (圆心过滤)")
            self._status_label.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;"
            )
            return

        for c in centers:
            row = self._result_table.rowCount()
            self._result_table.insertRow(row)
            self._result_table.setItem(row, 0, QTableWidgetItem(f"{c.get('x', 0):.2f}"))
            self._result_table.setItem(row, 1, QTableWidgetItem(f"{c.get('y', 0):.2f}"))
            self._result_table.setItem(row, 2, QTableWidgetItem(f"{c.get('z', 0):.2f}"))
            self._result_table.setItem(row, 3, QTableWidgetItem(f"{c.get('radius', 0):.2f}"))

        self._status_label.setText(f"检测到 {len(centers)} 个孔心")
        self._status_label.setStyleSheet(
            f"color: {GREEN_STATUS}; font-size: {FONT_SIZE_SM}px;"
        )

    def _on_pcl_error(self, msg: str):
        self._status_label.setText(f"PCL 处理失败: {msg}")
        self._status_label.setStyleSheet(
            f"color: {RED_ALERT}; font-size: {FONT_SIZE_SM}px;"
        )

    # ---- button handlers -----------------------------------------------------

    def _on_discover(self):
        self._camera.discover_camera()

    def _on_connect(self):
        if self._camera.is_connected:
            self._camera.disconnect_camera()
        else:
            self._camera.connect_camera()

    def _on_capture(self):
        if self._camera:
            self._status_label.setText("点云状态: 采集中...")
            self._status_label.setStyleSheet(
                f"color: {BLUE_FUNC}; font-size: {FONT_SIZE_SM}px;"
            )
            self._camera.trigger_3d_capture()

    def _on_reset_defaults(self):
        self._camera.apply_default_parameters()
        self._load_defaults_to_ui()

    # ---- helpers -------------------------------------------------------------

    def _load_defaults_to_ui(self):
        """将 system.yaml 中的默认参数加载到 UI 控件。"""
        from src.utils.config_manager import config as cfg

        params_2d = cfg.get("system.camera.default_parameters.2d", {})
        if self._tab_2d and self._tab_2d._rows:
            rows = self._tab_2d._rows
            if "exposure_mode" in rows:
                mode = params_2d.get("exposure_mode", "FLASH")
                idx = rows["exposure_mode"].findText(mode)
                if idx >= 0:
                    rows["exposure_mode"].setCurrentIndex(idx)
            if "exposure_time" in rows:
                rows["exposure_time"].setValue(
                    params_2d.get("exposure_time", 5000))
            if "gain" in rows:
                rows["gain"].setValue(params_2d.get("gain", 1))
            if "gamma" in rows:
                rows["gamma"].setValue(params_2d.get("gamma", 1.0))
            if "fast_hdr" in rows:
                rows["fast_hdr"].setChecked(params_2d.get("fast_hdr", False))
            if "gray_lower" in rows:
                rows["gray_lower"].setValue(params_2d.get("gray_value_lower", 0))
            if "gray_upper" in rows:
                rows["gray_upper"].setValue(params_2d.get("gray_value_upper", 255))

        params_3d = cfg.get("system.camera.default_parameters.3d", {})
        if self._tab_3d and self._tab_3d._rows:
            rows = self._tab_3d._rows
            if "gain" in rows:
                rows["gain"].setValue(params_3d.get("gain", 1))
            if "enhance_mode" in rows:
                rows["enhance_mode"].setChecked(
                    params_3d.get("enhance_mode", True))
            if "denoise_mode" in rows:
                rows["denoise_mode"].setChecked(
                    params_3d.get("denoise_mode", True))
            if "hole_spin" in rows:
                rows["hole_spin"].setValue(params_3d.get("hole_filling", 0))
            if "filter_mode" in rows:
                fmode = params_3d.get("filter_mode", "HIGH")
                idx = rows["filter_mode"].findText(fmode)
                if idx >= 0:
                    rows["filter_mode"].setCurrentIndex(idx)
            if "edge_protection" in rows:
                rows["edge_protection"].setChecked(
                    params_3d.get("edge_protection", True))
            if "decode_threshold" in rows:
                rows["decode_threshold"].setValue(
                    params_3d.get("decode_threshold", 8))
            if "depth_lower" in rows:
                rows["depth_lower"].setValue(
                    params_3d.get("depth_range_lower", 250))
            if "depth_upper" in rows:
                rows["depth_upper"].setValue(
                    params_3d.get("depth_range_upper", 350))
            # 曝光数组 — 直接更新两个固定输入框
            exp_array = params_3d.get("exposure_time_array", [20000, 6000])
            rows3d = self._tab_3d._rows
            if "exp0" in rows3d:
                rows3d["exp0"].setValue(exp_array[0] if len(exp_array) > 0 else 20000)
            if "exp1" in rows3d:
                rows3d["exp1"].setValue(exp_array[1] if len(exp_array) > 1 else 6000)

        self._status_label.setText("默认参数已加载")
        self._status_label.setStyleSheet(
            f"color: {GREEN_STATUS}; font-size: {FONT_SIZE_SM}px;"
        )

    def _set_controls_enabled(self, enabled: bool):
        """启用/禁用参数控件。"""
        if self._btn_capture:
            self._btn_capture.setEnabled(enabled)
        # 通过禁用 scroll area 来批量禁用所有参数控件
        if hasattr(self, "_scroll_2d") and self._scroll_2d:
            self._scroll_2d.setEnabled(enabled)
        if hasattr(self, "_scroll_3d") and self._scroll_3d:
            self._scroll_3d.setEnabled(enabled)
        # 显示/隐藏提示
        if hasattr(self, "_hint_label") and self._hint_label:
            self._hint_label.setVisible(not enabled)

    # ---- style helpers -------------------------------------------------------

    @staticmethod
    def _bar_style() -> str:
        return (
            f"background-color: {BG_PANEL};"
            f"border: 1px solid {BORDER_CARD};"
            f"border-radius: {CARD_RADIUS}px;"
        )

    @staticmethod
    def _card_style() -> str:
        return (
            f"QGroupBox {{"
            f"  background-color: {BG_PANEL};"
            f"  border: 1px solid {BORDER_CARD};"
            f"  border-radius: {CARD_RADIUS}px;"
            f"  margin-top: 12px;"
            f"  padding-top: 8px;"
            f"  font-family: {FONT_FAMILY};"
            f"  font-size: {FONT_SIZE_SM}px;"
            f"  color: {TEXT_PRIMARY};"
            f"}}"
            f"QGroupBox::title {{"
            f"  subcontrol-origin: margin;"
            f"  left: 10px;"
            f"  padding: 0 4px;"
            f"  color: {BLUE_FUNC};"
            f"}}"
        )

    @staticmethod
    def _tab_style() -> str:
        return (
            f"QTabWidget::pane {{"
            f"  border: 1px solid {BORDER_CARD};"
            f"  border-radius: 4px;"
            f"  background-color: {BG_PANEL};"
            f"}}"
            f"QTabBar::tab {{"
            f"  background-color: #FAFBFC;"
            f"  color: {TEXT_SECONDARY};"
            f"  border: 1px solid {BORDER_CARD};"
            f"  padding: 6px 16px;"
            f"  font-family: {FONT_FAMILY};"
            f"  font-size: {FONT_SIZE_SM}px;"
            f"}}"
            f"QTabBar::tab:selected {{"
            f"  background-color: {BG_PANEL};"
            f"  color: {BLUE_FUNC};"
            f"  border-bottom: 2px solid {BLUE_FUNC};"
            f"}}"
            f"QTabBar::tab:hover {{ color: {BLUE_FUNC}; }}"
        )

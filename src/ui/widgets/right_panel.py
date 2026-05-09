"""右侧固定面板 — 仪表盘 + 相机按钮 + 实时画面。

始终可见，宽约 1/3 窗口。
"""

from typing import Optional

from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPixmap
from PyQt5.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.models.app_state import app_state
from src.services.camera_service import CameraService
from src.services.pcl_service import PclService
from src.ui.styles import (
    BG_DARK,
    BG_PANEL,
    BLUE_FUNC,
    BORDER_CARD,
    CARD_RADIUS,
    FONT_FAMILY,
    FONT_MONO,
    FONT_SIZE_SM,
    GREEN_STATUS,
    QSS_DANGER_BUTTON,
    QSS_PRIMARY_BUTTON,
    QSS_SECONDARY_BUTTON,
    RED_ALERT,
    TEXT_DIM,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from src.ui.widgets.status_indicator import StatusIndicator


class RightPanel(QWidget):
    """右侧固定面板。

    绑定 CameraService / PclService 实例信号，订阅 app_state 实时更新。
    """

    def __init__(
        self,
        camera_service: CameraService = None,
        pcl_service: PclService = None,
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self._camera = camera_service
        self._pcl = pcl_service
        self.setFixedWidth(340)

        self._setup_ui()
        self._connect_signals()
        self._refresh_dashboard()

    # ---- UI construction -----------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(6, 6, 6, 6)
        layout.setSpacing(6)

        # [仪表盘]
        self._dash_group = self._build_dashboard()
        layout.addWidget(self._dash_group)

        # [相机按钮]
        self._btn_layout = QHBoxLayout()
        self._btn_layout.setSpacing(6)

        self._btn_connect = QPushButton("连接相机")
        self._btn_connect.setStyleSheet(QSS_PRIMARY_BUTTON)
        self._btn_connect.clicked.connect(self._on_connect)

        self._btn_capture = QPushButton("拍摄")
        self._btn_capture.setStyleSheet(QSS_SECONDARY_BUTTON)
        self._btn_capture.setEnabled(False)
        self._btn_capture.clicked.connect(self._on_capture)

        self._btn_process = QPushButton("计算")
        self._btn_process.setStyleSheet(QSS_SECONDARY_BUTTON)
        self._btn_process.setEnabled(False)
        self._btn_process.clicked.connect(self._on_process)

        self._btn_layout.addWidget(self._btn_connect)
        self._btn_layout.addWidget(self._btn_capture)
        self._btn_layout.addWidget(self._btn_process)
        layout.addLayout(self._btn_layout)

        # [相机画面]
        self._camera_view = QLabel("相机未连接")
        self._camera_view.setAlignment(Qt.AlignCenter)
        self._camera_view.setMinimumHeight(200)
        self._camera_view.setStyleSheet(
            f"background-color: {BG_DARK};"
            f"border: 1px solid {BORDER_CARD};"
            f"border-radius: 4px;"
            f"color: {TEXT_DIM};"
            f"font-family: {FONT_FAMILY};"
        )
        layout.addWidget(self._camera_view, stretch=1)

        self.setStyleSheet(
            f"QWidget {{ background-color: {BG_PANEL}; }}"
        )

    def _build_dashboard(self) -> QGroupBox:
        """构建仪表盘区域。"""
        group = QGroupBox("系统状态")
        group.setStyleSheet(self._card_style())

        layout = QVBoxLayout(group)
        layout.setContentsMargins(8, 12, 8, 8)
        layout.setSpacing(4)

        # PLC 状态行
        self._plc_indicator = StatusIndicator("offline", size=8)
        self._plc_label = QLabel("PLC: --")
        self._camera_indicator = StatusIndicator("offline", size=8)
        self._camera_label = QLabel("相机: --")
        row1 = QHBoxLayout()
        row1.addWidget(self._plc_indicator)
        row1.addWidget(self._plc_label)
        row1.addStretch()
        row1.addWidget(self._camera_indicator)
        row1.addWidget(self._camera_label)
        layout.addLayout(row1)

        # 急停
        self._estop_btn = QPushButton("急 停")
        self._estop_btn.setStyleSheet(
            f"QPushButton {{"
            f"  background-color: {RED_ALERT};"
            f"  color: #FFFFFF;"
            f"  font-size: 18px; font-weight: bold;"
            f"  border: none; border-radius: 4px;"
            f"  padding: 8px;"
            f"}}"
            f"QPushButton:hover {{ background-color: #FF6666; }}"
            f"QPushButton:checked {{ background-color: #CC0000; }}"
        )
        self._estop_btn.setCheckable(True)
        self._estop_btn.clicked.connect(self._on_estop)
        layout.addWidget(self._estop_btn)

        # 小龙门坐标
        layout.addWidget(self._section_label("小龙门坐标"))
        self._small_x = self._coord_row("X")
        self._small_y = self._coord_row("Y")
        self._small_z = self._coord_row("Z")
        layout.addLayout(self._small_x)
        layout.addLayout(self._small_y)
        layout.addLayout(self._small_z)

        # 大龙门坐标
        layout.addWidget(self._section_label("大龙门坐标"))
        self._big_x = self._coord_row("X")
        self._big_y = self._coord_row("Y")
        self._big_z = self._coord_row("Z")
        layout.addLayout(self._big_x)
        layout.addLayout(self._big_y)
        layout.addLayout(self._big_z)

        # 拧紧力矩
        self._torque_label = QLabel("--")
        self._torque_label.setStyleSheet(self._value_mono_style())
        layout.addLayout(self._labeled_row("拧紧力矩", self._torque_label, "N·m"))

        # 孔位坐标（标定转换后）
        layout.addWidget(self._section_label("孔位坐标 (实际)"))
        self._hole_x = self._coord_row("X")
        self._hole_y = self._coord_row("Y")
        self._hole_z = self._coord_row("Z")
        layout.addLayout(self._hole_x)
        layout.addLayout(self._hole_y)
        layout.addLayout(self._hole_z)

        return group

    # ---- signal wiring -------------------------------------------------------

    def _connect_signals(self):
        app_state.plc_online_changed.connect(self._on_plc_changed)
        app_state.camera_online_changed.connect(self._on_camera_changed)
        app_state.estop_changed.connect(self._on_estop_changed)
        app_state.motor_position_updated.connect(self._on_motor_position)
        app_state.motor_state_updated.connect(self._on_motor_updated)

        if self._camera:
            self._camera.connection_status.connect(self._on_camera_btn_state)
            self._camera.image_grabbed.connect(self._on_image_grabbed)
            self._camera.point_cloud_grabbed.connect(self._on_pc_grabbed)

        if self._pcl:
            self._pcl.processing_finished.connect(self._on_pcl_done)
            self._pcl.processing_error.connect(self._on_pcl_error)

    # ---- slot callbacks ------------------------------------------------------

    def _on_plc_changed(self, online: bool):
        self._plc_indicator.set_status("online" if online else "offline")
        self._plc_label.setText(f"PLC: {'在线' if online else '离线'}")
        self._plc_label.setStyleSheet(self._value_mono_style(GREEN_STATUS if online else TEXT_DIM))

    def _on_camera_changed(self, online: bool):
        self._camera_indicator.set_status("online" if online else "offline")
        self._camera_label.setText(f"相机: {'在线' if online else '离线'}")

    def _on_estop_changed(self, active: bool):
        self._estop_btn.setChecked(active)
        self._estop_btn.setText("急停中" if active else "急 停")
        if active:
            self._estop_btn.setStyleSheet(self._estop_btn.styleSheet().replace(
                f"background-color: {RED_ALERT};",
                "background-color: #CC0000;",
            ))
        else:
            self._estop_btn.setStyleSheet(self._estop_btn.styleSheet().replace(
                "background-color: #CC0000;",
                f"background-color: {RED_ALERT};",
            ))

    def _on_motor_position(self, name: str, pos: float):
        """高频位置更新 — 只更新坐标显示。"""
        value = f"{pos:.1f}" if pos else "--"
        self._update_coord(name, value)

    def _on_motor_updated(self, name: str):
        """完整电机状态更新。"""
        ms = app_state.motor_state(name)
        if ms is None:
            return
        pos = f"{ms.position:.1f}" if ms.position else "--"
        self._update_coord(name, pos)

    def _on_image_grabbed(self, path: str):
        pix = QPixmap(path)
        if not pix.isNull():
            scaled = pix.scaled(
                self._camera_view.width(),
                self._camera_view.height(),
                Qt.KeepAspectRatio,
                Qt.SmoothTransformation,
            )
            self._camera_view.setPixmap(scaled)

    def _on_pc_grabbed(self, path: str):
        self._btn_process.setEnabled(True)
        self._btn_process.setStyleSheet(QSS_PRIMARY_BUTTON)

    def _on_pcl_done(self, result: dict):
        centers = result.get("centers", [])
        if centers:
            c = centers[0]
            self._set_coord(self._hole_x, f"{c['x']:.1f}")
            self._set_coord(self._hole_y, f"{c['y']:.1f}")
            self._set_coord(self._hole_z, f"{c['z']:.1f}")
        self._btn_process.setEnabled(True)
        self._btn_process.setText("计算")
        self._btn_process.setStyleSheet(QSS_PRIMARY_BUTTON)

    def _on_pcl_error(self, msg: str):
        self._btn_process.setEnabled(True)
        self._btn_process.setText("计算")
        self._btn_process.setStyleSheet(QSS_PRIMARY_BUTTON)

    def _on_camera_btn_state(self, connected: bool, msg: str):
        if connected:
            self._btn_connect.setText("断开相机")
            self._btn_connect.setStyleSheet(QSS_DANGER_BUTTON)
            self._btn_capture.setEnabled(True)
            self._btn_capture.setStyleSheet(QSS_PRIMARY_BUTTON)
        else:
            self._btn_connect.setText("连接相机")
            self._btn_connect.setStyleSheet(QSS_PRIMARY_BUTTON)
            self._btn_capture.setEnabled(False)
            self._btn_capture.setStyleSheet(QSS_SECONDARY_BUTTON)
            self._btn_process.setEnabled(False)
            self._btn_process.setStyleSheet(QSS_SECONDARY_BUTTON)

    # ---- button handlers -----------------------------------------------------

    def _on_connect(self):
        if not self._camera:
            return
        if self._camera.is_connected:
            self._camera.disconnect_camera()
        else:
            self._camera.connect_camera()

    def _on_capture(self):
        if self._camera:
            self._btn_process.setEnabled(False)
            self._btn_process.setText("等待中...")
            self._btn_process.setStyleSheet(QSS_SECONDARY_BUTTON)
            self._camera.trigger_3d_capture()

    def _on_process(self):
        if self._pcl:
            pcd_path = self._camera._temp_dir + "/temp_3d_cloud.pcd"
            self._btn_process.setEnabled(False)
            self._btn_process.setText("计算中...")
            self._btn_process.setStyleSheet(QSS_SECONDARY_BUTTON)
            self._pcl.process_pcd(pcd_path)

    def _on_estop(self):
        app_state.is_estop = self._estop_btn.isChecked()

    # ---- helpers -------------------------------------------------------------

    def _update_coord(self, motor_name: str, value: str):
        mapping = {
            "X_motor": self._small_x, "YL_motor": self._small_y,
            "YR_motor": self._small_y, "Z_motor": self._small_z,
            "XX_motor": self._big_x, "YLL_motor": self._big_y,
            "YRR_motor": self._big_y, "ZZ_motor": self._big_z,
        }
        row = mapping.get(motor_name)
        if row:
            self._set_coord(row, value)

    @staticmethod
    def _set_coord(row: QHBoxLayout, value: str):
        label = row.itemAt(1).widget()
        if isinstance(label, QLabel):
            label.setText(value)

    def _refresh_dashboard(self):
        self._on_plc_changed(app_state.plc_online)
        self._on_camera_changed(app_state.camera_online)

    # ---- mini-factories ------------------------------------------------------

    def _section_label(self, text: str) -> QLabel:
        lbl = QLabel(text)
        lbl.setStyleSheet(
            f"color: {TEXT_SECONDARY};"
            f"font-size: {FONT_SIZE_SM}px;"
            f"font-family: {FONT_FAMILY};"
            f"margin-top: 6px;"
        )
        return lbl

    def _coord_row(self, axis: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)
        axis_lbl = QLabel(axis)
        axis_lbl.setFixedWidth(14)
        axis_lbl.setStyleSheet(
            f"color: {TEXT_DIM}; font-family: {FONT_MONO};"
            f"font-size: {FONT_SIZE_SM}px;"
        )
        val_lbl = QLabel("--")
        val_lbl.setStyleSheet(self._value_mono_style())
        row.addWidget(axis_lbl)
        row.addWidget(val_lbl)
        row.addStretch()
        return row

    def _labeled_row(self, label: str, val_lbl: QLabel, unit: str) -> QHBoxLayout:
        row = QHBoxLayout()
        row.setSpacing(4)
        lbl = QLabel(label + ":")
        lbl.setStyleSheet(f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;")
        unit_lbl = QLabel(unit)
        unit_lbl.setStyleSheet(f"color: {TEXT_DIM}; font-size: 10px;")
        row.addWidget(lbl)
        row.addWidget(val_lbl)
        row.addWidget(unit_lbl)
        row.addStretch()
        return row

    def _value_mono_style(self, color: str = TEXT_PRIMARY) -> str:
        return (
            f"color: {color}; font-family: {FONT_MONO};"
            f"font-size: {FONT_SIZE_SM}px; font-weight: bold;"
        )

    def _card_style(self) -> str:
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

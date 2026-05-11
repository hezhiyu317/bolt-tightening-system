"""数据记录页面 — 实时拧紧力矩图表 + 拧紧枪控制 + OK/NG 判定。

工作流：点击"启动"→ 枪体转动 → 记录力矩-时间曲线 → 枪停 → 自动判定 OK/NG。
X 轴为时间（秒），从拧紧开始计时。
"""

import csv
import time
from datetime import datetime

import pyqtgraph as pg
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QFileDialog,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
    QWidget,
)

from src.services.plc_service import PlcService
from src.ui.styles import (
    BG_PANEL,
    BLUE_FUNC,
    BORDER_CARD,
    CARD_RADIUS,
    FONT_FAMILY,
    FONT_MONO,
    FONT_SIZE_SM,
    GREEN_STATUS,
    ORANGE_WARN,
    QSS_DANGER_BUTTON,
    QSS_PRIMARY_BUTTON,
    QSS_SECONDARY_BUTTON,
    RED_ALERT,
    TEXT_DIM,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)

# 拧紧力矩公差带 (N·m)
TORQUE_LOWER = 28.0
TORQUE_UPPER = 33.0
VELOCITY_THRESHOLD = 0.5  # 判断枪体是否在转动


def _gun_registers():
    """读取拧紧枪控制寄存器地址（可配置）。"""
    from src.utils.config_manager import config as cfg
    defaults = {"start": 100, "reset": 101, "forward": 102, "reverse": 103}
    regs = cfg.get("system.gun.registers", {}) or {}
    return {k: regs.get(k, defaults[k]) for k in defaults}


def _torque_motor_names():
    """读取力矩监测电机名列表。"""
    from src.utils.config_manager import config as cfg
    return cfg.get("system.gun.torque_motors",
                   ["SPF_motor", "SPT_motor", "SPM_motor", "SPC_motor"])


class DataRecordingPage(QWidget):
    """数据记录页面 — 拧紧枪控制 + 力矩-时间曲线 + OK/NG 判定。"""

    IDLE = "idle"
    RUNNING = "running"
    DONE = "done"

    def __init__(
        self,
        plc_service: PlcService = None,
        torque_motor_names: list = None,
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self._plc = plc_service
        self._torque_motor_names = torque_motor_names or _torque_motor_names()
        self._gun_regs = _gun_registers()

        # 会话
        self._state = self.IDLE
        self._session_start_time: float = 0.0
        self._session_times: list = []
        self._session_torques: list = []
        self._session_csv_rows: list = []
        self._completed_sessions: list = []
        self._last_velocity = 0.0
        self._still_count = 0  # 连续静止计数，用于防抖

        # 曲线
        self._torque_curve = None
        self._band_upper = None
        self._band_lower = None
        self._fill_band = None
        self._scatter_oor = None
        self._scatter_in = None

        self._setup_ui()

        if self._plc:
            self._plc.data_updated.connect(self._on_plc_data)

    # ---- UI construction ----------------------------------------------------

    def _setup_ui(self):
        root = QHBoxLayout(self)
        root.setContentsMargins(12, 12, 12, 12)
        root.setSpacing(12)

        # ---- 左侧: 图表 ----
        chart_wrapper = QGroupBox("拧紧力矩-时间曲线")
        chart_wrapper.setStyleSheet(self._card_style())
        chart_layout = QVBoxLayout(chart_wrapper)
        chart_layout.setContentsMargins(4, 16, 4, 4)

        self._plot_widget = pg.PlotWidget()
        self._plot_widget.setBackground("#FFFFFF")
        self._plot_widget.setLabel("left", "力矩", units="N·m")
        self._plot_widget.setLabel("bottom", "时间", units="s")
        self._plot_widget.setYRange(0, 40)
        self._plot_widget.setXRange(0, 10)
        self._plot_widget.showGrid(x=True, y=True, alpha=0.3)

        # 公差带 (绿色填充)
        self._band_upper = self._plot_widget.plot(
            [0, 1], [TORQUE_UPPER, TORQUE_UPPER],
            pen=pg.mkPen(color=(82, 196, 26), width=1, style=Qt.DashLine),
        )
        self._band_lower = self._plot_widget.plot(
            [0, 1], [TORQUE_LOWER, TORQUE_LOWER],
            pen=pg.mkPen(color=(82, 196, 26), width=1, style=Qt.DashLine),
        )
        self._fill_band = pg.FillBetweenItem(
            self._band_lower, self._band_upper,
            brush=pg.mkBrush(82, 196, 26, 40),
        )
        self._plot_widget.addItem(self._fill_band)

        # 力矩曲线 (蓝色)
        self._torque_curve = self._plot_widget.plot(
            [], [], pen=pg.mkPen(color=(24, 144, 255), width=2),
        )

        # 超限散点 (红色)
        self._scatter_oor = pg.ScatterPlotItem(
            [], [], pen=None, brush=pg.mkBrush(255, 77, 79, 180), size=6,
        )
        self._plot_widget.addItem(self._scatter_oor)

        # 合格散点 (蓝色)
        self._scatter_in = pg.ScatterPlotItem(
            [], [], pen=None, brush=pg.mkBrush(24, 144, 255, 180), size=6,
        )
        self._plot_widget.addItem(self._scatter_in)

        chart_layout.addWidget(self._plot_widget)
        root.addWidget(chart_wrapper, stretch=7)

        # ---- 右侧: 控制与判定 ----
        right_panel = QVBoxLayout()
        right_panel.setSpacing(12)

        # -- 拧紧枪控制 --
        gun_group = QGroupBox("拧紧枪控制")
        gun_group.setStyleSheet(self._card_style())
        gun_layout = QVBoxLayout(gun_group)
        gun_layout.setContentsMargins(8, 16, 8, 8)
        gun_layout.setSpacing(8)

        # Row 1: 启动 | 复位
        row1 = QHBoxLayout()
        self._btn_start = QPushButton("启动")
        self._btn_start.setStyleSheet(QSS_PRIMARY_BUTTON)
        self._btn_start.setFixedHeight(36)
        self._btn_start.clicked.connect(self._on_gun_start)
        row1.addWidget(self._btn_start)

        self._btn_reset = QPushButton("复位")
        self._btn_reset.setStyleSheet(QSS_SECONDARY_BUTTON)
        self._btn_reset.setFixedHeight(36)
        self._btn_reset.clicked.connect(self._on_gun_reset)
        row1.addWidget(self._btn_reset)
        gun_layout.addLayout(row1)

        # Row 2: 正转 | 反转
        row2 = QHBoxLayout()
        self._btn_forward = QPushButton("正转")
        self._btn_forward.setStyleSheet(QSS_SECONDARY_BUTTON)
        self._btn_forward.setFixedHeight(36)
        self._btn_forward.pressed.connect(self._on_gun_forward_press)
        self._btn_forward.released.connect(self._on_gun_forward_release)
        row2.addWidget(self._btn_forward)

        self._btn_reverse = QPushButton("反转")
        self._btn_reverse.setStyleSheet(QSS_SECONDARY_BUTTON)
        self._btn_reverse.setFixedHeight(36)
        self._btn_reverse.pressed.connect(self._on_gun_reverse_press)
        self._btn_reverse.released.connect(self._on_gun_reverse_release)
        row2.addWidget(self._btn_reverse)
        gun_layout.addLayout(row2)

        right_panel.addWidget(gun_group)

        # -- OK/NG 判定 --
        verdict_group = QGroupBox("拧紧结果判定")
        verdict_group.setStyleSheet(self._card_style())
        verdict_layout = QVBoxLayout(verdict_group)
        verdict_layout.setContentsMargins(8, 16, 8, 8)
        verdict_layout.setSpacing(8)

        self._verdict_label = QLabel("等待拧紧启动")
        self._verdict_label.setAlignment(Qt.AlignCenter)
        self._verdict_label.setFixedHeight(80)
        self._verdict_label.setWordWrap(True)
        self._verdict_label.setStyleSheet(
            f"font-size: 28px; font-weight: bold;"
            f"font-family: {FONT_FAMILY};"
            f"background-color: {TEXT_DIM}; color: #FFFFFF;"
            f"border-radius: 8px; padding: 12px;"
        )
        verdict_layout.addWidget(self._verdict_label)

        self._peak_label = QLabel("峰值: -- N·m")
        self._peak_label.setStyleSheet(
            f"color: {TEXT_PRIMARY}; font-family: {FONT_MONO};"
            f"font-size: 18px; font-weight: bold;"
        )
        self._peak_label.setAlignment(Qt.AlignCenter)
        verdict_layout.addWidget(self._peak_label)

        self._last_label = QLabel("当前: -- N·m")
        self._last_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-family: {FONT_MONO};"
            f"font-size: 14px;"
        )
        self._last_label.setAlignment(Qt.AlignCenter)
        verdict_layout.addWidget(self._last_label)

        self._elapsed_label = QLabel("耗时: -- s")
        self._elapsed_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-family: {FONT_MONO};"
            f"font-size: 14px;"
        )
        self._elapsed_label.setAlignment(Qt.AlignCenter)
        verdict_layout.addWidget(self._elapsed_label)

        self._state_label = QLabel("状态: 待命")
        self._state_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;")
        self._state_label.setAlignment(Qt.AlignCenter)
        verdict_layout.addWidget(self._state_label)

        right_panel.addWidget(verdict_group)

        # -- 统计 --
        stats_group = QGroupBox("本次拧紧统计")
        stats_group.setStyleSheet(self._card_style())
        stats_layout = QVBoxLayout(stats_group)
        stats_layout.setContentsMargins(8, 12, 8, 8)
        stats_layout.setSpacing(4)

        self._count_label = QLabel("采样数: 0")
        self._count_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;")
        stats_layout.addWidget(self._count_label)

        self._oor_count_label = QLabel("超限点: 0")
        self._oor_count_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;")
        stats_layout.addWidget(self._oor_count_label)

        self._pass_rate_label = QLabel("合格率: --")
        self._pass_rate_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;")
        stats_layout.addWidget(self._pass_rate_label)

        self._history_count_label = QLabel("历史拧紧次数: 0")
        self._history_count_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;")
        stats_layout.addWidget(self._history_count_label)

        right_panel.addWidget(stats_group)

        # -- 操作 --
        btn_group = QGroupBox("操作")
        btn_group.setStyleSheet(self._card_style())
        btn_layout = QVBoxLayout(btn_group)
        btn_layout.setContentsMargins(8, 12, 8, 8)
        btn_layout.setSpacing(6)

        btn_clear = QPushButton("清空图表")
        btn_clear.setStyleSheet(QSS_SECONDARY_BUTTON)
        btn_clear.clicked.connect(self._on_clear)
        btn_layout.addWidget(btn_clear)

        btn_export = QPushButton("导出历史记录")
        btn_export.setStyleSheet(QSS_PRIMARY_BUTTON)
        btn_export.clicked.connect(self._on_export_csv)
        btn_layout.addWidget(btn_export)

        right_panel.addWidget(btn_group)
        right_panel.addStretch()

        root.addLayout(right_panel, stretch=3)

    # ---- PLC data -----------------------------------------------------------

    def _on_plc_data(self, motors_data: dict, global_data: dict):
        """接收 PLC 数据。"""
        torque = self._extract_torque(motors_data)
        velocity = self._extract_velocity(motors_data)
        self._last_velocity = velocity

        if self._state == self.RUNNING:
            if torque is not None:
                self._record_point(torque)
            # 检测枪停（防抖：连续 3 次静止才判定停止）
            if velocity < VELOCITY_THRESHOLD:
                self._still_count += 1
                if self._still_count >= 3 and self._session_times:
                    elapsed = time.perf_counter() - self._session_start_time
                    if elapsed > 0.3:
                        self._end_session()
            else:
                self._still_count = 0

    def _extract_torque(self, motors_data: dict):
        for name in self._torque_motor_names:
            data = motors_data.get(name, {})
            t = data.get("actl_tor", 0)
            if t:
                return float(t)
        best = 0.0
        for data in motors_data.values():
            t = data.get("actl_tor", 0)
            if t > best:
                best = float(t)
        return best if best > 0 else None

    def _extract_velocity(self, motors_data: dict) -> float:
        for name in self._torque_motor_names:
            data = motors_data.get(name, {})
            v = data.get("actl_vel", 0)
            if v:
                return float(v)
        best = 0.0
        for data in motors_data.values():
            v = data.get("actl_vel", 0)
            if v > best:
                best = float(v)
        return best

    # ---- gun control buttons ------------------------------------------------

    def _on_gun_start(self):
        """启动拧紧枪 + 开始记录会话。"""
        if self._plc:
            self._plc.add_write_task("coil", self._gun_regs["start"], True)
            QTimer.singleShot(200, lambda: self._plc.add_write_task(
                "coil", self._gun_regs["start"], False))
        self._begin_session()

    def _on_gun_reset(self):
        """复位拧紧枪。"""
        if self._plc:
            self._plc.add_write_task("coil", self._gun_regs["reset"], True)
            QTimer.singleShot(200, lambda: self._plc.add_write_task(
                "coil", self._gun_regs["reset"], False))

    def _on_gun_forward_press(self):
        """正转按下。"""
        if self._plc:
            self._plc.add_write_task("coil", self._gun_regs["forward"], True)

    def _on_gun_forward_release(self):
        """正转松开。"""
        if self._plc:
            self._plc.add_write_task("coil", self._gun_regs["forward"], False)

    def _on_gun_reverse_press(self):
        """反转按下。"""
        if self._plc:
            self._plc.add_write_task("coil", self._gun_regs["reverse"], True)

    def _on_gun_reverse_release(self):
        """反转松开。"""
        if self._plc:
            self._plc.add_write_task("coil", self._gun_regs["reverse"], False)

    # ---- session lifecycle --------------------------------------------------

    def _begin_session(self):
        """开始新拧紧会话。"""
        self._state = self.RUNNING
        self._session_start_time = time.perf_counter()
        self._session_times = []
        self._session_torques = []
        self._session_csv_rows = []
        self._still_count = 0

        self._verdict_label.setText("拧紧中...")
        self._verdict_label.setStyleSheet(
            f"font-size: 28px; font-weight: bold;"
            f"font-family: {FONT_FAMILY};"
            f"background-color: {ORANGE_WARN}; color: #FFFFFF;"
            f"border-radius: 8px; padding: 12px;"
        )
        self._state_label.setText("状态: 拧紧中")
        self._state_label.setStyleSheet(
            f"color: {ORANGE_WARN}; font-size: {FONT_SIZE_SM}px;")
        self._peak_label.setText("峰值: -- N·m")
        self._last_label.setText("当前: -- N·m")
        self._elapsed_label.setText("耗时: 0.0 s")
        self._count_label.setText("采样数: 0")
        self._oor_count_label.setText("超限点: 0")
        self._pass_rate_label.setText("合格率: --")
        self._pass_rate_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;")

        self._torque_curve.clear()
        self._scatter_in.clear()
        self._scatter_oor.clear()
        self._plot_widget.setXRange(0, 10)

    def _record_point(self, torque: float):
        elapsed = time.perf_counter() - self._session_start_time
        self._session_times.append(elapsed)
        self._session_torques.append(torque)

        ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S.%f")[:-3]
        in_range = TORQUE_LOWER <= torque <= TORQUE_UPPER
        self._session_csv_rows.append((ts, f"{elapsed:.3f}", f"{torque:.2f}",
                                        "OK" if in_range else "NG"))

        self._redraw_chart()

        peak = max(self._session_torques)
        total = len(self._session_torques)
        oor_count = sum(1 for t in self._session_torques
                        if t < TORQUE_LOWER or t > TORQUE_UPPER)
        pass_rate = (total - oor_count) / total * 100 if total > 0 else 100

        self._peak_label.setText(f"峰值: {peak:.1f} N·m")
        self._last_label.setText(f"当前: {torque:.1f} N·m")
        self._elapsed_label.setText(f"耗时: {elapsed:.1f} s")
        self._count_label.setText(f"采样数: {total}")
        self._oor_count_label.setText(f"超限点: {oor_count}")

        if pass_rate >= 95:
            color = GREEN_STATUS
        elif pass_rate >= 80:
            color = "#FAAD14"
        else:
            color = RED_ALERT
        self._pass_rate_label.setText(f"合格率: {pass_rate:.1f} %")
        self._pass_rate_label.setStyleSheet(
            f"color: {color}; font-size: {FONT_SIZE_SM}px;")

    def _end_session(self):
        """拧紧完成，冻结结果。"""
        self._state = self.DONE

        if not self._session_torques:
            self._verdict_label.setText("无数据")
            self._state_label.setText("状态: 待命")
            return

        total = len(self._session_torques)
        steady_points = [t for t in self._session_torques if t > 10.0]
        if steady_points:
            oor_steady = sum(1 for t in steady_points
                             if t < TORQUE_LOWER or t > TORQUE_UPPER)
            pass_rate_steady = (len(steady_points) - oor_steady) / len(steady_points) * 100
            passed = pass_rate_steady >= 90
        else:
            oor = sum(1 for t in self._session_torques
                      if t < TORQUE_LOWER or t > TORQUE_UPPER)
            passed = oor == 0

        peak = max(self._session_torques)
        elapsed = self._session_times[-1] if self._session_times else 0
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")

        self._completed_sessions.append({
            "id": len(self._completed_sessions) + 1,
            "time": ts,
            "peak": peak,
            "elapsed": elapsed,
            "samples": total,
            "passed": passed,
            "times": list(self._session_times),
            "torques": list(self._session_torques),
            "csv_rows": list(self._session_csv_rows),
        })

        if passed:
            self._verdict_label.setText("OK")
            self._verdict_label.setStyleSheet(
                f"font-size: 36px; font-weight: bold;"
                f"font-family: {FONT_FAMILY};"
                f"background-color: {GREEN_STATUS}; color: #FFFFFF;"
                f"border-radius: 8px; padding: 12px;"
            )
        else:
            self._verdict_label.setText("NG")
            self._verdict_label.setStyleSheet(
                f"font-size: 36px; font-weight: bold;"
                f"font-family: {FONT_FAMILY};"
                f"background-color: {RED_ALERT}; color: #FFFFFF;"
                f"border-radius: 8px; padding: 12px;"
            )

        self._elapsed_label.setText(f"耗时: {elapsed:.1f} s")
        self._state_label.setText("状态: 完成")
        self._state_label.setStyleSheet(
            f"color: {GREEN_STATUS if passed else RED_ALERT};"
            f"font-size: {FONT_SIZE_SM}px;")
        self._history_count_label.setText(
            f"历史拧紧次数: {len(self._completed_sessions)}")

    def _redraw_chart(self):
        times = self._session_times
        torques = self._session_torques
        self._torque_curve.setData(times, torques)

        in_t, in_q = [], []
        oor_t, oor_q = [], []
        for t, q in zip(times, torques):
            if TORQUE_LOWER <= q <= TORQUE_UPPER:
                in_t.append(t)
                in_q.append(q)
            else:
                oor_t.append(t)
                oor_q.append(q)

        self._scatter_in.setData(in_t, in_q)
        self._scatter_oor.setData(oor_t, oor_q)

        if times:
            x_max = max(times[-1] + 0.5, 5)
            self._band_upper.setData([0, x_max], [TORQUE_UPPER, TORQUE_UPPER])
            self._band_lower.setData([0, x_max], [TORQUE_LOWER, TORQUE_LOWER])
            self._plot_widget.setXRange(0, x_max)

    # ---- button handlers ----------------------------------------------------

    def _on_clear(self):
        """清空图表和所有历史。"""
        self._state = self.IDLE
        self._session_times = []
        self._session_torques = []
        self._session_csv_rows = []
        self._still_count = 0
        self._completed_sessions.clear()

        self._torque_curve.clear()
        self._scatter_in.clear()
        self._scatter_oor.clear()
        self._plot_widget.setXRange(0, 10)

        self._verdict_label.setText("等待拧紧启动")
        self._verdict_label.setStyleSheet(
            f"font-size: 28px; font-weight: bold;"
            f"font-family: {FONT_FAMILY};"
            f"background-color: {TEXT_DIM}; color: #FFFFFF;"
            f"border-radius: 8px; padding: 12px;"
        )
        self._state_label.setText("状态: 待命")
        self._state_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;")
        self._peak_label.setText("峰值: -- N·m")
        self._last_label.setText("当前: -- N·m")
        self._elapsed_label.setText("耗时: -- s")
        self._count_label.setText("采样数: 0")
        self._oor_count_label.setText("超限点: 0")
        self._pass_rate_label.setText("合格率: --")
        self._pass_rate_label.setStyleSheet(
            f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;")
        self._history_count_label.setText("历史拧紧次数: 0")

    def _on_export_csv(self):
        if not self._completed_sessions:
            QMessageBox.information(self, "提示", "暂无历史数据可导出")
            return

        default_name = f"torque_log_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
        path, _ = QFileDialog.getSaveFileName(
            self, "导出 CSV", default_name,
            "CSV Files (*.csv);;All Files (*)",
        )
        if not path:
            return

        try:
            with open(path, "w", newline="", encoding="utf-8-sig") as f:
                writer = csv.writer(f)
                writer.writerow(["拧紧编号", "时间戳", "耗时(s)", "力矩(N·m)", "判定",
                                 "峰值(N·m)", "总耗时(s)", "会话结果"])
                for sess in self._completed_sessions:
                    for row in sess["csv_rows"]:
                        ts, elapsed, torque, judge = row
                        writer.writerow([
                            sess["id"], ts, elapsed, torque, judge,
                            f"{sess['peak']:.2f}",
                            f"{sess['elapsed']:.2f}",
                            "OK" if sess["passed"] else "NG",
                        ])
            QMessageBox.information(
                self, "导出成功",
                f"已导出 {len(self._completed_sessions)} 次拧紧记录至:\n{path}",
            )
        except OSError as e:
            QMessageBox.warning(self, "导出失败", str(e))

    # ---- style helpers ------------------------------------------------------

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

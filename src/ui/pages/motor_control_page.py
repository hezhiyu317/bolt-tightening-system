"""三坐标平台页面 — 电机控制 + 龙门三坐标运动 + 点位管理。

重构自 test_total/test_total/main.py create_motor_tab / create_integrated_tab。
舍弃 YR / YRR 电机。
"""

from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtWidgets import (
    QGridLayout,
    QGroupBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QVBoxLayout,
    QWidget,
)
from PyQt5.QtWidgets import QAbstractItemView

from src.models.motor_config import MotorConfig, get_motor_names_by_group
from src.services.plc_service import PlcService
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
    RED_ALERT,
    TEXT_DIM,
    TEXT_PRIMARY,
    TEXT_SECONDARY,
)
from src.ui.widgets.motor_widget import MotorWidget


class MotorControlPage(QWidget):
    """三坐标平台页面。"""

    def __init__(
        self,
        plc_service: PlcService,
        motor_configs: dict,
        parent: QWidget = None,
    ):
        super().__init__(parent)
        self._plc = plc_service
        self._motor_configs = motor_configs
        self._motor_widgets: dict[str, MotorWidget] = {}
        self._synced = False
        self._latest_motor_data: dict = {}
        self._coord_inputs: dict[str, dict[str, QLineEdit]] = {}
        self._point_lists: dict[str, list] = {"small": [], "big": []}
        self._point_tables: dict[str, QTableWidget] = {}

        self._setup_ui()
        self._wire_signals()

    # ---- UI ----------------------------------------------------------------

    def _setup_ui(self):
        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)

        self._tabs = QTabWidget()
        self._tabs.setStyleSheet(self._tab_style())

        # 小龙门
        self._tabs.addTab(
            self._build_motor_grid("Small Gantry"), "小龙门 (Z / X / YL)")

        # 大龙门
        self._tabs.addTab(
            self._build_motor_grid("Big Gantry"), "大龙门 (ZZ / XX / YLL)")

        # 坐标运动
        self._tabs.addTab(self._build_integrated_tab(), "坐标运动")

        layout.addWidget(self._tabs)

    def _build_motor_grid(self, group: str) -> QWidget:
        """构建一组电机的 3 列网格。"""
        w = QWidget()
        layout = QGridLayout(w)
        layout.setSpacing(8)

        names = get_motor_names_by_group(group)
        for i, name in enumerate(names):
            mc = self._motor_configs.get(name)
            if mc is None:
                continue
            mw = MotorWidget(mc)
            mw.write_requested.connect(self._on_write_requested)
            self._motor_widgets[name] = mw
            layout.addWidget(mw, i // 3, i % 3)

        return w

    def _build_integrated_tab(self) -> QWidget:
        """坐标运动控制 — 小龙门 + 大龙门并排。"""
        w = QWidget()
        layout = QHBoxLayout(w)
        layout.setSpacing(12)

        layout.addWidget(self._build_point_panel("small", "小龙门"))
        layout.addWidget(self._build_point_panel("big", "大龙门"))
        return w

    def _build_point_panel(self, gantry_key: str, title: str) -> QGroupBox:
        """单个龙门的坐标控制面板。"""
        group = QGroupBox(f"{title} 三坐标控制")
        group.setStyleSheet(self._card_style())
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # 输入区
        grid = QGridLayout()
        grid.setSpacing(4)
        inputs: dict[str, QLineEdit] = {}
        for i, axis in enumerate(["X", "Y", "Z"]):
            lbl = QLabel(f"{axis}:")
            lbl.setStyleSheet(
                f"color: {TEXT_SECONDARY}; font-size: {FONT_SIZE_SM}px;")
            inp = QLineEdit("0.0")
            inp.setFixedWidth(100)
            inp.setStyleSheet(self._input_style())
            inputs[axis] = inp
            grid.addWidget(lbl, 0, i * 2)
            grid.addWidget(inp, 0, i * 2 + 1)

        grid.addWidget(
            QLabel("速度上限:"), 1, 0)
        speed_inp = QLineEdit("10.0")
        speed_inp.setFixedWidth(100)
        speed_inp.setStyleSheet(self._input_style())
        inputs["speed"] = speed_inp
        grid.addWidget(speed_inp, 1, 1)
        layout.addLayout(grid)
        self._coord_inputs[gantry_key] = inputs

        # 按钮区
        btn_row = QHBoxLayout()
        btn_row.setSpacing(6)

        btn_read = QPushButton("读取当前位置")
        btn_read.clicked.connect(
            lambda: self._on_read_position(gantry_key))
        btn_record = QPushButton("记录点位")
        btn_record.clicked.connect(
            lambda: self._on_record_point(gantry_key))
        btn_move = QPushButton("运动到当前点位")
        btn_move.clicked.connect(
            lambda: self._on_move_to_point(gantry_key))

        for b in (btn_read, btn_record, btn_move):
            b.setStyleSheet(self._btn_style())
            btn_row.addWidget(b)

        layout.addLayout(btn_row)

        # 点位列表
        table = QTableWidget(0, 3)
        table.setHorizontalHeaderLabels(["X", "Y", "Z"])
        table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        table.setSelectionBehavior(QAbstractItemView.SelectRows)
        table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        table.setMaximumHeight(180)
        table.setStyleSheet(
            f"QTableWidget {{"
            f"  background-color: {BG_DARK}; color: {TEXT_PRIMARY};"
            f"  border: 1px solid {BORDER_CARD};"
            f"  gridline-color: {BORDER_CARD};"
            f"  font-family: {FONT_MONO}; font-size: {FONT_SIZE_SM}px;"
            f"}}"
            f"QHeaderView::section {{"
            f"  background-color: {BG_PANEL}; color: {BLUE_FUNC};"
            f"  border: 1px solid {BORDER_CARD}; padding: 2px;"
            f"}}"
        )
        table.cellClicked.connect(
            lambda row, col: self._on_load_point(gantry_key, row))
        self._point_tables[gantry_key] = table
        layout.addWidget(table)

        btn_del = QPushButton("删除选中点位")
        btn_del.setStyleSheet(self._btn_style())
        btn_del.clicked.connect(
            lambda: self._on_delete_point(gantry_key))
        layout.addWidget(btn_del)

        return group

    # ---- signal wiring ----------------------------------------------------

    def _wire_signals(self):
        self._plc.data_updated.connect(self._on_plc_data)

    def _on_plc_data(self, motors_data: dict, global_data: dict):
        self._latest_motor_data = motors_data
        self._synced = global_data.get("sync_done", False)

        for name, data in motors_data.items():
            if name in self._motor_widgets:
                self._motor_widgets[name].update_display(data, self._synced)

    def _on_write_requested(self, task: dict):
        self._plc.add_write_task(
            task["type"], task["addr"], task["val"], task.get("bit"))

    # ---- point panel logic ------------------------------------------------

    def _motor_for_axis(self, gantry_key: str, axis: str) -> str:
        """返回龙门某轴对应的电机名。"""
        mapping = {
            "small": {"X": "X_motor", "Y": "YL_motor", "Z": "Z_motor"},
            "big": {"X": "XX_motor", "Y": "YLL_motor", "Z": "ZZ_motor"},
        }
        return mapping[gantry_key][axis]

    def _on_read_position(self, gantry_key: str):
        for axis in ("X", "Y", "Z"):
            motor_name = self._motor_for_axis(gantry_key, axis)
            pos = self._latest_motor_data.get(motor_name, {}).get(
                "actl_pos", 0.0)
            self._coord_inputs[gantry_key][axis].setText(f"{pos:.3f}")

    def _on_record_point(self, gantry_key: str):
        try:
            x = float(self._coord_inputs[gantry_key]["X"].text())
            y = float(self._coord_inputs[gantry_key]["Y"].text())
            z = float(self._coord_inputs[gantry_key]["Z"].text())
        except ValueError:
            QMessageBox.warning(self, "错误", "请输入有效的坐标值")
            return

        points = self._point_lists[gantry_key]
        if len(points) >= 10:
            QMessageBox.warning(self, "提示", "点位列表已满，请先删除旧点位")
            return

        points.append((x, y, z))
        self._refresh_table(gantry_key)

    def _on_load_point(self, gantry_key: str, row: int):
        points = self._point_lists[gantry_key]
        if 0 <= row < len(points):
            x, y, z = points[row]
            self._coord_inputs[gantry_key]["X"].setText(f"{x:.3f}")
            self._coord_inputs[gantry_key]["Y"].setText(f"{y:.3f}")
            self._coord_inputs[gantry_key]["Z"].setText(f"{z:.3f}")

    def _on_delete_point(self, gantry_key: str):
        table = self._point_tables[gantry_key]
        rows = sorted(
            set(i.row() for i in table.selectedItems()), reverse=True)
        if not rows:
            return
        for row in rows:
            if 0 <= row < len(self._point_lists[gantry_key]):
                self._point_lists[gantry_key].pop(row)
        self._refresh_table(gantry_key)

    def _on_move_to_point(self, gantry_key: str):
        try:
            tx = float(self._coord_inputs[gantry_key]["X"].text())
            ty = float(self._coord_inputs[gantry_key]["Y"].text())
            tz = float(self._coord_inputs[gantry_key]["Z"].text())
            v_max = float(self._coord_inputs[gantry_key]["speed"].text())
        except ValueError:
            QMessageBox.warning(self, "错误", "请输入有效的数值")
            return

        if v_max <= 0:
            QMessageBox.warning(self, "错误", "速度上限必须大于0")
            return

        # 当前坐标
        cx = self._latest_motor_data.get(
            self._motor_for_axis(gantry_key, "X"), {}).get("actl_pos", 0)
        cy = self._latest_motor_data.get(
            self._motor_for_axis(gantry_key, "Y"), {}).get("actl_pos", 0)
        cz = self._latest_motor_data.get(
            self._motor_for_axis(gantry_key, "Z"), {}).get("actl_pos", 0)

        dx, dy, dz = abs(tx - cx), abs(ty - cy), abs(tz - cz)

        if dy > 0.01 and not self._synced:
            QMessageBox.warning(
                self, "警告", "龙门未同步，无法执行 Y 轴运动！")
            return

        d_max = max(dx, dy, dz)
        if d_max < 0.001:
            QMessageBox.information(self, "提示", "已在目标位置附近")
            return

        min_speed = 0.1
        vx = max(v_max * dx / d_max, min_speed) if dx > 0.001 else min_speed
        vy = max(v_max * dy / d_max, min_speed) if dy > 0.001 else min_speed
        vz = max(v_max * dz / d_max, min_speed) if dz > 0.001 else min_speed

        motor_cmds = [
            (self._motor_for_axis(gantry_key, "X"), vx, tx),
            (self._motor_for_axis(gantry_key, "Z"), vz, tz),
            (self._motor_for_axis(gantry_key, "Y"), vy, ty),
        ]

        for motor_name, speed, target in motor_cmds:
            mc = self._motor_configs.get(motor_name)
            if mc is None:
                continue
            self._plc.add_write_task(
                "float", mc.register_addr("abs_vel_set"), speed)
            self._plc.add_write_task(
                "float", mc.register_addr("abs_pos_set"), target)

        bases = []
        for motor_name, _, _ in motor_cmds:
            mc = self._motor_configs.get(motor_name)
            if mc is None:
                continue
            self._plc.add_write_task(
                "register_bit", mc.base, 1,
                bit=mc.offset_of("abs_cmd"))
            bases.append(mc.base)

        def release():
            for b in bases:
                mc_release = next(
                    (m for m in self._motor_configs.values()
                     if m.base == b), None)
                if mc_release:
                    self._plc.add_write_task(
                        "register_bit", b, 0,
                        bit=mc_release.offset_of("abs_cmd"))

        QTimer.singleShot(200, release)

    def _refresh_table(self, gantry_key: str):
        table = self._point_tables[gantry_key]
        points = self._point_lists[gantry_key]
        table.setRowCount(len(points))
        for row, (x, y, z) in enumerate(points):
            table.setItem(row, 0, QTableWidgetItem(f"{x:.3f}"))
            table.setItem(row, 1, QTableWidgetItem(f"{y:.3f}"))
            table.setItem(row, 2, QTableWidgetItem(f"{z:.3f}"))

    # ---- enable / disable -------------------------------------------------

    def set_controls_enabled(self, enabled: bool):
        for mw in self._motor_widgets.values():
            mw.set_enabled_all(enabled)

    # ---- style helpers ----------------------------------------------------

    def _btn_style(self) -> str:
        return (
            f"QPushButton {{"
            f"  background-color: transparent; color: {BLUE_FUNC};"
            f"  border: 1px solid {BLUE_FUNC}; border-radius: 3px;"
            f"  padding: 5px 12px; font-size: {FONT_SIZE_SM}px;"
            f"}}"
            f"QPushButton:hover {{"
            f"  background-color: {BLUE_FUNC}; color: #FFF;"
            f"}}"
        )

    def _input_style(self) -> str:
        return (
            f"QLineEdit {{"
            f"  background-color: {BG_DARK}; color: {TEXT_PRIMARY};"
            f"  border: 1px solid {BORDER_CARD}; border-radius: 3px;"
            f"  padding: 4px 8px; font-family: {FONT_MONO};"
            f"  font-size: {FONT_SIZE_SM}px;"
            f"}}"
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

    def _tab_style(self) -> str:
        return (
            f"QTabWidget::pane {{"
            f"  border: 1px solid {BORDER_CARD};"
            f"  background-color: {BG_DARK};"
            f"}}"
            f"QTabBar::tab {{"
            f"  background-color: {BG_PANEL}; color: {TEXT_SECONDARY};"
            f"  border: 1px solid {BORDER_CARD};"
            f"  padding: 6px 16px; margin-right: 2px;"
            f"}}"
            f"QTabBar::tab:selected {{"
            f"  background-color: {BG_DARK}; color: {BLUE_FUNC};"
            f"  border-bottom: 2px solid {BLUE_FUNC};"
            f"}}"
        )

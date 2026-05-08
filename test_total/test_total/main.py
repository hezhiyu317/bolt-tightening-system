# main.py
import sys
import time
import threading
from PyQt5.QtWidgets import (QApplication, QMainWindow, QWidget, QVBoxLayout, 
                             QHBoxLayout, QGridLayout, QLabel, QLineEdit, 
                             QPushButton, QTabWidget, QGroupBox, QMessageBox,
                             QTableWidget, QTableWidgetItem, QHeaderView,
                             QAbstractItemView, QGraphicsView, QGraphicsScene,
                             QTextEdit)                               # 【修改】新增 QTextEdit
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QIntValidator, QPixmap

from camera_worker import CameraWorker
from pcl_bridge import PclBridge                                      # 【新增】

try:
    import pyvista as pv
    from pyvistaqt import QtInteractor
except ImportError:
    print("未检测到 pyvista 或 pyvistaqt，请使用 pip install pyvista pyvistaqt 安装")

from config import MOTOR_LIST, OFFSETS, SMALL_GANTRY, BIG_GANTRY
from plc_worker import PlcWorker
from ui_widgets import MotorWidget


class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("多轴电机及视觉控制系统 (集成结构光相机)")
        self.resize(1400, 950)
        
        # === 通讯层初始化 ===
        self.worker = PlcWorker("192.168.1.88")
        self.worker.connection_status.connect(self.on_connection_status)
        self.worker.data_updated.connect(self.update_ui_data)
        
        self.cam_worker = CameraWorker()
        self.cam_worker.connection_status.connect(self.on_camera_connection)
        self.cam_worker.image_grabbed.connect(self.on_camera_image_update)
        self.cam_worker.point_cloud_grabbed.connect(self.on_point_cloud_ready)
        
        # 【新增】点云处理桥接
        self.pcl_bridge = PclBridge()
        self.pcl_bridge.processing_finished.connect(self.on_pcl_processing_finished)
        self.pcl_bridge.processing_error.connect(self.on_pcl_processing_error)
        self.last_pcd_path = None
        
        # === 状态与缓存变量 ===
        self.motor_widgets = {}
        self.gantry_synced_status = False
        self.all_enable_flag = False
        
        self.latest_motor_data = {}
        self.latest_global_data = {}
        
        self.coord_inputs = {}
        self.point_tables = {}
        self.point_lists = {'small': [], 'big': []}
        self.integrated_btns = []
        self.integrated_inputs = []
        
        self.calib_state = 'IDLE'
        self.calib_z1 = 0.0
        self.calib_z2 = None
        self.calib_z3 = None
        self.calib_x_init = 0.0
        self.calib_y_init = 0.0
        self.calib_jog_start_time = 0
        self.calib_return_start_time = 0
        
        self.calib_timer = QTimer()
        self.calib_timer.setInterval(50)
        self.calib_timer.timeout.connect(self.check_calibration)
        
        self.init_ui()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QVBoxLayout(central_widget)
        
        # ================= 1. 顶部控制栏 =================
        top_layout = QHBoxLayout()
        
        top_layout.addWidget(QLabel("PLC IP:"))
        self.txt_ip = QLineEdit("192.168.1.88")
        self.txt_ip.setFixedWidth(110)
        top_layout.addWidget(self.txt_ip)
        
        self.btn_connect = QPushButton("连接 PLC")
        self.btn_connect.clicked.connect(self.toggle_connection)
        top_layout.addWidget(self.btn_connect)
        
        top_layout.addStretch()
        
        gantry_box = QGroupBox("龙门控制")
        gantry_layout = QHBoxLayout()
        gantry_layout.setContentsMargins(10, 5, 10, 5)
        
        self.btn_sync = QPushButton("龙门同步")
        self.btn_sync.clicked.connect(self.trigger_sync)
        self.btn_sync.setEnabled(False)
        
        self.lbl_sync_status = QLabel("未同步")
        self.lbl_sync_status.setStyleSheet("color: red; font-weight: bold; border: 1px solid gray; padding: 5px; background: #EEE;")
        self.lbl_sync_status.setFixedWidth(100)
        self.lbl_sync_status.setAlignment(Qt.AlignCenter)
        
        gantry_layout.addWidget(self.btn_sync)
        gantry_layout.addWidget(self.lbl_sync_status)
        gantry_box.setLayout(gantry_layout)
        top_layout.addWidget(gantry_box)
        
        top_layout.addStretch()
        
        estop_box = QGroupBox("全局控制")
        estop_layout = QHBoxLayout()
        estop_layout.setContentsMargins(10, 5, 10, 5)
        
        self.btn_brake = QPushButton("抱闸：锁死")
        self.btn_brake.setFixedSize(90, 40)
        self.btn_brake.setCheckable(True)
        self.btn_brake.clicked.connect(self.toggle_brake)
        self.btn_brake.setEnabled(False)
                
        self.btn_estop = QPushButton("总急停")
        self.btn_estop.setFixedSize(80, 40)
        self.btn_estop.setStyleSheet("background-color: red; color: white; font-weight: bold;")
        self.btn_estop.clicked.connect(self.global_estop)
        self.btn_estop.setEnabled(False)
        
        self.btn_global_enable = QPushButton("全轴使能")
        self.btn_global_enable.setFixedSize(80, 40)
        self.btn_global_enable.clicked.connect(self.toggle_all_enable)
        self.btn_global_enable.setEnabled(False)
        
        estop_layout.addWidget(self.btn_estop)
        estop_layout.addWidget(self.btn_brake)
        estop_layout.addWidget(self.btn_global_enable)
        estop_box.setLayout(estop_layout)
        top_layout.addWidget(estop_box)
        
        main_layout.addLayout(top_layout)
        
        # ================= 2. 标签页 =================
        self.tabs = QTabWidget()
        main_layout.addWidget(self.tabs)
        
        self.create_motor_tab("小龙门", ['Z_motor', 'X_motor', 'YL_motor', 'YR_motor'])
        self.create_motor_tab("大龙门", ['ZZ_motor', 'XX_motor', 'YLL_motor', 'YRR_motor'])
        self.create_motor_tab("旋转电机", ['SPF_motor', 'SPT_motor', 'SPM_motor', 'SPC_motor'])
        self.create_integrated_tab()
        self.create_calibration_tab()
        self.create_camera_tab()
        self.create_gun_tab()
        self.create_feeding_motors_tab()

    # ================= 结构光相机页面 =================
    def create_camera_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        
        # 1. 顶部控制栏
        cam_ctrl_layout = QHBoxLayout()
        
        self.btn_cam_connect = QPushButton("连接相机")
        self.btn_cam_connect.setFixedSize(120, 40)
        self.btn_cam_connect.clicked.connect(self.toggle_camera_connection)
        
        self.btn_cam_grab_3d = QPushButton("采集点云并显示")
        self.btn_cam_grab_3d.setFixedSize(150, 40)
        self.btn_cam_grab_3d.setStyleSheet("background-color: lightblue; font-weight: bold;")
        self.btn_cam_grab_3d.setEnabled(False)
        self.btn_cam_grab_3d.clicked.connect(self.trigger_3d_capture)
        
        # 【新增】处理点云按钮
        self.btn_process_pcl = QPushButton("运行算法处理")
        self.btn_process_pcl.setFixedSize(150, 40)
        self.btn_process_pcl.setStyleSheet("background-color: #FFD700; font-weight: bold;")
        self.btn_process_pcl.setEnabled(False)
        self.btn_process_pcl.clicked.connect(self.trigger_pcl_processing)
        
        self.lbl_cam_status = QLabel("相机状态: 未连接")
        self.lbl_cam_status.setStyleSheet("color: red; font-weight: bold; margin-left: 10px;")
        
        # 【新增】算法后端状态
        backend_text = f"算法后端: {self.pcl_bridge.backend or '不可用'}"
        self.lbl_pcl_backend = QLabel(backend_text)
        self.lbl_pcl_backend.setStyleSheet("color: gray; margin-left: 10px;")
        
        cam_ctrl_layout.addWidget(self.btn_cam_connect)
        cam_ctrl_layout.addWidget(self.btn_cam_grab_3d)
        cam_ctrl_layout.addWidget(self.btn_process_pcl)
        cam_ctrl_layout.addWidget(self.lbl_cam_status)
        cam_ctrl_layout.addWidget(self.lbl_pcl_backend)
        cam_ctrl_layout.addStretch()
        layout.addLayout(cam_ctrl_layout)
        
        # 2. 视觉显示子页面
        self.cam_sub_tabs = QTabWidget()
        
        # 2.1 实时画面 (2D)
        self.view_2d_widget = QWidget()
        layout_2d = QVBoxLayout(self.view_2d_widget)
        self.scene_2d = QGraphicsScene()
        self.view_2d = QGraphicsView(self.scene_2d)
        self.view_2d.setStyleSheet("background-color: #2b2b2b;")
        self.view_2d.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.view_2d.setVerticalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        self.pixmap_item = self.scene_2d.addPixmap(QPixmap())
        layout_2d.addWidget(self.view_2d)
        self.cam_sub_tabs.addTab(self.view_2d_widget, "实时画面 (2D)")
        
        # 2.2 点云显示 (3D)
        self.view_3d_widget = QWidget()
        layout_3d = QVBoxLayout(self.view_3d_widget)
        try:
            self.plotter = QtInteractor(self.view_3d_widget)
            layout_3d.addWidget(self.plotter.interactor)
            self.plotter.add_text("等待采集 3D 点云...", font_size=12)
        except Exception as e:
            err_lbl = QLabel(f"PyVista 初始化失败: {e}")
            err_lbl.setStyleSheet("color: red; font-size: 14px;")
            layout_3d.addWidget(err_lbl)
        self.cam_sub_tabs.addTab(self.view_3d_widget, "点云显示 (3D)")
        
        # 【新增】2.3 算法结果页面
        self.view_result_widget = QWidget()
        layout_result = QVBoxLayout(self.view_result_widget)
        
        # 结果摘要
        result_summary = QGroupBox("处理结果")
        summary_grid = QGridLayout()
        self.lbl_result_status = QLabel("等待处理...")
        self.lbl_result_status.setStyleSheet("font-weight: bold; font-size: 14px;")
        summary_grid.addWidget(QLabel("状态:"), 0, 0)
        summary_grid.addWidget(self.lbl_result_status, 0, 1, 1, 3)
        
        self.lbl_result_center = QLabel("--")
        self.lbl_result_center.setStyleSheet("color: darkblue; font-weight: bold; font-size: 16px;")
        summary_grid.addWidget(QLabel("圆心坐标:"), 1, 0)
        summary_grid.addWidget(self.lbl_result_center, 1, 1, 1, 3)
        
        self.lbl_result_radius = QLabel("--")
        self.lbl_result_radius.setStyleSheet("color: darkgreen; font-weight: bold; font-size: 14px;")
        summary_grid.addWidget(QLabel("拟合半径:"), 2, 0)
        summary_grid.addWidget(self.lbl_result_radius, 2, 1)
        
        self.lbl_result_plane = QLabel("--")
        summary_grid.addWidget(QLabel("平面方程:"), 3, 0)
        summary_grid.addWidget(self.lbl_result_plane, 3, 1, 1, 3)
        
        self.lbl_result_stats = QLabel("--")
        summary_grid.addWidget(QLabel("点数统计:"), 4, 0)
        summary_grid.addWidget(self.lbl_result_stats, 4, 1, 1, 3)
        
        result_summary.setLayout(summary_grid)
        layout_result.addWidget(result_summary)
        
        # 详细日志
        log_group = QGroupBox("处理日志")
        log_layout = QVBoxLayout()
        self.txt_pcl_log = QTextEdit()
        self.txt_pcl_log.setReadOnly(True)
        self.txt_pcl_log.setMaximumHeight(200)
        self.txt_pcl_log.setStyleSheet("font-family: Consolas, monospace; font-size: 11px;")
        log_layout.addWidget(self.txt_pcl_log)
        log_group.setLayout(log_layout)
        layout_result.addWidget(log_group)
        
        layout_result.addStretch()
        self.cam_sub_tabs.addTab(self.view_result_widget, "算法结果")
        
        layout.addWidget(self.cam_sub_tabs)
        self.tabs.addTab(tab, "结构光相机")

    # ----- 相机操作槽函数 -----
    def toggle_camera_connection(self):
        if not self.cam_worker.is_connected:
            self.btn_cam_connect.setText("连接中...")
            self.btn_cam_connect.setEnabled(False)
            threading.Thread(target=self.cam_worker.connect_camera, daemon=True).start()
        else:
            self.cam_worker.disconnect_camera()

    def on_camera_connection(self, is_connected, msg):
        self.btn_cam_connect.setEnabled(True)
        if is_connected:
            self.btn_cam_connect.setText("断开相机")
            self.btn_cam_connect.setStyleSheet("background-color: lightgreen;")
            self.lbl_cam_status.setText(f"相机状态: {msg}")
            self.lbl_cam_status.setStyleSheet("color: green; font-weight: bold; margin-left: 10px;")
            self.btn_cam_grab_3d.setEnabled(True)
            self.cam_sub_tabs.setCurrentIndex(0)
        else:
            self.btn_cam_connect.setText("连接相机")
            self.btn_cam_connect.setStyleSheet("")
            self.lbl_cam_status.setText(f"相机状态: {msg}")
            self.lbl_cam_status.setStyleSheet("color: red; font-weight: bold; margin-left: 10px;")
            self.btn_cam_grab_3d.setEnabled(False)
            self.btn_process_pcl.setEnabled(False)
            self.pixmap_item.setPixmap(QPixmap())

    def on_camera_image_update(self, img_path):
        pixmap = QPixmap(img_path)
        if not pixmap.isNull():
            self.pixmap_item.setPixmap(pixmap)
            self.view_2d.fitInView(self.pixmap_item, Qt.KeepAspectRatio)

    def trigger_3d_capture(self):
        self.btn_cam_grab_3d.setEnabled(False)
        self.btn_cam_grab_3d.setText("采集中...")
        self.cam_worker.trigger_3d_capture()

    def on_point_cloud_ready(self, pcd_path):
        self.btn_cam_grab_3d.setEnabled(True)
        self.btn_cam_grab_3d.setText("采集点云并显示")
        self.cam_sub_tabs.setCurrentIndex(1)
        
        # 【新增】记录最新点云路径，启用处理按钮
        self.last_pcd_path = pcd_path
        if self.pcl_bridge.is_available:
            self.btn_process_pcl.setEnabled(True)
        
        try:
            if hasattr(self, 'plotter'):
                self.plotter.clear()
                import open3d as o3d
                import numpy as np
                pcd = o3d.io.read_point_cloud(pcd_path)
                points = np.asarray(pcd.points)
                if len(points) == 0:
                    QMessageBox.warning(self, "警告", "读取到的点云数据为空")
                    return
                mesh = pv.PolyData(points)
                self.plotter.add_mesh(mesh, scalars=points[:, 2], cmap='viridis', point_size=2.0)
                self.plotter.reset_camera()
        except Exception as e:
            import traceback
            traceback.print_exc()
            QMessageBox.warning(self, "错误", f"无法渲染点云: {e}")

    # 【新增】----- 点云算法处理槽函数 -----
    def trigger_pcl_processing(self):
        if not self.last_pcd_path:
            QMessageBox.warning(self, "提示", "请先采集点云")
            return
        
        self.btn_process_pcl.setEnabled(False)
        self.btn_process_pcl.setText("处理中...")
        self.lbl_result_status.setText("正在处理...")
        self.lbl_result_status.setStyleSheet("font-weight: bold; font-size: 14px; color: orange;")
        self.txt_pcl_log.clear()
        
        # 可在此设置算法参数
        params = {
            'plane_distance_threshold': 0.05,
            'edge_search_radius': 2.0,
            # 'edge_k_neighbors': 50,
            'edge_num_threads': 4,
            # 'edge_curvature_thresh': 0.04,
            'cluster_tolerance': 2.0,
            'min_cluster_size': 50,
            'max_cluster_size': 1000,
            'input_in_millimeters': True,
        }
        self.pcl_bridge.process_pcd(self.last_pcd_path, params)

    def on_pcl_processing_finished(self, result):
        self.btn_process_pcl.setEnabled(True)
        self.btn_process_pcl.setText("运行算法处理")
        
        # 自动切到结果页
        self.cam_sub_tabs.setCurrentIndex(2)
        
        if result.get('success'):
            cx = result['center_x']
            cy = result['center_y']
            cz = result['center_z']
            r  = result['radius']
            
            self.lbl_result_status.setText("✅ 处理成功")
            self.lbl_result_status.setStyleSheet("font-weight: bold; font-size: 14px; color: green;")
            self.lbl_result_center.setText(f"({cx:.4f},  {cy:.4f},  {cz:.4f})")
            self.lbl_result_radius.setText(f"{r:.4f} mm")
            self.lbl_result_plane.setText(
                f"{result['plane_a']:.6f}x + {result['plane_b']:.6f}y + "
                f"{result['plane_c']:.6f}z + {result['plane_d']:.6f} = 0")
            self.lbl_result_stats.setText(
                f"原始: {result['original_points']}  有效: {result['valid_points']}  "
                f"平面: {result['plane_points']}  边缘: {result['edge_points']}  "
                f"聚类: {result['cluster_points']}")
        else:
            self.lbl_result_status.setText(f"❌ 处理失败: {result.get('message', '未知')}")
            self.lbl_result_status.setStyleSheet("font-weight: bold; font-size: 14px; color: red;")
            self.lbl_result_center.setText("--")
            self.lbl_result_radius.setText("--")
            self.lbl_result_plane.setText("--")
            self.lbl_result_stats.setText("--")
        
        self.txt_pcl_log.setPlainText(result.get('log', ''))

    def on_pcl_processing_error(self, error_msg):
        self.btn_process_pcl.setEnabled(True)
        self.btn_process_pcl.setText("运行算法处理")
        self.lbl_result_status.setText(f"⚠ 错误: {error_msg}")
        self.lbl_result_status.setStyleSheet("font-weight: bold; font-size: 14px; color: red;")
        self.cam_sub_tabs.setCurrentIndex(2)

    # ================= 以下为原有电机控制代码 =================
    
    def create_motor_tab(self, title, names):
        tab = QWidget()
        layout = QGridLayout(tab)
        for i, name in enumerate(names):
            info = next(m for m in MOTOR_LIST if m['name'] == name)
            widget = MotorWidget(info)
            widget.write_requested.connect(
                lambda task: self.worker.add_write_task(task['type'], task['addr'], task['val'], task.get('bit'))
            )
            self.motor_widgets[name] = widget
            layout.addWidget(widget, i // 2, i % 2)
        self.tabs.addTab(tab, title)

    def create_integrated_tab(self):
        tab = QWidget()
        main_layout = QHBoxLayout(tab)
        
        for gantry_key, gantry_name in [('small', '小龙门'), ('big', '大龙门')]:
            group = QGroupBox(f"{gantry_name} 三坐标控制")
            layout = QVBoxLayout()
            
            input_layout = QGridLayout()
            inputs = {}
            for i, axis in enumerate(['X', 'Y', 'Z']):
                input_layout.addWidget(QLabel(f"{axis}:"), 0, i * 2)
                inp = QLineEdit("0.0")
                inp.setFixedWidth(90)
                inputs[axis] = inp
                self.integrated_inputs.append(inp)
                input_layout.addWidget(inp, 0, i * 2 + 1)
            
            input_layout.addWidget(QLabel("速度上限:"), 1, 0)
            speed_inp = QLineEdit("10.0")
            speed_inp.setFixedWidth(90)
            inputs['speed'] = speed_inp
            self.integrated_inputs.append(speed_inp)
            input_layout.addWidget(speed_inp, 1, 1)
            
            layout.addLayout(input_layout)
            self.coord_inputs[gantry_key] = inputs
            
            btn_layout = QHBoxLayout()
            
            btn_read = QPushButton("读取当前位置")
            btn_read.clicked.connect(lambda checked, k=gantry_key: self.read_current_position(k))
            btn_layout.addWidget(btn_read)
            self.integrated_btns.append(btn_read)
            
            btn_record = QPushButton("记录点位")
            btn_record.clicked.connect(lambda checked, k=gantry_key: self.record_point(k))
            btn_layout.addWidget(btn_record)
            self.integrated_btns.append(btn_record)
            
            btn_move = QPushButton("运动到当前点位")
            btn_move.setStyleSheet("background-color: lightblue; font-weight: bold;")
            btn_move.clicked.connect(lambda checked, k=gantry_key: self.move_to_point(k))
            btn_layout.addWidget(btn_move)
            self.integrated_btns.append(btn_move)
            
            layout.addLayout(btn_layout)
            
            table = QTableWidget(0, 3)
            table.setHorizontalHeaderLabels(['X', 'Y', 'Z'])
            table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
            table.setSelectionBehavior(QAbstractItemView.SelectRows)
            table.setEditTriggers(QAbstractItemView.NoEditTriggers)
            table.cellClicked.connect(lambda row, col, k=gantry_key: self.load_point_from_table(k, row))
            self.point_tables[gantry_key] = table
            layout.addWidget(table)
            
            btn_delete = QPushButton("删除选中点位")
            btn_delete.clicked.connect(lambda checked, k=gantry_key: self.delete_selected_point(k))
            layout.addWidget(btn_delete)
            self.integrated_btns.append(btn_delete)
            
            group.setLayout(layout)
            main_layout.addWidget(group)
        
        self.tabs.addTab(tab, "一体化界面")

    def read_current_position(self, gantry_key):
        if gantry_key == 'small':
            x_m, y_m, z_m = 'X_motor', 'YL_motor', 'Z_motor'
        else:
            x_m, y_m, z_m = 'XX_motor', 'YLL_motor', 'ZZ_motor'
        
        x = self.latest_motor_data.get(x_m, {}).get('act_pos', 0.0)
        y = self.latest_motor_data.get(y_m, {}).get('act_pos', 0.0)
        z = self.latest_motor_data.get(z_m, {}).get('act_pos', 0.0)
        
        self.coord_inputs[gantry_key]['X'].setText(f"{x:.3f}")
        self.coord_inputs[gantry_key]['Y'].setText(f"{y:.3f}")
        self.coord_inputs[gantry_key]['Z'].setText(f"{z:.3f}")

    def record_point(self, gantry_key):
        try:
            x = float(self.coord_inputs[gantry_key]['X'].text())
            y = float(self.coord_inputs[gantry_key]['Y'].text())
            z = float(self.coord_inputs[gantry_key]['Z'].text())
        except ValueError:
            QMessageBox.warning(self, "错误", "请输入有效的坐标值")
            return
        
        points = self.point_lists[gantry_key]
        if len(points) >= 10:
            QMessageBox.warning(self, "提示", "点位列表已满，请先删除旧点位")
            return
        
        points.append((x, y, z))
        self._refresh_point_table(gantry_key)

    def _refresh_point_table(self, gantry_key):
        table = self.point_tables[gantry_key]
        points = self.point_lists[gantry_key]
        table.setRowCount(len(points))
        for row, (x, y, z) in enumerate(points):
            table.setItem(row, 0, QTableWidgetItem(f"{x:.3f}"))
            table.setItem(row, 1, QTableWidgetItem(f"{y:.3f}"))
            table.setItem(row, 2, QTableWidgetItem(f"{z:.3f}"))

    def load_point_from_table(self, gantry_key, row):
        points = self.point_lists[gantry_key]
        if 0 <= row < len(points):
            x, y, z = points[row]
            self.coord_inputs[gantry_key]['X'].setText(f"{x:.3f}")
            self.coord_inputs[gantry_key]['Y'].setText(f"{y:.3f}")
            self.coord_inputs[gantry_key]['Z'].setText(f"{z:.3f}")

    def delete_selected_point(self, gantry_key):
        table = self.point_tables[gantry_key]
        rows = sorted(set(item.row() for item in table.selectedItems()), reverse=True)
        if not rows: return
        for row in rows:
            if 0 <= row < len(self.point_lists[gantry_key]):
                self.point_lists[gantry_key].pop(row)
        self._refresh_point_table(gantry_key)

    def move_to_point(self, gantry_key):
        try:
            tx = float(self.coord_inputs[gantry_key]['X'].text())
            ty = float(self.coord_inputs[gantry_key]['Y'].text())
            tz = float(self.coord_inputs[gantry_key]['Z'].text())
            v_max = float(self.coord_inputs[gantry_key]['speed'].text())
        except ValueError:
            QMessageBox.warning(self, "错误", "请输入有效的数值")
            return
        
        if v_max <= 0:
            QMessageBox.warning(self, "错误", "速度上限必须大于0")
            return
        
        axes = SMALL_GANTRY if gantry_key == 'small' else BIG_GANTRY
        x_motor, y_master_motor, z_motor = axes['X'], axes['Y_left'], axes['Z']
        
        cx = self.latest_motor_data.get(x_motor, {}).get('act_pos', 0.0)
        cy = self.latest_motor_data.get(y_master_motor, {}).get('act_pos', 0.0)
        cz = self.latest_motor_data.get(z_motor, {}).get('act_pos', 0.0)
        
        dx, dy, dz = abs(tx - cx), abs(ty - cy), abs(tz - cz)
        
        if dy > 0.01 and not self.gantry_synced_status:
            QMessageBox.warning(self, "警告", "龙门未同步，无法执行 Y 轴运动！")
            return
        
        d_max = max(dx, dy, dz)
        if d_max < 0.001:
            QMessageBox.information(self, "提示", "已在目标位置附近")
            return
        
        MIN_SPEED = 0.1
        vx = max(v_max * dx / d_max, MIN_SPEED) if dx > 0.001 else MIN_SPEED
        vy = max(v_max * dy / d_max, MIN_SPEED) if dy > 0.001 else MIN_SPEED
        vz = max(v_max * dz / d_max, MIN_SPEED) if dz > 0.001 else MIN_SPEED
        
        motor_cmds = [(x_motor, vx, tx), (z_motor, vz, tz), (y_master_motor, vy, ty)]
        
        for motor_name, speed, target in motor_cmds:
            base = next(m for m in MOTOR_LIST if m['name'] == motor_name)['base']
            self.worker.add_write_task('float', base + OFFSETS['abs_vel_set'], speed)
            self.worker.add_write_task('float', base + OFFSETS['abs_pos_set'], target)
        
        bases_to_trigger = []
        for motor_name, _, _ in motor_cmds:
            base = next(m for m in MOTOR_LIST if m['name'] == motor_name)['base']
            self.worker.add_write_task('register_bit', base, 1, bit=OFFSETS['abs_cmd'])
            bases_to_trigger.append(base)
        
        def release_abs():
            for b in bases_to_trigger:
                self.worker.add_write_task('register_bit', b, 0, bit=OFFSETS['abs_cmd'])
        QTimer.singleShot(200, release_abs)

    def create_calibration_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignTop)
        
        ctrl_group = QGroupBox("标定控制（大龙门 Z 轴）")
        ctrl_layout = QVBoxLayout()
        
        init_layout = QHBoxLayout()
        self.calib_init_labels = {}
        for axis in ['X', 'Y', 'Z']:
            init_layout.addWidget(QLabel(f"初始{axis}:"))
            lbl = QLabel("--")
            lbl.setStyleSheet("font-weight: bold; color: darkblue; min-width: 70px;")
            self.calib_init_labels[axis] = lbl
            init_layout.addWidget(lbl)
        init_layout.addStretch()
        ctrl_layout.addLayout(init_layout)
        
        speed_layout = QHBoxLayout()
        speed_layout.addWidget(QLabel("下行点动速度:"))
        self.calib_jog_speed_input = QLineEdit("5.0")
        self.calib_jog_speed_input.setFixedWidth(70)
        speed_layout.addWidget(self.calib_jog_speed_input)
        speed_layout.addSpacing(20)
        speed_layout.addWidget(QLabel("回退速度:"))
        self.calib_return_speed_input = QLineEdit("10.0")
        self.calib_return_speed_input.setFixedWidth(70)
        speed_layout.addWidget(self.calib_return_speed_input)
        speed_layout.addStretch()
        ctrl_layout.addLayout(speed_layout)
        
        btn_layout = QHBoxLayout()
        self.btn_calib_start = QPushButton("开始一次标定")
        self.btn_calib_start.clicked.connect(self.calib_start)
        btn_layout.addWidget(self.btn_calib_start)
        
        self.btn_calib_execute = QPushButton("执行标定")
        self.btn_calib_execute.setStyleSheet("background-color: lightyellow; font-weight: bold;")
        self.btn_calib_execute.clicked.connect(self.calib_execute)
        self.btn_calib_execute.setEnabled(False)
        btn_layout.addWidget(self.btn_calib_execute)
        
        self.btn_calib_next = QPushButton("下一步")
        self.btn_calib_next.clicked.connect(self.calib_next)
        self.btn_calib_next.setEnabled(False)
        btn_layout.addWidget(self.btn_calib_next)
        
        self.btn_calib_cancel = QPushButton("取消标定")
        self.btn_calib_cancel.setStyleSheet("background-color: #FFCCCC;")
        self.btn_calib_cancel.clicked.connect(self.calib_cancel)
        self.btn_calib_cancel.setEnabled(False)
        btn_layout.addWidget(self.btn_calib_cancel)
        ctrl_layout.addLayout(btn_layout)
        
        status_layout = QHBoxLayout()
        status_layout.addWidget(QLabel("状态:"))
        self.lbl_calib_status = QLabel("空闲")
        self.lbl_calib_status.setStyleSheet("font-weight: bold; font-size: 13px;")
        status_layout.addWidget(self.lbl_calib_status)
        status_layout.addStretch()
        
        status_layout.addWidget(QLabel("X1传感器:"))
        self.lbl_calib_x1 = QLabel("OFF")
        self.lbl_calib_x1.setFixedWidth(50)
        self.lbl_calib_x1.setAlignment(Qt.AlignCenter)
        self.lbl_calib_x1.setStyleSheet("color: red; font-weight: bold;")
        status_layout.addWidget(self.lbl_calib_x1)
        
        status_layout.addSpacing(10)
        status_layout.addWidget(QLabel("当前Z:"))
        self.lbl_calib_current_z = QLabel("--")
        self.lbl_calib_current_z.setStyleSheet("font-weight: bold; color: darkblue; min-width: 70px;")
        status_layout.addWidget(self.lbl_calib_current_z)
        ctrl_layout.addLayout(status_layout)
        
        ctrl_group.setLayout(ctrl_layout)
        layout.addWidget(ctrl_group)
        
        result_group = QGroupBox("标定结果列表")
        result_layout = QVBoxLayout()
        
        self.calib_result_table = QTableWidget(0, 7)
        self.calib_result_table.setHorizontalHeaderLabels(
            ['序号', 'Z1(初始)', 'Z2(接触)', 'Z3(回退)', '接触差|Z1-Z2|', '回退差|Z1-Z3|', '平均差']
        )
        self.calib_result_table.horizontalHeader().setSectionResizeMode(QHeaderView.Stretch)
        self.calib_result_table.setEditTriggers(QAbstractItemView.NoEditTriggers)
        result_layout.addWidget(self.calib_result_table)
        
        btn_clear = QPushButton("清空结果")
        btn_clear.clicked.connect(lambda: self.calib_result_table.setRowCount(0))
        result_layout.addWidget(btn_clear)
        
        result_group.setLayout(result_layout)
        layout.addWidget(result_group)
        self.tabs.addTab(tab, "末端标定")

    def calib_start(self):
        zz_pos = self.latest_motor_data.get('ZZ_motor', {}).get('act_pos', 0.0)
        xx_pos = self.latest_motor_data.get('XX_motor', {}).get('act_pos', 0.0)
        yll_pos = self.latest_motor_data.get('YLL_motor', {}).get('act_pos', 0.0)
        
        self.calib_x_init, self.calib_y_init, self.calib_z1 = xx_pos, yll_pos, zz_pos
        self.calib_z2 = self.calib_z3 = None
        
        self.calib_init_labels['X'].setText(f"{xx_pos:.3f}")
        self.calib_init_labels['Y'].setText(f"{yll_pos:.3f}")
        self.calib_init_labels['Z'].setText(f"{zz_pos:.3f}")
        
        self.calib_state = 'READY'
        self.btn_calib_start.setEnabled(False)
        self.btn_calib_execute.setEnabled(True)
        self.btn_calib_cancel.setEnabled(True)
        self.btn_calib_next.setEnabled(False)
        self.lbl_calib_status.setText(f'已记录初始位置 Z1={zz_pos:.3f}，请点击执行标定')

    def calib_execute(self):
        try: jog_speed = float(self.calib_jog_speed_input.text())
        except ValueError: return
        
        zz_base = next(m for m in MOTOR_LIST if m['name'] == 'ZZ_motor')['base']
        self.worker.add_write_task('float', zz_base + OFFSETS['jog_vel_set'], jog_speed)
        self.worker.add_write_task('register_bit', zz_base, 1, bit=OFFSETS['jog_b_cmd'])
        
        self.calib_state = 'JOGGING'
        self.calib_jog_start_time = time.time()
        self.btn_calib_execute.setEnabled(False)
        self.lbl_calib_status.setText("Z 轴下行中，等待 X1 传感器触发...")
        self.calib_timer.start()

    def calib_next(self):
        try: return_speed = float(self.calib_return_speed_input.text())
        except ValueError: return
        
        zz_base = next(m for m in MOTOR_LIST if m['name'] == 'ZZ_motor')['base']
        self.worker.add_write_task('float', zz_base + OFFSETS['abs_vel_set'], return_speed)
        self.worker.add_write_task('float', zz_base + OFFSETS['abs_pos_set'], self.calib_z1)
        self.worker.add_write_task('register_bit', zz_base, 1, bit=OFFSETS['abs_cmd'])
        QTimer.singleShot(200, lambda: self.worker.add_write_task('register_bit', zz_base, 0, bit=OFFSETS['abs_cmd']))
        
        self.calib_state = 'RETURNING'
        self.calib_return_start_time = time.time()
        self.btn_calib_next.setEnabled(False)
        self.lbl_calib_status.setText("回退中，监测 X1 释放...")
        self.calib_timer.start()

    def calib_cancel(self):
        zz_base = next(m for m in MOTOR_LIST if m['name'] == 'ZZ_motor')['base']
        self.worker.add_write_task('register_bit', zz_base, 0, bit=OFFSETS['jog_b_cmd'])
        
        self.calib_state = 'IDLE'
        self.calib_timer.stop()
        self.btn_calib_start.setEnabled(True)
        self.btn_calib_execute.setEnabled(False)
        self.btn_calib_next.setEnabled(False)
        self.btn_calib_cancel.setEnabled(False)
        self.lbl_calib_status.setText("已取消标定")

    def check_calibration(self):
        if not self.latest_motor_data: return
        
        x1 = self.latest_global_data.get('x1_status', False)
        zz_data = self.latest_motor_data.get('ZZ_motor', {})
        zz_pos, zz_vel = zz_data.get('act_pos', 0.0), abs(zz_data.get('act_vel', 0.0))
        
        self.lbl_calib_x1.setText("ON" if x1 else "OFF")
        self.lbl_calib_x1.setStyleSheet("color: white; background: green; font-weight: bold; padding: 2px;" if x1 else "color: red; font-weight: bold; padding: 2px;")
        self.lbl_calib_current_z.setText(f"{zz_pos:.3f}")
        
        if self.calib_state == 'JOGGING':
            if x1:
                zz_base = next(m for m in MOTOR_LIST if m['name'] == 'ZZ_motor')['base']
                self.worker.add_write_task('register_bit', zz_base, 0, bit=OFFSETS['jog_b_cmd'])
                self.calib_z2 = zz_pos
                self.calib_state = 'CONTACTED'
                self.calib_timer.stop()
                self.btn_calib_next.setEnabled(True)
                self.lbl_calib_status.setText(f'接触检测! Z2={zz_pos:.3f}，请点击"下一步"回退')
            elif time.time() - self.calib_jog_start_time > 120:
                self.calib_cancel()
                self.lbl_calib_status.setText("标定超时（120秒未检测到接触）")
        elif self.calib_state == 'RETURNING':
            if not x1 and self.calib_z3 is None:
                self.calib_z3 = zz_pos
                self.lbl_calib_status.setText(f"X1 已释放，Z3={zz_pos:.3f}，等待回到初始位置...")
            
            if time.time() - self.calib_return_start_time > 1.0:
                if abs(zz_pos - self.calib_z1) < 0.1 and zz_vel < 1.0:
                    self.finish_calibration()

    def finish_calibration(self):
        self.calib_timer.stop()
        z1, z2, z3 = self.calib_z1, self.calib_z2 or self.calib_z1, self.calib_z3 or self.calib_z1
        contact_diff, retract_diff = abs(z1 - z2), abs(z1 - z3)
        avg_diff = (contact_diff + retract_diff) / 2.0
        
        row = self.calib_result_table.rowCount()
        self.calib_result_table.insertRow(row)
        for col, val in enumerate([str(row + 1), f"{z1:.3f}", f"{z2:.3f}", f"{z3:.3f}", f"{contact_diff:.3f}", f"{retract_diff:.3f}", f"{avg_diff:.3f}"]):
            item = QTableWidgetItem(val)
            item.setTextAlignment(Qt.AlignCenter)
            self.calib_result_table.setItem(row, col, item)
        
        self.calib_state = 'IDLE'
        self.btn_calib_start.setEnabled(True)
        self.btn_calib_execute.setEnabled(False)
        self.btn_calib_cancel.setEnabled(False)
        self.lbl_calib_status.setText(f"标定完成! 接触差={contact_diff:.3f}, 回退差={retract_diff:.3f}, 平均差={avg_diff:.3f}")

    def create_gun_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)
        layout.setAlignment(Qt.AlignTop)

        gun_box = QGroupBox("拧紧枪启停控制")
        gun_layout = QHBoxLayout()
        self.gun_btns = []
        for text, addr in [("启动 (M13)", 13), ("复位 (M14)", 14), ("正转 (M15)", 15), ("反转 (M16)", 16)]:
            btn = QPushButton(text)
            btn.setFixedSize(150, 50)
            btn.pressed.connect(lambda a=addr: self.worker.add_write_task('coil', a, True))
            btn.released.connect(lambda a=addr: self.worker.add_write_task('coil', a, False))
            btn.setEnabled(False)
            gun_layout.addWidget(btn)
            self.gun_btns.append(btn)
        gun_box.setLayout(gun_layout)
        layout.addWidget(gun_box)

        self.valve_btns = []
        valves_names = [f"A{i}" for i in range(1, 9)] + [f"B{i}" for i in range(1, 9)]
        for title, reg_addr in [("D21 (A1-A8, B1-B8)", 21), ("D22", 22), ("D23", 23), ("D24", 24)]:
            box = QGroupBox(title)
            grid = QGridLayout()
            for bit_index, valve_name in enumerate(valves_names):
                btn = QPushButton(valve_name)
                btn.setCheckable(True)
                btn.setEnabled(False)
                btn.clicked.connect(lambda checked, b=bit_index, addr=reg_addr, current_btn=btn: 
                    self.toggle_valve_state(checked, addr, b, current_btn))
                self.valve_btns.append(btn)
                grid.addWidget(btn, bit_index // 8, bit_index % 8)
            box.setLayout(grid)
            layout.addWidget(box)

        layout.addStretch()
        self.tabs.addTab(tab, "拧紧枪 & 电磁阀")

    def toggle_valve_state(self, checked, addr, bit_index, btn):
        btn.setStyleSheet("background-color: #00FF00; color: black;" if checked else "")
        self.worker.add_write_task('register_bit', addr, int(checked), bit=bit_index)

    def create_feeding_motors_tab(self):
        tab = QWidget()
        layout = QHBoxLayout(tab)
        
        self.feed_inputs = []
        self.feed_btns = []
        validator = QIntValidator(0, 5000)

        left_box = QGroupBox("独立电压设置 (D10 - D17)")
        left_layout = QVBoxLayout()
        grid = QGridLayout()
        for i in range(8):
            grid.addWidget(QLabel(f"电机 {i+1} (D{10+i}):"), i, 0)
            inp = QLineEdit("0")
            inp.setValidator(validator)
            self.feed_inputs.append(inp)
            grid.addWidget(inp, i, 1)
        left_layout.addLayout(grid)
        
        btn_sync_indiv = QPushButton("同步设置值到模块")
        btn_sync_indiv.clicked.connect(self.sync_feed_individual)
        btn_start_indiv = QPushButton("启动电机 (触发 M17)")
        btn_start_indiv.setStyleSheet("background-color: lightblue; font-weight: bold;")
        btn_start_indiv.clicked.connect(self.trigger_m17)
        self.feed_btns.extend([btn_sync_indiv, btn_start_indiv])
        left_layout.addWidget(btn_sync_indiv)
        left_layout.addWidget(btn_start_indiv)
        left_layout.addStretch()
        left_box.setLayout(left_layout)
        layout.addWidget(left_box)

        right_box = QGroupBox("集体控制区")
        right_layout = QVBoxLayout()
        right_layout.setAlignment(Qt.AlignTop)

        btn_estop_feed = QPushButton("急停 (置0并触发M17)")
        btn_estop_feed.setFixedSize(200, 50)
        btn_estop_feed.setStyleSheet("background-color: red; color: white; font-weight: bold;")
        btn_estop_feed.clicked.connect(self.estop_feed_motors)
        right_layout.addWidget(btn_estop_feed)
        right_layout.addSpacing(20)

        h_layout = QHBoxLayout()
        h_layout.addWidget(QLabel("共同电压设置:"))
        self.common_feed_input = QLineEdit("0")
        self.common_feed_input.setValidator(validator)
        h_layout.addWidget(self.common_feed_input)
        right_layout.addLayout(h_layout)

        btn_sync_common = QPushButton("设置到模块 (全轴同步)")
        btn_sync_common.clicked.connect(self.sync_feed_common)
        btn_start_common = QPushButton("同时启动 (触发 M17)")
        btn_start_common.setStyleSheet("background-color: lightblue; font-weight: bold;")
        btn_start_common.clicked.connect(self.trigger_m17)
        self.btn_toggle_dir = QPushButton("切换电机: 正转 (M19=0)")
        self.btn_toggle_dir.setCheckable(True)
        self.btn_toggle_dir.clicked.connect(self.toggle_feed_direction)
        
        right_layout.addWidget(btn_sync_common)
        right_layout.addWidget(btn_start_common)
        right_layout.addSpacing(20)
        right_layout.addWidget(self.btn_toggle_dir)
        self.feed_btns.extend([btn_estop_feed, btn_sync_common, btn_start_common, self.btn_toggle_dir])
        right_box.setLayout(right_layout)
        layout.addWidget(right_box)

        self.tabs.addTab(tab, "送料电机")

    def sync_feed_individual(self):
        for i, inp in enumerate(self.feed_inputs):
            self.worker.add_write_task('int16', 10 + i, int(inp.text() or 0))

    def sync_feed_common(self):
        val = int(self.common_feed_input.text() or 0)
        for addr in range(10, 18):
            self.worker.add_write_task('int16', addr, val)

    def trigger_m17(self):
        self.worker.add_write_task('coil', 17, True)
        QTimer.singleShot(200, lambda: self.worker.add_write_task('coil', 17, False))

    def estop_feed_motors(self):
        for addr in range(10, 18): self.worker.add_write_task('int16', addr, 0)
        self.trigger_m17()

    def toggle_feed_direction(self, checked):
        if checked:
            self.btn_toggle_dir.setText("切换电机: 反转 (M19=1)")
            self.btn_toggle_dir.setStyleSheet("background-color: orange; font-weight: bold;")
        else:
            self.btn_toggle_dir.setText("切换电机: 正转 (M19=0)")
            self.btn_toggle_dir.setStyleSheet("")
        self.worker.add_write_task('coil', 19, checked)

    # ================= 基础通讯与控制 =================
    def toggle_connection(self):
        if self.btn_connect.text() == "连接 PLC":
            self.btn_connect.setText("连接中...")
            self.btn_connect.setEnabled(False)
            self.worker.ip = self.txt_ip.text()
            self.worker.connect_plc()
        else:
            self.btn_connect.setText("断开中...")
            self.btn_connect.setEnabled(False)
            self.worker.disconnect_plc()

    def on_connection_status(self, connected, msg):
        self.btn_connect.setEnabled(True)
        if connected:
            self.btn_connect.setText("断开")
            self.btn_connect.setStyleSheet("background-color: lightgreen;")
            self.enable_controls(True)
        else:
            self.btn_connect.setText("连接 PLC")
            self.btn_connect.setStyleSheet("")
            self.enable_controls(False)
            if "异常" in msg or "超时" in msg:
                QMessageBox.warning(self, "连接提示", msg)

    def enable_controls(self, enable):
        self.btn_sync.setEnabled(enable)
        self.btn_estop.setEnabled(enable)
        self.btn_global_enable.setEnabled(enable)
        
        if hasattr(self, 'btn_brake'): self.btn_brake.setEnabled(enable)
        for w in self.motor_widgets.values(): w.set_enabled_all(enable)
        for b in self.gun_btns: b.setEnabled(enable)
        if hasattr(self, 'valve_btns'):
            for btn in self.valve_btns: btn.setEnabled(enable)
        if hasattr(self, 'feed_btns'):
            for btn in self.feed_btns: btn.setEnabled(enable)
            for inp in self.feed_inputs: inp.setEnabled(enable)
            self.common_feed_input.setEnabled(enable)
        if hasattr(self, 'integrated_btns'):
            for btn in self.integrated_btns: btn.setEnabled(enable)
            for inp in self.integrated_inputs: inp.setEnabled(enable)
        if hasattr(self, 'btn_calib_start'):
            if enable:
                self.btn_calib_start.setEnabled(self.calib_state == 'IDLE')
                self.calib_jog_speed_input.setEnabled(True)
                self.calib_return_speed_input.setEnabled(True)
            else:
                if self.calib_state != 'IDLE': self.calib_cancel()
                self.btn_calib_start.setEnabled(False)
                self.btn_calib_execute.setEnabled(False)
                self.btn_calib_next.setEnabled(False)
                self.btn_calib_cancel.setEnabled(False)
                self.calib_jog_speed_input.setEnabled(False)
                self.calib_return_speed_input.setEnabled(False)

    def update_ui_data(self, motors_data, global_data):
        self.latest_motor_data = motors_data
        self.latest_global_data = global_data
        
        self.gantry_synced_status = global_data.get('sync_done', False)
        if self.gantry_synced_status:
            self.lbl_sync_status.setText("龙门已同步")
            self.lbl_sync_status.setStyleSheet("color: white; font-weight: bold; border: 1px solid green; padding: 5px; background: green;")
        else:
            self.lbl_sync_status.setText("未同步")
            self.lbl_sync_status.setStyleSheet("color: red; font-weight: bold; border: 1px solid gray; padding: 5px; background: #EEE;")

        for name, data in motors_data.items():
            if name in self.motor_widgets:
                self.motor_widgets[name].update_display(data, self.gantry_synced_status)
        
        if hasattr(self, 'lbl_calib_x1'):
            x1 = global_data.get('x1_status', False)
            self.lbl_calib_x1.setText("ON" if x1 else "OFF")
            self.lbl_calib_x1.setStyleSheet("color: white; background: green; font-weight: bold; padding: 2px;" if x1 else "color: red; font-weight: bold; padding: 2px;")
            zz_pos = motors_data.get('ZZ_motor', {}).get('act_pos', 0.0)
            self.lbl_calib_current_z.setText(f"{zz_pos:.3f}")

    def trigger_sync(self):
        self.worker.add_write_task('register_bit', 0, 1, bit=0)
        QTimer.singleShot(200, lambda: self.worker.add_write_task('register_bit', 0, 0, bit=0))

    def global_estop(self):
        for m in MOTOR_LIST:
            self.worker.add_write_task('register_bit', m['base'], 1, bit=OFFSETS['stop_cmd'])
            QTimer.singleShot(200, lambda b=m['base']: self.worker.add_write_task('register_bit', b, 0, bit=OFFSETS['stop_cmd']))
        QMessageBox.warning(self, "警告", "已触发总急停！")

    def toggle_brake(self, checked):
        if checked:
            self.btn_brake.setText("抱闸：释放")
            self.btn_brake.setStyleSheet("background-color: orange; color: black; font-weight: bold;")
        else:
            self.btn_brake.setText("抱闸：锁死")
            self.btn_brake.setStyleSheet("")
        self.worker.add_write_task('coil', 18, checked)

    def toggle_all_enable(self):
        self.all_enable_flag = not self.all_enable_flag
        target = self.all_enable_flag
        
        if target:
            self.btn_global_enable.setText("全轴失能")
            self.btn_global_enable.setStyleSheet("background-color: lightgreen;")
        else:
            self.btn_global_enable.setText("全轴使能")
            self.btn_global_enable.setStyleSheet("")
            
        for m in MOTOR_LIST:
            self.worker.add_write_task('coil', m['enable_m'], target)
            if m['name'] in self.motor_widgets:
                self.motor_widgets[m['name']].set_btn_style(target)


if __name__ == "__main__":
    app = QApplication(sys.argv)
    app.setFont(QFont("Microsoft YaHei", 9))
    win = MainWindow()
    win.show()
    sys.exit(app.exec_())
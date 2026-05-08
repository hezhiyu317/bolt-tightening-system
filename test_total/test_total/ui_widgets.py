# ui_widgets.py
from PyQt5.QtWidgets import QWidget, QVBoxLayout, QHBoxLayout, QGridLayout, QLabel, QLineEdit, QPushButton, QGroupBox, QMessageBox
from PyQt5.QtCore import QTimer, pyqtSignal
from config import OFFSETS

class MotorWidget(QGroupBox):
    # 定义一个信号：向外请求写入数据
    write_requested = pyqtSignal(dict) 

    def __init__(self, motor_info):
        super().__init__(motor_info['name'])
        self.motor_info = motor_info
        self.is_gantry_y = motor_info['name'] in ['YL_motor', 'YR_motor', 'YLL_motor', 'YRR_motor']
        self.gantry_synced = False
        self.init_ui()

    def init_ui(self):
        main_layout = QVBoxLayout()
        # 1. 显示区域
        display_layout = QGridLayout()
        self.lbl_pos = QLabel("0.00")
        self.lbl_pos.setStyleSheet("color: darkblue; font-weight: bold; font-size: 14px;")
        self.lbl_vel = QLabel("0.00")
        self.lbl_tor = QLabel("0.00")
        self.lbl_state = QLabel("离线")
        display_layout.addWidget(QLabel("位置:"), 0, 0); display_layout.addWidget(self.lbl_pos, 0, 1)
        display_layout.addWidget(QLabel("速度:"), 0, 2); display_layout.addWidget(self.lbl_vel, 0, 3)
        display_layout.addWidget(QLabel("力矩:"), 1, 0); display_layout.addWidget(self.lbl_tor, 1, 1)
        display_layout.addWidget(QLabel("状态:"), 1, 2); display_layout.addWidget(self.lbl_state, 1, 3)
        main_layout.addLayout(display_layout)
        
        # 2. 参数设置区域
        param_layout = QGridLayout()
        self.inputs = {}
        param_config = [
            ('点动速度', 'jog_vel_set'), ('相对速度', 'rel_vel_set'), ('绝对速度', 'abs_vel_set'),
            ('相对距离', 'rel_pos_set'), ('绝对坐标', 'abs_pos_set'), ('加速度', 'acc_set'), ('减速度', 'dec_set')
        ]
        for i, (label_text, key) in enumerate(param_config):
            lbl = QLabel(label_text)
            inp = QLineEdit("100.0" if key in ['acc_set', 'dec_set'] else "0.0")
            self.inputs[key] = inp
            param_layout.addWidget(lbl, i, 0)
            param_layout.addWidget(inp, i, 1)
            
        btn_sync_param = QPushButton("同步参数至电机")
        btn_sync_param.clicked.connect(self.sync_params)
        param_layout.addWidget(btn_sync_param, len(param_config), 0, 1, 2)
        main_layout.addLayout(param_layout)
        
        # 3. 控制按钮区域
        move_layout = QGridLayout()
        self.btn_jog_neg = QPushButton("点动 -"); self.btn_jog_pos = QPushButton("点动 +")
        self.btn_rel = QPushButton("相对运动"); self.btn_abs = QPushButton("绝对运动")
        
        self.btn_jog_neg.pressed.connect(lambda: self.set_cmd_bit(OFFSETS['jog_b_cmd'], 1))
        self.btn_jog_neg.released.connect(lambda: self.set_cmd_bit(OFFSETS['jog_b_cmd'], 0))
        self.btn_jog_pos.pressed.connect(lambda: self.set_cmd_bit(OFFSETS['jog_f_cmd'], 1))
        self.btn_jog_pos.released.connect(lambda: self.set_cmd_bit(OFFSETS['jog_f_cmd'], 0))
        self.btn_rel.clicked.connect(lambda: self.trigger_cmd(OFFSETS['rel_cmd']))
        self.btn_abs.clicked.connect(lambda: self.trigger_cmd(OFFSETS['abs_cmd']))
        
        move_layout.addWidget(self.btn_jog_neg, 0, 0); move_layout.addWidget(self.btn_jog_pos, 0, 1)
        move_layout.addWidget(self.btn_rel, 1, 0); move_layout.addWidget(self.btn_abs, 1, 1)
        main_layout.addLayout(move_layout)
        
        state_layout = QHBoxLayout()
        self.btn_enable = QPushButton("使能")
        self.btn_enable.clicked.connect(self.handle_enable_click)
        self.btn_reset = QPushButton("复位")
        self.btn_reset.clicked.connect(lambda: self.trigger_cmd(OFFSETS['reset_cmd']))
        
        # 【新增】寻零按钮，触发 Dxxx.3
        self.btn_home = QPushButton("寻零")
        self.btn_home.clicked.connect(lambda: self.trigger_cmd(OFFSETS['home_cmd']))
        
        self.btn_stop = QPushButton("急停")
        self.btn_stop.setStyleSheet("background-color: red; color: white; font-weight: bold;")
        self.btn_stop.clicked.connect(lambda: self.trigger_cmd(OFFSETS['stop_cmd']))
        
        # 将寻零按钮加入布局
        state_layout.addWidget(self.btn_enable)
        state_layout.addWidget(self.btn_reset)
        state_layout.addWidget(self.btn_home)
        state_layout.addWidget(self.btn_stop)
        main_layout.addLayout(state_layout)
        
        self.setLayout(main_layout)
        self.set_enabled_all(False)

    def set_enabled_all(self, enabled):
        for child in self.findChildren(QWidget): child.setEnabled(enabled)

    def update_display(self, data, is_synced):
        self.lbl_pos.setText(f"{data['act_pos']:.2f}")
        self.lbl_vel.setText(f"{data['act_vel']:.2f}")
        self.lbl_tor.setText(f"{data['act_tor']:.2f}")
        self.lbl_state.setText("在线" if data['is_powered'] else "离线")
        
        current_green = "background-color: #00FF00" in self.btn_enable.styleSheet()
        if data['is_powered'] and not current_green: self.set_btn_style(True)
        elif not data['is_powered'] and not current_green: self.set_btn_style(False)
        self.gantry_synced = is_synced

    def set_btn_style(self, is_enabled):
        if is_enabled:
            self.btn_enable.setText("已使能")
            self.btn_enable.setStyleSheet("background-color: #00FF00; color: black;")
        else:
            self.btn_enable.setText("使能")
            self.btn_enable.setStyleSheet("background-color: white; color: black;")

    def handle_enable_click(self):
        target = not ("background-color: #00FF00" in self.btn_enable.styleSheet())
        self.set_btn_style(target) 
        self.write_requested.emit({'type': 'coil', 'addr': self.motor_info['enable_m'], 'val': target, 'bit': None})

    def sync_params(self):
        base = self.motor_info['base']
        try:
            for key, widget in self.inputs.items():
                val = float(widget.text())
                addr = base + OFFSETS[key]
                self.write_requested.emit({'type': 'float', 'addr': addr, 'val': val, 'bit': None})
        except ValueError:
            QMessageBox.warning(self, "错误", "参数必须是数字")

    def set_cmd_bit(self, bit_offset, val):
        motion_bits = [OFFSETS['jog_f_cmd'], OFFSETS['jog_b_cmd'], OFFSETS['rel_cmd'], OFFSETS['abs_cmd']]
        if bit_offset in motion_bits and val == 1:
            if self.is_gantry_y and not self.gantry_synced:
                QMessageBox.warning(self, "禁止操作", "龙门未同步！禁止操作 Y 轴电机。")
                return
        self.write_requested.emit({'type': 'register_bit', 'addr': self.motor_info['base'], 'val': val, 'bit': bit_offset})

    def trigger_cmd(self, bit_offset):
        self.set_cmd_bit(bit_offset, 1)
        QTimer.singleShot(200, lambda: self.set_cmd_bit(bit_offset, 0))
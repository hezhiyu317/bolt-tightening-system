# config.py

# ================= 配置区域 =================
MOTOR_LIST = [
    # 小龙门 (M1 - M4)
    {'name': 'Z_motor',   'base': 100, 'enable_m': 1,  'group': 'Small Gantry'},
    {'name': 'X_motor',   'base': 132, 'enable_m': 2,  'group': 'Small Gantry'},
    {'name': 'YL_motor',  'base': 164, 'enable_m': 3,  'group': 'Small Gantry'}, 
    {'name': 'YR_motor',  'base': 196, 'enable_m': 4,  'group': 'Small Gantry'}, 
    
    # 大龙门 (M5 - M8)
    {'name': 'ZZ_motor',  'base': 228, 'enable_m': 5,  'group': 'Big Gantry'},
    {'name': 'XX_motor',  'base': 260, 'enable_m': 6,  'group': 'Big Gantry'},
    {'name': 'YLL_motor', 'base': 292, 'enable_m': 7,  'group': 'Big Gantry'}, 
    {'name': 'YRR_motor', 'base': 324, 'enable_m': 8,  'group': 'Big Gantry'}, 
    
    # 旋转电机 (M9 - M12)
    {'name': 'SPF_motor', 'base': 356, 'enable_m': 9,  'group': 'Rotary'},
    {'name': 'SPT_motor', 'base': 388, 'enable_m': 10, 'group': 'Rotary'},
    {'name': 'SPM_motor', 'base': 420, 'enable_m': 11, 'group': 'Rotary'},
    {'name': 'SPC_motor', 'base': 452, 'enable_m': 12, 'group': 'Rotary'},
]

OFFSETS = {
    'reset_cmd': 1, 'stop_cmd': 2, 'home_cmd': 3,
    'jog_f_cmd': 4, 'jog_b_cmd': 5, 'rel_cmd': 6, 'abs_cmd': 7,
    'jog_vel_set': 3, 'rel_vel_set': 5, 'rel_pos_set': 7,
    'abs_vel_set': 11, 'abs_pos_set': 13, 'acc_set': 18, 'dec_set': 20,
    'act_pos': 23, 'act_vel': 25, 'act_tor': 27,
    'status_word_offset': 30, 'is_powered_bit': 1
}

# X1 传感器输入地址（Modbus 离散输入地址，PLC 软元件 X1）
X1_DISCRETE_INPUT_ADDR = 20

# 龙门三坐标轴映射
SMALL_GANTRY = {
    'X': 'X_motor',
    'Y_left': 'YL_motor',
    'Y_right': 'YR_motor',
    'Z': 'Z_motor'
}

BIG_GANTRY = {
    'X': 'XX_motor',
    'Y_left': 'YLL_motor',
    'Y_right': 'YRR_motor',
    'Z': 'ZZ_motor'
}
# 螺栓拧紧上位机系统 — 全新 UI 重构计划

## Context

基于现有的 `test_total/test_total/` 目录下的参考代码（PyQt5 GUI + pymodbus PLC 通讯 + C++ PCL 点云处理），重新设计并实现一套专业的工业控制风格上位机系统。当前计算机未配置开发环境，项目从零开始搭建。

现有代码的核心功能（PLC 通讯协议、点云处理流水线、相机 SDK 接口）保持不变，本次重构聚焦于：UI 架构、项目工程化、配置管理、日志系统、登录权限。

## 目标

- 工业控制风格的深色主题专业 UI
- 密码登录区分开发者/用户两种模式
- YAML 配置文件管理，消除硬编码
- 完整的日志系统（文件 + UI 面板）
- 标准 Python 项目结构，模块化架构
- 保留现有 C++ PCL 模块和通讯协议逻辑

## 项目结构

```
project/
├── src/
│   ├── ui/
│   │   ├── __init__.py
│   │   ├── main_window.py          # 主窗口框架
│   │   ├── login_dialog.py         # 登录对话框
│   │   ├── styles.py               # 全局样式常量
│   │   ├── pages/
│   │   │   ├── __init__.py
│   │   │   ├── dashboard_page.py   # 系统总览仪表盘
│   │   │   ├── motor_control_page.py    # 电机控制（小龙门/大龙门/旋转）
│   │   │   ├── vision_page.py      # 视觉系统（相机 + 点云）
│   │   │   ├── integrated_page.py  # 一体化操作
│   │   │   ├── calibration_page.py # 末端标定
│   │   │   ├── gun_valve_page.py   # 拧紧枪 & 电磁阀
│   │   │   ├── feeding_page.py     # 送料电机
│   │   │   ├── settings_page.py    # 系统设置（开发者模式）
│   │   │   └── log_viewer_page.py  # 日志查看
│   │   └── widgets/
│   │       ├── __init__.py
│   │       ├── motor_widget.py     # 单电机控制组件
│   │       ├── status_indicator.py # 状态指示灯组件
│   │       ├── data_display.py     # 实时数据显示组件
│   │       └── log_panel.py        # 底部日志面板
│   ├── services/
│   │   ├── __init__.py
│   │   ├── plc_service.py          # Modbus TCP 通讯服务（重构自 plc_worker.py）
│   │   ├── camera_service.py       # 相机服务（重构自 camera_worker.py）
│   │   └── pcl_service.py          # 点云处理服务（重构自 pcl_bridge.py）
│   ├── models/
│   │   ├── __init__.py
│   │   ├── motor_config.py         # 电机配置数据结构
│   │   └── app_state.py            # 应用全局状态管理
│   └── utils/
│       ├── __init__.py
│       ├── config_manager.py       # YAML 配置读写
│       └── app_logger.py           # 日志系统
├── cpp/                            # C++ PCL 模块（从 test_total/test_total/src/ 迁移）
├── resources/
│   ├── styles/
│   │   └── industrial.qss         # 工业控制深色主题 QSS
│   └── icons/                     # 图标资源
├── config/
│   ├── system.yaml                # 系统配置（PLC IP、相机参数等）
│   ├── motors.yaml                # 电机定义与 Modbus 地址映射
│   └── users.yaml                 # 用户账号与密码（SHA-256 哈希）
├── logs/                          # 运行日志文件
├── main.py                        # 入口
├── requirements.txt
└── README.md
```

## 架构设计

### 分层架构

```
┌─────────────────────────────────────────────┐
│  UI Layer (src/ui/)                          │
│  PyQt5 Widgets, Pages, Styles, Signals       │
├─────────────────────────────────────────────┤
│  Service Layer (src/services/)               │
│  PLC/Camera/PCL → QThread workers            │
│  通过 pyqtSignal 与 UI 层通信                │
├─────────────────────────────────────────────┤
│  Model Layer (src/models/)                   │
│  配置模型、应用状态                           │
├─────────────────────────────────────────────┤
│  Utility Layer (src/utils/)                  │
│  配置管理、日志系统                           │
└─────────────────────────────────────────────┘
```

### 核心设计原则

1. **信号驱动**: Service 层通过 pyqtSignal 向 UI 层推送数据，UI 层通过信号调用 Service 公开方法
2. **配置外置**: 所有参数（电机地址、PLC IP、相机设置、算法阈值）从 YAML 文件读取
3. **模式隔离**: 开发者模式/用户模式通过权限控制 UI 可见性（settings_page 仅在开发者模式可见）
4. **状态集中**: `app_state.py` 维护全局系统状态（连接状态、同步状态、当前模式、最近数据）

### UI 页面导航

```
登录 → 主窗口
         ├── 仪表盘 (首页)
         │    ├── 连接状态总览
         │    ├── 龙门同步状态
         │    ├── 报警/事件摘要
         │    └── 快捷操作
         ├── 电机控制 (TabWidget 子页)
         │    ├── 小龙门 (Z/X/YL/YR)
         │    ├── 大龙门 (ZZ/XX/YLL/YRR)
         │    └── 旋转电机 (SPF/SPT/SPM/SPC)
         ├── 一体化操作 (小龙门 + 大龙门三坐标控制)
         ├── 视觉系统 (相机连接/2D/3D/算法结果)
         ├── 末端标定
         ├── 拧紧枪 & 电磁阀
         ├── 送料电机
         ├── 系统设置 (仅开发者模式)
         │    ├── 电机参数配置
         │    ├── 通讯设置
         │    ├── 相机设置
         │    └── 算法参数
         └── 日志查看
```

## 实施步骤

### 步骤 1: 项目骨架搭建

- 创建目录结构
- 创建 `requirements.txt`（PyQt5, pymodbus, pyvista, pyvistaqt, open3d, numpy, PyYAML）
- 创建 `main.py` 入口
- 配置 `config/system.yaml`, `config/motors.yaml`, `config/users.yaml`
- 实现 `config_manager.py`（YAML 配置读写，带默认值回退）
- 实现 `app_logger.py`（双输出：文件 + 内存 buffer 供 UI 显示）

### 步骤 2: 全局样式系统

- 编写 `industrial.qss` — 深色工业主题
  - 主背景 #1a1a1a, 面板背景 #2d2d2d
  - 主色调：蓝色 #2196F3 (正常), 绿色 #4CAF50 (运行), 红色 #F44336 (报警/急停), 黄色 #FF9800 (警告)
  - 字体：Consolas/Microsoft YaHei
  - QGroupBox、QPushButton、QLineEdit、QTableWidget 等控件统一样式
- `src/ui/styles.py` — 颜色常量、状态颜色映射

### 步骤 3: 基础 Widget 组件

- `StatusIndicator` — 圆形状态灯（绿/红/黄/灰）
- `DataDisplay` — 数值显示组件（标题 + 数值 + 单位）
- `LogPanel` — 底部固定日志面板，支持级别过滤
- `MotorWidget` — 重构自现有 `ui_widgets.py`，使用新样式

### 步骤 4: Service 层

- `plc_service.py` — 重构自 `plc_worker.py`
  - 从 YAML 读取电机配置和寄存器映射
  - 保持现有 Modbus 读写逻辑和轮询机制
  - 信号：`data_updated`, `connection_status`, `error_occurred`
- `camera_service.py` — 重构自 `camera_worker.py`
  - 保持现有 Alson SDK 接口逻辑
  - 信号：`connection_status`, `image_grabbed`, `point_cloud_grabbed`
- `pcl_service.py` — 重构自 `pcl_bridge.py`
  - 保持 pybind11/subprocess 双后端逻辑
  - 信号：`processing_finished`, `processing_error`

### 步骤 5: 页面实现

按顺序实现各页面，每页继承 `QWidget`，接收 service 引用和 app_state 引用：
1. `login_dialog.py` — 密码输入 → 验证 SHA-256 → 选择模式
2. `dashboard_page.py` — 系统总览
3. `motor_control_page.py` — 三组电机 Tab 控制
4. `integrated_page.py` — 三坐标点位控制
5. `vision_page.py` — 相机 + 点云处理
6. `calibration_page.py` — 末端标定流程
7. `gun_valve_page.py` — 拧紧枪 + 电磁阀
8. `feeding_page.py` — 送料电机
9. `settings_page.py` — 开发者配置
10. `log_viewer_page.py` — 日志浏览

### 步骤 6: 主窗口组装

- `main_window.py` — 左侧导航栏 + 右侧 QStackedWidget 页面
- 底部 LogPanel（全局可见）
- 顶部状态栏（连接状态、当前模式、时间）
- 权限控制：根据当前用户角色显示/隐藏设置入口

### 步骤 7: C++ 模块迁移

- 将 `test_total/test_total/src/` 复制到 `cpp/`
- 将 `test_total/test_total/CMakeLists.txt` 复制到 `cpp/`
- 调整 CMakeLists.txt 中的路径
- 保留 `.pyd` 和 `.exe` 的构建产物路径映射

## 技术要点

- **PyQt5 信号/槽机制** 用于跨线程通信（Service worker threads → UI main thread）
- **QThread** 用于 PLC 轮询和相机采集，避免阻塞 UI
- **QSS (Qt Style Sheets)** 实现深色工业主题
- **PyYAML** 管理配置文件
- **logging 模块** 实现双输出日志（RotatingFileHandler + 自定义 QTextEdit handler）

## 关键配置示例

### motors.yaml 结构
```yaml
motors:
  - name: Z_motor
    base: 100
    enable_m: 1
    group: small_gantry
    axis: Z
  # ... 12 motors total

offsets:
  reset_cmd: 1
  stop_cmd: 2
  # ... etc

gantry:
  small:
    X: X_motor
    Y_left: YL_motor
    Y_right: YR_motor
    Z: Z_motor
  big:
    X: XX_motor
    Y_left: YLL_motor
    Y_right: YRR_motor
    Z: ZZ_motor
```

### system.yaml 结构
```yaml
plc:
  default_ip: "192.168.1.88"
  port: 502
  poll_interval_ms: 100

camera:
  log_config: "../LogConfig-Client.yaml"
  temp_dir: "./temp_cam_data"
  2d_exposure_mode: "FLASH"
  2d_exposure_time: 5000
  3d_exposure_time: 30000

pcl:
  default_params:
    plane_distance_threshold: 0.05
    edge_search_radius: 2.0
    edge_num_threads: 4
    cluster_tolerance: 2.0
    min_cluster_size: 50
    max_cluster_size: 1000
    input_in_millimeters: true

sensors:
  x1_discrete_input_addr: 20
```

### users.yaml 结构
```yaml
users:
  - username: admin
    password_hash: "<sha256>"
    role: developer
  - username: operator
    password_hash: "<sha256>"
    role: user
```

## 验证方式

1. 启动 `python main.py`，验证登录对话框出现
2. 输入开发者账号，验证所有页面可见（含设置页）
3. 输入用户账号，验证设置页隐藏
4. 验证 QSS 深色主题正确应用
5. 连接 PLC（如有硬件），验证实时数据更新
6. 连接相机（如有硬件），验证 2D 画面和 3D 点云采集
7. 运行点云处理，验证算法结果展示
8. 查看日志面板，验证日志实时滚动
9. 检查 `logs/` 目录，验证日志文件写入
10. 修改 `config/system.yaml`，重启验证配置生效

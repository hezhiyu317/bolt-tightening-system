"""全局样式常量 — 深色工业控制主题。

色彩体系来自 UIdetails.txt 规格说明书。
"""

# ---- 主色调 ----------------------------------------------------------------
BG_DARK = "#0B1622"          # 主背景 — 科技深蓝
BG_PANEL = "#0F1D2F"         # 卡片/面板背景
BG_HEADER = "#08111C"        # 顶部栏背景
BG_SIDEBAR = "#0A1420"       # 侧边栏背景
BG_FOOTER = "#060D14"        # 底部栏背景

# ---- 功能色 ----------------------------------------------------------------
GREEN_STATUS = "#00FFCC"     # 正常 / 在线 / 进行中
BLUE_FUNC = "#0099FF"        # 选中 / 主按钮 / 导航
RED_ALERT = "#FF4D4D"        # 急停 / 故障 / 报警
ORANGE_WARN = "#FFA500"      # 预警 / 待机

# ---- 文字色 ----------------------------------------------------------------
TEXT_PRIMARY = "#E0E6EE"     # 主要文字
TEXT_SECONDARY = "#8899AA"   # 次要文字 / 标签
TEXT_DIM = "#556677"         # 禁用 / 占位

# ---- 边框与发光 ------------------------------------------------------------
BORDER_CARD = "#1A3350"      # 卡片描边
GLOW_BLUE = "rgba(0, 153, 255, 0.3)"   # 蓝色发光（选中态）
GLOW_GREEN = "rgba(0, 255, 204, 0.3)"  # 绿色发光（运行态）

# ---- 状态色映射 ------------------------------------------------------------
STATUS_COLORS = {
    "online": GREEN_STATUS,
    "offline": TEXT_DIM,
    "error": RED_ALERT,
    "warning": ORANGE_WARN,
    "running": GREEN_STATUS,
    "idle": TEXT_SECONDARY,
    "active": BLUE_FUNC,
}

# ---- 尺寸 ----------------------------------------------------------------
HEADER_HEIGHT = 56
SIDEBAR_WIDTH = 56
FOOTER_HEIGHT = 28
RIGHT_PANEL_WIDTH = 340
CARD_RADIUS = 6

# ---- 字体 ----------------------------------------------------------------
FONT_FAMILY = "Microsoft YaHei, Segoe UI, sans-serif"
FONT_MONO = "Consolas, Courier New, monospace"
FONT_SIZE_XS = 10
FONT_SIZE_SM = 11
FONT_SIZE_BASE = 13
FONT_SIZE_LG = 16
FONT_SIZE_XL = 20

# ---- 复用 QSS 片段 ---------------------------------------------------------

QSS_CARD = f"""
    background-color: {BG_PANEL};
    border: 1px solid {BORDER_CARD};
    border-radius: {CARD_RADIUS}px;
    padding: 8px;
"""

QSS_PRIMARY_BUTTON = f"""
    QPushButton {{
        background-color: {BLUE_FUNC};
        color: #FFFFFF;
        border: none;
        border-radius: 4px;
        padding: 6px 16px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: #33ADFF;
    }}
    QPushButton:pressed {{
        background-color: #007ACC;
    }}
    QPushButton:disabled {{
        background-color: {TEXT_DIM};
    }}
"""

QSS_DANGER_BUTTON = f"""
    QPushButton {{
        background-color: {RED_ALERT};
        color: #FFFFFF;
        border: none;
        border-radius: 4px;
        padding: 6px 16px;
        font-weight: bold;
    }}
    QPushButton:hover {{
        background-color: #FF6666;
    }}
    QPushButton:pressed {{
        background-color: #CC0000;
    }}
"""

QSS_SECONDARY_BUTTON = f"""
    QPushButton {{
        background-color: transparent;
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_CARD};
        border-radius: 4px;
        padding: 6px 16px;
    }}
    QPushButton:hover {{
        border-color: {BLUE_FUNC};
        color: {BLUE_FUNC};
    }}
"""

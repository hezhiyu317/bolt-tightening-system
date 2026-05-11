"""全局样式常量 — 现代明亮工业控制主题（Light Theme）。

色彩体系来自 UI/UX 优化建议书。
"""

# ---- 背景层 ----------------------------------------------------------------
BG_BASE = "#F0F2F5"          # 全局大背景 — 浅灰蓝（不用纯白，大屏不刺眼）
BG_PANEL = "#FFFFFF"         # 卡片/面板背景 — 纯白
BG_HEADER = "#FFFFFF"        # 顶部栏背景
BG_SIDEBAR = "#FFFFFF"       # 侧边栏背景
BG_FOOTER = "#FFFFFF"        # 底部栏背景
BG_DARK = "#F0F2F5"          # 兼容旧引用 — 同 BG_BASE

# ---- 功能色 ----------------------------------------------------------------
GREEN_STATUS = "#52C41A"     # 正常 / 在线 / 已同步
BLUE_FUNC = "#1890FF"        # 选中 / 主按钮 / 导航 / 科技蓝
RED_ALERT = "#FF4D4F"        # 急停 / 故障 / 报警
ORANGE_WARN = "#FAAD14"      # 预警 / 待机 / 未连接

# ---- 文字色 ----------------------------------------------------------------
TEXT_PRIMARY = "#262626"     # 主要文字 / 标题
TEXT_SECONDARY = "#595959"   # 次要文字 / 标签
TEXT_DIM = "#8C8C8C"         # 禁用 / 占位 / 辅助信息

# ---- 边框与阴影 ------------------------------------------------------------
BORDER_CARD = "#E4E7ED"      # 卡片描边 / 分割线
GLOW_BLUE = "rgba(24, 144, 255, 0.3)"   # 蓝色发光（选中态）
GLOW_GREEN = "rgba(82, 196, 26, 0.3)"   # 绿色发光（运行态）

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
        background-color: #40A9FF;
    }}
    QPushButton:pressed {{
        background-color: #096DD9;
    }}
    QPushButton:disabled {{
        background-color: {TEXT_DIM};
        color: #FFFFFF;
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
        background-color: #FF7875;
    }}
    QPushButton:pressed {{
        background-color: #D9363E;
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

"""螺栓拧紧上位机系统 — 应用入口。

启动顺序：加载配置 → 初始化 Service → 启动 UI。
"""

import sys

from PyQt5.QtWidgets import QApplication

from src.utils.config_manager import config
from src.utils.app_logger import app_logger
from src.models.motor_config import create_motor_configs
from src.services.camera_service import CameraService
from src.services.pcl_service import PclService
from src.services.plc_service import PlcService
from src.ui.main_window import MainWindow


def main():
    # 加载所有配置
    config.load()
    app_logger.start()
    app_logger.info("应用启动")

    # 电机配置
    motor_configs = create_motor_configs()

    # 初始化 Service
    camera = CameraService()
    pcl = PclService()
    plc = PlcService(motor_configs=motor_configs)

    # 启动 UI
    app = QApplication(sys.argv)
    window = MainWindow(
        camera_service=camera,
        pcl_service=pcl,
        plc_service=plc,
        motor_configs=motor_configs,
    )
    window.show()

    app_logger.info("主窗口已显示")
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()

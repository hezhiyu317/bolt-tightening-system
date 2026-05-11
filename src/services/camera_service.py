"""Alson 结构光光栅相机服务 — 2D 纹理流 + 3D 点云采集 + 参数管理。

重构自 test_total/test_total/camera_worker.py。
后台线程采集 2D 图像（~20 FPS），支持单次 3D 点云触发采图。
2D/3D 互斥：3D 采集时暂停 2D 流，完成后自动恢复。
提供参数读写接口供 VisionPage 调用。
"""

import os
import threading
import time
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from src.utils.config_manager import config
from src.utils.app_logger import app_logger
from src.models.app_state import app_state

try:
    from AlsonClassicDevice import *  # noqa: F403
    _ALSON_AVAILABLE = True
except ImportError:
    _ALSON_AVAILABLE = False

# SDK 参数路径常量，避免字符串拼写错误
PARAM_2D_EXPOSURE_MODE = "2dParameters.exposureMode"
PARAM_2D_EXPOSURE_TIME = "2dParameters.exposureTime"
PARAM_2D_GAIN = "2dParameters.gain"
PARAM_2D_GAMMA = "2dParameters.gamma"
PARAM_2D_FAST_HDR = "2dParameters.fastHdr"
PARAM_2D_GRAY_LOWER = "2dParameters.grayValueRange.lowerLimit"
PARAM_2D_GRAY_UPPER = "2dParameters.grayValueRange.upperLimit"
PARAM_3D_EXPOSURE_ARRAY = "3dParameters.exposureTimeArray"
PARAM_3D_GAIN = "3dParameters.gain"
PARAM_3D_BRIGHTNESS = "3dParameters.lightEngineBrightness"
PARAM_3D_ENHANCE = "3dParameters.enhanceMode"
PARAM_3D_DENOISE = "3dParameters.denoiseMode"
PARAM_3D_HOLE_FILLING = "3dParameters.holeFilling"
PARAM_3D_FILTER_MODE = "3dParameters.filterMode"
PARAM_3D_EDGE_PROTECTION = "3dParameters.edgeProtection"
PARAM_3D_DECODE_THRESHOLD = "3dParameters.decodeThreshold"
PARAM_3D_DEPTH_LOWER = "3dParameters.depthRange.lowerLimit"
PARAM_3D_DEPTH_UPPER = "3dParameters.depthRange.upperLimit"


class CameraService(QObject):
    """Alson 结构光光栅相机服务。

    Usage:
        camera = CameraService()
        camera.connection_status.connect(on_conn)
        camera.image_grabbed.connect(on_2d)
        camera.point_cloud_grabbed.connect(on_3d)
        camera.connect_camera()
    """

    connection_status = pyqtSignal(bool, str)    # (connected, message)
    image_grabbed = pyqtSignal(str)              # 2D BMP 文件路径
    point_cloud_grabbed = pyqtSignal(str)        # 3D PCD 文件路径
    error_occurred = pyqtSignal(str)             # 错误描述
    camera_discovered = pyqtSignal(list)          # server_info 字典列表
    camera_params_changed = pyqtSignal(str, object)  # (param_path, new_value)
    device_exception = pyqtSignal(str)            # 设备硬件异常描述
    client_disconnected = pyqtSignal(str)         # 通信异常断开原因

    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self._client = None
        self._device_controller = None
        self._parameter_manager = None
        self._connected = False
        self._streaming = False
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None
        self._client_listener = None
        self._device_listener = None
        self._server_list: List[Any] = []

        # 从 system.yaml 读取相机参数
        cfg = config.camera_config
        self._temp_dir = cfg.get("temp_dir", "./temp_cam_data")
        self._log_config = cfg.get("log_config", "../LogConfig-Client.yaml")

        os.makedirs(self._temp_dir, exist_ok=True)

        if not _ALSON_AVAILABLE:
            app_logger.warning("AlsonClassicDevice SDK 未安装，相机功能不可用")

    # ---- event listeners (internal) -------------------------------------------

    def _register_listeners(self):
        """注册客户端和设备事件监听器。连接后调用。"""
        if not _ALSON_AVAILABLE:
            return
        self._client_listener = _CameraClientEventListener(self)
        self._client.set_client_event_listener(self._client_listener)
        self._device_listener = _CameraDeviceEventListener(self)
        self._device_controller.set_device_event_listener(self._device_listener)

    def _unregister_listeners(self):
        """清除事件监听器。断开前调用。"""
        self._client_listener = None
        self._device_listener = None

    def _on_client_disconnected(self):
        """客户端通信异常断开回调。"""
        self._connected = False
        self._streaming = False
        app_state.camera_online = False
        reason = "相机通信异常断开"
        self.client_disconnected.emit(reason)
        self.connection_status.emit(False, reason)
        app_logger.error(reason)

    def _on_device_exception(self):
        """设备硬件异常回调。"""
        msg = "相机硬件异常"
        self.device_exception.emit(msg)
        self.error_occurred.emit(msg)
        app_logger.error(msg)

    # ---- public API -----------------------------------------------------------

    def connect_camera(self):
        """发现并连接相机（后台线程，避免 SDK 与 Qt 事件循环冲突）。"""
        if self._connected:
            return
        if not _ALSON_AVAILABLE:
            msg = "AlsonClassicDevice SDK 未安装，无法连接相机"
            self.connection_status.emit(False, msg)
            self.error_occurred.emit(msg)
            return

        threading.Thread(target=self._connect_task, daemon=True).start()

    def _connect_task(self):
        """后台线程：发现 + 连接相机全流程。"""
        try:
            Client.init_log(self._log_config)  # noqa: F405

            server_info_list = Client.discovery()  # noqa: F405
            if len(server_info_list) == 0:
                self.connection_status.emit(False, "未发现任何相机设备")
                return

            server_info = server_info_list[0]
            self._camera_ip = server_info.get_server_network_card_info().get_ip()
            self._server_list = server_info_list

            self._client = Client()  # noqa: F405
            self._client.connect(
                self._camera_ip,
                server_info.get_server_network_card_info().get_bind_port(),
            )

            if not self._client.is_connected():
                self.connection_status.emit(False, "相机连接失败")
                return

            self._client.set_heartbeat_timeout(3000)
            self._device_controller = \
                self._client.create_classic_device_controller()

            self._register_listeners()
            self._device_controller.open()

            self._parameter_manager = \
                self._client.create_device_parameter_manager()

            self.apply_default_parameters()

            self._connected = True
            self.connection_status.emit(True, "相机连接成功")
            app_state.camera_online = True
            app_logger.info(f"相机已连接: {self._camera_ip}")

            self.start_2d_stream()

        except Exception as e:
            self.connection_status.emit(False, f"相机初始化异常: {str(e)}")
            self.error_occurred.emit(str(e))
            app_logger.exception(str(e))

    def disconnect_camera(self):
        """断开相机连接，停止 2D 流。"""
        self._streaming = False
        time.sleep(0.2)

        self._unregister_listeners()

        try:
            if self._device_controller:
                self._device_controller.close()
            if self._client:
                self._client.disconnect()
        except Exception as e:
            app_logger.warning(f"关闭相机异常: {e}")

        self._connected = False
        self._client = None
        self._device_controller = None
        self._parameter_manager = None
        self._server_list = []
        self.connection_status.emit(False, "相机已断开")
        app_logger.info("相机已断开")
        app_state.camera_online = False

    # ---- 2D streaming ---------------------------------------------------------

    def start_2d_stream(self):
        """启动 2D 纹理图像采集线程（~20 FPS）。"""
        if not self._connected or self._streaming:
            return
        self._streaming = True
        self._thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._thread.start()

    def stop_2d_stream(self):
        """停止 2D 采集线程。"""
        self._streaming = False

    def _stream_loop(self):
        """2D 图像采集主循环。"""
        img_path = os.path.join(self._temp_dir, "temp_2d_stream.bmp")

        while self._streaming:
            with self._lock:
                try:
                    texture = self._device_controller.grab_texture_image()
                    texture.save(img_path)
                    self.image_grabbed.emit(img_path)
                except Exception as e:
                    app_logger.error(f"获取 2D 图像失败: {e}")
            time.sleep(0.05)

    # ---- 3D capture -----------------------------------------------------------

    def trigger_3d_capture(self):
        """触发单次 3D 点云采集。

        暂停 2D 流 → 采集 3D → 恢复 2D 流（如之前开启）。
        """
        if not self._connected:
            return
        threading.Thread(target=self._capture_3d_task, daemon=True).start()

    def _capture_3d_task(self):
        was_streaming = self._streaming
        self._streaming = False
        time.sleep(0.1)

        # 参数由 apply_default_parameters()（连接时）和 UI 控件实时写入维护，
        # 此处不再 reset/re-apply，直接使用当前参数管理器中的值采集点云。
        with self._lock:
            try:
                pc_path = os.path.join(self._temp_dir, "temp_3d_cloud.pcd")
                point_cloud = self._device_controller.grab_point_cloud()
                point_cloud.save(pc_path)
                self.point_cloud_grabbed.emit(pc_path)
                app_logger.info(f"3D 点云已保存: {pc_path}")
            except Exception as e:
                msg = f"采集 3D 点云异常: {e}"
                self.error_occurred.emit(msg)
                app_logger.exception(msg)

        if was_streaming:
            self.start_2d_stream()

    # ---- discovery & parameters -----------------------------------------------

    def discover_camera(self):
        """发现可用相机设备（后台线程）。结果通过 camera_discovered 信号发射。"""
        if not _ALSON_AVAILABLE:
            self.error_occurred.emit("AlsonClassicDevice SDK 未安装")
            return
        threading.Thread(target=self._discover_task, daemon=True).start()

    def _discover_task(self):
        """后台线程：相机发现。"""
        try:
            Client.init_log(self._log_config)  # noqa: F405
            server_list = Client.discovery()  # noqa: F405
            self._server_list = server_list
            result = []
            for s in server_list:
                nic = s.get_server_network_card_info()
                result.append({"ip": nic.get_ip(), "port": nic.get_bind_port()})
            self.camera_discovered.emit(result)
        except Exception as e:
            msg = f"相机发现失败: {e}"
            self.error_occurred.emit(msg)
            app_logger.exception(msg)

    def apply_default_parameters(self):
        """从 system.yaml 加载默认参数并写入相机。"""
        if not self._parameter_manager:
            return
        with self._lock:
            try:
                self._parameter_manager.reset_current_value()
            except Exception:
                pass

            pm = self._parameter_manager
            p2 = config.get("system.camera.default_parameters.2d", {})
            p3 = config.get("system.camera.default_parameters.3d", {})

            # Each param write is isolated — one failure won't skip the rest.

            # -- 2D params --
            try:
                if p2.get("exposure_mode"):
                    pm.update_current_enumeration_value(PARAM_2D_EXPOSURE_MODE, p2["exposure_mode"])
            except Exception:
                pass
            try:
                if p2.get("exposure_time"):
                    pm.update_current_integer_value(PARAM_2D_EXPOSURE_TIME, p2["exposure_time"])
            except Exception:
                pass
            try:
                if p2.get("gain") is not None:
                    pm.update_current_integer_value(PARAM_2D_GAIN, p2["gain"])
            except Exception:
                pass
            try:
                if p2.get("gamma") is not None:
                    pm.update_current_float_value(PARAM_2D_GAMMA, p2["gamma"])
            except Exception:
                pass
            try:
                if p2.get("fast_hdr") is not None:
                    pm.update_current_boolean_value(PARAM_2D_FAST_HDR, p2["fast_hdr"])
            except Exception:
                pass
            try:
                if p2.get("gray_value_lower") is not None:
                    pm.update_current_integer_value(PARAM_2D_GRAY_LOWER, p2["gray_value_lower"])
            except Exception:
                pass
            try:
                if p2.get("gray_value_upper") is not None:
                    pm.update_current_integer_value(PARAM_2D_GRAY_UPPER, p2["gray_value_upper"])
            except Exception:
                pass

            # -- 3D exposure array --
            try:
                for i, val in enumerate(p3.get("exposure_time_array", [])):
                    if i > 0:
                        pm.add_array_element_for_current(PARAM_3D_EXPOSURE_ARRAY)
                    pm.update_current_integer_value(
                        f"{PARAM_3D_EXPOSURE_ARRAY}[{i}]", val)
            except Exception:
                pass

            # -- 3D params --
            try:
                if p3.get("gain") is not None:
                    pm.update_current_integer_value(PARAM_3D_GAIN, p3["gain"])
            except Exception:
                pass
            try:
                if p3.get("enhance_mode") is not None:
                    pm.update_current_boolean_value(PARAM_3D_ENHANCE, p3["enhance_mode"])
            except Exception:
                pass
            try:
                if p3.get("denoise_mode") is not None:
                    pm.update_current_boolean_value(PARAM_3D_DENOISE, p3["denoise_mode"])
            except Exception:
                pass
            try:
                if p3.get("hole_filling") is not None:
                    pm.update_current_integer_value(PARAM_3D_HOLE_FILLING, p3["hole_filling"])
            except Exception:
                pass
            try:
                if p3.get("filter_mode"):
                    pm.update_current_enumeration_value(PARAM_3D_FILTER_MODE, p3["filter_mode"])
            except Exception:
                pass
            try:
                if p3.get("edge_protection") is not None:
                    pm.update_current_boolean_value(PARAM_3D_EDGE_PROTECTION, p3["edge_protection"])
            except Exception:
                pass
            try:
                if p3.get("decode_threshold") is not None:
                    pm.update_current_integer_value(PARAM_3D_DECODE_THRESHOLD, p3["decode_threshold"])
            except Exception:
                pass
            try:
                if p3.get("depth_range_lower") is not None:
                    pm.update_current_integer_value(PARAM_3D_DEPTH_LOWER, p3["depth_range_lower"])
            except Exception:
                pass
            try:
                if p3.get("depth_range_upper") is not None:
                    pm.update_current_integer_value(PARAM_3D_DEPTH_UPPER, p3["depth_range_upper"])
            except Exception:
                pass

    # ---- parameter write helpers ----------------------------------------------

    def write_int_param(self, path: str, value: int):
        """写入整数参数。"""
        if not self._parameter_manager:
            return
        with self._lock:
            try:
                self._parameter_manager.update_current_integer_value(path, value)
                self.camera_params_changed.emit(path, value)
            except Exception as e:
                msg = f"写整数参数失败 {path}={value}: {e}"
                self.error_occurred.emit(msg)

    def write_float_param(self, path: str, value: float):
        """写入浮点参数。"""
        if not self._parameter_manager:
            return
        with self._lock:
            try:
                self._parameter_manager.update_current_float_value(path, value)
                self.camera_params_changed.emit(path, value)
            except Exception as e:
                msg = f"写浮点参数失败 {path}={value}: {e}"
                self.error_occurred.emit(msg)

    def write_enum_param(self, path: str, value: str):
        """写入枚举参数。"""
        if not self._parameter_manager:
            return
        with self._lock:
            try:
                self._parameter_manager.update_current_enumeration_value(path, value)
                self.camera_params_changed.emit(path, value)
            except Exception as e:
                msg = f"写枚举参数失败 {path}={value}: {e}"
                self.error_occurred.emit(msg)

    def write_bool_param(self, path: str, value: bool):
        """写入布尔参数。"""
        if not self._parameter_manager:
            return
        with self._lock:
            try:
                self._parameter_manager.update_current_boolean_value(path, value)
                self.camera_params_changed.emit(path, value)
            except Exception as e:
                msg = f"写布尔参数失败 {path}={value}: {e}"
                self.error_occurred.emit(msg)

    # ---- exposure array management --------------------------------------------

    def add_exposure_element(self):
        """向 3D 曝光时间数组追加一个元素。"""
        if not self._parameter_manager:
            return
        with self._lock:
            try:
                self._parameter_manager.add_array_element_for_current(
                    PARAM_3D_EXPOSURE_ARRAY)
            except Exception as e:
                self.error_occurred.emit(f"添加曝光层级失败: {e}")

    def remove_exposure_element(self, index: int):
        """移除指定索引的曝光时间数组元素。通过 SDK 节点 API 实现。"""
        if not self._parameter_manager or index < 0:
            return
        with self._lock:
            try:
                node = self._parameter_manager.get_array_parameter_node(
                    PARAM_3D_EXPOSURE_ARRAY)
                node.delete_element_by_index(index)
                new_values = self._get_exposure_array_values()
                self.camera_params_changed.emit(PARAM_3D_EXPOSURE_ARRAY, new_values)
            except Exception as e:
                self.error_occurred.emit(f"删除曝光层级失败: {e}")

    def get_exposure_array_size(self) -> int:
        """返回当前曝光时间数组大小。"""
        return len(self._get_exposure_array_values())

    def _get_exposure_array_values(self) -> List[int]:
        """读取当前曝光时间数组所有值。"""
        if not self._parameter_manager:
            return []
        try:
            # SDK 没有直接的 get_array_size 方法，通过试探索引读取
            values = []
            for i in range(5):  # 最多 5 组曝光
                try:
                    val = self._parameter_manager.get_current_integer_value(
                        f"{PARAM_3D_EXPOSURE_ARRAY}[{i}]")
                    values.append(val)
                except Exception:
                    break
            return values
        except Exception:
            return []

    # ---- properties -----------------------------------------------------------

    @property
    def parameter_manager(self):
        """公开参数管理器供 VisionPage 直接读取参数。"""
        return self._parameter_manager

    @property
    def is_connected(self) -> bool:
        return self._connected

    @property
    def is_streaming(self) -> bool:
        return self._streaming

    @property
    def camera_ip(self) -> str:
        return getattr(self, "_camera_ip", "")


# ---- internal event listener classes -----------------------------------------


class _CameraClientEventListener:
    """内部客户端事件监听器 — 通信异常断开通知。"""

    def __init__(self, service: "CameraService"):
        super().__init__()
        self._service = service

    def on_disconnected_by_exception(self):
        self._service._on_client_disconnected()


class _CameraDeviceEventListener:
    """内部设备事件监听器 — 硬件异常通知。"""

    def __init__(self, service: "CameraService"):
        super().__init__()
        self._service = service

    def on_device_exception(self):
        self._service._on_device_exception()


# 让监听器类继承 SDK 基类（如果可用）
if _ALSON_AVAILABLE:
    _CameraClientEventListener = type(
        "_CameraClientEventListener",
        (_CameraClientEventListener, AlsonBaseClientEventListener),
        {},
    )
    _CameraDeviceEventListener = type(
        "_CameraDeviceEventListener",
        (_CameraDeviceEventListener, AlsonClassicDeviceEventListener),
        {},
    )

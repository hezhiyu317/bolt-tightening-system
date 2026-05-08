# camera_worker.py
import threading
import time
import os
import subprocess
from PyQt5.QtCore import QObject, pyqtSignal

# 尝试引入 Alson SDK
try:
    from AlsonClassicDevice import *
except ImportError:
    print("【警告】未检测到 AlsonClassicDevice 环境，相机功能可能无法连接")

class CameraWorker(QObject):
    # 定义与 UI 通信的信号
    connection_status = pyqtSignal(bool, str)        # 连接状态信号
    image_grabbed = pyqtSignal(str)                  # 2D图像采集完成，传递本地路径
    point_cloud_grabbed = pyqtSignal(str)            # 3D点云采集完成，传递本地路径
    circle_center_calculated = pyqtSignal(float, float, float) 
    
    def __init__(self):
        super().__init__()
        self.client = None
        self.device_controller = None
        self.parameter_manager = None
        
        self.is_connected = False
        self.is_streaming_2d = False
        self._thread = None
        self._lock = threading.Lock()
        
        # 存放临时文件的目录（目前使用硬盘缓存，将来可优化为内存数组）
        self.temp_dir = "./temp_cam_data"
        if not os.path.exists(self.temp_dir):
            os.makedirs(self.temp_dir)

    def connect_camera(self):
        if self.is_connected:
            return
            
        try:
            # 1. 发现设备
            Client.init_log('../LogConfig-Client.yaml')
            server_info_list = Client.discovery()
            if len(server_info_list) == 0:
                self.connection_status.emit(False, "未发现任何相机设备")
                return

            server_info = server_info_list[0]

            # 2. 建立连接
            self.client = Client()
            self.client.connect(server_info.get_server_network_card_info().get_ip(),
                                server_info.get_server_network_card_info().get_bind_port())
            
            if not self.client.is_connected():
                self.connection_status.emit(False, "相机连接失败")
                return

            self.client.set_heartbeat_timeout(3000)
            
            # 3. 初始化控制器
            self.device_controller = self.client.create_classic_device_controller()
            self.device_controller.open()
            self.parameter_manager = self.client.create_device_parameter_manager()

            self.is_connected = True
            self.connection_status.emit(True, "相机连接成功")

            # 4. 自动开启 2D 实时画面流
            self.start_2d_stream()

        except Exception as e:
            self.connection_status.emit(False, f"相机初始化异常: {str(e)}")

    def disconnect_camera(self):
        self.is_streaming_2d = False
        time.sleep(0.2) # 等待采图线程退出
        
        try:
            if self.device_controller:
                self.device_controller.close()
            if self.client:
                self.client.disconnect()
        except Exception as e:
            print(f"关闭相机异常: {e}")
            
        self.is_connected = False
        self.connection_status.emit(False, "相机已断开")

    def start_2d_stream(self):
        if not self.is_connected or self.is_streaming_2d:
            return
            
        self.is_streaming_2d = True
        self._thread = threading.Thread(target=self._stream_loop, daemon=True)
        self._thread.start()

    def _stream_loop(self):
        """2D 图像采集循环"""
        # 设置为 FLASH 曝光模式
        try:
            self.parameter_manager.reset_current_value()
            self.parameter_manager.update_current_enumeration_value('2dParameters.exposureMode', 'FLASH')
            self.parameter_manager.update_current_integer_value('2dParameters.exposureTime', 5000)
        except Exception as e:
            print(f"设置 2D 参数失败: {e}")

        img_path = os.path.join(self.temp_dir, 'temp_2d_stream.bmp')
        
        while self.is_streaming_2d:
            with self._lock: # 使用锁，防止 3D 采集中断 2D 导致底层崩溃
                try:
                    texture_image = self.device_controller.grab_texture_image()
                    
                    # 💡【未来优化点】：如果您在官方文档找到了转 Numpy 数组的方法
                    # 可以直接在这里提取数组，并通过 image_grabbed.emit(numpy_array) 传给界面。
                    # 目前这里仍采用存入硬盘的方式。
                    texture_image.save(img_path)
                    
                    self.image_grabbed.emit(img_path)
                except Exception as e:
                    print(f"获取 2D 图像失败: {e}")
                    
            time.sleep(0.05) # 限制刷新率(约20帧/秒)，避免占满 CPU 并且保护硬盘

    def trigger_3d_capture(self):
        """触发拍摄 3D 点云（单次）"""
        if not self.is_connected:
            return
            
        # 暂停 2D 流，并在新线程中采集 3D
        threading.Thread(target=self._capture_3d_task, daemon=True).start()

    def _capture_3d_task(self):
        was_streaming = self.is_streaming_2d
        self.is_streaming_2d = False
        time.sleep(0.1) # 稍作等待，让 2D 循环彻底让出总线

        with self._lock:
            try:
                # 重置并配置 3D 参数
                self.parameter_manager.reset_current_value()
                self.parameter_manager.update_current_integer_value('3dParameters.exposureTimeArray[0]', 30000)
                
                pc_path = os.path.join(self.temp_dir, 'temp_3d_cloud.pcd')
                
                # 抓取点云并保存到本地
                point_cloud = self.device_controller.grab_point_cloud()
                point_cloud.save(pc_path)
                
                # 发送点云保存路径给主界面渲染
                self.point_cloud_grabbed.emit(pc_path)
                
            except Exception as e:
                print(f"采集 3D 点云异常: {e}")

        # 如果原本在实时流，采集完恢复 2D 画面
        if was_streaming:
            self.start_2d_stream()
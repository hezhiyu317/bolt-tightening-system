# pcl_bridge.py
"""
Python ↔ C++ 点云处理桥接模块
支持两种后端：
  1. pybind11 扩展 (pcl_processor.pyd)  —— 优先
  2. subprocess 调用 (pipeline_cli.exe)  —— 备选
"""
import os
import sys
import json
import subprocess
import threading
from PyQt5.QtCore import QObject, pyqtSignal

# ---------- 检测 pybind11 模块 ----------
_PYBIND_AVAILABLE = False
try:
    import pcl_processor
    _PYBIND_AVAILABLE = True
except ImportError:
    pass

# ---------- 检测 subprocess 可执行文件 ----------
_CLI_PATH = None
for candidate in ['./pipeline_cli.exe', './pipeline_cli',
                   './build/Release/pipeline_cli.exe',
                   './build/pipeline_cli.exe',
                   './build/pipeline_cli']:
    if os.path.isfile(candidate):
        _CLI_PATH = os.path.abspath(candidate)
        break


def _result_to_dict(r):
    """将 pybind11 PipelineResult 转为 Python dict"""
    return {
        'success':          r.success,
        'center_x':         r.center_x,
        'center_y':         r.center_y,
        'center_z':         r.center_z,
        'radius':           r.radius,
        'plane_a':          r.plane_a,
        'plane_b':          r.plane_b,
        'plane_c':          r.plane_c,
        'plane_d':          r.plane_d,
        'original_points':  r.original_points,
        'valid_points':     r.valid_points,
        'plane_points':     r.plane_points,
        'edge_points':      r.edge_points,
        'cluster_points':   r.cluster_points,
        'message':          r.message,
        'log':              getattr(r, 'log', ''),
    }


class PclBridge(QObject):
    """异步点云处理桥接类"""

    processing_finished = pyqtSignal(dict)   # 处理完成信号
    processing_error    = pyqtSignal(str)    # 处理出错信号

    def __init__(self):
        super().__init__()
        self._busy = False

        if _PYBIND_AVAILABLE:
            self._backend = 'pybind11'
        elif _CLI_PATH:
            self._backend = 'subprocess'
        else:
            self._backend = None

        print(f"[PclBridge] 后端: {self._backend or '无 (请编译 C++ 模块)'}")

    @property
    def is_available(self):
        return self._backend is not None

    @property
    def is_busy(self):
        return self._busy

    @property
    def backend(self):
        return self._backend

    # ------ 公开接口: 从 PCD 文件处理 ------
    def process_pcd(self, pcd_path, params_dict=None):
        if not self.is_available:
            self.processing_error.emit("C++ 后端不可用，请先编译 pcl_processor 或 pipeline_cli")
            return
        if self._busy:
            self.processing_error.emit("已有处理任务在运行，请等待")
            return

        self._busy = True
        threading.Thread(target=self._run, args=(pcd_path, params_dict), daemon=True).start()

    # ------ 公开接口: 从 numpy 数组处理 ------
    def process_numpy(self, points_array, params_dict=None):
        if self._backend != 'pybind11':
            self.processing_error.emit("numpy 直传仅支持 pybind11 后端")
            return
        if self._busy:
            self.processing_error.emit("已有处理任务在运行，请等待")
            return

        self._busy = True
        threading.Thread(target=self._run_numpy, args=(points_array, params_dict), daemon=True).start()

    # ============ 内部实现 ============

    def _build_pybind_params(self, d):
        params = pcl_processor.PipelineParams()
        if d:
            for k, v in d.items():
                if hasattr(params, k):
                    setattr(params, k, v)
        return params

    def _run(self, pcd_path, params_dict):
        try:
            if self._backend == 'pybind11':
                params = self._build_pybind_params(params_dict)
                result = pcl_processor.run_pipeline(pcd_path, params)
                self.processing_finished.emit(_result_to_dict(result))
            else:
                self._run_subprocess(pcd_path, params_dict)
        except Exception as e:
            self.processing_error.emit(f"处理异常: {e}")
        finally:
            self._busy = False

    def _run_numpy(self, points_array, params_dict):
        try:
            import numpy as np
            pts = np.asarray(points_array, dtype=np.float32).reshape(-1, 3)
            params = self._build_pybind_params(params_dict)
            result = pcl_processor.run_pipeline_from_numpy(pts, params)
            self.processing_finished.emit(_result_to_dict(result))
        except Exception as e:
            self.processing_error.emit(f"处理异常: {e}")
        finally:
            self._busy = False

    def _run_subprocess(self, pcd_path, params_dict):
        cmd = [_CLI_PATH, pcd_path]
        if params_dict:
            cmd.append(str(params_dict.get('plane_distance_threshold', 0.05)))
            cmd.append(str(params_dict.get('edge_search_radius', 2.0)))
            # cmd.append(str(params_dict.get('edge_k_neighbors', 50)))
            cmd.append(str(params_dict.get('edge_num_threads', 4)))
            # cmd.append(str(params_dict.get('edge_curvature_thresh', 0.04)))
            cmd.append(str(params_dict.get('cluster_tolerance', 2.0)))
            cmd.append(str(params_dict.get('min_cluster_size', 50)))
            cmd.append(str(params_dict.get('max_cluster_size', 1000)))

        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=120)

        # 提取 stdout 中的 JSON（可能混有 C++ 日志，取最后一个 { ... }）
        stdout = proc.stdout.strip()
        json_start = stdout.rfind('{')
        json_end   = stdout.rfind('}')
        if json_start == -1 or json_end == -1:
            self.processing_error.emit(f"未获取到 JSON 输出:\n{stdout}\n{proc.stderr}")
            return

        data = json.loads(stdout[json_start:json_end + 1])
        # 补全可能缺失的字段
        data.setdefault('log', proc.stderr)
        self.processing_finished.emit(data)
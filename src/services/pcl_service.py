"""PCL 点云处理服务 — 多簇批量圆拟合。

重构自 test_total/test_total/pcl_bridge.py。
异步后台线程：对一次 3D 采图的 PCD 文件，遍历所有簇做圆拟合，
返回所有螺栓孔圆心列表。

双后端透明切换：pybind11 .pyd 优先，pipeline_cli.exe subprocess 备选。
"""

import glob
import json
import os
import subprocess
import threading
from datetime import datetime
from typing import Any, Dict, List, Optional

from PyQt5.QtCore import QObject, pyqtSignal

from src.utils.config_manager import config
from src.utils.app_logger import app_logger
from src.models.app_state import app_state, PclResult

# ---- 后端检测 ---------------------------------------------------------------

_PYBIND_AVAILABLE = False
try:
    import pcl_processor  # noqa: F401
    _PYBIND_AVAILABLE = True
except ImportError:
    # 尝试把旧构建目录加入搜索路径再导入
    _OLD_BUILD = "test_total/test_total/build/Release"
    if os.path.isdir(_OLD_BUILD):
        import sys as _sys
        _abs_build = os.path.abspath(_OLD_BUILD)
        if _abs_build not in _sys.path:
            _sys.path.insert(0, _abs_build)
        try:
            import pcl_processor  # noqa: F401,F811
            _PYBIND_AVAILABLE = True
        except ImportError:
            pass

_CLI_PATH: Optional[str] = None
for _candidate in [
    "./pipeline_cli.exe",
    "./pipeline_cli",
    "./build/Release/pipeline_cli.exe",
    "./build/pipeline_cli.exe",
    "./build/pipeline_cli",
    "../cpp/build/Release/pipeline_cli.exe",
    "test_total/test_total/build/Release/pipeline_cli.exe",
]:
    if os.path.isfile(_candidate):
        _CLI_PATH = os.path.abspath(_candidate)
        break


class PclService(QObject):
    """PCL 点云处理服务 — 多簇批量圆拟合。

    Usage:
        pcl = PclService()
        pcl.processing_finished.connect(on_result)
        pcl.cluster_progress.connect(on_progress)
        pcl.process_pcd("temp_3d_cloud.pcd")
    """

    processing_finished = pyqtSignal(dict)     # 完整结果
    processing_error = pyqtSignal(str)         # 致命错误
    cluster_progress = pyqtSignal(int, int)    # (current, total)

    def __init__(self, parent: QObject = None):
        super().__init__(parent)
        self._busy = False
        self._cancel_flag = False

        if _PYBIND_AVAILABLE:
            self._backend = "pybind11"
        elif _CLI_PATH:
            self._backend = "subprocess"
        else:
            self._backend = None

        if self._backend:
            app_logger.info(f"PCL 后端: {self._backend}")
        else:
            app_logger.warning("PCL 后端不可用，请编译 C++ 模块")

    # ---- public API -----------------------------------------------------------

    @property
    def is_available(self) -> bool:
        return self._backend is not None

    @property
    def is_busy(self) -> bool:
        return self._busy

    @property
    def backend(self) -> Optional[str]:
        return self._backend

    def process_pcd(
        self,
        pcd_path: str,
        params_override: Dict[str, Any] = None,
    ):
        """异步处理 PCD 文件：遍历所有簇，批量圆拟合。

        Args:
            pcd_path: 3D 点云 PCD 文件路径。
            params_override: 覆盖 system.yaml 中 pcl.default_params 的参数字典。
        """
        if not self.is_available:
            self.processing_error.emit("C++ PCL 后端不可用，请先编译")
            return
        if self._busy:
            self.processing_error.emit("已有处理任务在运行")
            return

        self._busy = True
        self._cancel_flag = False
        app_state.pcl_status = "processing"
        threading.Thread(
            target=self._run,
            args=(pcd_path, params_override or {}),
            daemon=True,
        ).start()

    def cancel(self):
        """取消当前处理。"""
        self._cancel_flag = True

    # ---- internals ------------------------------------------------------------

    def _run(self, pcd_path: str, params_override: Dict[str, Any]):
        try:
            params = dict(config.pcl_params)
            params.update(params_override)

            # 清理上次残留的 cluster 文件
            cluster_pattern = os.path.join(os.getcwd(), "cluster*.pcd")
            for f in glob.glob(cluster_pattern):
                try:
                    os.remove(f)
                except OSError:
                    pass

            # 第一遍：全流水线 → 得到平面方程 + 第 1 个圆心 + 簇文件落盘
            result1 = self._call_backend(pcd_path, params, 1)
            if not result1.get("success"):
                msg = result1.get("message", "PCL 处理失败")
                self.processing_error.emit(msg)
                app_logger.error(f"PCL 第一遍失败: {msg}")
                self._finish(success=False)
                return

            # 扫描簇文件
            cluster_files = sorted(
                glob.glob(cluster_pattern),
                key=lambda f: int(
                    os.path.splitext(os.path.basename(f))[0].replace("cluster", "")
                ),
            )
            if not cluster_files:
                self.processing_error.emit("未找到任何聚类文件")
                self._finish(success=False)
                return

            total = len(cluster_files)
            self.cluster_progress.emit(1, total)

            # 收集所有圆心
            centers: List[Dict[str, Any]] = []
            center = self._extract_center(result1)
            if center:
                center["cluster_index"] = 1
                centers.append(center)

            # 遍历剩余簇文件
            for i, cluster_file in enumerate(cluster_files[1:], start=2):
                if self._cancel_flag:
                    app_logger.info("PCL 处理已取消")
                    self._finish(success=False)
                    return

                result = self._call_backend(cluster_file, params, 1)
                if result.get("success"):
                    c = self._extract_center(result)
                    if c:
                        c["cluster_index"] = i
                        centers.append(c)

                self.cluster_progress.emit(i, total)

            # 清理簇文件
            for f in cluster_files:
                try:
                    os.remove(f)
                except OSError:
                    pass

            # 汇总结果
            final = {
                "success": len(centers) > 0,
                "pcd_path": pcd_path,
                "timestamp": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
                "centers": centers,
                "plane": {
                    "a": result1.get("plane_a", 0),
                    "b": result1.get("plane_b", 0),
                    "c": result1.get("plane_c", 0),
                    "d": result1.get("plane_d", 0),
                },
                "stats": {
                    "original_points": result1.get("original_points", 0),
                    "valid_points": result1.get("valid_points", 0),
                    "plane_points": result1.get("plane_points", 0),
                    "edge_points": result1.get("edge_points", 0),
                    "cluster_points": result1.get("cluster_points", 0),
                },
                "cluster_count": total,
                "center_count": len(centers),
                "log": result1.get("log", ""),
            }

            self.processing_finished.emit(final)
            app_logger.info(
                f"PCL 处理完成: {len(centers)}/{total} 个簇拟合成功"
            )

            # 更新 app_state
            pcl_result = PclResult(
                success=True,
                center_x=centers[0]["x"] if centers else 0,
                center_y=centers[0]["y"] if centers else 0,
                center_z=centers[0]["z"] if centers else 0,
                radius=centers[0]["radius"] if centers else 0,
                cluster_count=total,
            )
            app_state.last_pcl_result = pcl_result
            self._finish(success=True)

        except Exception as e:
            msg = f"PCL 处理异常: {e}"
            self.processing_error.emit(msg)
            app_logger.exception(msg)
            self._finish(success=False)

    def _finish(self, *, success: bool):
        self._busy = False
        app_state.pcl_status = "done" if success else "error"

    # ---- backend call ---------------------------------------------------------

    def _call_backend(
        self,
        pcd_path: str,
        params: Dict[str, Any],
        target_cluster_index: int = 1,
    ) -> Dict[str, Any]:
        """同步调用 PCL 后端，返回结果字典。"""
        if self._backend == "pybind11":
            return self._call_pybind(pcd_path, params, target_cluster_index)
        else:
            return self._call_cli(pcd_path, params)

    def _call_pybind(
        self,
        pcd_path: str,
        params: Dict[str, Any],
        target_cluster_index: int,
    ) -> Dict[str, Any]:
        """pybind11 直调。"""
        p = pcl_processor.PipelineParams()  # noqa: F405
        for k, v in params.items():
            if hasattr(p, k):
                setattr(p, k, v)
        p.target_cluster_index = target_cluster_index

        r = pcl_processor.run_pipeline(pcd_path, p)  # noqa: F405
        return self._pybind_result_to_dict(r)

    @staticmethod
    def _pybind_result_to_dict(r) -> Dict[str, Any]:
        return {
            "success": r.success,
            "center_x": r.center_x,
            "center_y": r.center_y,
            "center_z": r.center_z,
            "radius": r.radius,
            "plane_a": r.plane_a,
            "plane_b": r.plane_b,
            "plane_c": r.plane_c,
            "plane_d": r.plane_d,
            "original_points": r.original_points,
            "valid_points": r.valid_points,
            "plane_points": r.plane_points,
            "edge_points": r.edge_points,
            "cluster_points": r.cluster_points,
            "message": r.message,
            "log": getattr(r, "log", ""),
        }

    def _call_cli(
        self,
        pcd_path: str,
        params: Dict[str, Any],
    ) -> Dict[str, Any]:
        """subprocess 调用 pipeline_cli.exe。"""
        cmd = [
            _CLI_PATH,
            pcd_path,
            str(params.get("plane_distance_threshold", 0.05)),
            str(params.get("edge_search_radius", 2.0)),
            str(params.get("edge_num_threads", 4)),
            str(params.get("cluster_tolerance", 2.0)),
            str(params.get("min_cluster_size", 50)),
            str(params.get("max_cluster_size", 1000)),
        ]
        proc = subprocess.run(
            cmd, capture_output=True, text=True, timeout=120,
        )

        stdout = proc.stdout.strip()
        json_start = stdout.rfind("{")
        json_end = stdout.rfind("}")
        if json_start == -1 or json_end == -1:
            return {
                "success": False,
                "message": f"CLI 未返回 JSON: {stdout[:200]}",
            }

        data = json.loads(stdout[json_start:json_end + 1])
        data.setdefault("log", proc.stderr or "")
        return data

    # ---- helpers --------------------------------------------------------------

    @staticmethod
    def _extract_center(result: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        """从单次流水线结果中提取圆心，过滤失败结果。"""
        if not result.get("success"):
            return None
        x = result.get("center_x", 0)
        y = result.get("center_y", 0)
        z = result.get("center_z", 0)
        r = result.get("radius", 0)
        # 圆拟合失败返回 (0,0,0) + radius=0 (C++ pipeline.cpp:110)
        if x == 0.0 and y == 0.0 and z == 0.0 and r == 0.0:
            return None
        return {"x": x, "y": y, "z": z, "radius": r}

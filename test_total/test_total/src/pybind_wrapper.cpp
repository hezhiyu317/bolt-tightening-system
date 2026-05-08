#include <pybind11/pybind11.h>
#include <pybind11/stl.h>
#include <pybind11/numpy.h>
#include "point_cloud_pipeline.h"

namespace py = pybind11;

PYBIND11_MODULE(pcl_processor, m) {
    m.doc() = "C++/PCL 点云处理流水线 – Python 桥接模块";

    // ---------- PipelineParams ----------
    py::class_<PipelineParams>(m, "PipelineParams")
        .def(py::init<>())
        .def_readwrite("plane_distance_threshold",
                       &PipelineParams::plane_distance_threshold)
        .def_readwrite("edge_search_radius",
                       &PipelineParams::edge_search_radius)
        .def_readwrite("edge_num_threads",
                       &PipelineParams::edge_num_threads)
        // .def_readwrite("edge_curvature_thresh",
        //                &PipelineParams::edge_curvature_thresh)
        .def_readwrite("cluster_tolerance",
                       &PipelineParams::cluster_tolerance)
        .def_readwrite("min_cluster_size",
                       &PipelineParams::min_cluster_size)
        .def_readwrite("max_cluster_size",
                       &PipelineParams::max_cluster_size)
        .def_readwrite("input_in_millimeters",
                       &PipelineParams::input_in_millimeters);

    // ---------- PipelineResult ----------
    py::class_<PipelineResult>(m, "PipelineResult")
        .def(py::init<>())
        .def_readonly("center_x",        &PipelineResult::center_x)
        .def_readonly("center_y",        &PipelineResult::center_y)
        .def_readonly("center_z",        &PipelineResult::center_z)
        .def_readonly("radius",          &PipelineResult::radius)
        .def_readonly("plane_a",         &PipelineResult::plane_a)
        .def_readonly("plane_b",         &PipelineResult::plane_b)
        .def_readonly("plane_c",         &PipelineResult::plane_c)
        .def_readonly("plane_d",         &PipelineResult::plane_d)
        .def_readonly("original_points", &PipelineResult::original_points)
        .def_readonly("valid_points",    &PipelineResult::valid_points)
        .def_readonly("plane_points",    &PipelineResult::plane_points)
        .def_readonly("edge_points",     &PipelineResult::edge_points)
        .def_readonly("cluster_points",  &PipelineResult::cluster_points)
        .def_readonly("success",         &PipelineResult::success)
        .def_readonly("message",         &PipelineResult::message)
        .def_readonly("log",             &PipelineResult::log);

    // ---------- run_pipeline (PCD 文件路径) ----------
    m.def("run_pipeline",
        [](const std::string& pcd_path, const PipelineParams& params) {
            py::gil_scoped_release release;   // 释放 GIL，不阻塞 UI
            return runPipeline(pcd_path, params);
        },
        py::arg("pcd_path"),
        py::arg("params") = PipelineParams(),
        "从 PCD 文件运行完整流水线");

    // ---------- run_pipeline_from_numpy (Nx3 float32 数组) ----------
    m.def("run_pipeline_from_numpy",
        [](py::array_t<float, py::array::c_style | py::array::forcecast> points,
           const PipelineParams& params) {
            py::buffer_info buf = points.request();
            if (buf.ndim != 2 || buf.shape[1] != 3)
                throw std::runtime_error("需要 Nx3 的 float32 数组");

            py::gil_scoped_release release;
            return runPipelineFromPoints(
                static_cast<const float*>(buf.ptr),
                static_cast<int>(buf.shape[0]),
                params);
        },
        py::arg("points"),
        py::arg("params") = PipelineParams(),
        "从 Nx3 numpy 数组运行流水线");
}

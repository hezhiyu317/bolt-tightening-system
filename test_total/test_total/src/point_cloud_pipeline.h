#ifndef POINT_CLOUD_PIPELINE_H
#define POINT_CLOUD_PIPELINE_H

#include <string>

/**
 * 流水线参数配置
 */
struct PipelineParams {
    float plane_distance_threshold;   // 平面分割距离阈值
    float edge_search_radius;         // 边缘检测搜索半径
    // int edge_k_neighbors;
    int edge_num_threads;             // 边缘检测线程数
    // float edge_curvature_thresh;           // 曲率阈值
    float cluster_tolerance;          // 欧式聚类容差
    int   min_cluster_size;           // 最小聚类点数
    int   max_cluster_size;           // 最大聚类点数
    bool  input_in_millimeters; 
    int target_cluster_index = 1;      // 目标聚类索引

    PipelineParams()
        : plane_distance_threshold(0.05f)
        , edge_search_radius(2.0f)
        // , edge_k_neighbors(50)
        , edge_num_threads(4)
        // , edge_curvature_thresh(0.04f)
        , cluster_tolerance(2.0f)
        , min_cluster_size(50)
        , max_cluster_size(1000)
        , input_in_millimeters(true)
        , target_cluster_index(1)
    {}
};

/**
 * 流水线处理结果
 */
struct PipelineResult {
    // 圆心坐标
    float center_x, center_y, center_z;
    float radius;

    // 平面方程 ax+by+cz+d=0
    float plane_a, plane_b, plane_c, plane_d;

    // 各步骤统计
    int original_points;
    int valid_points;
    int plane_points;
    int edge_points;
    int cluster_points;

    bool success;
    std::string message;   // 简要结果描述
    std::string log;       // 完整处理日志

    PipelineResult()
        : center_x(0), center_y(0), center_z(0), radius(0)
        , plane_a(0), plane_b(0), plane_c(0), plane_d(0)
        , original_points(0), valid_points(0), plane_points(0)
        , edge_points(0), cluster_points(0)
        , success(false) {}
};

/**
 * 从 PCD 文件运行完整流水线
 */
PipelineResult runPipeline(const std::string& pcd_path,
                           const PipelineParams& params = PipelineParams());

/**
 * 从内存点数据运行流水线（供 numpy 直传）
 * @param points_data 浮点数组 [x0,y0,z0, x1,y1,z1, ...]
 * @param num_points  点的数量
 */
PipelineResult runPipelineFromPoints(const float* points_data,
                                     int num_points,
                                     const PipelineParams& params = PipelineParams());

#endif // POINT_CLOUD_PIPELINE_H
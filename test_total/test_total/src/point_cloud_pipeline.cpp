#include "point_cloud_pipeline.h"
#include "point_cloud_processor.h"

#include <pcl/io/pcd_io.h>
#include <pcl/point_types.h>
#include <iostream>
#include <sstream>

// ============ 内部核心：对已加载点云执行流水线 ============
static PipelineResult runPipelineInternal(
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud,
    const PipelineParams& params)
{
    PipelineResult result;

    // 捕获所有 std::cout 输出到日志
    std::ostringstream log_buf;
    std::streambuf* saved_cout = std::cout.rdbuf(log_buf.rdbuf());

    try {
        result.original_points = static_cast<int>(cloud->points.size());

        if (cloud->empty()) {
            result.message = "输入点云为空";
            std::cout.rdbuf(saved_cout);
            result.log = log_buf.str();
            return result;
        }

        // === 步骤 1: 去除 NaN ===
        cloud = removeInvalidPoints(cloud);
        result.valid_points = static_cast<int>(cloud->points.size());
        if (cloud->empty()) {
            result.message = "去除 NaN 后无有效点";
            std::cout.rdbuf(saved_cout);
            result.log = log_buf.str();
            return result;
        }

        // === 步骤 2: RANSAC 平面分割 ===
        auto cloud_plane = planeSegmentation(cloud, params.plane_distance_threshold);
        result.plane_points = static_cast<int>(cloud_plane->points.size());
        // 从全局变量读取平面参数（planeSegmentation 内部已设置）
        result.plane_a = g_plane_params.a;
        result.plane_b = g_plane_params.b;
        result.plane_c = g_plane_params.c;
        result.plane_d = g_plane_params.d;

        if (cloud_plane->empty()) {
            result.message = "平面分割失败，未找到平面";
            std::cout.rdbuf(saved_cout);
            result.log = log_buf.str();
            return result;
        }

        // === 步骤 3: 边缘检测 ===
        auto edges = edge_detection(cloud_plane, params.edge_search_radius, params.edge_num_threads);


        result.edge_points = static_cast<int>(edges->points.size());

        if (edges->empty()) {
            result.message = "边缘检测未提取到边缘点";
            std::cout.rdbuf(saved_cout);
            result.log = log_buf.str();
            return result;
        }

        // === 步骤 4: 欧式聚类 —— 沿用原始逻辑，所有簇落盘 ===
        euclidean_cluster_template<pcl::PointXYZ>(
            edges,
            params.cluster_tolerance,
            params.min_cluster_size,
            params.max_cluster_size);

        // === 步骤 4.5: 从磁盘重新加载指定编号的聚类文件 ===
        // euclidean_cluster_template 内部的命名规则：
        //   第 0 个聚类 → cluster1.pcd
        //   第 1 个聚类 → cluster2.pcd  （cluster_id 先++再拼文件名）
        // 所以 target_cluster_index = 1 对应第一个聚类
        std::string cluster_filename = "cluster" + std::to_string(params.target_cluster_index) + ".pcd";
        pcl::PointCloud<pcl::PointXYZ>::Ptr cluster(new pcl::PointCloud<pcl::PointXYZ>);

        if (pcl::io::loadPCDFile<pcl::PointXYZ>(cluster_filename, *cluster) == -1) {
            result.message = "无法加载聚类文件: " + cluster_filename;
            std::cout.rdbuf(saved_cout);
            result.log = log_buf.str();
            return result;
        }

        result.cluster_points = static_cast<int>(cluster->points.size());

        if (cluster->empty()) {
            result.message = "聚类文件 " + cluster_filename + " 中无有效点，无法进行圆拟合";
            std::cout.rdbuf(saved_cout);
            result.log = log_buf.str();
            return result;
        }

        std::cout << "已加载聚类文件: " << cluster_filename
                  << "，包含 " << cluster->points.size() << " 个点" << std::endl;

        // === 步骤 5: 2D 圆拟合 ===
        float fitted_radius = 0.0f;
        pcl::PointXYZ center = detect_circle(cluster,
                                             params.input_in_millimeters,
                                             &fitted_radius);

        // detect_circle 失败时返回 (0,0,0) 且 radius=0
        if (center.x == 0.0f && center.y == 0.0f &&
            center.z == 0.0f && fitted_radius == 0.0f) {
            result.message = "圆拟合失败";
            std::cout.rdbuf(saved_cout);
            result.log = log_buf.str();
            return result;
        }

        result.center_x = center.x;
        result.center_y = center.y;
        result.center_z = center.z;
        result.radius   = fitted_radius;
        result.success  = true;
        result.message  = "流水线处理成功";

    } catch (const std::exception& e) {
        result.message = std::string("流水线异常: ") + e.what();
    } catch (...) {
        result.message = "流水线未知异常";
    }

    std::cout.rdbuf(saved_cout);
    result.log = log_buf.str();
    return result;
}


// ============ 文件路径入口 ============
PipelineResult runPipeline(const std::string& pcd_path,
                           const PipelineParams& params)
{
    PipelineResult result;
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud(new pcl::PointCloud<pcl::PointXYZ>);

    if (pcl::io::loadPCDFile<pcl::PointXYZ>(pcd_path, *cloud) == -1) {
        result.message = "无法加载 PCD 文件: " + pcd_path;
        return result;
    }
    return runPipelineInternal(cloud, params);
}


// ============ 内存数组入口（numpy 直传） ============
PipelineResult runPipelineFromPoints(const float* data, int num_points,
                                     const PipelineParams& params)
{
    PipelineResult result;
    if (!data || num_points <= 0) {
        result.message = "输入数据无效";
        return result;
    }

    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud(new pcl::PointCloud<pcl::PointXYZ>);
    cloud->points.resize(num_points);
    for (int i = 0; i < num_points; ++i) {
        cloud->points[i].x = data[i * 3 + 0];
        cloud->points[i].y = data[i * 3 + 1];
        cloud->points[i].z = data[i * 3 + 2];
    }
    cloud->width    = num_points;
    cloud->height   = 1;
    cloud->is_dense = false;

    return runPipelineInternal(cloud, params);
}
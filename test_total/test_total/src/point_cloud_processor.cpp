#include "point_cloud_processor.h"
#include <iostream>
#include <cmath>
#include <pcl/segmentation/sac_segmentation.h>
#include <pcl/filters/extract_indices.h>
#include <pcl/features/normal_3d.h>
#include <pcl/kdtree/kdtree_flann.h>
#include <pcl/features/boundary.h>
#include <pcl/features/moment_of_inertia_estimation.h>
#include <pcl/segmentation/extract_clusters.h>
#include <pcl/filters/statistical_outlier_removal.h>
#include <pcl/features/normal_3d_omp.h>

PlaneParameters g_plane_params = {0.0f, 0.0f, 0.0f, 0.0f};

// ==================== removeInvalidPoints ====================
pcl::PointCloud<pcl::PointXYZ>::Ptr removeInvalidPoints(
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud)
{
    pcl::PointCloud<pcl::PointXYZ>::Ptr filtered(new pcl::PointCloud<pcl::PointXYZ>);
    filtered->points.reserve(cloud->points.size());

    for (const auto& pt : cloud->points) {
        if (!std::isnan(pt.x) && !std::isnan(pt.y) && !std::isnan(pt.z))
            filtered->points.push_back(pt);
    }

    filtered->width    = filtered->points.size();
    filtered->height   = 1;
    filtered->is_dense = true;

    std::cout << "过滤后点云数量: " << filtered->points.size()
              << " (移除了 " << cloud->points.size() - filtered->points.size()
              << " 个无效点)" << std::endl;
    return filtered;
}


// ==================== planeSegmentation ====================
pcl::PointCloud<pcl::PointXYZ>::Ptr planeSegmentation(
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud,
    float distanceThreshold)
{
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud_plane(new pcl::PointCloud<pcl::PointXYZ>);
    pcl::SACSegmentation<pcl::PointXYZ> seg;
    pcl::ModelCoefficients::Ptr coefficients(new pcl::ModelCoefficients);
    pcl::PointIndices::Ptr inliers(new pcl::PointIndices);

    seg.setOptimizeCoefficients(true);
    seg.setModelType(pcl::SACMODEL_PLANE);
    seg.setMethodType(pcl::SAC_RANSAC);
    seg.setMaxIterations(5000);
    seg.setDistanceThreshold(distanceThreshold);

    seg.setInputCloud(cloud);
    seg.segment(*inliers, *coefficients);

    if (inliers->indices.empty()) {
        PCL_ERROR("Could not estimate a planar model for the given dataset.\n");
        return cloud_plane;
    }

    pcl::ExtractIndices<pcl::PointXYZ> extract;
    extract.setInputCloud(cloud);
    extract.setIndices(inliers);
    extract.setNegative(false);
    extract.filter(*cloud_plane);

    if (coefficients->values.size() >= 4) {
        g_plane_params.a = coefficients->values[0];
        g_plane_params.b = coefficients->values[1];
        g_plane_params.c = coefficients->values[2];
        g_plane_params.d = coefficients->values[3];

        Eigen::Vector3f normal(g_plane_params.a, g_plane_params.b, g_plane_params.c);
        normal.normalize();
        std::cout << "平面参数: a=" << g_plane_params.a
                  << " b=" << g_plane_params.b
                  << " c=" << g_plane_params.c
                  << " d=" << g_plane_params.d << std::endl;
        std::cout << "平面法向量: [" << normal[0] << ", "
                  << normal[1] << ", " << normal[2] << "]" << std::endl;
    }

    cloud_plane->width    = cloud_plane->points.size();
    cloud_plane->height   = 1;
    cloud_plane->is_dense = true;
    return cloud_plane;
}


// ==================== edge_detection ====================
pcl::PointCloud<pcl::PointXYZ>::Ptr edge_detection(
    pcl::PointCloud<pcl::PointXYZ>::Ptr& cloud,
    float search_radius,
    int num_threads)
{
    auto start = std::chrono::steady_clock::now();

    // ---- 法线估计：OMP 多线程 + 半径搜索（保持原有质量） ----
    pcl::NormalEstimationOMP<pcl::PointXYZ, pcl::Normal> ne;
    ne.setNumberOfThreads(num_threads);
    ne.setInputCloud(cloud);
    pcl::search::KdTree<pcl::PointXYZ>::Ptr tree(new pcl::search::KdTree<pcl::PointXYZ>());
    ne.setSearchMethod(tree);
    pcl::PointCloud<pcl::Normal>::Ptr normals(new pcl::PointCloud<pcl::Normal>);
    ne.setRadiusSearch(search_radius);          // ← 保持半径搜索
    ne.compute(*normals);

    auto after_normal = std::chrono::steady_clock::now();

    // ---- 边界估计：半径搜索 ----
    pcl::BoundaryEstimation<pcl::PointXYZ, pcl::Normal, pcl::Boundary> be;
    be.setInputCloud(cloud);
    be.setInputNormals(normals);
    be.setSearchMethod(tree);
    pcl::PointCloud<pcl::Boundary> boundaries;
    be.setRadiusSearch(search_radius);          // ← 保持半径搜索
    be.compute(boundaries);

    auto after_boundary = std::chrono::steady_clock::now();

    // ---- 提取边缘点 ----
    pcl::PointCloud<pcl::PointXYZ>::Ptr edge_points(new pcl::PointCloud<pcl::PointXYZ>);
    for (size_t i = 0; i < cloud->points.size(); ++i) {
        if (boundaries.points[i].boundary_point)
            edge_points->points.push_back(cloud->points[i]);
    }

    edge_points->width    = edge_points->points.size();
    edge_points->height   = 1;
    edge_points->is_dense = true;

    auto end = std::chrono::steady_clock::now();

    double t_normal   = std::chrono::duration<double, std::milli>(after_normal - start).count();
    double t_boundary = std::chrono::duration<double, std::milli>(after_boundary - after_normal).count();
    double t_total    = std::chrono::duration<double, std::milli>(end - start).count();

    std::cout << "边缘检测完成 (radius=" << search_radius
              << ", threads=" << num_threads << ")" << std::endl;
    std::cout << "  法线估计: " << t_normal << " ms" << std::endl;
    std::cout << "  边界估计: " << t_boundary << " ms" << std::endl;
    std::cout << "  总耗时:   " << t_total << " ms" << std::endl;
    std::cout << "  边缘点数: " << edge_points->points.size() << std::endl;

    return edge_points;
}
// pcl::PointCloud<pcl::PointXYZ>::Ptr edge_detection(
//     pcl::PointCloud<pcl::PointXYZ>::Ptr& cloud,
//     float search_radius,
//     int   num_threads,
//     float curvature_thresh)
// {
//     auto t0 = std::chrono::steady_clock::now();

//     // ---- 法线 + 曲率（OMP 多线程，半径搜索） ----
//     pcl::NormalEstimationOMP<pcl::PointXYZ, pcl::Normal> ne;
//     ne.setNumberOfThreads(num_threads);
//     ne.setInputCloud(cloud);
//     pcl::search::KdTree<pcl::PointXYZ>::Ptr tree(
//         new pcl::search::KdTree<pcl::PointXYZ>());
//     ne.setSearchMethod(tree);
//     ne.setRadiusSearch(search_radius);

//     pcl::PointCloud<pcl::Normal>::Ptr normals(new pcl::PointCloud<pcl::Normal>);
//     ne.compute(*normals);   // 内部同时计算了 curvature

//     auto t1 = std::chrono::steady_clock::now();

//     // ---- 直接用曲率筛选边缘点（无额外搜索） ----
//     pcl::PointCloud<pcl::PointXYZ>::Ptr edge_points(
//         new pcl::PointCloud<pcl::PointXYZ>);
//     edge_points->points.reserve(cloud->points.size() / 10);

//     for (size_t i = 0; i < cloud->points.size(); ++i) {
//         if (normals->points[i].curvature > curvature_thresh) {
//             edge_points->points.push_back(cloud->points[i]);
//         }
//     }

//     edge_points->width    = edge_points->points.size();
//     edge_points->height   = 1;
//     edge_points->is_dense = true;

//     auto t2 = std::chrono::steady_clock::now();

//     double ms_normal = std::chrono::duration<double, std::milli>(t1 - t0).count();
//     double ms_filter = std::chrono::duration<double, std::milli>(t2 - t1).count();
//     std::cout << "边缘检测 (曲率法): 法线=" << ms_normal
//               << "ms, 筛选=" << ms_filter
//               << "ms, 边缘点=" << edge_points->size() << std::endl;

//     return edge_points;
// }

// ==================== projectTo2D ====================
pcl::PointCloud<pcl::PointXY>::Ptr projectTo2D(
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud_3d)
{
    pcl::PointCloud<pcl::PointXY>::Ptr cloud_2d(new pcl::PointCloud<pcl::PointXY>);

    pcl::PCA<pcl::PointXYZ> pca;
    pca.setInputCloud(cloud_3d);

    Eigen::Vector3f axis_x = pca.getEigenVectors().col(0);
    Eigen::Vector3f axis_y = pca.getEigenVectors().col(1);

    Eigen::Vector4f centroid;
    pcl::compute3DCentroid(*cloud_3d, centroid);

    for (const auto& point : cloud_3d->points) {
        Eigen::Vector3f pt(point.x - centroid[0],
                           point.y - centroid[1],
                           point.z - centroid[2]);
        pcl::PointXY pt_2d;
        pt_2d.x = pt.dot(axis_x);
        pt_2d.y = pt.dot(axis_y);
        cloud_2d->points.push_back(pt_2d);
    }

    cloud_2d->width    = cloud_2d->points.size();
    cloud_2d->height   = 1;
    cloud_2d->is_dense = true;
    return cloud_2d;
}


// ==================== detect_circle（优化版） ====================
pcl::PointXYZ detect_circle(
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud,
    bool input_in_millimeters,
    float* out_radius)
{
    pcl::PointXYZ center;
    center.x = center.y = center.z = 0.0f;
    if (out_radius) *out_radius = 0.0f;

    if (!cloud || cloud->points.size() < 10) {
        std::cout << "警告：点云点数不足，无法进行圆拟合" << std::endl;
        return center;
    }

    try {
        // --- 副本 & 单位转换 ---
        pcl::PointCloud<pcl::PointXYZ>::Ptr proc(new pcl::PointCloud<pcl::PointXYZ>(*cloud));
        float scale_back = 1.0f;
        if (input_in_millimeters) {
            for (auto& p : proc->points) { p.x *= 0.001f; p.y *= 0.001f; p.z *= 0.001f; }
            scale_back = 1000.0f;
        }

        // --- 一次性 PCA（优化：避免重复计算） ---
        pcl::PCA<pcl::PointXYZ> pca;
        pca.setInputCloud(proc);
        Eigen::Matrix3f eigvecs = pca.getEigenVectors();
        Eigen::Vector3f axis_x  = eigvecs.col(0);
        Eigen::Vector3f axis_y  = eigvecs.col(1);

        Eigen::Vector4f centroid;
        pcl::compute3DCentroid(*proc, centroid);

        // --- 投影到 2D 并构造 PointXYZ (z=0) ---
        pcl::PointCloud<pcl::PointXYZ>::Ptr cloud2d(new pcl::PointCloud<pcl::PointXYZ>);
        cloud2d->points.reserve(proc->points.size());
        for (const auto& p : proc->points) {
            Eigen::Vector3f d(p.x - centroid[0], p.y - centroid[1], p.z - centroid[2]);
            pcl::PointXYZ q;
            q.x = d.dot(axis_x);
            q.y = d.dot(axis_y);
            q.z = 0.0f;
            cloud2d->points.push_back(q);
        }
        cloud2d->width = cloud2d->points.size();
        cloud2d->height = 1;
        cloud2d->is_dense = true;

        // --- 第一次 RANSAC 圆拟合 ---
        pcl::ModelCoefficients::Ptr coeff(new pcl::ModelCoefficients);
        pcl::PointIndices::Ptr inliers(new pcl::PointIndices);
        pcl::SACSegmentation<pcl::PointXYZ> seg;
        seg.setModelType(pcl::SACMODEL_CIRCLE2D);
        seg.setMethodType(pcl::SAC_RANSAC);
        seg.setDistanceThreshold(input_in_millimeters ? 0.0005f : 0.005f);
        seg.setMaxIterations(1000);
        seg.setInputCloud(cloud2d);
        seg.segment(*inliers, *coeff);

        if (inliers->indices.empty() || coeff->values.size() < 3) {
            std::cout << "圆拟合失败：内点不足" << std::endl;
            return center;
        }

        float cx2d   = coeff->values[0];
        float cy2d   = coeff->values[1];
        float radius  = coeff->values[2];

        // --- 统计滤波 + 二次精细拟合 ---
        std::vector<float> dists;
        dists.reserve(inliers->indices.size());
        for (int idx : inliers->indices) {
            float dx = cloud2d->points[idx].x - cx2d;
            float dy = cloud2d->points[idx].y - cy2d;
            dists.push_back(std::sqrt(dx * dx + dy * dy));
        }

        float mean_d = 0.0f;
        for (float d : dists) mean_d += d;
        mean_d /= static_cast<float>(dists.size());

        float std_d = 0.0f;
        for (float d : dists) std_d += (d - mean_d) * (d - mean_d);
        std_d = std::sqrt(std_d / static_cast<float>(dists.size()));

        float lo = std::max(0.0f, mean_d - 2.0f * std_d);
        float hi = mean_d + 2.0f * std_d;

        pcl::PointCloud<pcl::PointXYZ>::Ptr refined(new pcl::PointCloud<pcl::PointXYZ>);
        for (size_t i = 0; i < inliers->indices.size(); ++i) {
            if (dists[i] >= lo && dists[i] <= hi)
                refined->points.push_back(cloud2d->points[inliers->indices[i]]);
        }

        if (refined->points.size() >= 5) {
            refined->width = refined->points.size();
            refined->height = 1;
            refined->is_dense = true;

            pcl::ModelCoefficients::Ptr coeff2(new pcl::ModelCoefficients);
            pcl::PointIndices::Ptr inl2(new pcl::PointIndices);
            pcl::SACSegmentation<pcl::PointXYZ> seg2;
            seg2.setModelType(pcl::SACMODEL_CIRCLE2D);
            seg2.setMethodType(pcl::SAC_RANSAC);
            seg2.setDistanceThreshold(input_in_millimeters ? 0.0003f : 0.003f);
            seg2.setMaxIterations(2000);
            seg2.setInputCloud(refined);
            seg2.segment(*inl2, *coeff2);

            if (coeff2->values.size() >= 3) {
                cx2d   = coeff2->values[0];
                cy2d   = coeff2->values[1];
                radius = coeff2->values[2];
                std::cout << "二次精细拟合成功，内点: " << refined->points.size() << std::endl;
            }
        }

        // --- 2D → 3D 反投影（复用同一组 PCA 向量） ---
        center.x = centroid[0] + cx2d * axis_x[0] + cy2d * axis_y[0];
        center.y = centroid[1] + cx2d * axis_x[1] + cy2d * axis_y[1];
        center.z = centroid[2] + cx2d * axis_x[2] + cy2d * axis_y[2];

        if (input_in_millimeters) {
            center.x *= scale_back;
            center.y *= scale_back;
            center.z *= scale_back;
            radius   *= scale_back;
        }

        if (out_radius) *out_radius = radius;

        std::cout << "圆拟合成功: 圆心=(" << center.x << ", " << center.y
                  << ", " << center.z << ")  半径=" << radius << std::endl;

    } catch (const std::exception& e) {
        std::cerr << "圆拟合异常: " << e.what() << std::endl;
        center.x = center.y = center.z = 0.0f;
        if (out_radius) *out_radius = 0.0f;
    }

    return center;
}


// ==================== euclidean_cluster_template ====================
template<typename PointT>
void euclidean_cluster_template(
    const typename pcl::PointCloud<PointT>::Ptr& cloud,
    float cluster_tolerance,
    int min_cluster_size,
    int max_cluster_size)
{
    typename pcl::search::KdTree<PointT>::Ptr tree(new pcl::search::KdTree<PointT>);
    tree->setInputCloud(cloud);

    std::vector<pcl::PointIndices> cluster_indices;
    pcl::EuclideanClusterExtraction<PointT> ec;
    ec.setClusterTolerance(cluster_tolerance);
    ec.setMinClusterSize(min_cluster_size);
    ec.setMaxClusterSize(max_cluster_size);
    ec.setSearchMethod(tree);
    ec.setInputCloud(cloud);
    ec.extract(cluster_indices);

    int cluster_id = 0;
    for (const auto& indices : cluster_indices) {
        std::cout << "Cluster " << cluster_id << " size: " << indices.indices.size() << std::endl;
        typename pcl::PointCloud<PointT>::Ptr cc(new pcl::PointCloud<PointT>);
        for (const auto& idx : indices.indices)
            cc->points.push_back(cloud->points[idx]);
        cc->width = cc->points.size(); cc->height = 1; cc->is_dense = true;

        std::string filename = "cluster" + std::to_string(cluster_id + 1) + ".pcd";
        savePointCloud<PointT>(cc, filename, "聚类点云");
        ++cluster_id;
    }
}


// ==================== savePointCloud ====================
template<typename PointT>
bool savePointCloud(
    const typename pcl::PointCloud<PointT>::Ptr& cloud,
    const std::string& file_path,
    const std::string& description)
{
    if (!cloud || cloud->points.empty()) {
        std::cout << "警告: " << description << "为空，不进行保存" << std::endl;
        return false;
    }
    if (pcl::io::savePCDFileASCII(file_path, *cloud) == 0) {
        std::cout << "已保存 " << description << " → " << file_path << std::endl;
        return true;
    }
    PCL_ERROR("保存失败: %s → %s\n", description.c_str(), file_path.c_str());
    return false;
}


// ==================== removeOutliers ====================
pcl::PointCloud<pcl::PointXYZ>::Ptr removeOutliers(
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud,
    int mean_k,
    float std_dev_mul_thresh)
{
    pcl::PointCloud<pcl::PointXYZ>::Ptr filtered(new pcl::PointCloud<pcl::PointXYZ>);
    pcl::StatisticalOutlierRemoval<pcl::PointXYZ> sor;
    sor.setInputCloud(cloud);
    sor.setMeanK(mean_k);
    sor.setStddevMulThresh(std_dev_mul_thresh);
    sor.filter(*filtered);

    std::cout << "离群点去除: 保留 " << filtered->points.size()
              << " (移除 " << cloud->points.size() - filtered->points.size() << ")" << std::endl;

    filtered->width = filtered->points.size();
    filtered->height = 1;
    filtered->is_dense = true;
    return filtered;
}


// ==================== rotatePointCloud ====================
pcl::PointCloud<pcl::PointXYZ>::Ptr rotatePointCloud(
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud,
    Eigen::Vector3f vector_normal,
    Eigen::Vector3f vector_target)
{
    if (!cloud || cloud->empty()) {
        std::cerr << "错误：输入点云为空" << std::endl;
        return pcl::PointCloud<pcl::PointXYZ>::Ptr(new pcl::PointCloud<pcl::PointXYZ>);
    }

    vector_normal.normalize();
    vector_target.normalize();

    float dot = vector_normal.dot(vector_target);
    if (std::abs(dot) > 0.999999f)
        return pcl::PointCloud<pcl::PointXYZ>::Ptr(new pcl::PointCloud<pcl::PointXYZ>(*cloud));

    Eigen::Vector3f axis = vector_normal.cross(vector_target).normalized();
    float angle = std::acos(std::min(std::max(dot, -1.0f), 1.0f)); // clamp 防 NaN
    Eigen::Matrix3f R = Eigen::AngleAxisf(angle, axis).toRotationMatrix();

    pcl::PointCloud<pcl::PointXYZ>::Ptr rotated(new pcl::PointCloud<pcl::PointXYZ>);
    rotated->resize(cloud->size());
    for (size_t i = 0; i < cloud->points.size(); ++i) {
        Eigen::Vector3f v(cloud->points[i].x, cloud->points[i].y, cloud->points[i].z);
        v = R * v;
        rotated->points[i].x = v.x();
        rotated->points[i].y = v.y();
        rotated->points[i].z = v.z();
    }
    rotated->width = cloud->width;
    rotated->height = cloud->height;
    rotated->is_dense = cloud->is_dense;

    std::cout << "旋转完成, 角度: " << angle * 180.0f / static_cast<float>(M_PI) << " 度" << std::endl;
    return rotated;
}


// ==================== getLargestEuclideanCluster ====================
template<typename PointT>
typename pcl::PointCloud<PointT>::Ptr getLargestEuclideanCluster(
    const typename pcl::PointCloud<PointT>::Ptr& cloud,
    float cluster_tolerance,
    int min_cluster_size,
    int max_cluster_size)
{
    if (!cloud || cloud->empty()) {
        std::cerr << "错误: 输入点云为空!" << std::endl;
        return typename pcl::PointCloud<PointT>::Ptr(new pcl::PointCloud<PointT>);
    }

    typename pcl::search::KdTree<PointT>::Ptr tree(new pcl::search::KdTree<PointT>);
    tree->setInputCloud(cloud);

    std::vector<pcl::PointIndices> cluster_indices;
    pcl::EuclideanClusterExtraction<PointT> ec;
    ec.setClusterTolerance(cluster_tolerance);
    ec.setMinClusterSize(min_cluster_size);
    ec.setMaxClusterSize(max_cluster_size);
    ec.setSearchMethod(tree);
    ec.setInputCloud(cloud);
    ec.extract(cluster_indices);

    if (cluster_indices.empty()) {
        std::cout << "未找到符合条件的聚类" << std::endl;
        return typename pcl::PointCloud<PointT>::Ptr(new pcl::PointCloud<PointT>);
    }

    size_t max_size = 0;
    int best = 0;
    for (size_t i = 0; i < cluster_indices.size(); ++i) {
        size_t sz = cluster_indices[i].indices.size();
        std::cout << "聚类 " << i << " 大小: " << sz << std::endl;
        if (sz > max_size) { max_size = sz; best = static_cast<int>(i); }
    }

    typename pcl::PointCloud<PointT>::Ptr largest(new pcl::PointCloud<PointT>);
    for (const auto& idx : cluster_indices[best].indices)
        largest->points.push_back(cloud->points[idx]);
    largest->width = largest->points.size();
    largest->height = 1;
    largest->is_dense = true;

    std::cout << "最大聚类: " << largest->points.size() << " 点" << std::endl;
    return largest;
}


// ==================== 显式模板实例化 ====================
template void euclidean_cluster_template<pcl::PointXYZ>(
    const pcl::PointCloud<pcl::PointXYZ>::Ptr&, float, int, int);

template bool savePointCloud<pcl::PointXYZ>(
    const pcl::PointCloud<pcl::PointXYZ>::Ptr&, const std::string&, const std::string&);
template bool savePointCloud<pcl::PointXYZRGB>(
    const pcl::PointCloud<pcl::PointXYZRGB>::Ptr&, const std::string&, const std::string&);

template pcl::PointCloud<pcl::PointXYZ>::Ptr getLargestEuclideanCluster<pcl::PointXYZ>(
    const pcl::PointCloud<pcl::PointXYZ>::Ptr&, float, int, int);
template pcl::PointCloud<pcl::PointXYZRGB>::Ptr getLargestEuclideanCluster<pcl::PointXYZRGB>(
    const pcl::PointCloud<pcl::PointXYZRGB>::Ptr&, float, int, int);
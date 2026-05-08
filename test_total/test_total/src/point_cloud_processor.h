#ifndef POINT_CLOUD_PROCESSOR_H
#define POINT_CLOUD_PROCESSOR_H

#include <pcl/point_types.h>
#include <pcl/io/pcd_io.h>
#include <chrono>
#include <Eigen/Dense>
#include <pcl/common/pca.h>
#include <pcl/common/centroid.h>
#include <pcl/sample_consensus/model_types.h>
#include <pcl/sample_consensus/method_types.h>

// 平面参数结构体 ax+by+cz+d=0
typedef struct {
    float a;
    float b;
    float c;
    float d;
} PlaneParameters;

extern PlaneParameters g_plane_params;

/**
 * 去除点云中的 NaN 点
 */
pcl::PointCloud<pcl::PointXYZ>::Ptr removeInvalidPoints(
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud);

/**
 * RANSAC 平面分割
 */
pcl::PointCloud<pcl::PointXYZ>::Ptr planeSegmentation(
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud,
    float distanceThreshold);

/**
 * 2D 圆拟合，返回 3D 圆心
 * @param out_radius [可选] 输出拟合半径
 */
pcl::PointXYZ detect_circle(
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud,
    bool input_in_millimeters = true,
    float* out_radius = nullptr);

/**
 * 边缘检测
 */
pcl::PointCloud<pcl::PointXYZ>::Ptr edge_detection(
    pcl::PointCloud<pcl::PointXYZ>::Ptr& cloud,
    // int k_neighbors = 50,
    float search_radius = 2.0f,
    int num_threads = 4
    );

/**
 * PCA 投影 3D → 2D
 */
pcl::PointCloud<pcl::PointXY>::Ptr projectTo2D(
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud_3d);

/**
 * 通用欧式聚类（打印 + 保存）
 */
template<typename PointT>
void euclidean_cluster_template(
    const typename pcl::PointCloud<PointT>::Ptr& cloud,
    float cluster_tolerance,
    int min_cluster_size,
    int max_cluster_size);

/**
 * 通用点云保存
 */
template<typename PointT>
bool savePointCloud(
    const typename pcl::PointCloud<PointT>::Ptr& cloud,
    const std::string& file_path,
    const std::string& description = "点云");

/**
 * 统计滤波去除离群点
 */
pcl::PointCloud<pcl::PointXYZ>::Ptr removeOutliers(
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud,
    int mean_k = 50,
    float std_dev_mul_thresh = 1.0);

/**
 * 旋转点云
 */
pcl::PointCloud<pcl::PointXYZ>::Ptr rotatePointCloud(
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud,
    Eigen::Vector3f vector_normal,
    Eigen::Vector3f vector_target);

/**
 * 获取最大欧式聚类
 */
template<typename PointT>
typename pcl::PointCloud<PointT>::Ptr getLargestEuclideanCluster(
    const typename pcl::PointCloud<PointT>::Ptr& cloud,
    float cluster_tolerance,
    int min_cluster_size,
    int max_cluster_size);

#endif // POINT_CLOUD_PROCESSOR_H
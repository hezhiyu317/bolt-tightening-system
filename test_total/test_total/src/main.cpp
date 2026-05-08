#include <iostream>
#include <pcl/io/pcd_io.h>
#include <pcl/point_types.h>
#include "point_cloud_processor.h"

int main(int argc, char** argv) {
    // load a Point Cloud originPointCloud.pcd
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud(new pcl::PointCloud<pcl::PointXYZ>);
    pcl::PointCloud<pcl::PointXYZ>::Ptr cloud_plane(new pcl::PointCloud<pcl::PointXYZ>);
    pcl::PointCloud<pcl::PointXYZ>::Ptr edgePoints(new pcl::PointCloud<pcl::PointXYZ>);
    pcl::PointCloud<pcl::PointXYZ>::Ptr circlepoints(new pcl::PointCloud<pcl::PointXYZ>);
    if (pcl::io::loadPCDFile<pcl::PointXYZ>("../test700.pcd", *cloud) == -1) {
        PCL_ERROR("Couldn't read test700.pcd file.\n");
        return (-1);
    }
    
    // 打印原始点云信息
    std::cout << "点云加载完成，共包含 " << cloud->points.size() << " 个点" << std::endl;
    
    // 去除无效点
    cloud = removeInvalidPoints(cloud);
    
    // 执行平面分割
    float distanceThreshold = 0.05; // 调整距离阈值，较小的值可以提高精度
    cloud_plane = planeSegmentation(cloud, distanceThreshold);
    
    // 打印分割后的平面点云信息
    std::cout << "平面分割完成，共包含 " << cloud_plane->points.size() << " 个点" << std::endl;

    // 调用通用保存函数保存平面点云
    savePointCloud<pcl::PointXYZ>(cloud_plane, "../ptcfile/planePointCloud.pcd", "平面点云");

    // 调用edge_detection函数进行边缘检测
    float search_radius = 2.0; // 设置搜索半径
    edgePoints = edge_detection(cloud_plane, search_radius);
    
    // 调用通用保存函数保存边缘点云
    savePointCloud<pcl::PointXYZ>(edgePoints, "../ptcfile/edgePoints.pcd", "边缘点云");
    
    // 执行欧式聚类
    float cluster_tolerance = 2.0; // 聚类容差
    int min_cluster_size = 50; // 最小聚类大小
    int max_cluster_size = 1000; // 最大聚类大小
    
    // 调用通用欧式聚类函数
    euclidean_cluster_template<pcl::PointXYZ>(edgePoints, cluster_tolerance, min_cluster_size, max_cluster_size);

    if (pcl::io::loadPCDFile<pcl::PointXYZ>("cluster1.pcd", *circlepoints) == -1) {
        PCL_ERROR("Couldn't read cluster1.pcd file.\n");
        return (-1);
    }
    pcl::PointXYZ circle_center = detect_circle(circlepoints);
    std::cout << "拟合圆的圆心坐标: (" << circle_center.x << "," << circle_center.y << "," << circle_center.z << ")" << std::endl;
    return (0);
}
// Compile with: g++ main.cpp -o viewer -lpcl_io -lpcl_common -lboost_system -lboost_filesystem
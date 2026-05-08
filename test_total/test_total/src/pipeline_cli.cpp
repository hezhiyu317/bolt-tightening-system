#include "point_cloud_pipeline.h"
#include <iostream>
#include <string>
#include <cstdlib>

static void print_json(const PipelineResult& r) {
    std::cout << "{\n";
    std::cout << "  \"success\": "         << (r.success ? "true" : "false") << ",\n";
    std::cout << "  \"center_x\": "        << r.center_x << ",\n";
    std::cout << "  \"center_y\": "        << r.center_y << ",\n";
    std::cout << "  \"center_z\": "        << r.center_z << ",\n";
    std::cout << "  \"radius\": "          << r.radius   << ",\n";
    std::cout << "  \"plane_a\": "         << r.plane_a  << ",\n";
    std::cout << "  \"plane_b\": "         << r.plane_b  << ",\n";
    std::cout << "  \"plane_c\": "         << r.plane_c  << ",\n";
    std::cout << "  \"plane_d\": "         << r.plane_d  << ",\n";
    std::cout << "  \"original_points\": " << r.original_points << ",\n";
    std::cout << "  \"valid_points\": "    << r.valid_points    << ",\n";
    std::cout << "  \"plane_points\": "    << r.plane_points    << ",\n";
    std::cout << "  \"edge_points\": "     << r.edge_points     << ",\n";
    std::cout << "  \"cluster_points\": "  << r.cluster_points  << ",\n";
    std::string msg = r.message;
    for (auto& c : msg) { if (c == '\"') c = '\''; if (c == '\n') c = ' '; }
    std::cout << "  \"message\": \""       << msg << "\"\n";
    std::cout << "}\n";
}

int main(int argc, char* argv[]) {
    if (argc < 2) {
        std::cerr << "用法: pipeline_cli <pcd_path>"
                     " [plane_thresh] [edge_k_neighbors] [edge_threads]"
                     " [cluster_tol] [min_cluster] [max_cluster]"
                  << std::endl;
        return 1;
    }

    PipelineParams params;
    if (argc >= 3) params.plane_distance_threshold = std::atof(argv[2]);
    if (argc >= 4) params.edge_search_radius         = std::atof(argv[3]);
    if (argc >= 5) params.edge_num_threads         = std::atoi(argv[4]);
    // if (argc >= 6) params.edge_curvature_thresh      = std::atof(argv[5]);
    if (argc >= 6) params.cluster_tolerance         = std::atof(argv[5]);
    if (argc >= 7) params.min_cluster_size          = std::atoi(argv[6]);
    if (argc >= 8) params.max_cluster_size          = std::atoi(argv[7]);

    PipelineResult result = runPipeline(argv[1], params);
    print_json(result);

    return result.success ? 0 : 1;
}
cmake_minimum_required(VERSION 3.10)
project(MyPCLProject)

set(CMAKE_CXX_STANDARD 14)
set(CMAKE_CXX_STANDARD_REQUIRED ON)
set(CMAKE_CXX_EXTENSIONS OFF)

# ====================== PCL ======================
set(PCL_ROOT "C:/Program Files/PCL 1.12.1" CACHE PATH "PCL 路径" FORCE)
set(PCL_NO_PRECOMPILE ON)
find_package(PCL 1.12.1 REQUIRED COMPONENTS common visualization filters segmentation io)
set(PCL_LIBRARIES_FINAL ${PCL_LIBRARIES})

message(STATUS "PCL 版本: ${PCL_VERSION}")
message(STATUS "PCL 包含路径: ${PCL_INCLUDE_DIRS}")
message(STATUS "PCL 库: ${PCL_LIBRARIES_FINAL}")

# ====================== 原有可执行目标 ======================
set(PROCESSOR_SRC src/point_cloud_processor.cpp src/point_cloud_pipeline.cpp)

add_executable(MyPCLProject src/main.cpp ${PROCESSOR_SRC})
# add_executable(cylinder     src/cylinder.cpp ${PROCESSOR_SRC})
# add_executable(seg          src/seg.cpp ${PROCESSOR_SRC})
# add_executable(point_1030   src/point_1030.cpp ${PROCESSOR_SRC})

# 子进程 JSON 桥接可执行文件
add_executable(pipeline_cli src/pipeline_cli.cpp ${PROCESSOR_SRC})
find_package(OpenMP REQUIRED)

foreach(tgt  MyPCLProject pipeline_cli)   #MyPCLProject cylinder seg point_1030
    target_include_directories(${tgt} PRIVATE ${PCL_INCLUDE_DIRS})
    target_link_libraries(${tgt} PRIVATE ${PCL_LIBRARIES_FINAL})
    if(OpenMP_CXX_FOUND)
        target_link_libraries(${tgt} PRIVATE OpenMP::OpenMP_CXX)
    endif()
    set_target_properties(${tgt} PROPERTIES CXX_STANDARD 14 CXX_STANDARD_REQUIRED ON)
endforeach()

# ====================== pybind11 Python 模块（可选） ======================
# 安装方式:  pip install pybind11
# 如果 pybind11 未安装，此部分会被自动跳过，不影响其他目标
set(pybind11_DIR "C:/Users/Administrator/AppData/Local/Programs/Python/Python38/lib/site-packages/pybind11/share/cmake/pybind11" CACHE PATH "pybind11 cmake dir")
find_package(pybind11 QUIET)
if(pybind11_FOUND)
    message(STATUS ">>> pybind11 已找到，构建 Python 扩展模块 pcl_processor")

    pybind11_add_module(pcl_processor
        src/pybind_wrapper.cpp
        src/point_cloud_processor.cpp
        src/point_cloud_pipeline.cpp
    )
    target_include_directories(pcl_processor PRIVATE ${PCL_INCLUDE_DIRS})
    target_link_libraries(pcl_processor PRIVATE ${PCL_LIBRARIES_FINAL})
    if(OpenMP_CXX_FOUND)
        target_link_libraries(pcl_processor PRIVATE OpenMP::OpenMP_CXX)
    endif()
    set_target_properties(pcl_processor PROPERTIES CXX_STANDARD 14 CXX_STANDARD_REQUIRED ON)

    # 构建完成后自动复制到项目根目录（方便 Python 直接 import）
    add_custom_command(TARGET pcl_processor POST_BUILD
        COMMAND ${CMAKE_COMMAND} -E copy $<TARGET_FILE:pcl_processor> ${CMAKE_SOURCE_DIR}/
        COMMENT "已将 pcl_processor 模块复制到项目根目录"
    )
else()
    message(STATUS ">>> pybind11 未找到，跳过 Python 扩展模块构建")
    message(STATUS ">>> 可通过 pipeline_cli.exe 子进程方式桥接")
endif()

message(STATUS "编译器: ${CMAKE_CXX_COMPILER}")
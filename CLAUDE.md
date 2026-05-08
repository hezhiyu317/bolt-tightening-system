# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

螺栓拧紧上位机系统 — a bolt tightening upper computer system using Python + C++. Two gantry three-coordinate systems (small for bolt pickup/placement, large for bolt tightening with vision guidance) controlled via Modbus TCP to PLC, with 3D structured light camera + PCL for point cloud processing and bolt hole detection.

## Tech Stack

- **Python 3.8** + PyQt5 (GUI), pymodbus (PLC comm), pyvista/pyvistaqt (3D viz), open3d (point cloud I/O)
- **C++** PCL 1.12.1 (point cloud algorithms), Eigen, OpenMP, CMake build (Visual Studio)
- **pybind11** for Python↔C++ bridge; fallback: subprocess via `pipeline_cli.exe`
- **AlsonClassicDevice SDK** for 3D structured light grating camera

## Project Structure (relative to `test_total/test_total/`)

```
main.py              # App entry, MainWindow with tabbed UI
config.py            # Motor base addresses, Modbus register offsets, gantry axis mappings
plc_worker.py        # Modbus TCP read/write polling loop in background thread
camera_worker.py     # Alson camera: 2D streaming + 3D point cloud capture
ui_widgets.py        # MotorWidget QGroupBox (display, params, jog/rel/abs control)
pcl_bridge.py        # Async bridge to C++ PCL processing (pybind11 preferred, CLI fallback)
src/
  point_cloud_processor.h/.cpp  # PCL algorithms: NaN removal, RANSAC plane, edge detection, circle fitting, clustering
  point_cloud_pipeline.h/.cpp   # Full pipeline orchestrator + PipelineParams/PipelineResult structs
  pipeline_cli.cpp              # CLI executable for subprocess JSON bridge
  pybind_wrapper.cpp            # pybind11 module exposing pipeline to Python
  main.cpp                      # Original C++ test entry (not needed for runtime)
CMakeLists.txt                  # Builds MyPCLProject.exe, pipeline_cli.exe, pcl_processor.pyd
```

## Architecture & Key Patterns

**Communication flow:** PyQt5 main thread → PlcWorker (background polling thread, 100ms cycle) → Modbus TCP → PLC. Writes are queued via `add_write_task()` and drained in the poll loop.

**Point cloud pipeline (C++):** load PCD → remove NaN → RANSAC plane segmentation → edge detection (NormalEstimationOMP + BoundaryEstimation) → Euclidean clustering (clusters saved to disk as `clusterN.pcd`) → reload target cluster → PCA project to 2D → two-pass RANSAC circle2D fit → unproject center back to 3D.

**Bridge modes:** `pcl_bridge.py` auto-detects pybind11 `.pyd` module first; if not found, falls back to `pipeline_cli.exe` subprocess with JSON stdout parsing.

**PLC register layout:** 12 motors (M1-M12), each with a 32-register block. Motor base addresses start at 100 for M1, increment by 32. OFFSETS dict maps logical names to register offsets. Motor groups: Small Gantry (Z,X,YL,YR), Big Gantry (ZZ,XX,YLL,YRR), Rotary (SPF,SPT,SPM,SPC).

**Application has two modes (per Readme):**
- Developer mode: configure system parameters (speed, torque range, etc.)
- User mode: control system motion (tighten, loosen, query torque)

Login with password to select mode. Logging is required for error tracking.

**Hardware workflow:** Small gantry picks bolts from tray → places on rotating material table → Large gantry picks from table → moves to target position → camera captures bolt hole → tightening gun operation.

## Build Commands

C++ components use CMake with Visual Studio (Windows only, PCL 1.12.1 at `C:/Program Files/PCL 1.12.1`):

```bash
cd test_total/test_total/build
cmake .. -G "Visual Studio 16 2019" -A x64
cmake --build . --config Release
```

This produces:
- `build/Release/MyPCLProject.exe` — original test executable
- `build/Release/pipeline_cli.exe` — CLI JSON bridge (used if pybind11 not available)
- `build/Release/pcl_processor.cp38-win_amd64.pyd` (auto-copied to project root) — Python module

## Run GUI

```bash
cd test_total/test_total
python main.py
```

No test suite exists yet.

## Key Parameters

- PLC default IP: `192.168.1.88:502`
- Camera SDK: AlsonClassicDevice (requires `LogConfig-Client.yaml` in parent directory)
- PCL algorithm defaults: plane threshold 0.05, edge radius 2.0, 4 threads, cluster tolerance 2.0, min/max cluster 50/1000
- Temp data: `temp_cam_data/` (2D BMP stream), `temp_3d_cloud.pcd` (3D capture), `clusterN.pcd` (clustering output)
- X1 sensor: Modbus discrete input address 20 (used for end-effector calibration)

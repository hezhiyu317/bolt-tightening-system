#!/usr/bin/env python3
"""
Run this script from the project root to create the directory tree and empty files described in rebuild.md.
Usage:
    python create_project_structure.py
"""
import os

files_to_create = [
    # src/ui
    ("src/__init__.py", ""),
    ("src/ui/__init__.py", ""),
    ("src/ui/main_window.py", ""),
    ("src/ui/login_dialog.py", ""),
    ("src/ui/styles.py", ""),
    
    # src/ui/pages
    ("src/ui/pages/__init__.py", ""),
    ("src/ui/pages/dashboard_page.py", ""),
    ("src/ui/pages/motor_control_page.py", ""),
    ("src/ui/pages/vision_page.py", ""),
    ("src/ui/pages/integrated_page.py", ""),
    ("src/ui/pages/calibration_page.py", ""),
    ("src/ui/pages/gun_valve_page.py", ""),
    ("src/ui/pages/feeding_page.py", ""),
    ("src/ui/pages/settings_page.py", ""),
    ("src/ui/pages/log_viewer_page.py", ""),
    
    # src/ui/widgets
    ("src/ui/widgets/__init__.py", ""),
    ("src/ui/widgets/motor_widget.py", ""),
    ("src/ui/widgets/status_indicator.py", ""),
    ("src/ui/widgets/data_display.py", ""),
    ("src/ui/widgets/log_panel.py", ""),
    
    # src/services
    ("src/services/__init__.py", ""),
    ("src/services/plc_service.py", ""),
    ("src/services/camera_service.py", ""),
    ("src/services/pcl_service.py", ""),
    
    # src/models
    ("src/models/__init__.py", ""),
    ("src/models/motor_config.py", ""),
    ("src/models/app_state.py", ""),
    
    # src/utils
    ("src/utils/__init__.py", ""),
    ("src/utils/config_manager.py", ""),
    ("src/utils/app_logger.py", ""),
    
    # resources
    ("resources/styles/industrial.qss", ""),
    ("resources/icons/.gitkeep", ""),
    
    # config
    ("config/system.yaml", ""),
    ("config/motors.yaml", ""),
    ("config/users.yaml", ""),
    
    # root
    ("requirements.txt", ""),
    ("main.py", ""),
    ("README.md", ""),
]

base_path = os.path.abspath(os.path.dirname(__file__))

for file_path, content in files_to_create:
    full_path = os.path.join(base_path, file_path)
    dir_path = os.path.dirname(full_path)
    os.makedirs(dir_path, exist_ok=True)
    with open(full_path, 'w', encoding='utf-8') as f:
        f.write(content)
    print(f"Created: {file_path}")

# Create logs and cpp directories
os.makedirs(os.path.join(base_path, "logs"), exist_ok=True)
os.makedirs(os.path.join(base_path, "cpp"), exist_ok=True)
print("Created: logs/")
print("Created: cpp/")

print('\nDone. Run `python create_project_structure.py` from the project directory to recreate this structure locally if needed.')

"""Structural guard: the active ROS-draining loop must not sleep per callback."""
import ast
from pathlib import Path


def test_active_loop_does_not_block_sensor_callbacks_with_sleep():
    path = Path(__file__).resolve().parents[1] / 'scripts/duct_guarded_jog.py'
    tree = ast.parse(path.read_text())
    active_loops = [n for n in ast.walk(tree)
                    if isinstance(n, ast.While) and isinstance(n.test, ast.Constant)
                    and n.test.value is True]
    assert len(active_loops) == 1
    calls = [n.func.attr for n in ast.walk(active_loops[0])
             if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)]
    assert 'spin_once' in calls
    assert 'sleep' not in calls


def test_root_timer_has_scoped_ros_log_path_and_sufficient_budget():
    root = Path(__file__).resolve().parents[1]
    wrapper = (root / 'scripts/start_duct_motion_experiment.sh').read_text()
    mode = (root / 'scripts/duct_motion_mode.py').read_text()
    assert 'export ROS_LOG_DIR=/home/duct/pose3d_motion_experiment/ros_logs-${EUID}' in wrapper
    assert '--on-active=120s' in mode
    assert "'auto_restore_sec': 120" in mode

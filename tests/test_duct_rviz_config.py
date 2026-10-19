"""Guard Humble RViz topic properties and the two distinct marker types."""
from pathlib import Path

import pytest
import yaml


@pytest.mark.parametrize('name', ['duct_pose_3d.rviz', 'duct_pose_3d_robot.rviz'])
def test_skeleton_uses_marker_array_topic_property(name):
    root = Path(__file__).resolve().parents[1]
    path = root / 'ros2_ws/src/yolopose_ros/rviz' / name
    config = yaml.safe_load(path.read_text(encoding='utf-8'))
    displays = config['Visualization Manager']['Displays']
    skeletons = [display for display in displays
                 if display['Class'] == 'rviz_default_plugins/MarkerArray']
    assert len(skeletons) == 1
    assert skeletons[0]['Enabled']
    assert skeletons[0]['Topic']['Value'] == '/perception/pose_3d_markers'
    assert 'Marker Topic' not in skeletons[0]
    for display in displays:
        if display['Class'] == 'rviz_default_plugins/PointCloud2' and name.endswith('_robot.rviz'):
            assert display['Topic']['Reliability Policy'] == 'Reliable'
            assert display['Topic']['Durability Policy'] == 'Transient Local'
        if display['Class'] == 'rviz_default_plugins/Marker':
            assert display['Topic']['Value'] == '/perception/human_approach_preview'
            assert 'Marker Topic' not in display

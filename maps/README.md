# Kaiti House Static Map

This directory stores the known-map asset used by the house Nav2 + MILP planning demo.

Current map:

- `kaiti_house.yaml`
- `kaiti_house.pgm`

Use this map for the known-environment graduation-design validation. RTAB-Map is still useful for
mapping and spatial-state experiments, but the MILP-to-Nav2 execution loop should use this static
map to avoid online `/map` resizing.

Recommended launch:

```bash
ros2 launch yolopose_ros kaiti_house_static_nav2_planning.launch.py
```

Before enabling execution, set the robot pose in RViz with `2D Pose Estimate` so AMCL can publish
`map -> odom`.

Waypoint bounds check:

```bash
python3 scripts/check_planner_waypoints.py \
  --origin-x -3.93 \
  --origin-y -4.38 \
  --width 229 \
  --height 241 \
  --resolution 0.05 \
  --margin 0.10
```

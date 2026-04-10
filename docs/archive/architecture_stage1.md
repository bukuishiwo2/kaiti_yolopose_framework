# Architecture (YOLO-Pose First Stage)

> Archived document. This file records an earlier stage-1 architecture sketch and is no longer the current source of truth. Current project structure and system direction should be read from `README.md`, `docs/project_conventions.md`, and `docs/system_architecture.md`.

## Layering

1. Core inference (`src/yolopose`): model load, predict/track, event stabilization.
   Includes `fall_detector.py` for v1 fall-event extraction from pose keypoints.
2. Script entrypoints (`scripts`): train, infer, export.
3. Config/data (`configs`, `datasets`, `data/streams`): all runtime choices are configurable.
4. ROS2 bridge (`ros2_ws/src/yolopose_ros`): wraps the same inference core for future system integration.

## Why this shape

- Keeps model code independent from ROS2 runtime.
- Lets you test with local video/RTSP first, then plug into ROS2 without rewriting algorithm code.
- Supports multi-stream by using `.streams` source and `stream=True` generator mode.

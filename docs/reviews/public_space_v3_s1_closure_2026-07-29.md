# Public-space V3 S1 baseline closure

Date: 2026-07-29

Base checkpoint: `8d0e6a0033c9121969598e36d722339fe3340d16`

Branch: `feat/public-space-v3-s1`

Scope: S1 only; S2-S8 were not started.

## Outcome

S1 remains **FAIL**. The S1 implementation and regression gates pass. The
map-to-world mismatch was diagnosed and the real named-path and image-header
gates now pass, but real continuous navigation stops in round 1 at `D→S`.
No result was skipped and no mock result was reported as a real run.

## Implemented S1 interfaces

- Image header and explicit clock domains:
  [runner.py](../../src/yolopose/pipeline/runner.py) and
  [pose_stream_node.py](../../ros2_ws/src/yolopose_ros/yolopose_ros/pose_stream_node.py).
- Machine-readable S1 parameters and S1-only runtime asset selection:
  [public_space_v3_s1.yaml](../../configs/public_space_v3_s1.yaml).
- Continuous real-Nav2 route logger:
  [run_s1_continuous_nav.py](../../scripts/run_s1_continuous_nav.py) and
  [s1_navigation_baseline.py](../../src/kaiti_planning/s1_navigation_baseline.py).
- Structured path-cost adapter:
  [run_s1_path_cost_queries.py](../../scripts/run_s1_path_cost_queries.py) and
  [nav2_path_cost.py](../../src/kaiti_planning/nav2_path_cost.py).
- Static map, live costmap, TF, AMCL, full path and planner diagnostics:
  [audit_s1_nav2_diagnostics.py](../../scripts/audit_s1_nav2_diagnostics.py).
- Real ROS Image/header audit:
  [audit_s1_ros_image_headers.py](../../scripts/audit_s1_ros_image_headers.py).
- Per-round ROS runtime-log capture:
  [capture_s1_nav2_runtime_logs.py](../../scripts/capture_s1_nav2_runtime_logs.py).
- Frozen V3 protocol smoke:
  [public_space_v3_s1_smoke.py](../../src/kaiti_planning/public_space_v3_s1_smoke.py)
  and
  [public_space_v3_s1_smoke_node.py](../../ros2_ws/src/yolopose_ros/yolopose_ros/public_space_v3_s1_smoke_node.py).

The smoke node creates all eleven logical topic handles, but production
publishing remains disabled. It does not emit fabricated 3D events, zones,
service points, plans, or repair results.

## Root-cause evidence

The first real run loaded the exact protected map
`maps/kaiti_house.yaml`; this was verified from the live map-server parameter,
map data hash and metadata, not inferred from a filename. That map is not
aligned with the current Gazebo world and waypoint semantics:

| Waypoint | Old-map pixel | Static occupancy | Static clearance (m) | Global cost | Global component |
|---|---:|---:|---:|---:|---:|
| A | (98, 107) | 0 | 0.918 | 0 | 9 |
| B | (145, 138) | 0 | 0.364 | 47 | 9 |
| C | (187, 180) | 0 | 0.050 | 99 | 0 |
| D | (188, 107) | 0 | 0.100 | 99 | 0 |
| S | (108, 181) | 0 | 0.604 | 0 | 12 |

`C` and `D` were inside lethal/inflated global-costmap cells, and `S` was
outside the A/B traversable component. Searching the A component found no
0.45 m-clear candidate inside the frozen B, D, or S semantic regions.
Moving waypoints would therefore destroy their semantics rather than repair
the baseline. The complete pre-repair evidence is in
[pre-repair diagnostics](../../reports/s1/diagnostics/nav2_diagnostics_20260729_pre_repair_real_v2.json).

The repository already contains a tracked, reproducible static map generated
from the current SDF world:
`maps/candidates/2026-07-17/kaiti_house_sdf_static.yaml`. Its bytes match the
preserved untracked convenience copy, and an earlier real Nav2 audit had
already established A/B/C/D/S reachability. S1 therefore selects the tracked
world-aligned map in `s1_runtime_inputs`; protected V2 inputs remain unchanged.
No waypoint, robot radius, inflation radius, occupied threshold, world, or V2
map was modified.

After the S1-only map selection:

| Waypoint | Map pixel | Static occupancy | Static clearance (m) | Global cost | Outside inflation | Component |
|---|---:|---:|---:|---:|---|---:|
| A | (29, 29) | 0 | 0.850 | 0 | yes | 2 |
| B | (76, 60) | 0 | 0.750 | 0 | yes | 2 |
| C | (118, 102) | 0 | 1.000 | 0 | yes | 2 |
| D | (119, 29) | 0 | 0.850 | 0 | yes | 2 |
| S | (39, 103) | 0 | 0.650 | 0 | yes | 2 |

All five points meet the 0.175 m robot-radius check and the frozen 0.45 m
static-clearance check. The map server parameter, data hash, metadata,
costmap, AMCL covariance, TF snapshots, complete requests/responses, paths
and planner messages are in
[world-aligned diagnostics](../../reports/s1/diagnostics/nav2_diagnostics_20260729_s1_world_aligned.json).

## Clock-domain correction

Runtime records now use explicit names:

- `source_ros_stamp_ns` and `event_ros_stamp_ns` for ROS/simulation order,
  TF, stale checks and task timing;
- `wall_time_ns` for Unix traceability;
- `monotonic_elapsed_sec` for program runtime and p95;
- `simulation_elapsed_sec` for simulated task duration.

Navigation transitions store all three clocks independently. The 120 s goal
timeout uses ROS time. A separate configured 600 s monotonic watchdog detects
a stalled simulator. No ROS timestamp is compared with Unix wall time.
`/rosout` timestamps from this Humble stack are labelled `wall_time_ns`.

## Real gate results

### Named path cost

[The real path-cost report](../../reports/s1/path_cost/path_cost_20260729_s1_real_nav2.json)
is `PASSED`.

| Pair | Exists | Length (m) | Estimated time (s) | Monotonic runtime (s) |
|---|---|---:|---:|---:|
| A→B | yes | 2.926 | 11.705 | 0.0097 |
| B→C | yes | 3.552 | 14.209 | 0.0104 |
| C→D | yes | 3.671 | 14.683 | 0.0075 |
| D→S | yes | 10.584 | 42.337 | 0.0173 |

Runtime p95 is 0.0163 s, below the 1.0 s gate.

### Real image headers

[The 100-frame report](../../reports/s1/image_headers/image_header_100_frame_real.json)
is `PASSED`: 100/100 input Images, events and debug Images preserve the same
source stamp and `oakd_rgb_camera_optical_frame`. Monotonic inference latency
is 0.037-0.090 s (sample p95 0.052 s); simulation latency is 0.012-0.052 s.

### Continuous navigation

[Round 1](../../reports/s1/continuous_navigation/20260729_s1_world_aligned_three_rounds/round_01.json)
and its
[run summary](../../reports/s1/continuous_navigation/20260729_s1_world_aligned_three_rounds/run_summary.json)
are `FAILED`.

| Goal | Result | Simulation elapsed (s) | Wall/monotonic elapsed (s) | Recoveries | Final/actual pose |
|---|---|---:|---:|---:|---|
| A | success | 0.404 | 1.687 | 0 | (0.838, 0.805) |
| B | success | 22.752 | 90.894 | 5 | (3.170, 2.394) |
| C | success | 21.428 | 84.965 | 0 | (5.266, 4.586) |
| D | success | 21.092 | 84.525 | 0 | (5.419, 1.164) |
| S | timeout | 120.016 | 471.064 | 11 | (5.146, 3.469) |

The S leg remained near the valid global path but stopped making progress
with about 8.1 m remaining. The captured
[runtime log window](../../reports/s1/continuous_navigation/20260729_s1_world_aligned_three_rounds/nav2_runtime_logs_round_01.json)
contains 20 planner, 659 controller, 92 BT, 15 behavior, 1 AMCL and 12
motion-control lines. It records repeated controller `Failed to make
progress`, recovery spin/wait/backup, a failed backup, 20 Hz control-loop
misses, and Create3 safety-layer velocity/backup-limit warnings. This is now
an execution/control and recovery issue, not a named-path reachability issue.

The timeout report truthfully has no terminal Nav2 result payload because the
S1 runner canceled the action at the configured task deadline. The runner has
been corrected to retain AMCL covariance and minimum scan distance on future
timeout records; those two timeout-only fields are `null` in this already
completed run and are not retroactively fabricated.

## Verification

| Group | Result |
|---|---|
| S0 dedicated tests | `19 passed` |
| Existing root Python tests | `33 passed` |
| ROS execution-contract tests | `4 passed` |
| S1 baseline/new tests | `25 passed` (`22` original + `3` clock/diagnostic additions) |
| ROS package build | `1 package finished` |
| V2 planning smoke | `passed: true` |
| Dynamic repair matrix | all five scenarios returned expected structured outcomes |
| V2/house protected hashes | `13/13 unchanged` |
| `git diff --check` | passed |

## Gate decision

| Gate | Status |
|---|---|
| S1 implementation and unit/regression gates | PASS |
| Actual map identity and world-aligned S1 selection | PASS |
| Four structured named-path queries | PASS |
| Path length positive and runtime p95 ≤ 1.0 s | PASS |
| 100-frame real image header propagation | PASS |
| A→B→C→D→S, three complete rounds | FAIL |
| V2/house asset protection | PASS |
| Overall S1 | **FAIL** |

Do not enter S2. The next S1-only step is a controller execution audit around
the `(5.15, 3.47)` stall: compare `cmd_vel_nav`, smoothed `/cmd_vel`,
diff-drive input and odometry; snapshot local costmap/DWB trajectories; and
separate Create3 safety arbitration from direct diff-drive control. Parameters
must not be relaxed until that evidence identifies the failing layer.

# Kaiti House MILP-to-Nav2 Route Analysis - 2026-07-08

## Scope

This note explains the route observed in RViz during the single-robot online execution test and separates three layers that can look similar in the UI:

- MILP task schedule: discrete robot-task assignment and task start/finish times.
- Executor waypoint sequence: the Nav2 goals expanded from a selected robot's MILP tasks.
- RViz path display: the continuous path or accumulated RTAB-Map graph/history shown in the map frame.

## Frozen Task Scenario

The minimal experiment keeps the graduation-design task semantics unchanged:

- `T1`: R1-capable patrol at `A`.
- `T2`: patrol at `C`, using `corridor_H`.
- `T3`: verify fall event at `B`, using `corridor_H` and `event_zone_B`.
- `T4`: deliver supply to `B`, with pickup at `S`, using `corridor_H`, `supply_point_S`, and `event_zone_B`.
- `T5`: charge at `D`, using `charger_D`.
- Precedence: `T3` must finish before `T4` starts.

The current ROS2 executor is intentionally single-robot and is configured to control only `R2`.

## Current MILP Result

The static MILP result is:

| Robot | Task | Location | Start | Finish | Meaning |
| --- | --- | --- | ---: | ---: | --- |
| R1 | T1 | A | 0 | 20 | Patrol region A |
| R2 | T2 | C | 0 | 20 | Patrol region C |
| R3 | T5 | D | 0 | 40 | Charge at D |
| R1 | T3 | B | 38 | 53 | Verify the fall event at B |
| R2 | T4 | B | 53 | 78 | Deliver supply to B |

For `R2`, the MILP-level task order is therefore:

```text
R2 start(C) -> T2@C -> T4@B
```

Because `T4` has `pickup_location: S`, the executor expands the MILP task into two navigation goals:

```text
R2 current pose -> C / T2 task_location -> S / T4 pickup_location -> B / T4 task_location
```

This is why the execution-level route includes `S` even though the MILP assignment row for `T4` only lists `location=B`.

## Constraint Interpretation

The MILP plan is constrained by:

- Unique assignment: every required task is assigned exactly once.
- Capability matching: only robots with required task capabilities may take the task.
- Release time and deadline: tasks cannot start before release and must finish before deadline.
- Precedence: `T4` cannot start before `T3` finishes.
- Same-robot sequencing: one robot cannot execute two tasks at the same time; travel time between task locations is included.
- Shared resource mutex: tasks sharing `corridor_H`, `event_zone_B`, `charger_D`, or `supply_point_S` cannot overlap beyond resource capacity.
- Dynamic resource windows: blocked or temporarily occupied resources delay related tasks.
- Battery safety: robot energy after assigned work must remain above the configured safe threshold.
- Objective: weighted minimization of travel, delay, interrupt/resource/energy/change costs.

For the current static result, `T4` starts at `53` mainly because `T3` finishes at `53` and both tasks use `event_zone_B`; this satisfies the fall-response precedence and event-zone resource mutex.

## Why The Observed RViz Route Can Look Different

The user-observed route may appear as:

```text
start -> C -> B/middle -> C/right-top -> B/middle -> S/left-top -> B/middle
```

This is not necessarily the MILP route. The likely causes are:

- The blue RViz path can include RTAB-Map `MapGraph` or accumulated historical trajectory, not only the current Nav2 plan.
- The simulated robot's physical spawn pose may not equal the planner's discrete `R2 start=C` assumption.
- If the robot starts near an `R1 start` visual marker but the executor controls `R2`, the first Nav2 goal is still `C`.
- Nav2 may replan continuously while moving through narrow passages; the displayed curve can include local adjustments and repeated path updates.
- If `/planning/plan` is periodically republished, the executor must not replace an active queue during motion. The current executor mitigates this with `allow_plan_refresh_during_execution: false`.

## Expected Behavior For This Stage

For the current single-robot online test, the expected task-level behavior is:

```text
Controlled robot: R2
Expected executed task ids: T2, T4
Expected expanded Nav2 goals: C -> S -> B
Expected final task location: B
```

This is a Phase-5 ROS2/Nav2 execution adapter test. It is not yet a full three-robot closed loop, and it does not mean that R1 and R3 physically execute their assigned tasks in Gazebo.

## Current Interpretation

The observed final stop near the middle/B area is consistent with completing `T4`. A route that includes `S` before returning to `B` is also consistent, because `T4` is a delivery task with a pickup step.

The remaining mismatch to resolve is not the MILP task semantics. The main remaining issues are:

- Align Gazebo spawn pose, planner robot id, and the discrete start region.
- Separate RViz displays for current Nav2 `/plan` and RTAB-Map history/graph.
- Ensure `/planning/spatial_state` is based on the live `/map` instead of `waiting_for_costmap`.
- Use a saved static map for repeatable known-environment experiments.

## Recommended Next Check

Use these commands during the next run:

```bash
ros2 topic echo /planning/executor_status --field data
ros2 topic echo /planning/plan --field data
ros2 run tf2_ros tf2_echo map base_link
ros2 topic echo /plan
ros2 topic echo /planning/spatial_state --field data
```

The key success condition is not whether the blue line visually matches the MILP rows exactly, but whether:

- `completed_task_ids` becomes `["T2", "T4"]`;
- the final `map -> base_link` pose is close to waypoint `B`;
- Nav2 goals are sent in the expanded order `C -> S -> B`;
- planner updates do not reset the executor queue during active navigation.

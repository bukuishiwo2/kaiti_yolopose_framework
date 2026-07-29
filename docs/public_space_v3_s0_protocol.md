# Public Space V3.0.1 S0 Configuration and Test Protocol

## 1. Scope

This document records the S0 machine-readable contract derived from
[the frozen V3.0.1 research plan](research_plan_v3_0_1.md). S0 creates only
configuration, protocol validation, table-driven vectors, hash manifests,
safety-checker interfaces, and tests.

S0 does not implement or start Orbbec integration, dynamic Nav2 keepout,
multi-robot Nav2, online LocalRepair, the hospital simulation world, or any
S1–S8 runtime work.

## 2. Deliverables

| Deliverable | Location | S0 role |
|---|---|---|
| Frozen parameter/task configuration | [public_space_v3.yaml](../configs/public_space_v3.yaml) | 96 parameters, 4 task templates, enums, reason codes, triggers, fallback registry |
| Semantic-region fixture contract | [public_space_regions_v3.yaml](../configs/public_space_regions_v3.yaml) | S0-only geometry/topology fixture; explicitly not the S7 world |
| Dataclass-based logical message validator | [public_space_v3_protocol.py](../src/kaiti_planning/public_space_v3_protocol.py) | complete-object, enum, reason, revision, stale-message and fallback validation |
| Safety checker interface | [public_space_v3_safety.py](../src/kaiti_planning/public_space_v3_safety.py) | pure checker for the 13 frozen simulation safety rules |
| Table-driven test vectors | [public_space_v3_s0_test_vectors.yaml](../data/eval/public_space_v3_s0_test_vectors.yaml) | 12 positive + 12 negative state/action cases, 13 triggers, 9 fallback pairs and revision rejection |
| Benchmark manifest template | [public_space_v3_benchmark_manifest.template.yaml](../data/eval/public_space_v3_benchmark_manifest.template.yaml) | unexecuted 20-seed engineering-gate template |
| Parameter and artifact hashes | [public_space_v3_s0_hashes.json](../configs/generated/public_space_v3_s0_hashes.json) | canonical zone/service/edge/repair hashes and protected V2/house snapshot |
| S0 tests | [test_public_space_v3_s0.py](../tests/test_public_space_v3_s0.py) | mapping, schema, enums, reason codes, revisions, vectors, hashes and safety rules |

## 3. Mapping Rules

- Only leaves under `parameters` in `public_space_v3.yaml` count toward the
  frozen 96 parameters.
- Section counts are `18 + 15 + 20 + 10 + 11 + 11 + 11 = 96`.
- The four `*:E` entries are task templates and are not counted as parameters.
- Objective weights and other prose/formula constants are stored under
  `contract_constants`, each with a V3.0.1 source location.
- Region coordinates are marked `S0_CONTRACT_FIXTURE_NOT_S7_WORLD`; they are
  contract-test data, not a validated hospital map.
- Hashes use SHA-256. Parameter groups are serialized as compact,
  key-sorted UTF-8 JSON before hashing.

## 4. Validation Contract

The protocol validator rejects:

- incomplete or partial objects;
- unknown fields and message types;
- invalid enum and unregistered reason-code values;
- NaN and infinity;
- negative revision values;
- message revisions older than the consumer's current revision;
- confirmed events without required identity/observer information;
- valid 3D poses with missing or all-zero covariance;
- publishable task plans that did not pass the hard-constraint validator;
- `STOPPED` reports that do not satisfy cancel, active-goal, velocity and
  dispatch-lock conditions.

The repair gate is a policy contract only. It evaluates the nine top-level
Full-Replan conditions but does not solve LocalRepair, Full-Replan, MILP, or
navigation.

## 5. Verification Commands

Run the S0 tests:

```bash
cd /home/yhc/kaiti_yolopose_framework
PYTHONPATH=src python3 -m pytest -q tests/test_public_space_v3_s0.py
```

Run the existing Python regression suite:

```bash
cd /home/yhc/kaiti_yolopose_framework
PYTHONPATH=src python3 -m pytest -q tests
```

Run the existing ROS package contract tests without starting ROS nodes:

```bash
cd /home/yhc/kaiti_yolopose_framework
PYTHONPATH=src python3 -m pytest -q ros2_ws/src/yolopose_ros/test
```

No command in this S0 protocol launches an S1–S8 node or simulation.

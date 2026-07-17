from __future__ import annotations

from collections import deque
from pathlib import Path
import math
import subprocess
import sys

from PIL import Image
import yaml


ROOT = Path(__file__).resolve().parents[1]


def test_sdf_static_map_keeps_all_planner_waypoints_connected(tmp_path: Path) -> None:
    output = tmp_path / "house"
    subprocess.run(
        [
            sys.executable,
            str(ROOT / "scripts/build_house_static_map.py"),
            "--world",
            str(ROOT / "ros2_ws/src/yolopose_ros/worlds/kaiti_house_world.sdf"),
            "--output-base",
            str(output),
        ],
        check=True,
    )

    metadata = yaml.safe_load(output.with_suffix(".yaml").read_text(encoding="utf-8"))
    image = Image.open(output.with_suffix(".pgm")).convert("L")
    width, height = image.size
    resolution = float(metadata["resolution"])
    origin_x, origin_y, _ = metadata["origin"]
    inflation_cells = math.ceil(0.25 / resolution)
    blocked = {
        (x, y)
        for y in range(height)
        for x in range(width)
        if image.getpixel((x, y)) < 250
    }
    inflated = set()
    for x, y in blocked:
        for dy in range(-inflation_cells, inflation_cells + 1):
            for dx in range(-inflation_cells, inflation_cells + 1):
                if dx * dx + dy * dy <= inflation_cells * inflation_cells:
                    inflated.add((x + dx, y + dy))

    waypoints = yaml.safe_load(
        (ROOT / "configs/planner_waypoints.yaml").read_text(encoding="utf-8")
    )["waypoints"]

    def cell(waypoint: dict) -> tuple[int, int]:
        return (
            round((float(waypoint["x"]) - origin_x) / resolution),
            height - 1 - round((float(waypoint["y"]) - origin_y) / resolution),
        )

    start = cell(waypoints["A"])
    queue = deque([start])
    reachable = {start}
    while queue:
        x, y = queue.popleft()
        for dx, dy in ((1, 0), (-1, 0), (0, 1), (0, -1), (1, 1), (1, -1), (-1, 1), (-1, -1)):
            candidate = (x + dx, y + dy)
            if (
                0 <= candidate[0] < width
                and 0 <= candidate[1] < height
                and candidate not in inflated
                and candidate not in reachable
            ):
                reachable.add(candidate)
                queue.append(candidate)

    assert {name: cell(value) in reachable for name, value in waypoints.items()} == {
        "A": True,
        "B": True,
        "C": True,
        "D": True,
        "S": True,
    }

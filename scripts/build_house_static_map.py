#!/usr/bin/env python3
"""Generate the reproducible Gazebo known-map asset from the house SDF.

This is intentionally a simulation asset generator, not a SLAM replacement.
Physical-robot maps must still be produced by the selected SLAM package.
"""

from __future__ import annotations

import argparse
import math
import xml.etree.ElementTree as ET
from pathlib import Path

import yaml
from PIL import Image, ImageDraw


STATIC_VISUALS = {"bed_B", "supply_shelf_S_visual"}


def _pose_xy(element: ET.Element) -> tuple[float, float]:
    pose = element.findtext("pose", default="0 0 0 0 0 0").split()
    return float(pose[0]), float(pose[1])


def _box_xy(element: ET.Element) -> tuple[float, float] | None:
    size = element.findtext("geometry/box/size")
    if not size:
        return None
    fields = size.split()
    return float(fields[0]), float(fields[1])


def _world_boxes(root: ET.Element) -> list[tuple[str, float, float, float, float]]:
    boxes = []
    for model in root.findall(".//world/model"):
        model_x, model_y = _pose_xy(model)
        for link in model.findall("link"):
            link_x, link_y = _pose_xy(link)
            for collision in link.findall("collision"):
                if collision.get("name") == "floor_collision":
                    continue
                size = _box_xy(collision)
                if size is None:
                    continue
                x, y = _pose_xy(collision)
                boxes.append(
                    (
                        collision.get("name", "collision"),
                        model_x + link_x + x,
                        model_y + link_y + y,
                        size[0],
                        size[1],
                    )
                )
            for visual in link.findall("visual"):
                if visual.get("name") not in STATIC_VISUALS:
                    continue
                size = _box_xy(visual)
                if size is None:
                    continue
                x, y = _pose_xy(visual)
                boxes.append(
                    (
                        visual.get("name", "visual"),
                        model_x + link_x + x,
                        model_y + link_y + y,
                        size[0],
                        size[1],
                    )
                )
    return boxes


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--world",
        type=Path,
        default=Path("ros2_ws/src/yolopose_ros/worlds/kaiti_house_world.sdf"),
    )
    parser.add_argument(
        "--output-base",
        type=Path,
        default=Path("maps/candidates/kaiti_house_sdf_static"),
    )
    parser.add_argument("--resolution", type=float, default=0.05)
    parser.add_argument("--origin-x", type=float, default=-0.5)
    parser.add_argument("--origin-y", type=float, default=-0.5)
    parser.add_argument("--width-m", type=float, default=8.0)
    parser.add_argument("--height-m", type=float, default=7.0)
    args = parser.parse_args()

    root = ET.parse(args.world).getroot()
    boxes = _world_boxes(root)
    width = math.ceil(args.width_m / args.resolution)
    height = math.ceil(args.height_m / args.resolution)
    image = Image.new("L", (width, height), color=254)
    draw = ImageDraw.Draw(image)

    def pixel(x: float, y: float) -> tuple[int, int]:
        return (
            round((x - args.origin_x) / args.resolution),
            height - 1 - round((y - args.origin_y) / args.resolution),
        )

    for _name, center_x, center_y, size_x, size_y in boxes:
        left, top = pixel(center_x - size_x / 2.0, center_y + size_y / 2.0)
        right, bottom = pixel(center_x + size_x / 2.0, center_y - size_y / 2.0)
        draw.rectangle((left, top, right, bottom), fill=0)

    args.output_base.parent.mkdir(parents=True, exist_ok=True)
    pgm_path = args.output_base.with_suffix(".pgm")
    yaml_path = args.output_base.with_suffix(".yaml")
    image.save(pgm_path)
    metadata = {
        "image": pgm_path.name,
        "mode": "trinary",
        "resolution": args.resolution,
        "origin": [args.origin_x, args.origin_y, 0.0],
        "negate": 0,
        "occupied_thresh": 0.65,
        "free_thresh": 0.25,
        "source_world": str(args.world),
        "generator": "scripts/build_house_static_map.py",
    }
    yaml_path.write_text(yaml.safe_dump(metadata, sort_keys=False), encoding="utf-8")
    print(f"Generated {pgm_path} and {yaml_path} from {len(boxes)} static boxes")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

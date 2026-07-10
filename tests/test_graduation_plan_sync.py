from __future__ import annotations

import hashlib
import json
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
MANIFEST_PATH = PROJECT_ROOT / "docs/generated/graduation_research_plan_v2.manifest.json"


def _sha256(path: Path) -> str:
    digest = hashlib.sha256()
    digest.update(path.read_bytes())
    return digest.hexdigest()


def test_generated_research_plan_matches_manifest() -> None:
    manifest = json.loads(MANIFEST_PATH.read_text(encoding="utf-8"))
    source = PROJECT_ROOT / manifest["source_path"]
    output = PROJECT_ROOT / manifest["output_path"]

    assert manifest["research_plan_version"] == "2.0"
    assert manifest["generator_version"] == "2.0.0"
    assert source.exists()
    assert output.exists()
    assert _sha256(source) == manifest["source_sha256"]
    assert _sha256(output) == manifest["output_sha256"]


def test_research_plan_freezes_required_method_boundaries() -> None:
    text = (PROJECT_ROOT / "docs/graduation_research_plan_v2.md").read_text(encoding="utf-8")
    required_phrases = [
        "局部修复研究",
        "pickup 与 deliver 必须由同一机器人",
        "degraded 保留 active episode",
        "直接后继变量",
        "资源预约按路径进入/离开区间互斥",
        "不调用 PlanSys2 Planner",
        "SATISFIED / VIOLATED / INCONCLUSIVE",
        "3 车仿真",
        "2 车实物",
    ]
    for phrase in required_phrases:
        assert phrase in text

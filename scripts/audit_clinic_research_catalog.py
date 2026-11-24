#!/usr/bin/env python3
"""Read-only audit of the curated Clinic presentation catalog and raw history."""
from __future__ import annotations
import argparse
import json
from pathlib import Path
import sys

REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO / "src"))
from kaiti_review.data import descriptors
from kaiti_review.explanations import catalog_metadata, research_catalog


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/home/yhc/clinic_planning_ws"))
    parser.add_argument("--out", type=Path, required=True)
    args = parser.parse_args()
    root = args.workspace.resolve()
    runs = catalog_metadata(root, descriptors(root))
    selected = {row["run_id"] for row in research_catalog().get("primary", [])}
    rows = []
    for run in runs:
        core = run["run_id"] in selected
        rows.append({
            "run_id": run["run_id"],
            "display_name_zh": run["display_name_zh"],
            "result_status": run["result_status"],
            "research_content": run.get("research_content", []),
            "listing_group": "core_research" if core else ("engineering_probe" if run.get("debug_confirmed") else "historical_development"),
            "listing_reason": run.get("listing_reason", "已人工审核并列入当前研究主展示目录。") if not core else "已人工审核并列入当前研究主展示目录。",
            "configuration_source": run.get("configuration_source"),
        })
    out = args.out.resolve()
    out.mkdir(parents=True, exist_ok=True)
    result = {
        "schema": "clinic-research-catalog-audit/v1",
        "read_only": True,
        "raw_run_count": len(rows),
        "primary_run_count": sum(row["listing_group"] == "core_research" for row in rows),
        "engineering_probe_count": sum(row["listing_group"] == "engineering_probe" for row in rows),
        "historical_not_promoted_count": sum(row["listing_group"] == "historical_development" for row in rows),
        "offline_supporting_studies": research_catalog().get("supporting", []),
        "runs": rows,
        "note": "Non-primary files remain intact in the source workspace; this audit only records default presentation classification.",
    }
    (out / "research_catalog_audit.json").write_text(json.dumps(result, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({key: result[key] for key in ("raw_run_count", "primary_run_count", "engineering_probe_count", "historical_not_promoted_count")}, ensure_ascii=False))


if __name__ == "__main__":
    main()

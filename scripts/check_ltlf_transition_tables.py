#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_TABLE = REPO_ROOT / "configs/generated/ltlf_transition_tables.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main() -> None:
    parser = argparse.ArgumentParser(description="Check generated LTLf table integrity.")
    parser.add_argument("--table", type=Path, default=DEFAULT_TABLE)
    args = parser.parse_args()

    table_path = args.table.resolve()
    payload = json.loads(table_path.read_text(encoding="utf-8"))
    source_path = REPO_ROOT / payload["source_path"]
    if payload["source_sha256"] != _sha256(source_path):
        raise SystemExit("LTLf source hash mismatch; regenerate transition tables")

    for specification in payload.get("specifications", []):
        ap_count = len(specification["atomic_propositions"])
        state_count = int(specification["state_count"])
        expected_width = 1 << ap_count
        transitions = specification["transitions"]
        if len(transitions) != state_count:
            raise SystemExit(f"{specification['id']}: state count mismatch")
        for state in range(state_count):
            row = transitions.get(str(state))
            if row is None or len(row) != expected_width:
                raise SystemExit(f"{specification['id']}: incomplete state {state}")
            if any(int(destination) < 0 or int(destination) >= state_count for destination in row):
                raise SystemExit(f"{specification['id']}: invalid destination in state {state}")

    print(
        json.dumps(
            {
                "in_sync": True,
                "table_path": str(table_path.relative_to(REPO_ROOT)),
                "source_sha256": payload["source_sha256"],
                "specification_count": len(payload.get("specifications", [])),
            },
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

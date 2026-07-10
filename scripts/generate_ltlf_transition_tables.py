#!/usr/bin/env python3
from __future__ import annotations

import argparse
import hashlib
import json
from pathlib import Path
from typing import Any

import buddy
import spot

REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_SOURCE = REPO_ROOT / "configs/ltlf_specifications.json"
DEFAULT_OUTPUT = REPO_ROOT / "configs/generated/ltlf_transition_tables.json"


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _valuation_cube(automaton: Any, propositions: list[tuple[str, Any]], mask: int) -> Any:
    cube = buddy.bddtrue
    dictionary = automaton.get_dict()
    for bit, (_, proposition) in enumerate(propositions):
        variable = dictionary.varnum(proposition)
        literal = (
            buddy.bdd_ithvar(variable)
            if mask & (1 << bit)
            else buddy.bdd_nithvar(variable)
        )
        cube &= literal
    return cube


def _reachable(graph: dict[int, set[int]], start: int) -> set[int]:
    seen = {start}
    pending = [start]
    while pending:
        state = pending.pop()
        for destination in graph[state]:
            if destination not in seen:
                seen.add(destination)
                pending.append(destination)
    return seen


def build_transition_table(specification: dict[str, Any]) -> dict[str, Any]:
    formula = str(specification["formula"])
    translated = spot.from_ltlf(formula)
    buchi = translated.translate("buchi", "sbacc", "deterministic", "complete")
    automaton = spot.to_finite(buchi)
    if not automaton.is_deterministic():
        raise RuntimeError(f"Spot returned a non-deterministic automaton for {formula!r}")

    propositions = sorted((str(item), item) for item in automaton.ap())
    proposition_names = [name for name, _ in propositions]
    valuation_count = 1 << len(propositions)
    transitions: dict[str, list[int]] = {}
    graph: dict[int, set[int]] = {state: set() for state in range(automaton.num_states())}

    for state in range(automaton.num_states()):
        row: list[int] = []
        outgoing = list(automaton.out(state))
        for mask in range(valuation_count):
            cube = _valuation_cube(automaton, propositions, mask)
            destinations = sorted(
                {
                    int(edge.dst)
                    for edge in outgoing
                    if (edge.cond & cube) != buddy.bddfalse
                }
            )
            if len(destinations) != 1:
                raise RuntimeError(
                    f"Expected one destination for state={state}, mask={mask}; got {destinations}"
                )
            destination = destinations[0]
            row.append(destination)
            graph[state].add(destination)
        transitions[str(state)] = row

    accepting = {
        state
        for state in range(automaton.num_states())
        if automaton.state_is_accepting(state)
    }
    permanently_accepting = []
    rejecting = []
    for state in range(automaton.num_states()):
        reachable = _reachable(graph, state)
        if reachable and reachable.issubset(accepting):
            permanently_accepting.append(state)
        if not reachable.intersection(accepting):
            rejecting.append(state)

    return {
        "id": str(specification["id"]),
        "scope": str(specification["scope"]),
        "formula": formula,
        "spot_rewrite": str(translated),
        "atomic_propositions": proposition_names,
        "mask_semantics": "bit i is 1 iff atomic_propositions[i] is true",
        "initial_state": int(automaton.get_init_state_number()),
        "state_count": int(automaton.num_states()),
        "accepting_states": sorted(accepting),
        "permanently_accepting_states": permanently_accepting,
        "rejecting_states": rejecting,
        "transitions": transitions,
    }


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Generate runtime-only LTLf transition tables with Spot."
    )
    parser.add_argument("--source", type=Path, default=DEFAULT_SOURCE)
    parser.add_argument("--output", type=Path, default=DEFAULT_OUTPUT)
    args = parser.parse_args()

    source = args.source.resolve()
    output = args.output.resolve()
    raw = json.loads(source.read_text(encoding="utf-8"))
    specifications = raw.get("specifications", [])
    if not specifications:
        raise ValueError("LTLf specification source contains no specifications")

    payload = {
        "schema_version": 1,
        "source_path": str(source.relative_to(REPO_ROOT)),
        "source_sha256": _sha256(source),
        "generator": {
            "name": "Spot",
            "version": spot.version(),
            "pipeline": "from_ltlf -> deterministic complete buchi/sbacc -> to_finite",
        },
        "specifications": [build_transition_table(item) for item in specifications],
    }
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    print(json.dumps({"output": str(output), "specification_count": len(specifications)}, indent=2))


if __name__ == "__main__":
    main()

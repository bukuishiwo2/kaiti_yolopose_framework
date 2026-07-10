from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import json
from pathlib import Path
from typing import Iterable


class TraceVerdict(str, Enum):
    SATISFIED = "SATISFIED"
    VIOLATED = "VIOLATED"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass(frozen=True)
class TransitionTable:
    specification_id: str
    scope: str
    formula: str
    atomic_propositions: tuple[str, ...]
    initial_state: int
    accepting_states: frozenset[int]
    permanently_accepting_states: frozenset[int]
    rejecting_states: frozenset[int]
    transitions: dict[int, tuple[int, ...]]


def load_transition_tables(path: str | Path) -> dict[str, TransitionTable]:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    tables: dict[str, TransitionTable] = {}
    for item in payload.get("specifications", []):
        table = TransitionTable(
            specification_id=str(item["id"]),
            scope=str(item["scope"]),
            formula=str(item["formula"]),
            atomic_propositions=tuple(str(value) for value in item["atomic_propositions"]),
            initial_state=int(item["initial_state"]),
            accepting_states=frozenset(int(value) for value in item["accepting_states"]),
            permanently_accepting_states=frozenset(
                int(value) for value in item["permanently_accepting_states"]
            ),
            rejecting_states=frozenset(int(value) for value in item["rejecting_states"]),
            transitions={
                int(state): tuple(int(value) for value in row)
                for state, row in item["transitions"].items()
            },
        )
        tables[table.specification_id] = table
    return tables


class LtlfTraceMonitor:
    def __init__(self, table: TransitionTable, *, scope_id: str) -> None:
        if not scope_id:
            raise ValueError("scope_id must be non-empty")
        self.table = table
        self.scope_id = scope_id
        self.state = table.initial_state
        self.step_count = 0

    def reset(self) -> None:
        self.state = self.table.initial_state
        self.step_count = 0

    def step(self, propositions: Iterable[str]) -> TraceVerdict:
        active = set(propositions)
        unknown = active.difference(self.table.atomic_propositions)
        if unknown:
            raise ValueError(f"unknown propositions for {self.table.specification_id}: {sorted(unknown)}")
        mask = 0
        for bit, proposition in enumerate(self.table.atomic_propositions):
            if proposition in active:
                mask |= 1 << bit
        self.state = self.table.transitions[self.state][mask]
        self.step_count += 1
        return self.verdict(trace_ended=False)

    def verdict(self, *, trace_ended: bool) -> TraceVerdict:
        if trace_ended:
            return (
                TraceVerdict.SATISFIED
                if self.state in self.table.accepting_states
                else TraceVerdict.VIOLATED
            )
        if self.state in self.table.permanently_accepting_states:
            return TraceVerdict.SATISFIED
        if self.state in self.table.rejecting_states:
            return TraceVerdict.VIOLATED
        return TraceVerdict.INCONCLUSIVE

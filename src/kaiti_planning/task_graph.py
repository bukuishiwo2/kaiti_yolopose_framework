from __future__ import annotations

from collections import defaultdict, deque

from .models import PlanningProblem


def build_predecessor_map(problem: PlanningProblem) -> dict[str, set[str]]:
    preds: dict[str, set[str]] = defaultdict(set)
    for before, after in problem.precedence:
        preds[after].add(before)
        preds.setdefault(before, set())
    for task in problem.tasks:
        preds.setdefault(task.id, set())
    return preds


def topological_task_order(problem: PlanningProblem) -> list[str]:
    preds = build_predecessor_map(problem)
    outgoing: dict[str, set[str]] = defaultdict(set)
    indegree: dict[str, int] = {}
    for task_id, task_preds in preds.items():
        indegree[task_id] = len(task_preds)
        for pred in task_preds:
            outgoing[pred].add(task_id)

    queue = deque(sorted([task_id for task_id, degree in indegree.items() if degree == 0]))
    order: list[str] = []
    while queue:
        current = queue.popleft()
        order.append(current)
        for nxt in sorted(outgoing.get(current, set())):
            indegree[nxt] -= 1
            if indegree[nxt] == 0:
                queue.append(nxt)

    if len(order) != len(indegree):
        raise ValueError("precedence graph contains a cycle")
    return order

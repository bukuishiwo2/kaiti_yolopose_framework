"""Independent checker mutations and enumeration completeness for the new harness."""
from copy import deepcopy
from pathlib import Path
import sys

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import verify_random_repair_equivalence as h


def test_seeded_generation_and_structure_counts():
    for nr, nt, masked, expected in [(2, 4, False, 8), (3, 5, False, 240), (3, 6, True, 28)]:
        a = h.make_instance(7, nr, nt, masked)
        assert h.encode(a) == h.encode(h.make_instance(7, nr, nt, masked))
        assert h.encode(a) != h.encode(h.make_instance(19, nr, nt, masked))
        structures = list(h.structures(a))
        assert len(structures) == expected
        assert len({h.encode(s) for s in structures}) == expected


@pytest.fixture(scope="module")
def solved(tmp_path_factory):
    out = tmp_path_factory.mktemp("seeded_equivalence")
    (out / "cbc_logs").mkdir()
    data = next(h.variants(h.make_instance(7, 3, 5, False)))
    tpl = h.template(data)
    runner = h.Runner(out, 5.)
    reference = {"owners": data["reference"]["owners"],
                 "routes": data["reference"]["routes"],
                 "orders": data["reference"]["resource_orders"]}
    result = h.solve(data, tpl, runner, "monolithic", reference, 20., 100)
    assert result["status"] == "OPTIMAL"
    assert result["validation"]["passed"]
    core = dict.fromkeys(tpl["bounds"], 0.)
    core.update(result["core"])
    return data, core, result["outer"], result["objective"]


def invalid_groups(data, core, outer, objective):
    result = h.validate(data, core, outer, objective)
    assert not result["passed"]
    return {x["group"] for x in result["failures"]}, result


def test_checker_rejects_monitor_gap(solved):
    data, core, outer, objective = deepcopy(solved)
    outer["m"] = core["s_D"] + data["tasks"]["D"]["duration"] - 1
    assert "monitor" in invalid_groups(data, core, outer, objective)[0]


def test_checker_rejects_resource_overlap(solved):
    data, core, outer, objective = deepcopy(solved)
    core["s_Q0"] = core["s_P"]
    assert "resource" in invalid_groups(data, core, outer, objective)[0]


def test_checker_rejects_cargo_handoff(solved):
    data, core, outer, objective = deepcopy(solved)
    owner = next(i for i in data["robots"] if core[h.xkey(i, "P")] > .5)
    alternate = next(i for i in data["tasks"]["P"]["allowed"] if i != owner)
    core[h.xkey(owner, "P")] = 0
    core[h.xkey(alternate, "P")] = 1
    assert "cargo" in invalid_groups(data, core, outer, objective)[0]


def test_checker_rejects_energy_trace_mismatch(solved):
    data, core, outer, objective = deepcopy(solved)
    outer["Eend_R0"] += 1
    assert "energy" in invalid_groups(data, core, outer, objective)[0]


def test_checker_rejects_hard_deadline(solved):
    data, core, outer, objective = deepcopy(solved)
    data["tasks"]["D"]["deadline"] = core["s_D"] + data["tasks"]["D"]["duration"] - 1
    assert "deadline" in invalid_groups(data, core, outer, objective)[0]


def test_checker_rejects_nonbinary_direction(solved):
    data, core, outer, objective = deepcopy(solved)
    core["order_0"] = .5
    assert "integrality" in invalid_groups(data, core, outer, objective)[0]


def test_checker_rejects_omitted_cost(solved):
    data, core, outer, objective = solved
    _, result = invalid_groups(data, core, outer, objective - 1)
    assert result["objective_error"] > .99


def test_iteration_limit_does_not_claim_infeasible(tmp_path):
    (tmp_path / "cbc_logs").mkdir()
    data = next(d for d in h.variants(h.make_instance(7, 2, 4, False)) if d["mode"] == "energy_infeasible")
    result = h.solve(data, h.template(data), h.Runner(tmp_path, 5.), "decomposition", None, 20., 1)
    assert result["status"] == "UNKNOWN_BUDGET"
    assert "objective" not in result

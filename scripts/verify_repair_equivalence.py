#!/usr/bin/env python3
"""Isolated A0--A5/B verification; never imports the production planner or ROS.

Requires the existing PuLP/CBC and SciPy installations. All output is written to
a new directory. This is a finite example harness, not the proposed general
planner, and analytic projections are explicitly distinguished from LP cuts.
"""
from __future__ import annotations

import argparse
from dataclasses import asdict, dataclass, replace
from datetime import datetime
import hashlib
import itertools
import json
from pathlib import Path
import platform
import sys
from time import perf_counter
from zoneinfo import ZoneInfo

import numpy as np
import pulp
import scipy
from scipy.optimize import linprog


ROOT = Path(__file__).resolve().parents[1]
FEAS_TOL = 1e-7
OBJ_TOL = 1e-6


@dataclass(frozen=True)
class Case:
    name: str
    family: str = "A"
    d_min: float = 90
    u_max: float = 110
    v_fixed: float | None = None
    sigma_fixed: int | None = None
    owner_fixed: str | None = None
    only_r1: bool = False
    sequence: tuple[tuple[str, ...], tuple[str, ...]] | None = None
    expected: float | None = None  # None denotes an analytically infeasible case.


def cases() -> list[Case]:
    return [
        Case("A0", sigma_fixed=0, expected=29),
        Case("A1", expected=29),
        Case("A2", v_fixed=95, sigma_fixed=0),
        Case("A3", v_fixed=95, expected=49),
        Case("A4", u_max=100, v_fixed=95),
        Case("A5", d_min=94),
        Case("B", family="B", expected=0),
        Case("B_owner_R1", family="B", owner_fixed="R1", expected=0),
        Case("B_owner_R2", family="B", owner_fixed="R2", expected=1),
        Case("B_only_R1", family="B", only_r1=True, expected=0),
    ]


@dataclass
class Row:
    name: str
    outer: dict[str, float]
    rhs: float
    core: dict[str, float]


@dataclass
class External:
    names: list[str]
    cost: dict[str, float]
    rows: list[Row]

    def matrices(self, core: dict[str, float]):
        a = np.array([[r.outer.get(k, 0) for k in self.names] for r in self.rows], dtype=float)
        rhs = np.array([r.rhs + sum(c * core[k] for k, c in r.core.items()) for r in self.rows])
        c = np.array([self.cost.get(k, 0) for k in self.names], dtype=float)
        return a, rhs, c


def external(case: Case) -> External:
    rows: list[Row] = []

    def row(name, outer, rhs=0.0, core=None):
        rows.append(Row(name, outer, rhs, core or {}))

    def bound(name, low, high):
        row(f"{name}_lower", {name: 1}, low)
        row(f"{name}_upper", {name: -1}, -high)

    if case.family == "A":
        row("monitor_covers_delivery", {"m": 1}, core={"d": 1})
        row("monitor_before_U", {"m": -1}, 5, {"u": -1})
        row("energy_equality_ge", {"E": 1, "m": .5}, 56.5)
        row("energy_equality_le", {"E": -1, "m": -.5}, -56.5)
        row("future_energy_and_return", {"E": 1}, 10)
        row("monitor_shift_positive", {"hm": 1, "m": -1}, -80)
        row("monitor_shift_negative", {"hm": 1, "m": 1}, 80)
        bound("m", 60, 150)
        bound("E", 0, 60)
        bound("hm", 0, 70)
        return External(["m", "E", "hm"], {"hm": 1}, rows)

    names = ["sA", "fA", "sB", "fB", "end_R1", "end_R2"]
    for task, release, deadline in [("A", 0, 2), ("B", 4, 6)]:
        row(f"{task}_duration_ge", {f"f{task}": 1, f"s{task}": -1}, 2)
        row(f"{task}_duration_le", {f"f{task}": -1, f"s{task}": 1}, -2)
        row(f"{task}_release", {f"s{task}": 1}, release)
        row(f"{task}_deadline", {f"f{task}": -1}, -deadline)
    for name in names:
        bound(name, 0, 10)

    def time_expr(node, robot, finish):
        if node == "0":
            return {}, {}, 0.0
        if node == "end":
            return {f"end_{robot}": 1}, {}, 0.0
        if node == "C":
            return {}, {"sC": 1}, 2.0 if finish else 0.0
        return {f"{'f' if finish else 's'}{node}": 1}, {}, 0.0

    for robot, u, v in arcs():
        eo, ec, const = time_expr(v, robot, False)
        fo, fc, previous = time_expr(u, robot, True)
        outer = {k: eo.get(k, 0) - fo.get(k, 0) for k in set(eo) | set(fo)}
        coeff = {k: fc.get(k, 0) - ec.get(k, 0) for k in set(ec) | set(fc)}
        coeff[arc_key(robot, u, v)] = 20
        row(f"time_{robot}_{u}_{v}", outer, -20 - const + previous, coeff)
    return External(names, {}, rows)


def arcs():
    for robot in ("R1", "R2"):
        for u in ("0", "A", "B", "C"):
            for v in ("A", "B", "C", "end"):
                if u != v:
                    yield robot, u, v


def arc_key(robot, u, v):
    return f"a_{robot}_{u}_{v}"


def expr(coeff, variables):
    return pulp.lpSum(c * variables[k] for k, c in coeff.items())


def build_core(case: Case):
    model = pulp.LpProblem(case.name, pulp.LpMinimize)
    if case.family == "A":
        v = {
            "d": pulp.LpVariable("d", case.d_min, 100),
            "u": pulp.LpVariable("u", 60, case.u_max),
            "v": pulp.LpVariable("v", 60, 105),
            "sigma": pulp.LpVariable("sigma", cat="Binary"),
        }
        model += v["v"] >= v["d"] + 5
        model += v["v"] - v["u"] >= 1 - 200 * v["sigma"]
        model += v["u"] - v["v"] >= 11 - 200 * (1 - v["sigma"])
        if case.v_fixed is not None:
            model += v["v"] == case.v_fixed
        if case.sigma_fixed is not None:
            model += v["sigma"] == case.sigma_fixed
        return model, v, v["d"] - 80 + v["u"] - 90 + v["v"] - 92 + 10 * v["sigma"]

    v = {f"x_{r}_{j}": pulp.LpVariable(f"x_{r}_{j}", cat="Binary")
         for r in ("R1", "R2") for j in ("A", "B", "C")}
    v.update({arc_key(r, u, w): pulp.LpVariable(arc_key(r, u, w), cat="Binary")
              for r, u, w in arcs()})
    v["sC"] = pulp.LpVariable("sC", 2, 2)
    rank = {(r, j): pulp.LpVariable(f"q_{r}_{j}", 0, 3)
            for r in ("R1", "R2") for j in ("A", "B", "C")}
    for j in ("A", "B", "C"):
        model += sum(v[f"x_{r}_{j}"] for r in ("R1", "R2")) == 1
    for j in ("A", "B"):
        model += v[f"x_R1_{j}"] == 1
    if case.only_r1:
        model += v["x_R1_C"] == 1
    if case.owner_fixed:
        model += v[f"x_{case.owner_fixed}_C"] == 1
    for r in ("R1", "R2"):
        model += sum(v[arc_key(r, u, w)] for rr, u, w in arcs() if rr == r and u == "0") == 1
        model += sum(v[arc_key(r, u, w)] for rr, u, w in arcs() if rr == r and w == "end") == 1
        for j in ("A", "B", "C"):
            model += sum(v[arc_key(r, u, w)] for rr, u, w in arcs() if rr == r and w == j) == v[f"x_{r}_{j}"]
            model += sum(v[arc_key(r, u, w)] for rr, u, w in arcs() if rr == r and u == j) == v[f"x_{r}_{j}"]
            model += rank[r, j] >= v[f"x_{r}_{j}"]
            model += rank[r, j] <= 3 * v[f"x_{r}_{j}"]
        for rr, u, w in arcs():
            if rr == r and u in "ABC" and w in "ABC":
                model += rank[r, w] >= rank[r, u] + 1 - 4 * (1 - v[arc_key(r, u, w)])
    model += rank["R1", "B"] >= rank["R1", "A"] + 1
    if case.sequence is not None:
        for r, tasks in zip(("R1", "R2"), case.sequence):
            route = ("0",) + tasks + ("end",)
            for u, w in zip(route, route[1:]):
                model += v[arc_key(r, u, w)] == 1
    return model, v, v["sC"] - 2 + v["x_R2_C"]


def add_external(model, core, spec):
    outer = {k: pulp.LpVariable(k, lowBound=None) for k in spec.names}
    for row in spec.rows:
        model += expr(row.outer, outer) >= row.rhs + expr(row.core, core), f"outer_{row.name}"
    return outer


def add_projection(model, core, case):
    if case.family == "A":
        model += core["u"] >= core["d"] + 5
        model += core["d"] <= 93
        theta = pulp.LpVariable("theta", 0)
        model += theta >= core["d"] - 80
        return theta

    def time(node, finish):
        if node == "0":
            return 0
        if node == "end":
            return 10  # An end time <=10 exists iff every selected last task finishes <=10.
        return core["sC"] + (2 if finish else 0) if node == "C" else {
            ("A", False): 0, ("A", True): 2, ("B", False): 4, ("B", True): 6
        }[node, finish]
    for r, u, v in arcs():
        model += time(v, False) >= time(u, True) - 20 * (1 - core[arc_key(r, u, v)])
    return 0


def lp_extend(spec: External, core: dict[str, float]):
    """Phase-I gives a checkable Farkas certificate; optimal LP gives cost duals."""
    a, rhs, c = spec.matrices(core)
    nrows, nvars = a.shape
    phase = linprog(np.r_[np.zeros(nvars), np.ones(nrows)],
                    A_ub=np.c_[-a, -np.eye(nrows)], b_ub=-rhs,
                    bounds=[(None, None)] * nvars + [(0, None)] * nrows, method="highs")
    if phase.status != 0:
        raise RuntimeError(f"Phase-I LP did not reach optimum: {phase.message}")
    if phase.fun > FEAS_TOL:
        dual = -phase.ineqlin.marginals
        stationarity = float(np.max(np.abs(a.T @ dual)))
        violation = float(dual @ rhs)
        valid = min(dual) >= -FEAS_TOL and stationarity <= FEAS_TOL and violation > FEAS_TOL
        if not valid:
            raise RuntimeError("Invalid Farkas certificate")
        return {"status": "INFEASIBLE", "certificate": dual.tolist(),
                "stationarity_residual": stationarity, "certificate_value": violation,
                "phase_one_objective": float(phase.fun), "certificate_valid": True}
    opt = linprog(c, A_ub=-a, b_ub=-rhs, bounds=[(None, None)] * nvars, method="highs")
    if opt.status != 0:
        raise RuntimeError(f"External cost LP did not reach optimum: {opt.message}")
    dual = -opt.ineqlin.marginals
    residual = float(np.max(np.abs(a.T @ dual - c)))
    primal_residual = float(max(0, np.max(rhs - a @ opt.x)))
    dual_value = float(dual @ rhs)
    gap = abs(dual_value - opt.fun)
    if min(dual) < -FEAS_TOL or max(residual, primal_residual) > FEAS_TOL or gap > OBJ_TOL:
        raise RuntimeError("Invalid external LP primal/dual certificate")
    return {"status": "OPTIMAL", "objective": float(opt.fun),
            "outer": dict(zip(spec.names, map(float, opt.x))), "certificate": dual.tolist(),
            "stationarity_residual": residual, "primal_residual": primal_residual,
            "certificate_value": dual_value, "duality_gap": gap, "certificate_valid": True}


class Runner:
    def __init__(self, out: Path, time_limit: float):
        self.out, self.time_limit, self.calls = out, time_limit, 0

    def cbc(self, model):
        self.calls += 1
        log = self.out / "cbc_logs" / f"solve_{self.calls:04d}.log"
        solver = pulp.PULP_CBC_CMD(msg=False, threads=0, gapRel=0, gapAbs=0,
                                  options=["randomSeed 1", "randomCbcSeed 1"],
                                  timeLimit=self.time_limit, logPath=str(log))
        model.solve(solver)
        raw = log.read_text()
        # PuLP may map a time-limited incumbent to LpStatusOptimal: require a
        # solver proof and its independent solution status before accepting it.
        if ("Result - Optimal solution found" in raw or "Optimal objective" in raw) and model.sol_status == pulp.LpSolutionOptimal:
            return "OPTIMAL"
        if model.status == pulp.LpStatusInfeasible and "infeasible" in raw.lower():
            return "INFEASIBLE"
        return "UNKNOWN_BUDGET" if "Stopped on time limit" in raw else "SOLVER_ERROR"

    def solve(self, case, method):
        begin, call_start = perf_counter(), self.calls
        model, variables, local_cost = build_core(case)
        spec = external(case)
        base = {"method": method, "case": case.name, "trace": []}
        if method == "monolithic":
            outer = add_external(model, variables, spec)
            model += local_cost + expr(spec.cost, outer)
            status = self.cbc(model)
            if status == "OPTIMAL":
                base["core"] = {k: float(v.value()) for k, v in variables.items()}
                base["outer"] = {k: float(v.value()) for k, v in outer.items()}
                base["objective"] = float(pulp.value(model.objective))
        elif method == "projection":
            model += local_cost + add_projection(model, variables, case)
            status = self.cbc(model)
            if status == "OPTIMAL":
                core = {k: float(v.value()) for k, v in variables.items()}
                if case.family == "A":
                    outer = {"m": core["d"], "E": 56.5 - .5 * core["d"], "hm": core["d"] - 80}
                else:
                    outer = {"sA": 0., "fA": 2., "sB": 4., "fB": 6.}
                    for r in ("R1", "R2"):
                        tasks = [u for rr, u, v in arcs() if rr == r and v == "end" and core[arc_key(r, u, v)] > .5]
                        outer[f"end_{r}"] = {"0": 0., "A": 2., "B": 6., "C": core["sC"] + 2}[tasks[0]]
                base.update(core=core, outer=outer, objective=float(pulp.value(model.objective)))
        else:
            theta = pulp.LpVariable("theta", 0)
            model += local_cost + theta
            status, seen = "UNKNOWN_BUDGET", set()
            spec_hash = digest(json.dumps(asdict(spec), sort_keys=True).encode())
            for iteration in range(1, 101):
                status = self.cbc(model)
                if status != "OPTIMAL":
                    break
                core = {k: float(v.value()) for k, v in variables.items()}
                result = lp_extend(spec, core)
                trace = {"iteration": iteration, "core": core, "theta": float(theta.value()),
                         "master_lower_bound": float(pulp.value(model.objective)), "external": result,
                         "matrix_hash": spec_hash,
                         "scope_hash": digest(json.dumps(asdict(case), sort_keys=True).encode())}
                dual = result["certificate"]
                constant = sum(weight * row.rhs for weight, row in zip(dual, spec.rows))
                coefficients = {k: sum(weight * row.core.get(k, 0) for weight, row in zip(dual, spec.rows))
                                for k in variables}
                cut = constant + expr(coefficients, variables)
                if result["status"] == "INFEASIBLE":
                    kind = "feasibility"
                    model += cut <= 0, f"feasibility_{iteration}"
                else:
                    full_cost = float(pulp.value(local_cost)) + result["objective"]
                    gap = full_cost - trace["master_lower_bound"]
                    trace.update(candidate_upper_bound=full_cost, bound_gap=gap)
                    if gap <= OBJ_TOL * (1 + abs(full_cost)):
                        if gap < -OBJ_TOL:
                            raise RuntimeError("Invalid negative bound gap")
                        base["trace"].append(trace)
                        base.update(core=core, outer=result["outer"], objective=full_cost,
                                    lower_bound=trace["master_lower_bound"], upper_bound=full_cost)
                        status = "OPTIMAL"
                        break
                    kind = "optimality"
                    model += theta >= cut, f"optimality_{iteration}"
                key = (kind, round(constant, 8), tuple((k, round(v, 8)) for k, v in sorted(coefficients.items())))
                if key in seen:
                    raise RuntimeError("Repeated violated cut: no valid progress")
                seen.add(key)
                trace["added_cut"] = {"kind": kind, "constant": constant, "coefficients": coefficients}
                base["trace"].append(trace)
            else:
                status = "UNKNOWN_BUDGET"
        base.update(status=status, runtime_seconds=perf_counter() - begin, cbc_calls=self.calls-call_start,
                    cbc_logs=[f"cbc_logs/solve_{n:04d}.log" for n in range(call_start+1,self.calls+1)])
        if status == "OPTIMAL":
            base["objective_constant"] = float(model.objective.constant)
            base["cbc_objective_without_constant"] = float(pulp.value(model.objective) - model.objective.constant)
            base["validation"] = validate(case, base["core"], base["outer"], base["objective"])
        return base


def validate(case, core, outer, claimed):
    """Independent physical/semantic reconstruction, not reuse of model rows."""
    checks, plan = [], {}

    def ge(name, left, right):
        residual = max(0., float(right-left))
        checks.append({"name": name, "residual": residual, "passed": residual <= FEAS_TOL})

    def eq(name, left, right):
        residual = abs(float(left-right))
        checks.append({"name": name, "residual": residual, "passed": residual <= FEAS_TOL})

    def binary(name, value):
        eq(name + "_integrality", value, round(value))
        ge(name + "_lower", value, 0)
        ge(name + "_upper", 1, value)

    if case.family == "A":
        d,u,v,sigma = (core[k] for k in ("d","u","v","sigma"))
        m = outer["m"]
        binary("sigma", sigma)
        if case.sigma_fixed is not None:
            eq("scope_sigma", sigma, case.sigma_fixed)
        if case.v_fixed is not None:
            eq("fixed_reservation", v, case.v_fixed)
        for name, x, low, high in [("d",d,case.d_min,100),("m",m,60,150),
                                   ("u",u,60,case.u_max),("v",v,60,105)]:
            ge(name+"_lower",x,low); ge(name+"_upper",high,x)
        ge("delivery_robot_available", d-10, 80)
        ge("monitor_covers_delivery", m, d)
        ge("R1_nonoverlap_and_travel", u-5, m)
        ge("R2_nonoverlap_and_travel", v, d+5)
        if round(sigma) == 0:
            ge("H_R1_before_R2_with_buffer", v, u+1)
        else:
            ge("H_R2_before_R1_with_buffer", u-5, v+6)
        e = 26.5 - .5*(m-60)
        eq("monitor_remaining_energy",outer["E"],e)
        for name,value in [("monitor",e),("U_arrival",e-1),("U_finish",e-2),("R1_return",e-3)]:
            ge(name+"_safe",value,7); ge(name+"_capacity",60,value)
        r2_energy = [50.,49.,47.,46.,45.]
        for n,energy in enumerate(r2_energy):
            ge(f"R2_energy_{n}",energy,7); ge(f"R2_capacity_{n}",60,energy)
        ge("U_deadline",case.u_max+10,u+10)
        ge("V_deadline",120,v+15)
        ge("R1_return_horizon",150,u+15)
        ge("R2_return_horizon",150,v+20)
        ge("shift_epigraph_positive",outer["hm"],m-80)
        ge("shift_epigraph_negative",outer["hm"],80-m)
        ge("shift_lower",outer["hm"],0); ge("shift_upper",70,outer["hm"])
        objective = abs(d-80)+abs(m-80)+abs(u-90)+abs(v-92)+10*sigma
        plan = {"owner":{"M":"R1","U":"R1","D":"R2","V":"R2"},
                "tasks":{"M":[60,m],"U":[u,u+10],"D":[d-10,d],"V":[v+5,v+15]},
                "H":{"R1":[u-5,u],"R2":[v,v+5]},
                "return_times":{"R1":u+15,"R2":v+20},
                "R1_energy":[26.5,e,e-1,e-2,e-3],"R2_energy":r2_energy,
                "cargo_owner":"R2","monitor_actual_start":20,"energy_snapshot_time":60}
    else:
        starts = {"A":outer["sA"],"B":outer["sB"],"C":core["sC"]}
        finishes = {"A":outer["fA"],"B":outer["fB"],"C":core["sC"]+2}
        for j,release,deadline in [("A",0,2),("B",4,6),("C",2,4)]:
            eq(j+"_duration",finishes[j]-starts[j],2)
            ge(j+"_release",starts[j],release); ge(j+"_deadline",deadline,finishes[j])
            eq(j+"_unique",sum(core[f"x_{r}_{j}"] for r in ("R1","R2")),1)
        eq("A_owner",core["x_R1_A"],1); eq("B_owner",core["x_R1_B"],1)
        if case.only_r1:
            eq("C_capability",core["x_R1_C"],1)
        if case.owner_fixed:
            eq("C_scope_owner",core[f"x_{case.owner_fixed}_C"],1)
        for k,value in core.items():
            if k.startswith(("x_","a_")):
                binary(k,value)
        routes = {}
        for r in ("R1","R2"):
            selected = [(u,v) for rr,u,v in arcs() if rr==r and core[arc_key(r,u,v)]>.5]
            eq(r+"_source_degree",sum(u=="0" for u,v in selected),1)
            eq(r+"_sink_degree",sum(v=="end" for u,v in selected),1)
            for j in ("A","B","C"):
                eq(r+j+"_in",sum(v==j for u,v in selected),core[f"x_{r}_{j}"])
                eq(r+j+"_out",sum(u==j for u,v in selected),core[f"x_{r}_{j}"])
            route, node, visited = [], "0", set()
            for _ in range(5):
                next_nodes=[v for u,v in selected if u==node]
                if len(next_nodes)!=1:
                    break
                successor=next_nodes[0]
                if successor=="end":
                    node="end"; break
                if successor in visited:
                    break
                visited.add(successor); route.append(successor); node=successor
            eq(r+"_reaches_sink",int(node=="end"),1)
            eq(r+"_no_disconnected_tasks",len(route),sum(core[f"x_{r}_{j}"] for j in "ABC"))
            previous=0.
            for j in route:
                ge(r+j+"_nonoverlap",starts[j],previous)
                previous=finishes[j]
            ge(r+"_return_after_tasks",outer[f"end_{r}"],previous)
            ge(r+"_horizon",10,outer[f"end_{r}"])
            if r=="R1" and "A" in route and "B" in route:
                ge("external_subsequence_A_before_B",route.index("B"),route.index("A")+1)
            routes[r]=route
        if case.sequence is not None:
            for r,expected in zip(("R1","R2"),case.sequence):
                eq(r+"_fixed_structure",int(tuple(routes[r])==expected),1)
        objective=starts["C"]-2+core["x_R2_C"]
        plan={"routes":routes,"tasks":{j:[starts[j],finishes[j]] for j in "ABC"},
              "return_times":{r:outer[f"end_{r}"] for r in ("R1","R2")},
              "energy_model":"zero_consumption; ample battery; no resource or cargo constraints"}
    objective_error=abs(objective-claimed)
    checks.append({"name":"independently_recomputed_objective","residual":objective_error,
                   "passed":objective_error<=OBJ_TOL*(1+abs(objective))})
    return {"passed":all(c["passed"] for c in checks),"checks":checks,"plan":plan,
            "recomputed_objective":objective,"max_constraint_residual":max(c["residual"] for c in checks
                                        if c["name"]!="independently_recomputed_objective")}


def digest(data):
    return hashlib.sha256(data).hexdigest()


def protected_hashes():
    paths = list((ROOT/"src/kaiti_planning").rglob("*.py"))
    paths += list((ROOT/"ros2_ws/src").rglob("*.py"))
    paths += list((ROOT/"configs").glob("planner*.yaml"))
    paths += list((ROOT/"configs").glob("public_space_v3*.yaml"))
    return {str(p.relative_to(ROOT)):digest(p.read_bytes()) for p in sorted(paths)}


def compare(case, results):
    statuses=[r["status"] for r in results]
    expected_status="INFEASIBLE" if case.expected is None else "OPTIMAL"
    if any(s in {"UNKNOWN_BUDGET","SOLVER_ERROR"} for s in statuses):
        return "UNKNOWN_BUDGET"
    valid=all(s==expected_status for s in statuses)
    if case.expected is not None:
        valid &= all(r.get("validation",{}).get("passed",False) and
                     abs(r.get("objective",float("inf"))-case.expected)<=OBJ_TOL*(1+abs(case.expected))
                     for r in results)
    return "PASS_EQUIVALENT" if valid else "FAIL_MODEL"


def branches(case):
    if case.family=="A":
        for sigma in (0,1):
            if case.sigma_fixed is not None and case.sigma_fixed!=sigma:
                continue
            expected=case.expected
            if case.name in ("A0","A1"):
                expected=29 if sigma==0 else 49
            if case.name=="A3" and sigma==0:
                expected=None
            yield replace(case,name=case.name+f"__sigma_{sigma}",sigma_fixed=sigma,expected=expected)
    else:
        for owner in ("R1","R2"):
            if case.owner_fixed and case.owner_fixed!=owner or case.only_r1 and owner!="R1":
                continue
            sequences=[(order,()) for order in itertools.permutations("ABC") if order.index("A")<order.index("B")] if owner=="R1" else [(("A","B"),("C",))]
            for n,seq in enumerate(sequences):
                feasible=seq==(("A","C","B"),()) if owner=="R1" else True
                yield replace(case,name=f"{case.name}__{owner}_order_{n}",owner_fixed=owner,sequence=seq,
                              expected=(0 if owner=="R1" else 1) if feasible else None)


def negative_checks(solved, runner):
    lookup={entry["case"]["name"]:entry for entry in solved}
    good=lookup["A0"]["methods"][0]
    checks=[]
    if not all(lookup[name]["methods"][0].get("validation",{}).get("passed") for name in ("A0","A3")):
        return [{"name":"negative_checks_preconditions","passed":False,"reason":"valid A0/A3 plan unavailable"}]
    def rejected(name,case,core,outer,objective):
        result=validate(case,core,outer,objective)
        checks.append({"name":name,"passed":not result["passed"],
                       "detected_by":[c["name"] for c in result["checks"] if not c["passed"]]})
    core=dict(good["core"]); core.update(u=104,v=96)
    rejected("independent_windows",cases()[0],core,good["outer"],38)
    rejected("missing_monitor_cost",cases()[0],good["core"],good["outer"],19)
    core=dict(good["core"]); core.update(u=95,v=95,sigma=1/200)
    rejected("fractional_resource_direction",cases()[3],core,good["outer"],28.05)
    outer=dict(good["outer"]); outer["E"]=26.5-.5*(outer["m"]-20)
    rejected("double_count_history_energy",cases()[0],good["core"],outer,29)
    outer=dict(good["outer"]); outer.update(m=80,E=16.5,hm=0)
    rejected("freeze_old_monitor_end",cases()[0],good["core"],outer,19)
    a3=lookup["A3"]["methods"][0]
    rejected("ignore_hard_deadline",cases()[4],a3["core"],a3["outer"],49)
    core=dict(good["core"]); core.update(d=94,u=99,v=100)
    outer={"m":94.,"E":9.5,"hm":14.}
    rejected("ignore_energy_boundary",cases()[5],core,outer,45)
    # These probes explicitly exercise phase-I certificates, including an energy
    # failure which may not be the first candidate in the optimization loop.
    for name,point in [("temporal_certificate",{"d":90.,"u":94.,"v":96.,"sigma":0.}),
                       ("energy_certificate",{"d":94.,"u":99.,"v":100.,"sigma":0.})]:
        cert=lp_extend(external(cases()[0]),point)
        checks.append({"name":name,"passed":cert["status"]=="INFEASIBLE" and cert["certificate_valid"],
                       "external":cert,"candidate":point})
    for name,case,expected in [("wrong_fixed_old_arc",cases()[6],"OPTIMAL"),
                               ("wrong_fixed_old_arc_single_capability",cases()[9],"INFEASIBLE")]:
        model,variables,cost=build_core(case)
        model += variables["a_R1_A_B"] == 1
        outer=add_external(model,variables,external(case))
        model += cost + expr(external(case).cost,outer)
        status=runner.cbc(model)
        objective=float(pulp.value(model.objective)) if status=="OPTIMAL" else None
        checks.append({"name":name,"status":status,"objective":objective,
                       "correct_model_objective":0,"cbc_log":f"cbc_logs/solve_{runner.calls:04d}.log",
                       "passed":status==expected and (objective is None or abs(objective-1)<=OBJ_TOL)})
    return checks


def projection_probes():
    """Finite boundary probes supplement, and do not replace, the analytic proof."""
    spec=external(cases()[0])
    results=[]
    for d in (90.,91.5,93.,94.):
        for u in (d+4,d+5,104.,110.):
            core={"d":d,"u":u,"v":105.,"sigma":0.}
            result=lp_extend(spec,core)
            expected=d<=93 and u>=d+5
            passed=(result["status"]=="OPTIMAL")==expected
            if expected:
                passed &= abs(result["objective"]-(d-80))<=OBJ_TOL
            results.append({"candidate":core,"expected_external_feasible":expected,
                            "passed":bool(passed),"external":result})
    return results


def markdown(report):
    lines=["# 独立小规模修复模型等价性实测", "",f"运行时间：{report['metadata']['started_at']}。",
           "", "三路：单体 MILP / 解析投影 / 逐次 LP 加割。未调用生产规划器或 ROS。", "",
           "| 算例 | 单体 | 投影 | 分解 | 最优值 | 完整验证 |", "|---|---|---|---|---:|---|"]
    for row in report["cases"]:
        methods=row["methods"]
        values=" / ".join(str(m.get("objective","—")) for m in methods)
        lines.append(f"| {row['case']['name']} | {methods[0]['status']} | {methods[1]['status']} | {methods[2]['status']} | {values} | {row['comparison']} |")
    lines += ["",f"固定结构分支：{len(report['branches'])}；通过：{sum(r['comparison']=='PASS_EQUIVALENT' for r in report['branches'])}。",
              f"负面/证书检查：{len(report['negative_checks'])}；通过：{sum(r['passed'] for r in report['negative_checks'])}。",
              f"外部投影边界探针：{len(report['projection_probes'])}；通过：{sum(r['passed'] for r in report['projection_probes'])}。",
              f"生产文件哈希保持：{report['protected_files_unchanged']}。", "",
              "完整输入、计划、约束残差、LP 对偶、逐轮割及软件版本见 results.json；CBC 原始日志见 cbc_logs/。",
              "本结果只验证指定小实例，不证明通用模型实现、扩展性、性能优势或学术新颖性。", ""]
    return "\n".join(lines)


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out-dir",type=Path,default=None)
    parser.add_argument("--time-limit",type=float,default=10.,help="Per CBC solve limit; not a real-time planner budget.")
    args=parser.parse_args()
    if not np.isfinite(args.time_limit) or args.time_limit<=0:
        parser.error("--time-limit must be positive")
    now=datetime.now(ZoneInfo("Asia/Shanghai"))
    out=args.out_dir or ROOT/"outputs/repair_equivalence"/now.strftime("%Y%m%d_%H%M%S_%f")
    out=out.resolve()
    out.mkdir(parents=True,exist_ok=False)
    (out/"cbc_logs").mkdir()
    (out/"script_snapshot.py").write_bytes(Path(__file__).read_bytes())
    before=protected_hashes()
    runner=Runner(out,args.time_limit)
    begin=perf_counter()
    report={"metadata":{"started_at":now.isoformat(),"python":sys.version,"platform":platform.platform(),
                        "pulp":pulp.__version__,"scipy":scipy.__version__,"numpy":np.__version__,
                        "cbc_path":pulp.PULP_CBC_CMD().path,"cbc_sha256":digest(Path(pulp.PULP_CBC_CMD().path).read_bytes()),
                        "script_sha256":digest(Path(__file__).read_bytes()),"per_cbc_limit":args.time_limit,
                        "cbc_threads":0,"cbc_random_seed":1,"cbc_branch_seed":1,
                        "specification_sha256":digest((ROOT/"docs/reviews/repair_unified_model_equivalence_design_2026-11-05.md").read_bytes()),
                        "tolerances":{"feasibility":FEAS_TOL,"objective_relative":OBJ_TOL}},
            "cases":[],"branches":[]}
    for case in cases():
        for scope,collection in [(case,report["cases"])]+[(b,report["branches"]) for b in branches(case)]:
            results=[runner.solve(scope,method) for method in ("monolithic","projection","decomposition")]
            comparison=compare(scope,results)
            collection.append({"case":asdict(scope),"comparison":comparison,"methods":results,
                               "external_specification":asdict(external(scope))})
            print(scope.name,comparison," / ".join(r["status"]+":"+str(r.get("objective","—")) for r in results),flush=True)
    report["negative_checks"]=negative_checks(report["cases"],runner)
    report["projection_probes"]=projection_probes()
    report["protected_file_hashes_before"]=before
    report["protected_file_hashes_after"]=protected_hashes()
    report["protected_files_unchanged"]=before==report["protected_file_hashes_after"]
    report["metadata"].update(runtime_seconds=perf_counter()-begin,cbc_calls=runner.calls)
    report["passed"]=(report["protected_files_unchanged"] and
                      all(x["comparison"]=="PASS_EQUIVALENT" for x in report["cases"]+report["branches"]) and
                      all(x["passed"] for x in report["negative_checks"]+report["projection_probes"]))
    (out/"results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    (out/"summary.md").write_text(markdown(report))
    print(json.dumps({"passed":report["passed"],"out_dir":str(out),"cbc_calls":runner.calls},ensure_ascii=False))
    return 0 if report["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())

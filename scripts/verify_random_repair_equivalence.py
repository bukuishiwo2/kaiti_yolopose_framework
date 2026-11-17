#!/usr/bin/env python3
"""Seeded, exhaustively enumerated small repair models, isolated from ROS/planners.

Shared resources are exclusive SERVICE equipment (pickup hatch / service bay),
not collision-free routes. Charging, optional tasks and monitor handoffs are not
implemented. Requires the same existing PuLP, NumPy and SciPy as the A/B harness.
"""
from __future__ import annotations

import argparse
from collections import Counter
from datetime import datetime
import hashlib
import itertools
import json
import math
from pathlib import Path
import platform
import random
import statistics
import sys
from time import perf_counter
from zoneinfo import ZoneInfo

import numpy as np
import pulp
import scipy

from verify_repair_equivalence import (
    External, Row, Runner, FEAS_TOL, OBJ_TOL, digest, lp_extend, protected_hashes,
)

ROOT = Path(__file__).resolve().parents[1]
WEIGHTS = dict(travel=.1, response=1., wait=.05, energy=.1,
               owner=2., adjacency=1., resource=1., time=.2, returning=.01)


def encode(value):
    return json.dumps(value, ensure_ascii=False, sort_keys=True, allow_nan=False)


def task_names(data):
    return list(data["tasks"])


def xkey(i, j):
    return f"x_{i}_{j}"


def akey(i, u, v):
    return f"a_{i}_{u}_{v}"


def arcs(data):
    tasks = task_names(data)
    for i in data["robots"]:
        for u in ["start"] + tasks:
            for v in tasks + ["end"]:
                if u != v:
                    yield i, u, v


def distance(p, q):
    return float(abs(p[0]-q[0]) + abs(p[1]-q[1]))


def travel(data, i, u, v):
    robot = data["robots"][i]
    p = robot["start"] if u == "start" else data["tasks"][u]["location"]
    q = robot["start"] if v == "end" else data["tasks"][v]["location"]
    return distance(p, q)


def make_instance(seed, nr, nt, masked):
    rng = random.Random(seed * 1000 + nr * 100 + nt)
    robots = {f"R{i}": {"start": [rng.randint(0, 4), rng.randint(0, 4)],
                         "move_rate": .2 + .05*i, "idle_rate": .03,
                         "minimum": 5., "capacity": 60., "initial": 50.}
              for i in range(nr)}
    tasks = {
        "M": {"location": [2, 2], "duration": None, "release": 0., "service_energy": 0.},
        "P": {"location": [rng.randint(4, 6), rng.randint(0, 2)],
              "duration": float(rng.randint(2, 4)), "release": float(rng.randint(0, 3))},
        "D": {"location": [2, 3], "duration": float(rng.randint(2, 4)), "release": 0.},
    }
    for n in range(nt-3):
        tasks[f"Q{n}"] = {"location": [rng.randint(0, 6), rng.randint(0, 6)],
                           "duration": float(rng.randint(1, 4)), "release": float(rng.randint(0, 6))}
    robots["R0"]["start"] = tasks["M"]["location"][:]
    for j, t in tasks.items():
        t["allowed"] = ["R0"] if j == "M" else (
            [f"R{i}" for i in range(1, nr)] if j in ("P", "D") else list(robots))
        t["service_energy"] = 0. if j == "M" else .3*t["duration"]
    data = {"seed": seed, "profile": f"{nr}r_{nt}t_{'masked' if masked else 'free'}",
            "robots": robots, "tasks": tasks, "monitor_rate": rng.choice([.2,.3,.4]),
            "monitor_minimum": float(rng.randint(1,3)), "masked": masked,
            "resource_pairs": [["P", "Q0"]] + ([["D", "Q1"]] if nt>=5 else []),
            "buffer": 1., "weights": WEIGHTS.copy()}
    owners = {"M":"R0", "P":"R1", "D":"R1"}
    for n in range(nt-3):
        owners[f"Q{n}"] = "R0" if nr == 2 or n % 2 else "R2"
    routes = {i: [] for i in robots}
    routes["R0"] = ["M"]
    routes["R1"] = ["P", "D"]
    for j in tasks:
        if j.startswith("Q"):
            routes[owners[j]].append(j)
    starts = {"M":0.}
    starts["P"] = max(tasks["P"]["release"], travel(data,"R1","start","P"))
    starts["D"] = starts["P"]+tasks["P"]["duration"]+travel(data,"R1","P","D")
    mend = max(data["monitor_minimum"], starts["D"]+tasks["D"]["duration"])
    finish = {"M":mend, "P":starts["P"]+tasks["P"]["duration"],
              "D":starts["D"]+tasks["D"]["duration"]}
    previous = {i:"start" for i in robots}
    previous.update(R0="M",R1="D")
    for j in tasks:
        if not j.startswith("Q"):
            continue
        i=owners[j]; u=previous[i]
        start=max(tasks[j]["release"], (0 if u=="start" else finish[u])+travel(data,i,u,j))
        for p,q in data["resource_pairs"]:
            if q==j:
                start=max(start,finish[p]+data["buffer"])
        starts[j]=start; finish[j]=start+tasks[j]["duration"]; previous[i]=j
    ends={i:(0 if not route else finish[route[-1]])+travel(data,i,route[-1] if route else "start","end")
          for i,route in routes.items()}
    horizon=float(math.ceil(max(ends.values())+15))
    data["horizon"]=horizon
    for j,t in tasks.items():
        t["deadline"] = horizon if j=="M" else finish[j]+rng.randint(7,14)
    data["reference"]={"owners":owners,"routes":routes,"starts":starts,"mend":mend,"ends":ends,
                       "resource_orders":[1]*len(data["resource_pairs"])}
    for i,robot in robots.items():
        consumed=0.; u="start"; f=0.
        for j in routes[i]+["end"]:
            s=ends[i] if j=="end" else starts[j]
            tau=travel(data,i,u,j)
            consumed+=robot["move_rate"]*tau+robot["idle_rate"]*(s-f-tau)
            if j!="end":
                consumed+=data["monitor_rate"]*mend if j=="M" else tasks[j]["service_energy"]
            f=s if j=="end" else finish[j]; u=j
        robot["initial"]=robot["minimum"]+consumed+rng.randint(3,7)
        robot["capacity"]=max(60.,float(math.ceil(robot["initial"]+5)))
        robot["reference_consumption"]=consumed
    return data


def variants(base):
    for mode in ("nominal","energy_limited","deadline_infeasible"):
        d=json.loads(encode(base)); d["mode"]=mode
        if mode=="energy_limited":
            for robot in d["robots"].values():
                robot["initial"]=robot["minimum"]+robot["reference_consumption"]+.25
        if mode=="deadline_infeasible":
            d["tasks"]["D"]["deadline"]=(d["tasks"]["P"]["release"]+d["tasks"]["P"]["duration"]+
                travel(d,"R1","P","D")+d["tasks"]["D"]["duration"]-.5)
        d["name"]=f"seed{d['seed']}_{d['profile']}_{mode}"
        yield d
    if len(base["robots"])==2:
        d=json.loads(encode(base));d["mode"]="energy_infeasible"
        d["robots"]["R0"]["initial"]=5+data_monitor_min_draw(d)/2
        d["name"]=f"seed{d['seed']}_{d['profile']}_energy_infeasible"
        yield d


def data_monitor_min_draw(data):
    return data["monitor_minimum"]*data["monitor_rate"]


def structures(data):
    """Exhaust ALL allowed owners, robot permutations and resource directions.

    Only structural requirements filter entries: ability, pickup/delivery owner,
    monitor first, pickup before delivery and masked exterior subsequences.
    No deadline, resource timing or battery feasibility oracle is used here.
    """
    qs=[j for j in data["tasks"] if j.startswith("Q")]
    domains=[[data["reference"]["owners"][q]] if data["masked"] else data["tasks"][q]["allowed"] for q in qs]
    for courier in data["tasks"]["P"]["allowed"]:
        for assignment in itertools.product(*domains):
            owners={"M":"R0","P":courier,"D":courier,**dict(zip(qs,assignment))}
            choices=[]
            for i in data["robots"]:
                jobs=[j for j in data["tasks"] if owners[j]==i]
                perms=[]
                for seq in itertools.permutations(jobs):
                    if "M" in seq and seq[0]!="M":
                        continue
                    if "P" in seq and seq.index("P")>seq.index("D"):
                        continue
                    if data["masked"]:
                        frozen=[j for j in data["reference"]["routes"][i] if j.startswith("Q")]
                        if [j for j in seq if j in frozen]!=frozen:
                            continue
                    perms.append(list(seq))
                choices.append(perms)
            for routes in itertools.product(*choices):
                for orders in itertools.product((0,1),repeat=len(data["resource_pairs"])):
                    yield {"owners":owners,"routes":dict(zip(data["robots"],routes)),"orders":list(orders)}


def template(data):
    """A single static linear row catalogue shared by both formulations."""
    core_bounds={}; binaries=set(); outer_names=["m","mh"]
    rows=[]; outer_cost={"mh":data["weights"]["time"]}; local={}; constant=0.
    h=data["horizon"]; w=data["weights"]
    for i in data["robots"]:
        for j in data["tasks"]:
            key=xkey(i,j);core_bounds[key]=(0,1);binaries.add(key)
        core_bounds[f"end_{i}"]=(0,h)
        local[f"end_{i}"]=w["returning"]
        outer_names.append(f"Eend_{i}");outer_cost[f"Eend_{i}"]=-w["energy"]
        constant+=w["energy"]*data["robots"][i]["initial"]
        for j in data["tasks"]:
            outer_names.extend([f"Bpre_{i}_{j}",f"Bpost_{i}_{j}"])
    for j in data["tasks"]:
        core_bounds[f"s_{j}"]=(0,h)
        if j!="M":
            core_bounds[f"shift_{j}"]=(0,h)
            local[f"shift_{j}"]=2*w["time"]
        constant+=w["owner"];local[xkey(data["reference"]["owners"][j],j)]=-w["owner"]
    for n,old in enumerate(data["reference"]["resource_orders"]):
        key=f"order_{n}";core_bounds[key]=(0,1);binaries.add(key)
        local[key]=w["resource"]*(-1 if old else 1);constant+=w["resource"]*old
    outer_set=set(outer_names)
    mt=4*h+4*max(travel(data,i,u,v) for i,u,v in arcs(data))+10
    me=4*max(r["capacity"] for r in data["robots"].values())+4*h+10

    def add(name,coeff,rhs=0.):
        coeff={k:float(c) for k,c in coeff.items() if c}
        rows.append(Row(name,{k:c for k,c in coeff.items() if k in outer_set},float(rhs),
                        {k:-c for k,c in coeff.items() if k not in outer_set}))

    def implied(name,coeff,rhs,selector,M):
        coeff=coeff.copy();coeff[selector]=coeff.get(selector,0)-M
        add(name,coeff,rhs-M)

    def equality(name,coeff,rhs=0.,selector=None,M=0.):
        if selector is None:
            add(name+"_ge",coeff,rhs);add(name+"_le",{k:-c for k,c in coeff.items()},-rhs)
        else:
            implied(name+"_ge",coeff,rhs,selector,M)
            implied(name+"_le",{k:-c for k,c in coeff.items()},-rhs,selector,M)

    def bound(name,lo,hi):
        add(name+"_lower",{name:1},lo);add(name+"_upper",{name:-1},-hi)

    def start(node,i):
        return {} if node=="start" else {f"end_{i}" if node=="end" else f"s_{node}":1}

    def finish(node):
        if node=="start":
            return {},0.
        if node=="M":
            return {"m":1},0.
        return {f"s_{node}":1},data["tasks"][node]["duration"]

    bound("m",data["monitor_minimum"],h);bound("mh",0,h)
    add("monitor_cover",{"m":1,"s_D":-1},data["tasks"]["D"]["duration"])
    add("monitor_shift_positive",{"mh":1,"m":-1},-data["reference"]["mend"])
    add("monitor_shift_negative",{"mh":1,"m":1},data["reference"]["mend"])
    for j,t in data["tasks"].items():
        add(j+"_release",{f"s_{j}":1},t["release"])
        if j=="M":
            equality("monitor_continuation_start",{"s_M":1})
        else:
            add(j+"_deadline",{f"s_{j}":-1},t["duration"]-t["deadline"])
            add(j+"_shift_pos",{f"shift_{j}":1,f"s_{j}":-1},-data["reference"]["starts"][j])
            add(j+"_shift_neg",{f"shift_{j}":1,f"s_{j}":1},data["reference"]["starts"][j])
    add("pickup_before_delivery",{"s_D":1,"s_P":-1},data["tasks"]["P"]["duration"])
    local["s_P"]=w["response"];local["s_D"]=w["response"]
    constant+=w["response"]*data["tasks"]["D"]["duration"]
    for n,(p,q) in enumerate(data["resource_pairs"]):
        implied(f"resource_{n}_p_first",{f"s_{q}":1,f"s_{p}":-1},data["tasks"][p]["duration"]+data["buffer"],f"order_{n}",mt)
        # order=0 activates q first, so add its big-M form directly.
        add(f"resource_{n}_q_first",{f"s_{p}":1,f"s_{q}":-1,f"order_{n}":mt},
            data["tasks"][q]["duration"]+data["buffer"])
    for i,robot in data["robots"].items():
        bound(f"Eend_{i}",robot["minimum"],robot["capacity"])
        for j,t in data["tasks"].items():
            key=xkey(i,j)
            for prefix in ("Bpre","Bpost"):
                e=f"{prefix}_{i}_{j}"
                add(e+"_safe",{e:1,key:-robot["minimum"]})
                add(e+"_capacity",{e:-1,key:robot["capacity"]})
            coeff={f"Bpost_{i}_{j}":1,f"Bpre_{i}_{j}":-1}
            cost=t["service_energy"]
            if j=="M":
                coeff["m"]=data["monitor_rate"]
            equality(f"service_energy_{i}_{j}",coeff,-cost,key,me)
    for i,u,v in arcs(data):
        a=akey(i,u,v);hk=f"wait_{i}_{u}_{v}"
        core_bounds[a]=(0,1);binaries.add(a);core_bounds[hk]=(0,h)
        tau=travel(data,i,u,v);f,fd=finish(u);s=start(v,i)
        timing=s.copy()
        for k,c in f.items():timing[k]=timing.get(k,0)-c
        implied("time_"+a,timing,tau+fd,a,mt)
        gap={hk:1}
        for k,c in timing.items():gap[k]=gap.get(k,0)-c
        equality("wait_"+a,gap,-tau-fd,a,mt)
        add("wait_selection_"+a,{hk:-1,a:h})
        local[a]=local.get(a,0)+w["travel"]*tau;local[hk]=w["wait"]
        robot=data["robots"][i]
        energy={f"Eend_{i}" if v=="end" else f"Bpre_{i}_{v}":1}
        source=robot["initial"] if u=="start" else 0.
        if u!="start":energy[f"Bpost_{i}_{u}"]=-1
        for k,c in timing.items():energy[k]=energy.get(k,0)+robot["idle_rate"]*c
        rhs=source-(robot["move_rate"]-robot["idle_rate"])*tau+robot["idle_rate"]*fd
        equality("travel_energy_"+a,energy,rhs,a,me)
    for i,route in data["reference"]["routes"].items():
        chain=["start"]+route+["end"]
        for u,v in zip(chain,chain[1:]):
            local[akey(i,u,v)]=local.get(akey(i,u,v),0)-w["adjacency"]
            constant+=w["adjacency"]
    spec=External(outer_names,outer_cost,[])
    pure=[]
    for row in rows:
        (spec.rows if row.outer else pure).append(row)
    return {"bounds":core_bounds,"binaries":binaries,"pure":pure,"external":spec,
            "local_cost":local,"constant":constant,"mt":mt,"me":me}


def expression(coeff,v):
    return pulp.lpSum(c*v[k] for k,c in coeff.items())


def build_master(data,tpl,structure=None):
    model=pulp.LpProblem("seeded_repair",pulp.LpMinimize)
    v={k:pulp.LpVariable(k,lo,hi,cat="Binary" if k in tpl["binaries"] else "Continuous")
       for k,(lo,hi) in tpl["bounds"].items()}
    jobs=task_names(data);n=len(jobs)
    rank={(i,j):pulp.LpVariable(f"rank_{i}_{j}",0,n) for i in data["robots"] for j in jobs}
    for j in jobs:
        model+=sum(v[xkey(i,j)] for i in data["robots"])==1
        for i in data["robots"]:
            if i not in data["tasks"][j]["allowed"]:
                model+=v[xkey(i,j)]==0
            if data["masked"] and j.startswith("Q"):
                model+=v[xkey(i,j)]==int(data["reference"]["owners"][j]==i)
    for i in data["robots"]:
        model+=v[xkey(i,"P")]==v[xkey(i,"D")]
        model+=sum(v[akey(i,u,w)] for ii,u,w in arcs(data) if ii==i and u=="start")==1
        model+=sum(v[akey(i,u,w)] for ii,u,w in arcs(data) if ii==i and w=="end")==1
        for j in jobs:
            model+=sum(v[akey(i,u,w)] for ii,u,w in arcs(data) if ii==i and w==j)==v[xkey(i,j)]
            model+=sum(v[akey(i,u,w)] for ii,u,w in arcs(data) if ii==i and u==j)==v[xkey(i,j)]
            model+=rank[i,j]>=v[xkey(i,j)];model+=rank[i,j]<=n*v[xkey(i,j)]
        for ii,u,w in arcs(data):
            if ii==i and u in jobs and w in jobs:
                model+=rank[i,w]>=rank[i,u]+1-(n+1)*(1-v[akey(i,u,w)])
        if data["masked"]:
            frozen=[j for j in data["reference"]["routes"][i] if j.startswith("Q")]
            for u,w in zip(frozen,frozen[1:]):model+=rank[i,w]>=rank[i,u]+1
    model+=v[akey("R0","start","M")]==1
    for row in tpl["pure"]:
        model+=0>=row.rhs+expression(row.core,v),row.name
    if structure:
        for j,owner in structure["owners"].items():model+=v[xkey(owner,j)]==1
        for i,route in structure["routes"].items():
            chain=["start"]+route+["end"]
            for u,w in zip(chain,chain[1:]):model+=v[akey(i,u,w)]==1
        for n,value in enumerate(structure["orders"]):model+=v[f"order_{n}"]==value
    return model,v


def solve(data,tpl,runner,method,structure,budget,max_iterations):
    begin=perf_counter();before=runner.calls
    model,v=build_master(data,tpl,structure);spec=tpl["external"]
    local=expression(tpl["local_cost"],v)+tpl["constant"]
    result={"method":method,"trace":[]}
    times={"build":0.,"cbc":0.,"external_lp":0.,"validation":0.}
    def cbc():
        remaining=budget-(perf_counter()-begin)
        if remaining<=0:return "UNKNOWN_BUDGET"
        runner.time_limit=min(5.,remaining)
        t=perf_counter();status=runner.cbc(model);times["cbc"]+=perf_counter()-t
        return status
    if method=="monolithic":
        z={k:pulp.LpVariable(k,lowBound=None) for k in spec.names}
        for row in spec.rows:
            model+=expression(row.outer,z)>=row.rhs+expression(row.core,v),row.name
        model+=local+expression(spec.cost,z)
        times["build"]=perf_counter()-begin
        status=cbc()
        if status=="OPTIMAL":
            result.update(core={k:float(a.value()) for k,a in v.items()},
                          outer={k:float(a.value()) for k,a in z.items()},objective=float(pulp.value(model.objective)))
    else:
        theta=pulp.LpVariable("theta",lowBound=-data["weights"]["energy"]*sum(r["capacity"] for r in data["robots"].values()))
        model+=local+theta
        times["build"]=perf_counter()-begin
        seen=set();status="UNKNOWN_BUDGET"
        for iteration in range(max_iterations):
            status=cbc()
            if status!="OPTIMAL":break
            core={k:float(a.value()) for k,a in v.items()}
            t=perf_counter();outer=lp_extend(spec,core);times["external_lp"]+=perf_counter()-t
            dual=outer["certificate"]
            const=sum(c*row.rhs for c,row in zip(dual,spec.rows))
            coeff={k:sum(c*row.core.get(k,0) for c,row in zip(dual,spec.rows)) for k in v}
            coeff={k:c for k,c in coeff.items() if abs(c)>1e-12}
            trace={"iteration":iteration+1,"status":outer["status"],
                   "candidate_core":{k:c for k,c in core.items() if abs(c)>1e-12},
                   "theta":float(theta.value()),
                   "certificate_support":[[n,float(c)] for n,c in enumerate(dual) if abs(c)>1e-12],
                   "stationarity_residual":outer["stationarity_residual"],
                   "certificate_value":outer["certificate_value"],
                   "certificate_valid":outer["certificate_valid"],
                   "lower_bound":float(pulp.value(model.objective))}
            if "phase_one_objective" in outer:
                trace["phase_one_objective"]=outer["phase_one_objective"]
            if outer["status"]=="OPTIMAL":
                upper=float(pulp.value(local))+outer["objective"]
                gap=upper-trace["lower_bound"]
                trace.update(upper_bound=upper,gap=gap,duality_gap=outer["duality_gap"])
                if gap < -OBJ_TOL*(1+abs(upper)):raise RuntimeError("Negative decomposition gap")
                if gap<=OBJ_TOL*(1+abs(upper)):
                    result["trace"].append(trace)
                    result.update(core=core,outer=outer["outer"],objective=upper,
                                  lower_bound=trace["lower_bound"],upper_bound=upper)
                    break
                kind="optimality";model+=theta>=const+expression(coeff,v)
            else:
                kind="feasibility";model+=const+expression(coeff,v)<=0
            key=encode([kind,round(const,8),{k:round(c,8) for k,c in sorted(coeff.items())}])
            if key in seen:raise RuntimeError("Repeated violated cut")
            seen.add(key);trace["cut"]={"kind":kind,"constant":const,"coefficients":coeff}
            result["trace"].append(trace)
        else:status="UNKNOWN_BUDGET"
    if status=="OPTIMAL" and "core" not in result:status="UNKNOWN_BUDGET"
    result["status"]=status
    if status=="OPTIMAL":
        t=perf_counter();result["validation"]=validate(data,result["core"],result["outer"],result["objective"],structure)
        times["validation"]=perf_counter()-t
        # Complete input+structure reconstructs all inactive variables. Keep the
        # chosen solution sparse to avoid duplicating thousands of zero arcs.
        result["core"]={k:c for k,c in result["core"].items() if abs(c)>1e-12}
    result.update(timing_seconds={**times,"total":perf_counter()-begin},
                  cbc_logs=[f"cbc_logs/solve_{n:04d}.log" for n in range(before+1,runner.calls+1)])
    return result


def validate(data,core,outer,claimed,scope=None):
    """Reconstruct routes and resource/energy physics WITHOUT using template rows."""
    failures=[];counts=Counter();max_residual=0.
    def check(group,name,residual):
        nonlocal max_residual
        residual=float(max(0,residual));max_residual=max(max_residual,residual);counts[group]+=1
        if residual>FEAS_TOL:failures.append({"group":group,"name":name,"residual":residual})
    def eq(g,n,a,b):check(g,n,abs(a-b))
    def ge(g,n,a,b):check(g,n,b-a)
    def binary(n,value):
        eq("integrality",n,value,round(value));ge("integrality",n+"_lower",value,0);ge("integrality",n+"_upper",1,value)
    tasks=data["tasks"];h=data["horizon"]
    starts={j:core[f"s_{j}"] for j in tasks}
    finishes={j:outer["m"] if j=="M" else starts[j]+t["duration"] for j,t in tasks.items()}
    owners={};routes={};consumed={};selected_arcs=[]
    for j,t in tasks.items():
        eq("assignment",j,sum(core[xkey(i,j)] for i in data["robots"]),1)
        selected=[i for i in data["robots"] if core[xkey(i,j)]>.5]
        if len(selected)!=1:raise RuntimeError("Invalid assignment reconstruction")
        owners[j]=selected[0]
        eq("capability",j,int(owners[j] in t["allowed"]),1)
        for i in data["robots"]:binary(xkey(i,j),core[xkey(i,j)])
        ge("time",j+"_release",starts[j],t["release"]);ge("time",j+"_horizon",h,finishes[j])
        ge("time",j+"_start",starts[j],0);ge("time",j+"_duration",finishes[j],starts[j])
        if j!="M":
            ge("deadline",j,t["deadline"],finishes[j])
            shift=core[f"shift_{j}"];delta=starts[j]-data["reference"]["starts"][j]
            ge("epigraph",j+"_positive",shift,delta);ge("epigraph",j+"_negative",shift,-delta)
            ge("epigraph",j+"_lower",shift,0);ge("epigraph",j+"_upper",h,shift)
    eq("execution","monitor_start",starts["M"],0);eq("execution","monitor_owner",int(owners["M"]=="R0"),1)
    ge("monitor","minimum",finishes["M"],data["monitor_minimum"])
    ge("monitor","cover_delivery",finishes["M"],finishes["D"])
    ge("monitor","cover_pickup_start",starts["P"],starts["M"])
    eq("cargo","same_owner",int(owners["P"]==owners["D"]),1)
    ge("precedence","pickup_before_delivery",starts["D"],finishes["P"])
    delta=finishes["M"]-data["reference"]["mend"]
    ge("epigraph","monitor_positive",outer["mh"],delta);ge("epigraph","monitor_negative",outer["mh"],-delta)
    ge("epigraph","monitor_lower",outer["mh"],0);ge("epigraph","monitor_upper",h,outer["mh"])
    for i,robot in data["robots"].items():
        pairs=[(u,v) for ii,u,v in arcs(data) if ii==i and core[akey(i,u,v)]>.5]
        for ii,u,v in arcs(data):
            if ii==i:binary(akey(i,u,v),core[akey(i,u,v)])
        eq("flow",i+"_source",sum(u=="start" for u,v in pairs),1)
        eq("flow",i+"_sink",sum(v=="end" for u,v in pairs),1)
        for j in tasks:
            eq("flow",i+j+"_in",sum(v==j for u,v in pairs),core[xkey(i,j)])
            eq("flow",i+j+"_out",sum(u==j for u,v in pairs),core[xkey(i,j)])
        path=[];node="start";seen=set()
        for _ in range(len(tasks)+2):
            nxt=[v for u,v in pairs if u==node]
            if len(nxt)!=1:break
            dest=nxt[0]
            if dest=="end":node=dest;break
            if dest in seen:break
            path.append(dest);seen.add(dest);node=dest
        eq("flow",i+"_reaches_end",int(node=="end"),1)
        eq("flow",i+"_connected",len(path),sum(core[xkey(i,j)] for j in tasks))
        if i=="R0":eq("execution","monitor_first",int(bool(path) and path[0]=="M"),1)
        routes[i]=path
        if data["masked"]:
            old=[j for j in data["reference"]["routes"][i] if j.startswith("Q")]
            eq("scope",i+"_subsequence",int([j for j in path if j.startswith("Q")]==old),1)
        if scope:
            eq("scope",i+"_fixed_route",int(path==scope["routes"][i]),1)
        energy=robot["initial"];previous="start";last_finish=0.;draw=0.
        ge("energy",i+"_initial_safe",energy,robot["minimum"])
        ge("energy",i+"_initial_capacity",robot["capacity"],energy)
        for j in path+["end"]:
            s=core[f"end_{i}"] if j=="end" else starts[j]
            tau=travel(data,i,previous,j);wait=s-last_finish-tau
            ge("travel",i+previous+j,s,last_finish+tau)
            eq("waiting",i+previous+j,core[f"wait_{i}_{previous}_{j}"],wait)
            amount=robot["move_rate"]*tau+robot["idle_rate"]*wait
            energy-=amount;draw+=amount;selected_arcs.append(akey(i,previous,j))
            if j=="end":eq("energy",i+"_end",outer[f"Eend_{i}"],energy)
            else:
                eq("energy",i+j+"_pre",outer[f"Bpre_{i}_{j}"],energy)
                ge("energy",i+j+"_pre_safe",energy,robot["minimum"])
                ge("energy",i+j+"_pre_capacity",robot["capacity"],energy)
                amount=data["monitor_rate"]*(finishes[j]-s) if j=="M" else tasks[j]["service_energy"]
                energy-=amount;draw+=amount
                eq("energy",i+j+"_post",outer[f"Bpost_{i}_{j}"],energy)
            ge("energy",i+j+"_safe",energy,robot["minimum"]);ge("energy",i+j+"_capacity",robot["capacity"],energy)
            last_finish=s if j=="end" else finishes[j];previous=j
        ge("time",i+"_return",h,core[f"end_{i}"]);consumed[i]=draw
        for j in tasks:
            if owners[j]!=i:
                eq("energy",i+j+"_inactive_pre",outer[f"Bpre_{i}_{j}"],0)
                eq("energy",i+j+"_inactive_post",outer[f"Bpost_{i}_{j}"],0)
    for i,u,v in arcs(data):
        if akey(i,u,v) not in selected_arcs:eq("waiting",akey(i,u,v)+"_inactive",core[f"wait_{i}_{u}_{v}"],0)
    orders=[]
    for n,(p,q) in enumerate(data["resource_pairs"]):
        z=core[f"order_{n}"];binary(f"order_{n}",z)
        ge("resource",str(n),starts[q] if round(z) else starts[p],
           (finishes[p] if round(z) else finishes[q])+data["buffer"])
        orders.append(int(round(z)))
        if scope:eq("scope",f"resource_{n}",z,scope["orders"][n])
    if scope:
        for j,i in scope["owners"].items():eq("scope",j+"_owner",int(owners[j]==i),1)
    parts=objective_parts(data,owners,routes,orders,starts,finishes,core,consumed)
    full=sum(parts.values());error=abs(full-claimed)
    passed=not failures and error<=OBJ_TOL*(1+abs(full))
    return {"passed":bool(passed),"check_counts":dict(counts),"max_constraint_residual":max_residual,
            "failures":failures,"objective_error":error,"objective_parts":parts,
            "plan":{"owners":owners,"routes":routes,"starts":starts,"finishes":finishes,
                    "resource_orders":orders,"returns":{i:core[f"end_{i}"] for i in routes},
                    "energy_used":consumed,"energy_end":{i:outer[f"Eend_{i}"] for i in routes}}}


def objective_parts(data,owners,routes,orders,starts,finishes,core,consumed):
    w=data["weights"];ref=data["reference"];chosen=set();travel_sum=0.;waiting=0.
    for i,route in routes.items():
        chain=["start"]+route+["end"]
        for u,v in zip(chain,chain[1:]):
            chosen.add((i,u,v));tau=travel(data,i,u,v);travel_sum+=tau
            waiting+=(core[f"end_{i}"] if v=="end" else starts[v])-(0 if u=="start" else finishes[u])-tau
    broken=0
    for i,route in ref["routes"].items():
        chain=["start"]+route+["end"]
        broken+=sum((i,u,v) not in chosen for u,v in zip(chain,chain[1:]))
    return {"travel":w["travel"]*travel_sum,"response":w["response"]*(starts["P"]+finishes["D"]),
            "wait":w["wait"]*waiting,"energy":w["energy"]*sum(consumed.values()),
            "owner":w["owner"]*sum(owners[j]!=ref["owners"][j] for j in owners),
            "adjacency":w["adjacency"]*broken,
            "resource":w["resource"]*sum(a!=b for a,b in zip(orders,ref["resource_orders"])),
            "time":w["time"]*(2*sum(abs(starts[j]-ref["starts"][j]) for j in starts if j!="M")+
                                    abs(finishes["M"]-ref["mend"])),
            "returning":w["returning"]*sum(core[f"end_{i}"] for i in routes)}


def compare(results):
    if any(r["status"] not in ("OPTIMAL","INFEASIBLE") for r in results):return "UNKNOWN_BUDGET"
    if results[0]["status"]!=results[1]["status"]:return "FAIL_MODEL"
    if results[0]["status"]=="INFEASIBLE":return "PASS_EQUIVALENT"
    a,b=results
    ok=all(r["validation"]["passed"] for r in results) and abs(a["objective"]-b["objective"])<=OBJ_TOL*(1+abs(a["objective"]))
    return "PASS_EQUIVALENT" if ok else "FAIL_MODEL"


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds",nargs="+",type=int,default=[7,19,43])
    p.add_argument("--out-dir",type=Path)
    p.add_argument("--budget",type=float,default=30.,help="Soft method/scope budget checked before CBC; actual LP/total time is recorded.")
    p.add_argument("--max-iterations",type=int,default=200)
    p.add_argument("--quick",action="store_true",help="Only 2-robot/4-task profile, all variants and structures.")
    args=p.parse_args()
    if not math.isfinite(args.budget) or args.budget<=0 or args.max_iterations<1:p.error("positive budgets required")
    now=datetime.now(ZoneInfo("Asia/Shanghai"))
    out=(args.out_dir or ROOT/"outputs/random_repair_equivalence"/now.strftime("%Y%m%d_%H%M%S_%f")).resolve()
    out.mkdir(parents=True,exist_ok=False);(out/"cbc_logs").mkdir();(out/"instances").mkdir()
    (out/"script_snapshot.py").write_bytes(Path(__file__).read_bytes())
    helper=Path(__file__).with_name("verify_repair_equivalence.py")
    (out/"verify_repair_equivalence.py").write_bytes(helper.read_bytes())
    before=protected_hashes();runner=Runner(out,5.)
    metadata={"started_at":now.isoformat(),"seeds":args.seeds,"python":sys.version,"platform":platform.platform(),
              "pulp":pulp.__version__,"scipy":scipy.__version__,"numpy":np.__version__,
              "cbc_threads":0,"cbc_random_seed":1,"cbc_branch_seed":1,"budget_per_method":args.budget,
              "script_sha256":digest(Path(__file__).read_bytes()),"helper_sha256":digest(helper.read_bytes()),
              "solver_sha256":digest(Path(pulp.PULP_CBC_CMD().path).read_bytes()),
              "constraints":"service-resource model; no charging or geometric collision planning"}
    warm_start=perf_counter()
    warm=lp_extend(External(["z"],{"z":1},[Row("lower",{"z":1},1,{}),Row("upper",{"z":-1},-2,{})]),{})
    if warm["status"]!="OPTIMAL" or abs(warm["objective"]-1)>FEAS_TOL:raise RuntimeError("LP warmup failed")
    warm_model=pulp.LpProblem("warmup",pulp.LpMinimize);warm_var=pulp.LpVariable("w",cat="Binary")
    warm_model+=warm_var;warm_model+=warm_var>=.5
    if runner.cbc(warm_model)!="OPTIMAL":raise RuntimeError("CBC warmup failed")
    metadata["warmup_seconds"]=perf_counter()-warm_start
    metadata["warmup_log"]="cbc_logs/solve_0001.log"
    summaries=[];all_times={m:[] for m in ("monolithic","decomposition")};begin=perf_counter()
    profiles=[(2,4,False)] if args.quick else [(2,4,False),(3,5,False),(3,6,True)]
    with (out/"structures.jsonl").open("x") as stream:
        for seed in args.seeds:
            for nr,nt,masked in profiles:
                for data in variants(make_instance(seed,nr,nt,masked)):
                    t=perf_counter();tpl=template(data);generation=perf_counter()-t
                    inventory=list(structures(data));name=data["name"]
                    (out/"instances"/(name+".json")).write_text(encode(data)+"\n")
                    spec=tpl["external"]
                    spec_data={"names":spec.names,"cost":spec.cost,"rows":[vars(row) for row in spec.rows]}
                    (out/"instances"/(name+"_external.json")).write_text(encode(spec_data)+"\n")
                    entry={"name":name,"seed":seed,"robots":nr,"tasks":nt,"masked":masked,"mode":data["mode"],
                           "instance_hash":digest(encode(data).encode()),"external_hash":digest(encode(spec_data).encode()),
                           "template_seconds":generation,"enumerated_structures":len(inventory),"counts":{},"models":{}}
                    main_results=[solve(data,tpl,runner,m,None,args.budget,args.max_iterations) for m in all_times]
                    entry["unfixed_results"]=main_results;entry["unfixed_comparison"]=compare(main_results)
                    counts=Counter();feasible_objectives=[];method_best={m:[] for m in all_times}
                    timings={m:[] for m in all_times};maxres=0.;check_total=Counter()
                    for n,structure in enumerate(inventory):
                        method_order=list(all_times) if n%2==0 else list(reversed(all_times))
                        result_map={m:solve(data,tpl,runner,m,structure,args.budget,args.max_iterations) for m in method_order}
                        ordered=[result_map[m] for m in all_times];verdict=compare(ordered)
                        counts[verdict]+=1;counts[ordered[0]["status"]]+=1
                        for m,r in result_map.items():
                            timings[m].append(r["timing_seconds"]["total"]);all_times[m].append(r["timing_seconds"]["total"])
                            if r["status"]=="OPTIMAL":
                                method_best[m].append(r["objective"])
                                check_total.update(r["validation"]["check_counts"])
                                maxres=max(maxres,r["validation"]["max_constraint_residual"])
                        stream.write(encode({"instance":name,"instance_hash":entry["instance_hash"],"structure_id":n,
                                             "structure":structure,"execution_order":method_order,
                                             "comparison":verdict,"methods":ordered})+"\n")
                        if (n+1)%80==0:
                            stream.flush();print(name,f"structures {n+1}/{len(inventory)}",flush=True)
                    entry["counts"]=dict(counts);entry["constraint_checks"]=dict(check_total);entry["max_residual"]=maxres
                    entry["enumerated_optima"]={m:min(v) if v else None for m,v in method_best.items()}
                    entry["timing_seconds"]={m:{"sum":sum(v),"median":statistics.median(v),"p95":float(np.percentile(v,95)),"count":len(v)} for m,v in timings.items()}
                    entry["enumeration_matches_unfixed"]=all(
                        ((r["status"]=="INFEASIBLE" and not method_best[r["method"]]) or
                         (r["status"]=="OPTIMAL" and method_best[r["method"]] and
                          abs(r["objective"]-min(method_best[r["method"]]))<=OBJ_TOL*(1+abs(r["objective"]))))
                        for r in main_results)
                    entry["control_expectation_passed"]=all(r["status"]==("INFEASIBLE" if data["mode"].endswith("infeasible") else "OPTIMAL") for r in main_results)
                    entry["passed"]=(entry["unfixed_comparison"]=="PASS_EQUIVALENT" and
                        counts["PASS_EQUIVALENT"]==len(inventory) and entry["enumeration_matches_unfixed"] and entry["control_expectation_passed"])
                    summaries.append(entry)
                    (out/"progress.json").write_text(encode(summaries)+"\n")
                    stream.flush()
                    print(name,"PASS" if entry["passed"] else "FAIL",dict(counts),flush=True)
    after=protected_hashes()
    report={"metadata":metadata,"instances":summaries,"protected_before":before,"protected_after":after,
            "protected_files_unchanged":before==after,"cbc_calls":runner.calls,"runtime_seconds":perf_counter()-begin}
    report["passed"]=before==after and all(x["passed"] for x in summaries)
    report["aggregate_timing_seconds"]={m:{"median":statistics.median(v),"p95":float(np.percentile(v,95)),"sum":sum(v),"count":len(v)} for m,v in all_times.items()}
    (out/"results.json").write_text(json.dumps(report,ensure_ascii=False,indent=2,allow_nan=False)+"\n")
    print(encode({"passed":report["passed"],"out_dir":str(out),"instances":len(summaries),
                  "structures":sum(x["enumerated_structures"] for x in summaries)}))
    return 0 if report["passed"] else 1


if __name__=="__main__":
    raise SystemExit(main())

"""Common deterministic MILP and LP decomposition for isolated DES experiments.

The service resource model does not provide continuous motion collision safety.
Every incumbent penalty is shared across all policies. Active ordinary work is
advanced through an immutable prefix in the input robot source state.
"""
from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from time import perf_counter

import numpy as np
import pulp
from scipy.optimize import linprog

TOL = 1e-6
WEIGHTS = {"travel": .1, "normal_delay": .1, "response": 1., "wait": .01,
           "energy": .1, "owner": 2., "shift": .25, "adjacency": 1., "return": .01}


def ak(i, u, v):
    return f"a_{i}_{u}_{v}"


def xk(i, j):
    return f"x_{i}_{j}"


def arcs(p):
    for i in p["robots"]:
        for u in ["src"] + list(p["tasks"]):
            for v in list(p["tasks"]) + ["end"]:
                if u != v:
                    yield i, u, v


def tau(p, i, u, v):
    """Clinic fixed-map path prior; used by model, objective and validation alike."""
    a = p["robots"][i]["source_anchor"] if u == "src" else p["tasks"][u]["anchor"]
    b = p["robots"][i]["home_anchor"] if v == "end" else p["tasks"][v]["anchor"]
    return float(p["travel_times"][a][b])


@dataclass
class Row:
    name: str
    coefficients: dict[str, float]
    rhs: float


class Model:
    def __init__(self, p):
        self.p = p
        self.bounds = {}
        self.binary = set()
        self.outer = set()
        self.rows = []
        self.cost = {}
        self.constant = 0.
        self.pairs = []
        self._build()

    def var(self, name, lo, hi, binary=False, outer=False):
        self.bounds[name] = (float(lo), float(hi))
        if binary: self.binary.add(name)
        if outer: self.outer.add(name)
        return name

    def row(self, name, c, rhs=0.):
        self.rows.append(Row(name, {k: float(v) for k, v in c.items() if v}, float(rhs)))

    def eq(self, name, c, rhs=0., selector=None, big_m=0.):
        self.ge(name+"_ge", c, rhs, selector, big_m)
        self.ge(name+"_le", {k:-v for k,v in c.items()}, -rhs, selector, big_m)

    def ge(self, name, c, rhs, selector=None, big_m=0.):
        c = c.copy()
        if selector:
            c[selector] = c.get(selector, 0)-big_m
            rhs -= big_m
        self.row(name, c, rhs)

    def add_cost(self, k, c):
        self.cost[k] = self.cost.get(k, 0)+c

    def finish(self, j):
        if j in self.p["tasks"] and self.p["tasks"][j]["kind"] == "monitor":
            return {f"f_{j}":1}, 0.
        return {f"s_{j}":1}, self.p["tasks"][j]["duration"]

    def _build(self):
        p, w = self.p, self.p["weights"]
        h, now = p["horizon"], p["time"]
        mt = 5*h+20
        me = 5*max(r["capacity"] for r in p["robots"].values())+5*h
        for j,t in p["tasks"].items():
            self.var(f"s_{j}", now, h)
            self.row(j+"_release", {f"s_{j}":1}, t["release"])
            if t.get("start_deadline") is not None:
                self.row(j+"_start_deadline", {f"s_{j}":-1}, -t["start_deadline"])
            if t["kind"] == "monitor":
                self.var(f"f_{j}", now, h, outer=True)
                self.row(j+"_minimum", {f"f_{j}":1, f"s_{j}":-1}, t["minimum_duration"])
            else:
                self.row(j+"_deadline", {f"s_{j}":-1}, t["duration"]-t["deadline"])
            if j in p["reference"]["owners"]:
                self.constant += w["owner"]
                self.add_cost(xk(p["reference"]["owners"][j], j), -w["owner"])
                self.var(f"shift_{j}", 0, h)
                old = p["reference"]["starts"][j]
                self.row(j+"_shift_pos", {f"shift_{j}":1,f"s_{j}":-1}, -old)
                self.row(j+"_shift_neg", {f"shift_{j}":1,f"s_{j}":1}, old)
                self.add_cost(f"shift_{j}", w["shift"])
            if t["kind"] == "normal":
                self.add_cost(f"s_{j}", w["normal_delay"])
                self.constant -= w["normal_delay"]*t["release"]
            for dep in t.get("dependencies", []):
                if dep in p["tasks"]:
                    f, c = self.finish(dep)
                    self.row(j+"_after_"+dep, {f"s_{j}":1, **{k:-v for k,v in f.items()}}, c)
                else:
                    self.row(j+"_after_history_"+dep, {f"s_{j}":1}, p["known_finishes"][dep])
        for event in p["events"].values():
            m, pickup, delivery = (event[k] for k in ("monitor", "pickup", "deliver"))
            if not all(j in p["tasks"] for j in (m,pickup,delivery)):
                raise ValueError("This experiment replans before monitor/pickup start only")
            self.row("monitor_cover_"+m, {f"f_{m}":1,f"s_{delivery}":-1}, p["tasks"][delivery]["duration"])
            self.row("monitor_before_pickup_"+m, {f"s_{pickup}":1,f"s_{m}":-1})
            self.add_cost(f"s_{m}", w["response"])
            self.add_cost(f"s_{delivery}", w["response"])
            self.constant += w["response"]*(p["tasks"][delivery]["duration"]-2*event["observed_at"])
        for i,r in p["robots"].items():
            self.var(f"end_{i}", r["ready"], h)
            self.var(f"Eend_{i}", r["minimum"], r["capacity"], outer=True)
            self.add_cost(f"end_{i}", w["return"])
            self.constant -= w["return"]*r["ready"]
            self.add_cost(f"Eend_{i}", -w["energy"])
            self.constant += w["energy"]*r["energy"]
            for j,t in p["tasks"].items():
                x = self.var(xk(i,j), 0, 1, binary=True)
                pre = self.var(f"pre_{i}_{j}", 0, r["capacity"], outer=True)
                post = self.var(f"post_{i}_{j}", 0, r["capacity"], outer=True)
                for e in (pre,post):
                    self.row(e+"_safe", {e:1,x:-r["minimum"]})
                    self.row(e+"_cap", {e:-1,x:r["capacity"]})
                if not set(t["capabilities"]).issubset(r["capabilities"]):
                    self.eq("ability_"+x, {x:1})
                if t["kind"] == "monitor":
                    rate = t["energy_rate"]
                    c = {post:1,pre:-1,f"f_{j}":rate,f"s_{j}":-rate}
                    self.eq("service_"+x, c, selector=x, big_m=me)
                else:
                    self.eq("service_"+x, {post:1,pre:-1}, -t["energy_rate"]*t["duration"], x, me)
        for i,u,v in arcs(p):
            a = self.var(ak(i,u,v), 0,1,binary=True)
            wait = self.var(f"wait_{i}_{u}_{v}",0,h)
            dt = tau(p,i,u,v)
            s = f"end_{i}" if v=="end" else f"s_{v}"
            f, fc = ({},p["robots"][i]["ready"]) if u=="src" else self.finish(u)
            c = {s:1}
            for k,x in f.items(): c[k]=c.get(k,0)-x
            self.ge("time_"+a, c, dt+fc, a, mt)
            wc = {wait:1, **{k:-x for k,x in c.items()}}
            self.eq("waiting_"+a, wc, -dt-fc, a, mt)
            self.row("select_wait_"+a, {wait:-1,a:h})
            r=p["robots"][i]
            ec={f"Eend_{i}" if v=="end" else f"pre_{i}_{v}":1}
            source=r["energy"] if u=="src" else 0.
            if u!="src": ec[f"post_{i}_{u}"]=-1
            for k,x in c.items(): ec[k]=ec.get(k,0)+r["idle_rate"]*x
            rhs=source-(r["move_rate"]-r["idle_rate"])*dt+r["idle_rate"]*fc
            self.eq("energy_"+a, ec, rhs, a, me)
            self.add_cost(a,w["travel"]*dt)
            self.add_cost(wait,w["wait"])
        for i, route in p["reference"]["routes"].items():
            route=[j for j in route if j in p["tasks"]]
            for u,v in zip(route,route[1:]):
                self.add_cost(ak(i,u,v),-w["adjacency"])
                self.constant+=w["adjacency"]
        jobs=list(p["tasks"])
        for n,u in enumerate(jobs):
            for v in jobs[n+1:]:
                common=set(p["tasks"][u]["resources"]) & set(p["tasks"][v]["resources"])
                for resource in sorted(common):
                    if any(p["tasks"][j]["kind"]=="monitor" for j in (u,v)):
                        raise ValueError("Monitor has a distinct service point in this experiment")
                    key=self.var(f"resource_{len(self.pairs)}",0,1,binary=True)
                    self.pairs.append((key,u,v,resource))
                    self.ge(key+"_u_first", {f"s_{v}":1,f"s_{u}":-1}, p["tasks"][u]["duration"]+p["buffer"],key,mt)
                    self.row(key+"_v_first", {f"s_{u}":1,f"s_{v}":-1,key:mt}, p["tasks"][v]["duration"]+p["buffer"])
        for lock in p["fixed_resources"]:
            for j,t in p["tasks"].items():
                if lock["resource"] in t["resources"]:
                    self.row(j+"_after_lock_"+lock["task"], {f"s_{j}":1},lock["finish"]+p["buffer"])

    def pulp_model(self, scope):
        p=self.p
        model=pulp.LpProblem("independent_des",pulp.LpMinimize)
        v={k:pulp.LpVariable(k,a,b,cat="Binary" if k in self.binary else "Continuous") for k,(a,b) in self.bounds.items() if k not in self.outer}
        n=len(p["tasks"])
        rank={(i,j):pulp.LpVariable(f"rank_{i}_{j}",0,n) for i in p["robots"] for j in p["tasks"]}
        for j in p["tasks"]:
            model+=sum(v[xk(i,j)] for i in p["robots"])==1
        for i in p["robots"]:
            model+=sum(v[ak(ii,u,w)] for ii,u,w in arcs(p) if ii==i and u=="src")==1
            model+=sum(v[ak(ii,u,w)] for ii,u,w in arcs(p) if ii==i and w=="end")==1
            for j in p["tasks"]:
                model+=sum(v[ak(ii,u,w)] for ii,u,w in arcs(p) if ii==i and w==j)==v[xk(i,j)]
                model+=sum(v[ak(ii,u,w)] for ii,u,w in arcs(p) if ii==i and u==j)==v[xk(i,j)]
                model+=rank[i,j]>=v[xk(i,j)];model+=rank[i,j]<=n*v[xk(i,j)]
            for ii,u,w in arcs(p):
                if ii==i and u in p["tasks"] and w in p["tasks"]:
                    model+=rank[i,w]>=rank[i,u]+1-(n+1)*(1-v[ak(i,u,w)])
            for event in p["events"].values():
                m,a,b=(event[k] for k in ("monitor","pickup","deliver"))
                model+=v[xk(i,a)]==v[xk(i,b)]
                model+=v[xk(i,m)]+v[xk(i,a)]<=1
        free=set(scope["free"])
        for j,owner in p["reference"]["owners"].items():
            if j in p["tasks"] and j not in free:
                model+=v[xk(owner,j)]==1
                if scope["freeze_time"]: model+=v[f"s_{j}"]==p["reference"]["starts"][j]
        for i,old in p["reference"]["routes"].items():
            fixed=[j for j in old if j in p["tasks"] and j not in free]
            for u,w in zip(fixed,fixed[1:]): model+=rank[i,w]>=rank[i,u]+1
        for row in self.rows:
            if not any(k in self.outer for k in row.coefficients):
                model+=sum(c*v[k] for k,c in row.coefficients.items())>=row.rhs,row.name
        return model,v

    def lp(self, core, deadline):
        names=sorted(self.outer)
        rows=[r for r in self.rows if any(k in self.outer for k in r.coefficients)]
        rows+= [Row("boundlo_"+k,{k:1},self.bounds[k][0]) for k in names]
        rows+= [Row("boundhi_"+k,{k:-1},-self.bounds[k][1]) for k in names]
        a=np.array([[r.coefficients.get(k,0) for k in names] for r in rows])
        rhs=np.array([r.rhs-sum(c*core[k] for k,c in r.coefficients.items() if k not in self.outer) for r in rows])
        c=np.array([self.cost.get(k,0) for k in names])
        opts={"time_limit":max(.001,deadline-perf_counter())}
        phase=linprog(np.r_[np.zeros(len(names)),np.ones(len(rows))],A_ub=np.c_[-a,-np.eye(len(rows))],b_ub=-rhs,
                      bounds=[(None,None)]*len(names)+[(0,None)]*len(rows),method="highs",options=opts)
        if phase.status!=0:return {"status":"UNKNOWN_BUDGET","message":phase.message}
        infeasible=phase.fun>TOL
        if infeasible:
            dual=-phase.ineqlin.marginals
            residual=float(np.max(abs(a.T@dual)))
            if min(dual)<-TOL or residual>TOL or dual@rhs<=TOL:raise RuntimeError("Invalid feasibility certificate")
            result={"status":"INFEASIBLE","residual":residual,"certificate_value":float(dual@rhs)}
        else:
            cost=linprog(c,A_ub=-a,b_ub=-rhs,bounds=[(None,None)]*len(names),method="highs",
                         options={"time_limit":max(.001,deadline-perf_counter())})
            if cost.status!=0:return {"status":"UNKNOWN_BUDGET","message":cost.message}
            dual=-cost.ineqlin.marginals
            residual=float(max(np.max(abs(a.T@dual-c)),max(0,np.max(rhs-a@cost.x))))
            if min(dual)<-TOL or residual>TOL or abs(dual@rhs-cost.fun)>TOL:raise RuntimeError("Invalid cost certificate")
            result={"status":"OPTIMAL","residual":residual,"objective":float(cost.fun),"outer":dict(zip(names,map(float,cost.x)))}
        constant=sum(float(y)*r.rhs for y,r in zip(dual,rows))
        coefficients={}
        for y,row in zip(dual,rows):
            for k,x in row.coefficients.items():
                if k not in self.outer:coefficients[k]=coefficients.get(k,0)-float(y)*x
        result["cut"]={"constant":constant,"coefficients":{k:x for k,x in coefficients.items() if abs(x)>1e-12}}
        result["certificate_support"]=[(rows[n].name,float(y)) for n,y in enumerate(dual) if abs(y)>1e-12]
        return result


def objective(p, plan):
    w=p["weights"];ref=p["reference"]
    travel_sum=wait=draw=adj=0.
    for i,route in plan["routes"].items():
        r=p["robots"][i];previous="src";finish=r["ready"]
        pairs=set(zip(route,route[1:]))
        old=[j for j in ref["routes"].get(i,[]) if j in p["tasks"]]
        adj+=sum(pair not in pairs for pair in zip(old,old[1:]))
        for j in route+["end"]:
            start=plan["ends"][i] if j=="end" else plan["starts"][j]
            dt=tau(p,i,previous,j);idle=start-finish-dt
            travel_sum+=dt;wait+=idle;draw+=r["move_rate"]*dt+r["idle_rate"]*idle
            if j!="end":
                t=p["tasks"][j];draw+=t["energy_rate"]*(plan["finishes"][j]-start)
            finish=start if j=="end" else plan["finishes"][j];previous=j
    response=sum(plan["starts"][e["monitor"]]+plan["finishes"][e["deliver"]]-2*e["observed_at"] for e in p["events"].values())
    parts={"travel":w["travel"]*travel_sum,"wait":w["wait"]*wait,"energy":w["energy"]*draw,
           "response":w["response"]*response,
           "normal_delay":w["normal_delay"]*sum(plan["starts"][j]-t["release"] for j,t in p["tasks"].items() if t["kind"]=="normal"),
           "owner":w["owner"]*sum(plan["owners"][j]!=i for j,i in ref["owners"].items() if j in p["tasks"]),
           "shift":w["shift"]*sum(abs(plan["starts"][j]-ref["starts"][j]) for j in ref["owners"] if j in p["tasks"]),
           "adjacency":w["adjacency"]*adj,
           "return":w["return"]*sum(plan["ends"][i]-p["robots"][i]["ready"] for i in p["robots"])}
    return parts


def reconstruct(p, values):
    plan={"routes":{},"owners":{},"starts":{},"finishes":{},"ends":{},"energy_end":{}}
    for j,t in p["tasks"].items():
        plan["owners"][j]=next(i for i in p["robots"] if values[xk(i,j)]>.5)
        plan["starts"][j]=values[f"s_{j}"]
        plan["finishes"][j]=values[f"f_{j}"] if t["kind"]=="monitor" else values[f"s_{j}"]+t["duration"]
    for i in p["robots"]:
        route=[];u="src"
        for _ in range(len(p["tasks"])+1):
            options=[v for ii,uu,v in arcs(p) if ii==i and uu==u and values[ak(i,u,v)]>.5]
            if len(options)!=1:raise RuntimeError("Invalid route degree")
            v=options[0]
            if v=="end":break
            if v in route:raise RuntimeError("Route cycle")
            route.append(v);u=v
        plan["routes"][i]=route;plan["ends"][i]=values[f"end_{i}"];plan["energy_end"][i]=values[f"Eend_{i}"]
    return plan


def validate(p, plan, scope, claimed=None):
    errors=[];checks=0;maximum=0.
    def check(name,left,right,equal=False):
        nonlocal checks,maximum
        residual=abs(left-right) if equal else max(0,right-left)
        maximum=max(maximum,residual);checks+=1
        if residual>TOL:errors.append({"name":name,"residual":residual})
    counts={j:0 for j in p["tasks"]}
    for i,route in plan["routes"].items():
        robot=p["robots"][i];energy=robot["energy"];previous="src";finish=robot["ready"]
        for j in route+["end"]:
            s=plan["ends"][i] if j=="end" else plan["starts"][j]
            dt=tau(p,i,previous,j);gap=s-finish-dt
            check(i+j+"_travel",gap,0)
            energy-=robot["move_rate"]*dt+robot["idle_rate"]*gap
            check(i+j+"_arrival_energy",energy,robot["minimum"])
            if j!="end":
                counts[j]+=1;t=p["tasks"][j];f=plan["finishes"][j]
                check(j+"_ability",int(set(t["capabilities"]).issubset(robot["capabilities"])),1,True)
                check(j+"_owner",int(plan["owners"][j]==i),1,True)
                check(j+"_release",s,max(p["time"],t["release"]))
                if t.get("start_deadline") is not None:check(j+"_start_deadline",t["start_deadline"],s)
                if t["kind"]=="monitor":check(j+"_min",f-s,t["minimum_duration"])
                else:
                    check(j+"_duration",f-s,t["duration"],True);check(j+"_deadline",t["deadline"],f)
                for dep in t.get("dependencies",[]):check(j+"_dependency",s,plan["finishes"].get(dep,p["known_finishes"].get(dep,0)))
                energy-=t["energy_rate"]*(f-s);finish=f
            else:finish=s
            check(i+j+"_energy",energy,robot["minimum"]);check(i+j+"_capacity",robot["capacity"],energy)
            if j!='end':check(j+'_horizon',p['horizon'],plan['finishes'][j])
            previous=j
        check(i+"_return",p["horizon"],plan["ends"][i]);check(i+"_energy_trace",plan["energy_end"][i],energy,True)
    for j,n in counts.items():check(j+"_unique",n,1,True)
    for event in p["events"].values():
        m,a,b=(event[k] for k in ("monitor","pickup","deliver"))
        check("monitor_before_pickup",plan["starts"][a],plan["starts"][m])
        check("monitor_until_delivery",plan["finishes"][m],plan["finishes"][b])
        check("cargo",int(plan["owners"][a]==plan["owners"][b]),1,True)
        check("distinct_roles",int(plan['owners'][m]!=plan['owners'][a]),1,True)
    jobs=list(p["tasks"])
    for n,u in enumerate(jobs):
        for v in jobs[n+1:]:
            if set(p["tasks"][u]["resources"]) & set(p["tasks"][v]["resources"]):
                check("resource_"+u+v,max(plan["starts"][v]-plan["finishes"][u],plan["starts"][u]-plan["finishes"][v]),p["buffer"])
    for lock in p["fixed_resources"]:
        for j,t in p["tasks"].items():
            if lock["resource"] in t["resources"]:check("active_resource_"+j,plan["starts"][j],lock["finish"]+p["buffer"])
    for i,old in p["reference"]["routes"].items():
        fixed=[j for j in old if j in p["tasks"] and j not in scope["free"]]
        actual=[j for j in plan["routes"][i] if j in fixed]
        check("external_sequence",int(actual==fixed),1,True)
        for j in fixed:
            check(j+"_frozen_owner",int(plan["owners"][j]==i),1,True)
            if scope["freeze_time"]:check(j+"_frozen_time",plan["starts"][j],p["reference"]["starts"][j],True)
    parts=objective(p,plan)
    if claimed is not None:check("objective",sum(parts.values()),claimed,True)
    return {"passed":not errors,"checks":checks,"max_residual":maximum,"errors":errors,"objective_parts":parts}


class Solver:
    def __init__(self,out):
        self.out=Path(out);self.out.mkdir(parents=True,exist_ok=True);self.counter=0

    def solve(self,p,scope,kind,deadline):
        begin=perf_counter();self.counter+=1;tag=f"attempt_{self.counter:03d}"
        tpl=Model(p);model,v=tpl.pulp_model(scope)
        local=tpl.constant+sum(c*v[k] for k,c in tpl.cost.items() if k not in tpl.outer)
        trace=[];values=None;logs=[];lp_seconds=cbc_seconds=0.
        def call():
            nonlocal cbc_seconds
            remaining=deadline-perf_counter()
            if remaining<=0:return "UNKNOWN_BUDGET"
            log=self.out/f"{tag}_cbc_{len(logs):03d}.log";logs.append(str(log))
            t=perf_counter()
            model.solve(pulp.PULP_CBC_CMD(msg=False,threads=0,gapRel=0,gapAbs=0,timeLimit=remaining,
                        options=["randomSeed 1","randomCbcSeed 1"],logPath=str(log)))
            cbc_seconds+=perf_counter()-t;s=log.read_text()
            if ("Result - Optimal solution found" in s or "Optimal objective" in s) and model.sol_status==pulp.LpSolutionOptimal:return "OPTIMAL"
            if model.status==pulp.LpStatusInfeasible and "infeasible" in s.lower():return "INFEASIBLE"
            return "UNKNOWN_BUDGET"
        if kind=="monolithic":
            z={k:pulp.LpVariable(k,*tpl.bounds[k]) for k in tpl.outer}
            for row in tpl.rows:
                if any(k in tpl.outer for k in row.coefficients):
                    model+=sum(c*(z[k] if k in z else v[k]) for k,c in row.coefficients.items())>=row.rhs,row.name
            model+=local+sum(tpl.cost.get(k,0)*x for k,x in z.items())
            status=call()
            if status=="OPTIMAL":values={k:float(x.value()) for k,x in {**v,**z}.items()};cost=float(pulp.value(model.objective))
        else:
            lo=sum(min(c*tpl.bounds[k][0],c*tpl.bounds[k][1]) for k,c in tpl.cost.items() if k in tpl.outer)
            theta=pulp.LpVariable("theta",lowBound=lo);model+=local+theta
            seen=set();status="UNKNOWN_BUDGET"
            for iteration in range(200):
                status=call()
                if status!="OPTIMAL":break
                core={k:float(x.value()) for k,x in v.items()};t=perf_counter();o=tpl.lp(core,deadline);lp_seconds+=perf_counter()-t
                if o["status"]=="UNKNOWN_BUDGET":status=o["status"];break
                cut=o["cut"];expr=cut["constant"]+sum(c*v[k] for k,c in cut["coefficients"].items())
                log={"iteration":iteration+1,"master_lower_bound":float(pulp.value(model.objective)),
                     "candidate":{k:x for k,x in core.items() if abs(x)>1e-12},"external":o}
                if o["status"]=="OPTIMAL":
                    upper=float(pulp.value(local))+o["objective"];gap=upper-log["master_lower_bound"]
                    log.update(upper_bound=upper,gap=gap)
                    if gap < -TOL:raise RuntimeError("Invalid bound")
                    if gap<=TOL:
                        values={**core,**o["outer"]};cost=upper;trace.append(log);break
                    model+=theta>=expr
                else:model+=expr<=0
                key=json.dumps([o["status"],cut],sort_keys=True)
                if key in seen:raise RuntimeError("Repeated violated cut")
                seen.add(key);trace.append(log)
            else:status="UNKNOWN_BUDGET"
        if status=="OPTIMAL" and values is None:status="UNKNOWN_BUDGET"
        result={"status":status,"kind":kind,"scope":scope,"trace":trace,"cbc_logs":logs,
                "timing":{"total":perf_counter()-begin,"cbc":cbc_seconds,"external_lp":lp_seconds}}
        if values is not None:
            plan=reconstruct(p,values);audit=validate(p,plan,scope,cost)
            result.update(plan=plan,objective=cost,validation=audit)
            if not audit["passed"]:result["status"]="INVALID_PLAN"
        result["timing"]["total"]=perf_counter()-begin
        (self.out/f"{tag}_input.json").write_text(json.dumps({"problem":p,"scope":scope,"kind":kind},indent=2))
        return result


def affected_closure(p,new):
    """Independent adaptation of current dynamic_repair's seed/forward closure."""
    graph={j:set() for j in p["tasks"]}
    for j,t in p["tasks"].items():
        for dep in t.get("dependencies",[]):
            if dep in graph:graph[dep].add(j)
    for route in p["reference"]["routes"].values():
        route=[j for j in route if j in graph]
        for u,v in zip(route,route[1:]):graph[u].add(v)
    reached=set(new);pending=list(new)
    while pending:
        for successor in graph.get(pending.pop(),set()):
            if successor not in reached:reached.add(successor);pending.append(successor)
    return reached


def policy_stages(p,policy):
    """One shared retention/expansion policy, independent of its solver backend."""
    new=set(p["tasks"])-set(p["reference"]["owners"])
    free=affected_closure(p,new)
    if policy=="full_replan":stages=[{"free":list(p["tasks"]),"freeze_time":False}]
    elif policy=="local_repair":
        stages=[{"free":sorted(free),"freeze_time":True},{"free":list(p["tasks"]),"freeze_time":False}]
    elif policy in {"candidate","retained_milp"}:
        stages=[{"free":sorted(free),"freeze_time":False}]
        old=sorted(set(p["tasks"])-free,key=lambda j:(p["reference"]["starts"].get(j,float("inf")),j))
        for j in old:
            free.add(j);stages.append({"free":sorted(free),"freeze_time":False})
    else:raise ValueError(policy)
    return stages


def replan(p,policy,out,budget=30.):
    begin=perf_counter();deadline=begin+budget;solver=Solver(out);attempts=[]
    stages=policy_stages(p,policy)
    for n,scope in enumerate(stages):
        method="decomposition" if policy=="candidate" else "monolithic"
        result=solver.solve(p,scope,method,deadline);attempts.append(result)
        if result["status"]=="OPTIMAL":
            return {"policy":policy,"status":"OPTIMAL","plan":result["plan"],"objective":result["objective"],
                    "validation":result["validation"],"attempts":attempts,"fallback_used":policy=="local_repair" and n>0,
                    "scope_expansions":n if policy in {"candidate","retained_milp"} else 0,"planning_seconds":perf_counter()-begin}
        if result["status"]!="INFEASIBLE":break
    return {"policy":policy,"status":attempts[-1]["status"],"attempts":attempts,
            "planning_seconds":perf_counter()-begin,"fallback_used":policy=="local_repair" and len(attempts)>1}

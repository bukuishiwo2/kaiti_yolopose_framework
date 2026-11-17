"""A deterministic event queue, with actual energy integration and immutable prefixes.

Planning wall time pauses the virtual clock. This is not a real-time simulator.
"""
from copy import deepcopy
import heapq
import hashlib
import json
from pathlib import Path
from .planner import replan, tau, TOL
from .scenarios import TaskFactory


class Simulation:
    def __init__(self,problem,initial_plan,out,policy=None,fall_at=8,budget=30):
        self.problem=deepcopy(problem);self.initial=deepcopy(initial_plan)
        self.out=Path(out);self.out.mkdir(parents=True,exist_ok=True)
        self.policy=policy;self.fall_at=fall_at;self.budget=budget
        self.now=0.;self.queue=[];self.serial=0;self.trace=[];self.records={};self.actions=[]
        self.revision={i:0 for i in problem['robots']};self.active={i:None for i in problem['robots']}
        self.state={i:dict(position=list(r['position']),energy=r['energy'],minimum_energy=r['energy']) for i,r in problem['robots'].items()}
        self.factory=TaskFactory();self.repair=None;self.snapshot=None;self.failed=False
        self.install(problem,initial_plan)
        if policy:self.push(fall_at,2,'fall',None)

    def push(self,time,priority,kind,data):
        self.serial+=1;heapq.heappush(self.queue,(float(time),priority,self.serial,kind,data))

    def log(self,kind,**extra):self.trace.append(dict(time=self.now,kind=kind,**extra))

    def install(self,p,plan):
        for i,route in plan['routes'].items():
            self.revision[i]+=1;rev=self.revision[i]
            r=p['robots'][i];finish=r['ready'];u='src';position=list(r['position'])
            def add(kind,start,end,dest,rate,job=None):
                if end-start<=TOL:return
                a=dict(id=len(self.actions),robot=i,revision=rev,kind=kind,start=start,end=end,
                       position=list(dest),rate=rate,task=job)
                self.actions.append(a)
                priority=3 if job and p['tasks'][job]['kind']=='monitor' else 4
                self.push(start,priority,'start',a)
                self.push(end,1 if job and p['tasks'][job]['kind']=='monitor' else 0,'finish',a)
            for j in route+['end']:
                s=plan['ends'][i] if j=='end' else plan['starts'][j]
                dt=tau(p,i,u,j);dest=r['home'] if j=='end' else p['tasks'][j]['location']
                add('wait',finish,s-dt,position,r['idle_rate'])
                add('travel',s-dt,s,dest,r['move_rate'])
                if j!='end':
                    add('service',s,plan['finishes'][j],dest,p['tasks'][j]['energy_rate'],j)
                    finish=plan['finishes'][j]
                else:finish=s
                position=list(dest);u=j

    def advance(self,at):
        if at<self.now-TOL:raise RuntimeError('Time reversed')
        for i,state in self.state.items():
            a=self.active[i]
            if a:state['energy']-=a['rate']*(at-self.now)
            state['minimum_energy']=min(state['minimum_energy'],state['energy'])
            if state['energy']<self.problem['robots'][i]['minimum']-TOL:raise RuntimeError('Battery unsafe')
        self.now=at

    def make_snapshot(self):
        p=deepcopy(self.problem);p['time']=self.now;p['known_finishes']={j:v['finish'] for j,v in self.records.items() if 'finish' in v}
        p['fixed_resources']=[];prefix=set(p['known_finishes'])
        for i,state in self.state.items():
            r=p['robots'][i];a=self.active[i]
            r.update(ready=self.now,position=list(state['position']),energy=state['energy'])
            if a and a['kind'] in ('service','travel'):
                r.update(ready=a['end'],position=list(a['position']),energy=state['energy']-a['rate']*(a['end']-self.now))
                if a['kind']=='service':
                    j=a['task'];prefix.add(j);p['known_finishes'][j]=a['end']
                    for resource in p['tasks'][j]['resources']:
                        p['fixed_resources'].append(dict(resource=resource,task=j,finish=a['end']))
            elif a:  # Waiting can be interrupted; its old finish event is invalidated.
                self.active[i]=None
        p['tasks']={j:t for j,t in p['tasks'].items() if j not in prefix}
        p['reference']=dict(owners={j:i for j,i in self.initial['owners'].items() if j in p['tasks']},
                            starts={j:s for j,s in self.initial['starts'].items() if j in p['tasks']},
                            routes={i:[j for j in route if j in p['tasks']] for i,route in self.initial['routes'].items()})
        return p

    def event(self):
        jobs,events=self.factory.fall('E1',self.now)
        self.problem['tasks'].update(jobs);self.problem['events'].update(events)
        self.log('fall_observed',event='E1');self.log('tasks_generated',tasks=list(jobs))
        p=self.make_snapshot();self.snapshot=p
        self.log('planning_requested',tasks=list(p['tasks']),immutable_prefix=p['known_finishes'])
        self.repair=replan(p,self.policy,self.out/'solver',self.budget)
        self.log('planning_returned',status=self.repair['status'],wall_seconds=self.repair['planning_seconds'])
        if self.repair['status']!='OPTIMAL':self.failed=True;return
        self.install(p,self.repair['plan'])

    def execute(self):
        while self.queue and not self.failed:
            at,_,_,kind,a=heapq.heappop(self.queue)
            if kind!='fall':
                i=a['robot']
                if kind=='start' and a['revision']!=self.revision[i]:continue
                if kind=='finish' and self.active[i] is not a:continue
            self.advance(at)
            if kind=='fall':self.event();continue
            i=a['robot'];j=a['task']
            if kind=='start':
                if self.active[i]:raise RuntimeError('Robot overlapping actions')
                self.active[i]=a
                if j:
                    if j in self.records:raise RuntimeError('Duplicate task execution')
                    t=self.problem['tasks'][j]
                    if any(dep not in self.records or 'finish' not in self.records[dep] for dep in t['dependencies']):raise RuntimeError('Dependency not completed')
                    if t['kind']=='pickup':
                        m=self.problem['events'][t['event_id']]['monitor']
                        if not any(v and v['task']==m for v in self.active.values()):raise RuntimeError('Pickup without monitoring')
                    self.records[j]=dict(owner=i,start=self.now)
                self.log('action_start',robot=i,action=a['kind'],task=j)
            else:
                if j:
                    t=self.problem['tasks'][j]
                    if t['kind']=='monitor':
                        d=self.problem['events'][t['event_id']]['deliver']
                        if 'finish' not in self.records.get(d,{}):raise RuntimeError('Monitor ended too early')
                    self.records[j]['finish']=self.now
                self.state[i]['position']=list(a['position']);self.active[i]=None
                self.log('action_finish',robot=i,action=a['kind'],task=j,energy=self.state[i]['energy'])
        audit=self.audit()
        result=dict(policy=self.policy or 'no_fall',status='FAILED' if self.failed else 'COMPLETE',
                    makespan=self.now,records=self.records,state=self.state,execution_audit=audit,
                    initial_plan=self.initial,repair=self.repair,snapshot=self.snapshot,trace=self.trace)
        if self.snapshot:result['snapshot_sha256']=hashlib.sha256(json.dumps(self.snapshot,sort_keys=True).encode()).hexdigest()
        (self.out/'simulation.json').write_text(json.dumps(result,indent=2))
        return result

    def audit(self):
        errors=[];tasks=self.problem['tasks'];checks=0
        def ck(ok,label):
            nonlocal checks
            checks+=1
            if not ok:errors.append(label)
        ck(set(self.records)==set(tasks),'all tasks executed')
        for j,rec in self.records.items():
            if 'finish' not in rec:ck(False,j+' incomplete');continue
            t=tasks[j];r=self.problem['robots'][rec['owner']]
            ck(set(t['capabilities']).issubset(r['capabilities']),j+' ability')
            ck(rec['start']>=t['release']-TOL,j+' release')
            ck(rec['finish']<=t['deadline']+TOL,j+' deadline')
            ck(t.get('start_deadline') is None or rec['start']<=t['start_deadline']+TOL,j+' start deadline')
            duration=t['minimum_duration'] if t['kind']=='monitor' else t['duration']
            ck(rec['finish']-rec['start']>=duration-TOL if t['kind']=='monitor' else abs(rec['finish']-rec['start']-duration)<=TOL,j+' duration')
            for dep in t['dependencies']:ck(self.records[dep]['finish']<=rec['start']+TOL,j+' dependency')
        complete=[j for j in self.records if 'finish' in self.records[j]]
        for n,j in enumerate(complete):
            a=self.records[j]
            for k in complete[n+1:]:
                b=self.records[k];gap=max(a['start']-b['finish'],b['start']-a['finish'])
                if a['owner']==b['owner']:ck(gap>=-TOL,j+k+' robot overlap')
                if set(tasks[j]['resources'])&set(tasks[k]['resources']):ck(gap>=self.problem['buffer']-TOL,j+k+' resource')
        for event in self.problem['events'].values():
            if not all('finish' in self.records.get(event[k],{}) for k in ('monitor','pickup','deliver')):
                ck(False,'event incomplete');continue
            m,p,d=(self.records[event[k]] for k in ('monitor','pickup','deliver'))
            ck(m['start']<=p['start']+TOL and m['finish']>=d['finish']-TOL,'monitor coverage')
            ck(p['owner']==d['owner'] and p['owner']!=m['owner'],'event roles')
        for i,r in self.problem['robots'].items():
            ck(self.state[i]['position']==r['home'],i+' home')
            ck(self.state[i]['minimum_energy']>=r['minimum']-TOL,i+' battery')
        if self.snapshot:
            for j in self.snapshot['known_finishes']:
                ck('finish' in self.records.get(j,{}) and abs(self.records[j]['finish']-self.initial['finishes'][j])<=TOL,j+' immutable finish')
                ck(self.records[j]['owner']==self.initial['owners'][j],j+' immutable owner')
            if self.repair and self.repair['status']=='OPTIMAL':
                for i,e in self.repair['plan']['energy_end'].items():ck(abs(self.state[i]['energy']-e)<=TOL,i+' energy predicted/actual')
        return dict(passed=not errors,checks=checks,errors=errors)

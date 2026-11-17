"""Seeded task fixtures and idempotent event-to-task templates (no perception)."""
from copy import deepcopy
from random import Random
from .planner import WEIGHTS


def task(kind, location, duration, release, deadline, capabilities, resources=(), **extra):
    return dict(kind=kind, location=list(location), duration=duration, release=release,
                deadline=deadline, capabilities=list(capabilities), resources=list(resources),
                dependencies=[], energy_rate=.15, **extra)


def routine(seed, variant='reassignment_required'):
    if variant not in ('reassignment_required','retiming_allowed'):raise ValueError(variant)
    rng=Random(seed)
    robots={}
    for i,home,speed,caps in [
        ('R0',[0,0],1,['move','camera','carry','patrol']),
        ('R1',[8,0],2,['move','camera','carry','patrol','inspect']),
        ('R2',[4,5],1.2,['move','carry','patrol','inspect','guide','zone'])]:
        robots[i]=dict(position=home,home=home,ready=0,energy=60,capacity=60,minimum=5,
                       speed=speed,move_rate=.2,idle_rate=.02,capabilities=caps)
    tasks={
        'N0':task('normal',(0,0),18,0,28,['move','patrol'],start_deadline=0),
        'N1':task('normal',(8,0),18,0,28,['move','inspect'],start_deadline=0),
        'N2':task('normal',(4,5),16,0,26,['move','carry'],start_deadline=0),
        'N3':task('normal',(1,1),8,20,32 if variant=='reassignment_required' else 55,['move','patrol']),
        'N4':task('normal',(6,4),rng.randint(5,7),19,55,['move','carry'],['supply_station']),
        'N5':task('normal',(8,3),rng.randint(7,9),32,60,['move','patrol']),
    }
    return dict(seed=seed,variant=variant,time=0,horizon=90,buffer=1,weights=deepcopy(WEIGHTS),robots=robots,
                tasks=tasks,events={},known_finishes={},fixed_resources=[],
                reference=dict(owners={},starts={},routes={i:[] for i in robots}))


class TaskFactory:
    """Task-level templates; guide/zone do not simulate humans or geometric safety."""
    def __init__(self): self.seen=set()

    def fall(self,event_id,at,location=(2,1),extensions=()):
        if event_id in self.seen:return {},{}
        if set(extensions)-{'guide','safety_zone'}:raise ValueError('Unknown extension')
        self.seen.add(event_id)
        x,y=location;m,p,d=(event_id+'_'+s for s in ('monitor','pickup','deliver'))
        jobs={
            m:task('monitor',(x,y-1),None,at,90,['move','camera'],minimum_duration=2,start_deadline=at+12),
            p:task('pickup',(6,4),3,at,at+21,['move','carry'],['supply_station']),
            d:task('deliver',(x+1,y),3,at,at+24,['move','carry']),
        }
        jobs[m]['energy_rate']=.2;jobs[d]['dependencies']=[p]
        if 'safety_zone' in extensions:
            z=event_id+'_zone'
            jobs[z]=task('safety_zone',(x+1,y+1),2,at,at+24,['move','zone'])
            jobs[p]['dependencies'].append(z)
        if 'guide' in extensions:
            g=event_id+'_guide'
            jobs[g]=task('guide',(x+1,y+1),6,at,at+40,['move','guide'])
            if 'safety_zone' in extensions:jobs[g]['dependencies']=[event_id+'_zone']
        for t in jobs.values():t['event_id']=event_id
        event=dict(monitor=m,pickup=p,deliver=d,observed_at=at,location=list(location),
                   safety_region=[x-.6,y-.6,x+.6,y+.6],extensions=list(extensions))
        return jobs,{event_id:event}

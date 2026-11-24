#!/usr/bin/env python3
"""Read-only compatibility/registry audit. Does not execute solvers, ROS or Gazebo."""
import argparse
import csv
import hashlib
import json
from pathlib import Path
import sys
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'src'))
from kaiti_review.data import descriptors, load_uncached
from kaiti_review.explanations import catalog_metadata

def dump(path,value):
    path.write_text(json.dumps(value,ensure_ascii=False,indent=2,allow_nan=False)+'\n')

def main():
    parser=argparse.ArgumentParser();parser.add_argument('--workspace',type=Path,default=Path('/home/yhc/clinic_planning_ws'));parser.add_argument('--out',type=Path,required=True);args=parser.parse_args();args.out.mkdir(parents=True,exist_ok=True)
    mapping=descriptors(args.workspace);catalog=catalog_metadata(args.workspace,mapping);dump(args.out/'experiment_catalog.json',catalog)
    results=[];full=[];counts={'runs':0,'records':0,'trace_lines':0}
    for name,descriptor in mapping.items():
        try:
            run,_=load_uncached(args.workspace,name,descriptor)
            e=run['explanation'];json.dumps(e,allow_nan=False);counts['runs']+=1;counts['records']+=len(run['records']);counts['trace_lines']+=run['raw_trace_lines'];full.append(e['metadata'])
            results.append({'run_id':name,'readable':True,'passed_original':run['passed'],'records':len(run['records']),'nodes':len(e['nodes']),'dictionary':len(e['tasks']),'plans':len(run['plan_versions']),'event_source':e['metadata']['event_source']})
            if name=='unified_bed_local_r1':
                for key in ('nodes','tasks','repair_diagnostics','path_report','event_planning'):
                    dump(args.out/('unified_bed_local_r1-'+key+'.json'),e[key])
                with (args.out/'node_registry.csv').open('w',encoding='utf-8-sig',newline='') as f:
                    fields=['id','display_name_zh','categories','coordinate','frame','static_registered','event_generated_coordinate','service_point','navigation_topology_point','candidate_approach_point','related_tasks','capabilities','reachability','sources'];w=csv.DictWriter(f,fieldnames=fields,extrasaction='ignore');w.writeheader();w.writerows({k:json.dumps(n[k],ensure_ascii=False) if isinstance(n[k],(dict,list)) else n[k] for k in fields} for n in e['nodes'])
        except Exception as error:
            results.append({'run_id':name,'readable':False,'error':repr(error)})
    dump(args.out/'experiment_registry.json',full)
    dump(args.out/'compatibility.json',{'passed':all(r['readable'] for r in results),'counts':counts,'runs':results,'scope':'read-only adapter compatibility, not new robot experiment'})
    before=args.out/'protected_before.json'
    if before.is_file():
        baseline=json.loads(before.read_text())['files'];changed=[]
        for name,old in baseline.items():
            p=Path(name)
            if not p.is_file() or hashlib.sha256(p.read_bytes()).hexdigest()!=old['sha256']:changed.append(name)
        dump(args.out/'protected_verification.json',{'passed':not changed,'checked':len(baseline),'changed':changed,'scope':'Exact baseline files: results/traces/maps/config/frozen and current research execution sources'})
    print(json.dumps({'counts':counts,'errors':[r for r in results if not r['readable']]},ensure_ascii=False))

if __name__=='__main__':main()

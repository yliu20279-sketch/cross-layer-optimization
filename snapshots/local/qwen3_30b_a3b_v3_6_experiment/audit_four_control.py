"""Independent diagnostic audit; explicitly measures BSA/BGA interval overlap."""
import argparse,csv,json
from collections import Counter,defaultdict
from pathlib import Path
def overlap(rows):
    by=defaultdict(lambda:defaultdict(list))
    for r in rows:by[int(r['npu'])][r['engine']].append((float(r['start']),float(r['done'])))
    total=0.0
    for npu,e in by.items():
        for a,b in e.get('BSA',[]):
            total+=sum(max(0,min(b,d)-max(a,c)) for c,d in e.get('BGA',[]))
    return total
def main():
    ap=argparse.ArgumentParser();ap.add_argument('--root',type=Path,required=True);ap.add_argument('--out',type=Path,required=True);a=ap.parse_args();status=json.loads((a.root/'status.json').read_text());assert status['status']=='PASS'
    report={'status':'PASS','cases':[]}
    for case in status['cases']:
        name=case['scheme'];run=a.root/name/'run';graph=a.root/name/'graph'
        with (run/'compute_resources.csv').open(newline='') as f:cr=list(csv.DictReader(f))
        with (graph/'ops.csv').open(newline='') as f:ops=list(csv.DictReader(f))
        engines=Counter(r['engine'] for r in cr);phases=Counter(r['phase'] for r in ops if r['kind']=='COMPUTE')
        ov=overlap(cr);dynamic=name in ('hiband','hiband_sem_moe');launch=json.loads((run/'launch.json').read_text())
        assert ('HB_FIXED_MODE' not in launch['controls'])==dynamic
        if dynamic:assert engines['BSA']>0 and engines['BGA']>0
        else:assert engines['FULL']>0 and not engines['BSA'] and not engines['BGA']
        report['cases'].append({'scheme':name,'cycles':case['validation']['total_cycles'],'engines':dict(engines),'graph_compute_phases':dict(phases),'bsa_bga_overlap_cycles':ov,'mode_changes_rows':max(0,sum(1 for _ in open(run/'mode_changes.csv'))-1)})
    report['claim_gate']={'hic_overlap_positive':all(c['bsa_bga_overlap_cycles']>0 for c in report['cases'] if c['scheme'] in ('hiband','hiband_sem_moe')),'formal_four_control_ready':False,'reason':'current full-layer DAG has no continuous-microbatch BSA/BGA overlap; diagnostic timing cannot represent HiBand benefit'}
    a.out.write_text(json.dumps(report,indent=2)+'\n');print(json.dumps(report,indent=2))
if __name__=='__main__':main()

"""Audit RTL receipts against frozen inputs, then report paired comparisons."""
import collections,csv,hashlib,json,math
from pathlib import Path
R=Path(__file__).resolve().parent
FULL=['mesh','dual','runtime','forced_cs','hiband_FG','hiband_GB','hiband_LB']
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def main():
    manifest=json.loads((R/'MATRIX.json').read_text());assert manifest['status']=='PASS'
    out=Path(manifest['result_path']);cases={c['name']:c for c in json.loads((R/'CASES.json').read_text())}
    rows=[];results={};reason=collections.Counter();installed=0;checks=0
    for task in manifest['tasks']:
        name=task['case']+'_'+task['arm']+'_b'+str(task['bank'])+('_clk'+str(task['clock']) if task['clock']!=1 else '')
        p=out/(name+'.json');d=json.loads(p.read_text());case=cases[task['case']]
        assert d['status']=='PASS_RTL_DELIVERY_PAYLOAD_AND_SRAM'
        assert len(d['waves'])==len(case['waves'])==6
        read=write=bank=0
        for w,expected in zip(d['waves'],case['waves']):
            gets=0 if task['arm']=='moe_only' else expected['gets']
            payload=0 if task['arm']=='gets_only' else expected['moe_payload_bytes']
            moe_packets=payload//512
            assert w['gets_count']==gets and w['packets']==moe_packets+2*gets,(name,w['stage'],'packet accounting')
            assert w['m_flits']+w['c_flits']+w['cs_flits']==moe_packets*17+gets*4+2*w['configuration_requests'],(name,w['stage'],'wire accounting')
            if task['mode']==1:assert w['c_flits']==4*gets,(name,w['stage'],'C plane opcode routing')
            else:assert w['cs_flits']==w['c_flits']==0
            if task['arm']=='dual':assert w['cs_flits']==w['configuration_requests']==0
            if task['arm']=='forced_cs':assert w['configuration_requests'] in [0,62]
            if task['arm']=='runtime':reason[w['policy_reason']]+=1;installed+=int(w['installed'])
            read+=payload//32;write+=payload//32+gets*2;bank+=gets*2;checks+=1
        assert (d['read_flits'],d['write_flits'],d['bank_flits'])==(read,write,bank),(name,'SRAM service accounting')
        results[(task['case'],task['arm'],task['bank'],task['clock'])]=d
        rows.append(dict(case=task['case'],tokens=case['tokens'],pattern=case['pattern'],interval=case['interval'],
            arm=task['arm'],bank=task['bank'],clock_ns=task['clock'],
            phase_sum_cycles=sum(w['finish'] for w in d['waves']),moe_phase_sum_cycles=sum(w['moe'] for w in d['waves']),
            gets_phase_sum_cycles=sum(w['gets'] for w in d['waves']),max_phase_gets_p99=max(w['gets_p99'] for w in d['waves']),
            source_wait_sum=sum(w['gets_injection_wait_sum'] for w in d['waves']),cs_flits=sum(w['cs_flits'] for w in d['waves']),
            config_requests=sum(w['configuration_requests'] for w in d['waves']),planner_ns=sum(w['planner_ns'] for w in d['waves']),
            runtime_installed=sum(int(w['installed']) for w in d['waves']),sha256=sha(p)))
    fg_differences=[]
    for name in cases:
        base=results[name,'mesh',8,1]
        for arm in FULL:
            d=results[name,arm,8,1]
            assert [w['canonical_payload_hash'] for w in d['waves']]==[w['canonical_payload_hash'] for w in base['waves']],(name,arm,'cross-arm payload equality')
        fg=results[name,'hiband_FG',8,1]
        if [(w['finish'],w['moe'],w['gets'],w['gets_p99']) for w in fg['waves']]!=[(w['finish'],w['moe'],w['gets'],w['gets_p99']) for w in base['waves']]:fg_differences.append(name)
    with (out/'SUMMARY.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator="\n");w.writeheader();w.writerows(rows)
    # Strong comparison bound: choose the fastest legal HiBand allocation
    # separately for every phase, granting free, perfectly informed switching.
    # This is derived from measured RTL runs, not another executed policy.
    phase_best={}
    for name in cases:
        options=[results[name,a,8,1]['waves'] for a in ['hiband_FG','hiband_GB','hiband_LB']]
        choice=[min(range(3),key=lambda j:options[j][i]['finish']) for i in range(6)]
        results[name,'hiband_phase_best',8,1]={'waves':[options[j][i] for i,j in enumerate(choice)]}
        phase_best[name]=choice
    comparisons=[]
    for baseline in ['mesh','hiband_FG','hiband_GB','hiband_LB','hiband_phase_best','dual']:
        for arm in ['dual','runtime','forced_cs']:
            if arm==baseline:continue
            values=[];p99=[];moe=[]
            for name in cases:
                a=results[name,arm,8,1]['waves'];b=results[name,baseline,8,1]['waves']
                values.append(sum(w['finish'] for w in b)/sum(w['finish'] for w in a))
                p99.append(max(w['gets_p99'] for w in b)/max(w['gets_p99'] for w in a))
                moe.append(sum(w['moe'] for w in b)/sum(w['moe'] for w in a))
            comparisons.append(dict(arm=arm,baseline=baseline,n=len(values),geomean_speedup=math.exp(sum(map(math.log,values))/len(values)),
              min_speedup=min(values),max_speedup=max(values),wins=sum(v>1+1e-12 for v in values),losses=sum(v<1-1e-12 for v in values),
              geomean_moe_speedup=math.exp(sum(map(math.log,moe))/len(moe)),geomean_max_phase_p99_ratio=math.exp(sum(map(math.log,p99))/len(p99))))
    audit=dict(status='PASS_INPUT_PAYLOAD_PLANE_WIRE_AND_SRAM_ACCOUNTING',runs=len(rows),phase_checks=checks,
      input_cases=len(cases),cross_arm_payload_comparisons=len(cases)*len(FULL),
      hiband_FG_timing_differences=fg_differences,runtime_installed_phases=installed,runtime_reasons=dict(reason),
      comparisons=comparisons,hiband_phase_best_mode_indices=phase_best,summary_sha256=sha(out/'SUMMARY.csv'),
      scope='Six separately initialized communication phases; deterministic synthetic payload with trace-derived endpoints and byte counts. No numerical MoE inference or complete CPU coherence protocol.')
    (out/'AUDIT.json').write_text(json.dumps(audit,indent=2)+'\n')
    text=['# RTL experiment results','',f"{len(rows)} runs / {checks} communication phases passed packet, payload, plane, wire and SRAM checks.",'',
      '| Arm | Baseline | Geometric mean speedup | Range | Wins / losses |','|---|---|---:|---:|---:|']
    for c in comparisons:text.append(f"| {c['arm']} | {c['baseline']} | {c['geomean_speedup']:.3f} | {c['min_speedup']:.3f}–{c['max_speedup']:.3f} | {c['wins']} / {c['losses']} |")
    text+=['',f"Runtime controller installed in {installed} phases. Reasons: `{dict(reason)}`.",
      f"HiBand full-global versus fixed Mesh timing differences: {len(fg_differences)} / {len(cases)} cases.",'',
      'Speedup is the baseline sum of six phase completion times divided by the tested sum. Each phase begins with a fresh NoC; this is not end-to-end model latency.',
      '`forced_cs` is a preselected routing mechanism control with actual configuration messages, not a successful online controller decision.',
      'The new design includes an additional 256-bit C plane and CS fabric. The reference uses one four-lane 256-bit physical bundle per direction. These results are not normalized for area or wiring.',
      '`hiband_phase_best` chooses the fastest measured legal mode per phase and grants free switching and perfect knowledge. It is an optimistic latency bound, not an executed HiBand policy.',
      'The HiBand implementation is a target-platform unicast NoC adaptation. Three legal static modes are reported separately; no result is attributed to author RTL.',
      'The runtime prototype charges measured host construction/model time at the selected target clock period. Host scheduling and contention affect these costs; a repeated run need not reproduce planner nanoseconds.',
      'The predictor unit test uses synthetic paired expert counts. The supplied transport metadata cannot establish prediction accuracy or full application performance.','']
    (out/'RESULTS.md').write_text('\n'.join(text))
    print(json.dumps({k:v for k,v in audit.items() if k not in ['comparisons','hiband_phase_best_mode_indices']},indent=2))
if __name__=='__main__':main()

"""Audit conservation and aggregate independent phase replay experiments."""
import csv, hashlib, json, statistics
from pathlib import Path
ROOT=Path(__file__).resolve().parent
ARMS=['mesh','dual','proposed','delay_control','hiband_FG','hiband_GB','hiband_LB','gets_only','moe_only']
COMPONENTS=['request_source_wait','request_transport','bank_wait_and_read',
            'reply_source_wait','reply_transport','reply_write']
def load(name,arm,setup=40,bank=8):
    p=ROOT/'results'/f'{name}_{arm}_s{setup}_e0_b{bank}.json'
    return json.loads(p.read_text())
def aggregate(waves):
    n=max(1,sum(w['gets_count'] for w in waves))
    d=dict(moe_phase_cycles=sum(w['moe'] for w in waves),
           join_phase_cycles=sum(w['finish'] for w in waves),
           max_stage_gets_p99=max(w['gets_p99'] for w in waves),
           cs_payload_bytes=sum(w['selected_payload'] for w in waves),
           accepted_phases=sum(bool(w['paths']) for w in waves),
           gets_mean_cycles=sum(sum(w['gets_latency_component_sums']) for w in waves)/n)
    for j,c in enumerate(COMPONENTS):d[c]=sum(w['gets_latency_component_sums'][j] for w in waves)/n
    return d
def main():
    cases=json.loads((ROOT/'CASES.json').read_text())
    manifest=json.loads((ROOT/'RUN_MANIFEST.json').read_text())
    digest=hashlib.sha256((ROOT/'model.cpp').read_bytes()).hexdigest()
    assert digest==manifest['model_sha256'],'Source does not match executable manifest'
    rows=[];audits=[];details=[]
    for c in cases:
        allarms={a:load(c['name'],a) for a in ARMS}
        for arm,d in allarms.items():
            assert d['status']=='PASS_DELIVERY_AND_DRAIN'
            assert len(d['waves'])==len(c['waves'])==6
            for w,src in zip(d['waves'],c['waves']):
                assert w['stage']==src['stage']
                ng=0 if arm=='moe_only' else src['gets']
                mb=0 if arm=='gets_only' else src['moe_payload_bytes']
                mw=0 if arm=='gets_only' else src['moe_wire_bytes']
                assert w['gets_count']==ng
                assert w['max_input_phits']<=64 and w['max_receive_packets']<=16
                assert 8*w['tx_phits']==mw+ng*128
                assert 8*w['sram_phits']==2*mb+ng*128
                assert src['gets_wire_bytes']==src['moe_wire_bytes']
                # Every source message is 4096B split into eight payloads.
                assert w['packets']==mb//512+2*ng
                assert sum(w['gets_latency_component_sums'])>=0
                if arm=='proposed':
                    assert w['guard_max_gets_delta']<=32
                    assert w['moe']<=w['guard_baseline_moe']
                    if w['paths']:assert w['finish']<w['guard_baseline_join']
                    cs=set()
                    for path in w['paths']:
                        assert len(path['cs'])==len(set(path['cs']))
                        assert not(cs & set(path['cs']));cs.update(path['cs'])
                details.append(dict(case=c['name'],tokens=c['tokens'],pattern=c['pattern'],arm=arm,**w))
            audits.append(dict(case=c['name'],arm=arm,conservation=True,drain=True,causality=True))
            rows.append(dict(case=c['name'],tokens=c['tokens'],pattern=c['pattern'],interval=c['interval'],arm=arm,**aggregate(d['waves'])))
        # Explicit hindsight bound: choose lowest join time per phase, and use
        # that same mode's MoE and GetS values. Never call this an online policy.
        h=[min([allarms[a]['waves'][j] for a in ARMS if a.startswith('hiband')],
               key=lambda w:(w['finish'],w['moe'])) for j in range(6)]
        rows.append(dict(case=c['name'],tokens=c['tokens'],pattern=c['pattern'],interval=c['interval'],
                         arm='hiband_phase_oracle',**aggregate(h)))
    # Verify all extra runs too; their input traffic is the same reference case.
    sensitivity=[]
    ref=next(c for c in cases if c['name']=='fit16_641103_distributed')
    for p in sorted((ROOT/'results').glob(ref['name']+'_*.json')):
        d=json.loads(p.read_text())
        if d['setup_cycles']==40 and d['bank_latency']==8:continue
        for w,s in zip(d['waves'],ref['waves']):
            assert w['tx_phits']*8==s['moe_wire_bytes']+s['gets_wire_bytes']
            assert w['sram_phits']*8==2*s['moe_payload_bytes']+s['gets']*128
            assert w['max_input_phits']<=64 and w['max_receive_packets']<=16
            if d['arm']=='proposed':
                assert w['guard_max_gets_delta']<=32 and w['finish']<=w['guard_baseline_join']
        sensitivity.append(dict(file=p.name,arm=d['arm'],setup=d['setup_cycles'],bank=d['bank_latency'],**aggregate(d['waves'])))
    assert len(sensitivity)==11
    (ROOT/'SENSITIVITY.json').write_text(json.dumps(sensitivity,indent=2))
    with (ROOT/'SUMMARY.csv').open('w',newline='') as f:
        out=csv.DictWriter(f,fieldnames=list(rows[0]),lineterminator='\n');out.writeheader();out.writerows(rows)
    (ROOT/'PHASE_RESULTS.json').write_text(json.dumps(details,indent=2))
    summary=[]
    for tokens in [4,8,16]:
        for pattern in ['hotspot','distributed']:
            group=[c for c in cases if c['tokens']==tokens and c['pattern']==pattern and c['interval']==1]
            armstats={a:[] for a in ['proposed','dual','hiband_phase_oracle']}
            for c in group:
                for a in armstats:armstats[a].append(next(r for r in rows if r['case']==c['name'] and r['arm']==a))
            means={a:{k:statistics.mean(x[k] for x in vs) for k in ['moe_phase_cycles','join_phase_cycles','max_stage_gets_p99','cs_payload_bytes','accepted_phases']} for a,vs in armstats.items()}
            gain=statistics.mean(100*(1-p['join_phase_cycles']/h['join_phase_cycles']) for p,h in zip(armstats['proposed'],armstats['hiband_phase_oracle']))
            summary.append(dict(tokens=tokens,pattern=pattern,seeds=len(group),arms=means,join_gain_pct=gain))
    (ROOT/'AUDIT.json').write_text(json.dumps(dict(status='PASS',jobs=len(manifest['tasks']),main_arms=len(audits),sensitivity_arms=len(sensitivity),source_sha256=digest,checks=audits,group_summary=summary),indent=2))
    print('Conservation, source hash, finite credits and protection checks PASS')
    for x in summary:print(x['tokens'],x['pattern'],'new join',round(x['arms']['proposed']['join_phase_cycles'],2),'HiBand oracle',round(x['arms']['hiband_phase_oracle']['join_phase_cycles'],2),'gain %',round(x['join_gain_pct'],3),'CS phases',x['arms']['proposed']['accepted_phases'])
    try:
        import matplotlib
        matplotlib.use('Agg')
        import matplotlib.pyplot as plt
        plt.rcParams.update({'font.family':'DejaVu Sans','font.size':9,'pdf.fonttype':42})
        fig,axes=plt.subplots(1,2,figsize=(8,2.8),layout='constrained')
        for ax,pattern in zip(axes,['hotspot','distributed']):
            groups=[s for s in summary if s['pattern']==pattern]
            xs=range(3)
            for off,(arm,label,color) in enumerate([('hiband_phase_oracle','HiBand modes: phase oracle','#777777'),('dual','C + M, CS off','#d4b05b'),('proposed','C + M, offline CS selection','#3d7b89')]):
                ax.bar([x+(off-1)*.23 for x in xs],[s['arms'][arm]['join_phase_cycles']/1000 for s in groups],width=.23,label=label,color=color)
            ax.set_xticks(list(xs),['4','8','16']);ax.set_xlabel('MoE tokens');ax.set_ylabel('Sum of phase joins (1000 cycles)');ax.set_title(pattern.capitalize());ax.spines[['top','right']].set_visible(False)
        axes[0].legend(frameon=False,fontsize=7)
        fig.savefig(ROOT/'screening_summary.pdf');fig.savefig(ROOT/'screening_summary.png',dpi=180);plt.close(fig)
    except ImportError:print('matplotlib unavailable; CSV and JSON generated')
if __name__=='__main__':main()

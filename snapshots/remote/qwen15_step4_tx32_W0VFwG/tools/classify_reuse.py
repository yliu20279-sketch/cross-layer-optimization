"""Classify observed historical identities; no simulator/model imports."""
from pathlib import Path
import collections
import csv
import json
import sys
ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.common import file_hash,require,digest
from core.reuse import compare_contracts

raw=json.loads((ROOT/'evidence/REUSE_FRESH_RAW.json').read_text())
q15=json.loads((ROOT/'contracts/qwen15.json').read_text())
q3=json.loads((ROOT/'contracts/qwen3.json').read_text())
build=json.loads((ROOT/'evidence/BUILD_LIVE.json').read_text())
def target(c,binary=None):
    result={k:c.get(k) for k in ('model_id','checkpoint_content_sha256','tokenizer_sha256','precision_sha256')}
    result['binary_sha256']=binary or c['runtime']['binary']['sha256']
    result['libraries_sha256']=digest(c['runtime']['libraries'])
    # No made-up hashes for a future complete B graph/input/state/timing.
    return result
rows=[]
for case in raw['q15_cases']:
    old={'binary_sha256':case['recorded_binary_sha256']}
    verdict=compare_contracts(old,target(q15,build['binary_sha256']))
    require(not verdict['cycle_reuse_allowed'],'unexpected promotion of old W4 proxy')
    rows.append({'model':'qwen15','case':case['case'],'source':case['graph'],'group':case['group'],
                 'old_memory_contract':case['memory_contract'],'historical_cycles':case['cycles'],
                 'checks':dict(collections.Counter(x['status'] for x in case['checks'])),
                 'verdict':verdict,'reuse':'historical negative/diagnostic and audit method only',
                 'extra_incompatibilities':['INT4 allocation versus decoded FP16','sampled mechanism versus full-transaction candidate',
                                           'actual dynamic control/CA/composite input graph not frozen']})
summary_path=ROOT/'evidence/Q3_SEVEN_SOURCE.csv'
summary=list(csv.DictReader(summary_path.open(encoding='utf-8-sig')))
for item in summary:
    matches=[p for p in raw['q3_pairs'] if p['endpoints'][0].get('cycles')==int(item['total_cycles'])]
    require(len(matches)==1,'seven-case source cannot be uniquely reconstructed')
    pair=matches[0]
    require(int(item['bank_conflict_cycles'])==pair['endpoints'][0]['cycles']-pair['endpoints'][1]['cycles'],
            'summary delta differs from raw endpoints')
    hashes=[c for c in pair['checks'] if c['path'].endswith('/popnet')]
    old={'binary_sha256':hashes[0].get('sha256') if hashes else None}
    verdict=compare_contracts(old,target(q3))
    require(not verdict['cycle_reuse_allowed'],'unexpected Q3 promotion')
    rows.append({'model':'qwen3','case':item['case'],'source':pair['case'],'group':'seven-summary',
                 'historical_cycles':int(item['total_cycles']),'historical_delta':int(item['bank_conflict_cycles']),
                 'checks':dict(collections.Counter(c['status'] for c in pair['checks'])),
                 'verdict':verdict,'reuse':'historical sensitivity, negative case, DEV/method only',
                 'extra_incompatibilities':['old proxy execution does not establish complete native BF16 B',
                                            'capacity 768/1024MiB cases are not 512MiB partition matches']})
allchecks=raw['binary_checks']+[c for q in raw['q15_cases'] for c in q['checks']]+[c for p in raw['q3_pairs'] for c in p['checks']]
failures=[c for c in allchecks if c['status'] in ('MISSING','MISMATCH','DEFERRED_READ_BUDGET')]
require(not failures,'identity audit has unresolved checks')
receipt={'status':'COMPLETE_REUSE_DISPOSITIONS_SCOPED','scope':'identity-gated reuse decisions, not replay/all-event reaudit',
         'q15_main_cases':sum(q['group']=='matrix_full_v2' for q in raw['q15_cases']),
         'q15_counterfactual_cases':sum(q['group']=='counterfactual_v1' for q in raw['q15_cases']),
         'q15_counterfactual_zero_deltas':sum(x['delta']==0 for x in raw['q15_pair_deltas']),
         'q3_seven_reconstructed':len(summary),'q3_remote_pairs_observed':len(raw['q3_pairs']),
         'check_status_counts':dict(collections.Counter(c['status'] for c in allchecks)),
         'raw_evidence_sha256':file_hash(ROOT/'evidence/REUSE_FRESH_RAW.json'),
         'matched_cycle_cases':0,'raw_events_replayed':False,'rows':rows,
         'other_assets':[
             {'asset':'183 Q15 projections','reuse':'exact payload equality from v3, use under explicit profile ownership; no cycle inheritance'},
             {'asset':'old Q15 four numerics','reuse':'old normalized layer0 FP16 tolerance scope only'},
             {'asset':'old joint backend','reuse':'33 verified link objects/source ABI, not old composite cycles'},
             {'asset':'Q3 old FP16','reuse':'do not substitute for BF16 model'},
             {'asset':'old stage1/stage2 and 288-case formula','reuse':'methods and already-seen historical controls; not independent TEST or new B cycles'}]}
(ROOT/'evidence/REUSE_DISPOSITIONS.json').write_text(json.dumps(receipt,ensure_ascii=False,indent=2),encoding='utf-8')
with (ROOT/'REUSE_DECISIONS.csv').open('w',newline='',encoding='utf-8-sig') as f:
    writer=csv.DictWriter(f,fieldnames=['model','case','source','group','cycle_reuse_allowed','missing','differences','reuse'])
    writer.writeheader()
    for row in rows:writer.writerow({**{k:row[k] for k in ('model','case','source','group','reuse')},
          'cycle_reuse_allowed':False,'missing':'|'.join(row['verdict']['missing']),'differences':'|'.join(row['verdict']['differences'])})
print(json.dumps({k:v for k,v in receipt.items() if k not in ('rows','other_assets')}))

"""Server-free preparation. Synthetic fixtures never constitute model evidence."""
import csv,gzip,hashlib,json,subprocess,sys,tempfile
from pathlib import Path
from paging_preflight import budget
from tiered_pages import selftest

ROOT=Path(__file__).resolve().parent
def main():
    definition=json.loads((ROOT/'experiment_definition.json').read_text())
    matrix=[]
    for context in definition['contexts_screen']:
        for policy in ('fixed_source_order','exploratory_high_skew'):
            for batch in definition['scales']:
                assert budget(context,batch)['combined_capacity_possible']
                for rep in range(1,6):
                    for scheme in definition['schemes']:
                        for intervention in ('normal','no_bank','no_noc','no_bank_no_noc'):
                            matrix.append(dict(context=context,policy=policy,batch=batch,rep=rep,scheme=scheme,intervention=intervention,hiband=scheme in ('hiband','hiband_sem_moe'),sem_moe=scheme in ('sem_moe','hiband_sem_moe'),status='BLOCKED_UNTIL_IMPLEMENTATION_AND_INTERVENTION_VALIDATION'))
    out=ROOT/'offline_artifacts';out.mkdir(exist_ok=True)
    with (out/'planned_matrix.csv').open('w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(matrix[0]));w.writeheader();w.writerows(matrix)
    tests=[]
    with tempfile.TemporaryDirectory(prefix='qwen3_offline_') as tmp:
        root=Path(tmp)
        # Request IDs and experts below are synthetic parser/DAG test fixtures.
        for context,batch,steps,micro in ((128,1,2,0),(512,16,2,0),(128,4,2,1)):
            source=root/f'results/routes_context{context}';source.mkdir(parents=True,exist_ok=True)
            records=[dict(request_id=f'fixture{i}') for i in range(100)]
            (source/'trace_manifest.json').write_text(json.dumps(dict(records=records)))
            with gzip.open(source/'routing_trace.csv.gz','wt',newline='') as f:
                w=csv.DictWriter(f,fieldnames=['request_id','position','layer','token_id','expert']);w.writeheader()
                for step in range(steps):
                    for layer in range(48):
                        for req in range(20,20+batch):
                            for k in range(8):w.writerow(dict(request_id=f'fixture{req}',position=context+step,layer=layer,token_id=req,expert=(req*8+k)%128))
            graph=root/f'graph{context}'
            cmd=[sys.executable,str(ROOT/'build_paging_smoke.py'),'--root',str(root),'--context',str(context),'--batch',str(batch),'--steps',str(steps),'--out',str(graph)]
            if micro:cmd+=['--microbatch-size',str(micro),'--hiband']
            p=subprocess.run(cmd,capture_output=True,text=True)
            if p.returncode:raise RuntimeError(p.stderr)
            manifest=json.loads((graph/'graph_manifest.json').read_text())
            with (graph/'ops.csv').open(newline='') as f:ops=list(csv.DictReader(f))
            with (graph/'deps.csv').open(newline='') as f:deps=list(csv.DictReader(f))
            parents={int(o['id']):set() for o in ops}
            bytask={o['task']:o for o in ops}
            assert len(bytask)==len(ops), 'duplicate operation names'
            for d in deps:parents[int(d['dst'])].add(int(d['src']))
            for page in manifest['page_operations']:
                assert page['fetch'] in parents[page['evict']]
                assert page['evict'] in parents[page['commit']]
                read=bytask[ops[page['fetch']]['task'].replace('_fetch','_weight_read')]
                assert page['commit'] in parents[int(read['id'])]
            assert manifest['hits']+manifest['misses']==sum(o['task'].endswith('_SwiGLU') for o in ops)
            tests.append(dict(context=context,batch=batch,steps=steps,microbatch_size=manifest['microbatch_size'],status='PASS',operations=len(ops),page_misses=manifest['misses'],evidence_type='SYNTHETIC_TEST_ONLY'))
    report=dict(status='PASS',matrix_rows=len(matrix),base_runs=len(matrix)//4,graph_tests=tests,tiered_pages=selftest(),limitations=['No server accessed or simulation launched','Synthetic routes validate code structure only, not Qwen performance','Planning table is not a results table','No statistical or Bank bottleneck claim'])
    (out/'validation.json').write_text(json.dumps(report,indent=2)+'\n')
    # Snapshot inventory, not immutable bundle: mutable files must be rehashed.
    hashes={p.relative_to(ROOT).as_posix():hashlib.sha256(p.read_bytes()).hexdigest() for p in ROOT.rglob('*') if p.is_file() and '__pycache__' not in p.parts and p.name!='local_inventory.json'}
    (out/'local_inventory.json').write_text(json.dumps(dict(type='MUTABLE_LOCAL_SNAPSHOT_NOT_FINAL_PROVENANCE',sha256=hashes),indent=2)+'\n')
    print(json.dumps(report,indent=2))
if __name__=='__main__':main()

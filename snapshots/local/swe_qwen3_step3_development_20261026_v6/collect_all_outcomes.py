"""Collect final task trees including staged/untracked edits; never edit source/tests."""
import json,subprocess,hashlib
from pathlib import Path
ROOT=Path(__file__).resolve().parent
OLD=ROOT.parent/'swe_qwen3_step3_gpu_20261026_v1'

def cmd(args):
    p=subprocess.run(args,capture_output=True,text=True,timeout=60)
    if p.returncode:raise RuntimeError(dict(args=args,stdout=p.stdout,stderr=p.stderr))
    return p.stdout

def main():
    registration=[x for x in json.loads((OLD/'TASK_REGISTRATION.json').read_text())['tasks'] if x['split']=='dev']
    predictions=[];audits=[]
    for task in registration:
        out=ROOT/task['instance_id']
        result_path=out/'RESULT.json' if (out/'RESULT.json').exists() else out/'FAILURE.json'
        if not result_path.exists():continue
        result=json.loads(result_path.read_text());cid=result['container_id'];base=task['base_commit']
        inspect=json.loads(cmd(['docker','inspect',cid]))[0]
        assert inspect['Config']['Labels'].get('swe_qwen3_step3_v2')=='1'
        assert inspect['HostConfig']['NetworkMode']=='none'
        if inspect['State']['Running']:raise RuntimeError('Wait for original task container to stop')
        cmd(['docker','start',cid])
        try:
            original=cmd(['docker','exec',cid,'git','diff','--binary'])
            staged=cmd(['docker','exec',cid,'git','diff','--cached','--name-only'])
            untracked=cmd(['docker','exec',cid,'git','ls-files','--others','--exclude-standard'])
            cmd(['docker','exec',cid,'git','add','--intent-to-add','.'])
            patch=cmd(['docker','exec',cid,'git','diff','--binary',base])
            paths=cmd(['docker','exec',cid,'git','diff','--name-only',base]).splitlines()
            baseline_tests=set(cmd(['docker','exec',cid,'git','ls-tree','-r','--name-only',base,'tests']).splitlines())
            changed_tests=sorted(set(paths)&baseline_tests)
            (out/'COMPLETE_PATCH.diff').write_text(patch)
            audit=dict(instance_id=task['instance_id'],container_id=cid,base_commit=base,changed_paths=paths,changed_existing_tests=changed_tests,
                test_preservation_contract_pass=not changed_tests,untracked_before_collection=untracked.splitlines(),staged_paths_before_collection=staged.splitlines(),
                original_diff_matches_saved=original==(out/'PATCH.diff').read_text() if (out/'PATCH.diff').exists() else None,complete_patch_sha256=hashlib.sha256(patch.encode()).hexdigest(),
                generation_outcome_file=result_path.name,controlled_stagnation_stop=(out/'STAGNATION_STOP.json').exists(),
                test_edit_rejections=[x for x in json.loads((out/'TOOL_EVENTS_GUARD.json').read_text()) if x.get('kind')=='protected_tests_restored'],
                scope='snapshot collection only, git index intent metadata changed; source/test contents not edited; model output not repaired')
            (out/'PATCH_CONTRACT_AUDIT.json').write_text(json.dumps(audit,indent=2));audits.append(audit)
            predictions.append(dict(instance_id=task['instance_id'],model_name_or_path='local_Qwen3_30B_A3B_BF16_v6',model_patch=patch))
        finally:cmd(['docker','stop','--time','2',cid])
    (ROOT/'predictions_complete.jsonl').write_text(''.join(json.dumps(x)+'\n' for x in predictions))
    (ROOT/'PATCH_CONTRACT_AUDIT.json').write_text(json.dumps(audits,indent=2))

if __name__=='__main__':main()

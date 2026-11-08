"""Run engineering regressions on native PopNet, not application performance."""
from pathlib import Path
from datetime import datetime,timezone
import collections,csv,hashlib,json,os,platform,subprocess,traceback

ROOT=Path(__file__).resolve().parent
BUILD=ROOT/'build'
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def switch_state(mapping):
    return sum((4+[i for i in range(4) if i!=o].index(mapping[o]))<<(3*o) for o in range(4))
def fixture(name,hold=3000,timeout=15000,length=17,credit=100,move=False):
    cells=(0,2,6,8)
    settings=[f'params 2 1 1 {credit} 1\n']
    plan=[f'timing 20 {timeout}\n','epoch 1\n','probe_bad_load 1\n','probe_stale_reply 1\n','probe_duplicate_arm 1\n']
    next_cell={n:((0 if n//4==0 else 2 if n//4==3 else 1)*3+(0 if n%4<2 else 2)) for n in range(16)} if move else {}
    for c in range(9):
        settings.append(f'cs {c} {switch_state([3,2,1,0]) if c in cells else 0}\n')
        if move:
            nodes=[4*(c//3)+c%3+i for i in (0,1,4,5)]
            state=0
            for i,g in enumerate(nodes):
                if next_cell[g]!=c:continue
                o=nodes.index(g^1);sel=[j for j in range(4) if j!=o].index(i)
                state|=(4+sel)<<(3*o)
        else:state=switch_state([1,0,3,2]) if c in cells else 0
        plan.append(f'cs {c} {state}\n')
    for n in range(16):
        cs=next(c for c in cells if n//4 in (c//3,c//3+1) and n%4 in (c%3,c%3+1))
        settings.extend([f'node {n} {16+cs} {16+cs}\n',f'hold {n} {hold}\n'])
        new_cs=next_cell[n] if move else cs
        plan.append(f'node {n} {16+new_cs} {16+new_cs}\n')
    records=[]
    for g in range(16):records.append((1,g^4,g^5,length,g,0))
    # One ordinary flit per NI: it waits for SRAM but cannot fill a Mesh VC
    # behind the deliberately blocked tensor FIFO and delay FREEZE until drain.
    # Long ordinary-packet backpressure is covered by the static mixed regression.
    for d in range(16):records.append((1.5,d^2,d,1,-1,0))
    for g in range(16):records.append((2,g^4,g^1,length,g,1))
    for i,(_,s,d,_,g,epoch) in enumerate(records):
        if g>=0:
            settings.append(f'route {i} {s} {d} {g}\n')
            plan.append(f'packet_epoch {i} {epoch}\n')
    (ROOT/'inputs'/f'{name}.cfg').write_text(''.join(settings))
    (ROOT/'inputs'/f'{name}.plan').write_text(''.join(plan))
    (ROOT/'inputs'/f'{name}.trace').write_text(''.join(f'{t} {s} {d} {n}\n' for t,s,d,n,_,_ in records))
    return records
def main():
    BUILD.mkdir(exist_ok=True)
    result={'status':'running','host':platform.node(),'application_performance':False,'commands':[]}
    report=BUILD/'validation.json'
    def save():report.write_text(json.dumps(result,indent=2)+'\n')
    def run(name,args,cwd=ROOT,env=None,expect=0,timeout=600):
        cwd.mkdir(parents=True,exist_ok=True)
        cp=subprocess.run(list(map(str,args)),cwd=cwd,env=env,capture_output=True,text=True,errors='replace',timeout=timeout)
        log=BUILD/(name+'.log');log.write_text(cp.stdout+cp.stderr)
        result['commands'].append({'name':name,'argv':list(map(str,args)),'cwd':str(cwd),'returncode':cp.returncode,'expected':expect,'log_sha256':sha(log)})
        save();assert cp.returncode==expect,(name,cp.returncode,cp.stderr[-1200:]);return cp
    save()
    try:
        fixtures={}
        fixtures['transition']=fixture('transition')
        fixture('timeout',hold=50000,timeout=4000)
        fixtures['credit_tail']=fixture('credit_tail',hold=0,length=1,credit=10000)
        fixture('credit_timeout',hold=0,timeout=4000,length=1,credit=50000)
        fixtures['selector_move']=fixture('selector_move',length=3,credit=30,move=True)
        run('cmake',['cmake','-S',ROOT,'-B',BUILD/'cmake','-DCMAKE_BUILD_TYPE=Release'])
        run('compile',['cmake','--build',BUILD/'cmake','-j2'])
        exe=BUILD/'cmake/popnet_cs_ni'
        common=['-A',16,'-c',1,'-V',3,'-B',8,'-O',8,'-F',4,'-R',4,'-G',ROOT/'inputs/target_mesh.gv','-T',30000,'-r',1]
        clean=os.environ.copy()
        for k in ('NOC_AUX_CONFIG','NOC_AUX_LOG','NOC_DYNAMIC_PLAN'):clean.pop(k,None)
        old=json.loads((ROOT/'reference_manifest.json').read_text())['original_binary']
        assert sha(Path(old['path']))==old['sha256']
        for tag,binary in [('original',old['path']),('disabled',exe)]:
            d=BUILD/tag
            run(tag,[binary]+common+['-I',ROOT/'inputs/baseline.trace','-T',160000,'-D',d/'delay.txt'],d,clean)
        assert (BUILD/'original/delay.txt').read_bytes()==(BUILD/'disabled/delay.txt').read_bytes()
        result['disabled_exact_reference_match']=True
        for name in ('mixed','sync'):
            d=BUILD/('static_'+name);env=clean.copy();env['NOC_AUX_CONFIG']=str(ROOT/'inputs'/f'{name}.cfg');env['NOC_AUX_LOG']=str(d/'events.csv')
            args=[exe]+common+['-I',ROOT/'inputs'/f'{name}.trace','-D',d/'delay.txt']
            if name=='sync':args+=['-P']
            run('static_'+name,args,d,env)
            reference=ROOT.parent/'noc_popnet_cs_ni_20261104/build'/name/'delay.txt'
            assert reference.read_bytes()==(d/'delay.txt').read_bytes(),name
        result['static_mixed_and_sync_exact_match']=True
        for name,expected in [('transition',0),('timeout',1),('credit_tail',0),('credit_timeout',1),('selector_move',0)]:
            d=BUILD/name;env=clean.copy()
            env['NOC_AUX_CONFIG']=str(ROOT/'inputs'/f'{name}.cfg');env['NOC_AUX_LOG']=str(d/'events.csv');env['NOC_DYNAMIC_PLAN']=str(ROOT/'inputs'/f'{name}.plan')
            run(name,[exe]+common+['-I',ROOT/'inputs'/f'{name}.trace','-D',d/'delay.txt'],d,env,expected)
            s=json.loads((d/'dynamic_summary.json').read_text())
            control=list(csv.DictReader((d/'control_events.csv').open()))
            commits=[r for r in control if r['event']=='COMMIT']
            if expected==1:
                assert not s['passed'] and s['reason']=='stage_timeout' and s['frozen_nodes']==16
                assert not commits and not any(r['event']=='RUN' for r in control)
                assert s['stage']==(2 if name=='timeout' else 3)
                result[name+'_fail_closed']=s;continue
            records=fixtures[name]
            assert s['passed'] and s['frozen_nodes']==0 and s['nacks']>=1 and s['ignored_responses']>=1
            assert s['duplicate_arm_preserved']
            assert len(commits)==41
            barrier=[r for r in control if r['event']=='COUNT_BARRIER']
            expected_old=sum(r[3] for r in records if r[4]>=0 and r[5]==0)
            if name=='transition':assert any(int(r['accepted'])>int(r['written']) for r in barrier),'no old traffic in flight at count barrier'
            elif name=='credit_tail':assert any(r['event']=='NACK' and r['stage']=='3' for r in control),'final-credit waiting not exercised'
            assert int(barrier[-1]['accepted'])==int(barrier[-1]['written'])==expected_old
            arm=[float(r['time']) for r in control if r['event']=='ARM'];restart=[float(r['time']) for r in control if r['event']=='RUN']
            assert len(arm)==len(restart)==16 and max(arm)<min(restart)
            events=list(csv.DictReader((d/'events.csv').open()))
            app=[r for r in events if int(r['packet'])<(1<<62)]
            counts=collections.Counter(r['event'] for r in app)
            assert counts['INJECT']==counts['WRITE_AUX']+counts['WRITE_MESH']==sum(r[3] for r in records)
            assert counts['WRITE_AUX']==2*expected_old and counts['WRITE_MESH']==16 and counts['COMPLETE']==48
            assert len((d/'delay.txt').read_text().splitlines())==48,'control traffic leaked into application transaction output'
            groups=collections.defaultdict(list)
            for r in app:groups[int(r['packet'])].append(r)
            for i,(t,src,dst,n,g,epoch) in enumerate(records):
                rows=groups[i]
                assert len([r for r in rows if r['event']=='INJECT'])==n
                wr=[r for r in rows if r['event'].startswith('WRITE_')]
                assert len(wr)==n and [int(r['ordinal']) for r in wr]==list(range(n))
                assert all(int(r['node'])==dst for r in wr)
                done=[r for r in rows if r['event']=='COMPLETE'];assert len(done)==1 and done[0]['time']==wr[-1]['time']
                if epoch==1:assert min(float(r['time']) for r in rows if r['event']=='INJECT')>=min(restart)
            writes=collections.Counter((r['time'],r['node']) for r in events if r['event'].startswith('WRITE_'))
            assert max(writes.values())==1,'control and data bypassed single physical NI write slot'
            if name=='credit_tail':
                assert max(float(r['time']) for r in events if r['event']=='CONTROL_ACCEPT')>max(float(r['time']) for r in app if r['event']=='COMPLETE'),'pending control after application completion not exercised'
            result[name]={'controller':s,'application_counts':dict(counts),'barriers':len(barrier),'all_arms_before_any_run':True}
        result['sha256']={p.relative_to(ROOT).as_posix():sha(p) for folder in ('adapter','inputs') for p in sorted((ROOT/folder).rglob('*')) if p.is_file()}
        for name in ('run_validation.py','main_bridge.cc','CMakeLists.txt','reference_manifest.json'):result['sha256'][name]=sha(ROOT/name)
        result['sha256']['build/cmake/popnet_cs_ni']=sha(exe)
        for p in sorted(BUILD.rglob('*')):
            if p.is_file() and 'cmake' not in p.parts and 'attempts' not in p.parts and p!=report and p.suffix in ('.csv','.json','.txt'):
                result['sha256'][p.relative_to(ROOT).as_posix()]=sha(p)
        result['status']='passed_dynamic_control_native_popnet';save();print(json.dumps(result,indent=2))
    except BaseException as e:
        result['status']='failed';result['error']=str(e);save();traceback.print_exc();raise
if __name__=='__main__':main()

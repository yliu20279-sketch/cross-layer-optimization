"""Bounded CPU functional checks using real checkpoint operands; no benchmark.

One normalized-input MoE block per model on deterministic diagnostic vectors,
three Q15 Q/K/V projections with retained bias, and all-object BF16 byte spans.
No complete attention/model execution, no GPU, no target/performance run.
"""
from pathlib import Path
import hashlib
import json
import sys
import numpy as np

ROOT=Path(__file__).resolve().parents[1]
sys.path.insert(0,str(ROOT))
from core.artifacts import TargetArtifactStore
from core.native_payload import NativePayload
from core.payload_collectives import HostPayloadTransport,srs_payload,sag_payload
from core.scheduling import DecisionInput
from core.common import digest,require
from models.qwen3.build_graph import execute_moe as q3_moe
from models.qwen15.build_graph import execute_moe as q15_moe

receipt_path=ROOT/'evidence/PAYLOAD_AUDIT_v2.json'
require(not receipt_path.exists(),'preserve previous completed audit')

def read(p):return json.loads(Path(p).read_text())
build=read(ROOT/'evidence/BUILD_LIVE_02.json')
native=NativePayload(build['payload_library'],build['payload_sha256'])
source=Path('/mnt/sda1/h3240101068/ca_semmoe_hiband_fp16_20261102_v3')
q15_manifest=read(source/'decoded_assets/TARGET_MANIFEST_ARCHIVEFREE.json')
q3_inv=read(ROOT/'contracts/qwen3_tensor_inventory.json')['objects']
offsets={x['file']:x for x in read(ROOT/'evidence/Q3_PAYLOAD_OFFSETS.json')}
q3_manifest=[];headers={}
for filename,row in offsets.items():
    with Path(filename).open('rb') as f:
        n=int.from_bytes(f.read(8),'little');raw=f.read(n)
    require(n+8==row['payload_offset'] and hashlib.sha256(raw).hexdigest()==row['header_sha256'],'Q3 source header changed')
    headers[filename]=json.loads(raw)
for name,obj in q3_inv.items():
    entry=headers[obj['file']][name]
    require(entry['dtype']=='BF16' and entry['shape']==obj['shape'] and entry['data_offsets']==obj['offsets'],'Q3 header/inventory differs')
    q3_manifest.append({'name':name,'dtype':'BF16','shape':obj['shape'],'bytes':obj['bytes'],'layout':'output_major',
                        'header_sha256':obj['header_sha256'],'checkpoint_sha256':obj['checkpoint_sha256'],
                        'parts':[{'file':obj['file'],'offset':offsets[obj['file']]['payload_offset']+obj['offsets'][0],
                                  'bytes':obj['bytes'],'shape':obj['shape'],'dtype':'BF16'}]})
(ROOT/'contracts/qwen3_target_manifest.json').write_text(json.dumps(q3_manifest))
stores={'qwen3':TargetArtifactStore(q3_manifest,'BF16'),'qwen15':TargetArtifactStore(q15_manifest,'F16')}
spans=0
objects=list(stores['qwen3'].objects.items())
selected={i*len(objects)//128 for i in range(128)}
files=set()
for i,(name,obj) in enumerate(objects):
    file=obj['parts'][0]['file']
    if file not in files:selected.add(i);files.add(file)
for index in sorted(selected):
    name,obj=objects[index]
    for start in sorted({0,max(0,obj['bytes']//2-16),max(0,obj['bytes']-32)}):
        data=stores['qwen3'].read(name,start,min(32,obj['bytes']-start));require(data,'short BF16 span');spans+=1

# Exhaustive finite-domain codec identity, independent NumPy FP16 conversion
# and direct BF16 float32 bit construction. NaN payload encoding is not claimed.
codes=np.arange(65536,dtype='<u2');codec={}
for dtype in ('F16','BF16'):
    got=native.decode(codes.tobytes(),dtype)
    ref=codes.view('<f2').astype('<f4') if dtype=='F16' else (codes.astype('<u4')<<16).view('<f4')
    finite=np.isfinite(ref)
    require(np.array_equal(got[finite].view('<u4'),ref[finite].view('<u4')),'native codec differs')
    roundtrip=np.frombuffer(native.encode(got,dtype),dtype='<u2')
    require(np.array_equal(roundtrip[finite],codes[finite]),'16-bit codec roundtrip differs')
    require(np.array_equal(np.isnan(got),np.isnan(ref)) and np.array_equal(np.isinf(got),np.isinf(ref)), 'nonfinite class differs')
    codec[dtype]={'finite_checked':int(finite.sum()),'nan_inf_class_checks':True}

collectives={}
for dtype,ranks in [('F16',4),('BF16',16)]:
    transport=HostPayloadTransport(native);width=2048;tokens=5
    # Exactly representable diagnostic integers make rank-order reference clear.
    partials=[[native.encode(np.full(width,(r+t)%7,dtype='<f4'),dtype) for t in range(tokens)] for r in range(ranks)]
    destinations=[(3*t+1)%ranks for t in range(tokens)]
    shards=srs_payload(partials,destinations,dtype,native,transport)
    replicas=sag_payload(shards,tokens,native,transport)
    for token,payload in enumerate(replicas[0]):
        require(np.all(native.decode(payload,dtype)==sum((r+token)%7 for r in range(ranks))),'SRS/SAG numerical mismatch')
    require(len(transport.events)==2*(ranks-1)*tokens,'collective all-peer bytes mismatch')
    collectives[dtype]={'ranks':ranks,'tokens':tokens,'width':width,'packets':len(transport.events),
                         'payload_bytes':sum(x['bytes'] for x in transport.events),'target_noc':False}

moe={}
for name,execute,experts,ep,layers,dtype in [('qwen3',q3_moe,128,16,48,'BF16'),('qwen15',q15_moe,60,4,24,'F16')]:
    # Explicit diagnostic-only profile table. Does not open or relabel TEST data.
    placement={'method':'diagnostic-static-table','ep':ep,'experts':experts,'layers':{
        str(i):{'expert_to_rank':{str(e):e%ep for e in range(experts)},'token_to_rank':{'17':0}} for i in range(layers)}}
    transport=HostPayloadTransport(native)
    data=DecisionInput(request_id='diagnostic_only',position=0,token_id=17,layer=0,available_at=0,decision_at=0)
    operand=native.encode(np.arange(2048,dtype='<f4')%13/128,dtype)
    before=stores[name].served_bytes
    result=execute(placement,[{'decision_input':data,'normalized_input':operand}],stores[name],native,transport)
    output=result['replicas'][0][0]
    require(len(output)==4096 and np.isfinite(native.decode(output,dtype)).all(),'invalid MoE output')
    moe[name]={'scope':result['scope'],'operations':result['operations'],'output_sha256':hashlib.sha256(output).hexdigest(),
               'read_bytes':stores[name].served_bytes-before,'transfers':transport.events,
               'original_model_numerics_verified':False,'target_timing':False}

qkv=[]
store=stores['qwen15'];x=native.encode(np.arange(2048,dtype='<f4')%11/256,'F16')
for kind in ('q_proj','k_proj','v_proj'):
    prefix='model.layers.0.self_attn.'+kind
    w=store.objects[prefix+'.weight'];bias=store.objects[prefix+'.bias']
    weight=store.read(w['name'],0,w['bytes']);b=store.read(bias['name'],0,bias['bytes'])
    k,n=w['shape'];out=native.linear(x,weight,1,k,n,'F16','input_major',b)
    # Independent scalar FP32 reduction for a fixed spread of output columns.
    a=np.frombuffer(x,dtype='<f2').astype('<f4');matrix=np.frombuffer(weight,dtype='<f2').reshape(k,n).astype('<f4')
    actual=np.frombuffer(out,dtype='<u2');columns=sorted({0,n//2,n-1})
    for j in columns:
        total=np.float32(0)
        for begin in range(0,k,64):
            partial=np.float32(0)
            for i in range(begin,min(k,begin+64)):partial=np.float32(partial+np.float32(a[i]*matrix[i,j]))
            total=np.float32(total+partial)
        total=np.float32(total+np.frombuffer(b,dtype='<f2')[j])
        require(actual[j]==np.asarray(total,dtype='<f2').view('<u2'),'QKV retained-bias kernel differs')
    qkv.append({'projection':prefix,'shape_KN':[k,n],'checked_columns':columns,'bias_applied':True})

receipt={'status':'PASS_CPU_PAYLOAD_INTEGRATION_SCOPED','codec':codec,'collectives':collectives,'moe':moe,'q15_qkv':qkv,
         'q3_object_count':len(q3_manifest),'q3_sampled_objects':len(selected),'q3_sampled_shards':len(files),
         'q3_sampled_spans':spans,'native_library_sha256':native.sha256,
         'q3_byte_service_read_bytes':stores['qwen3'].served_bytes,'full_attention_or_model':False,
         'target_simulations':0,'gpu_runs':0,'formal_performance_runs':0,'original_model_oracle_compared':False}
receipt['sources']={str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest()
                    for directory in ('core','models') for p in (ROOT/directory).rglob('*.py')}
receipt_path.write_text(json.dumps(receipt,indent=2))
print(json.dumps({'status':receipt['status'],'q3_objects':len(q3_manifest),'q3_spans':spans,'moe_ops':{k:len(v['operations']) for k,v in moe.items()},'formal_performance_runs':0}))

"""Read saved evidence only; no model forward and no CUDA context."""
import pathlib,json,hashlib,datetime,collections,subprocess,os
import torch
import imageio_ffmpeg

P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_steps1_2_20261027_v1')
A=P/'attempt2'
ASSET=pathlib.Path('/mnt/sda1/models/LingBot-Video-MoE-30B-A3B-TI2V-base-f2e538f64afe')
torch.set_num_threads(1)
result={'checked_utc':datetime.datetime.utcnow().isoformat(),'kind':'INDEPENDENT_SAVED_EVIDENCE_AUDIT_NO_MODEL_RUN','checks':[]}
def check(name,value,**kw):
    assert value,(name,kw)
    result['checks'].append(dict(name=name,passed=True,**kw))

final=json.loads((A/'FINAL_REFERENCE.json').read_text())
check('external_reference_pass',final['status']=='PASS_LIMITED_EXTERNAL_GPU_REFERENCE')
check('target_GPU_count_zero',final['target_gpu_count']==0)
check('target_execution_not_claimed',not final['target_execution_certified'] and not final['target_timing_certified'])
runs=json.loads((A/'REFERENCE_RUNS.json').read_text())
boundaries=json.loads((A/'FORWARD_BOUNDARY_LOG.json').read_text())
check('forward_boundary_layer0_count',sum(x['layer']==0 for x in boundaries)==82)
check('forward_boundary_layer47_count',sum(x['layer']==47 for x in boundaries)==82)
for steps in [1,40]:
    x=torch.load(A/('latent_%dstep.pt'%steps),map_location='cpu',weights_only=True)
    check('latent_shape_'+str(steps),list(x.shape)==[1,16,31,60,104])
    check('latent_F32_'+str(steps),x.dtype==torch.float32)
    check('latent_finite_'+str(steps),bool(torch.isfinite(x).all()))
    h=hashlib.sha256(x.contiguous().numpy().tobytes()).hexdigest()
    check('latent_raw_SHA256_'+str(steps),h==runs[str(steps)]['sha256_raw_FP32'],sha256=h)
    check('actual_forward_count_'+str(steps),runs[str(steps)]['forwards']==steps*2)
    check('scheduler_steps_'+str(steps),len(runs[str(steps)]['scheduler_timesteps'])==steps)

head=json.loads((ASSET/'OPERATOR_GRAPH_HEADER_AUDIT_20261027.json').read_text())
loaded=json.loads((A/'LOADED_DTYPE_AUDIT.json').read_text())
for part,rows in head['parts'].items():
    expected=collections.Counter()
    for row in rows:
        if row['name'].endswith('.router.e_score_correction_bias'):continue
        expected[{'F32':'torch.float32','BF16':'torch.bfloat16'}[row['dtype']]]+=row['elements']
    check('loaded_dtype_elements_'+part,dict(expected)==loaded[part],expected=dict(expected),actual=loaded[part])

manifest=json.loads((ASSET/'DOWNLOAD_MANIFEST.json').read_text())
sources=[]
for row in manifest:
    if not row['path'].startswith('source/'):continue
    q=ASSET/row['path'];data=q.read_bytes()
    h=hashlib.sha1(('blob %d\0'%len(data)).encode()+data).hexdigest()
    assert h==row['git_blob']
    sources.append(dict(path=row['path'],git_blob=h))
check('source_git_blob_unchanged',len(sources)==93,count=len(sources))
check('refiner_weights_absent',not (ASSET/'model/refiner').exists())

video=imageio_ffmpeg.read_frames(str(A/'reference_40step.mp4'),pix_fmt='rgb24')
metadata=next(video);n=0;preview_hashes=[]
for frame in video:
    assert len(frame)==480*832*3
    if n in [0,30,60,90,120]:preview_hashes.append(dict(frame=n,sha256=hashlib.sha256(frame).hexdigest()))
    n+=1
check('decoded_video_frame_count',n==121,count=n)
check('decoded_video_size',tuple(metadata['size'])==(832,480),size=metadata['size'])
check('decoded_video_fps',abs(metadata['fps']-24)<1e-6,fps=metadata['fps'])
result['decoded_preview_hashes']=preview_hashes
result['video_metadata']=metadata
result['source_files']=sources
result['status']='PASS_LIMITED_SAVED_REFERENCE_AND_DTYPE_INTEGRITY'
result['limitations']=['not target NPU execution or timing','not video-quality benchmark','no route IDs/weights trace captured yet','not backend-equivalence test against recommended nightly']
(P/'INDEPENDENT_REFERENCE_AUDIT.json').write_text(json.dumps(result,indent=2),encoding='utf8')
files=[q for q in P.rglob('*') if q.is_file() and 'venv' not in q.relative_to(P).parts and q.name!='EVIDENCE_MANIFEST.json']
members={str(q.relative_to(P)):{'bytes':q.stat().st_size,'sha256':hashlib.sha256(q.read_bytes()).hexdigest()} for q in sorted(files)}
(P/'EVIDENCE_MANIFEST.json').write_text(json.dumps(members,indent=2),encoding='utf8')
print(json.dumps({'status':result['status'],'checks':len(result['checks']),'files':len(members),'bytes':sum(x['bytes'] for x in members.values()),'video_frames':n}))

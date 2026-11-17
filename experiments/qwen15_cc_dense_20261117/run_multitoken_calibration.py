"""Run the 8-endpoint layer using the original FP16/K64 target operators."""

from collections import Counter, defaultdict
import hashlib
import json
from pathlib import Path
import struct
import sys
import traceback

import numpy as np


ROOT, BINARY, OUT = (Path(arg).resolve() for arg in sys.argv[1:4])
TOKENS, SEED = map(int, sys.argv[4:6])
ARM = sys.argv[6]
sys.path.insert(0,str(ROOT))

from core.artifacts import TargetArtifactStore
from core.coupled_backend import CoupledPayload, LiveBackend, MAGIC
from core.coupled_layer import CoupledLayer
from core.live_moe import MoEPayloadExecutor
from models.qwen15 import SPEC
from models.qwen15.fp16_math import sigmoid32


def digest(payload):
    return hashlib.sha256(payload).hexdigest()


def dump(path, data):
    path.write_text(json.dumps(data,indent=2)+'\n')


def read(path):
    return json.loads(path.read_text())


class TiledPayload(CoupledPayload):
    def linear(self, activation, weight, m, k, n, dtype, layout, bias=None, _output_fp32=False):
        parts = []
        for start in range(0,m,16):
            rows = min(m-start,16)
            part = activation[start*k*2:(start+rows)*k*2]
            parts.append(super().linear(part,weight,rows,k,n,dtype,layout,bias,_output_fp32))
            if len(self.calls)%8==0:
                print(json.dumps(dict(event='matrix_progress',count=len(self.calls),label=self.label,
                                      clock_ns=self.backend.clock)),flush=True)
        return b''.join(parts)


class WaveTransport:
    def __init__(self, backend, arm):
        self.backend = backend
        self.events = []
        self.waves = []
        mode = {'mesh_prerequisite':0,'hiband_reference':1,'project_noc':2}[arm]
        self.routes = None
        if mode == 2:
            from planner import wired_paths
            self.routes = wired_paths()
        self.command(17,mode)

    def command(self, op, count, payload=b''):
        backend = self.backend
        backend.process.stdin.write(struct.pack('<8Q',op,count,0,0,0,0,0,0)+payload)
        backend.process.stdin.flush()
        reply = struct.unpack('<8Q',backend._read(64))
        assert reply[0]==MAGIC
        if reply[1]:
            raise RuntimeError(backend._read(reply[2]).decode())
        backend.clock = reply[7]
        return reply

    def send_wave(self, stage, transfers, calibration_circuits=()):
        """Return tensor payloads only after their destinations have committed."""
        if not transfers:
            return {}
        b = self.backend
        handles = []
        rows = []
        ready = b.clock
        circuits, decision = (),None
        if self.routes is not None:
            from multitoken_circuit_plan import select
            circuits,decision = select([(s,d,len(p)) for _,s,d,p in transfers],self.routes)
            if calibration_circuits:
                circuits = calibration_circuits
                decision['forced_transport_probe'] = True
        encoded = {(p.src,p.dst):(i,len(p.switches)) for i,p in enumerate(circuits,1)}
        try:
            assert len({key for key,_,_,_ in transfers})==len(transfers)
            for _,src,dst,payload in transfers:
                source = b.stage(src,payload)
                handles.append(source)
                destination = b.alloc(dst,len(payload))
                handles.append(destination)
                path,hops = encoded.get((src,dst),(0,0))
                rows.extend((source,destination,len(payload),path,hops))
            count = len(transfers)
            reply = self.command(18,count,struct.pack(f'<{len(rows)}Q',*rows))
            stamps = struct.unpack(f'<{count*4}Q',b._read(count*4*8))
            payloads = {}
            first_event = len(self.events)
            for i,(key,src,dst,expected) in enumerate(transfers):
                raw = b.get(rows[5*i+1])
                assert raw==expected,'endpoint transfer changed the tensor'
                payloads[key]=raw
                begin,inject,wire_done,commit = stamps[4*i:4*i+4]
                path = rows[5*i+3]
                assert ready<=begin<=inject<wire_done<=commit<=b.clock
                if path:
                    assert inject>=begin+40
                self.events.append(dict(stage=stage,key=key,src=src,dst=dst,bytes=len(raw),ready_ns=ready,
                                        release_ns=begin,inject_ns=inject,wire_done_ns=wire_done,
                                        commit_ns=commit,circuit=path,payload_sha256=digest(raw)))
            wave = dict(stage=stage,ready_ns=ready,complete_ns=b.clock,first=first_event,count=count,
                        local_budget=reply[2],global_budget=reply[3],policy_decision=decision)
            self.waves.append(wave)
            print(json.dumps(wave),flush=True)
            return payloads
        except BaseException:
            b.abort()
            raise
        finally:
            for handle in reversed(handles):
                if not b.closed:
                    b.free(handle)


def slices(raw,width,count):
    assert len(raw)==width*count
    return [raw[i*width:(i+1)*width] for i in range(count)]


def with_parallel_transfers(placements, spec, store, native, transport, cfg, positions, hidden):
    layer_number = 5
    tp, h = spec['tp'], spec['hidden']
    width = h*2
    assert tp==4 and layer_number//spec['layers_per_stage']==0
    tokens = len(positions)
    owners = [i%tp for i in positions]
    # The original TP4 attention numerical path is unchanged. EP placement is
    # applied explicitly to the sparse expert branch after real router output.
    layer = CoupledLayer(spec,cfg,store,native,transport,placements,'F16')
    helper = MoEPayloadExecutor(spec,store,native,transport,'F16')
    layer.request_owner = 1
    start = native.backend.clock
    prefix = f'model.layers.{layer_number}'
    mlp = prefix+'.mlp'
    try:
        attention = [slices(layer._rank_attention(hidden,tokens,positions,layer_number,rank,helper),width,tokens)
                     for rank in range(tp)]
        reduced = transport.send_wave('attention_SRS',[
            ((i,rank),rank,owner,attention[rank][i]) for i,owner in enumerate(owners)
            for rank in range(tp) if rank!=owner])
        normalized, residuals = [], []
        original = slices(hidden,width,tokens)
        # Residual rows are the common input, pre-positioned on their TP owner.
        for i,owner in enumerate(owners):
            native.select_partition(owner,'attention_residual_reduce')
            value = native.sum([attention[r][i] if r==owner else reduced[i,r] for r in range(tp)],'F16')
            residual = native.binary(original[i],value,'F16')
            residuals.append(residual)
            normalized.append(layer._rms(residual,(1,h),prefix+'.post_attention_layernorm.weight'))
        moe_start = native.backend.clock
        routes = [None]*tokens
        for rank in range(tp):
            indices = [i for i,owner in enumerate(owners) if owner==rank]
            logits = helper._linear(b''.join(normalized[i] for i in indices),mlp+'.gate',rank)
            for i,row in zip(indices,slices(logits,spec['experts']*2,len(indices))):
                route = native.software_op('router_softmax_topk_mass_and_storage_cast',[row],
                                           lambda parts:helper._route_descriptor(parts[0]))
                count = spec['topk']
                ids = np.frombuffer(route[:count*8],dtype='<u8').tolist()
                weights = np.frombuffer(route[count*8:],dtype='<f4').tolist()
                routes[i] = dict(token=i,owner=rank,selected=ids,weights=weights,
                                 expert_ranks=[placements[int(e)] for e in ids],ready_ns=native.backend.clock)
        dispatch, dispatch_work = {}, []
        by_expert = defaultdict(list)
        for i,route in enumerate(routes):
            owner = route['owner']
            for expert,dst in zip(route['selected'],route['expert_ranks']):
                by_expert[expert].append(i)
                if owner==dst:
                    dispatch[i,expert]=normalized[i]
                else:
                    dispatch_work.append(((i,expert),owner,dst,normalized[i]))
        dispatch.update(transport.send_wave('dispatch',dispatch_work))
        sparse_result = {}
        for expert,indices in sorted(by_expert.items()):
            rank = placements[expert]
            path = f'{mlp}.experts.{expert}'
            operand = b''.join(dispatch[i,expert] for i in indices)
            gate = helper._linear(operand,path+'.gate_proj',rank)
            up = helper._linear(operand,path+'.up_proj',rank)
            value = helper._linear(helper._activation(gate,up),path+'.down_proj',rank)
            sparse_result.update({(i,expert):row for i,row in zip(indices,slices(value,width,len(indices)))})
        sparse_result.update(transport.send_wave('combine',[
            (key,placements[key[1]],owners[key[0]],row) for key,row in sparse_result.items()
            if placements[key[1]]!=owners[key[0]]]))
        shared_path = mlp+'.shared_expert'
        weight = store.objects[shared_path+'.gate_proj.weight']
        shared_width = weight['shape'][1] if weight['layout']=='input_major' else weight['shape'][0]
        assert shared_width%tp==0
        shared_input = transport.send_wave('shared_input',[
            ((i,rank),owner,rank,normalized[i]) for i,owner in enumerate(owners) for rank in range(tp) if rank!=owner])
        shared_result = {}
        for rank in range(tp):
            low,high = rank*(shared_width//tp),(rank+1)*(shared_width//tp)
            operand = b''.join(normalized[i] if rank==owners[i] else shared_input[i,rank] for i in positions)
            gate = helper._linear(operand,shared_path+'.gate_proj',rank,[0,h,low,high])
            up = helper._linear(operand,shared_path+'.up_proj',rank,[0,h,low,high])
            activation = helper._activation(gate,up)
            padded = np.zeros((tokens,shared_width),dtype='<u2')
            padded[:,low:high] = np.frombuffer(activation,dtype='<u2').reshape(tokens,high-low)
            partial = helper._linear(padded.tobytes(),shared_path+'.down_proj',rank,[low,high,0,h])
            shared_result.update({(i,rank):row for i,row in enumerate(slices(partial,width,tokens))})
        shared_result.update(transport.send_wave('shared_reduce',[
            (key,key[1],owners[key[0]],row) for key,row in shared_result.items() if key[1]!=owners[key[0]]]))
        results = []
        for i,route in enumerate(routes):
            owner = route['owner']
            native.select_partition(owner,'routed_expert_accumulate')
            routed = native.encode(np.zeros(h,dtype='<f4'),'F16')
            for expert,score in sorted(zip(route['selected'],route['weights'])):
                score_raw = native.encode(np.full(h,score,dtype='<f4'),'F16')
                contribution = native.binary(sparse_result[i,expert],score_raw,'F16',mul=True)
                routed = native.sum([routed,contribution],'F16')
            shared = native.sum([shared_result[i,r] for r in range(tp)],'F16')
            gate = helper._linear(normalized[i],mlp+'.shared_expert_gate',owner)
            scalar = native.software_op('shared_gate_sigmoid',[gate],
                                        lambda parts:native.encode(sigmoid32(native.decode(parts[0],'F16')),'F16'))
            value = native.binary(routed,native.binary(shared,scalar*h,'F16',mul=True),'F16')
            results.append(native.binary(value,residuals[i],'F16'))
        gathered = transport.send_wave('SAG',[
            ((i,rank),owner,rank,results[i]) for i,owner in enumerate(owners) for rank in range(tp) if rank!=owner])
        assert all(value==results[i] for (i,_),value in gathered.items())
        return b''.join(results),routes,(start,moe_start,native.backend.clock)
    finally:
        if not native.backend.closed:
            layer.close()


def main():
    assert TOKENS in (16,64) and ARM in ('hiband_reference','project_noc')
    OUT.mkdir()
    config = read(ROOT/'upstream/qwen15_config.json')
    codec = read(ROOT/'evidence/REMOTE_BUILD_LIVE_02.json')
    store = TargetArtifactStore(list(read(ROOT/'contracts/qwen15_tensor_inventory.json')['objects'].values()),'F16')
    rng = np.random.default_rng(SEED)
    hidden = (rng.normal(0,.09,(TOKENS,SPEC['hidden']))).astype('<f2').tobytes()
    (OUT/'L5_INPUT.bin').write_bytes(hidden)
    placement = {e:e%8 for e in range(SPEC['experts'])}
    binary_sha = digest(BINARY.read_bytes())
    dump(OUT/'PROTOCOL.json',dict(layer=5,tokens=TOKENS,seed=SEED,input_type='deterministic diagnostic hidden states',
                                  input_sha256=digest(hidden),placement=placement,scheme='TP4 with EP8 sparse experts',
                                  partitions=[list(range(4)),list(range(4,8))],gets=0,thermal=False,opp=1.0,
                                  flit_bytes=32,max_packet_flits=16,
                                  backend_sha256=binary_sha,arm=ARM))
    backend = LiveBackend(BINARY,binary_sha,OUT/'backend',str(ROOT/'ramulator32.yaml'),controls='off',timeout=72000)
    try:
        native = TiledPayload(backend,codec['payload_library'],codec['payload_sha256'])
        transfer = WaveTransport(backend,ARM)
        output,routes,clock = with_parallel_transfers(placement,SPEC,store,native,transfer,config,list(range(TOKENS)),hidden)
        assert len(output)==TOKENS*SPEC['hidden']*2 and np.isfinite(np.frombuffer(output,dtype='<f2')).all()
        native.close_weights()
        counters = backend.close()
        assert counters['transactions']==counters['callbacks'] and counters['packets']==counters['packet_callbacks']
        (OUT/'L5_OUTPUT.bin').write_bytes(output)
        dump(OUT/'ROUTES.json',routes)
        dump(OUT/'MATRICES.json',native.calls)
        dump(OUT/'TRANSPORT.json',dict(events=transfer.events,waves=transfer.waves))
        endpoints = sorted({e[key] for e in transfer.events for key in ('src','dst')})
        assert endpoints==list(range(8))
        pairs = Counter((e['src'],e['dst']) for e in transfer.events)
        cross = sum(e['bytes'] for e in transfer.events if e['src']//4!=e['dst']//4)
        assert cross>0
        in_flight = peak = 0
        for _,change in sorted([(e['inject_ns'],1) for e in transfer.events]+[
            (e['wire_done_ns'],-1) for e in transfer.events]):
            in_flight+=change
            peak=max(peak,in_flight)
        assert in_flight==0 and peak>=2
        moe_waves = [w for w in transfer.waves if w['stage']!='attention_SRS']
        moe_communication = sum(w['complete_ns']-w['ready_ns'] for w in moe_waves)
        wire_sum = sum(e['wire_done_ns']-e['inject_ns'] for e in transfer.events if e['stage']!='attention_SRS')
        stats = dict(status='PASS_MULTITOKEN_LAYER_ARM',arm=ARM,tokens=TOKENS,
                     input_sha256=digest(hidden),output_sha256=digest(output),layer_ns=clock[2]-clock[0],
                     moe_ns=clock[2]-clock[1],messages=len(transfer.events),endpoint_pairs=len(pairs),
                     active_endpoints=endpoints,cross_partition_bytes=cross,peak_in_flight=peak,
                     moe_communication_ns=moe_communication,moe_wire_latency_sum_ns=wire_sum,
                     circuit_messages=sum(bool(e['circuit']) for e in transfer.events),
                     callbacks=counters['callbacks'],packets=counters['packets'])
        dump(OUT/'RESULT.json',stats)
        print(json.dumps(stats),flush=True)
    except BaseException:
        (OUT/'ERROR.txt').write_text(traceback.format_exc())
        if not backend.closed:
            backend.abort()
        raise


if __name__=='__main__':
    main()

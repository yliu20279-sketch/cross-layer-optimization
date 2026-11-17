"""Run the frozen real-weight layer through the live OPP-aware backend."""

import csv
import hashlib
import json
from pathlib import Path
import struct
import sys
import traceback


def load(path):
    return json.loads(path.read_text())


def sha(data):
    return hashlib.sha256(data).hexdigest()


def save(path, obj):
    path.write_text(json.dumps(obj, indent=2) + '\n')


def main(root, binary, frozen_services, out, opp, arrivals_path=None, calibration=None, policy_path=None,
         paired_policy=None, moe_only_contract=None):
    from core.artifacts import TargetArtifactStore
    from core.coupled_backend import LiveBackend, CoupledPayload, CoupledTransport, MAGIC
    from core.coupled_layer import CoupledLayer
    from core.coupled_decoder import DecoderSlice
    from models.qwen15 import SPEC

    out.mkdir()
    freeze = root / 'runs/qwen15_pp56rmsfixed'
    hidden = (freeze / 'prefill_L5_input.bin').read_bytes()
    expected = load(freeze / 'RESULT.json')['phases'][0]
    frozen = load(frozen_services)
    scheduled = [e for s in frozen['segments'] for e in s['events'] if e['kind'] == 'native_matrix_rpc']
    assert len(scheduled) == 25
    raw = (freeze / 'NUMERIC_CALLS.json').read_bytes()
    assert sha(raw) == frozen['source_hashes']['NUMERIC_CALLS.json']
    expected_calls = {row['FP32_result_handle']:row for row in json.loads(raw)}
    cfg = load(root / 'upstream/qwen15_config.json')
    codec = load(root / 'evidence/REMOTE_BUILD_LIVE_02.json')
    placement = load(freeze / 'PROTOCOL.json')['placement']
    store = TargetArtifactStore(list(load(root / 'contracts/qwen15_tensor_inventory.json')['objects'].values()), 'F16')
    thermal = None
    assert paired_policy in (None,'project_noc','hiband_reference')
    if paired_policy:
        assert (arrivals_path or moe_only_contract) and opp == 4
    if moe_only_contract:
        assert not arrivals_path and paired_policy
        selection = 'FULL_LOCAL'
        if paired_policy == 'project_noc':
            screening = load(policy_path)
            assert screening['contract_sha256'] == sha(moe_only_contract.read_bytes())
            assert screening['selected'] == 'mesh', 'An active native CS requires a bound circuit transport'
            selection = screening['selected']
        save(out/'NETWORK_POLICY.json',dict(selected=selection,paired_policy=paired_policy,
                                          gets=0,thermal_enabled=False))
    if arrivals_path:
        assert opp in (0,4), 'Mixed runs use online thermal or fixed 1.0×'
        arrivals = load(arrivals_path)
        case = arrivals['case']
        prior = load(calibration.parent.parent / case / 'LAUNCH.json')
        assert sha(arrivals_path.read_bytes()) == prior['arrivals_sha256']
        policy_path = policy_path or calibration.parent/'RTL_INGRESS.json'
        if paired_policy == 'hiband_reference':
            selection = 'FULL_LOCAL'
        else:
            policy = load(policy_path)['cases']
            selection, = [row['selected'] for row in policy if row['case']==case]
            assert selection == 'mesh', 'Native circuit binding is only available for retained Mesh'
        if opp == 0:
            from native_thermal import NativeThermal
            thermal = NativeThermal(calibration.parent,calibration,case,out,len(arrivals['transactions']))
        policy_source = ('single-stage local scope and HiBand reference bandwidth modes'
                         if paired_policy == 'hiband_reference' else 'first-dispatch RTL candidate audit')
        save(out/'NETWORK_POLICY.json',dict(source=policy_source,selected=selection,
                                          audit_sha256=sha(policy_path.read_bytes()), paired_policy=paired_policy,
                                          gets_sha256=prior['arrivals_sha256'],thermal_enabled=bool(thermal)))
    save(out / 'INPUTS.json', dict(input_sha256=sha(hidden), frozen_sha256=sha(frozen_services.read_bytes()),
                                  binary_sha256=sha(binary.read_bytes()), opp_quarters=opp,
                                  thermal_enabled=bool(thermal)))
    backend = LiveBackend(str(binary), sha(binary.read_bytes()), out / 'backend', str(root/'ramulator32.yaml'),
                          controls='off' if arrivals_path or moe_only_contract else 'project_dynamic',timeout=3600)
    try:
        native = CoupledPayload(backend, codec['payload_library'], codec['payload_sha256'])
        transport = CoupledTransport(native)
        layer = CoupledLayer(SPEC, cfg, store, native, transport, placement, 'F16')
        layer.request_owner = 1
        original_rpc = backend.rpc
        cursor = 0
        decisions = []
        mixed_origin = None

        def command(opcode, a, b, c=0):
            backend.process.stdin.write(struct.pack('<8Q',opcode,a,b,c,0,0,0,0))
            backend.process.stdin.flush()
            reply = struct.unpack('<8Q',backend._read(64))
            assert reply[0]==MAGIC
            if reply[1]:
                raise RuntimeError(backend._read(reply[2]).decode())
            backend.clock=reply[7]
            return reply

        if paired_policy:
            reference = load(moe_only_contract or calibration.parent.parent/case/'CONTRACT.json')
            transport_work = [(row['src'],row['dst'],row['bytes']) for row in reference['transport']]
            gets_work = [(row['src'],row['dst'],row['request_bytes']+row['reply_bytes'])
                         for row in arrivals['transactions']] if arrivals_path else []
            assert all(0 <= src < 4 and 0 <= dst < 4 for src,dst,_ in transport_work+gets_work)
            command(16,int(paired_policy=='hiband_reference'),sum(size for _,_,size in transport_work+gets_work),0)
            assert backend.clock==0

        if arrivals_path:
            path = out/'backend/GETS.stim'
            path.write_text(''.join(f"{row['arrival']} {row['address']}\n" for row in arrivals['transactions']))
            transport_send = transport.send

            def send(src,dst,token,stage,payload):
                nonlocal mixed_origin
                if stage=='dispatch' and mixed_origin is None:
                    assert (src,dst)==(0,1) and len(payload)==4096
                    mixed_origin=backend.clock
                    if thermal:
                        thermal.origin=mixed_origin
                    assigned = command(15,len(arrivals['transactions']),32)
                    assert assigned[3]==mixed_origin and backend.clock==mixed_origin+32
                return transport_send(src,dst,token,stage,payload)

            transport.send=send

        def rpc(opcode, *args, **kwargs):
            nonlocal cursor
            label = native.label
            if opcode != 5 or not label.startswith('model.layers.5.mlp.') or label.endswith('.mlp.gate'):
                start = backend.clock
                answer = original_rpc(opcode, *args, **kwargs)
                if thermal:
                    thermal.observe_rpc(opcode,args,backend.live,start,backend.clock)
                return answer
            assert cursor < len(scheduled), label
            item = scheduled[cursor]
            _, _, _, m, n, k, fp16 = args
            assert [m,k,n] == item['mkn'] and fp16 and native.partition==item['partition'] and label==item['label']
            ready = backend.clock
            # Mode 0 is a separate actuator probe; the first real target
            # matrix is deliberately deferred and run at the 3/4 setting.
            if thermal:
                ratio, release = thermal.schedule(cursor,native.partition,ready)
            else:
                ratio = opp or (3 if cursor == 0 else 4)
                release = ready + (1000000 if opp == 0 and cursor == 0 else 0)
            command(14,ratio,release)
            assert backend.clock==ready
            decision = dict(index=cursor, label=label, requested_release=release, ready=ready, opp_quarters=ratio)
            print(json.dumps(decision), flush=True)
            cursor += 1
            reply = original_rpc(opcode, *args, **kwargs)
            decision['complete'] = backend.clock
            if thermal:
                thermal.commit_matrix(cursor-1,native.partition,ratio,release,backend.clock)
            decisions.append(decision)
            save(out / 'PROGRESS.json', decisions)
            return reply

        backend.rpc = rpc
        output = DecoderSlice(layer).forward(hidden,[0],[17],5,6)
        assert sha(output) == expected['output_sha256']
        assert cursor == len(decisions) == len(scheduled)
        assert layer.phases[0]['routes'][0]['selected'] == expected['routes'][0]['selected']
        actual_calls = [e for e in native.calls if e['label'].startswith('model.layers.5.mlp.') and not e['label'].endswith('.mlp.gate')]
        assert len(actual_calls) == len(scheduled)
        for observed, item in zip(actual_calls, scheduled):
            original = expected_calls[item['output_handle']]
            assert all(observed[k] == original[k] for k in ('label','MKN','source_sha256','output_sha256'))
        layer.close()
        native.close_weights()
        summary = backend.close()
        with (out/'backend/OPP_MATRIX.csv').open() as stream:
            timing = [{k:int(v) for k,v in row.items()} for row in csv.DictReader(stream)]
        assert len(timing) == len(decisions)
        lowering = {j['job']:j for j in map(json.loads, (out/'backend/LOWERING.jsonl').read_text().splitlines())}
        for row, decision in zip(timing, decisions):
            assert row['opp_quarters']==decision['opp_quarters'] and row['requested_release']==decision['requested_release']
            assert row['actual_start']==row['requested_release'] and row['rpc_ready']==decision['ready']
            assert row['complete'] == decision['complete'] >= row['actual_start']
            lower=lowering[row['job']]
            assert lower['begin'] == row['actual_start'] and lower['complete'] == row['complete']
            row['compute_cycles'],row['sram_bank_cycles']=lower['compute_cycles'],lower['bank_cycles']
        result=dict(status='PASS_NATIVE_OPP_ACTUATOR_PROBE' if not opp else 'PASS_NATIVE_OPP_CALIBRATION',
                    opp_quarters=opp, matrices=len(timing), output_sha256=sha(output),
                    target_complete=layer.phases[0]['complete'], backend_summary=summary, timing=timing)
        if arrivals_path:
            with (out/'backend/GETS.csv').open() as stream:
                gets = [{k:int(v) for k,v in row.items()} for row in csv.DictReader(stream)]
            assert len(gets)==len(arrivals['transactions'])
            for row, expected_arrival in zip(gets,arrivals['transactions']):
                assert row['id']==expected_arrival['id'] and row['arrival']==expected_arrival['arrival']
                points = [row[k] for k in ('arrival','request_inject','request_done','read_done','reply_inject','reply_done')]
                assert points==sorted(points)
                if not paired_policy:
                    assert points[0]==points[1]
            status = 'PASS_NATIVE_MOE_GETS_THERMAL_DIAGNOSTIC' if thermal else 'PASS_NATIVE_NOC_MOE_GETS_DIAGNOSTIC'
            result.update(status=status,case=case,gets=len(gets),thermal_enabled=bool(thermal),
                          gets_last_reply=max(r['reply_done'] for r in gets),
                          mixed_origin_ns=mixed_origin,
                          moe_suffix=layer.phases[0]['complete']-mixed_origin,
                          joined_makespan=int(summary['clock_ns'])-mixed_origin)
            if thermal:
                result['thermal'] = thermal.finish(int(summary['clock_ns']))
            else:
                assert all(r['opp_quarters']==4 and r['rpc_ready']==r['actual_start'] for r in timing)
        if paired_policy:
            execution_policy=load(out/'backend/PAIRED_POLICY.json')
            assert execution_policy['policy']==paired_policy
            assert execution_policy['admitted_packets']==summary['packets']
            assert execution_policy['global_bytes']==0
            result.update(status='PASS_NATIVE_PAIRED_NOC_DIAGNOSTIC',paired_policy=execution_policy)
            save(out/'TRANSPORT.json',transport.events)
        if moe_only_contract:
            work = [(e['stage'],e['src'],e['dst'],e['bytes']) for e in transport.events]
            expected_work = [(e['stage'],e['src'],e['dst'],e['bytes']) for e in reference['transport']]
            first = next(i for i,e in enumerate(transport.events) if e['stage']=='dispatch')
            assert work[first:] == expected_work
            assert all(e['target_noc'] and e['start'] < e['complete'] for e in transport.events[first:])
            assert not (out/'backend/GETS.csv').exists()
            assert all(r['opp_quarters']==4 and r['rpc_ready']==r['actual_start'] for r in timing)
            assert summary['transactions']==summary['callbacks'] and summary['packets']==summary['packet_callbacks']
            origin = transport.events[first]['start']
            result.update(status='PASS_NATIVE_MOE_ONLY_PAIR_ARM',gets=0,thermal_enabled=False,selection=selection,
                          frozen_contract_sha256=sha(moe_only_contract.read_bytes()),moe_origin_ns=origin,
                          moe_suffix_ns=result['target_complete']-origin,
                          moe_transport_ns=sum(e['complete']-e['start'] for e in transport.events[first:]),
                          moe_messages=len(expected_work))
        save(out/'RESULT.json',result)
        print(json.dumps({k:v for k,v in result.items() if k!='timing'}),flush=True)
    except BaseException:
        (out/'ERROR.txt').write_text(traceback.format_exc())
        if not backend.closed:
            backend.abort()
        raise


if __name__=='__main__':
    _, root, binary, frozen, out, setting, *joint = sys.argv
    root, binary, frozen, out = (Path(p).resolve() for p in (root,binary,frozen,out))
    sys.path.insert(0,str(root))
    if joint and joint[0]=='--moe-only':
        _, arm, contract, *audit = joint
        main(root,binary,frozen,out,int(setting),paired_policy=arm,moe_only_contract=Path(contract).resolve(),
             policy_path=Path(audit[0]).resolve() if audit else None)
    else:
        main(root,binary,frozen,out,int(setting),*(Path(p).resolve() for p in joint[:3]),*joint[3:])

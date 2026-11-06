import hashlib
import json
from graphlib import TopologicalSorter
from pathlib import Path

root = Path(__file__).resolve().parent
binding_file = root / 'STEP1_BINDING.json'
binding = json.loads(binding_file.read_text())
assert binding['state'] == 'PASS_LIMITED_BINDING'
assert set(binding['branches']) == {'cond', 'uncond'}
nodes = {}

def node(name, resource, *deps, evidence='planned', **details):
    assert name not in nodes
    nodes[name] = dict(resource=resource, dependencies=list(deps), evidence=evidence, **details)
    return name

def chain(prefix, operations, first, resource):
    for op in operations.split():
        first = node(prefix + op, resource, first)
    return first

arrival = node('arrival', 'request', target_ns=binding['request_arrival_target_ns'])
visual = node('first_frame_vlm', 'condition_encoder', arrival)
encoded = node('first_frame_vae_encode', 'VAE', arrival)
latent = node('initial_latent', 'latent', visual, encoded)

for branch, reference in binding['branches'].items():
    p = branch + '.'
    text = node(p+'text_encode', 'condition_encoder', arrival, polarity=branch)
    inputs = node(p+'block_input', 'DiT', text, visual, latent,
                  evidence='frozen_fixture_boundary', reference=reference['fixtures']['block_input'])
    norm = chain(p, 'time_modulation rmsnorm', inputs, 'compute')
    projections = []
    for axis in ('q', 'k', 'v'):
        w = node(p+axis+'_weight_read_complete', 'HB', inputs,
                 frozen_slices=[w for w in binding['qkv_weight_slices']
                                if w['name'].endswith('to_'+axis+'.weight')])
        a = node(p+axis+'_projection', 'compute', norm, w)
        if axis != 'v':
            a = chain(p, axis+'_norm '+axis+'_rope', a, 'compute')
        projections.append(a)
    attention = node(p+'noncausal_score', 'compute', *projections, inputs_used=['q','k'])
    attention = node(p+'softmax', 'compute', attention)
    attention = node(p+'value', 'compute', attention, projections[2])
    o = chain(p, 'o_projection ordered_fp32_rank_carry o_bias attention_residual moe_norm',
              attention, 'compute_and_TP')
    route = chain(p, 'router_fp32 sigmoid correction_bias group_top2 top8', o, 'compute')
    weights = node(p+'unbiased_weight_normalize_scale_padding', 'compute', route, p+'sigmoid')
    pack = node(p+'pack', 'compute', weights, o)
    dispatch = node(p+'dispatch_tail_arrival', 'NoC_EP', pack)
    expert_weight = node(p+'expert_weight_read_complete', 'HB', route)
    expert = node(p+'expert_gate_up', 'compute', dispatch, expert_weight)
    expert = chain(p, 'silu_mul down return_tail_arrival restore_source_slot fp32_weighted_reduce',
                   expert, 'compute_and_EP')
    shared = chain(p, 'shared_gate_up shared_silu_mul shared_down', o, 'compute')
    join = node(p+'shared_routed_join', 'compute', expert, shared)
    chain(p, 'post_ffn_norm modulation_residual block_output', join, 'compute')
    nodes[p+'block_output']['reference'] = reference['fixtures']['block_output']
    nodes[p+'value']['kv_regression_only'] = reference['v11_case1_rank0_kv_compare_only']

    # A separate proposed cost-probe path. These nodes have no runtime receipts yet.
    cpu = node(p+'probe.cpu_return', 'Sniper', norm)
    wb = node(p+'probe.dirty_writeback_callback', 'DRAM', cpu)
    dma = node(p+'probe.dma_poll_complete', 'PCIe', cpu, wb)
    tail = node(p+'probe.noc_receive_tail', 'PopNet', dma)
    node(p+'probe.consumer', 'consumer', cpu, wb, dma, tail,
         release='max of matched completion times on the common clock',
         match_fields=['request','step','layer','cfg','token','buffer_version','transaction'])

merge = node('cfg_combine', 'compute', 'cond.block_output', 'uncond.block_output',
             requirement='both branches finish all 48 layers before CFG combine')
updated = chain('', 'scheduler_update inpainting next_latent', merge, 'latent')
decode = node('vae_decode', 'VAE', updated, requirement='consume final latent after step 39')
node('frame_output', 'output', decode)

assert all(dep in nodes for n in nodes.values() for dep in n['dependencies'])
order = list(TopologicalSorter({k:v['dependencies'] for k,v in nodes.items()}).static_order())
assert len(order) == len(nodes)
for branch in binding['branches']:
    p=branch+'.probe.'
    assert set(nodes[p+'consumer']['dependencies']) == {p+x for x in (
        'cpu_return','dirty_writeback_callback','dma_poll_complete','noc_receive_tail')}
graph = dict(
    state='PASS_STRUCTURAL_TEMPLATE', sample='example_4',
    binding_sha256=hashlib.sha256(binding_file.read_bytes()).hexdigest(),
    scope='layer-0 step-0 dual CFG template plus application boundaries; no runtime validation',
    expansion=dict(layers=48, steps=40, layer_edge='output[L] -> input[L+1] within CFG',
                   step_edge='next_latent[S] -> both CFG inputs[S+1]'),
    communication=dict(source_CP=['Q sequence-to-head','K sequence-to-head',
                                    'V sequence-to-head','output head-to-sequence'],
                       source_CFG=['latent broadcast','unconditional output broadcast'],
                       target_TP='ordered O FP32 rank carry', target_EP='dispatch and return',
                       note='Source CP and CFG are separate accounting categories, not target TP/EP events.'),
    event_fields=['request','step','timestep','layer','cfg','token','token_thw','padding',
                  'rank','expert','slot','shape','dtype','bytes','address','owner',
                  'last_reader','buffer_version','transaction','clock_domain',
                  'start_tick','complete_tick','complete_target_ns','dependencies'],
    coverage=dict(v11='continuous single-layer numerical and macro completion evidence',
                  gpu_stage_reference='step 1 fixtures; no intermediate injection',
                  probe='planned, no completion timestamps',
                  full_video='planned', uncond_independent_fp32='pending'),
    node_count=len(nodes), edge_count=sum(len(n['dependencies']) for n in nodes.values()),
    nodes=nodes, topological_order=order)
(root/'STEP2_OPERATOR_DAG.json').write_text(json.dumps(graph,indent=2)+'\n')
print(graph['state'], graph['node_count'], graph['edge_count'])

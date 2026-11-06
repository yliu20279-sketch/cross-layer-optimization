from pathlib import Path
p=Path('tools/reference_layer_cpu.py')
s=p.read_text().replace("out=run/'pinned_cpu_reference'","out=run/'attention_cpu_reference'")
i=s.index('with torch.inference_mode():')
s=s[:i]+"""def trace_attention(frame,event,arg):
    if event=='return' and frame.f_code.co_name=='eager_attention_forward':
        variables=frame.f_locals
        query=variables['query']
        keys=variables['key_states']
        raw=torch.matmul(query,keys.transpose(2,3))
        for name,tensor in [('rotated_q',query),('qk',raw),('probability',arg[1])]:
            captured[name]=tensor.detach().contiguous().view(torch.uint16).numpy().tobytes()
    return trace_attention

sys.settrace(trace_attention)
"""+s[i:]
Path('tools/reference_attention_cpu.py').write_text(s)

from pathlib import Path
import sys
root=Path(sys.argv[1])
p=root/'core/coupled_layer.py'
s=p.read_text()
s=s.replace('        q_per=self.qh//tp;', "        self.capture(part,'input_norm',x)\n        q_per=self.qh//tp;".replace(chr(92)+'n','\n'))
s=s.replace("        if prefix+'.self_attn.q_norm.weight' in self.store.objects:", """        for stage_name, data in [('q_proj',q),('k_proj',k),('v_proj',v)]:
            self.capture(part,stage_name,data)
        if prefix+'.self_attn.q_norm.weight' in self.store.objects:""")
s=s.replace("            probability=self._math", "            self.capture(part,f'head{head}_qk',scores)\n            probability=self._math".replace(chr(92)+'n','\n'))
s=s.replace("            self.n.select_partition(part,'attention_PV')", "            self.capture(part,f'head{head}_probability',probability)\n            self.n.select_partition(part,'attention_PV')".replace(chr(92)+'n','\n'))
s=s.replace("        # Q3 keeps FP32", "        self.capture(part,'o_input',context)\n        # Q3 keeps FP32".replace(chr(92)+'n','\n'))
s=s.replace('    def _math(', '    def capture(self, partition, name, raw):\n        pass\n\n    def _math('.replace(chr(92)+'n','\n'))
p.write_text(s)
p=root/'tools/run_interleaved.py'
s=p.read_text()
s=s.replace("                (out/(name+'_'+phase+'_input.bin')).write_bytes(hidden)", """                frozen = ROOT/'frozen_inputs'/args.model/(name+'_'+phase+'_input.bin')
                require(hidden==frozen.read_bytes(),'original input changed')
                hidden=frozen.read_bytes()
                capture_dir=out/'stages'/name/phase
                capture_dir.mkdir(parents=True)
                def capture(rank, stage, raw, directory=capture_dir):
                    (directory/f'R{rank}_{stage}.bin').write_bytes(raw)
                layer.capture=capture
                (out/(name+'_'+phase+'_input.bin')).write_bytes(hidden)""")
p.write_text(s)
p=root/'tools/reference_layer_cpu.py'
s=p.read_text()
point='native=json.loads'
i=s.index(point)
s=s[:i]+"""captured={}
def hook(name, pre=False):
    def save(module,args,output=None):
        tensor=args[0] if pre else output
        captured[name]=tensor.detach().contiguous().view(torch.uint16).numpy().tobytes()
    return save
layer.input_layernorm.register_forward_hook(hook('input_norm'))
for name in ('q_proj','k_proj','v_proj'):
    getattr(layer.self_attn,name).register_forward_hook(hook(name))
layer.self_attn.o_proj.register_forward_pre_hook(hook('o_input',True))
"""+s[i:]
s=s.replace("        target=decode", """        for name, raw in captured.items():
            (out/f'{phase}_{name}.bin').write_bytes(raw)
        target=decode""")
p.write_text(s)

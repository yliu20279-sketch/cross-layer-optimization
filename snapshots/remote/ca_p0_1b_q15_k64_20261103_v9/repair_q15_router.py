from pathlib import Path
p=Path('core/live_moe.py')
s=p.read_text()
old="""            from models.qwen15.fp16_math import softmax32
            scores=softmax32(logits)"""
new="""            import torch
            probabilities=torch.softmax(torch.from_numpy(logits.copy()),dim=-1,dtype=torch.float32)
            scores=probabilities.numpy()
            top=torch.topk(probabilities,self.spec['topk']).indices.numpy()"""
assert old in s
s=s.replace(old,new)
s=s.replace('        top=np.lexsort((np.arange(logits.size),-logits))[:self.spec[\'topk\']]','            top=np.lexsort((np.arange(logits.size),-logits))[:self.spec[\'topk\']]')
p.write_text(s)

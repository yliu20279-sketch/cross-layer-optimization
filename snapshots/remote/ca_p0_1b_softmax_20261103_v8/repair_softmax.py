from pathlib import Path
p=Path('core/coupled_layer.py')
s=p.read_text()
s=s.replace('import numpy as np','import numpy as np\nimport torch')
start=s.index('                s=self.n.decode(parts[0]')
end=s.index("            self.capture(part,f'head{head}_qk'",start)
s=s[:start]+"""                dtype=torch.bfloat16 if self.dtype=='BF16' else torch.float16
                scores=torch.from_numpy(np.frombuffer(parts[0],dtype='<u2').copy()).view(dtype)
                scores=scores.reshape(tokens,total)*float(self.d**-.5)
                mask=torch.arange(total)[None,:]>(past+torch.arange(tokens)[:,None])
                scores=scores.masked_fill(mask,-torch.inf)
                probability=torch.softmax(scores,dim=-1,dtype=torch.float32).to(dtype)
                return probability.contiguous().view(torch.uint16).numpy().tobytes()
"""+s[end:]
p.write_text(s)

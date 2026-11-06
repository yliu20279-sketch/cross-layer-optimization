import pathlib,numpy as np,ctypes,json
P=pathlib.Path('/mnt/sda1/h3240101068/lingbot_step4_bitexact_20261029_v4');D=P/'router_kspread_probe';z=np.load(D/'probe.npz');y=z['y'];print('distinct_rows',len(np.unique(y.transpose(1,0,2).reshape(128,-1),axis=0)),flush=True)
# Identify all output positions; duplicate input rows intentionally expose thread-layout differences.
lib=ctypes.CDLL(str(P/'libidentify_kspread.so'));lib.identify.argtypes=[ctypes.c_void_p]*4
out=np.full((128,128,9),-1,dtype=np.int32);x=z['x'].copy();w=z['w'].copy();y=y.copy();fail=lib.identify(x.ctypes.data,w.ctypes.data,y.ctypes.data,out.ctypes.data);np.save(D/'orders.npy',out)
unique,counts=np.unique(out[:1].reshape(-1,9),axis=0,return_counts=True);r=dict(failures=fail,orders=[dict(order=a[:8].tolist(),matching_permutations=int(a[8]),outputs=int(c)) for a,c in zip(unique,counts)])
(D/'ORDERS.json').write_text(json.dumps(r,indent=2));print(json.dumps(r),flush=True)

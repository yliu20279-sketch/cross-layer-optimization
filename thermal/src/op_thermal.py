"""HotSpot-exported thermal RC with an explicit, hashable operator directory."""
from pathlib import Path

import numpy as np
from scipy.sparse import csc_matrix, eye
from scipy.sparse.linalg import splu

from graph_paths import LEGACY_RC


class ThermalPlant:
    def __init__(self, initial_C, rc_folder=None, substeps=2):
        folder = Path(rc_folder) if rc_folder is not None else LEGACY_RC
        n, blocks, ambient = map(
            float, (folder / "dimension.txt").read_text().splitlines()[0].split())
        n = int(n)
        assert blocks == 96
        self.ambient = ambient - 273.15
        self.substeps = substeps
        self.state = np.full(n, initial_C-self.ambient)
        self.fact = {}
        def read(name, shape):
            a = np.loadtxt(folder / (name+".csv"), delimiter=",", skiprows=1)
            return csc_matrix((a[:,2],(a[:,0].astype(int),a[:,1].astype(int))),
                              shape=shape)
        self.A = read("A", (n,n))
        self.B = read("B", (n,96))
        self.C = read("C", (96,n))
        assert np.max(abs(np.asarray(self.C.sum(1)).ravel()-1)) < 1e-12
        assert np.all(self.A.diagonal() < 0)

    def step(self, power, dt=.001):
        power = np.asarray(power)
        assert power.shape == (96,) and power.min() >= 0
        h = dt/self.substeps
        if h not in self.fact:
            self.fact[h] = splu(eye(len(self.state), format="csc")-h*self.A)
        forcing = h*(self.B@power)
        solve = self.fact[h].solve
        for _ in range(self.substeps):
            self.state = solve(self.state+forcing)
        return self.ambient+self.C@self.state

    def close(self):
        pass

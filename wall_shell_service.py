"""Experimental layered shell equilibrium at service loads.

Tension positive. N in kN/m, M in kNm/m, z in mm, stresses in MPa.
Concrete carries only compressive principal stresses; steel is linear
elastic, uniaxial in each bar direction. No crack-width law is implied.
"""
from dataclasses import dataclass

import numpy as np


@dataclass(frozen=True)
class BarLayer:
    axis: int
    z_mm: float
    area_mm2_m: float


@dataclass(frozen=True)
class ShellServiceResult:
    mid_strain: np.ndarray
    curvature_per_mm: np.ndarray
    steel_stress_mpa: np.ndarray
    face_principal_strain: np.ndarray
    residual_mpa: float


def solve_cracked_shell(h_mm, n, m, bars, ec_mpa, es_mpa=200000., fibres=48, *, concrete_weights=None, concrete_positions=None):
    """Solve six resultants by minimising total potential energy.

    Internal strain coordinates are (eps_x, eps_y, sqrt(2)*eps_xy).
    Return None if residual tolerance cannot be met, e.g. pure net shear
    without enough concurrent normal force to equilibrate it.
    """
    bars = tuple(bars)
    n, m = np.asarray(n, dtype=float), np.asarray(m, dtype=float)
    if (n.shape != (3,) or m.shape != (3,) or not np.isfinite(np.r_[n, m, h_mm, ec_mpa, es_mpa]).all()
            or min(h_mm, ec_mpa, es_mpa) <= 0 or fibres < 8
            or any(b.axis not in (0, 1) or not np.isfinite([b.z_mm, b.area_mm2_m]).all()
                   or abs(b.z_mm) >= h_mm/2 or b.area_mm2_m <= 0 for b in bars)):
        raise ValueError("Dados de secção ou de esforços inválidos")
    root = np.sqrt(2.)
    scale = np.array([1., 1., root])
    target = np.r_[n*scale/h_mm, m*scale*2000/h_mm**2]
    tol = max(1e-9, 1e-8*np.max(abs(target)))
    s = (np.arange(fibres)+.5)*2/fibres-1
    w=np.full(fibres,1./fibres) if concrete_weights is None else np.asarray(concrete_weights,float)
    if w.shape!=(fibres,) or not np.isfinite(w).all() or np.any(w<=0) or w.sum()>1+1e-9:
        raise ValueError("Pesos de betão inválidos")
    if concrete_positions is not None:
        s=np.asarray(concrete_positions,float)
        edges=np.linspace(-1.,1.,fibres+1)
        if (s.shape!=(fibres,) or not np.isfinite(s).all()
                or np.any(s<edges[:-1]-1e-9) or np.any(s>edges[1:]+1e-9)):
            raise ValueError("Centroides de betão inválidos")
    steel = np.zeros((len(bars), 6))
    for i, b in enumerate(bars):
        steel[i, b.axis] = 1
        steel[i, b.axis+3] = 2*b.z_mm/h_mm
    weights = np.array([b.area_mm2_m for b in bars])*es_mpa/(1000*h_mm)
    ksteel = (steel.T*weights) @ steel
    k0=ksteel+ec_mpa*np.kron(np.array([[w.sum(),w@s],[w@s,w@(s*s)]]),np.eye(3))

    def matrix(a):
        out = np.empty(a.shape[:-1]+(2, 2))
        out[..., 0, 0], out[..., 1, 1] = a[..., 0], a[..., 1]
        out[..., 0, 1] = out[..., 1, 0] = a[..., 2]/root
        return out

    def state(x):
        e = matrix(x[:3]+s[:, None]*x[3:])
        lam, vec = np.linalg.eigh(e)
        neg = np.minimum(lam, 0)
        sig = (vec*neg[:, None, :]) @ vec.swapaxes(-1, -2)
        v = np.stack((sig[:, 0, 0], sig[:, 1, 1], root*sig[:, 0, 1]), axis=1)
        gradient = ec_mpa*np.r_[w@v, (w*s)@v]+ksteel@x-target
        energy = .5*(ec_mpa*(w@np.sum(neg**2, axis=1))+x@ksteel@x)-target@x
        return gradient, energy

    x = np.linalg.solve(k0, target)
    g, f = state(x)
    inv = np.linalg.inv(k0)
    for _ in range(100):
        residual = np.max(abs(g))
        if residual <= tol:
            return ShellServiceResult(x[:3]/scale, x[3:]*2/h_mm/scale, es_mpa*(steel@x),
                                      np.linalg.eigvalsh(matrix(np.stack((x[:3]+x[3:], x[:3]-x[3:])))),
                                      float(residual))
        p = -inv@g
        if g@p >= 0:
            return None
        for j in range(30):
            step = p*2.**(-j)
            trial = x+step
            if np.max(abs(trial)) > .05:
                continue
            ng, nf = state(trial)
            if nf <= f+1e-4*(g@step)+1e-16:
                break
        else:
            return None
        y = ng-g
        sy = step@y
        if sy > 1e-24:
            ident = np.eye(6)-np.outer(step, y)/sy
            inv = ident@inv@ident.T+np.outer(step, step)/sy
        x, g, f = trial, ng, nf
    return None

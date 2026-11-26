"""Independent tensor reconstruction of the smeared diagonal core truss.

Core concrete is uniaxial compression along the inclined diagonal. Normal
links cancel its zz component as a smeared stress within the core, not a
verified physical anchorage/detail. Resultants in kN/m, moments kNm/m.
This certifies sectional equilibrium of the trial only, not a continuum
stress field at a free edge, crack compatibility or structural resistance.
"""
from dataclasses import dataclass
import math
import numpy as np

@dataclass(frozen=True)
class CoreStressField:
    concrete_mpa: np.ndarray
    links_mpa: np.ndarray
    n: np.ndarray
    m: np.ndarray
    q: np.ndarray
    nzz: float
    strut_util: float
    link_util: float
    residual: float
    valid: bool


def reconstruct(q, thickness, z, cot, fc, fyd, asw):
    q=np.asarray(q,float)
    if (q.shape!=(2,) or not np.isfinite(np.r_[q,thickness,z,cot,fc,fyd,asw]).all()
        or min(thickness,fc,fyd)<=0 or not 1<=cot<=2.5 or asw<0):
        raise ValueError('Dados inválidos para reconstrução da treliça')
    v=float(np.linalg.norm(q));normal=np.zeros(3);normal[2]=1
    if v:
        axis=np.r_[cot*q/v,-1.]/math.sqrt(1+cot*cot)
        amp=v/thickness*(cot+1/cot)
        concrete=-amp*np.outer(axis,axis)
    else:
        amp=0.;concrete=np.zeros((3,3))
    # Normal ties balance the average transverse compression in the core.
    links=-concrete[2,2]*np.outer(normal,normal)
    resultant=(concrete+links)*thickness
    n=np.array([resultant[0,0],resultant[1,1],resultant[0,1]])
    m=n*z/1000; recovered=resultant[:2,2]; nzz=float(resultant[2,2])
    need=float(links[2,2])*1e6/fyd
    link_util=need/asw if asw>0 else (math.inf if need>0 else 0.)
    # Compare against a separately implemented Annex LL force increment.
    from wall_coupled_shear import truss_increment
    delta=truss_increment(q,cot)
    residual=float(np.max(np.abs(np.r_[recovered-q,n+delta,(m+delta*z/1000)*1000/thickness,nzz])))
    valid=(residual<=1e-7*max(1.,v) and amp/fc<=1+1e-7 and link_util<=1+1e-7)
    return CoreStressField(concrete,links,n,m,recovered,nzz,amp/fc,link_util,residual,valid)

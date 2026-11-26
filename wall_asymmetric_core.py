"""Experimental asymmetric outer layers, retaining a specified minimum core.

First-order static stress-field trial. Does not certify service, anchorage,
modal concomitance, stability, or EC2 shell resistance. For Q <= VRdc the
in-plane stress field and empirical shear check remain separate. For Q >
VRdc the core strut's eccentric in-plane resultant is balanced in BOTH N
and M. Proposed links are not credited as installed.
"""
from dataclasses import dataclass
import math
import numpy as np
from wall_physical_layers import PhysicalCapacity
from wall_adaptive_capacity import solve
from wall_coupled_shear import truss_increment
from wall_core_equilibrium import link_grid

@dataclass(frozen=True)
class AsymmetricTrial:
    status: str
    face_util: float=math.nan
    fraction_plus: float=math.nan
    fraction_minus: float=math.nan
    core_mm: float=math.nan
    core_z_mm: float=math.nan
    cot_theta: float=math.nan
    core_util: float=math.nan
    asw_required: float=math.nan
    asw_proposed: float=math.nan
    phi: float=math.nan
    pitch_x: float=math.nan
    pitch_y: float=math.nan
    residual: float=math.nan
    candidates: int=0
    tensor_residual: float=math.nan
    link_util: float=math.nan


def exterior_actions(n,m,q,cot,z_core):
    """N_core=-delta, M_core=-delta*z_core/1000; total N,M preserved."""
    delta=truss_increment(q,cot)
    return np.asarray(n,float)+delta,np.asarray(m,float)+delta*z_core/1000


class AsymmetricCore:
    def __init__(self,h,families,fck,fcd,fyk,fyd,*,min_core_fraction=.20,step=.025,subdivisions=6):
        if not np.isfinite([h,fck,fcd,fyk,fyd,min_core_fraction,step]).all() or min(h,fck,fcd,fyk,fyd,step)<=0 or not 0<min_core_fraction<1:
            raise ValueError('Geometria/materiais inválidos')
        self.h=h;self.fck=fck;self.fyk=fyk;self.fyd=fyd;self.fc=.6*(1-fck/250)*fcd
        if self.fc<=0 or not families:raise ValueError('Materiais/armaduras inválidos')
        self.d=min(h/2+abs(f.bar.z_mm) for f in families)
        # Maximise available exterior concrete without reducing the minimum
        # core. Keep a separate uniform stress budget in each disjoint strip.
        total=1-min_core_fraction
        mins=[max((h/2-abs(f.bar.z_mm)+f.phi/2)/h for f in families if sign*f.bar.z_mm>0) for sign in (1,-1)]
        self.models=[]
        lo,hi=mins[0],total-mins[1]
        if hi<lo-1e-10:return
        # Anchor grid at mid-thickness, not at a particular face, so the
        # set of layouts is invariant under reflection through z=0.
        mid=total/2
        steps=range(math.ceil((lo-mid-1e-10)/step),math.floor((hi-mid+1e-10)/step)+1)
        fractions=sorted(set([lo,hi]+[min(hi,max(lo,mid+k*step)) for k in steps]))
        for plus in fractions:
            try:
                model=PhysicalCapacity(h,families,fyd,self.fc,subdivisions=subdivisions,net_area=True,band_fractions=(plus,total-plus))
            except ValueError:continue
            self.models.append(model)

    def assess(self,n,m,q,vrdc,*,force_links=False):
        n,m,q=map(lambda x:np.asarray(x,float),(n,m,q))
        if n.shape!=(3,) or m.shape!=(3,) or q.shape!=(2,) or not np.isfinite(np.r_[n,m,q,vrdc]).all() or vrdc<0:
            return AsymmetricTrial('Dados insuficientes')
        v=float(np.linalg.norm(q)); links=v>vrdc+1e-7 or (force_links and v>0)
        candidates=[];count=0
        for model in self.models:
            for cot in (1.,1.25,1.5,1.75,2.,2.25,2.5) if links else (0.,):
                if links:
                    cu=v/model.core_mm*(cot+1/cot)/self.fc
                    if cu>1+1e-7:continue
                    req=max(v*1e6/(model.core_mm*self.fyd*cot),.08*math.sqrt(self.fck)/self.fyk*1e6)
                    grid=link_grid(req,self.d)
                    if grid is None:continue
                    from wall_core_stress_field import reconstruct
                    field=reconstruct(q,model.core_mm,model.core_z_mm,cot,self.fc,self.fyd,grid[0])
                    if not field.valid:continue
                    nn,mm=n-field.n,m-field.m
                else:
                    field=None;cu=math.nan;req=0.;grid=(0.,0.,0.,0.);nn,mm=n,m
                count+=1
                u,res,_=model.check(nn,mm)
                if not np.isfinite(u) or u>1+1e-7:
                    a=solve(model,nn,mm)
                    if np.isfinite(a.util) and (not np.isfinite(u) or a.util<u):u,res=a.util,a.residual
                if not np.isfinite(u):continue
                candidates.append(AsymmetricTrial('Proposta experimental com treliça; amarração por confirmar' if links else 'Equilíbrio N-M experimental; corte avaliado separadamente por VRdc',u,*model.band_fractions,model.core_mm,model.core_z_mm,cot if links else math.nan,cu,req,*grid,res,count,field.residual if field is not None else math.nan,field.link_util if field is not None else math.nan))
        if not candidates:return AsymmetricTrial('Sem solução no ensaio assimétrico',candidates=count)
        feasible=[a for a in candidates if a.face_util<=1+1e-7]
        best=min(feasible,key=lambda a:(a.asw_proposed,max(a.face_util,a.core_util if links else 0),abs(a.core_z_mm))) if feasible else min(candidates,key=lambda a:a.face_util)
        from dataclasses import replace
        return replace(best,status=best.status if feasible else 'Capacidade insuficiente no ensaio assimétrico',candidates=count)

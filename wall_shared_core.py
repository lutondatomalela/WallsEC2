"""First-order sectional stress-field trial with one shared core budget.

Eight signed shell actions and zero transverse normal resultant are enforced
in the SAME LP. Exterior steel/struts retain their physical positions. Core
compressive directions include in-plane and inclined struts, all sharing one
trace limit; ties cancel the transverse normal force. This is a discrete
static model, NOT a compatibility/anchorage or EC2 shell certification. No
unprovided ties are credited in the actual design. Units: kN/m, kNm/m, mm.
"""
from dataclasses import dataclass
import math
import numpy as np
from scipy.optimize import linprog
from wall_lp_certificate import certify
from wall_physical_layers import load
from wall_core_equilibrium import link_grid

@dataclass(frozen=True)
class SharedTrial:
    status: str
    util: float = math.nan
    core_util: float = math.nan
    outer_util: float = math.nan
    asw_required: float = math.nan
    asw_proposed: float = math.nan
    phi: float = math.nan
    pitch_x: float = math.nan
    pitch_y: float = math.nan
    core_mm: float = math.nan
    core_z_mm: float = math.nan
    residual: float = math.nan
    min_principal_core: float = math.nan

class SharedCore:
    def __init__(self, model, fck, fyk, fc, *, azimuths=16):
        self.model=model; self.fc=fc; self.fck=fck; self.fyk=fyk
        if not np.isfinite([fck,fyk,fc]).all() or min(fck,fyk,fc)<=0 or azimuths<4 or azimuths%4:
            raise ValueError('Parâmetros inválidos para núcleo partilhado')
        self.azimuths=azimuths
        self.d=min(model.h/2+abs(f.bar.z_mm) for f in model.families)
        if any(f.bar.z_mm-f.phi/2 < model.core_z_mm+model.core_mm/2-1e-8 and
               f.bar.z_mm+f.phi/2 > model.core_z_mm-model.core_mm/2+1e-8 for f in model.families):
            raise ValueError('Varões intersectam núcleo reservado')

    def problem(self,q):
        m=self.model
        theta=np.arange(self.azimuths)*2*math.pi/self.azimuths
        if np.linalg.norm(q)>0:
            a=math.atan2(q[1],q[0]);theta=np.r_[theta,a,a+math.pi]
        dirs=[(math.cos(t),math.sin(t),0.) for t in theta]
        for cot in (1.,1.25,1.5,1.75,2.,2.25,2.5):
            d=math.sqrt(1+cot*cot)
            dirs.extend((cot*math.cos(t)/d,cot*math.sin(t)/d,-1/d) for t in theta)
        dirs=np.asarray(dirs); stress=-np.einsum('ki,kj->kij',dirs,dirs)
        n=stress[:,[0,1,0],[0,1,1]].T
        c=np.vstack((n,n*2*m.core_z_mm/m.h,stress[:,0,2],stress[:,1,2],stress[:,2,2]))
        outer=np.vstack((m.matrix,np.zeros((3,m.matrix.shape[1]))))
        tie=np.zeros((9,1));tie[-1,0]=1
        eq=np.column_stack((outer,c,tie))
        ub=np.zeros((len(m.cap)+1,eq.shape[1]));ub[:-1,:outer.shape[1]]=m.Aub[:,:-1];ub[-1,outer.shape[1]:-1]=1
        caps=np.r_[m.cap,self.fc*m.core_mm]
        bounds=m.bounds[:-1]+[(0,None)]*(len(dirs)+1)
        return eq,ub,caps,bounds,stress

    def assess(self,n,m,q):
        n,m,q=map(lambda x:np.asarray(x,float),(n,m,q))
        if n.shape!=(3,) or m.shape!=(3,) or q.shape!=(2,) or not np.isfinite(np.r_[n,m,q]).all():
            return SharedTrial('Dados insuficientes')
        eq,ub,caps,bounds,stress=self.problem(q)
        target=np.r_[load(n,m,self.model.h),q,0.]
        objective=np.zeros(eq.shape[1]);objective[-1]=1
        r=linprog(objective,A_ub=ub,b_ub=caps,A_eq=eq,b_eq=target,bounds=bounds,method='highs')
        if not r.success or not certify(r.x,eq,target,ub,caps,bounds).valid:
            return SharedTrial('Sem equilíbrio no campo discreto')
        req=max(0.,r.x[-1])*1e6/(self.model.core_mm*self.model.fyd)
        if np.linalg.norm(q)>1e-9:req=max(req,.08*math.sqrt(self.fck)/self.fyk*1e6)
        grid=link_grid(req,self.d)
        if grid is None:return SharedTrial('Sem proposta de ligações na grelha',asw_required=req)
        # With a fixed discrete tie proposal, calculate proportional capacity
        # of the whole eight-action tensor, not a maximum of separate checks.
        bounds[-1]=(0,grid[0]*self.model.core_mm*self.model.fyd/1e6)
        a=np.column_stack((eq,-target));b=np.column_stack((ub,np.zeros(len(caps))))
        bd=bounds+[(0,1024)]
        p=linprog(np.r_[np.zeros(eq.shape[1]),-1.],A_ub=b,b_ub=caps,A_eq=a,b_eq=np.zeros(9),bounds=bd,method='highs')
        if not p.success or not certify(p.x,a,np.zeros(9),b,caps,bd).valid or p.x[-1]<1-1e-7:
            return SharedTrial('Sem capacidade demonstrada com a proposta discreta',asw_required=req)
        # Recover actual-load stresses from the proportional solution.
        f=p.x[:-1]/p.x[-1]; ratios=(ub@f)/caps
        core=np.einsum('k,kij->ij',f[self.model.matrix.shape[1]:-1],stress)/self.model.core_mm
        residual=float(np.max(np.abs(eq@f-target)))
        if not np.any(target):util=0.
        else:util=1/p.x[-1]
        return SharedTrial('Equilíbrio experimental; ligações propostas, não instaladas' if req>0 else 'Equilíbrio experimental sem ligações',util,float(ratios[-1]),float(max(ratios[:-1])),req,*grid,self.model.core_mm,self.model.core_z_mm,residual,float(np.linalg.eigvalsh(core)[0]))


def assess_layouts(models,n,m,q,fck,fyk,fc,*,azimuths=16):
    """Search only layouts with a concrete-only core and fixed longitudinal steel."""
    valid=[]
    for model in models:
        try:r=SharedCore(model,fck,fyk,fc,azimuths=azimuths).assess(n,m,q)
        except ValueError:continue
        if math.isfinite(r.util):valid.append(r)
    return min(valid,key=lambda r:(r.asw_proposed,r.util,abs(r.core_z_mm))) if valid else SharedTrial('Sem equilíbrio no conjunto de núcleos')

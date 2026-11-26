"""Conditional static sandwich trial with explicit reserved core.

This is a stress-field diagnostic, not a validated EC2 shell design. All forces
are signed, tension positive; N,Q kN/m, M kNm/m, dimensions mm. The core strut
and transverse ties balance Q and Nzz=0 in an averaged continuum. Outer layers
use the existing 2D LP, with actual steel centroids. No credit for proposed ties.
"""
from dataclasses import dataclass, asdict
import math
import numpy as np
from wall_coupled_shear import truss_increment


@dataclass(frozen=True)
class CoreTrial:
    status: str
    band_fraction: float = math.nan
    core_mm: float = math.nan
    cot_theta: float = math.nan
    core_util: float = math.nan
    face_util: float = math.nan
    asw_required: float = math.nan
    asw_proposed: float = math.nan
    phi: float = math.nan
    pitch_x: float = math.nan
    pitch_y: float = math.nan
    residual: float = math.nan
    angular_refined: bool = False
    angular_factor_upper: float = math.nan
    tensor_residual: float = math.nan
    link_util: float = math.nan


def link_grid(required, d):
    """Candidate single effective normal leg per cell; no anchorage credit.
    Use 0.75d pitch cap in BOTH directions as conservative screen, not a full
    detailing check (EC2 9.2.2, slab/wall-specific rules still apply)."""
    if not math.isfinite(required) or required<0 or not math.isfinite(d) or d<=0:
        raise ValueError('Área/altura útil inválida')
    if required==0:return (0.,0.,0.,0.)
    candidates=[]
    for phi in (8.,10.,12.,16.):
        for sx in (75.,100.,125.,150.,175.,200.):
            if sx>0.75*d+1e-9:continue
            for sy in (75.,100.,125.,150.,175.,200.):
                if sy>0.75*d+1e-9:continue
                area=math.pi*phi**2/4*1e6/(sx*sy)
                if area>=required-1e-9:candidates.append((area,phi,sx,sy))
    return min(candidates,key=lambda x:(x[0],x[1],abs(x[2]-x[3]))) if candidates else None


class CoreEquilibrium:
    def __init__(self,h,families,fck,fcd,fyk,fyd,*,fractions=(.30,.35,.40),angles=(1.,1.25,1.5,1.75,2.,2.25,2.5)):
        from wall_physical_layers import PhysicalCapacity
        if min(h,fck,fcd,fyk,fyd)<=0:raise ValueError('Materiais inválidos')
        self.h=h;self.fck=fck;self.fyk=fyk;self.fyd=fyd;self.fc=.6*(1-fck/250)*fcd
        if self.fc<=0:raise ValueError('Betão fora do domínio')
        self.d=min(h/2+abs(f.bar.z_mm) for f in families)
        self.angles=tuple(angles);self.models=[]
        if not self.angles or any(not 1<=c<=2.5 for c in self.angles):raise ValueError('Ângulo inválido')
        for frac in fractions:
            # The core is concrete-only in this trial. Do not count a strip
            # that intersects the bar cross-section as an unoccupied core.
            if any(h/2-abs(f.bar.z_mm)+f.phi/2>frac*h+1e-9 for f in families):continue
            try:model=PhysicalCapacity(h,families,fyd,self.fc,band_fraction=frac,subdivisions=3,net_area=True)
            except ValueError:continue
            self.models.append((frac,model))

    def assess(self,n,m,q,vrdc):
        n,m,q=map(lambda x:np.asarray(x,float),(n,m,q))
        if n.shape!=(3,) or m.shape!=(3,) or q.shape!=(2,) or not np.isfinite(np.r_[n,m,q,vrdc]).all() or vrdc<0:
            return CoreTrial('Dados insuficientes')
        v=float(np.linalg.norm(q)); links=v>vrdc+1e-7
        candidates=[];best=math.inf
        for frac,model in self.models:
            core=self.h*(1-2*frac)
            for cot in self.angles if links else (0.,):
                if links:
                    # Uniaxial diagonal compression in the shear direction:
                    # |sigma_c|=v/core*(cot+tan); transverse ties balance Nzz.
                    core_u=v/core*(cot+1/cot)/self.fc
                    req=max(v*1e6/(core*self.fyd*cot),.08*math.sqrt(self.fck)/self.fyk*1e6)
                    # The tie force averaged across the wall thickness must
                    # balance the core transverse normal force v/cot. Since
                    # the core strut occupies only the core, area density is
                    # obtained with core thickness (conservative vs .9d).
                    if core_u>1+1e-7:continue
                    grid=link_grid(req,self.d)
                    if grid is None:continue
                    from wall_core_stress_field import reconstruct
                    field=reconstruct(q,core,0.,cot,self.fc,self.fyd,grid[0])
                    if not field.valid:continue
                    nn=n-field.n
                else:
                    field=None;core_u=math.nan;req=0.;grid=(0.,0.,0.,0.);nn=n
                u,res,_=model.check(nn,m)
                adaptive=None
                if not np.isfinite(u) or u>1+1e-7:
                    from wall_adaptive_capacity import solve
                    adaptive=solve(model,nn,m)
                    if np.isfinite(adaptive.util) and (not np.isfinite(u) or adaptive.util<u):
                        u,res=adaptive.util,adaptive.residual
                if np.isfinite(u):best=min(best,u)
                if not np.isfinite(u) or u>1+1e-7:continue
                candidates.append(CoreTrial('Proposta de treliça; instalação/amarração por confirmar' if links else 'Equilíbrio estático experimental; sem armadura específica pelo ensaio VRdc',frac,core,cot if links else math.nan,core_u,u,req,*grid,res,adaptive is not None,adaptive.factor_upper if adaptive is not None else math.nan,field.residual if field is not None else math.nan,field.link_util if field is not None else math.nan))
        if not candidates:return CoreTrial('Sem solução no modelo de núcleo/camadas; não demonstra rotura',face_util=best if math.isfinite(best) else math.nan)
        return min(candidates,key=lambda a:(a.asw_proposed,max(a.face_util, a.core_util if links else 0),-a.core_mm))


def flatten(trial):return {'Core_'+k:v for k,v in asdict(trial).items()}

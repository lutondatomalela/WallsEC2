"""Independent experimental section equilibrium (first order).

Plane sections, compression-only spectral concrete, signed axial steel,
parabola-rectangle concrete (normal strength), elastic-perfectly plastic steel.
Full depth is used: no reserve for transverse shear. The trace of compressive
stress is screened separately against the chosen reduced compression cap.
Not a full EC2 shell verification or a proof of failure if the solve fails.
Units: kN/m, kNm/m, mm, MPa. Tension positive.
"""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import least_squares

@dataclass(frozen=True)
class CompatibleResult:
    status: str
    residual_mpa: float
    concrete_strain: float
    steel_strain: float
    compression_ratio: float
    steel_stress_max: float
    strain_ratio: float


def compatible_equilibrium(h,n,m,bars,fc,fyd,eps_ud=.01,es=200000.,fibres=48,eps_c2=.002,eps_cu=.0035):
    bars=tuple(bars); n=np.asarray(n,float);m=np.asarray(m,float)
    if (n.shape!=(3,) or m.shape!=(3,) or not np.isfinite(np.r_[n,m,h,fc,fyd,eps_ud,es,eps_c2,eps_cu]).all()
        or min(h,fc,fyd,eps_ud,es,eps_c2)<=0 or eps_cu<eps_c2 or fibres<8
        or any(b.axis not in (0,1) or not np.isfinite([b.z_mm,b.area_mm2_m]).all() or abs(b.z_mm)>=h/2 or b.area_mm2_m<=0 for b in bars)):
        raise ValueError('Dados inválidos para equilíbrio compatível')
    root=np.sqrt(2); scale=np.array([1.,1.,root]);target=np.r_[n*scale/h,m*scale*2000/h**2]
    s=(np.arange(fibres)+.5)*2/fibres-1
    w=np.full(fibres,1/fibres); steel=np.zeros((len(bars),6)); area=np.array([b.area_mm2_m for b in bars])/(1000*h)
    zbar=np.array([2*b.z_mm/h for b in bars])
    if area.sum()>=1:raise ValueError('Área de aço incompatível com a secção')
    for j,b in enumerate(bars):
        steel[j,b.axis]=1;steel[j,b.axis+3]=zbar[j]
    # Integrate the gross concrete and deduct the displaced concrete
    # resultants at each actual bar centroid. This point-area approximation
    # avoids negative strip weights with coincident or dense families. It
    # is consistent with the transformed elastic section; finite bar size
    # and local stress gradients across a bar are not resolved.
    def tensors(v):
        a=np.empty(v.shape[:-1]+(2,2));a[...,0,0]=v[...,0];a[...,1,1]=v[...,1];a[...,0,1]=a[...,1,0]=v[...,2]/root;return a
    def concrete(v):
        e,vec=np.linalg.eigh(tensors(v)); c=np.clip(-e/eps_c2,0,1);sig=-fc*(2*c-c*c)
        st=(vec*sig[:,None,:])@vec.swapaxes(-1,-2)
        return np.stack((st[:,0,0],st[:,1,1],root*st[:,0,1]),axis=1),e,sig
    def state(x):
        q=x*.001;sig,_,_=concrete(q[:3]+s[:,None]*q[3:]);ss=np.clip(es*(steel@q),-fyd,fyd)
        displaced,_,_=concrete(q[:3]+zbar[:,None]*q[3:])
        return np.r_[w@sig-area@displaced,(w*s)@sig-(area*zbar)@displaced]+steel.T@(area*ss)
    # Multi-stage load stepping improves robustness near the yield plateau.
    x=np.zeros(6)
    tol=max(1e-7,1e-7*np.max(np.abs(target)))
    for factor in (.25,.5,.75,1.):
        t=factor*target
        fit=least_squares(lambda v:state(v)-t,x,bounds=(-40.,40.),max_nfev=120,ftol=1e-10,gtol=1e-10,xtol=1e-10)
        x=fit.x
        if np.max(np.abs(state(x)-t))>tol:break
    q=x*.001;res=float(np.max(np.abs(state(x)-target)))
    _,e,sig=concrete(q[:3]+np.array([-1.,1.])[:,None]*q[3:]);_,_,all_sig=concrete(q[:3]+s[:,None]*q[3:]);
    cs=max(0.,-float(e.min())); st=float(np.max(np.abs(steel@q),initial=0)); cr=float(max(np.max(-sig.sum(axis=1)),np.max(-all_sig.sum(axis=1)))/fc);sr=max(cs/eps_cu,st/eps_ud)
    if res>tol: status='Sem equilíbrio demonstrado'
    elif sr>1+1e-7:status='Limites de extensão excedidos no modelo'
    elif cr>1+1e-7:status='Compressão biaxial acima do orçamento reduzido'
    else:status='Equilíbrio compatível experimental; sem corte transversal'
    return CompatibleResult(status,res,cs,st,cr,float(np.max(np.abs(np.clip(es*(steel@q),-fyd,fyd)),initial=0)),sr)

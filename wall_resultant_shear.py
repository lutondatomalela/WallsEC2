"""Directional shear screen: EN 1992-2 LL.109–110; EN 1992-1-1 6.2.2.
Not a full sandwich check: anchorage, core depth and shear-induced longitudinal
forces are not verified. Tension positive; N, Q kN/m, depth mm.
"""
import numpy as np

def resultant_shear(h, families, n, q, fck, fcd, gamma_c, *, compression_credit=False):
    n=np.asarray(n,float); q=np.asarray(q,float)
    if n.ndim!=2 or n.shape[1]!=3 or q.shape!=(len(n),2) or min(h,fck,fcd,gamma_c)<=0 or not np.isfinite([h,fck,fcd,gamma_c]).all():
        raise ValueError('Dados inválidos para corte resultante')
    v=np.hypot(q[:,0],q[:,1]); nz=v>0
    direction=np.divide(q,v[:,None],out=np.zeros_like(q),where=nz[:,None]); direction[~nz,0]=1
    weights=direction**2
    normal=n[:,0]*weights[:,0]+n[:,1]*weights[:,1]+2*n[:,2]*direction[:,0]*direction[:,1]
    sig=np.minimum(.2*fcd if compression_credit else 0.,-normal/h)
    caps=[]; depths=[]; rhos=[]
    for side in (1,-1):
        a=[]; d=[]
        for axis in (0,1):
            bars=[f.bar for f in families if f.bar.axis==axis and f.bar.z_mm*side>0]
            if not bars:raise ValueError('Falta armadura numa direcção/face')
            areas=np.array([b.area_mm2_m for b in bars]); dd=np.array([h/2+abs(b.z_mm) for b in bars]); a.append(areas.sum());d.append(np.average(dd,weights=areas))
        depth=np.min(np.where(weights>1e-12,np.array(d),np.inf),axis=1)
        rho=np.minimum(.02,weights@ (np.array(a)/(1000*np.array(d))))
        k=np.minimum(2.,1+np.sqrt(200/depth)); c=np.maximum(.18/gamma_c*k*(100*rho*fck)**(1/3),.035*k**1.5*np.sqrt(fck))
        caps.append(np.maximum(0,c+.15*sig)*depth);depths.append(depth);rhos.append(rho)
    governing=np.argmin(caps,axis=0); i=np.arange(len(n)); cap=np.asarray(caps)[governing,i]
    ratio=np.divide(v,cap,out=np.full_like(v,np.inf),where=cap>0);ratio[~nz]=0
    valid=np.isfinite(n).all(axis=1)&np.isfinite(q).all(axis=1)
    return {'PhysShear_VEd_kN_m':np.where(valid,v,np.nan),'PhysShear_angle_deg':np.where(valid,np.degrees(np.arctan2(q[:,1],q[:,0])),np.nan),
            'PhysShear_VRdc_kN_m':np.where(valid,cap,np.nan),'PhysShear_util':np.where(valid,ratio,np.nan),
            'PhysShear_d_mm':np.where(valid,np.asarray(depths)[governing,i],np.nan),'PhysShear_rho':np.where(valid,np.asarray(rhos)[governing,i],np.nan),
            'PhysShear_sigma_cp_MPa':np.where(valid,sig,np.nan),'PhysShear_face':np.where(valid,np.where(governing==0,'+','-'),'?'),
            'PhysShear_status':np.where(~valid,'Dados insuficientes',np.where(ratio>1,'Corte resultante: requer análise adicional','Corte resultante: triagem experimental'))}


def transfer_shear_reserve(h, families, n, q, fck, fcd, gamma_c):
    """Lower bound of VRdc for every direction, without favourable compression.

    The positive margin is an allowable bound on an externally determined
    additional transverse shear magnitude (triangle inequality). Not a
    calculation of LL.115 transfer demand; no ties assumed. The concrete
    shear law still requires longitudinal anchorage and its other conditions.
    """
    n,q=np.asarray(n,float),np.asarray(q,float)
    if n.ndim!=2 or n.shape[1]!=3 or q.shape!=(len(n),2) or not np.isfinite(np.c_[n,q]).all() or min(h,fck,fcd,gamma_c)<=0:
        raise ValueError('Dados inválidos para reserva de corte')
    tension=np.maximum(0.,(n[:,0]+n[:,1])/2+np.hypot((n[:,0]-n[:,1])/2,n[:,2]))
    capacities=[]
    for side in (1,-1):
        aa=[];dd=[]
        for axis in (0,1):
            bars=[f.bar for f in families if f.bar.axis==axis and f.bar.z_mm*side>0]
            if not bars:raise ValueError('Falta armadura numa direcção/face')
            areas=np.array([b.area_mm2_m for b in bars]); depths=np.array([h/2+abs(b.z_mm) for b in bars])
            aa.append(areas.sum());dd.append(np.average(depths,weights=areas))
        rho=min(.02,*[a/(1000*d) for a,d in zip(aa,dd)])
        k=min(2.,1+np.sqrt(200/max(dd)))
        c=max(.18/gamma_c*k*(100*rho*fck)**(1/3),.035*k**1.5*np.sqrt(fck))
        capacities.append(np.maximum(0.,c-.15*tension/h)*min(dd))
    cap=np.minimum(*capacities);v=np.linalg.norm(q,axis=1)
    return cap,cap-v


def check_additional_shear(capacity, original, additional_bound):
    """Compare a documented nonnegative external upper bound, never infer it."""
    cap,v,extra=np.broadcast_arrays(np.asarray(capacity,float),np.asarray(original,float),np.asarray(additional_bound,float))
    valid=np.isfinite(cap)&np.isfinite(v)&np.isfinite(extra)&(cap>=0)&(v>=0)&(extra>=0)
    return np.where(valid,np.where(v+extra<=cap,'Limite sem armadura específica satisfeito','Limite sem armadura específica não demonstrado'),'Dados insuficientes')

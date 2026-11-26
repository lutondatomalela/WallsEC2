"""NP EN 1992-1-1:2010 Annex F membrane reference (tension positive).

Force resultants kN/m; thickness mm; strengths MPa; steel force kN/m.
Annex F.1(2)-(5), expressions F.1-F.10. The alternative tensile
reinforcement forces are constrained to [0.5,2] times the optimum.
This function verifies only a uniform, planar membrane layer. Applying it
to a nominal shell split is a diagnostic, not a shell design certification.
No compression reinforcement, local anchorage or through-thickness shear.
"""
import numpy as np


def membrane_reference(n, cap, thickness, fck, fcd):
    n=np.asarray(n,float);cap=np.asarray(cap,float)
    if n.shape[-1:]!=(3,) or cap.shape!=n.shape[:-1]+(2,) or not np.isfinite(n).all() or not np.isfinite(cap).all() or (cap<0).any() or not np.isfinite([thickness,fck,fcd]).all() or thickness<=0 or not 12<=fck<=90 or fcd<=0:
        raise ValueError('Dados inválidos para Anexo F')
    x,y,q=np.moveaxis(n,-1,0); a=np.abs(q)
    swap=x>y; u=np.minimum(x,y);v=np.maximum(x,y)
    # Both principal stresses strictly compressive: F.1(3).
    hi=(x+y)/2+np.hypot((x-y)/2,q)
    lo=(x+y)/2-np.hypot((x-y)/2,q)
    both=hi<0
    zero=(x==0)&(y==0)&(q==0)
    # F.2-7, with most compressive direction first as prescribed.
    branch=-u>a
    with np.errstate(divide='ignore',invalid='ignore'):
        bb=np.divide(a*a,-u,out=np.zeros_like(a),where=branch)
    tx=np.where(branch,0.,u+a);ty=np.where(branch,v+bb,v+a)
    opt=np.stack((np.where(swap,ty,tx),np.where(swap,tx,ty)),axis=-1)
    opt=np.maximum(opt,0.);opt=np.where(both[...,None]|zero[...,None],0.,opt)
    # Determine feasible tensile force intervals under F.8-10 restrictions.
    low=.5*opt;high=np.minimum(2*opt,cap)
    lower=np.maximum(0.,low[...,0]-x); upper=high[...,0]-x
    bmin=np.maximum(0.,low[...,1]-y);bmax=high[...,1]-y
    with np.errstate(divide='ignore',invalid='ignore'):
        alow=np.divide(a*a,bmax,out=np.full_like(a,np.inf),where=bmax>0)
        ahigh=np.divide(a*a,bmin,out=np.full_like(a,np.inf),where=bmin>0)
    amin=np.maximum(lower,alow);amax=np.minimum(upper,ahigh)
    ac=np.minimum(np.maximum(a,amin),amax)
    bc=np.divide(a*a,ac,out=np.full_like(a,np.inf),where=ac>0)
    no_shear=a==0
    # For zero shear use the direct F.2-7 solution, no angle redistribution.
    ac=np.where(no_shear,np.maximum(-x,0.),ac);bc=np.where(no_shear,np.maximum(-y,0.),bc)
    # In the strict compression branch use the applied tensor directly.
    ac=np.where(both,-x,ac);bc=np.where(both,-y,bc)
    steel=np.stack((x+ac,y+bc),axis=-1)
    stress=(ac+bc)/thickness
    stress=np.where(both,-lo/thickness,stress)
    strength=np.where(both,fcd,.6*(1-fck/250)*fcd)
    tol=1e-8*np.maximum(1,np.abs(n).sum(axis=-1)+cap.sum(axis=-1))
    admissible=(np.isfinite(stress)&np.isfinite(steel).all(axis=-1)&(ac>=-tol)&(bc>=-tol)&
                (steel>=-tol[...,None]).all(axis=-1)&(steel<=cap+tol[...,None]).all(axis=-1)&
                (steel>=low-tol[...,None]).all(axis=-1)&(steel<=high+tol[...,None]).all(axis=-1)&
                ((no_shear|both)|(amin<=amax+tol))&(stress<=strength+tol/thickness))
    return dict(ok=admissible,steel_opt=opt,steel=np.where(admissible[...,None],steel,np.nan),
                concrete=np.where(admissible[...,None],np.stack((-ac,-bc,q),axis=-1),np.nan),
                concrete_stress_mpa=np.where(admissible,stress,np.nan),
                concrete_limit_mpa=strength,compression_only=both)


def nominal_shell_reference(n,m,areas,h,z,fck,fcd,fyd):
    """Independent F.1 reference on nominal concentric steel/concrete faces.
    Never substitute for actual geometry, Q, stability or crack checks.
    """
    n,m,areas=map(lambda x:np.asarray(x,float),(n,m,areas))
    if n.shape!=m.shape or areas.shape!=n.shape[:-1]+(4,) or not 0<z<h or fyd<=0:raise ValueError('Geometria de casca inválida')
    thickness=min(h-z,z)
    plus=membrane_reference(n/2+1000*m/z,areas[...,[0,2]]*fyd/1000,thickness,fck,fcd)
    minus=membrane_reference(n/2-1000*m/z,areas[...,[1,3]]*fyd/1000,thickness,fck,fcd)
    return plus,minus

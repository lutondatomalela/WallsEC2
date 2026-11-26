"""Adaptive angular refinement of the fixed-band lower-bound stress field.

This removes angular discretisation error only. Compression strength, band
thickness, steel positions and tension-only steel remain those of the input
PhysicalCapacity. No EC2 shell verdict, no transverse shear or stability claim.
Each successful primal LP is a statically admissible discrete stress field.
The continuous angular relaxation is bounded by the corrected dual objective.
"""
from dataclasses import dataclass
import math
import numpy as np
from scipy.optimize import linprog
from wall_lp_certificate import certify

@dataclass(frozen=True)
class AdaptiveResult:
    util: float
    residual: float
    factor_lower: float
    factor_upper: float
    iterations: int
    converged: bool
    status: str


def solve(model, n, m, *, max_iterations=32, relative_gap=1e-5):
    from wall_physical_layers import load
    q=load(n,m,model.h)
    if q.shape!=(6,) or not np.isfinite(q).all() or max_iterations<1 or relative_gap<=0:
        raise ValueError('Dados inválidos para refinamento angular')
    if not np.any(q):return AdaptiveResult(0.,0.,math.inf,math.inf,0,True,'Equilíbrio nulo')
    matrix=model.matrix.copy(); aub=model.Aub[:,:-1].copy(); bounds=list(model.bounds[:-1]); cap=np.asarray(model.cap,float)
    last=None
    for it in range(1,max_iterations+1):
        eq=np.column_stack((matrix,-q)); ub=np.column_stack((aub,np.zeros(len(cap))))
        r=linprog(np.r_[np.zeros(matrix.shape[1]),-1.],A_ub=ub,b_ub=cap,A_eq=eq,b_eq=np.zeros(6),bounds=bounds+[(0,1024)],method='highs')
        if not r.success:
            if last is not None:break
            return AdaptiveResult(math.nan,math.nan,math.nan,math.nan,it,False,'Falha solver angular')
        certificate=certify(r.x,eq,np.zeros(6),ub,cap,bounds+[(0,1024)])
        res=certificate.equality_error
        if not certificate.valid:
            if last is not None:break
            return AdaptiveResult(math.nan,res,math.nan,math.nan,it,False,'Equilíbrio não demonstrado')
        factor=float(r.x[-1])
        y=np.asarray(r.eqlin.marginals); mu=np.asarray(r.ineqlin.marginals)
        if not np.isfinite(np.r_[y,mu]).all():
            return AdaptiveResult(1/factor if factor>1e-10 else math.inf,res,factor,math.nan,it,False,"Ponto primal válido; limite dual indisponível")
        cols=[]; ubcols=[]; corrections=[]
        for j,z in enumerate(model.centers):
            v=y[:3]+2*z/model.h*y[3:]
            eig,vec=np.linalg.eigh([[v[0],v[2]/2],[v[2]/2,v[1]]])
            # max over all compression strut directions of y @ column.
            violation=max(0.,float(-eig[0]+mu[j]));corrections.append(violation)
            if violation>1e-9:
                c,s=vec[:,0]; sig=-np.array([c*c,s*s,c*s]);cols.append(np.r_[sig,sig*2*z/model.h]);u=np.zeros(len(cap));u[j]=1;ubcols.append(u)
        # For min(-factor), correcting each dual multiplier downwards makes
        # all continuous angular columns dual feasible; steel and load
        # columns unchanged. Dual correction bounds the maximum factor.
        upper=min(1024.,max(factor,factor+float(cap@np.array(corrections))))
        converged=upper-factor<=relative_gap*max(1.,factor)
        last=AdaptiveResult(1/factor if factor>1e-10 else math.inf,res,factor,upper,it,converged,
                            'Intervalo angular convergido' if converged else 'Limite angular parcial')
        if converged or not cols:break
        matrix=np.column_stack((matrix,*cols));aub=np.column_stack((aub,*ubcols));bounds.extend([(0,None)]*len(cols))
    return last

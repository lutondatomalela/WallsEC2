"""Numerical certificate for a proposed LP point (not structural certification).
Check the actual primal point, independent of the solver's success flag.
All tolerances are absolute, in the scaled force coordinates of the model.
"""
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class PrimalCertificate:
    valid: bool
    equality_error: float
    inequality_excess: float
    bound_excess: float


def certify(x, a_eq, b_eq, a_ub, b_ub, bounds, *, tolerance=1e-6):
    x=np.asarray(x,float)
    a_eq,b_eq,a_ub,b_ub=map(lambda a:np.asarray(a,float),(a_eq,b_eq,a_ub,b_ub))
    if (x.ndim!=1 or len(bounds)!=len(x) or a_eq.shape!=(len(b_eq),len(x))
            or a_ub.shape!=(len(b_ub),len(x)) or not np.isfinite(tolerance) or tolerance<0
            or not all(np.isfinite(a).all() for a in (x,a_eq,b_eq,a_ub,b_ub))):
        return PrimalCertificate(False,np.inf,np.inf,np.inf)
    eq=float(np.max(np.abs(a_eq@x-b_eq),initial=0))
    ub=float(np.max(a_ub@x-b_ub,initial=0))
    be=0.
    for value,(lo,hi) in zip(x,bounds):
        if lo is not None:be=max(be,float(lo-value))
        if hi is not None:be=max(be,float(value-hi))
    return PrimalCertificate(max(eq,ub,be)<=tolerance,eq,ub,be)

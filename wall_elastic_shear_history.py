"""Elastic 3D stress screen for a rectangular shell strip, not a crack law.

The in-plane field is affine in z (transformed plane-stress section). The
transverse shear trial is the gross rectangular parabolic distribution,
with zero traction on the two free faces and integral equal to Q. It is not
a local 3D elasticity solution at discontinuities, nor a cracked shear model.

For each half thickness we bound the largest eigenvalue of THIS trial field.
Convexity of lambda_max on a segment plus Weyl's inequality bounds the missed
quadratic shear term by 1.5*|Q|/h*(delta_t**2)/4, t=2*z/h. This bound does
not include modeling uncertainty, imposed strains, or early-age cracking.
"""
from dataclasses import dataclass
import numpy as np

@dataclass(frozen=True)
class ElasticShearScreen:
    tensile_sample_mpa: np.ndarray
    tensile_upper_mpa: np.ndarray
    interpolation_bound_mpa: np.ndarray


def screen(h, strains, transverse, ec, *, nu=.2, intervals=16):
    """Rows: generalized strains [ex,ey,gxy, kx*h/2,ky*h/2,kxy*h/2].
    Q in kN/m, h in mm, E in MPa. Output columns +z/-z. Invalid rows are NaN.
    No normal transverse stress is assumed. The half-thickness split only
    locates candidate tension; it is not the effective area of a crack.
    """
    strains=np.asarray(strains,float); q=np.asarray(transverse,float)
    if (strains.ndim!=2 or strains.shape[1]!=6 or q.shape!=(len(strains),2)
        or not np.isfinite([h,ec,nu]).all() or min(h,ec)<=0 or not 0<=nu<.5
        or not isinstance(intervals,int) or isinstance(intervals,bool) or intervals<1):
        raise ValueError('Dados inválidos para triagem elástica 3D')
    out=np.full((len(q),2),np.nan);bound=np.full(len(q),np.nan)
    valid=np.isfinite(strains).all(axis=1)&np.isfinite(q).all(axis=1)
    if valid.any():
        v=strains[valid]; Q=q[valid]; D=ec/(1-nu**2)*np.array([[1,nu,0],[nu,1,0],[0,0,(1-nu)/2]])
        mid=v[:,:3]@D.T; slope=v[:,3:]@D.T; shear=1.5*Q/h
        # Stream one depth at a time; no nrows*ndepths tensor allocation.
        S=np.zeros((len(v),3,3)); maxima=[]
        for side in (1.,-1.):
            peak=np.zeros(len(v))
            for t in np.linspace(0,side,intervals+1):
                plane=mid+t*slope; tau=shear*(1-t*t)
                S[:,0,0]=plane[:,0]; S[:,1,1]=plane[:,1]
                S[:,0,1]=S[:,1,0]=plane[:,2]
                S[:,0,2]=S[:,2,0]=tau[:,0]; S[:,1,2]=S[:,2,1]=tau[:,1]
                peak=np.maximum(peak,np.linalg.eigvalsh(S)[:,-1])
            maxima.append(peak)
        out[valid]=np.column_stack(maxima)
        bound[valid]=np.hypot(shear[:,0],shear[:,1])/(4*intervals**2)
    return ElasticShearScreen(out,out+bound[:,None],bound)

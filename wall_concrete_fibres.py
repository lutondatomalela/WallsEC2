"""Exact net concrete area and first moment by thickness slice.
Stress integration is still piecewise uniform, not a constitutive validation.
"""
import numpy as np


def net_slices(h, families, centers, widths):
    z=np.asarray(centers,float); w=np.asarray(widths,float)
    if (not np.isfinite(h) or h<=0 or z.ndim!=1 or not z.size or z.shape!=w.shape
            or not np.isfinite(np.r_[z,w]).all() or np.any(w<=0)):
        raise ValueError('Discretização inválida')
    lo=z-w/2;hi=z+w/2;order=np.argsort(lo)
    if np.any(lo < -h/2-1e-8) or np.any(hi > h/2+1e-8) or np.any(lo[order][1:] < hi[order][:-1]-1e-8):
        raise ValueError('Subcamadas fora da secção ou sobrepostas')
    a=w.copy(); first=w*z
    for f in families:
        radius=f.phi/2; zb=f.bar.z_mm; area=f.bar.area_mm2_m/1000
        if radius<=0 or area<=0 or abs(zb)+radius>h/2+1e-9 or not np.isfinite([radius,zb,area]).all():
            raise ValueError('Família fora da secção')
        x=np.clip((lo-zb)/radius,-1,1);y=np.clip((hi-zb)/radius,-1,1)
        def F(t):return (np.arcsin(t)+t*np.sqrt(np.maximum(0,1-t*t)))/np.pi+.5
        def G(t):return -2/(3*np.pi)*np.maximum(0,1-t*t)**1.5
        portion=F(y)-F(x)
        if not np.isclose(portion.sum(),1.,rtol=0,atol=1e-8):
            raise ValueError('Varão fora das bandas resistentes')
        a-=area*portion
        first-=area*(zb*portion+radius*(G(y)-G(x)))
    if np.any(a<=0) or not np.isfinite(np.r_[a,first]).all():
        raise ValueError('Área líquida de betão insuficiente numa fibra')
    centroid=first/a
    if np.any(centroid<lo-1e-8) or np.any(centroid>hi+1e-8):
        raise ValueError('Centroide líquido fora da subcamada')
    return a,centroid


def net_fibre_geometry(h,families,fibres=48):
    if not np.isfinite(h) or h<=0 or not isinstance(fibres,int) or fibres<8:
        raise ValueError('Discretização inválida')
    z=(np.arange(fibres)+.5)*h/fibres-h/2
    a,centroid=net_slices(h,families,z,np.full(fibres,h/fibres))
    return a/h,2*centroid/h


def net_weights(h,families,fibres=48):
    return net_fibre_geometry(h,families,fibres)[0]

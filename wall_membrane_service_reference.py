"""Independent exact equilibrium for a symmetric, membrane-only cracked section.
Same compression-only spectral constitutive law as wall_shell_service, not a
validation of that law. No bending, Poisson effect, bond or crack-width law.
N tension positive, kN/m; A in mm2/m; dimensions mm; stress MPa.
"""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import brentq

@dataclass(frozen=True)
class MembraneReference:
    strain: np.ndarray
    steel_stress: np.ndarray
    concrete_stress: np.ndarray
    regime: str


def membrane_service(n,h,ax,ay,ec,es=200000.):
    n=np.asarray(n,float)
    if n.shape!=(3,) or not np.isfinite(np.r_[n,h,ax,ay,ec,es]).all() or min(h,ax,ay,ec,es)<=0 or (ax+ay)/1000>=h:
        raise ValueError('Dados de membrana inválidos')
    nx,ny,q=n; a=np.array([ax,ay])/1000; ac=h-a.sum(); k=a*es
    e=np.r_[n[:2]/(ac*ec+k),q/(ac*ec)]
    if np.linalg.eigvalsh([[e[0],e[2]],[e[2],e[1]]])[-1]<=0:
        return MembraneReference(e,es*e[:2],ec*e,'Compressão biaxial')
    if q==0:
        e=np.r_[np.where(n[:2]>=0,n[:2]/k,n[:2]/(ac*ec+k)),0.]
        return MembraneReference(e,es*e[:2],ec*np.minimum(e,0),'Sem corte')
    # Positive compression resultants a_c, b_c. a_c*b_c=q² for rank-one
    # compression. Equilibrium gives steel axial strains. Coaxiality of
    # stress and strain eliminates the remaining tensile principal strain.
    u=abs(q)
    def state(t):
        c=u*np.exp(t); b=u*np.exp(-t); ec1=-(c+b)/(ac*ec)
        ex=(nx+c)/k[0]; ey=(ny+b)/k[1]
        return c,b,ec1,ex,ey
    def objective(t):
        c,b,ec1,ex,ey=state(t)
        return c*(ex-ec1)-b*(ey-ec1)
    t=brentq(objective,-35,35,xtol=1e-13)
    c,b,ec1,ex,ey=state(t); et=ex+ey-ec1
    if et<-1e-10:raise ValueError('Raiz fora do domínio de membrana fendilhada')
    # Concrete compression shear has same sign as the applied shear;
    # strain shear is obtained from the two principal directions.
    exy=(et-ec1)*q/(c+b)
    return MembraneReference(np.array([ex,ey,exy]),es*np.array([ex,ey]),np.array([-c,-b,q])/ac,'Campo de compressão uniaxial')

"""Faixa rectangular: compatibilidade de extensões EC2 3.1.7/6.1.

Unidades internas: N, mm, MPa. Esforço normal positivo = compressão;
momento positivo = tracção na face + (coordenada y positiva).
"""
from dataclasses import dataclass
import math
from functools import lru_cache
import numpy as np


@dataclass(frozen=True)
class Section:
    h: float
    cover_axis: float
    as_plus: float
    as_minus: float
    fck: float = 30.0
    fcd: float = 20.0
    fyd: float = 500/1.15
    es: float = 200000.0
    eps_ud: float = 0.01
    fibres: int = 160

    def __post_init__(self):
        for name in ('h','cover_axis','as_plus','as_minus','fck','fcd','fyd','es','eps_ud'):
            if not math.isfinite(getattr(self,name)) or getattr(self,name)<=0:
                raise ValueError(f'Parâmetro de secção inválido: {name}')
        if not 0 < self.cover_axis < self.h/2 or not 12 <= self.fck <= 90:
            raise ValueError('Geometria/classe de betão fora do domínio')
        if self.fibres < 40 or self.eps_ud <= self.fyd/self.es:
            raise ValueError('Discretização ou extensão última do aço inválida')

    @property
    def eps_c2(self):
        return .002 if self.fck <= 50 else (2+.085*(self.fck-50)**.53)/1000

    @property
    def eps_cu(self):
        return .0035 if self.fck <= 50 else (2.6+35*((90-self.fck)/100)**4)/1000

    @property
    def exponent(self):
        return 2 if self.fck <= 50 else 1.4+23.4*((90-self.fck)/100)**4

    def concrete_stress(self, strain):
        ratio=np.clip(np.asarray(strain)/self.eps_c2,0,1)
        return self.fcd*(1-(1-ratio)**self.exponent)

    def response(self, top, bottom):
        y=(np.arange(self.fibres)+.5)*self.h/self.fibres-self.h/2
        eps=(top+bottom)/2+(bottom-top)*y/self.h
        stress=self.concrete_stress(eps)
        force=stress*1000*self.h/self.fibres
        ys=np.array([self.h/2-self.cover_axis,-self.h/2+self.cover_axis])
        steel_eps=(top+bottom)/2+(bottom-top)*ys/self.h
        steel_stress=np.clip(self.es*steel_eps,-self.fyd,self.fyd)
        areas=np.array([self.as_plus,self.as_minus])
        # Área líquida de betão nos níveis de armadura.
        steel_force=(steel_stress-self.concrete_stress(steel_eps))*areas
        return float((force.sum()+steel_force.sum())/1000),float(-(force@y+steel_force@ys)/1e6)

    @lru_cache(maxsize=256)
    def interaction(self, points=160):
        # Domínios 1/2: limite de extensão do aço na face extrema, conservador.
        profiles=[(a,-self.eps_ud) for a in np.linspace(-self.eps_ud,self.eps_cu,points)]
        # Domínios 3/4: compressão extrema eps_cu; zona traccionada variável.
        profiles += [(self.eps_cu,b) for b in np.linspace(-self.eps_ud,0,points)]
        # Domínio 5: rotação em torno do ponto C; compressão uniforme eps_c2.
        pivot=1-self.eps_c2/self.eps_cu
        if pivot>1e-10:
            profiles += [(a,self.eps_c2-(a-self.eps_c2)*(1-pivot)/pivot)
                         for a in np.linspace(self.eps_cu,self.eps_c2,points)]
        else:
            profiles += [(self.eps_c2,self.eps_c2)]
        return np.array([self.response(a,b) for a,b in profiles]+[self.response(b,a) for a,b in profiles])

    def moment_bounds(self,n_kn,points=160):
        # Intersecções dos ramos de compatibilidade com NEd constante.
        curve=self.interaction(points)
        values=[]
        for branch in np.split(curve,2):
            for (n0,m0),(n1,m1) in zip(branch[:-1],branch[1:]):
                if min(n0,n1)-1e-8 <= n_kn <= max(n0,n1)+1e-8:
                    if abs(n1-n0)<1e-10:
                        values += [m0,m1]
                    else:
                        values.append(m0+(m1-m0)*(n_kn-n0)/(n1-n0))
        if not values:
            return None
        return min(values),max(values)

    def check(self,n_kn,m_knm,points=160):
        bounds=self.moment_bounds(n_kn,points)
        if bounds is None:
            return dict(utilisation=float('inf'),mrd=0.0,status='Não conforme')
        capacity=bounds[1] if m_knm >=0 else -bounds[0]
        utilisation=abs(m_knm)/capacity if capacity>1e-9 else (0.0 if abs(m_knm)<1e-9 else float('inf'))
        return dict(utilisation=utilisation,mrd=max(0.0,capacity),status='OK' if utilisation<=1+1e-6 else 'Não conforme')

    def service(self,n_kn,m_knm,creep=0.0):
        """Secção elástica fendilhada: betão traccionado desprezado.

        Resolve equilíbrio com conjunto activo de fibras comprimidas. Retorna
        tensões reais no aço; fluência entra por Ec,eff = Ecm/(1+phi).
        """
        if not math.isfinite(creep) or creep<0:
            raise ValueError('Coeficiente de fluência inválido')
        ec=22000*((self.fck+8)/10)**.3/(1+creep)
        y=(np.arange(self.fibres)+.5)*self.h/self.fibres-self.h/2
        ys=np.array([self.h/2-self.cover_axis,-self.h/2+self.cover_axis])
        areas=np.array([self.as_plus,self.as_minus])
        dy=1000*self.h/self.fibres
        eps0=0.0; k=0.0
        target=np.array([n_kn*1000,m_knm*1e6])
        for _ in range(100):
            compressed=(eps0-k*y)>=0
            weights=ec*dy*compressed
            steel_weights=self.es*areas-ec*areas*((eps0-k*ys)>=0)
            mat=np.array([[weights.sum()+steel_weights.sum(),-weights@y-steel_weights@ys],
                          [-weights@y-steel_weights@ys,weights@(y*y)+steel_weights@(ys*ys)]])
            new=np.linalg.solve(mat,target)
            if np.max(np.abs(new-np.array([eps0,k])))<1e-13:
                eps0,k=new
                break
            eps0,k=new
        else:
            raise ValueError('Secção fendilhada sem convergência em ELS')
        strains=eps0-k*ys
        steel=self.es*strains
        concrete=ec*np.maximum(eps0-k*y,0)
        steel_force=(steel-ec*np.maximum(strains,0))*areas
        residual=np.array([concrete.sum()*dy+steel_force.sum(),-concrete@y*dy-steel_force@ys])-target
        if max(abs(residual[0])/max(1,abs(target[0])),abs(residual[1])/max(1,abs(target[1])))>1e-6:
            raise ValueError('Resíduo de equilíbrio ELS excessivo')
        return dict(sigma_plus=float(steel[0]),sigma_minus=float(steel[1]),
                    concrete_max=float(concrete.max()),eps0=float(eps0),curvature=float(k),
                    residual_n=float(residual[0]),residual_m=float(residual[1]))


def nominal_stiffness(n_kn,m0_knm,h,as_total,axis_cover,fck,fcd,fyd,l0_mm,phi_eff=0.0,beta=math.pi**2/8):
    """EC2 5.8.7: faixa isolada, N/secção constantes, l0 imposto pelo projectista.

    Não representa estabilidade global nem paredes acopladas. M0 deve incluir
    imperfeições. rho >= 0,002; gamma_CE = 1,2.
    """
    vals=(n_kn,m0_knm,h,as_total,axis_cover,fck,fcd,fyd,l0_mm,phi_eff,beta)
    if not all(math.isfinite(v) for v in vals) or h<=0 or as_total<=0 or l0_mm<=0 or phi_eff<0 or beta<=0 or not 0 < axis_cover < h/2 or not 12 <= fck <= 90 or fcd<=0 or fyd<=0:
        raise ValueError('Parâmetros de estabilidade inválidos')
    if n_kn<=0:
        return dict(moment=abs(m0_knm),amplification=1.,slenderness=0.,buckling_load=float('inf'),status='Sem compressão')
    ac=1000*h
    if as_total/ac<.002:
        raise ValueError('Rigidez nominal requer rho >= 0,002')
    slenderness=l0_mm/(h/math.sqrt(12))
    reduced=n_kn*1000/(ac*fcd)
    kc=math.sqrt(fck/20)*min(reduced*slenderness/170,.2)/(1+phi_eff)
    ecd=22000*((fck+8)/10)**.3/1.2
    ei=kc*ecd*1000*h**3/12+200000*as_total*(h/2-axis_cover)**2
    nb=math.pi**2*ei/l0_mm**2/1000
    amplification=1+beta/(nb/n_kn-1) if nb>n_kn else float('inf')
    return dict(moment=abs(m0_knm)*amplification,amplification=amplification,
                slenderness=slenderness,buckling_load=nb,
                status='OK' if nb>n_kn else 'Instável no modelo de faixa')

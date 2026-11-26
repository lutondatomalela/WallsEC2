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
    layers: tuple = ()  # (signed centroid z in mm, area in mm2/m)

    def __post_init__(self):
        for name in ('h','cover_axis','as_plus','as_minus','fck','fcd','fyd','es','eps_ud'):
            if not math.isfinite(getattr(self,name)) or getattr(self,name)<=0:
                raise ValueError(f'Parâmetro de secção inválido: {name}')
        if not 0 < self.cover_axis < self.h/2 or not 12 <= self.fck <= 90:
            raise ValueError('Geometria/classe de betão fora do domínio')
        if self.fibres < 40 or self.eps_ud <= self.fyd/self.es:
            raise ValueError('Discretização ou extensão última do aço inválida')
        if self.layers:
            if any(len(v)!=2 or not all(map(math.isfinite,v)) or not 0<abs(v[0])<self.h/2 or v[1]<=0 for v in self.layers):
                raise ValueError('Famílias de aço fora da secção')
            for sign, area in ((1,self.as_plus),(-1,self.as_minus)):
                if not math.isclose(sum(a for z,a in self.layers if sign*z>0),area,rel_tol=1e-7,abs_tol=1e-6):
                    raise ValueError('Área de aço incompatível com as famílias')

    @property
    def steel_geometry(self):
        return self.layers or ((self.h/2-self.cover_axis,self.as_plus),(-self.h/2+self.cover_axis,self.as_minus))

    @property
    def steel_inertia(self):
        return sum(a*z*z for z,a in self.steel_geometry)

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
        ys,areas=np.array(self.steel_geometry).T
        steel_eps=(top+bottom)/2+(bottom-top)*ys/self.h
        steel_stress=np.clip(self.es*steel_eps,-self.fyd,self.fyd)
        # Área líquida de betão nos níveis de armadura.
        steel_force=(steel_stress-self.concrete_stress(steel_eps))*areas
        return float((force.sum()+steel_force.sum())/1000),float(-(force@y+steel_force@ys)/1e6)

    def strain_profiles(self, points=160):
        """Domain boundary, compression positive, actual extreme steel strain.

        Domain 1/2 rotates around the outermost tensile steel (not the
        fictitious extreme tensile concrete fibre). Domain 3/4 limits the
        compressed concrete face. Domain 5 rotates around point C. Both
        bending orientations are generated separately for asymmetric layers.
        """
        if not isinstance(points,int) or points<20:
            raise ValueError('Discretização dos domínios insuficiente')
        out=[]
        for tensile_face in (1,-1):
            z=max(abs(z) for z,a in self.steel_geometry if tensile_face*z>0)
            d=self.h/2+z
            # Strain at tensile concrete surface from the extreme steel strain.
            def far(ec,es):return ec+(es-ec)*self.h/d
            p=[(a,far(a,-self.eps_ud)) for a in np.linspace(-self.eps_ud,self.eps_cu,points)]
            # Fixed compression limit, from first intersection to zero strain
            # at opposite concrete surface, not at the bar centroid.
            es0=self.eps_cu*(1-d/self.h)
            p.extend((self.eps_cu,far(self.eps_cu,es)) for es in np.linspace(-self.eps_ud,es0,points))
            pivot=1-self.eps_c2/self.eps_cu
            if pivot>1e-10:
                p.extend((a,self.eps_c2-(a-self.eps_c2)*(1-pivot)/pivot)
                         for a in np.linspace(self.eps_cu,self.eps_c2,points))
            else:p.append((self.eps_c2,self.eps_c2))
            out.append(np.asarray(p) if tensile_face==1 else np.asarray(p)[:,::-1])
        return np.concatenate(out,axis=0)

    @lru_cache(maxsize=256)
    def interaction(self, points=160):
        p=self.strain_profiles(points)
        top,bottom=p[:,0,None],p[:,1,None]
        y=(np.arange(self.fibres)+.5)*self.h/self.fibres-self.h/2
        eps=(top+bottom)/2+(bottom-top)*y/self.h
        force=self.concrete_stress(eps)*1000*self.h/self.fibres
        ys,areas=np.array(self.steel_geometry).T
        se=(top+bottom)/2+(bottom-top)*ys/self.h
        sf=(np.clip(self.es*se,-self.fyd,self.fyd)-self.concrete_stress(se))*areas
        return np.column_stack(((force.sum(axis=1)+sf.sum(axis=1))/1000,
                                -((force*y).sum(axis=1)+(sf*ys).sum(axis=1))/1e6))

    @lru_cache(maxsize=32768)
    def moment_bounds(self,n_kn,points=160):
        # Intersecções dos ramos de compatibilidade com NEd constante.
        curve=self.interaction(points)
        values = []
        for branch in np.split(curve, 2):
            n0, m0 = branch[:-1].T
            n1, m1 = branch[1:].T
            hit = (np.minimum(n0,n1)-1e-8 <= n_kn) & (n_kn <= np.maximum(n0,n1)+1e-8)
            flat = hit & (np.abs(n1-n0)<1e-10)
            slope = hit & ~flat
            values.extend(m0[flat])
            values.extend(m1[flat])
            values.extend(m0[slope]+(m1[slope]-m0[slope])*(n_kn-n0[slope])/(n1[slope]-n0[slope]))
        return (min(values),max(values)) if values else None

    def check(self,n_kn,m_knm,points=160):
        bounds=self.moment_bounds(n_kn,points)
        if bounds is None:
            return dict(utilisation=float('inf'),mrd=0.0,status='Não conforme')
        capacity=bounds[1] if m_knm >=0 else -bounds[0]
        utilisation=abs(m_knm)/capacity if capacity>1e-9 else (0.0 if abs(m_knm)<1e-9 else float('inf'))
        in_domain = bounds[0]-1e-6 <= m_knm <= bounds[1]+1e-6
        if not in_domain and utilisation <= 1:
            utilisation = float('inf')
        return dict(utilisation=utilisation,mrd=max(0.0,capacity),status='OK' if in_domain and utilisation<=1+1e-6 else 'Não conforme')

    def service(self,n_kn,m_knm,creep=0.0):
        """Secção elástica fendilhada: betão traccionado desprezado.

        Resolve equilíbrio com conjunto activo de fibras comprimidas. Retorna
        tensões reais no aço; fluência entra por Ec,eff = Ecm/(1+phi).
        """
        if not math.isfinite(creep) or creep<0:
            raise ValueError('Coeficiente de fluência inválido')
        ec=22000*((self.fck+8)/10)**.3/(1+creep)
        y=(np.arange(self.fibres)+.5)*self.h/self.fibres-self.h/2
        ys,areas=np.array(self.steel_geometry).T
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
        return dict(sigma_plus=float(steel[ys>0].min()),sigma_minus=float(steel[ys<0].min()),
                    sigma_layers=tuple(float(v) for v in steel),
                    concrete_max=float(ec*max(0.,eps0-k*self.h/2,eps0+k*self.h/2)),eps0=float(eps0),curvature=float(k),
                    residual_n=float(residual[0]),residual_m=float(residual[1]))

    def cracking(self, n_kn, m_knm, phi_plus, spacing_plus, phi_minus, spacing_minus,
                 creep=0.0, kt=0.4, *, family_details=None):
        """EC2 7.3.4, faixa N-M, varões aderentes, carregamento imposto.

        hc,eff por face, sem sobrepor áreas na tracção integral. A deformação
        imposta/retracção e a membrana NXY não fazem parte desta resolução.
        """
        values=(n_kn,m_knm,phi_plus,spacing_plus,phi_minus,spacing_minus,kt)
        if not all(math.isfinite(v) for v in values) or min(phi_plus,spacing_plus,phi_minus,spacing_minus)<=0 or not 0<kt<=.6:
            raise ValueError('Parâmetros de fendilhação inválidos')
        # Records (diameter, pitch, count), aligned with steel_geometry.
        if family_details is not None:
            if len(family_details)!=len(self.steel_geometry) or any(
                len(v)!=3 or not all(map(math.isfinite,v)) or min(v)<=0
                for v in family_details):
                raise ValueError('Detalhes de famílias inválidos')
        service=self.service(n_kn,m_knm,creep)
        alpha=self.es/(22000*((self.fck+8)/10)**.3)
        fctm=.3*self.fck**(2/3) if self.fck<=50 else 2.12*math.log(1+(self.fck+8)/10)
        ext_plus=-service['eps0']+service['curvature']*self.h/2
        ext_minus=-service['eps0']-service['curvature']*self.h/2
        output={'service':service}
        for name,ext,other,sigma,area,phi,spacing in (
            ('plus',ext_plus,ext_minus,service['sigma_plus'],self.as_plus,phi_plus,spacing_plus),
            ('minus',ext_minus,ext_plus,service['sigma_minus'],self.as_minus,phi_minus,spacing_minus)):
            tension=max(0.,-sigma)
            if ext<=1e-14:
                output[name]=dict(wk=0.,sigma_s=tension,sr_max=0.,hc_eff=0.,rho_eff=0.,k2=0.,eps_difference=0.)
                continue
            if tension<=1e-9:
                output[name]=dict(wk=math.nan,sigma_s=tension,sr_max=math.nan,hc_eff=math.nan,rho_eff=math.nan,k2=math.nan,eps_difference=math.nan)
                continue
            face_sign=1 if name=='plus' else -1
            face_layers=[(i,z,a,s) for i,((z,a),s) in enumerate(zip(self.steel_geometry,service['sigma_layers'])) if face_sign*z>0 and s<0]
            area=sum(a for i,z,a,s in face_layers)
            axis_depth=sum((self.h/2-abs(z))*a for i,z,a,s in face_layers)/area
            full_tension=other>=0
            depth=self.h if full_tension else self.h*ext/(ext-other)
            hc=min(2.5*axis_depth,self.h/2)
            if not full_tension:
                hc=min(hc,depth/3)
            eligible=[(i,z,a,s) for i,z,a,s in face_layers if self.h/2-abs(z)<=hc+1e-9]
            def pending(reason):
                return dict(wk=math.nan,sigma_s=tension,sr_max=math.nan,hc_eff=hc,
                            rho_eff=math.nan,k2=math.nan,eps_difference=math.nan,
                            reason=reason,as_eff=0.)
            if not eligible:
                output[name]=pending('Nenhuma armadura traccionada dentro de Ac,eff')
                continue
            if family_details is None and len(eligible)!=sum(face_sign*z>0 for z,a in self.steel_geometry):
                output[name]=pending('Geometria das famílias eficazes não definida')
                continue
            area=sum(a for i,z,a,s in eligible)
            rho=area/(1000*hc)
            if not 0<rho<1:
                output[name]=pending('Taxa eficaz fora do domínio')
                continue
            e1=max(ext,max(0.,other)); e2=min(ext,max(0.,other))
            k2=(e1+e2)/(2*e1)
            if family_details is not None:
                data=[family_details[i] for i,z,a,s in eligible]
                phi=sum(n*p*p/sp for p,sp,n in data)/sum(n*p/sp for p,sp,n in data)
                # No intercalation credit without verified relative offsets.
                spacing=max(sp for p,sp,n in data)
                cover=max(self.h/2-abs(z)-family_details[i][0]/2 for i,z,a,s in eligible)
            else:
                cover=max(self.h/2-abs(z) for i,z,a,s in eligible)-phi/2
            if cover<0:
                raise ValueError('Diâmetro incompatível com o eixo da camada')
            # Keep largest face steel stress even when one family is excluded.
            sr=3.4*cover+.8*k2*.425*phi/rho
            if spacing>5*(cover+phi/2):
                sr=1.3*depth
            difference=max((tension-kt*fctm/rho*(1+alpha*rho))/self.es,.6*tension/self.es)
            output[name]=dict(wk=sr*difference,sigma_s=tension,sr_max=sr,hc_eff=hc,
                              rho_eff=rho,k2=k2,eps_difference=difference,as_eff=area,
                              phi_eff=phi,spacing_eff=spacing,cover_eff=cover)
        return output


def nominal_stiffness(n_kn,m0_knm,h,as_total,axis_cover,fck,fcd,fyd,l0_mm,phi_eff=0.0,beta=math.pi**2/8,*,steel_inertia=None):
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
    inertia=as_total*(h/2-axis_cover)**2 if steel_inertia is None else steel_inertia
    if not math.isfinite(inertia) or not 0<inertia<as_total*(h/2)**2:
        raise ValueError('Inércia de armadura inválida')
    ei=kc*ecd*1000*h**3/12+200000*inertia
    nb=math.pi**2*ei/l0_mm**2/1000
    amplification=1+beta/(nb/n_kn-1) if nb>n_kn else float('inf')
    return dict(moment=abs(m0_knm)*amplification,amplification=amplification,
                slenderness=slenderness,buckling_load=nb,
                status='OK' if nb>n_kn else 'Instável no modelo de faixa')


def gross_face_principal(h, n, m):
    """Indicative gross concrete stresses, tension positive; M+ tensions face +.

    h in mm; n=(Nxx,Nyy,Nxy) in kN/m; m=(Mxx,Myy,Mxy) in kNm/m.
    Returns maximum/minimum principal stress (MPa) and direction from local X
    (degrees) for each face. This is not a cracked section or a wk check.
    """
    out = []
    for sign in (1, -1):
        x, y, xy = (a/h + sign*6000*b/h**2 for a,b in zip(n,m))
        r = math.hypot((x-y)/2, xy)
        angle = math.degrees(0.5*math.atan2(2*xy, x-y)) if r else float("nan")
        out.append(((x+y)/2+r, (x+y)/2-r, angle))
    return tuple(out)

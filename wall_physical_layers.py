"""Research section models with explicit bar layers, not full EC2 verification.
N (kN/m), M (kNm/m), z (mm), stress (MPa). Positive N = tension.
Concrete bands at their centroids; compression-only strut discretization.
Service: gross concrete + axial steel with no Poisson coupling in the cracked
model; elastic trial uses plane stress and subtracts displaced concrete.
"""
from dataclasses import dataclass
import math
import numpy as np
import pandas as pd
from scipy.optimize import linprog
from wall_shell_service import BarLayer, solve_cracked_shell
from wall_compatible_ultimate import compatible_equilibrium
from wall_resultant_shear import resultant_shear
from wall_coupled_shear import assess as assess_coupled_shear
from wall_concrete_fibres import net_fibre_geometry, net_slices
from wall_lp_certificate import certify
from shell_crack_detail import projected_tension_band, crack_spacing_orthogonal, relative_mean_strain, principal_relative_strain

LABELS=('X+','X-','Y+','Y-')

@dataclass(frozen=True)
class Family:
    label: str
    phi: float
    spacing: float
    count: int
    cover: float
    bar: BarLayer


def layout(h, cover, families, outer_axis=1):
    """Aligned outer surfaces within a direction, intercalated families.
    Crossing directions touch; no additional gap. Explicit trial assumption.
    No claim that the in-plane anchorage or intercalation fits.
    """
    if len(families)!=4 or outer_axis not in (0,1) or not 0<cover<h/2:
        raise ValueError('Geometria de camadas inválida')
    out=[]
    for j,items in enumerate(families):
        if not items or any(n<1 or not np.isfinite([p,s]).all() or p<=0 or s<=0 for n,p,s in items):
            raise ValueError('Família de varões inválida')
    for j,items in enumerate(families):
        axis=j//2; face=1 if j%2==0 else -1
        c=cover if axis==outer_axis else cover+max(p for n,p,s in families[2*outer_axis+j%2])
        for count,phi,spacing in items:
            if c+phi>=h/2: raise ValueError('Camadas não cabem na meia espessura')
            out.append(Family(LABELS[j],phi,spacing,count,c,BarLayer(axis,face*(h/2-c-phi/2),count*1000*math.pi*phi**2/(4*spacing))))
    return tuple(out)


def load(n,m,h):
    # N and M normalized to force units (kN/m) for conditioning.
    return np.concatenate((np.asarray(n,float),np.asarray(m,float)*2000/h),axis=-1)


def elastic_trial(h,n,m,families,ec,es=200000.,nu=.2):
    """Linear transformed section, plane stress, constant concrete E.
    The displaced concrete is deducted at each bar centroid (small local
    second moment of individual bars neglected); steel acts axially.
    Generalized strain uses engineering shear gamma_xy.
    Concrete/steel stress outputs are trials only if cracking/history unknown.
    """
    if not 0<=nu<.5 or not 0<ec<es or not h>0: raise ValueError('Materiais elásticos inválidos')
    D=ec/(1-nu**2)*np.array([[1,nu,0],[nu,1,0],[0,0,(1-nu)/2]])
    K=np.zeros((6,6));K[:3,:3]=D*h; K[3:,3:]=D*h/3
    for f in families:
        b=f.bar; B=np.column_stack((np.eye(3),np.eye(3)*2*b.z_mm/h)); v=B[b.axis]
        K+=b.area_mm2_m/1000*(es*np.outer(v,v)-B.T@D@B)
    q=np.linalg.solve(K,load(n,m,h).T).T
    face=np.stack(((q[...,:3]+q[...,3:])@D.T,(q[...,:3]-q[...,3:])@D.T),axis=-2)
    princ=np.stack(((face[...,0]+face[...,1])/2-np.hypot((face[...,0]-face[...,1])/2,face[...,2]),(face[...,0]+face[...,1])/2+np.hypot((face[...,0]-face[...,1])/2,face[...,2])),axis=-1)
    steel=np.stack([es*(q[...,f.bar.axis]+2*f.bar.z_mm/h*q[...,f.bar.axis+3]) for f in families],axis=-1)
    return q,princ,steel


class PhysicalCapacity:
    """LP static equilibrium with distinct steel axes and concrete bands.
    Finite strut directions (inner approximation of PSD cone). For a fixed
    layout, solve maximum proportional load factor in one LP. Neither
    compatibility, transverse shear nor 2nd order is included.
    """
    def __init__(self,h,families,fyd,fc,band_fraction=.35,directions=16,subdivisions=1,net_area=False,*,band_fractions=None):
        # Fractions ordered by physical face (+z, -z). Distinct bands are
        # disjoint and leave a strictly positive core. Symmetric by default.
        fractions=tuple(band_fractions) if band_fractions is not None else (band_fraction,band_fraction)
        if (len(fractions)!=2 or not np.isfinite([h,fyd,fc,*fractions]).all()
                or min(h,fyd,fc,*fractions)<=0 or sum(fractions)>=1
                or max(fractions)>=1 or directions<4 or not isinstance(subdivisions,int) or subdivisions<1):raise ValueError('Parâmetros inválidos')
        if band_fractions is None and not 0<band_fraction<.5:raise ValueError('Parâmetros inválidos')
        self.h=h; self.families=families; self.fyd=fyd; self.directions=directions; self.band=h*fractions[0]; self.z=h/2-self.band/2
        self.band_fractions=fractions
        self.core_mm=h*(1-sum(fractions)); self.core_z_mm=h*(fractions[1]-fractions[0])/2
        angle=np.arange(directions)*math.pi/directions
        stress=np.stack((-np.cos(angle)**2,-np.sin(angle)**2,-np.cos(angle)*np.sin(angle)),axis=0)
        # Keep the core reserved, but allow compression resultants to move
        # within each exterior band. Each strip has its own stress budget.
        widths=np.repeat(np.asarray(fractions)*h/subdivisions,subdivisions)
        centers=[sign*(h/2-(j+.5)*h*frac/subdivisions) for sign,frac in zip((1,-1),fractions) for j in range(subdivisions)]
        self.geometric_centers=tuple(centers)
        self.widths=tuple(widths); self.subdivisions=subdivisions
        if net_area:
            net,centers=net_slices(h,families,centers,widths)
        else:
            occupied=np.zeros(len(centers))
            for f in families:
                j=int(np.argmin(np.abs(np.array(centers)-f.bar.z_mm)))
                occupied[j]+=f.bar.area_mm2_m/1000
            net=widths-occupied
        self.centers=tuple(centers)
        self.nc=len(centers)*directions
        blocks=[np.vstack((stress,stress*2*z/h)) for z in centers]
        steel=[]
        for f in families:
            v=np.zeros(6);v[f.bar.axis]=1;v[f.bar.axis+3]=2*f.bar.z_mm/h;steel.append(v)
        self.matrix=np.column_stack((np.hstack(blocks),np.array(steel).T))
        self.Aub=np.zeros((len(centers),self.matrix.shape[1]+1))
        for j in range(len(centers)):self.Aub[j,j*directions:(j+1)*directions]=1
        self.cap=fc*net
        if min(self.cap)<=0:raise ValueError('Subcamada de betão sem área disponível')
        self.bounds=[(0,None)]*self.nc+[(0,f.bar.area_mm2_m*fyd/1000) for f in families]+[(0,1024)]
        self.obj=np.r_[np.zeros(self.matrix.shape[1]),-1.]
    def check(self,n,m):
        q=load(n,m,self.h)
        if not np.isfinite(q).all():raise ValueError('Esforços inválidos')
        if not np.any(q):return 0.,0.,'Equilíbrio nulo'
        a=np.column_stack((self.matrix,-q))
        r=linprog(self.obj,A_ub=self.Aub,b_ub=self.cap,A_eq=a,b_eq=np.zeros(6),bounds=self.bounds,method='highs')
        if not r.success:return np.nan,np.nan,'Solver: '+str(r.status)
        certificate=certify(r.x,a,np.zeros(6),self.Aub,self.cap,self.bounds)
        residual=certificate.equality_error
        if not certificate.valid:return np.nan,residual,'Ponto primal inválido; equilíbrio não demonstrado'
        factor=r.x[-1]
        if factor<=1e-10:return np.inf,residual,'Sem capacidade proporcional positiva'
        return 1/factor,residual,'Equilíbrio no modelo' if factor>=1-1e-7 else 'Capacidade insuficiente no modelo'


    def required_areas(self,n,m):
        """Minimum added tension capacity at the existing axes; no change of
        concrete bands during this LP. The discrete bar selection must be
        rechecked, since changed diameters change centres and band capacity.
        Returns None if no equilibrium even with unlimited tension steel.
        """
        q=load(n,m,self.h)
        if not np.isfinite(q).all():raise ValueError('Esforços inválidos')
        nb=len(self.families); nc=self.nc; nv=nc+nb; ns=len(self.cap)
        eq=np.column_stack((self.matrix,np.zeros((6,nb))))
        aub=np.zeros((ns+nb,nv+nb));aub[:ns,:nv]=self.Aub[:,:-1]
        aub[ns:,nc:nv]=np.eye(nb);aub[ns:,nv:]=-np.eye(nb)
        caps=np.array([f.bar.area_mm2_m*self.fyd/1000 for f in self.families])
        r=linprog(np.r_[np.zeros(nv),np.ones(nb)],A_ub=aub,b_ub=np.r_[self.cap,caps],A_eq=eq,b_eq=q,bounds=(0,None),method='highs')
        if not r.success or not certify(r.x,eq,q,aub,np.r_[self.cap,caps],[(0,None)]*(nv+nb)).valid:return None
        return np.array([sum((caps[i]+max(0.,r.x[nv+i]))*1000/self.fyd for i,f in enumerate(self.families) if f.label==k) for k in LABELS])


def refine_mesh(designer,provisional,adopted,max_iterations=3):
    """Experimental monotonic refinement by panel on original signed ELU tensors.
    No reduction. Exclusions/failures leave a diagnostic for the final LP.
    """
    if not designer.shell_qp_diagnostic or designer.axial_convention not in ('Tracção positiva','Compressão positiva'):return
    sign=1 if designer.axial_convention=='Tracção positiva' else -1
    for panel,g in provisional[provisional.tensor_ok].groupby('Panel'):
        mesh=adopted[str(panel)]
        n=sign*g[['NXX','NYY','NXY']].to_numpy(); m=g[['MXX','MYY','MXY']].to_numpy()
        for _ in range(max_iterations):
            try:
                fam=layout(designer.t,designer.cover,[designer._parse_rebar_text(v.text) for v in mesh],outer_axis=1 if designer.local_y_is_vertical else 0)
                model=PhysicalCapacity(designer.t,fam,designer.fyd,.6*(1-designer.fck/250)*designer.cp['fcd'],subdivisions=3,net_area=True)
            except ValueError:break
            initial=np.array([v.as_prov for v in mesh]);target=initial.copy()
            for ni,mi in zip(n,m):
                req=model.required_areas(ni,mi)
                if req is not None:target=np.maximum(target,req)
            modified=False
            for i,k in enumerate(LABELS):
                if target[i]<=initial[i]+1e-5:continue
                vertical=(i//2==1)==designer.local_y_is_vertical
                try:
                    candidate=designer.optimize_rebar_solution(target[i]+1e-5,designer.max_spacing_for_direction(vertical),vertical,k)
                except ValueError:continue
                if candidate.as_prov>mesh[i].as_prov+1e-5:
                    candidate.optimization_note += '; reforço por equilíbrio de camadas físicas (experimental)'
                    mesh[i]=candidate;modified=True
            if not modified:break

def crack_candidate(h,families,n,m,ec,fctm,es=200000.,solution=None,fyk=None,ec_reference=None):
    """Experimental use of directional EC2 components with actual bar geometry.
    The normal to principal strain is only a crack-normal candidate. 7.9
    is applied to directional steel tensions in the candidate bands; the
    projection is a hypothesis, not a validated shell mean relative strain.
    """
    if solution is None:
        weights,positions=net_fibre_geometry(h,families)
        r=solve_cracked_shell(h,n,m,[f.bar for f in families],ec,es,concrete_weights=weights,concrete_positions=positions)
    else:
        r=solution
    if r is None:return dict(PhysQP_status='Sem convergência')
    out={'PhysQP_status':'Equilíbrio experimental; wk pendente','PhysQP_sigma_s_max_MPa':float(np.max(np.abs(r.steel_stress_mpa))), 'PhysQP_residual_MPa':r.residual_mpa}
    if fyk is not None and out['PhysQP_sigma_s_max_MPa']>=fyk:
        out['PhysQP_status']='Aço fora do domínio elástico; wk pendente'
        return out
    indicators=[]
    for sign,side in ((1,'plus'),(-1,'minus')):
        xx,yy,xy=r.mid_strain+sign*h/2*r.curvature_per_mm
        theta=.5*math.atan2(2*xy,xx-yy)
        angle=math.atan2(abs(math.sin(theta)),abs(math.cos(theta)))
        sr=[]; eps=[]; reason='Indicador experimental'; val=np.nan; tan_val=np.nan
        if (xx+yy)/2+math.hypot((xx-yy)/2,xy)<=0:
            reason='Sem extensão de tracção no modelo; história desconhecida'; val=0.0
        else:
            axes=(0,) if angle<=math.pi/12 else ((1,) if angle>=5*math.pi/12 else (0,1))
            for axis in axes:
                data=[(f,s) for f,s in zip(families,r.steel_stress_mpa) if f.bar.axis==axis and f.bar.z_mm*sign>0]
                depth=max(h/2-abs(f.bar.z_mm) for f,s in data)
                band=projected_tension_band(h,r.mid_strain,r.curvature_per_mm,sign,theta,depth)
                eligible=[(f,s) for f,s in data if h/2-abs(f.bar.z_mm)<=band.candidate_depth_mm+1e-9 and s>0]
                if not eligible or band.candidate_depth_mm<=0:
                    reason='Banda candidata sem armadura traccionada eficaz';break
                area=sum(f.bar.area_mm2_m for f,s in eligible);rho=area/(1000*band.candidate_depth_mm)
                if not 0<rho<1:reason='Taxa eficaz inválida';break
                phi=sum(f.count*f.phi**2/f.spacing for f,s in eligible)/sum(f.count*f.phi/f.spacing for f,s in eligible)
                cover=max(f.cover for f,s in eligible); spacing=max(f.spacing for f,s in eligible) # no credit for unconfirmed intercalation
                sig=max(s for f,s in eligible)
                # k2=1 for candidate membrane/flexure combination; not a validated multiaxial law.
                sr.append(3.4*cover+.8*.425*phi/rho if spacing<=5*(cover+phi/2) else 1.3*band.tension_depth_mm)
                eps.append(relative_mean_strain(sig,es,ec if ec_reference is None else ec_reference,rho,fctm))
            if len(sr)==len(axes):
                if len(axes)==1: val=sr[0]*eps[0]
                else:
                    spacing_n=crack_spacing_orthogonal(*sr,angle)
                    val=spacing_n*(eps[0]*math.cos(theta)**2+eps[1]*math.sin(theta)**2)
                    # Sensitivity only: Eq.31 combines relative normal strains
                    # and total engineering shear. Here these come from two
                    # candidate bands and the tensionless shell surface, not
                    # the MCMM; do not substitute for a normative width.
                    tan_val=spacing_n*principal_relative_strain(eps[0],eps[1],2*xy)
        out['PhysQP_Tan31_candidate_'+side+'_mm']=tan_val
        out['PhysQP_surface_tensile_strain_'+side]=max(0.,(xx+yy)/2+math.hypot((xx-yy)/2,xy));out['PhysQP_candidate_'+side+'_mm']=val;out['PhysQP_reason_'+side]=reason;out['PhysQP_theta_'+side+'_deg']=math.degrees(theta);indicators.append(val)
    out['PhysQP_candidate_max_mm']=max((x for x in indicators if np.isfinite(x)),default=np.nan)
    out['PhysQP_faces_finite']=sum(np.isfinite(x) for x in indicators)
    out['PhysQP_complete_candidate']=all(np.isfinite(x) for x in indicators)
    if not out['PhysQP_complete_candidate']:out['PhysQP_status']='Equilíbrio experimental; cobertura parcial; wk pendente'
    return out


class _ColumnAccess:
    """Explicit two-axis assignment into an independently allocated Series."""
    def __init__(self, owner, scalar):
        self.owner=owner; self.scalar=scalar

    def __getitem__(self, key):
        index, name=key
        col=self.owner.columns.get(name)
        if col is None: col=self.owner.frame[name]
        return (col.at if self.scalar else col.loc)[index]

    def __setitem__(self, key, value):
        index, name=key
        if name not in self.owner.columns:
            if name in self.owner.frame:
                col=self.owner.frame[name].copy()
            else:
                # Preserve missing numeric values and distinguish strings/bools.
                kind=np.asarray(value).dtype.kind
                col=pd.Series(index=self.owner.frame.index, dtype=float if kind in 'iuf' else object)
            self.owner.columns[name]=col
        col=self.owner.columns[name]
        (col.at if self.scalar else col.loc)[index]=value


class _DiagnosticColumns:
    """Batch diagnostic columns, avoiding repeated DataFrame insertions.

    The original data and index remain unchanged. Missing diagnostic entries
    remain missing; neither sparse records nor string/boolean fields are filled
    with zero. Existing columns retain their positions in the exported table.
    """
    def __init__(self, frame):
        self.frame=frame; self.columns={}
        self.loc=_ColumnAccess(self,False); self.at=_ColumnAccess(self,True)

    def finish(self):
        if not self.columns: return self.frame
        names=list(self.frame.columns)+[k for k in self.columns if k not in self.frame]
        unchanged=self.frame.drop(columns=[k for k in self.columns if k in self.frame])
        return pd.concat([unchanged,pd.DataFrame(self.columns,index=self.frame.index)],axis=1).loc[:,names]


def attach(r,designer):
    r=r.copy();r['PhysELU_status']='Não avaliado';r['PhysELS_status']='Não avaliado';r['PhysQP_status']='Não avaliado'
    if not designer.shell_qp_diagnostic or designer.axial_convention not in ('Tracção positiva','Compressão positiva'):return r
    columns=_DiagnosticColumns(r)
    sign=1 if designer.axial_convention=='Tracção positiva' else -1
    for panel,g in r.groupby('Panel',sort=False):
        try:
            row=g.iloc[0]; fs=[designer._parse_rebar_text(row[k+'_rebar']) for k in LABELS]
            fam=layout(designer.t,designer.cover,fs,outer_axis=1 if designer.local_y_is_vertical else 0)
            for j,k in enumerate(LABELS):
                expected=row['As'+k.lower()+'_prov_mm2_m']; actual=sum(f.bar.area_mm2_m for f in fam if f.label==k)
                if not np.isclose(expected,actual,rtol=1e-6):raise ValueError('Áreas de aço incompatíveis com descrição')
        except (ValueError,KeyError) as exc:
            for col in ('PhysELU_status','PhysELS_status','PhysQP_status'):columns.loc[g.index,col]='Geometria indisponível: '+str(exc)
            continue
        # A failed fixed-band capacity model must not prevent a service solve
        # or the independent alternative core trial. Preserve missing status.
        try:
            model=PhysicalCapacity(designer.t,fam,designer.fyd,.6*(1-designer.fck/250)*designer.cp['fcd'],subdivisions=3,net_area=True)
        except ValueError as exc:
            class UnavailableCapacity:
                def __init__(self,reason):self.reason=reason
                def check(self,n,m):return np.nan,np.nan,'Modelo de bandas indisponível: '+self.reason
            model=UnavailableCapacity(str(exc))
        columns.loc[g.index,'Phys_layout']=('Y exterior' if designer.local_y_is_vertical else 'X exterior')+'; famílias alinhadas; sem folga no cruzamento (hipótese)'
        for k in LABELS:
            columns.loc[g.index,'Phys_z_'+k+'_mm']=sum(f.bar.z_mm*f.bar.area_mm2_m for f in fam if f.label==k)/sum(f.bar.area_mm2_m for f in fam if f.label==k)
        eligible=g[g.Tensor_complete.eq(True)]
        for role in ('ELU','ELS-CAR','ELS-FREQ','ELS-QP'):
            sub=eligible[eligible.Combo_type.eq(role)]
            if sub.empty:continue
            n=sign*sub[['NXX_kN_m','NYY_kN_m','NXY_kN_m']].to_numpy();m=sub[['MXX_kNm_m','MYY_kNm_m','MXY_kNm_m']].to_numpy()
            if role=='ELU':
                q=sub[['QXX_kN_m','QYY_kN_m']].to_numpy(float)
                for key,values in resultant_shear(designer.t,fam,n,q,designer.fck,designer.cp['fcd'],designer.gamma_c).items():
                    columns.loc[sub.index,key]=values
                for key,values in assess_coupled_shear(designer.t,fam,n,m,q,designer.fck,designer.cp['fcd'],designer.gamma_c,designer.fyk,designer.fyd,model).items():
                    columns.loc[sub.index,key]=values
                vals=[model.check(ni,mi) for ni,mi in zip(n,m)]
                columns.loc[sub.index,'PhysELU_util']=[a for a,b,c in vals];columns.loc[sub.index,'PhysELU_residual_kN_m']=[b for a,b,c in vals];columns.loc[sub.index,'PhysELU_status']=[c for a,b,c in vals]
                modal=sub.Case.astype(str).str.contains('CQC|SRSS',case=False,regex=True)
                columns.loc[sub.index[modal],'PhysLL_status']='Modal; sinais por confirmar; '+columns.loc[sub.index[modal],'PhysLL_status']
                columns.loc[sub.index[modal],'PhysELU_status']='Modal; sinais por confirmar; '+columns.loc[sub.index[modal],'PhysELU_status']
                # Audit each insufficient/missing LP row and the governing row
                # of this panel. Keep the original LP result and do not turn
                # the compatible full-depth experiment into a design verdict.
                u=np.array([a for a,b,c in vals]); critical=~np.isfinite(u)|(u>1+1e-7)
                if np.isfinite(u).any():critical[np.nanargmax(np.where(np.isfinite(u),u,np.nan))]=True
                from wall_core_equilibrium import CoreEquilibrium, flatten
                cap=columns.loc[sub.index,'PhysLL_VRdc_kN_m'].to_numpy(float)
                core_critical=critical | (columns.loc[sub.index,'PhysLL_util'].to_numpy(float)>1+1e-7) | ~np.isfinite(cap)
                if core_critical.any():
                    try:
                        core_model=CoreEquilibrium(designer.t,fam,designer.fck,designer.cp['fcd'],designer.fyk,designer.fyd)
                        asym_model=None
                        shared_models=None
                        for j in np.flatnonzero(core_critical):
                            idx=sub.index[j]
                            trial=core_model.assess(n[j],m[j],q[j],cap[j])
                            for k,v in flatten(trial).items():columns.at[idx,k]=v
                            if modal.iloc[j]:columns.at[idx,'Core_status']='Modal; sinais por confirmar; '+columns.at[idx,'Core_status']
                            # One shared concrete stress budget for N, M, Q and
                            # Nzz=0. Links remain conditional proposals. Keep all
                            # earlier checks, and never promote a panel status.
                            try:
                                from wall_shared_core import assess_layouts
                                from wall_asymmetric_core import AsymmetricCore
                                if shared_models is None:
                                    shared_models=[v for _,v in core_model.models]
                                    shared_models+=AsymmetricCore(designer.t,fam,designer.fck,designer.cp['fcd'],designer.fyk,designer.fyd).models
                                shared=assess_layouts(shared_models,n[j],m[j],q[j],designer.fck,designer.fyk,core_model.fc)
                                for k,v in vars(shared).items():columns.at[idx,'PhysShared_'+k]=v
                                if modal.iloc[j]:columns.at[idx,'PhysShared_status']='Modal; sinais por confirmar; '+columns.at[idx,'PhysShared_status']
                            except (ValueError,np.linalg.LinAlgError) as exc:
                                columns.at[idx,'PhysShared_status']='Modelo indisponível: '+str(exc)
                            # Independent sensitivity trial: do not overwrite
                            # the original core result or panel verdict.
                            if trial.status.startswith('Sem solução'):
                                try:
                                    from wall_asymmetric_core import AsymmetricCore
                                    if asym_model is None:
                                        asym_model=AsymmetricCore(designer.t,fam,designer.fck,designer.cp['fcd'],designer.fyk,designer.fyd)
                                    alternative=asym_model.assess(n[j],m[j],q[j],cap[j])
                                    for k,v in vars(alternative).items():columns.at[idx,'Asym_'+k]=v
                                    if modal.iloc[j]:columns.at[idx,'Asym_status']='Modal; sinais por confirmar; '+columns.at[idx,'Asym_status']
                                    # For a residual N-M-only solution, test a
                                    # separate complete smeared core truss even
                                    # below VRdc. Never adopt the links implicitly.
                                    if alternative.asw_proposed==0 and np.linalg.norm(q[j])>0:
                                        combined=asym_model.assess(n[j],m[j],q[j],cap[j],force_links=True)
                                        for k,v in vars(combined).items():columns.at[idx,'AsymTruss_'+k]=v
                                        if modal.iloc[j]:columns.at[idx,'AsymTruss_status']='Modal; sinais por confirmar; '+columns.at[idx,'AsymTruss_status']
                                except (ValueError,np.linalg.LinAlgError) as exc:columns.at[idx,'Asym_status']='Modelo indisponível: '+str(exc)
                    except ValueError as exc:columns.loc[sub.index[core_critical],'Core_status']='Modelo indisponível: '+str(exc)
                if designer.fck<=50:
                    for j in np.flatnonzero(critical):
                        idx=sub.index[j]
                        try:
                            sol=compatible_equilibrium(designer.t,n[j],m[j],[f.bar for f in fam],.6*(1-designer.fck/250)*designer.cp['fcd'],designer.fyd,designer.steel_ultimate_strain)
                            for k,v in vars(sol).items():columns.at[idx,'PhysCompat_'+k]=v
                            if modal.iloc[j]:columns.at[idx,'PhysCompat_status']='Modal; sinais por confirmar; '+sol.status
                        except (ValueError,np.linalg.LinAlgError) as exc:columns.at[idx,'PhysCompat_status']='Modelo indisponível: '+str(exc)
                else:columns.loc[sub.index[critical],'PhysCompat_status']='Fck > 50 MPa: fora do domínio do ensaio'
            else:
                ecm=22000*((designer.fck+8)/10)**.3
                ec=ecm/(1+designer.creep_effective) if role=='ELS-QP' else ecm
                columns.loc[sub.index,'PhysELS_Ec_MPa']=ec
                columns.loc[sub.index,'PhysELS_creep_source']=('Coeficiente final por painel' if designer.stability_params is not None else 'Hipótese de serviço: fluência efectiva de entrada; coeficiente final não confirmado') if role=='ELS-QP' else 'Instantâneo'
                strain,p,s=elastic_trial(designer.t,n,m,fam,ec)
                columns.loc[sub.index,'PhysELS_sigma_c_MPa']=np.maximum(0,-p.min(axis=(1,2)))
                columns.loc[sub.index,'PhysELS_sigma_t_MPa']=np.maximum(0,p.max(axis=(1,2)))
                columns.loc[sub.index,'PhysELS_sigma_t_plus_MPa']=np.maximum(0,p[:,0,1])
                columns.loc[sub.index,'PhysELS_sigma_t_minus_MPa']=np.maximum(0,p[:,1,1])
                # Preserve the plane-stress surface result, but screen history
                # against the full elastic trial including transverse shear.
                from wall_elastic_shear_history import screen
                shear_trial=screen(designer.t,strain,sub[['QXX_kN_m','QYY_kN_m']].to_numpy(float),ec)
                for j,side in enumerate(('plus','minus')):
                    columns.loc[sub.index,'PhysELS_3D_sigma_t_'+side+'_MPa']=shear_trial.tensile_upper_mpa[:,j]
                columns.loc[sub.index,'PhysELS_3D_sigma_t_MPa']=shear_trial.tensile_upper_mpa.max(axis=1)
                columns.loc[sub.index,'PhysELS_3D_grid_bound_MPa']=shear_trial.interpolation_bound_mpa
                columns.loc[sub.index,'PhysELS_sigma_s_MPa']=np.max(np.abs(s),axis=1)
                columns.loc[sub.index,'PhysELS_status']=np.where(p.max(axis=(1,2))>designer.cp['fctm'],'Tracção > fctm; modelo elástico insuficiente','Ensaio elástico; história de fendas por confirmar')
                if role=='ELS-CAR':
                    columns.loc[sub.index,'PhysELS_ratio_c_06fck']=np.maximum(0,-p.min(axis=(1,2)))/(.6*designer.fck)
                    columns.loc[sub.index,'PhysELS_ratio_s_08fyk']=np.maximum(0,np.max(s,axis=1))/(.8*designer.fyk)
                elif role=='ELS-QP':
                    columns.loc[sub.index,'PhysELS_ratio_c_045fck']=np.maximum(0,-p.min(axis=(1,2)))/(.45*designer.fck)
                    # Cracked response for all service combinations with signed original tensors.
                # It remains a research model, including where elastic trial is below fctm.
                try:weights,positions=net_fibre_geometry(designer.t,fam)
                except ValueError as exc:
                    columns.loc[sub.index,'PhysCracked_status']='Área líquida indisponível: '+str(exc)
                    if role=='ELS-QP':columns.loc[sub.index,'PhysQP_status']='Área líquida indisponível: '+str(exc)
                    continue
                for idx,ni,mi in zip(sub.index,n,m):
                    sol=solve_cracked_shell(designer.t,ni,mi,[f.bar for f in fam],ec,concrete_weights=weights,concrete_positions=positions)
                    if sol is None:
                        columns.at[idx,'PhysCracked_status']='Sem convergência'
                        if role=='ELS-QP':columns.at[idx,'PhysQP_status']='Sem convergência'
                        continue
                    steel=float(np.max(np.abs(sol.steel_stress_mpa)))
                    c=max(0.,-float(sol.face_principal_strain.min())*ec)
                    columns.at[idx,'PhysCracked_sigma_c_MPa']=c
                    columns.at[idx,'PhysCracked_sigma_s_MPa']=steel
                    columns.at[idx,'PhysCracked_status']='Aço fora do domínio elástico' if steel>=designer.fyk else 'Equilíbrio experimental (sem tracção do betão)'
                    if role=='ELS-CAR':
                        columns.at[idx,'PhysCracked_ratio_c_06fck']=c/(.6*designer.fck)
                        columns.at[idx,'PhysCracked_ratio_s_08fyk']=max(0.,float(np.max(sol.steel_stress_mpa)))/(.8*designer.fyk)
                    elif role=='ELS-QP':
                        columns.at[idx,'PhysCracked_ratio_c_045fck']=c/(.45*designer.fck)
                        for k,v in crack_candidate(designer.t,fam,ni,mi,ec,designer.cp['fctm'],solution=sol,fyk=designer.fyk,ec_reference=ecm).items():columns.at[idx,k]=v
    # Elastic trial history screen across the imported service combinations,
    # not evidence of an initially uncracked wall or of restraint effects.
    r=columns.finish()
    columns=_DiagnosticColumns(r)
    if 'PhysELS_3D_sigma_t_MPa' in r:
        for _,g in r[r.Combo_type.isin(['ELS-CAR','ELS-FREQ','ELS-QP'])].groupby(['Panel','Node'],dropna=False):
            qp=g[g.Combo_type.eq('ELS-QP')]
            if qp.empty:continue
            vals=g.PhysELS_3D_sigma_t_MPa
            peak=vals.max()
            complete=(np.isfinite(vals.to_numpy(float)).all() and set(g.Combo_type)=={'ELS-CAR','ELS-FREQ','ELS-QP'} and g.Case_coverage.eq('Completo').all() and not g.Case.astype(str).str.contains('CQC|SRSS',case=False,regex=True).any())
            columns.loc[qp.index,'PhysHistory_sigma_t_max_MPa']=peak
            for side in ('plus','minus'):
                side_peak=g['PhysELS_3D_sigma_t_'+side+'_MPa'].max()
                columns.loc[qp.index,'PhysHistory_sigma_t_'+side+'_MPa']=side_peak
                columns.loc[qp.index,'PhysHistory_mechanical_'+side]=('Cobertura insuficiente' if not complete else ('Excede fctm; avaliar fenda' if side_peak>designer.cp['fctm'] else 'Sem excedência nos ELS importados; não é wk'))
            columns.loc[qp.index,'PhysHistory_status']=('Cobertura insuficiente' if not complete else ('Tracção elástica excede fctm em ELS importado' if peak>designer.cp['fctm'] else 'Sem excedência elástica nos ELS importados; história/coacção por confirmar'))
            from wall_service_history import classify_history
            for side in ('plus','minus'):
                outcome=classify_history(g['PhysELS_3D_sigma_t_'+side+'_MPa'].to_numpy(float),designer.cp['fctm'],complete=complete)
                columns.loc[qp.index,'History_'+side+'_status']=outcome.status
                columns.loc[qp.index,'History_'+side+'_ratio_fctk005']=outcome.ratio
                columns.loc[qp.index,'History_'+side+'_wk_conditional_mm']=outcome.wk_conditional_mm

    return columns.finish()


def summary(r):
    out=[]
    for p,g in r.groupby('Panel'):
        for role in ('ELU','ELS-CAR','ELS-FREQ','ELS-QP'):
            s=g[g.Combo_type.eq(role)]
            if s.empty:continue
            row={'Panel':p,'Combinação':role,'Linhas':len(s)}
            if role=='ELU' and 'PhysELU_util' in s:
                v=pd.to_numeric(s.PhysELU_util,errors='coerce')
                row['PhysCompat_linhas']=int(s.get('PhysCompat_status',pd.Series(index=s.index,dtype=object)).notna().sum())
                row.update(PhysELU_avaliadas=int(v.notna().sum()),PhysELU_insuficientes=int(v.gt(1+1e-7).sum()),PhysELU_sem_resultado=int(v.isna().sum()))
            if role=='ELS-QP':
                complete=s.get('PhysQP_complete_candidate',pd.Series(False,index=s.index)).eq(True)
                row['PhysQP_completas']=int(complete.sum());row['PhysQP_parciais']=int((~complete).sum())
            for col in ('PhysELU_util','PhysShear_util','PhysLL_util','PhysLL_Asw_req_mm2_m2','PhysLL_Face_util_com_trelica','PhysELS_ratio_c_06fck','PhysELS_ratio_s_08fyk','PhysELS_ratio_c_045fck','PhysQP_candidate_max_mm','PhysQP_sigma_s_max_MPa','PhysCracked_ratio_c_06fck','PhysCracked_ratio_s_08fyk','PhysCracked_ratio_c_045fck','PhysCompat_strain_ratio','PhysCompat_compression_ratio','PhysCompat_residual_mpa','PhysHistory_sigma_t_max_MPa','PhysELS_3D_sigma_t_MPa','PhysELS_3D_grid_bound_MPa','Core_face_util','Core_core_util','Core_asw_required','Core_asw_proposed','Asym_face_util','Asym_core_util','Asym_asw_required','AsymTruss_face_util','AsymTruss_core_util','AsymTruss_link_util','AsymTruss_tensor_residual','History_plus_ratio_fctk005','History_minus_ratio_fctk005','PhysShared_util','PhysShared_core_util','PhysShared_outer_util','PhysShared_asw_proposed','PhysShared_residual','PhysQP_Tan31_candidate_plus_mm','PhysQP_Tan31_candidate_minus_mm'):
                if col in s and s[col].notna().any():
                    peak=s[col].idxmax();row[col]=s.at[peak,col];row[col+'_n']=int(s[col].notna().sum());row[col+'_Node']=s.at[peak,'Node'];row[col+'_Case']=s.at[peak,'Case']
            out.append(row)
    return pd.DataFrame(out)

"""Conditional Annex LL shear/face-force trial. NP EN 1992-2 LL.109–115.
Uses signed concomitant N,M,Q, actual bar centroids, EC2 6.2.2/6.2.3.
Links are proposals, never installed by the calculation. No global verdict.
"""
import math
import numpy as np
from wall_resultant_shear import resultant_shear
from wall_shear_design import shear_reinforcement_trial


def truss_increment(q, cot_theta=1.):
    """LL.124–127: total longitudinal tensile tensor; each face receives half.
    N in kN/m, q in kN/m; tension positive. No resultant for zero shear.
    """
    q=np.asarray(q,float)
    if q.shape[-1:]!=(2,) or not np.isfinite(q).all() or not 1<=cot_theta<=2.5:
        raise ValueError('Corte ou inclinação inválidos')
    v=np.linalg.norm(q,axis=-1)
    a=np.stack((q[...,0]**2,q[...,1]**2,q[...,0]*q[...,1]),axis=-1)
    return np.divide(cot_theta*a,v[...,None],out=np.zeros_like(a),where=v[...,None]>0)


def assess(h,families,n,m,q,fck,fcd,gamma_c,fyk,fyd,model):
    """Conditional design of perpendicular links for the resultant.
    Uses smaller depth on both faces for proposals, no credit for installed links.
    If links are needed, recheck the physical face equilibrium with LL increment.
    The core/outer-band model and anchorage must be independently validated.
    """
    n,m,q=map(lambda x:np.asarray(x,float),(n,m,q))
    r=resultant_shear(h,families,n,q,fck,fcd,gamma_c,compression_credit=True)
    raw=resultant_shear(h,families,n,q,fck,fcd,gamma_c)
    out={k.replace('PhysShear_','PhysLL_'):v for k,v in r.items()}
    out['PhysLL_util_sem_credito']=raw['PhysShear_util']
    keys=['Asw_req_mm2_m2','VRdmax_kN_m','DeltaNxx_kN_m','DeltaNyy_kN_m','DeltaNxy_kN_m','Face_util_com_trelica']
    for k in keys:out['PhysLL_'+k]=np.full(len(n),np.nan)
    out['PhysLL_status']=np.full(len(n),'Dados insuficientes',object)
    # Capacity with no reinforcement credit can be inspected independently.
    for i in np.flatnonzero(np.isfinite(r['PhysShear_VEd_kN_m'])):
        v=r['PhysShear_VEd_kN_m'][i]; cap=r['PhysShear_VRdc_kN_m'][i]
        # Use smallest depth over all families in both faces for z of links.
        d=min(h/2+abs(f.bar.z_mm) for f in families)
        proposal=shear_reinforcement_trial(v,cap,d,fck,fcd,fyk,fyd)
        out['PhysLL_Asw_req_mm2_m2'][i]=proposal['asw_mm2_m2']
        out['PhysLL_VRdmax_kN_m'][i]=proposal['vrdmax_kN_m']
        if v<=cap+1e-9:
            out['PhysLL_status'][i]='Sem necessidade de armadura de corte no ensaio LL.110; amarração por confirmar'
            for k in keys[2:5]:out['PhysLL_'+k][i]=0.
        elif not math.isfinite(proposal['asw_mm2_m2']):
            out['PhysLL_status'][i]='Limite da biela no ensaio; rever secção'
        else:
            delta=truss_increment(q[i]);
            for k,value in zip(keys[2:5],delta):out['PhysLL_'+k][i]=value
            u,res,status=model.check(n[i]+delta,m[i]);out['PhysLL_Face_util_com_trelica'][i]=u
            out['PhysLL_status'][i]=('Proposta de armadura de corte; equilíbrio de faces experimental; não instalada' if np.isfinite(u) and u<=1+1e-7 else 'Proposta de armadura de corte; equilíbrio de faces não demonstrado')
    return out


def refine_resultant_mesh(designer, provisional, adopted):
    """Search discrete longitudinal reinforcement to satisfy directional and
    resultant screens simultaneously. Only accept a full passing candidate;
    preserve minima, maximum vertical reinforcement and existing mesh areas.
    No credit for unconfirmed ties. Does not certify anchorage or shell ELU.
    """
    from wall_physical_layers import layout
    if not designer.optimize_rebar or not (designer.shell_qp_diagnostic or getattr(designer,"sandwich_design",False)) or 'tensor_ok' not in provisional or 'shear_ok' not in provisional:return
    sign=1 if designer.axial_convention=='Tracção positiva' else -1
    for panel,g in provisional.groupby('Panel',sort=False):
        if not g.tensor_ok.all() or not g.shear_ok.all():continue
        n=sign*g[['NXX','NYY','NXY']].to_numpy(float);q=g[['QXX','QYY']].to_numpy(float)
        original=adopted[str(panel)]
        def evaluate(mesh):
            try:
                fam=layout(designer.t,designer.cover,[designer._parse_rebar_text(v.text) for v in mesh],outer_axis=int(designer.local_y_is_vertical))
                # Guard all directional capacities as well as the resultant.
                ratios=[resultant_shear(designer.t,fam,n,qq,designer.fck,designer.cp['fcd'],designer.gamma_c,compression_credit=True)['PhysShear_util'].max() for qq in (q,q*np.array([1.,0.]),q*np.array([0.,1.]))]
                return max(ratios)
            except (ValueError,TypeError):return math.inf
        baseline=evaluate(original)
        if baseline<=1+1e-7 or not math.isfinite(baseline):continue
        candidates=[];seen=set();vertical=2 if designer.local_y_is_vertical else 0
        # Small bounded search; no changes to base and no partial adoption.
        for axes in ((0,),(1,),(0,1)):
            for scale in (1.15,1.35,1.6,2.,2.5,3.,4.):
                mesh=list(original)
                try:
                    for axis in axes:
                        for j in (2*axis,2*axis+1):
                            v=designer.optimize_rebar_solution(original[j].as_prov*scale,designer.max_spacing_for_direction(j//2==vertical//2),j//2==vertical//2,'XY'[axis]+('+' if j%2==0 else '-'))
                            if v.as_prov>mesh[j].as_prov:mesh[j]=v
                    designer.enforce_horizontal_minimum(mesh)
                except ValueError:continue
                if sum(v.as_prov for v in mesh[vertical:vertical+2])>designer.min_wall_reinf_total()[2]+1e-7:continue
                if any(a.as_prov+1e-7<b.as_prov for a,b in zip(mesh,original)):continue
                signature=tuple(v.text for v in mesh)
                if signature in seen:continue
                seen.add(signature)
                u=evaluate(mesh)
                if u<=1+1e-7:
                    candidates.append((sum(v.as_prov for v in mesh),u,mesh));break
        if candidates:
            mesh=min(candidates,key=lambda x:(x[0],x[1]))[2]
            for i,v in enumerate(mesh):
                if v is not original[i]:v.optimization_note+='; reforço para corte resultante (ensaio LL; amarração por confirmar)'
            adopted[str(panel)]=mesh

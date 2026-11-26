"""Conditional automation for isolated strips, not global stability.
Geometry of nodes cannot establish restraints. All factors are explicit.
"""
import math
import pandas as pd
from wall_geometry import panel_geometry


def slenderness_limit(n_kn, h, fcd, as_total, fyd, phi):
    """EC2 5.8.3.1 (5.13N), C=0.7 (unknown end moment ratio)."""
    if not all(map(math.isfinite,(n_kn,h,fcd,as_total,fyd,phi))) or min(n_kn,h,fcd,as_total,fyd)<=0 or phi<0:
        raise ValueError('Dados inválidos para esbelteza limite')
    n=n_kn/(h*fcd)
    omega=as_total*fyd/(1000*h*fcd)
    return 20/(1+.2*phi)*math.sqrt(1+2*omega)*.7/math.sqrt(n)


def moment_ratio(group, designer, direction):
    """EC2 5.8.4(3): section of largest absolute first-order moment per ELU.
    Use same node in QP; maximum absolute ratio across ELU cases, no cancellation.
    Reject missing QP, ambiguous duplicates and zero-denominator nonzero QP.
    This is a representative ratio for the strip model, not a global analysis.
    """
    axis=direction.lower()
    if designer.swap_local_axes: axis={'x':'y','y':'x'}[axis]
    col='m'+axis*2
    if col not in group or not group[col].map(math.isfinite).all() or group.get('__missing_'+col,pd.Series(False,index=group.index)).any():
        return None
    group=group.reset_index(drop=True)
    qp=group[group.case.map(designer.is_qp_case)]
    elu=group[group.case.map(lambda c: designer.case_role(c).startswith('ELU'))]
    if qp.empty or elu.empty or qp.node.duplicated().any() or elu.duplicated(['node','case']).any(): return None
    q=qp.set_index('node')[col]
    if not set(elu.node)<=set(q.index): return None
    values=[]
    for _,rows in elu.groupby('case'):
        peak=rows.loc[rows[col].abs().idxmax()]
        den=abs(float(peak[col])); num=abs(float(q.loc[peak.node]))
        if den<=1e-9:
            if q.abs().max()>1e-9: return None
            values.append(0.)
        else: values.append(num/den)
    return max(values) if values and all(map(math.isfinite,values)) else None


def panel_parameters(group,nodes,designer,kx,ky,rh,age,exposed_faces,creep_function):
    if not all(map(math.isfinite,(kx,ky,rh,age))) or min(kx,ky)<0 or not 40<=rh<=100 or age<.5 or exposed_faces not in (1,2):
        raise ValueError('Confirmar kX/kY, RH (40–100%), t0 ajustado ≥0,5 e faces expostas (1/2).')
    geo=panel_geometry(group.node,nodes)
    if geo['estado']!='Plano identificado': raise ValueError('Geometria inválida: '+geo['estado'])
    h=1000*geo['altura_no_plano_m']; w=1000*geo['largura_horizontal_no_plano_m']
    lx,ly=(w,h) if designer.local_y_is_vertical else (h,w)
    h0=2*designer.t/exposed_faces # broad faces only, neglect exposed edges
    phi=creep_function(designer.fck,rh,h0,age)
    ratios={a:moment_ratio(group,designer,a) for a in ('X','Y')}
    return dict(l0_x=kx*lx,l0_y=ky*ly,phi_final=phi,h0=h0,rh=rh,age=age,exposed_faces=exposed_faces,kx=kx,ky=ky,
                ratio_x=ratios['X'],ratio_y=ratios['Y'],phi_x=None if ratios['X'] is None else phi*ratios['X'],
                phi_y=None if ratios['Y'] is None else phi*ratios['Y'])

"""Local EC2 shear sizing, first-generation EC2 6.2.2/6.2.3/9.2.2.
Not a coupled shell or anchorage check. All results per 1 m strip.
For transverse reinforcement normal to the mid-plane, Asw/s [mm²/mm]
for a 1 m strip is converted to mm²/m². No credit for proposed links.
"""
import math
import numpy as np


def shear_reinforcement_trial(v, vrdc, d, fck, fcd, fyk, fyd, missing=False):
    if missing or not all(math.isfinite(x) for x in (v,vrdc,d,fck,fcd,fyk,fyd)) or min(d,fck,fcd,fyk,fyd)<=0:
        return dict(status='Dados insuficientes',asw_mm2_m2=math.nan,delta_ftd_kN_m=math.nan,vrdmax_kN_m=math.nan)
    # cot theta=1: maximum strut capacity and minimum additional chord tension.
    z=.9*d; cap=z*.6*(1-fck/250)*fcd/2
    if v<=vrdc+1e-9:
        return dict(status='Sem necessidade pelo modelo de faixa',asw_mm2_m2=0.,delta_ftd_kN_m=0.,vrdmax_kN_m=cap)
    if v>cap+1e-9:
        return dict(status='Esmagamento no modelo de faixa; rever secção',asw_mm2_m2=math.nan,delta_ftd_kN_m=math.nan,vrdmax_kN_m=cap)
    # EC2 (6.8): no addition of VRdc, Asw/s = VEd/(z fywd cot theta).
    req=max(v*1e6/(z*fyd),.08*math.sqrt(fck)/fyk*1e6)
    return dict(status='Armadura de corte a dimensionar/pormenorizar',asw_mm2_m2=req,delta_ftd_kN_m=.5*v,vrdmax_kN_m=cap)


def required_longitudinal_area(v,depth,sigma,fck,fcd,gamma_c):
    """Inverse of EC2 (6.2a,b). Infinity means rho limit prevents compliance."""
    k=min(2.,1+math.sqrt(200/depth)); c=.18/gamma_c*k
    stress=np.maximum(0,np.asarray(v)/depth-.15*np.minimum(sigma,.2*fcd))
    vmin=.035*k**1.5*math.sqrt(fck)
    rho=(stress/c)**3/(100*fck)
    return np.where(stress<=vmin+1e-10,0.,np.where(rho<=.02+1e-10,rho*1000*depth,np.inf))


def refine_directional_shear_mesh(designer, provisional, adopted, max_iterations=4):
    """Optional longitudinal reinforcement for VRdc, both faces conservative.
    Never credit unprovided shear reinforcement, never reduce adopted steel.
    Only attempt where the full directional envelope can be met within rho<=2%,
    vertical maximum and existing candidate/clear-spacing limits. No silent
    partial adoption on a failed search. Shell result is still an independent screen.
    """
    if not designer.optimize_rebar or 'shear_ok' not in provisional:return
    sign=1 if designer.axial_convention=='Compressão positiva' else -1
    for panel,g in provisional.groupby('Panel',sort=False):
        if not g.shear_ok.all():continue
        original=adopted[str(panel)]; mesh=list(original)
        for _ in range(max_iterations):
            changed=False
            for axis,name in enumerate('XY'):
                vertical=(axis==1)==designer.local_y_is_vertical
                q=g['Q'+name*2].abs().to_numpy(); sig=sign*g['N'+name*2].to_numpy()/designer.t
                for side in range(2):
                    j=2*axis+side; cross=2*(1-axis)+side
                    d=designer.shear_face_depth(mesh[j],mesh[cross],vertical)
                    target=float(required_longitudinal_area(q,d,sig,designer.fck,designer.cp['fcd'],designer.gamma_c).max())
                    if not math.isfinite(target) or target<=mesh[j].as_prov+1e-6:continue
                    try:candidate=designer.optimize_rebar_solution(target+1e-5,designer.max_spacing_for_direction(vertical),vertical,name+('+' if side==0 else '-'))
                    except ValueError:continue
                    if candidate.as_prov<=mesh[j].as_prov+1e-6:continue
                    if vertical and candidate.as_prov+mesh[2*axis+(1-side)].as_prov>designer.min_wall_reinf_total()[2]+1e-6:continue
                    candidate.optimization_note+='; reforço longitudinal para VRd,c (6.2.2; amarração por confirmar)'
                    mesh[j]=candidate;changed=True
            if not changed:break
        # Recheck both directions with final geometry; do not add steel if an
        # attempted solution fails to improve both faces of its own axis.
        for axis,name in enumerate('XY'):
            vertical=(axis==1)==designer.local_y_is_vertical
            q=g['Q'+name*2].abs().to_numpy(); sig=sign*g['N'+name*2].to_numpy()/designer.t
            for side in range(2):
                j=2*axis+side;cross=2*(1-axis)+side
                d=designer.shear_face_depth(mesh[j],mesh[cross],vertical)
                target=float(required_longitudinal_area(q,d,sig,designer.fck,designer.cp['fcd'],designer.gamma_c).max())
                if not math.isfinite(target) or target>mesh[j].as_prov+1e-5:
                    mesh[2*axis:2*axis+2]=original[2*axis:2*axis+2];break
        # Both checks recomputed in design_one afterwards, never treated as pass here.
        adopted[str(panel)]=mesh

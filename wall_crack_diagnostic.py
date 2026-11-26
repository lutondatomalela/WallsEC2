"""Experimental coupled QP stress/strain diagnostic, NOT an EC2 wk verdict.
Uses existing no-tension shell solver, common conservative nominal axis depth.
No validated mean relative strain or inclined crack band law is available.
"""
import math
import numpy as np
from wall_shell_service import BarLayer, solve_cracked_shell
from shell_crack_detail import projected_tension_band, crack_spacing_orthogonal


def diagnose(h,n,m,areas,axis_depth,ec,bar_geometry=None):
    bars=[BarLayer(axis,face*(h/2-axis_depth),area) for (axis,face),area in zip(((0,1),(0,-1),(1,1),(1,-1)),areas)]
    r=solve_cracked_shell(h,n,m,bars,ec)
    if r is None:
        return {'ShellQP_status':'Sem convergência / fora do domínio'}
    eps=r.face_principal_strain
    steel=r.steel_stress_mpa
    # Output principal strains and bar stresses, not a crack width.
    angles=[]
    for face in (1,-1):
        x,y,xy=r.mid_strain+face*h/2*r.curvature_per_mm
        angles.append(math.degrees(.5*math.atan2(2*xy,x-y)))
    output=dict(ShellQP_status='Equilíbrio experimental; wk pendente',
        ShellQP_eps1_plus_permille=1000*eps[0,-1],ShellQP_eps1_minus_permille=1000*eps[1,-1],
        ShellQP_theta_plus_deg=angles[0],ShellQP_theta_minus_deg=angles[1],
        ShellQP_sigma_x_plus_MPa=steel[0],ShellQP_sigma_x_minus_MPa=steel[1],
        ShellQP_sigma_y_plus_MPa=steel[2],ShellQP_sigma_y_minus_MPa=steel[3],
        ShellQP_residual_MPa=r.residual_mpa,ShellQP_axis_depth_mm=axis_depth)

    # Indicador exploratório: extensão principal bruta, sem tension stiffening.
    # A banda efectiva e a normal são aproximações geométricas, não uma lei
    # validada de abertura característica. Não é limite superior garantido.
    if bar_geometry is not None:
        indicators=[]
        for idx,face in enumerate((1,-1)):
            theta=math.atan2(abs(math.sin(math.radians(angles[idx]))),abs(math.cos(math.radians(angles[idx]))))
            band=projected_tension_band(h,r.mid_strain,r.curvature_per_mm,face,math.radians(angles[idx]),axis_depth)
            label='plus' if face==1 else 'minus'
            width=float('nan'); sr=float('nan')
            why='Banda de tracção não contém eixo nominal'
            if band.face_strain <= 0:
                width=0.; why='Sem extensão principal de tracção na superfície (modelo experimental)'
            elif band.contains_bar_axis and band.candidate_depth_mm>0:
                sr_values=[]
                for j in (idx,idx+2):
                    phi,spacing=bar_geometry[j]
                    rho=areas[j]/(1000*band.candidate_depth_mm)
                    cover=axis_depth-phi/2
                    if not (0<rho<1 and phi>0 and spacing>0 and cover>=0): break
                    sr_values.append(3.4*cover+.8*.425*phi/rho if spacing<=5*(cover+phi/2) else 1.3*band.tension_depth_mm)
                if len(sr_values)==2:
                    sr=crack_spacing_orthogonal(*sr_values,theta)
                    width=sr*max(0.,band.face_strain)
                    why="Indicador calculado (não é wk)"
            output['ShellQP_indicator_reason_'+label]=why
            output['ShellQP_indicator_'+label+'_mm']=width
            output['ShellQP_sr_candidate_'+label+'_mm']=sr
            output['ShellQP_hc_candidate_'+label+'_mm']=band.candidate_depth_mm
            indicators.append(width)
        output['ShellQP_indicator_max_mm']=max(indicators) if all(map(math.isfinite,indicators)) else float('nan')
        output['ShellQP_indicator_max_available_mm']=max((v for v in indicators if math.isfinite(v)),default=float('nan'))
        output['ShellQP_faces_evaluated']=sum(math.isfinite(v) for v in indicators)
    return output

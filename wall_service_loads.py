"""Elastic service-load assessment for the adopted reinforcement.
Conditional on an initially uncracked section, no imposed strains, confirmed
load history and concrete strength at loading. Not a crack-opening law.
"""
import numpy as np
import pandas as pd
from wall_physical_layers import layout, elastic_trial, LABELS
from wall_elastic_shear_history import screen


def attach_service_loads(r, d):
    cols=pd.DataFrame(index=r.index)
    for c in ('ELS_sigma_t_upper_MPa','ELS_sigma_c_upper_MPa','ELS_sigma_s_max_MPa','ELS_fctk005_MPa','wk_cargas_cond_mm','ELS_historico_ratio','ELS_72_eta_c','ELS_72_eta_s','ELS_72_lim_c_MPa','ELS_72_lim_s_MPa'):
        cols[c]=np.nan
    cols['ELS_cargas_estado']='Não aplicável'
    cols['ELS_72_estado']='Não aplicável'
    cols['ELS_72_modelo']='—'
    roles=['ELS-CAR','ELS-FREQ','ELS-QP']
    if d.axial_convention not in ('Tracção positiva','Compressão positiva'):return pd.concat([r,cols],axis=1)
    sign=1 if d.axial_convention=='Tracção positiva' else -1
    ec=22000*((d.fck+8)/10)**.3
    limit=.7*d.cp['fctm']
    names=['NXX_kN_m','NYY_kN_m','NXY_kN_m','MXX_kNm_m','MYY_kNm_m','MXY_kNm_m','QXX_kN_m','QYY_kN_m']
    for _,g in r.groupby('Panel',sort=False):
        s=g[g.Combo_type.isin(roles)]; cols.loc[s.index,'ELS_cargas_estado']='Dados/hipóteses insuficientes'
        cols.loc[s.index,'ELS_72_estado']='Dados/hipóteses insuficientes'
        if s.empty:continue
        try:
            fam=layout(d.t,d.cover,[d._parse_rebar_text(g.iloc[0][k+'_rebar']) for k in LABELS],outer_axis=1 if d.local_y_is_vertical else 0)
        except (ValueError,KeyError):continue
        v=s[names].to_numpy(float); valid=s.Tensor_complete.eq(True).to_numpy() & np.isfinite(v).all(axis=1)
        if not valid.any():continue
        idx=s.index[valid]; v=v[valid]
        # Convexity: the extreme plane principal stress of the affine field
        # occurs at a face. Weyl: adding transverse shear increases the
        # maximum eigenvalue by at most its spectral norm 1.5*|Q|/h.
        # Evaluate instantaneous and effective trial, envelope both.
        try:
            def bounds(modulus):
                strains,principal,steel=elastic_trial(d.t,sign*v[:,:3],v[:,3:6],fam,modulus)
                # Two independently valid upper bounds of the SAME trial
                # field. The smaller remains an upper bound. No increased
                # tensile strength, no relaxation of service history.
                shear=1.5*np.linalg.norm(v[:,6:],axis=1)/d.t
                t_old=np.maximum(0,principal[:,:,1].max(axis=1))+shear
                c_old=np.maximum(0,-principal[:,:,0].min(axis=1))+shear
                t_new=screen(d.t,strains,v[:,6:],modulus,intervals=32).tensile_upper_mpa.max(axis=1)
                c_new=screen(d.t,-strains,-v[:,6:],modulus,intervals=32).tensile_upper_mpa.max(axis=1)
                return np.minimum(t_old,t_new),np.minimum(c_old,c_new),np.abs(steel).max(axis=1)
            t,c,a=bounds(ec)
            if np.isfinite(d.creep_effective) and d.creep_effective>0:
                t2,c2,a2=bounds(ec/(1+d.creep_effective))
                t=np.maximum(t,t2);c=np.maximum(c,c2);a=np.maximum(a,a2)
        except (ValueError,np.linalg.LinAlgError):continue
        cols.loc[idx,'ELS_sigma_t_upper_MPa']=t;cols.loc[idx,'ELS_sigma_c_upper_MPa']=c;cols.loc[idx,'ELS_sigma_s_max_MPa']=a;cols.loc[idx,'ELS_fctk005_MPa']=limit
        cols.loc[idx,'ELS_cargas_estado']=np.where(t<=limit,'Secção elástica: sem excedência por cargas','Excede resistência inferior à tração')
        # All explicitly selected service cases must be present per node;
        # require CAR/FREQ/QP and no missing tensor, and do not presume history.
        from WallsEC2 import canonical_case_id
        if not (d.characteristic_cases and d.frequent_cases and d.qp_case):continue
        expected=d.characteristic_cases | d.frequent_cases | {canonical_case_id(d.qp_case)}
        for _,h in s.groupby('Node',sort=False):
            if set(h.Case.map(canonical_case_id))!=expected or h.Case.map(canonical_case_id).duplicated().any():continue
            vals=cols.loc[h.index,'ELS_sigma_t_upper_MPa'];qp=h.index[h.Combo_type.eq('ELS-QP')]
            car=h.index[h.Combo_type.eq('ELS-CAR')];freq=h.index[h.Combo_type.eq('ELS-FREQ')]
            # 7.2(2)-(4): 0.6 fck CAR is a conservative adopted limit;
            # 0.45 fck QP is a threshold for nonlinear creep, not failure.
            # 0.8 fyk CAR for directly applied actions; absolute stress is conservative.
            cols.loc[freq,'ELS_72_estado']='Sem limite específico 7.2 em FREQ'
            cols.loc[car,'ELS_72_lim_c_MPa']=.6*d.fck
            cols.loc[car,'ELS_72_lim_s_MPa']=.8*d.fyk
            cols.loc[qp,'ELS_72_lim_c_MPa']=.45*d.fck
            for ids in (car,qp):
                cols.loc[ids,'ELS_72_eta_c']=cols.loc[ids,'ELS_sigma_c_upper_MPa']/cols.loc[ids,'ELS_72_lim_c_MPa']
                cols.loc[ids,'ELS_72_eta_s']=cols.loc[ids,'ELS_sigma_s_max_MPa']/cols.loc[ids,'ELS_72_lim_s_MPa']
                cols.loc[ids,'ELS_72_modelo']='Secção íntegra; hipótese de histórico/coacção'
                if vals.notna().all() and vals.max()<=limit:
                    for i in ids:
                        rc=cols.at[i,'ELS_72_eta_c'];rs=cols.at[i,'ELS_72_eta_s']
                        if not np.isfinite(rc) or (i in car and not np.isfinite(rs)):continue
                        cols.at[i,'ELS_72_estado']=('Limites satisfeitos (condicional)' if rc<=1 and (i not in car or rs<=1) else ('Rever fluência não linear (limite superior)' if i in qp else 'Limite superior excedido; verificar tensões'))
                else:cols.loc[ids,'ELS_72_estado']='Secção íntegra não demonstrada; verificar tensões'
            # Strict uniaxial N-M, without any other concomitant tensor
            # component: check both uncracked and cracked normal-stress models.
            # No extension of the uniaxial law to biaxial cracking.
            hv=h[names].to_numpy(float)
            for axis,other in (('X',1),('Y',0)):
                strict=np.isfinite(hv).all(axis=1)&h.Tensor_complete.eq(True).to_numpy()&(np.abs(hv[:,[other,2,other+3,5,6,7]])<=1e-9).all(axis=1)
                # Require same uniaxial domain for all available service history.
                if not strict.all():continue
                for ids in (car,qp):
                    if not len(ids):continue
                    sc=r.loc[ids,f'ELS_{axis}_sigma_c_cracked_MPa'];ss=r.loc[ids,f'ELS_{axis}_sigma_s_cracked_MPa']
                    rc=np.maximum(cols.loc[ids,'ELS_72_eta_c'],sc/cols.loc[ids,'ELS_72_lim_c_MPa'])
                    rs=np.maximum(cols.loc[ids,'ELS_72_eta_s'],ss/cols.loc[ids,'ELS_72_lim_s_MPa'])
                    valid=rc.notna() & (rs.notna() if ids is car else True)
                    good=valid & rc.le(1) & (rs.le(1) if ids is car else True)
                    cols.loc[ids,'ELS_72_eta_c']=rc;cols.loc[ids,'ELS_72_eta_s']=rs
                    cols.loc[ids,'ELS_72_modelo']='Envolvente secções íntegra/fendilhada N-M '+axis
                    cols.loc[ids[good],'ELS_72_estado']='Limites satisfeitos (faixa N-M)'
                    cols.loc[ids[valid & ~good],'ELS_72_estado']='Rever tensões / fluência no modelo N-M'
                break

            if vals.notna().all() and len(qp):
                ratio=float(vals.max()/limit);cols.loc[qp,'ELS_historico_ratio']=ratio
                if ratio<=1 and d.wk_check_enabled:
                    pending=qp[r.loc[qp,'wk_max_mm'].isna() & ~r.loc[qp,'wk_partial_max_mm'].gt(0)]
                    cols.loc[pending,'wk_cargas_cond_mm']=0.
                    cols.loc[pending,'ELS_cargas_estado']='Sem fendilhação por cargas (condicional)'
    return pd.concat([r,cols],axis=1)

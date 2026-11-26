"""First-order sandwich demand SCREEN, not an EC2 resistance verification.
N tension positive; M positive tensions +; units kN/m, kNm/m, mm.
Fixed trial plane separation, not actual steel/concrete centroid positions.
"""
import numpy as np
import pandas as pd


def screen(n, m, z_mm, areas, fyd):
    n,m,areas = map(lambda a: np.asarray(a, dtype=float), (n,m,areas))
    if n.shape != m.shape or n.shape[-1] != 3 or areas.shape != n.shape[:-1]+(4,):
        raise ValueError('Invalid tensor/steel shape')
    if not np.isfinite(z_mm) or z_mm <= 0 or not np.isfinite(fyd) or fyd <= 0 or not all(np.isfinite(a).all() for a in (n,m,areas)) or (areas<=0).any():
        raise ValueError('Invalid screen inputs')
    out={}
    for face, sign, ix in [('plus',1,[0,2]),('minus',-1,[1,3])]:
        f=n/2+sign*m*1000/z_mm
        q=np.abs(f[...,2]); steel=np.maximum(f[...,:2]+q[...,None],0)
        c=f.copy(); c[...,:2]-=steel
        mid=(c[...,0]+c[...,1])/2
        rad=np.hypot((c[...,0]-c[...,1])/2,c[...,2])
        for j,axis in enumerate('xy'):
            out[f'Screen_F{axis}_{face}_kN_m']=f[...,j]
            out[f'Screen_T{axis}_{face}_kN_m']=steel[...,j]
            out[f'Screen_As{axis}_{face}_mm2_m']=steel[...,j]*1000/fyd
            out[f'Screen_ratio_{axis}_{face}']=steel[...,j]*1000/(areas[...,ix[j]]*fyd)
        out[f'Screen_Fxy_{face}_kN_m']=f[...,2]
        out[f'Screen_C1_{face}_kN_m']=mid+rad
        out[f'Screen_C2_{face}_kN_m']=mid-rad
    out['Screen_z_mm']=np.full(n.shape[:-1],z_mm)
    out['Screen_ratio_max']=np.maximum.reduce([out[f'Screen_ratio_{a}_{f}'] for a in 'xy' for f in ('plus','minus')])
    return out


def attach(results, thickness, cover, max_phi, fyd, convention, fck=None, fcd=None):
    """Add a transparent independent diagnostic; never change design/status."""
    results=results.copy()
    eligible=results.Combo_type.eq('ELU') & results.Tensor_complete.eq(True)
    if convention not in ('Tracção positiva','Compressão positiva'):
        eligible &= False
    results['Screen_status']='Não aplicável / dados incompletos'
    if not eligible.any():
        results['Screen_ratio_max']=np.nan
        return results
    g=results.loc[eligible]
    sign=1 if convention=='Tracção positiva' else -1
    # Trial inner bar plane, consistent with conservative depth assumption of strips.
    z=thickness-2*(cover+1.5*max_phi)
    vals=screen(sign*g[['NXX_kN_m','NYY_kN_m','NXY_kN_m']].to_numpy(),
                g[['MXX_kNm_m','MYY_kNm_m','MXY_kNm_m']].to_numpy(),z,
                g[['Asx+_prov_mm2_m','Asx-_prov_mm2_m','Asy+_prov_mm2_m','Asy-_prov_mm2_m']].to_numpy(),fyd)
    if fck is not None and fcd is not None:
        # Trial concrete band centred on each nominal face resultant plane.
        # Maximum geometrically admissible equal band depth, no overlapping bands.
        band=min(thickness-z,z)
        limit=.6*(1-fck/250)*fcd
        if band>0 and limit>0:
            vals['Screen_band_mm']=np.full(len(g),band)
            vals['Screen_fc_trial_MPa']=np.full(len(g),limit)
            for face in ('plus','minus'):
                vals[f'Screen_sigma_c_{face}_MPa']=-vals[f'Screen_C2_{face}_kN_m']/band
            vals['Screen_ratio_concrete']=np.maximum(vals['Screen_sigma_c_plus_MPa'],vals['Screen_sigma_c_minus_MPa'])/limit
    for k,v in vals.items():
        results.loc[eligible,k]=v
    results.loc[eligible,'Screen_status']='Diagnóstico 1.ª ordem; não verifica resistência'
    modal=eligible & results.Case.astype(str).str.contains('CQC|SRSS',case=False,regex=True)
    results.loc[modal,'Screen_status']='Diagnóstico modal; concomitância física por confirmar'
    return results


def envelope(results):
    rows=[]
    for p,g in results.groupby('Panel'):
        e=g[g.Combo_type.eq('ELU')]; valid=e.Screen_ratio_max.dropna()
        r=e.loc[valid.idxmax()] if len(valid) else {}
        rows.append({'Panel':p,'ELU_linhas':len(e),'diagnosticadas':len(valid),
                     'ratio_tracao_max':r.get('Screen_ratio_max',np.nan),'Node':r.get('Node',''), 'Case':r.get('Case',''),
                     'ratio_acima_1':int(valid.gt(1+1e-9).sum()),'ratio_betao_max':e.get('Screen_ratio_concrete',pd.Series(dtype=float)).max(),'Estado':'Diagnóstico; não é verificação ELU'})
    return pd.DataFrame(rows)

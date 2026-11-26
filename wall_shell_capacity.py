"""Static admissibility for an idealized two-plane membrane model, first order.

Tension positive. Each face has tension-only orthogonal steel, and a
negative-semidefinite concrete stress resultant. Its compressive trace is
bounded by band thickness times a reduced design strength. Both steel and
concrete resultants act at the same *nominal* face plane. This is not a
complete EN 1992-2 Annex LL verification (actual layer positions, strain
compatibility, transverse shear, stability, anchorage and modal signs remain).
Failure means no solution in this restricted model, not structural failure.
"""
import numpy as np
import pandas as pd


def face_state(force, steel_cap, concrete_cap):
    """Exact existence test in the stated model; capacities in kN/m.

    Concrete = [[-a,q],[q,-b]], steel = (Fx+a,Fy+b). PSD requires
    a,b>=0 and ab>=q². Minimize a+b on the feasible rectangle.
    """
    f=np.asarray(force,float); s=np.asarray(steel_cap,float)
    if f.shape[-1]!=3 or s.shape!=f.shape[:-1]+(2,) or not np.isfinite(f).all() or not np.isfinite(s).all() or (s<0).any() or not np.isfinite(concrete_cap) or concrete_cap<=0:
        raise ValueError('Dados inválidos do modelo resistente de duas camadas')
    x,y,q=np.moveaxis(f,-1,0); sx,sy=np.moveaxis(s,-1,0)
    q2=q*q; lo=np.maximum(-x,0); blo=np.maximum(-y,0); hi=sx-x; bhi=sy-y
    with np.errstate(divide='ignore',invalid='ignore'):
        req=np.divide(q2,bhi,out=np.full_like(q2,np.inf),where=bhi>0)
        req=np.where(q2==0,0,req)
        lower=np.maximum(lo,req)
        ideal=np.minimum(abs(q),np.divide(q2,blo,out=np.full_like(q2,np.inf),where=blo>0))
        a=np.minimum(np.maximum(ideal,lower),hi)
        b=np.maximum(blo,np.divide(q2,a,out=np.full_like(q2,np.inf),where=a>0))
        b=np.where(q2==0,blo,b)
    tol=1e-8*np.maximum(1,np.maximum(abs(x)+abs(y)+abs(q),np.maximum(sx,sy)))
    good=(hi>=lo-tol)&(bhi>=blo-tol)&(lower<=hi+tol)&(a>=-tol)&(b<=bhi+tol)&(a+b<=concrete_cap+tol)&np.isfinite(a+b)
    return good,a,b


def check(n,m,areas,h,z,fyd,fc):
    """Maximum proportional load factor in the restricted model (bisection)."""
    n,m,areas=map(lambda a:np.asarray(a,float),(n,m,areas))
    if n.shape!=m.shape or n.shape[-1]!=3 or areas.shape!=n.shape[:-1]+(4,) or not np.isfinite([h,z,fyd,fc]).all() or not 0<z<h or min(fyd,fc)<=0 or not np.isfinite(areas).all() or (areas<=0).any():
        raise ValueError('Geometria/materiais inválidos')
    band=min(h-z,z); cap=band*fc
    fp=n/2+m*1000/z; fm=n/2-m*1000/z
    sp=areas[..., [0,2]]*fyd/1000; sm=areas[..., [1,3]]*fyd/1000
    def feasible(lam):
        return face_state(fp*lam[...,None],sp,cap)[0]&face_state(fm*lam[...,None],sm,cap)[0]
    # monotonic proportional capacity; limit reported utilization to resolution 1/1024.
    low=np.zeros(n.shape[:-1]); high=np.full_like(low,1024.)
    for _ in range(30):
        mid=(low+high)/2; yes=feasible(mid); low=np.where(yes,mid,low); high=np.where(yes,high,mid)
    util=np.divide(1.,low,out=np.full_like(low,np.inf),where=low>0)
    zero=np.all(n==0,axis=-1)&np.all(m==0,axis=-1)
    util=np.where(zero,0,util)
    ok=feasible(np.ones_like(low))
    out={'Capacity_trial_util':util,'Capacity_trial_ok':ok,'Capacity_trial_band_mm':np.full_like(low,band),'Capacity_trial_fc_MPa':np.full_like(low,fc)}
    for label,f,s in [('plus',fp,sp),('minus',fm,sm)]:
        good,a,b=face_state(f,s,cap)
        for key,v in [('Tx',f[...,0]+a),('Ty',f[...,1]+b),('Cxx',-a),('Cyy',-b),('Cxy',f[...,2])]:
            out[f'Capacity_{key}_{label}_kN_m']=np.where(good,v,np.nan)
    return out


def attach(r,h,cover,max_phi,fyd,fck,fcd,convention):
    r=r.copy(); r['Capacity_trial_status']='Não avaliado'; r['Capacity_trial_util']=np.nan
    z=h-2*(cover+1.5*max_phi); fc=.6*(1-fck/250)*fcd
    eligible=r.Combo_type.eq('ELU')&r.Tensor_complete.eq(True)
    if convention not in ('Tracção positiva','Compressão positiva') or not 0<z<h or fc<=0 or not eligible.any():return r
    g=r.loc[eligible]; sign=1 if convention=='Tracção positiva' else -1
    a=g[['Asx+_prov_mm2_m','Asx-_prov_mm2_m','Asy+_prov_mm2_m','Asy-_prov_mm2_m']].to_numpy()
    valid=np.isfinite(a).all(axis=1)&(a>0).all(axis=1); g=g.loc[valid]; a=a[valid]
    if g.empty:return r
    v=check(sign*g[['NXX_kN_m','NYY_kN_m','NXY_kN_m']].to_numpy(),g[['MXX_kNm_m','MYY_kNm_m','MXY_kNm_m']].to_numpy(),a,h,z,fyd,fc)
    for k,x in v.items():
        if k=='Capacity_trial_ok':continue
        r.loc[g.index,k]=x
    # Independent Annex F reference on the same nominal split. The
    # normative membrane criteria do not validate physical shell geometry.
    from wall_annex_f import nominal_shell_reference
    fplus,fminus=nominal_shell_reference(sign*g[['NXX_kN_m','NYY_kN_m','NXY_kN_m']].to_numpy(),g[['MXX_kNm_m','MYY_kNm_m','MXY_kNm_m']].to_numpy(),a,h,z,fck,fcd,fyd)
    r.loc[g.index,'AnnexF_nominal_ok']=fplus['ok']&fminus['ok']
    for name,ref in (('plus',fplus),('minus',fminus)):
        r.loc[g.index,'AnnexF_nominal_concrete_'+name+'_MPa']=ref['concrete_stress_mpa']
        r.loc[g.index,'AnnexF_nominal_concrete_limit_'+name+'_MPa']=ref['concrete_limit_mpa']
        for j,axis in enumerate('xy'):
            r.loc[g.index,'AnnexF_nominal_steel_'+axis+'_'+name+'_kN_m']=ref['steel'][...,j]
            r.loc[g.index,'AnnexF_nominal_steel_opt_'+axis+'_'+name+'_kN_m']=ref['steel_opt'][...,j]
    r.loc[g.index,'AnnexF_nominal_status']=np.where(fplus['ok']&fminus['ok'],'Anexo F: referência nominal com equilíbrio; não é ELU de casca','Anexo F: sem solução na referência nominal')
    r.loc[g.index,'Capacity_trial_status']=np.where(v['Capacity_trial_ok'],'Equilíbrio admissível no modelo idealizado','Sem solução no modelo idealizado')
    modal=g.Case.astype(str).str.contains('CQC|SRSS',case=False,regex=True)
    r.loc[g.index[modal],'Capacity_trial_status']='Modal: sinais/concomitância por confirmar; '+r.loc[g.index[modal],'Capacity_trial_status']
    r.loc[g.index[modal],'AnnexF_nominal_status']='Modal: sinais/concomitância por confirmar; '+r.loc[g.index[modal],'AnnexF_nominal_status']
    return r


def envelope(r):
    rows=[]
    for p,g in r[r.Combo_type.eq('ELU')].groupby('Panel'):
        u=g.Capacity_trial_util.dropna(); worst=g.loc[u.idxmax()] if len(u) else {}
        f=g.get('AnnexF_nominal_ok',pd.Series(index=g.index,dtype=object))
        rows.append(dict(Panel=p,Linhas=len(g),Avaliadas=len(u),Sem_solucao=int(g.Capacity_trial_status.str.contains('Sem solução',regex=False).sum()),Util_modelo=worst.get('Capacity_trial_util',np.nan),Node=worst.get('Node',''),Case=worst.get('Case',''),AnexoF_nominal_com_equilibrio=int(f.eq(True).sum()),AnexoF_nominal_sem_equilibrio=int(f.eq(False).sum()),AnexoF_nominal_nao_avaliadas=int(f.isna().sum()),Estado='Modelos nominais; não é verificação ELU completa'))
    return pd.DataFrame(rows)

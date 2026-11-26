"""Cálculo de ensaio; confirmar hipóteses de apoio e ambiente externamente."""
import argparse,json
from pathlib import Path
from WallsEC2 import WallDesigner,WallsEC2App,clean_dataframe,read_csv_robust,APP_VERSION
from wall_geometry import read_nodes
from wall_shell_screen import envelope
from wall_shell_capacity import envelope as capacity_envelope
from wall_physical_layers import summary as physical_summary

def _panel_job(payload):
    panel,group,settings,nos,options=payload
    d=WallDesigner(**settings);d.sandwich_design=True
    if options is not None:d.auto_stability=(read_nodes(nos),options)
    return panel,d.design_dataframe(group.reset_index(drop=True))


def calculate_parallel(df,settings,nos,options,workers):
    # Auto mode already treats each panel independently. Do not change the
    # numerical workflow; preserve panel order and every selected row.
    from concurrent.futures import ProcessPoolExecutor,as_completed
    import multiprocessing as mp
    import pandas as pd
    jobs=[(str(panel),group,settings,nos,options) for panel,group in df.groupby('panel',sort=False,dropna=False)]
    results={}
    with ProcessPoolExecutor(max_workers=workers,mp_context=mp.get_context('spawn')) as ex:
        futures=[ex.submit(_panel_job,job) for job in jobs]
        for future in as_completed(futures):
            panel,r=future.result();results[panel]=r
            print(f'Painel {panel}: {len(r)} linhas; {len(results)}/{len(jobs)} painéis',flush=True)
    return pd.concat([results[job[0]] for job in jobs],ignore_index=True)


def run(source,profile,target,nos=None,options=None,workers=1):
    cfg=json.loads(Path(profile).read_text(encoding='utf-8-sig'))
    d=WallDesigner(**cfg['calculo']); d.sandwich_design=True
    if options is not None:
        if nos is None: raise ValueError('Importar nós para automatizar.')
        d.auto_stability=(read_nodes(nos),options)
    df=clean_dataframe(read_csv_robust(str(source)))
    out=Path(target);out.mkdir(parents=True,exist_ok=True)
    r=calculate_parallel(df,cfg['calculo'],nos,options,workers) if workers>1 and options is not None else d.design_dataframe(df,progress=lambda i,n: print(f'{i}/{n}',flush=True) if i%5000==0 else None)
    qp=r[r.Combo_type.eq('ELS-QP')]
    tables={'Resumo':WallsEC2App.build_panel_summary(None,r),'Envolvente_NM':WallsEC2App.build_nm_envelope(r),
            'Estabilidade':r.loc[r.Combo_type.eq('ELU'),['Panel','Node','Case']+[c for c in r if c.startswith('Stability_') or c.startswith('NM_')]],
            'Parametros_Auto':r[['Panel']+[c for c in r if c.startswith('Auto_')]].drop_duplicates(),
            'QP_Fendilhacao_Convencional':qp[['Panel','Node','Case','wk_max_mm','Crack_control_status','Crack_control_note']],
            'Sandwich_ELU':r.loc[r.Combo_type.eq('ELU'),['Panel','Node','Case']+[c for c in r if c.startswith('Sand_')]],
            'Cobertura_Estabilidade':WallsEC2App.build_stability_coverage(r)}
    for name,tab in tables.items(): tab.to_csv(out/(name+'.csv'),index=False,sep=';',decimal=',',encoding='utf-8-sig')
    (out/'Hipoteses.json').write_text(json.dumps(dict(versao=APP_VERSION,perfil=cfg,auto=options,nota='Modelo sandwich com envolvente de incrementos por faixa; amarração, compressão oblíqua e estabilidade global por confirmar.'),ensure_ascii=False,indent=2),encoding='utf-8')
    print('ELU:',r.Combo_type.eq('ELU').sum(),'QP:',len(qp),flush=True)
    if 'ShellQP_status' in qp: print(qp.ShellQP_status.value_counts(dropna=False).to_string(),flush=True)
    return r

if __name__=='__main__':
    p=argparse.ArgumentParser(description=__doc__)
    for a in ['source','profile','target']:p.add_argument(a)
    p.add_argument('--nos');p.add_argument('--confirmar-travamentos',action='store_true')
    for a in ['kx','ky','rh','t0']:p.add_argument('--'+a,type=float)
    p.add_argument('--faces',type=int,choices=[1,2]); p.add_argument('--workers',type=int,choices=range(1,5),default=1); a=p.parse_args()
    opts=(a.kx,a.ky,a.rh,a.t0,a.faces)
    if (a.confirmar_travamentos or any(v is not None for v in opts)) and not (a.nos and a.confirmar_travamentos and all(v is not None for v in opts)):p.error('Modo automático exige nós, confirmação e cinco parâmetros.')
    run(a.source,a.profile,a.target,a.nos,opts if a.confirmar_travamentos else None,a.workers)

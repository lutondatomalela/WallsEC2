"""Small synthetic end-to-end startup test, suitable for a frozen GUI build."""
import json
from pathlib import Path

def run(output):
    import numpy as np
    import pandas as pd
    from WallsEC2 import WallsEC2App,WallDesigner,clean_dataframe,APP_VERSION
    app=WallsEC2App()
    try:
        app.withdraw(); app.update_idletasks()
        if not app.icon_loaded:raise RuntimeError('Ícone não carregado')
        d=WallDesigner(250,30,'C30/37',500,elu_cases='101',qp_case='302',characteristic_cases='303',frequent_cases='311',axial_convention='Tracção positiva',wk_check_enabled=True)
        d.sandwich_design=True
        df=clean_dataframe(pd.DataFrame([dict(panel=1,node=1,case=c,nxx=-20,nyy=-40,nxy=3,mxx=2,myy=3,mxy=.2,qxx=1,qyy=2) for c in (101,302,303,311)]))
        r=d.design_dataframe(df)
        if len(r)!=4 or not np.isfinite(r.loc[r.Combo_type.eq('ELU'),'util_max']).all():raise RuntimeError('Falha do motor no ensaio sintético')
        status,reason=app.panel_outcome(r)
        result=dict(version=APP_VERSION,rows=len(r),icon=True,status=status,reason=reason,smoke_test='passed')
        Path(output).write_text(json.dumps(result,ensure_ascii=False,indent=2),encoding='utf-8')
    finally:app.destroy()

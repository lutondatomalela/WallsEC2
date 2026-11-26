"""Audit explicit case coverage without inventing missing results."""
import pandas as pd


def case_audit(df, expected, case_id):
    expected=set(expected)
    # Audit only if explicit combination set was requested. Keep non-numeric node labels.
    cols=['Panel','Node','Casos_esperados','Casos_presentes','Casos_em_falta','Estado']
    if not expected: return pd.DataFrame(columns=cols)
    v=df[['panel','node','case']].copy()
    v['id']=v.case.map(case_id)
    for col in ('panel','node'):
        v[col]=v[col].astype(str).str.strip()
    selected=v[v.id.isin(expected)]
    if selected.duplicated(['panel','node','id']).any():
        raise ValueError('Combinações duplicadas na mesma identidade painel/nó/caso')
    rows=[]
    for (panel,node),g in v.groupby(['panel','node'],sort=False):
        present=set(g.id)&expected; missing=expected-present
        rows.append([panel,node,len(expected),len(present),' '.join(sorted(missing,key=lambda x:(len(x),x))),
                     'Incompleto' if missing or not node or node.lower()=='nan' else 'Completo'])
    return pd.DataFrame(rows,columns=cols)

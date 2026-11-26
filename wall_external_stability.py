"""Traceable external global stability declaration.

This records a project engineer's assessment, not an independent analysis of
its report. Fingerprints detect a different calculation, not authenticity.
Local verification status is never upgraded by an external declaration.
"""
import hashlib
import json
from pathlib import Path
import pandas as pd

SCHEMA=1
STATES=('Pendente','Conforme','Não conforme')
CHECKS=('modelo_e_acoes_confirmados','segunda_ordem_global_confirmada','imperfeicoes_e_travamentos_confirmados')


def _json(value):
    return json.dumps(value,ensure_ascii=False,sort_keys=True,allow_nan=False,separators=(',',':'))


def file_sha256(path):
    h=hashlib.sha256()
    with Path(path).open('rb') as f:
        for chunk in iter(lambda:f.read(1024*1024),b''):h.update(chunk)
    return h.hexdigest()


def calculation_scope(*,version,settings,efforts,nodes,results):
    if efforts.empty or results.empty or not {'Panel','Case','Combo_type','Node'}<=set(results.columns):
        raise ValueError('Sem cálculo completo para associar a declaração')
    elu=results[results.Combo_type.eq('ELU')]
    if elu.empty:raise ValueError('Sem combinações ELU classificadas')
    panel_ids=sorted(set(results.Panel.astype(str)))
    scopes=[]
    for p in panel_ids:
        g=elu[elu.Panel.astype(str).eq(p)]
        complete=bool(len(g) and 'Case_coverage' in g and g.Case_coverage.eq('Completo').all())
        scopes.append(dict(painel=p,casos_elu=sorted(set(g.Case.astype(str))),cobertura_elu_completa=complete))
    # Bind full normalized input, settings, geometry and the selected results
    # (including final reinforcement and calculation version). Canonical CSV
    # is intentionally order-sensitive; a different snapshot is rejected.
    def digest_frame(df):
        return hashlib.sha256(df.to_csv(index=False,na_rep='<NA>',float_format='%.17g',lineterminator='\n').encode()).hexdigest()
    identity=dict(versao=str(version),configuracao=settings,nos=nodes or {},esforcos=digest_frame(efforts),resultados=digest_frame(results),paineis=scopes)
    return dict(versao=str(version),sha256=hashlib.sha256(_json(identity).encode()).hexdigest(),paineis=scopes)


def template(scope):
    return dict(schema=SCHEMA,scope_sha256=scope['sha256'],versao=scope['versao'],
                responsavel='',metodo='',referencia_relatorio='',relatorio_sha256='',
                confirmacoes={key:False for key in CHECKS},
                paineis=[dict(**p,estado='Pendente',observacoes='') for p in scope['paineis']])


def validate_declaration(scope,declaration,report_path):
    if not isinstance(declaration,dict) or declaration.get('schema')!=SCHEMA or declaration.get('versao')!=scope['versao'] or declaration.get('scope_sha256')!=scope['sha256']:
        raise ValueError('Declaração não corresponde a este cálculo/versão')
    expected={p['painel']:p for p in scope['paineis']}
    received=declaration.get('paineis')
    if not isinstance(received,list) or len(received)!=len(expected):raise ValueError('Cobertura de painéis incompleta')
    if any(not isinstance(p,dict) or not isinstance(p.get('painel'),str) for p in received):raise ValueError('Painéis inválidos')
    if set(p['painel'] for p in received)!=set(expected) or len({p['painel'] for p in received})!=len(received):raise ValueError('Painéis diferentes ou duplicados')
    metadata={key:declaration.get(key) for key in ('responsavel','metodo','referencia_relatorio')}
    if any(not isinstance(v,str) or not v.strip() or len(v)>300 for v in metadata.values()):raise ValueError('Identificar responsável, método e relatório')
    if not Path(report_path).is_file() or Path(report_path).stat().st_size==0:raise ValueError('Relatório externo inexistente/vazio')
    digest=file_sha256(report_path)
    previous=declaration.get('relatorio_sha256','')
    if previous and previous!=digest:raise ValueError('O ficheiro do relatório externo não corresponde ao hash declarado')
    confirmations=declaration.get('confirmacoes',{})
    complete=isinstance(confirmations,dict) and all(confirmations.get(k) is True for k in CHECKS)
    rows=[]
    for p in received:
        id=p['painel'];cases=p.get('casos_elu');state=p.get('estado')
        if not isinstance(cases,list) or any(not isinstance(c,str) for c in cases) or sorted(cases)!=expected[id]['casos_elu']:raise ValueError(f'Painel {id}: combinações ELU diferentes ou incompletas')
        if state not in STATES:raise ValueError(f'Painel {id}: estado inválido')
        if state=='Conforme' and (not complete or not cases or not expected[id]['cobertura_elu_completa']):raise ValueError(f'Painel {id}: confirmação externa incompleta')
        notes=p.get('observacoes','')
        if not isinstance(notes,str):raise ValueError(f'Painel {id}: observações inválidas')
        rows.append(dict(Panel=id,Estabilidade_global_externa=state+' (declaração externa)' if state!='Pendente' else 'Pendente',
                         Casos_ELU='; '.join(cases),**metadata,Relatorio_SHA256=digest,Calculo_SHA256=scope['sha256'],Observacoes=notes))
    return pd.DataFrame(rows)

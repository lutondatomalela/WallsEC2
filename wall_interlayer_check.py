"""LL(115)(c): verify the documented additional transverse shear bound.

The external bound must cover the continuous spatial field, all ELU positions
and all strip moment scenarios, with the final reinforcement. No inference
from a nodal force difference is made. The section check is conservative for
any direction of the additional shear, without credit for compression and
without specific transverse reinforcement. A failure to prove the bound is
not proof of structural failure. This is not an interpretation of the external
report or a general method of computing the LL.115 spatial field.
"""
import math
from pathlib import Path
import pandas as pd
import numpy as np
from wall_external_stability import file_sha256

CHECKS=('campo_espacial_continuo','todas_posicoes_e_combinacoes_elu',
        'envolvente_incrementos_por_faixa','armaduras_finais_e_amarração',
        'eixos_sinais_e_concomitancia','reserva_valida_em_todo_campo')


def panel_reserves(results):
    required={'Panel','Combo_type','Case','Node','Sand_transfer_reserve_kN_m','Sand_transfer_VRdc_lower_kN_m','Sand_Asw_req_mm2_m2','Sand_util','Case_coverage','Sand_strip_order_status','Sand_transfer_status'}
    if not required.issubset(results.columns):raise ValueError('Sem resultados sandwich e reserva de corte')
    e=results[results.Combo_type.eq('ELU')];out={}
    for panel,g in e.groupby('Panel',sort=False):
        v=g.Sand_transfer_reserve_kN_m.to_numpy(float)
        ok=(len(g)>0 and np.isfinite(v).all() and np.isfinite(g.Sand_util.to_numpy(float)).all() and g.Sand_Asw_req_mm2_m2.eq(0).all() and g.Case_coverage.eq('Completo').all() and not g.Sand_strip_order_status.eq('Dados locais pendentes').any())
        out[str(panel)]=dict(reserva_min_kN_m=float(np.min(v)) if np.isfinite(v).all() else None,condicoes_locais=bool(ok))
    return out


def template(scope,results):
    bounds=panel_reserves(results)
    return dict(schema=1,tipo='LL115_corte_intercamadas',scope_sha256=scope['sha256'],versao=scope['versao'],responsavel='',referencia_relatorio='',metodo='',relatorio_sha256='',confirmacoes={k:False for k in CHECKS},paineis=[dict(**p,**bounds.get(p['painel'],dict(reserva_min_kN_m=None,condicoes_locais=False)),limite_corte_adicional_kN_m=None) for p in scope['paineis']])


def evaluate(scope,results,record,report_path):
    if not isinstance(record,dict) or record.get('schema')!=1 or record.get('tipo')!='LL115_corte_intercamadas' or record.get('scope_sha256')!=scope['sha256'] or record.get('versao')!=scope['versao']:
        raise ValueError('Ficha de corte não corresponde ao cálculo actual')
    info={k:record.get(k) for k in ('responsavel','referencia_relatorio','metodo')}
    if any(not isinstance(v,str) or not v.strip() or len(v)>300 for v in info.values()):raise ValueError('Identificar responsável, método e referência do relatório')
    if not Path(report_path).is_file() or Path(report_path).stat().st_size==0:raise ValueError('Relatório externo inexistente/vazio')
    digest=file_sha256(report_path)
    if record.get('relatorio_sha256') not in ('',None,digest):raise ValueError('O relatório não corresponde ao hash')
    confirm=record.get('confirmacoes',{})
    if not isinstance(confirm,dict) or not all(confirm.get(k) is True for k in CHECKS):raise ValueError('Confirmar as condições de cobertura do limite externo')
    expected={p['painel']:p for p in scope['paineis']};data=record.get('paineis')
    if not isinstance(data,list) or len(data)!=len(expected) or any(not isinstance(p,dict) or not isinstance(p.get('painel'),str) for p in data) or len({p['painel'] for p in data})!=len(data) or {p['painel'] for p in data}!=set(expected):raise ValueError('Cobertura de painéis incorrecta')
    bounds=panel_reserves(results);out=[]
    for p in data:
        panel=p['painel'];ref=expected[panel];cases=p.get('casos_elu')
        if not isinstance(cases,list) or any(not isinstance(c,str) for c in cases) or sorted(cases)!=ref['casos_elu']:raise ValueError(f'Painel {panel}: combinações diferentes')
        b=p.get('limite_corte_adicional_kN_m');r=bounds.get(panel,{})
        if b is not None and (isinstance(b,bool) or not isinstance(b,(int,float)) or not math.isfinite(b) or b<0):raise ValueError(f'Painel {panel}: limite adicional inválido')
        reserve=r.get('reserva_min_kN_m');complete=bool(ref['cobertura_elu_completa'] and r.get('condicoes_locais',False))
        if b is None or not complete or reserve is None:state='Condicionado — dados insuficientes'
        elif b<=reserve+1e-9:state='Satisfeito com limite externo'
        else:state='Condicionado — reserva insuficiente'
        out.append(dict(Panel=panel,Estado_intercamadas=state,Limite_adicional_kN_m=b,Reserva_kN_m=reserve,Margem_kN_m=reserve-b if reserve is not None and b is not None else None,**info,Relatorio_SHA256=digest,Calculo_SHA256=scope['sha256']))
    return pd.DataFrame(out)

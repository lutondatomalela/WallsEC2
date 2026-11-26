"""Independent-result exchange. Never upgrades the internal design verdict.
Exact immutable inputs bind an external calculation to the same signed loads,
physical reinforcement and material/geometry assumptions. Numeric comparisons
are diagnostics, not acceptance tolerances or a validation of the external report.
"""
import hashlib
import json
import math
from pathlib import Path

METRICS = {'ELU': ('util_casca','VRdc_kN_m','Asw_mm2_m2'),
           'ELS-QP': ('wk_plus_mm','wk_minus_mm')}
FORCES = ('Nxx','Nyy','Nxy','Mxx','Myy','Mxy','Qx','Qy')


def canonical(obj):
    return json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(',', ':'), allow_nan=False)


def fingerprint(obj):
    return hashlib.sha256(canonical(obj).encode('utf-8')).hexdigest()


def number(value, *, nonnegative=False):
    if isinstance(value, bool) or not isinstance(value, (int,float)) or not math.isfinite(value) or (nonnegative and value < 0):
        raise ValueError('Valor numérico inválido')
    return float(value)


def make_request(rows):
    """Each row contains identity, role, signed forces, materials, mesh and
    internal diagnostic metrics; no missing internal value is interpreted as 0."""
    result=[]; seen=set()
    for row in rows:
        inputs=row['inputs']; role=inputs['role']; metrics=METRICS[role]
        key=tuple(inputs[k] for k in ('project','panel','node','case','role'))
        if key in seen: raise ValueError('Registo duplicado')
        seen.add(key)
        if set(inputs['forces'])!=set(FORCES):raise ValueError('Tensor incompleto')
        for v in inputs['forces'].values():number(v)
        if set(inputs['mesh'])!={'X+','X-','Y+','Y-'} or any(not isinstance(v,str) or not v.strip() for v in inputs['mesh'].values()):raise ValueError('Malha incompleta')
        for v in ('h_mm','cover_mm','fck_MPa','fyk_MPa'):
            if number(inputs[v],nonnegative=True)<=0:raise ValueError('Material/geometria inválidos')
        internal=row['internal_experimental']
        if set(internal)!=set(metrics):raise ValueError('Métricas internas incompletas')
        for v in internal.values():
            if v is not None:number(v,nonnegative=True)
        result.append({'id':fingerprint(inputs),'inputs':inputs,'internal_experimental':internal})
    if not result:raise ValueError('Pedido vazio')
    return {'schema':1,'rows':result,'request_sha256':fingerprint(result)}


def blank_response(request):
    return {'schema':1,'request_sha256':request['request_sha256'],'responsavel':'','metodo':'','relatorio_sha256':'',
            'rows':[{'id':r['id'],'inputs_sha256':r['id'],'reference':dict.fromkeys(METRICS[r['inputs']['role']]),'equivalence_confirmed':False,'observacoes':''} for r in request['rows']]}


def compare(request,response,report_path):
    if request!=make_request(request['rows']):raise ValueError('Pedido alterado ou inválido')
    if response.get('schema')!=1 or response.get('request_sha256')!=request['request_sha256']:raise ValueError('Resposta não corresponde ao pedido')
    for k in ('responsavel','metodo'):
        if not isinstance(response.get(k),str) or not response[k].strip():raise ValueError('Identificar responsável e método')
    p=Path(report_path)
    if not p.is_file() or p.stat().st_size==0:raise ValueError('Relatório de referência em falta')
    digest=hashlib.sha256(p.read_bytes()).hexdigest()
    if response.get('relatorio_sha256')!=digest:raise ValueError('Hash do relatório não corresponde')
    rows=response.get('rows',[]); expected={r['id']:r for r in request['rows']}
    if len(rows)!=len(expected) or {r.get('id') for r in rows}!=set(expected):raise ValueError('Cobertura diferente ou duplicados')
    out=[]
    for r in rows:
        rid=r['id']; base=expected[rid]; inp=base['inputs']; role=inp['role']; metrics=METRICS[role]
        if r.get('inputs_sha256')!=rid:raise ValueError('Identidade dos dados alterada')
        ref=r.get('reference',{})
        if set(ref)!=set(metrics):raise ValueError('Métricas externas incompletas')
        eq=r.get('equivalence_confirmed') is True
        for metric in metrics:
            a=base['internal_experimental'][metric]; b=ref[metric]
            if b is not None:number(b,nonnegative=True)
            comparable=eq and a is not None and b is not None
            out.append({**{k:inp[k] for k in ('project','panel','node','case','role')},'metric':metric,'internal_experimental':a,'external':b,
                        'difference':a-b if comparable else None,'relative_difference':(a-b)/b if comparable and b>0 else None,
                        'status':'Comparação numérica; não é aprovação' if comparable else 'Pendente / não comparável',
                        'reference_report_sha256':digest,'responsavel':response['responsavel'],'metodo':response['metodo']})
    return out

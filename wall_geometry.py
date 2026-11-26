"""Geometry in metres, global Z vertical; geometric axes are not FE material axes."""
import csv
import math
from pathlib import Path
import re

import numpy as np
import pandas as pd


class MissingCoordinateUnits(ValueError):
    """Coordinate units must be explicitly provided when absent from headers."""


def node_id(value):
    s = str(value).strip()
    if not re.fullmatch(r'[0-9]+(?:[.,]0+)?', s):
        raise ValueError(f"Número de nó inválido: {value}")
    return str(int(re.split(r'[.,]', s)[0]))


def _header(value):
    import unicodedata
    return re.sub(r'\s+', ' ', ''.join(c for c in unicodedata.normalize('NFKD', str(value).strip().lower()) if not unicodedata.combining(c)))


def _layout(row):
    fields = [_header(v) for v in row]
    identifiers = [i for i,v in enumerate(fields) if v in ('node','no','nos','node id','node number','numero do no','numero de no','n. no','id no','id node')]
    if len(identifiers) != 1:
        return None
    axes = []
    for axis in 'xyz':
        matches = []
        for i,v in enumerate(fields):
            m = re.fullmatch(rf'(?:coord(?:enada)?\.?\s+)?{axis}(?:\s*(?:\(\s*(m|cm|mm)\s*\)|\[\s*(m|cm|mm)\s*\]|\s+(m|cm|mm)))?', v)
            if m:
                matches.append((i,next((u for u in m.groups() if u),None)))
        if len(matches) != 1:
            return None
        axes.append(matches[0])
    support = next((i for i,v in enumerate(fields) if v in ('support','apoio','apoios')), None)
    return identifiers[0], axes, support


def _table(rows):
    for i,row in enumerate(rows[:100]):
        layout = _layout(row)
        if layout is not None:
            return i,layout,rows
    return None


def _read_table(path):
    path = Path(path)
    if path.suffix.lower() in ('.xlsx','.xlsm'):
        from openpyxl import load_workbook
        wb = load_workbook(path, read_only=True, data_only=True)
        matches = []
        try:
            for ws in wb.worksheets:
                iterator=ws.values
                from itertools import islice
                head=list(islice(iterator,100))
                match=_table(head)
                if match:
                    matches.append((ws.title,match[0],match[1],head+list(iterator)))
        finally:
            wb.close()
        if len(matches)!=1:
            raise ValueError('O Excel deve conter uma única folha com Node/Nó e X/Y/Z reconhecíveis. Folhas encontradas: '+', '.join(m[0] for m in matches))
        return matches[0][1:]
    raw=path.read_bytes()
    if raw.startswith((b'\xff\xfe',b'\xfe\xff')):
        encodings=('utf-16',)
    elif b'\x00' in raw[:1024]:
        encodings=('utf-16-le','utf-16-be')
    else:
        encodings=('utf-8-sig','cp1252','latin1')
    import io
    for encoding in encodings:
        try:
            content=raw.decode(encoding)
        except UnicodeError:
            continue
        for delimiter in (';','\t',',','|'):
            try:
                rows=list(csv.reader(io.StringIO(content),delimiter=delimiter,strict=True))
            except csv.Error:
                continue
            match=_table(rows)
            if match:
                return match
    raise ValueError('Cabeçalho de nós não reconhecido. Esperam-se Node/Nó e X/Y/Z (m, cm ou mm); CSV/TXT ou XLSX.')


def _coordinate(value):
    s=str(value).strip().replace('\u00a0','').replace(' ','')
    if re.fullmatch(r'[+-]?\d{1,3}(?:\.\d{3})+,\d+',s):
        s=s.replace('.','')
    v=float(s.replace(',','.'))
    if not math.isfinite(v):
        raise ValueError('Coordenada não finita')
    return v


def read_nodes(path, units=None):
    """Read node coordinates in metres. No inferred units or silent duplicates."""
    i,(id_col,axes,support),rows=_read_table(path)
    scales={'m':1.,'cm':.01,'mm':.001}
    if units is not None and units not in scales:
        raise ValueError('Unidade de coordenadas inválida: use m, cm ou mm.')
    if any(u is None for _,u in axes) and units is None:
        raise MissingCoordinateUnits('O cabeçalho não indica todas as unidades. Confirme a unidade das coordenadas sem unidade.')
    nodes={}
    for line,row in enumerate(rows[i+1:],i+2):
        def cell(j):
            return '' if j is None or j>=len(row) or row[j] is None else str(row[j]).strip()
        ident=cell(id_col)
        if ident in ('*','') and not any(cell(c) for c,_ in axes):
            continue
        try:
            if any(str(v).strip() for v in row[len(rows[i]):] if v is not None):
                raise ValueError("Colunas a mais; confirme separador e aspas das vírgulas decimais")
            key=node_id(ident)
            coords=tuple(_coordinate(cell(c))*scales[u or units] for c,u in axes)
            if key in nodes:
                raise ValueError(f'Nó duplicado: {key}')
        except (ValueError,OverflowError) as exc:
            raise ValueError(f'Linha {line}, nó {ident or "sem ID"}: {exc}') from exc
        nodes[key]=(*coords,cell(support))
    if not nodes:
        raise ValueError('A tabela de coordenadas não contém nós.')
    return nodes


def geometry_tables(efforts, nodes):
    """Associate only by panel/node, independently of combination or row order."""
    summaries=[]; details=[]
    if efforts.empty or not {'panel','node'} <= set(efforts.columns):
        return pd.DataFrame(),pd.DataFrame()
    for panel,group in efforts.groupby('panel',sort=False,dropna=False):
        valid=[]; invalid=[]; seen=set()
        for raw in group['node'].drop_duplicates():
            try:
                key=node_id(raw)
                if key not in seen:
                    valid.append(key); seen.add(key)
            except ValueError:
                invalid.append(str(raw))
        for key in valid:
            xyz=nodes.get(key)
            details.append(dict(Painel=str(panel),No=key,X_m=xyz[0] if xyz else None,Y_m=xyz[1] if xyz else None,Z_m=xyz[2] if xyz else None,Apoio=xyz[3] if xyz else '',estado='Encontrado' if xyz else 'Em falta'))
        for key in invalid:
            details.append(dict(Painel=str(panel),No=key,estado='ID inválido'))
        if invalid or not valid or not str(panel).strip() or pd.isna(panel) or str(panel).lower() in ('nan','none'):
            g=dict(nos=len(valid)+len(invalid),nos_em_falta=sum(i not in nodes for i in valid),estado='Identificação incompleta',ids_invalidos=' '.join(invalid))
        else:
            g=panel_geometry(valid,nodes)
        summaries.append(dict(Painel=str(panel),**g,altura_livre_confirmada=False))
    summary=pd.DataFrame(summaries)
    cols=['Painel','estado','nos','nos_em_falta','altura_no_plano_m','largura_horizontal_no_plano_m','desnivel_m','desvio_plano_max_m','inclinacao_sobre_horizontal_graus','azimute_largura_desde_X_graus','z_min_m','z_max_m','nos_com_apoio','ids_em_falta','ids_invalidos','altura_livre_confirmada']
    return summary.reindex(columns=cols),pd.DataFrame(details)


def panel_geometry(ids, nodes, tolerance=.012):
    ids = list(dict.fromkeys(node_id(x) for x in ids))
    missing = [i for i in ids if i not in nodes]
    report = dict(nos=len(ids), nos_em_falta=len(missing))
    if missing:
        return dict(report,estado='Faltam coordenadas', ids_em_falta=' '.join(missing))
    if not ids:
        return dict(report,estado="Sem nós identificados")
    p = np.array([nodes[i][:3] for i in ids])
    report.update(z_min_m=p[:,2].min(), z_max_m=p[:,2].max(), desnivel_m=np.ptp(p[:,2]),
                  nos_com_apoio=sum(bool(nodes[i][3]) for i in ids))
    if len(p)<3:
        return dict(report,estado='Menos de três pontos')
    c = p-p.mean(axis=0)
    _,sv,v = np.linalg.svd(c,full_matrices=False)
    if sv[1] / math.sqrt(len(p)) <= tolerance:
        return dict(report,estado='Nós colineares ou largura insuficiente')
    n = v[-1]
    residual = np.max(np.abs(c@n))
    report.update(desvio_plano_max_m=residual)
    if residual > tolerance:
        return dict(report,estado='Fora da tolerância de planeza')
    up = np.array([0.,0.,1.])-n*n[2]
    slope = np.linalg.norm(up)
    report.update(inclinacao_sobre_horizontal_graus=np.degrees(np.arctan2(slope,abs(n[2]))))
    if slope < .01:
        return dict(report,estado='Quase horizontal: altura de parede indefinida')
    up /= slope
    strike = np.cross(up,n)
    if strike[np.argmax(abs(strike))] < 0:
        strike *= -1
    return dict(report,estado='Plano identificado', altura_no_plano_m=np.ptp(c@up),
                largura_horizontal_no_plano_m=np.ptp(c@strike),
                azimute_largura_desde_X_graus=np.degrees(np.arctan2(strike[1],strike[0]))%180)


def confirmed_restraint_spacing(ids, nodes, lines, tolerance=.012):
    """Explicit confirmed full-width horizontal restraints; return max bay in plane.
    No inference from Support labels or node-cloud alone. Each line specifies
    two end nodes, verified by designer to be continuous lateral restraint.
    """
    ids = list(dict.fromkeys(node_id(i) for i in ids))
    geo = panel_geometry(ids, nodes, tolerance)
    if geo['estado'] != 'Plano identificado':
        raise ValueError('Travamentos exigem geometria plana completa')
    p = np.array([nodes[i][:3] for i in ids]); origin = p.mean(axis=0)
    n = np.linalg.svd(p-origin,full_matrices=False)[2][-1]
    up = np.array([0.,0.,1.])-n*n[2]; up /= np.linalg.norm(up)
    strike = np.cross(up,n)
    u=(p-origin)@strike; v=(p-origin)@up
    levels=[]; seen=set()
    if not isinstance(lines,list) or len(lines)<2:
        raise ValueError('São necessárias pelo menos duas linhas de travamento confirmadas')
    for line in lines:
        if not isinstance(line,dict) or set(line)!={'nos_extremos','justificacao'} or not isinstance(line['justificacao'],str) or not line['justificacao'].strip():
            raise ValueError('Cada travamento exige nos_extremos e justificacao')
        ends=line['nos_extremos']
        if not isinstance(ends,list) or len(ends)!=2:
            raise ValueError('Indicar dois nós extremos por travamento')
        a,b=map(node_id,ends)
        if a==b or a not in ids or b not in ids or frozenset((a,b)) in seen:
            raise ValueError('Nós extremos repetidos ou exteriores ao painel')
        seen.add(frozenset((a,b)))
        q=np.array([nodes[a][:3],nodes[b][:3]])-origin
        x=q@strike; y=q@up
        if np.ptp(y)>tolerance or abs(min(x)-min(u))>tolerance or abs(max(x)-max(u))>tolerance:
            raise ValueError('A linha deve ser horizontal no plano e abranger a largura total')
        levels.append(float(np.mean(y)))
    levels.sort()
    if abs(levels[0]-min(v))>tolerance or abs(levels[-1]-max(v))>tolerance:
        raise ValueError('Travamentos extremos devem coincidir com limites inferior e superior')
    gaps=np.diff(levels)
    if min(gaps)<=2*tolerance:
        raise ValueError('Níveis de travamento coincidentes ou demasiado próximos')
    return {'altura_mm':float(max(gaps)*1000), 'distancias_mm':(gaps*1000).tolist(), 'n_linhas':len(levels)}

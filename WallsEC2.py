# -*- coding: utf-8 -*-
"""
Created on Mon May 19 17:26:04 2025

@author: Engº Lutonda Tomalela

github: https://github.com/lutondatomalela/WallsEC2
"""


import io
import json
import math
import numpy as np
import re
import webbrowser
from datetime import datetime
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from wall_section import Section, nominal_stiffness, gross_face_principal
from wall_auto_stability import slenderness_limit, panel_parameters
from wall_crack_diagnostic import diagnose as diagnose_shell_qp
from wall_shell_capacity import attach as attach_shell_capacity, envelope as shell_capacity_envelope
from wall_physical_layers import attach as attach_physical_layers, summary as physical_layers_summary, refine_mesh as refine_physical_mesh
from wall_shell_screen import attach as attach_shell_screen, envelope as shell_screen_envelope, screen as shell_screen
from wall_case_audit import case_audit
from wall_shear_design import shear_reinforcement_trial, refine_directional_shear_mesh
from wall_coupled_shear import refine_resultant_mesh

import pandas as pd
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

APP_TITLE = "WallsEC2 - Paredes de Betão Armado (EC2)"
APP_NAME = "WallsEC2"
APP_VERSION = "v2.0.0-rc1"
from wall_sandwich_design import attach as attach_sandwich, refine as refine_sandwich
APP_AUTHOR = "Eng.º Lutonda Tomalela"
APP_REPORT_AUTHOR = "https://github.com/lutondatomalela/WallsEC2"
APP_SUBJECT = "Dimensionamento e verificação de paredes de betão armado segundo o Eurocódigo 2"
APP_KEYWORDS = "WallsEC2, Eurocódigo 2, EC2, NP EN 1992-1-1, paredes de betão armado, armaduras, esforço transverso, fendilhação"
APP_CATEGORY = "Structural Engineering / Reinforced Concrete Design"
APP_XLSX_DESCRIPTION = "Workbook de cálculo com dados de entrada, validação, resultados por painel, armaduras, fendilhação, corte e diagnóstico."
GITHUB_URL = "https://github.com/lutondatomalela/WallsEC2"
MAX_PREVIEW_ROWS = 250


# ============================================================
# Utilidades gerais
# ============================================================
def normalize_text(s: str) -> str:
    s = str(s).strip().lower()
    s = s.replace("\u00a0", " ")
    s = re.sub(r"\s+", " ", s)
    return s


def safe_float(value, default=float("nan")):
    try:
        if pd.isna(value):
            return default
        if isinstance(value, (int, float)):
            return float(value)
        s = str(value).strip()
        if not s:
            return default
        s = s.replace("\u00a0", " ").replace(" ", "")
        # Formato PT: 1.234,56
        if re.fullmatch(r"-?\d{1,3}(\.\d{3})+,\d+", s):
            s = s.replace(".", "").replace(",", ".")
        else:
            s = s.replace(",", ".")
        return float(s)
    except Exception:
        return default


def bar_area_mm2(phi_mm: float) -> float:
    return math.pi * phi_mm * phi_mm / 4.0


def parse_strength_from_class(cls: str, default: float = 30.0) -> float:
    m = re.search(r"(\d+(?:[.,]\d+)?)\s*/\s*(\d+(?:[.,]\d+)?)", str(cls))
    if m:
        return float(m.group(1).replace(",", "."))
    m = re.search(r"(\d+(?:[.,]\d+)?)", str(cls))
    if m:
        return float(m.group(1).replace(",", "."))
    return default


def concrete_props(fck: float, alpha_cc: float = 1.0, gamma_c: float = 1.5) -> Dict[str, float]:
    fcm = fck + 8.0
    fcd = alpha_cc * fck / gamma_c
    fctm = 0.30 * fck ** (2.0 / 3.0) if fck <= 50 else 2.12 * math.log(1 + fcm / 10.0)
    return {"fck": fck, "fcm": fcm, "fcd": fcd, "fctm": fctm}


def steel_fyd(fyk: float, gamma_s: float = 1.15) -> float:
    return fyk / gamma_s


# ============================================================
# Importação / limpeza da tabela software de análise estrutural
# ============================================================
COLUMN_ALIASES = {
    "panel_node_case": [
        "panel/node/case", "panel / node / case", "panel/node", "panel node case",
        "object/node/case", "object / node / case", "element/node/case",
        "finite element/node/case", "fe/node/case", "painel/nó/caso", "painel/no/caso"
    ],
    "panel": ["panel", "painel", "object", "element", "finite element", "fe", "objeto", "elemento"],
    "node": ["node", "nó", "no"],
    "case": ["case", "caso", "combination", "combinação", "combinacao"],
    "mxx": ["mxx (knm/m)", "mxx [knm/m]", "mxx", "mx (knm/m)", "mx [knm/m]", "mx"],
    "myy": ["myy (knm/m)", "myy [knm/m]", "myy", "my (knm/m)", "my [knm/m]", "my"],
    "mxy": ["mxy (knm/m)", "mxy [knm/m]", "mxy", "mxyy"],
    # Momentos já transformados para dimensionamento de armadura por Wood-Armer.
    # Nestes casos o programa não volta a aplicar MXY. Usa directamente M+/M- por direcção.
    "mxx_pos_wa": ["mxx+", "mxx +", "mxx+ (w&a)", "mxx+ (&wa)", "mxx+ (knm/m)", "mxx+ (&wa) (knm/m)", "mxx+ (w&a) (knm/m)", "mx+", "mx+ (w&a)", "mx+ (&wa)"],
    "mxx_neg_wa": ["mxx-", "mxx -", "mxx- (w&a)", "mxx- (&wa)", "mxx- (knm/m)", "mxx- (&wa) (knm/m)", "mxx- (w&a) (knm/m)", "mx-", "mx- (w&a)", "mx- (&wa)"],
    "myy_pos_wa": ["myy+", "myy +", "myy+ (w&a)", "myy+ (&wa)", "myy+ (knm/m)", "myy+ (&wa) (knm/m)", "myy+ (w&a) (knm/m)", "my+", "my+ (w&a)", "my+ (&wa)"],
    "myy_neg_wa": ["myy-", "myy -", "myy- (w&a)", "myy- (&wa)", "myy- (knm/m)", "myy- (&wa) (knm/m)", "myy- (w&a) (knm/m)", "my-", "my- (w&a)", "my- (&wa)"],
    # Forças/membrana já transformadas por Wood-Armer. Ficam guardadas para auditoria, mas não entram na verificação global N-M desta versão.
    "nxx_pos_wa": ["nxx+", "nxx+ (w&a)", "nxx+ (&wa)", "nxx+ (kn/m)", "nxx+ (&wa) (kn/m)", "nx+", "nx+ (w&a)", "nx+ (&wa)"],
    "nxx_neg_wa": ["nxx-", "nxx- (w&a)", "nxx- (&wa)", "nxx- (kn/m)", "nxx- (&wa) (kn/m)", "nx-", "nx- (w&a)", "nx- (&wa)"],
    "nyy_pos_wa": ["nyy+", "nyy+ (w&a)", "nyy+ (&wa)", "nyy+ (kn/m)", "nyy+ (&wa) (kn/m)", "ny+", "ny+ (w&a)", "ny+ (&wa)"],
    "nyy_neg_wa": ["nyy-", "nyy- (w&a)", "nyy- (&wa)", "nyy- (kn/m)", "nyy- (&wa) (kn/m)", "ny-", "ny- (w&a)", "ny- (&wa)"],
    "qxx": ["qxx (kn/m)", "qxx [kn/m]", "qxx", "qx (kn/m)", "qx [kn/m]", "qx", "vxx", "vx"],
    "qyy": ["qyy (kn/m)", "qyy [kn/m]", "qyy", "qy (kn/m)", "qy [kn/m]", "qy", "vyy", "vy"],
    "nxx": ["nxx (kn/m)", "nxx [kn/m]", "nxx", "nx (kn/m)", "nx [kn/m]", "nx"],
    "nyy": ["nyy (kn/m)", "nyy [kn/m]", "nyy", "ny (kn/m)", "ny [kn/m]", "ny"],
    "nxy": ["nxy (kn/m)", "nxy [kn/m]", "nxy"],
    "nmises": ["nmises", "nmises (kn/m)", "nmises [kn/m]", "n mises (kn/m)"],
}


def parse_pasted_table(text: str) -> pd.DataFrame:
    text = text.strip()
    if not text:
        return pd.DataFrame()

    # Excel/tabela de cálculo copiado normalmente vem separado por tabs, ponto e vírgula ou barras verticais.
    for sep in ("\t", ";", "|"):
        try:
            df = pd.read_csv(io.StringIO(text), sep=sep, engine="python", dtype=str)
            if len(df.columns) > 1:
                return df
        except Exception:
            pass

    lines = [ln.rstrip() for ln in text.splitlines() if ln.strip()]
    if len(lines) < 2:
        return pd.DataFrame()

    #leitura robusta para tabelas copiadas do software de análise estrutural com espaços simples, por exemplo:
    # 43/ 49/ 302 (CQC) -2,17 -0,13 0,83 43 5,59 3,69
    #também aceita tabelas de momentos já transformados para armadura (W&A), com colunas MXX+/MXX-/MYY+/MYY-
    header_norm = normalize_text(lines[0]) if lines else ""
    header_has_wa_moments = all(k in header_norm for k in ["mxx+", "mxx-", "myy+", "myy-"])
    robot_rows = []
    row_re = re.compile(
        r"^\s*(?P<panel>\S+)\s*/\s*(?P<node>\S+)\s*/\s*(?P<case>\d+)\s*"
        r"(?P<casetype>\([^)]*\))?\s+(?P<rest>.*)$"
    )
    num_re = re.compile(r"[-+]?\d+(?:[\.,]\d+)?")
    for ln in lines[1:]:
        m = row_re.match(ln)
        if not m:
            robot_rows = []
            break
        nums = num_re.findall(m.group("rest"))
        case_txt = m.group("case")
        if m.group("casetype"):
            case_txt = f"{case_txt} {m.group('casetype').strip()}"

        if header_has_wa_moments and len(nums) >= 4:
            # Esperado: MXX+, MXX-, MYY+, MYY- [, NXX-, NYY-, NXX+, NYY+].
            row = {
                "panel_node_case": f"{m.group('panel')}/{m.group('node')}/{case_txt}",
                "panel": m.group("panel"),
                "node": m.group("node"),
                "case": case_txt,
                "mxx_pos_wa": nums[0],
                "mxx_neg_wa": nums[1],
                "myy_pos_wa": nums[2],
                "myy_neg_wa": nums[3],
            }
            if len(nums) >= 8:
                row.update({
                    "nxx_neg_wa": nums[4],
                    "nyy_neg_wa": nums[5],
                    "nxx_pos_wa": nums[6],
                    "nyy_pos_wa": nums[7],
                })
            robot_rows.append(row)
            continue

        # Esperado: MXX, MYY, MXY, Panel, QXX, QYY. Em algumas tabelas o Panel repetido pode faltar.
        if len(nums) >= 6:
            mxx, myy, mxy, panel_rep, qxx, qyy = nums[:6]
        elif len(nums) >= 5:
            mxx, myy, mxy, qxx, qyy = nums[:5]
            panel_rep = m.group("panel")
        else:
            robot_rows = []
            break
        robot_rows.append({
            "panel_node_case": f"{m.group('panel')}/{m.group('node')}/{case_txt}",
            "panel": panel_rep,
            "node": m.group("node"),
            "case": case_txt,
            "mxx": mxx,
            "myy": myy,
            "mxy": mxy,
            "qxx": qxx,
            "qyy": qyy,
        })
    if robot_rows:
        return pd.DataFrame(robot_rows)

    # Fallback para espaços múltiplos.
    rows = [re.split(r"\s{2,}", ln.strip()) for ln in lines]
    header = rows[0]
    body = rows[1:]
    width = len(header)
    body = [r[:width] + [""] * max(0, width - len(r)) for r in body]
    return pd.DataFrame(body, columns=header)



def read_csv_robust(path: str) -> pd.DataFrame:
    """Leitura robusta de CSV exportado por folhas de cálculo ou software de análise.

    Tenta automaticamente encoding e separador. Mantém tudo como texto para preservar
    vírgulas decimais; a conversão numérica é feita depois por safe_float().
    """
    with open(path, "rb") as stream:
        prefix = stream.read(4)
    if prefix.startswith((b"\xff\xfe", b"\xfe\xff")):
        encodings = ["utf-16"]
    else:
        encodings = ["utf-8-sig", "utf-8", "cp1252", "latin1"]
    attempts = []
    for enc in encodings:
        # sep=None usa o detector do pandas; depois tenta separadores explícitos.
        for sep in [None, ";", ",", "\t", "|"]:
            try:
                kwargs = {"dtype": str, "encoding": enc, "engine": "python"}
                if sep is None:
                    kwargs["sep"] = None
                else:
                    kwargs["sep"] = sep
                df = pd.read_csv(path, **kwargs)
                # Aceita a primeira leitura com mais de uma coluna ou, no mínimo, dados.
                if df is not None and not df.empty and len(df.columns) > 1 and not any("\x00" in str(c) for c in df.columns):
                    return df
                attempts.append((enc, sep, len(df.columns) if df is not None else 0))
            except Exception as exc:
                attempts.append((enc, sep, str(exc)[:80]))
    # último fallback: lê o texto e usa o parser de colagem.
    for enc in encodings:
        try:
            with open(path, "r", encoding=enc, errors="ignore") as f:
                txt = f.read()
            df = parse_pasted_table(txt)
            if df is not None and not df.empty:
                return df
        except Exception:
            pass
    raise ValueError("Não foi possível importar o CSV. Confirmar se o ficheiro não está vazio e se usa separador ;, vírgula, tabulação ou |.")

def rename_known_columns(df: pd.DataFrame) -> pd.DataFrame:
    norm_to_original = {normalize_text(c): c for c in df.columns}
    rename_map = {}
    for target, aliases in COLUMN_ALIASES.items():
        for alias in aliases:
            if alias in norm_to_original:
                rename_map[norm_to_original[alias]] = target
                break
    # fallback: remove units/brackets and retry, useful for softwares de análise estrutural tables with headers like MXX [kNm/m]. (otimizado pra utilizar com o robot structural anaysis)
    for original in df.columns:
        if original in rename_map:
            continue
        simplified = normalize_text(re.sub(r"[\[\(].*?[\]\)]", "", str(original)))
        for target, aliases in COLUMN_ALIASES.items():
            if target in rename_map.values():
                continue
            if simplified in [normalize_text(re.sub(r"[\[\(].*?[\]\)]", "", a)) for a in aliases]:
                rename_map[original] = target
                break
    return df.rename(columns=rename_map).copy()


def split_panel_node_case(s: str) -> Tuple[str, str, str]:
    parts = [p.strip() for p in str(s).split("/")]
    panel = parts[0] if len(parts) > 0 else ""
    node = parts[1] if len(parts) > 1 else ""
    case = parts[2] if len(parts) > 2 else ""
    panel = re.sub(r"\*+$", "", panel).strip()
    node = re.sub(r"\*+$", "", node).strip()
    return panel, node, case


def canonical_case_id(value: object) -> str:
    """Extrai o número do caso/combinação, ignorando textos como (C), (CQC)."""
    txt = normalize_text(str(value))
    txt = txt.replace("case", "").replace("caso", "").replace("comb.", "").replace("comb", "")
    m = re.search(r"\d+", txt)
    return m.group(0) if m else txt.strip()


def clean_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    df = rename_known_columns(df).reset_index(drop=True)
    df["__row_order"] = range(len(df))

    if "panel_node_case" in df.columns:
        vals = df["panel_node_case"].map(split_panel_node_case)
        df["panel_from_id"] = vals.map(lambda x: x[0])
        if "node" not in df.columns:
            df["node"] = vals.map(lambda x: x[1])
        if "case" not in df.columns:
            df["case"] = vals.map(lambda x: x[2])
    else:
        df["panel_from_id"] = ""
        if "node" not in df.columns:
            df["node"] = ""
        if "case" not in df.columns:
            df["case"] = ""

    if "panel" not in df.columns:
        df["panel"] = df["panel_from_id"]
    df["panel"] = df["panel"].astype(str).replace("nan", "")
    df.loc[df["panel"].str.strip() == "", "panel"] = df["panel_from_id"]
    if "case" in df.columns:
        df["case_id"] = df["case"].map(canonical_case_id)

    numeric_cols = [
        "mxx", "myy", "mxy", "qxx", "qyy", "nxx", "nyy", "nxy", "nmises",
        "mxx_pos_wa", "mxx_neg_wa", "myy_pos_wa", "myy_neg_wa",
        "nxx_pos_wa", "nxx_neg_wa", "nyy_pos_wa", "nyy_neg_wa",
    ]
    for c in numeric_cols:
        missing = c not in df.columns
        df[f"__missing_{c}"] = bool(missing)
        if missing:
            df[c] = 0.0
        values = df[c].map(safe_float)
        if not missing and not values.map(math.isfinite).all():
            bad = list(df.index[~values.map(math.isfinite)][:10])
            raise ValueError(f"Valores ausentes/não finitos na coluna {c}, linhas {bad}")
        df[c] = values

    return df


def combine_effort_tables(tables):
    """Junta tabelas complementares pela mesma identidade painel/nó/caso.

    Sem somar esforços ou juntar registos por posição. Recusa chaves diferentes,
    duplicadas, unidades incompatíveis e sobreposições em conflito.
    """
    if not tables:
        raise ValueError("Seleccionar pelo menos uma tabela")
    work = []
    header_units = {"moment": set(), "force": set()}
    for table in tables:
        for column in table.columns:
            header = normalize_text(column).replace(" ", "")
            if header.startswith(("mxx", "myy", "mxy")):
                for unit in ("knmm/m", "nmm/mm", "knm/m", "nm/m"):
                    if unit in header:
                        header_units["moment"].add(moment_unit_factor_to_kNm_per_m(unit))
                        break
            elif header.startswith(("nxx", "nyy", "nxy", "nmises", "qxx", "qyy")):
                for unit in ("kn/m", "n/mm", "n/m"):
                    if unit in header:
                        header_units["force"].add(shear_unit_factor_to_kN_per_m(unit))
                        break
        if any(len(values) > 1 for values in header_units.values()):
            raise ValueError("Unidades incompatíveis entre tabelas; converter antes da junção")
        original = rename_known_columns(table)
        checked = clean_dataframe(table)
        if checked.empty:
            raise ValueError("Tabela de esforços vazia")
        keys = pd.MultiIndex.from_arrays([checked["panel"].astype(str).str.strip(),
            checked["node"].astype(str).str.strip(), checked["case_id"].astype(str).str.strip()],
            names=["panel", "node", "case_id"])
        if any((checked[c].astype(str).str.strip() == "").any() for c in ("panel", "node", "case_id")):
            raise ValueError("A junção exige painel, nó e número de caso em todas as linhas")
        if keys.has_duplicates:
            raise ValueError("Chaves painel/nó/caso duplicadas; não é possível juntar sem ambiguidade")
        original.index = keys
        work.append(original)
    combined = work[0].copy()
    id_cols = {"panel_node_case", "panel", "node", "case", "case_id", "panel_from_id"}
    numeric_cols = set(COLUMN_ALIASES) - id_cols
    for other in work[1:]:
        absent = combined.index.difference(other.index)
        extra = other.index.difference(combined.index)
        if len(absent) or len(extra):
            raise ValueError(f"Tabelas não coincidentes: {len(absent)} chaves em falta e {len(extra)} adicionais. Não foram associadas linhas de painéis/nós/casos diferentes.")
        other = other.reindex(combined.index)
        for col in other.columns:
            if col in combined.columns:
                if col in numeric_cols:
                    left = combined[col].map(safe_float)
                    right = other[col].map(safe_float)
                    if not ((left-right).abs() <= 1e-9).all():
                        raise ValueError(f"Valores em conflito na coluna {col}")
                continue
            combined[col] = other[col]
    combined = combined.reset_index(drop=True)
    combined["source_tables_count"] = len(tables)
    return combined


def reduce_to_governing_cases(df: pd.DataFrame) -> pd.DataFrame:
    if df is None or df.empty:
        return df
    # Não descartar combinações por máximos de componentes: o caso governante
    # depende de MXY, face, armadura adoptada e ELS. Preservar rastreabilidade.
    return df.copy().reset_index(drop=True)


# ============================================================
# Dimensionamento EC2 simplificado para parede como elemento de placa
# ============================================================
@dataclass
class RebarSolution:
    phi: float
    spacing: float
    as_prov: float
    text_override: str = ""
    base_text: str = ""
    add_text: str = ""
    as_base: float = 0.0
    as_add: float = 0.0
    optimization_note: str = ""
    n_iterations: int = 0

    @property
    def text(self) -> str:
        if self.text_override:
            return self.text_override
        return f"Ø{int(self.phi)}//{int(self.spacing)}"


def moment_unit_factor_to_kNm_per_m(unit: str) -> float:
    u = normalize_text(unit)
    if "nmm/mm" in u:
        return 0.001
    if "nm/m" in u and "kn" not in u:
        return 0.001
    if "knmm/m" in u:
        return 0.001
    if "knm/m" in u or "kn.m/m" in u or "kn·m/m" in u:
        return 1.0
    raise ValueError(f"Unidade de momento desconhecida: {unit}")


def shear_unit_factor_to_kN_per_m(unit: str) -> float:
    u = normalize_text(unit)
    if "n/mm" in u:
        return 1.0
    if "n/m" in u and "kn" not in u:
        return 0.001
    if "kn/m" in u:
        return 1.0
    raise ValueError(f"Unidade de esforço desconhecida: {unit}")


def ec2_final_creep(fck, rh, h0, adjusted_age):
    """EC2 Annex B, final coefficient (t tends to infinity)."""
    if not all(math.isfinite(x) for x in (fck, rh, h0, adjusted_age)) or not (
        12 <= fck <= 90 and 0 < rh <= 100 and h0 > 0 and adjusted_age >= 0.5
    ):
        raise ValueError("Confirmar fck, humidade, h0 e idade ajustada (mínimo 0,5 dias).")
    fcm = fck + 8
    humidity = (1-rh/100)/(0.1*h0**(1/3))
    phi_rh = 1+humidity if fcm <= 35 else (1+humidity*(35/fcm)**0.7)*(35/fcm)**0.2
    return phi_rh * (16.8/math.sqrt(fcm))/(0.1+adjusted_age**0.20)


def parse_case_set(text):
    out = set()
    for token in str(text).replace(",", " ").replace(";", " ").split():
        match = re.fullmatch(r"(\d+)(?:[-–](\d+))?", token)
        if not match:
            raise ValueError(f"Combinação/intervalo inválido: {token}")
        a = int(match.group(1)); b = int(match.group(2) or a)
        if b < a or b - a > 100000:
            raise ValueError("Intervalo de combinações inválido")
        out.update(str(i) for i in range(a, b+1))
    return out


def format_case_ranges(values):
    ids=sorted({int(x) for x in values if str(x).isdigit()})
    spans=[]
    for n in ids:
        if spans and n==spans[-1][1]+1:spans[-1][1]=n
        else:spans.append([n,n])
    return ", ".join(str(a) if a==b else f"{a}–{b}" for a,b in spans)


def compact_panel_reason(value):
    # Keep the critical cause; summarise repeated review conditions only.
    result=[]
    for part in value.split("; "):
        for needle,label in (("condições da secção 6.109","Campos comprimidos (6.109)"),("transferência adicional LL.115","Corte intercamadas [LL(115)(c)]"),("sandwich de primeira ordem","Amarração/2.ª ordem"),("combinações modais","Sinais modais"),("ELS CAR/FREQ parciais","ELS tensões"),("limite conservador de triagem",""),("confirmar amarração e efeitos acoplados",""),("ELS: ","ELS cargas*"),("confirmar coacção/histórico","")):
            if needle in part:
                if label:result.append(label)
                break
        else:result.append(part)
    return "; ".join(dict.fromkeys(result))



ENGINEERING_LABELS = {
    'panel':'Painel','node':'Nó','case':'Combinação','Combo_type':'Tipo de combinação',
    'NXX_kN_m':'Nxx [kN/m]','NYY_kN_m':'Nyy [kN/m]','NXY_kN_m':'Nxy [kN/m]',
    'Sand_util':'η sandwich','Sand_status':'Estado sandwich','ELS_cargas_estado':'ELS — cargas','ELS_72_estado':'Tensões ELS','Status':'Estado',
    'Panel':'Painel','Node':'Nó','Case':'Combinação','Status_global':'Estado seccional','ELU_faixas':'ELU por faixa',
    'ELU_modelo':'ELU calculado','ELS_cargas':'ELS — cargas','ELS_tensoes':'Tensões ELS (7.2)','Sand_transfer_reserve_min':'Reserva de corte [kN/m]','Segunda_ordem_faixas':'2.ª ordem — faixas',
    'Compressao_faces':'Resistência dos campos comprimidos','Transferencia_faces':'Corte adicional por transferência intercamadas',
    'Estabilidade_global_externa':'Estabilidade global externa','Motivo_estado':'Condições por confirmar',
    'util_max':'η faixa','Sand_util_max':'η sandwich','Sand_util_1ordem_max':'η sandwich (1.ª ordem)',
    'Sand_linhas_acima_1':'Linhas η > 1','wk_QP_avaliadas':'QP com wₖ calculado','wk_cargas_cond_QP':'QP sem fendas por cargas*',
    'wk_QP_total':'QP total','caso_governante':'Comb. gov. (faixa)','node_governante':'Nó gov. (faixa)',
    'Auto_l0_x':'l₀,x [mm]','Auto_l0_y':'l₀,y [mm]','Auto_h0':'h₀ [mm]','Auto_phi_final':'φ∞',
    'Auto_phi_x':'φef,x','Auto_phi_y':'φef,y','Stability_l0_mm':'l₀ [mm]','Stability_phi_eff':'φef',
    'Sand_steel_util_max':'η aço','Sand_concrete_util_max':'η betão','Sand_shear_util_max':'η corte',
    'Sand_Asw_req_max_mm2_m2':'Aₛw,req [mm²/m²]','Sand_no_governante':'Nó gov.','Sand_caso_governante':'Comb. gov.',
    'Sand_linhas_sem_resultado':'Sem resultado','Sand_linhas_trelica':'Com Aₛw proposta',
    'Sand_intact_linhas':'Linhas LL(107) satisfeitas*','Sand_intact_phi_max':'Φ sup.','Sand_intact_util_max':'η betão (elástico)','Sand_intact_t_max':'σt sup. [MPa]','Sand_intact_fctd':'fctd [MPa]',
    'Sand_2ordem_pendente':'Linhas com incrementos de faixa pendentes','Sand_delta_Mx_max':'ΔMx [kNm/m]','Sand_delta_My_max':'ΔMy [kNm/m]',
    'wk_max_mm':'wₖ,máx [mm]','wk_cargas_cond_mm':'w por cargas* [mm]','wmax_mm':'wlim [mm]',
    'ELS_historico_ratio':'σt/fctk,0.05','Crack_control_status':'Estado ELS', 'Transverse_links':'Aₛv > 2% A꜀',
    'MXX_kNm_m':'Mxx [kNm/m]','MYY_kNm_m':'Myy [kNm/m]','MXY_kNm_m':'Mxy [kNm/m]',
    'QXX_kN_m':'Qx [kN/m]','QYY_kN_m':'Qy [kN/m]','Croquis_textual':'Armaduras por face','Nota_desenho':'Nota de desenho',
    'Optimization_mode':'Estratégia','governing_case':'Comb. gov. ELU',
}
for _face in ('X+','X-','Y+','Y-'):
    for _key,_caption in (('adopted','Adotada'),('base','Base'),('additional','Reforço'),('rebar','Adotada')):
        ENGINEERING_LABELS[f'{_face}_{_key}']=f'{_face} — {_caption}'
    ENGINEERING_LABELS[f'wk_{_face.lower()}_mm']=f'wₖ {_face} [mm]'


def engineering_label(key):
    return ENGINEERING_LABELS.get(key,key)


def panel_scope_fields(g):
    """Separate evaluated limits from the scope of outstanding checks."""
    e=g[g.Combo_type.eq('ELU')];q=g[g.Combo_type.eq('ELS-QP')]
    sandwich='Sand_status' in e
    # Never convert numerical screening into an overall compliance statement.
    u=e.get('Sand_util',pd.Series(dtype=float)) if sandwich else e.util_max
    local_bad=e.util_max.gt(1).any() or e.Status.eq('Não conforme').any()
    if local_bad:el='Limite local excedido'
    elif e.empty or u.isna().any() or e.util_max.isna().any():el='Sem resultado completo'
    elif u.gt(1+1e-7).any():el='Limite sandwich excedido'
    else:el='Limites calculados satisfeitos'
    qp_known=q.wk_max_mm.notna();qp_cond=q.get('wk_cargas_cond_mm',pd.Series(index=q.index,dtype=float)).eq(0)
    if q.empty:els='Sem QP' if g.get("wk_check_enabled",pd.Series(dtype=str)).eq("Sim").any() else 'Não selecionada'
    elif q.wk_max_mm.gt(q.wmax_mm).any() or q.get('wk_partial_max_mm',pd.Series(index=q.index,dtype=float)).gt(q.wmax_mm).any():els='Limite excedido'
    elif qp_known.all():els='wₖ calculado'
    elif (qp_known|qp_cond).all():els='Sem fendas por cargas*' if qp_cond.all() else 'Avaliação mista*'
    else:els=f'{int((qp_known|qp_cond).sum())}/{len(q)} QP avaliadas*'
    st=pd.concat([e.get(f'Stability_{a}_status',pd.Series(dtype=str)) for a in 'XY']).astype(str)
    if st.empty or st.str.contains('Pendente|Não avaliado',regex=True).any():so='Dados pendentes'
    elif st.str.contains('Instável',regex=False).any():so='Instabilidade na faixa'
    elif st.str.startswith('Incluída').any():so='Incluída'
    elif st.str.startswith(('Dispensada','Não requerida')).all():so='Dispensada'
    else:so='A confirmar'
    # Missing local increments remain pending; no independent shell-stability verdict.
    pend=e.get('Sand_strip_order_status',pd.Series(dtype=str)).eq('Dados locais pendentes')
    intact=e.get('Sand_intact_candidate',pd.Series(False,index=e.index)).eq(True)
    all_intact=not e.empty and intact.all()
    if all_intact and not local_bad and u.notna().all() and e.util_max.notna().all():el='Via elástica satisfeita*'
    stress=g[g.Combo_type.isin(['ELS-CAR','ELS-QP'])].get('ELS_72_estado',pd.Series(dtype=str))
    stress_ok=not stress.empty and stress.str.startswith('Limites satisfeitos').all()
    return dict(ELU_modelo=el,ELS_cargas=els,ELS_tensoes='Limites satisfeitos*' if stress_ok else 'Por verificar' if not stress.empty else 'Não avaliado',
        Sand_transfer_reserve_min=e.get('Sand_transfer_reserve_kN_m',pd.Series(dtype=float)).min(),Segunda_ordem_faixas=so,
        Sand_intact_linhas=int(intact.sum()),Sand_intact_phi_max=e.get('Sand_intact_phi_upper',pd.Series(dtype=float)).max(),
        Sand_intact_util_max=e.get('Sand_intact_util',pd.Series(dtype=float)).max(),Sand_intact_t_max=e.get('Sand_intact_sigma_t_upper_MPa',pd.Series(dtype=float)).max(),
        Sand_intact_fctd=e.get('Sand_intact_fctd_MPa',pd.Series(dtype=float)).max(),
        Compressao_faces=('Via elástica condicional' if all_intact else 'Não demonstrada' if e.loc[~intact].get('Sand_status',pd.Series(dtype=str)).str.contains('6.109 não demonstrado',regex=False,na=False).any() else 'Critério aplicado') if sandwich else 'Não avaliada',
        Transferencia_faces=('Dispensável se secção íntegra' if all_intact else 'Verificação complementar requerida' if e.loc[~intact].get('Sand_transfer_status',pd.Series(dtype=str)).str.startswith('LL.115',na=False).any() else 'Sem correção local') if sandwich else 'Não avaliada',
        Sand_2ordem_pendente=int(pend.sum()),Sand_util_1ordem_max=e.get('Sand_util_first_order',pd.Series(dtype=float)).max(),
        Sand_delta_Mx_max=e.get('Sand_delta_Mx_kNm_m',pd.Series(dtype=float)).max(),Sand_delta_My_max=e.get('Sand_delta_My_kNm_m',pd.Series(dtype=float)).max())

def status_rank(status: str) -> int:
    order = {"OK": 0, "OK*": 1, "Verificar": 2, "Dados insuficientes": 3, "Não conforme": 4}
    return order.get(str(status), 2)


class WallDesigner:
    def __init__(
        self,
        thickness_mm: float,
        cover_mm: float,
        concrete_class: str,
        fyk: float,
        gamma_c: float = 1.5,
        gamma_s: float = 1.15,
        alpha_cc: float = 1.0,
        local_y_is_vertical: bool = True,
        aggregate_mm: float = 20.0,
        crack_spacing_limit_mm: Optional[float] = None,
        wood_armer_method: str = "Conservativo |MXY|",
        swap_local_axes: bool = False,
        crack_check_enabled: bool = True,
        wk_check_enabled: bool = False,
        qp_case: str = "",
        moment_unit: str = "kNm/m",
        shear_unit: str = "kN/m",
        combo_type: str = "ELU",
        wmax_mm: float = 0.30,
        phi_min_mm: float = 8.0,
        phi_max_mm: float = 16.0,
        optimize_rebar: bool = False,
        rebar_strategy: str = "Base + reforços",
        base_vertical_phi: float = 10.0,
        base_vertical_spacing: float = 200.0,
        base_horizontal_phi: float = 8.0,
        base_horizontal_spacing: float = 200.0,
        elu_cases: str = "",
        axial_convention: str = "Não definida",
        effective_length_mm: float = 0.0,
        creep_effective: float = 0.0,
        steel_ultimate_strain: float = 0.01,
        characteristic_cases: str = "",
        frequent_cases: str = "",
    ):
        for name, value in {"espessura": thickness_mm, "fyk": fyk,
                            "gamma_c": gamma_c, "gamma_s": gamma_s,
                            "alpha_cc": alpha_cc, "wmax": wmax_mm}.items():
            if not math.isfinite(value) or value <= 0:
                raise ValueError(f"{name} deve ser positivo e finito")
        if not math.isfinite(cover_mm) or cover_mm < 0 or 2 * (cover_mm + 1.5 * phi_max_mm) >= thickness_mm:
            raise ValueError("Espessura insuficiente para duas faces e duas direcções de armadura")
        if not math.isfinite(aggregate_mm) or aggregate_mm < 0:
            raise ValueError("Dimensão do agregado inválida")
        self.elu_cases = parse_case_set(elu_cases)
        self.characteristic_cases = parse_case_set(characteristic_cases)
        self.frequent_cases = parse_case_set(frequent_cases)
        groups = (self.elu_cases, self.characteristic_cases, self.frequent_cases,
                  {canonical_case_id(qp_case)} if qp_case else set())
        if sum(map(len, groups)) != len(set().union(*groups)):
            raise ValueError("Uma combinação não pode pertencer a dois grupos ELU/ELS")
        if canonical_case_id(qp_case) in self.elu_cases:
            raise ValueError("A combinação QP não pode pertencer ao conjunto ELU")
        if axial_convention not in ("Não definida", "Compressão positiva", "Tracção positiva"):
            raise ValueError("Convenção de esforço normal inválida")
        if not math.isfinite(effective_length_mm) or effective_length_mm < 0 or not math.isfinite(creep_effective) or creep_effective < 0:
            raise ValueError("Comprimento efectivo/fluência inválido")
        if not math.isfinite(steel_ultimate_strain) or not fyk / gamma_s / 200000 < steel_ultimate_strain <= .05:
            raise ValueError("Extensão última de cálculo do aço inválida")
        self.axial_convention = axial_convention
        self.effective_length_mm = effective_length_mm
        self.creep_effective = creep_effective
        self.auto_stability = None
        self.stability_params = None
        self.shell_qp_diagnostic = False
        self.sandwich_design = False  # legacy API compatibility; GUI uses sandwich
        self.steel_ultimate_strain = steel_ultimate_strain
        self.gamma_c = gamma_c
        self.t = thickness_mm
        self.cover = cover_mm
        if not re.fullmatch(r"C\d+(?:[.,]\d+)?/\d+(?:[.,]\d+)?", str(concrete_class).strip(), re.IGNORECASE):
            raise ValueError("Classe de betão inválida; indicar Cxx/yy")
        self.fck = parse_strength_from_class(concrete_class, 30.0)
        if not 12.0 <= self.fck <= 90.0:
            raise ValueError("Classe de betão fora do âmbito C12/15 a C90/105")
        self.cp = concrete_props(self.fck, alpha_cc=alpha_cc, gamma_c=gamma_c)
        self.fyd = steel_fyd(fyk, gamma_s)
        self.fyk = fyk
        self.local_y_is_vertical = local_y_is_vertical
        self.aggregate_mm = aggregate_mm
        self.crack_spacing_limit_mm = crack_spacing_limit_mm
        self.wood_armer_method = wood_armer_method
        self.swap_local_axes = swap_local_axes
        self.crack_check_enabled = crack_check_enabled
        self.wk_check_enabled = wk_check_enabled
        self.qp_case = str(qp_case).strip()
        self.moment_unit = moment_unit
        self.shear_unit = shear_unit
        self.moment_factor = moment_unit_factor_to_kNm_per_m(moment_unit)
        self.shear_factor = shear_unit_factor_to_kN_per_m(shear_unit)
        self.combo_type = combo_type
        self.wmax_mm = wmax_mm
        base_phi = [8.0, 10.0, 12.0, 16.0, 20.0, 25.0]
        self.phi_candidates = [p for p in base_phi if phi_min_mm <= p <= phi_max_mm]
        if not self.phi_candidates:
            raise ValueError("Intervalo de diâmetros sem varões disponíveis")
        self.spacing_candidates = [75.0, 100.0, 125.0, 150.0, 175.0, 200.0, 225.0, 250.0, 300.0, 350.0, 400.0]
        self.optimize_rebar = bool(optimize_rebar)
        self.rebar_strategy = str(rebar_strategy)
        self.base_vertical_phi = float(base_vertical_phi)
        self.base_vertical_spacing = float(base_vertical_spacing)
        self.base_horizontal_phi = float(base_horizontal_phi)
        self.base_horizontal_spacing = float(base_horizontal_spacing)

    @property
    def ac_per_m(self) -> float:
        return 1000.0 * self.t

    def min_wall_reinf_total(self) -> Tuple[float, float, float]:
        """Retorna mínimos totais por metro: vertical, horizontal e máximo vertical."""
        ac = self.ac_per_m
        # EC2 9.6.2: As,vmin recomendado = 0,002 Ac; As,vmax recomendado = 0,04 Ac.
        asv_min = 0.002 * ac
        asv_max = 0.04 * ac
        # EC2 9.6.3: As,hmin >= max(25% da armadura vertical; 0,001 Ac).
        ash_min = max(0.25 * asv_min, 0.001 * ac)
        return asv_min, ash_min, asv_max

    def slab_flexural_min_per_face(self, phi: float = 12.0) -> float:
        """Mínimo de flexão tipo laje/faixa de 1 m: EC2 9.3.1.1."""
        d = self.effective_depth(phi)
        return max(0.26 * self.cp["fctm"] / self.fyk * 1000.0 * d, 0.0013 * 1000.0 * d)

    def max_spacing_for_direction(self, is_vertical_direction: bool) -> float:
        # EC2 9.6.2: varões verticais <= min(3t, 400 mm).
        # EC2 9.6.3: varões horizontais <= 400 mm.
        base = min(3.0 * self.t, 400.0) if is_vertical_direction else 400.0
        if self.crack_spacing_limit_mm and self.crack_spacing_limit_mm > 0:
            base = min(base, self.crack_spacing_limit_mm)
        return base

    def effective_depth(self, phi: float = 12.0) -> float:
        # Armadura numa face, flexão transversal da parede/laje.
        # Reserva conservativa da camada ortogonal exterior de cada face.
        return self.t - self.cover - max(self.phi_candidates) - phi / 2.0

    def flexural_as_required(self, m_ed_kNm_per_m: float, phi_assumed: float = 12.0) -> float:
        """As requerido por metro de largura, mm2/m, para flexão simples de faixa de 1 m."""
        m = abs(m_ed_kNm_per_m) * 1e6  # Nmm/m
        if m <= 1e-9:
            return 0.0
        d = self.effective_depth(max(self.phi_candidates))
        # Bloco rectangular EC2 3.1.7, conservador para flexão simples.
        eta = 1.0 if self.fck <= 50 else 1.0 - (self.fck - 50.0) / 200.0
        capacity = eta * 1000.0 * self.cp["fcd"]
        discriminant = d * d - 2.0 * m / capacity
        if discriminant <= 0:
            raise ValueError("Momento excede domínio de flexão simples; rever secção")
        z = 0.5 * (d + math.sqrt(discriminant))
        return m / (self.fyd * z)

    def mrd_kNm_per_m(self, as_mm2_per_m: float, phi: float) -> float:
        d = self.effective_depth(phi)
        eta = 1.0 if self.fck <= 50 else 1.0 - (self.fck - 50.0) / 200.0
        lam = 0.8 if self.fck <= 50 else 0.8 - (self.fck - 50.0) / 400.0
        x = as_mm2_per_m * self.fyd / (lam * eta * 1000.0 * self.cp["fcd"])
        # Limite declarado deste motor de flexão simples (sem armadura comprimida).
        if x > 0.45 * d:
            return 0.0
        return as_mm2_per_m * self.fyd * (d - 0.5 * lam * x) / 1e6

    def choose_rebar(self, as_req_per_face: float, max_spacing: float = 400.0) -> RebarSolution:
        best = None
        for phi in self.phi_candidates:
            for s in self.spacing_candidates:
                if s > max_spacing + 1e-9:
                    continue
                clear = s - phi
                min_clear = max(phi, self.aggregate_mm + 5.0, 20.0)
                if clear < min_clear:
                    continue
                as_prov = bar_area_mm2(phi) * 1000.0 / s
                if as_prov + 1e-9 >= as_req_per_face:
                    cand = RebarSolution(phi=phi, spacing=s, as_prov=as_prov)
                    excess = cand.as_prov / max(as_req_per_face, 1.0)
                    # Engenharia prática: evita espaçamentos <100 mm, evita Ø20/Ø25 quando não necessários,
                    # e minimiza excesso de aço sem penalizar demasiado soluções correntes Ø10/Ø12.
                    penalty_spacing = 0 if cand.spacing >= 100.0 else 10
                    penalty_large_phi = max(0.0, cand.phi - 16.0) / 10.0
                    penalty_preferred = 0 if cand.phi in (8.0, 10.0, 12.0, 16.0) else 1
                    key = (penalty_spacing, penalty_large_phi, excess, cand.as_prov, penalty_preferred, cand.phi, -cand.spacing)
                    if best is None:
                        best = cand
                        best_key = key
                    elif key < best_key:
                        best = cand
                        best_key = key
        if best is None:
            raise ValueError("Sem armadura exequível dentro dos diâmetros/espaçamentos definidos")
        return best

    def rebar_from_phi_spacing(self, phi: float, spacing: float) -> RebarSolution:
        phi = float(phi)
        spacing = float(spacing)
        if phi <= 0 or spacing <= 0:
            return RebarSolution(0.0, 1e9, 0.0, text_override="-")
        return RebarSolution(phi, spacing, bar_area_mm2(phi) * 1000.0 / spacing)

    def base_solution_for_direction(self, is_vertical_direction: bool) -> RebarSolution:
        if is_vertical_direction:
            return self.rebar_from_phi_spacing(self.base_vertical_phi, self.base_vertical_spacing)
        return self.rebar_from_phi_spacing(self.base_horizontal_phi, self.base_horizontal_spacing)

    def base_solution_is_valid(self, sol: RebarSolution, max_spacing: float) -> Tuple[bool, str]:
        if sol.phi not in self.phi_candidates or sol.spacing <= 0:
            return False, "armadura base não definida"
        if sol.spacing > max_spacing + 1e-9:
            return False, f"espaçamento base {sol.spacing:.0f} mm > smax {max_spacing:.0f} mm"
        clear = sol.spacing - sol.phi
        min_clear = max(sol.phi, self.aggregate_mm + 5.0, 20.0)
        if clear < min_clear:
            return False, f"distância livre base insuficiente ({clear:.0f} mm < {min_clear:.0f} mm)"
        return True, "armadura base válida"

    def choose_compatible_additional_rebar(self, deficit_as: float, base: RebarSolution, max_spacing: float) -> RebarSolution:
        """Escolhe reforço coerente com a malha base.

        Regra de projecto adoptada nesta versão:
        - o reforço adicional mantém o mesmo espaçamento da armadura base;
        - evita soluções do tipo Ø10//200 + Ø8//150, que são pouco coerentes em desenho/obra;
        - se uma única família adicional não for suficiente, admite 2 ou 3 famílias iguais, sempre com o mesmo espaçamento da base.

        Exemplo: base Ø10//200 + adicional Ø8//200. Na prática, as duas famílias podem ser intercaladas,
        resultando numa distância alternada próxima de 100 mm entre varões.
        """
        s = float(base.spacing)
        if s <= 0 or s > max_spacing + 1e-9:
            return self.choose_rebar(deficit_as, max_spacing=max_spacing)

        candidates = []
        for n_layers in (1, 2, 3):
            for phi in self.phi_candidates:
                # Distância livre aproximada entre varões intercalados da base e do reforço.
                # Se houver várias famílias adicionais, o espaçamento real fica ainda mais apertado,
                # pelo que se usa s/(n_layers+1) como aproximação conservativa.
                equivalent_spacing = s / (n_layers + 1)
                clear_between_families = equivalent_spacing - max(phi, base.phi)
                min_clear = max(phi, base.phi, self.aggregate_mm + 5.0, 20.0)
                if clear_between_families < min_clear:
                    continue

                as_add_single = bar_area_mm2(phi) * 1000.0 / s
                as_add = n_layers * as_add_single
                if as_add + 1e-9 < deficit_as:
                    continue

                if n_layers == 1:
                    text = f"Ø{int(phi)}//{int(s)}"
                else:
                    text = f"{n_layers}Ø{int(phi)}//{int(s)}"

                sol = RebarSolution(phi=phi, spacing=s, as_prov=as_add, text_override=text)
                excess = as_add / max(deficit_as, 1.0)
                penalty_layers = n_layers - 1
                penalty_phi = 0 if phi <= 12.0 else (phi - 12.0) / 10.0
                key = (penalty_layers, penalty_phi, excess, phi)
                candidates.append((key, sol))

        if candidates:
            candidates.sort(key=lambda x: x[0])
            return candidates[0][1]

        raise ValueError("Sem reforço intercalado exequível; rever armadura base/espessura")

    def optimize_rebar_solution(self, as_req: float, max_spacing: float, is_vertical_direction: bool, label: str) -> RebarSolution:
        """Adopta armadura automática. Se activado, usa base + reforço adicional local coerente."""
        def direct(note="solução automática directa"):
            full=self.choose_rebar(as_req,max_spacing=max_spacing)
            full.as_base=0.;full.as_add=full.as_prov;full.add_text=full.text
            full.optimization_note=note;full.n_iterations=1
            return full
        if not self.optimize_rebar:
            return direct()
        if "substituir" in normalize_text(self.rebar_strategy):
            return direct(f"estratégia substituir base: adoptada solução uniforme directa para {label}")
        base = self.base_solution_for_direction(is_vertical_direction)
        ok_base, base_note = self.base_solution_is_valid(base, max_spacing)
        if not ok_base:
            # Preserve an explicit warning, never describe the rejected base
            # as a family of installed/adopted steel.
            return direct(f"base rejeitada ({base_note}); adoptada solução automática directa")

        # Iteração 0: armadura base
        if base.as_prov + 1e-9 >= as_req:
            return RebarSolution(
                base.phi, base.spacing, base.as_prov,
                text_override=base.text, base_text=base.text, add_text="-",
                as_base=base.as_prov, as_add=0.0,
                optimization_note=f"base suficiente para {label}", n_iterations=0,
            )

        # Iteração 1: manter base e acrescentar reforço local com o MESMO espaçamento da base.
        # Isto evita combinações pouco coerentes, como Ø10//200 + Ø8//150.
        deficit = max(0.0, as_req - base.as_prov)
        add = self.choose_compatible_additional_rebar(deficit, base, max_spacing=max_spacing)
        final_as = base.as_prov + add.as_prov
        text = f"{base.text} + {add.text}"

        return RebarSolution(
            max(base.phi, add.phi), base.spacing, final_as,
            text_override=text, base_text=base.text, add_text=add.text,
            as_base=base.as_prov, as_add=add.as_prov,
            optimization_note=f"base insuficiente; reforço local coerente com a malha base para {label}", n_iterations=1,
        )

    def shear_face_depth(self, sol, other, is_vertical):
        """Effective depth to centroid of actual intercalated families.
        Vertical outer in both faces, consistent with physical shell layout.
        Does not establish anchorage or actual installation. Fall back to
        conservative nominal depth if geometry cannot be reconstructed.
        """
        fam = self._parse_rebar_text(sol.text)
        cross = self._parse_rebar_text(other.text)
        if not fam or not cross:
            return self.effective_depth(sol.phi)
        cover = self.cover if is_vertical else self.cover + max(p for _,p,_ in cross)
        if cover + max(p for _,p,_ in fam) >= self.t/2:
            return self.effective_depth(sol.phi)
        weights = [n*p*p/s for n,p,s in fam]
        return self.t-cover-sum(w*p/2 for w,(_,p,_) in zip(weights,fam))/sum(weights)

    def shear_vrdc_kN_per_m(self, as_l_per_m: float, d_mm: float, sigma_cp: float = 0.0) -> float:
        fck = self.fck
        gamma_c = self.gamma_c
        crdc = 0.18 / gamma_c
        k = min(2.0, 1.0 + math.sqrt(200.0 / d_mm)) if d_mm > 0 else 2.0
        rho_l = min(0.02, max(0.0, as_l_per_m / (1000.0 * d_mm))) if d_mm > 0 else 0.0
        vrdc = crdc * k * (100.0 * rho_l * fck) ** (1.0 / 3.0) if rho_l > 0 else 0.0
        vmin = 0.035 * k ** 1.5 * math.sqrt(fck)
        vrdc = max(0.0, max(vrdc, vmin) + 0.15 * min(sigma_cp, 0.2 * self.cp["fcd"]))  # EC2 (6.2a/b)
        return vrdc * d_mm  # N/mm = kN/m

    def shear_vrdmax_kN_per_m(self, d_mm: float, cot_theta: float = 1.0) -> float:
        """Limite superior simplificado de esmagamento da biela comprimida, por metro."""
        if d_mm <= 0:
            return 0.0
        fcd = self.cp["fcd"]
        nu1 = 0.6 * (1.0 - self.fck / 250.0)
        z = 0.9 * d_mm
        tan_theta = 1.0 / cot_theta
        # N/mm = kN/m, para bw = 1000 mm
        return 1000.0 * z * nu1 * fcd / (cot_theta + tan_theta) / 1000.0

    def wood_armer_moments(self, mxx: float, myy: float, mxy: float) -> Tuple[float, float, float, float, str]:
        method = normalize_text(self.wood_armer_method)
        if "optimizado" in method:
            # Minimum sum of nonnegative orthogonal moment capacities such
            # that diag(Mx,My) - M is positive semidefinite. Both faces
            # independently, no rotation of the reinforcement axes.
            def face(a,b,c):
                q=abs(c)
                if a+q>=0 and b+q>=0:return a+q,b+q
                if a+q<0 and b+q<0:return 0.,0.
                if a+q<0:return 0.,max(0.,b+q*q/(-a))
                return max(0.,a+q*q/(-b)),0.
            xp,yp=face(mxx,myy,mxy);xn,yn=face(-mxx,-myy,-mxy)
            return xp,xn,yp,yn,"Wood-Armer optimizado (ortogonal)"
        if "principal" in method:
            avg = 0.5 * (mxx + myy)
            rad = math.sqrt((0.5 * (mxx - myy)) ** 2 + mxy ** 2)
            m1 = avg + rad
            m2 = avg - rad
            # Distribuição conservativa por armadura ortogonal: adopta o principal máximo como referência nas duas direcções.
            mx_pos = max(0.0, m1)
            mx_neg = max(0.0, -m2)
            my_pos = max(0.0, m1)
            my_neg = max(0.0, -m2)
            return mx_pos, mx_neg, my_pos, my_neg, "Momentos principais conservativos"
        # Método base: envelope conservativo com |MXY|.
        mx_pos = max(0.0, mxx + abs(mxy))
        mx_neg = max(0.0, -mxx + abs(mxy))
        my_pos = max(0.0, myy + abs(mxy))
        my_neg = max(0.0, -myy + abs(mxy))
        return mx_pos, mx_neg, my_pos, my_neg, "Wood-Armer conservativo |MXY|"

    def crack_simplified_status(self, sol: RebarSolution) -> Tuple[str, str]:
        # Controlo indirecto quando wk não é seleccionado.
        # Não substitui o cálculo explícito da largura de fenda em ELS quase-permanente.
        # Usa espaçamento efectivo quando existe reforço intercalado.
        phi_ctrl, s_eff, _ = self.rebar_crack_geometry(sol)
        if s_eff <= 200.0 and phi_ctrl <= 12.0:
            return "OK*", "controlo indirecto: Ø≤12 e s_ef≤200 mm; wk não calculado"
        if s_eff <= 250.0 and phi_ctrl <= 16.0:
            return "OK*", "controlo indirecto no limite: Ø≤16 e s_ef≤250 mm; confirmar por ELS se condicionante"
        return "Verificar", "diâmetro/espaçamento efectivo elevado; recomenda-se verificação wk com combinação quase-permanente"

    def crack_min_as_per_face(self, sigma_s_lim: float = 500.0) -> float:
        # EC2 7.3.2 em forma simplificada para faixa de 1 m: kc*k*fct,eff*Act/sigma_s.
        # Act é aproximado como a meia espessura traccionada por face.
        kc = 0.40
        k = 1.0 if self.t <= 300.0 else (0.65 if self.t >= 800.0 else 1.0 - 0.35 * (self.t - 300.0) / 500.0)
        fct_eff = self.cp["fctm"]
        act = 1000.0 * self.t / 2.0
        return kc * k * fct_eff * act / max(sigma_s_lim, 1.0)

    def _parse_rebar_text(self, txt: str) -> List[Tuple[int, float, float]]:
        """Extrai famílias de armadura do texto: Ø10//200, 2Ø12//200, etc."""
        out = []
        for part in str(txt or "").replace("phi", "Ø").split("+"):
            p = part.strip().replace(" ", "")
            if not p or p == "-":
                continue
            m = re.search(r"(?:(\d+)Ø)?(\d+(?:[.,]\d+)?)//(\d+(?:[.,]\d+)?)", p)
            if not m:
                m = re.search(r"(\d+)?\s*[Øø]\s*(\d+(?:[.,]\d+)?)\s*/{2,3}\s*(\d+(?:[.,]\d+)?)", p)
            if m:
                n = int(m.group(1)) if m.group(1) else 1
                phi = float(m.group(2).replace(",", "."))
                s = float(m.group(3).replace(",", "."))
                out.append((max(1, n), phi, s))
        return out

    def rebar_crack_geometry(self, sol: RebarSolution) -> Tuple[float, float, int]:
        """Retorna Ø de controlo, espaçamento efectivo e nº aproximado de famílias para fendilhação.

        Para base + reforços, assume reforços intercalados com o mesmo espaçamento da base:
        Ø10//200 + Ø8//200 -> s_eff ≈ 100 mm.
        """
        # The adopted description is authoritative. base_text/add_text
        # can describe rejected candidates and must not inflate rho or count.
        families = self._parse_rebar_text(sol.text)
        if not families:
            return sol.phi, sol.spacing, 1
        phi_ctrl = sum(n * phi**2 / sp for n, phi, sp in families) / sum(n * phi / sp for n, phi, sp in families)
        # se as famílias têm o mesmo espaçamento, usa intercalamento; caso contrário, adopta conservadoramente o maior espaçamento.
        spacings = [s for n, phi, s in families if s > 0]
        n_fam = sum(n for n, phi, s in families)
        if spacings and max(spacings) - min(spacings) < 1e-6:
            s_eff = spacings[0] / max(1, n_fam)
        else:
            s_eff = max(spacings) if spacings else sol.spacing
        return phi_ctrl, s_eff, max(1, n_fam)

    def _interp_limit(self, sigma_s: float, table: List[Tuple[float, float]]) -> float:
        if not table:
            return 0.0
        sigma_s = max(0.0, float(sigma_s))
        table = sorted(table)
        if sigma_s <= table[0][0]:
            return table[0][1]
        for (s0, v0), (s1, v1) in zip(table[:-1], table[1:]):
            if s0 <= sigma_s <= s1:
                if abs(s1 - s0) < 1e-9:
                    return v0
                return v0 + (v1 - v0) * (sigma_s - s0) / (s1 - s0)
        return table[-1][1]

    def ec2_crack_limits(self, sigma_s: float) -> Tuple[float, float, str]:
        """Limites aproximados por tabelas EC2 7.3N/7.2N para controlo sem cálculo directo.

        As tabelas são usadas como verificação de coerência de diâmetro/espaçamento para o valor de wmax
        seleccionado. Para valores intermédios de tensão é feita interpolação linear.
        """
        w = float(self.wmax_mm)
        # Tabelas indicativas usuais do EC2 para betão armado.
        # sigma_s [MPa] -> phi_max [mm]
        phi_tables = {
            0.4: [(160, 40), (200, 32), (240, 20), (280, 16), (320, 12), (360, 10), (400, 8), (450, 6)],
            0.3: [(160, 32), (200, 25), (240, 16), (280, 12), (320, 10), (360, 8), (400, 6), (450, 5)],
            0.2: [(160, 25), (200, 16), (240, 12), (280, 8), (320, 6), (360, 5), (400, 4), (450, 0)],
        }
        # sigma_s [MPa] -> s_max [mm]
        spacing_tables = {
            0.4: [(160, 300), (200, 300), (240, 250), (280, 200), (320, 150), (360, 100), (400, 50), (450, 0)],
            0.3: [(160, 300), (200, 250), (240, 200), (280, 150), (320, 100), (360, 50), (400, 0), (450, 0)],
            0.2: [(160, 200), (200, 150), (240, 100), (280, 50), (320, 0), (360, 0), (400, 0), (450, 0)],
        }
        # selecciona a classe de wmax imediatamente inferior/igual, por segurança
        if w <= 0.20 + 1e-9:
            key = 0.2
        elif w <= 0.30 + 1e-9:
            key = 0.3
        else:
            key = 0.4
        phi_lim = self._interp_limit(sigma_s, phi_tables[key])
        s_lim = self._interp_limit(sigma_s, spacing_tables[key])
        note = f"limites EC2 indicativos para wmax≈{key:.1f} mm e σs={sigma_s:.0f} MPa"
        return phi_lim, s_lim, note

    def crack_width_estimate(self, m_ed_kNm_per_m: float, sol: RebarSolution) -> Tuple[float, float, float, str]:
        # Estimativa EC2 7.3.4 simplificada para flexão de faixa de 1 m.
        # Usa a armadura final real na face traccionada: As_base + As_reforço.
        # Deve ser usada apenas com esforços ELS.
        m = abs(m_ed_kNm_per_m) * 1e6
        if m <= 1e-9 or sol.as_prov <= 1e-9:
            return 0.0, 0.0, 0.0, "sem tracção relevante"
        Es = 200000.0
        Ecm = 22.0 * ((self.fck + 8.0) / 10.0) ** 0.3 * 1000.0
        alpha_e = Es / Ecm if Ecm > 0 else 6.0
        phi_ctrl, s_eff, _ = self.rebar_crack_geometry(sol)
        d = self.effective_depth(phi_ctrl)
        z = 0.90 * d
        # Secção fendilhada transformada, sem limitar artificialmente sigma_s.
        na = alpha_e * sol.as_prov / 1000.0
        x = math.sqrt(na * na + 2.0 * na * d) - na
        z = d - x / 3.0
        sigma_s = m / (z * sol.as_prov)
        h_ceff = min(2.5 * (self.t - d), (self.t - x) / 3.0, self.t / 2.0)
        a_ceff = max(1.0, 1000.0 * h_ceff)
        rho_eff = max(sol.as_prov / a_ceff, 1e-5)
        k1 = 0.8
        k2 = 0.5
        k3 = 3.4
        k4 = 0.425
        kt = 0.4 if "quase" in normalize_text(self.combo_type) or self.wk_check_enabled else 0.6
        c = self.cover
        sr_formula = k3 * c + k1 * k2 * k4 * phi_ctrl / rho_eff
        # Não se força sr_max ao espaçamento, mas reporta-se s_eff e compara-se com o limite EC2.
        sr_max = sr_formula if s_eff <= 5.0 * (c + phi_ctrl / 2.0) else 1.3 * (self.t - x)
        eps = max((sigma_s - kt * self.cp["fctm"] / rho_eff * (1.0 + alpha_e * rho_eff)) / Es, 0.6 * sigma_s / Es)
        wk = sr_max * eps
        note = "wk estimado com As final real da face traccionada; confirmar se os esforços são de ELS quase-permanente"
        return wk, sigma_s, sr_max, note

    def crack_check_detail(self, m_ed_kNm_per_m: float, sol: RebarSolution, face: str, direction: str) -> Dict[str, object]:
        wk, sigma_s, sr_max, note = self.crack_width_estimate(m_ed_kNm_per_m, sol)
        phi_ctrl, s_eff, n_fam = self.rebar_crack_geometry(sol)
        phi_lim, s_lim, lim_note = self.ec2_crack_limits(sigma_s)
        if sigma_s > 0.8 * self.fyk:
            st = "Verificar"
            reason = f"Tensão ELS no aço {sigma_s:.1f} MPa > 0,8 fyk; rever secção"
        elif wk <= self.wmax_mm + 1e-9 and phi_ctrl <= phi_lim + 1e-9 and s_eff <= s_lim + 1e-9:
            st = "OK"
            reason = f"wk={wk:.3f} mm ≤ wmax; Øctrl={phi_ctrl:.0f}≤Ølim={phi_lim:.0f}; s_eff={s_eff:.0f}≤s_lim={s_lim:.0f}"
        elif wk <= self.wmax_mm + 1e-9:
            st = "OK*"
            reason = f"wk cumpre, mas diâmetro/espaçamento excede limite simplificado: Øctrl={phi_ctrl:.0f}/Ølim={phi_lim:.0f}; s_eff={s_eff:.0f}/s_lim={s_lim:.0f}"
        else:
            st = "Verificar"
            reason = f"wk={wk:.3f} mm > wmax={self.wmax_mm:.3f} mm"
        return {
            "Face": face, "Direction": direction, "Rebar": sol.text,
            "As_total_mm2_m": sol.as_prov, "As_base_mm2_m": sol.as_base, "As_add_mm2_m": sol.as_add,
            "phi_control_mm": phi_ctrl, "s_eff_mm": s_eff, "n_families": n_fam,
            "sigma_s_MPa": sigma_s, "phi_lim_EC2_mm": phi_lim, "s_lim_EC2_mm": s_lim,
            "sr_max_mm": sr_max, "wk_mm": wk, "wmax_mm": self.wmax_mm,
            "Status": st, "Reason": reason, "Note": note + "; " + lim_note,
        }

    def optimize_solution_for_cracking(self, m_qp: float, sol: RebarSolution, as_req: float, max_spacing: float, is_vertical_direction: bool, label: str) -> RebarSolution:
        """Optimização específica de fendilhação para a combinação quase-permanente.

        Prioriza: mais varões, menor diâmetro, reforço intercalado e coerência com a malha base.
        """
        if not self.wk_check_enabled or abs(m_qp) <= 1e-9:
            return sol
        current_detail = self.crack_check_detail(m_qp, sol, label[-1:] if label else "", label[:1] if label else "")
        if current_detail["Status"] in ("OK", "OK*") and current_detail["wk_mm"] <= self.wmax_mm + 1e-9:
            return sol

        candidates: List[RebarSolution] = [sol]
        as_req=max(as_req,sol.as_prov)
        base=self.base_solution_for_direction(is_vertical_direction)
        preserve_base=self.optimize_rebar and "substituir" not in normalize_text(self.rebar_strategy) and self.base_solution_is_valid(base,max_spacing)[0]
        # soluções directas com espaçamentos menores
        for phi in ([] if preserve_base else sorted(self.phi_candidates)):
            for s in sorted(self.spacing_candidates):
                if s > max_spacing + 1e-9:
                    continue
                cand_as = bar_area_mm2(phi) * 1000.0 / s
                if cand_as + 1e-9 < as_req:
                    continue
                cand = RebarSolution(phi, s, cand_as, as_base=0.0, as_add=cand_as, add_text=f"Ø{int(phi)}//{int(s)}", optimization_note=f"optimização wk directa para {label}", n_iterations=2)
                candidates.append(cand)

        # soluções base + reforços coerentes com a malha base
        if preserve_base:
            base = self.base_solution_for_direction(is_vertical_direction)
            ok_base, _ = self.base_solution_is_valid(base, max_spacing)
            if ok_base:
                # base isolada
                if base.as_prov >= as_req:
                    candidates.append(RebarSolution(base.phi, base.spacing, base.as_prov, text_override=base.text, base_text=base.text, add_text="-", as_base=base.as_prov, as_add=0.0, optimization_note=f"base suficiente após verificação wk para {label}", n_iterations=1))
                # reforços intercalados, mesmo espaçamento da base
                for n_layers in (1, 2, 3):
                    for phi in sorted(self.phi_candidates):
                        add_as = n_layers * bar_area_mm2(phi) * 1000.0 / base.spacing
                        final_as = base.as_prov + add_as
                        if final_as + 1e-9 < as_req:
                            continue
                        add_txt = f"{n_layers}Ø{int(phi)}//{int(base.spacing)}" if n_layers > 1 else f"Ø{int(phi)}//{int(base.spacing)}"
                        txt = f"{base.text} + {add_txt}"
                        candidates.append(RebarSolution(max(base.phi, phi), base.spacing, final_as, text_override=txt, base_text=base.text, add_text=add_txt, as_base=base.as_prov, as_add=add_as, optimization_note=f"reforço intercalado por wk para {label}", n_iterations=2 + n_layers))

        valid = []
        fallback = []
        for cand in candidates:
            phi, spacing, _ = self.rebar_crack_geometry(cand)
            phi_max=max(p for n,p,sp in self._parse_rebar_text(cand.text))
            if preserve_base and cand.as_base+1e-9<base.as_prov:
                continue
            if spacing - phi_max < max(phi_max, self.aggregate_mm + 5.0, 20.0):
                continue
            det = self.crack_check_detail(m_qp, cand, "", "")
            if det["sigma_s_MPa"] > 0.8 * self.fyk:
                continue
            if cand.as_prov + 1e-9 < as_req:
                continue
            key = (cand.as_prov, det["s_eff_mm"], det["phi_control_mm"], cand.text)
            if det["wk_mm"] <= self.wmax_mm + 1e-9 and det["phi_control_mm"] <= det["phi_lim_EC2_mm"] + 1e-9 and det["s_eff_mm"] <= det["s_lim_EC2_mm"] + 1e-9:
                valid.append((key, cand))
            elif det["wk_mm"] <= self.wmax_mm + 1e-9:
                fallback.append((key, cand))
        if valid:
            best = sorted(valid, key=lambda x: x[0])[0][1]
            best.optimization_note = (best.optimization_note + "; " if best.optimization_note else "") + "wk verificado"
            return best
        if fallback:
            best = sorted(fallback, key=lambda x: x[0])[0][1]
            best.optimization_note = (best.optimization_note + "; " if best.optimization_note else "") + "wk cumpre; confirmar limites Ø/s"
            return best
        return sol

    def is_qp_case(self, case_value: object) -> bool:
        if not self.qp_case:
            return False
        return canonical_case_id(case_value) == canonical_case_id(self.qp_case)

    def crack_full_status(self, wk_values: List[float], case_value: object) -> Tuple[str, str]:
        if not self.wk_check_enabled:
            return "OK*", "wk não seleccionado; aplicado apenas controlo indirecto por diâmetro/espaçamento"
        if not self.qp_case:
            return "Verificar", "verificação wk seleccionada, mas o número da combinação quase-permanente não foi indicado"
        if not self.is_qp_case(case_value):
            return "Não avaliado", f"wk só é avaliado para a combinação quase-permanente indicada: {self.qp_case}"
        finite=[v for v in wk_values if math.isfinite(v)]
        if len(finite)!=4:
            if any(v>self.wmax_mm+1e-9 for v in finite):
                return "Verificar", "wk excede wmax numa face calculada; restantes faces por avaliar"
            return "Não avaliado", "Cobertura insuficiente do cálculo de wk"
        wk_max = max(finite)
        if wk_max <= self.wmax_mm + 1e-9:
            return "OK", f"combinação quase-permanente {self.qp_case}: wk,max={wk_max:.3f} mm ≤ wmax={self.wmax_mm:.3f} mm"
        return "Verificar", f"combinação quase-permanente {self.qp_case}: wk,max={wk_max:.3f} mm > wmax={self.wmax_mm:.3f} mm"

    def composite_crack_details(self, normal, moment, plus, minus, direction, cross=None):
        sign = 1 if self.axial_convention == "Compressão positiva" else -1
        pp, sp, _ = self.rebar_crack_geometry(plus)
        pm, sm, _ = self.rebar_crack_geometry(minus)
        section = self.section_for(plus, minus,direction,cross)
        phi_service = self.stability_params["phi_final"] if self.stability_params is not None else self.creep_effective
        family_details = None
        if section.layers:
            family_details=tuple((phi,spacing,count) for sol in (plus,minus)
                                 for count,phi,spacing in self._parse_rebar_text(sol.text))
        calculated = section.cracking(sign*normal, moment, pp, sp, pm, sm, phi_service,
                                      family_details=family_details)
        results = []
        for face, sol, key in (("+", plus, "plus"), ("-", minus, "minus")):
            value = calculated[key]
            phi, spacing, families = self.rebar_crack_geometry(sol)
            sigma = value["sigma_s"]
            overstress = sigma > .8*self.fyk or calculated["service"]["concrete_max"] > .45*self.fck
            # Limite conservador 7.3.2: kc=1 e Act=h/2 por face traccionada.
            minimum_as = self.crack_min_as_per_face() / .4 if sigma > 1e-9 else 0.0
            minimum_ok = sol.as_prov >= minimum_as - 1e-9
            status = "Não avaliado" if not math.isfinite(value["wk"]) else ("OK" if value["wk"] <= self.wmax_mm and not overstress and minimum_ok else "Verificar")
            reason = f"wk N-M={value['wk']:.3f} mm; σs={sigma:.1f} MPa; k2={value['k2']:.3f}"
            if value.get("reason"):
                reason += "; " + value["reason"]
            if not minimum_ok:
                reason += f"; As inferior ao mínimo conservador N-M ({minimum_as:.1f} mm²/m)"
            if overstress:
                reason += "; tensão ELS fora dos limites adoptados para modelo linear"
            results.append(dict(Face=face,Direction=direction,Rebar=sol.text,
                As_total_mm2_m=sol.as_prov,As_base_mm2_m=sol.as_base,As_add_mm2_m=sol.as_add,
                phi_control_mm=value.get("phi_eff",phi),s_eff_mm=value.get("spacing_eff",spacing),n_families=families,
                As_eff_mm2_m=value.get("as_eff",0. if value["wk"]==0. else float("nan")),
                cover_eff_mm=value.get("cover_eff",float("nan")),
                sigma_s_MPa=sigma,phi_lim_EC2_mm=float("nan"),s_lim_EC2_mm=float("nan"),
                sr_max_mm=value["sr_max"],wk_mm=value["wk"],wmax_mm=self.wmax_mm,
                Status=status,Reason=reason,Note="EC2 7.3.4; N-M assinado, secção fendilhada; sem retracção impedida",
                hc_eff_mm=value["hc_eff"],rho_eff=value["rho_eff"],k2=value["k2"],As_min_nm=minimum_as))
        return results, calculated["service"]

    def case_role(self, value):
        if self.is_qp_case(value):
            return "ELS-QP"
        if canonical_case_id(value) in self.characteristic_cases:
            return "ELS-CAR"
        if canonical_case_id(value) in self.frequent_cases:
            return "ELS-FREQ"
        if self.elu_cases:
            return "ELU" if canonical_case_id(value) in self.elu_cases else "Não seleccionado"
        return "ELU (não separado)"

    def section_for(self, plus, minus, direction=None, cross=None):
        nominal = self.cover + max(self.phi_candidates) + max(plus.phi, minus.phi)/2
        layers=()
        if direction is not None and cross is not None:
            vertical = (direction == "Y") == self.local_y_is_vertical
            data=[]
            for sign,sol,other in ((1,plus,cross[0]),(-1,minus,cross[1])):
                fam=self._parse_rebar_text(sol.text); orth=self._parse_rebar_text(other.text)
                if not fam or not orth:
                    raise ValueError("Famílias de armaduras não reconhecidas")
                cover=self.cover if vertical else self.cover+max(p for n,p,s in orth)
                for count,phi,spacing in fam:
                    if cover+phi>=self.t/2:
                        raise ValueError("Armaduras não cabem na meia espessura")
                    data.append((sign*(self.t/2-cover-phi/2),count*1000*math.pi*phi**2/(4*spacing)))
                # Manual/legacy areas can be rounded to whole mm²; permit only
                # sub-per-mille rounding and distribute the declared total.
                side=[i for i,(z,a) in enumerate(data) if sign*z>0]
                actual=sum(data[i][1] for i in side)
                if not math.isclose(actual,sol.as_prov,rel_tol=.001,abs_tol=.01):
                    raise ValueError("Área declarada incompatível com os varões")
                for i in side:
                    z,a=data[i];data[i]=(z,a*sol.as_prov/actual)
            layers=tuple(data)
            nominal=max(self.t/2-abs(z) for z,a in layers)
        return Section(self.t, nominal, plus.as_prov, minus.as_prov, self.fck, self.cp["fcd"], self.fyd,
                       eps_ud=self.steel_ultimate_strain,layers=layers)

    def stability_values(self, direction):
        if self.stability_params is not None:
            axis=direction.lower()
            return self.stability_params['l0_'+axis],self.stability_params['phi_'+axis]
        return self.effective_length_mm,self.creep_effective

    def composite_detail(self, n_value, mplus, mminus, plus, minus, direction="X", cross=None):
        length, phi = self.stability_values(direction)
        normal = n_value if self.axial_convention == "Compressão positiva" else -n_value
        sec = self.section_for(plus, minus,direction,cross)
        minimum_moment = normal * max(self.t/30.0, 20.0)/1000 if normal > 0 else 0.0
        moments = [max(mplus, minimum_moment), -max(mminus, minimum_moment)]
        stability = dict(status="Não requerida (N ≤ 0)", buckling_load=float("nan"), amplification=1., slenderness=float("nan"), limit=float("nan"))
        if normal > 0 and (length <= 0 or phi is None):
            stability.update(status="Pendente: l0" if length <= 0 else "Pendente: fluência", amplification=float("nan"))
        if normal > 0 and length > 0 and phi is not None:
            # excentricidade mínima 6.1(4) + imperfeição de faixa isolada
            e_min = max(self.t/30.0, 20.0)
            e_i = length/400.0
            m0 = max(mplus, mminus, normal*e_min/1000) + normal*e_i/1000
            lam = length/(self.t/math.sqrt(12))
            lim = slenderness_limit(normal,self.t,self.cp["fcd"],plus.as_prov+minus.as_prov,self.fyd,phi)
            if lam < lim:
                # Still include geometric imperfection even if second order is dispensable.
                stability = dict(moment=m0,amplification=1.,slenderness=lam,limit=lim,
                                 buckling_load=float("nan"),status="Dispensada (λ < λlim)")
            else:
                stability = nominal_stiffness(normal, m0, self.t, plus.as_prov+minus.as_prov,
                    sec.cover_axis, self.fck, self.cp["fcd"], self.fyd, length, phi,steel_inertia=sec.steel_inertia)
                stability["limit"] = lim
                if stability["status"] == "OK": stability["status"] = "Incluída (rigidez nominal)"
            if not math.isfinite(stability["moment"]):
                return dict(utilisation=float("inf"),mrd=0.0,status="Não conforme", ned=normal, med=float("nan")), stability
            # Aplicar envolvente desfavorável nas duas orientações de flexão.
            moments = [stability["moment"], -stability["moment"]]
        checks = [dict(sec.check(normal, moment), ned=normal, med=moment) for moment in moments]
        return max(checks, key=lambda v:v["utilisation"]), stability

    def design_one(self, row: pd.Series, adopted=None, sizing_only=False, skip_shell_diagnostic=False) -> Dict[str, object]:
        for c in ("mxx", "myy", "mxy", "qxx", "qyy", "nxx", "nyy", "nxy", "mxx_pos_wa", "mxx_neg_wa", "myy_pos_wa", "myy_neg_wa"):
            if c in row.index and not math.isfinite(safe_float(row[c])):
                raise ValueError(f"Esforço inválido na coluna {c}")
        mxx_raw = safe_float(row.get("mxx", 0.0), 0.0)
        myy_raw = safe_float(row.get("myy", 0.0), 0.0)
        mxy_raw = safe_float(row.get("mxy", 0.0), 0.0)
        qxx_raw = safe_float(row.get("qxx", 0.0), 0.0)
        qyy_raw = safe_float(row.get("qyy", 0.0), 0.0)
        mxx = mxx_raw * self.moment_factor
        myy = myy_raw * self.moment_factor
        mxy = mxy_raw * self.moment_factor
        qxx = qxx_raw * self.shear_factor
        qyy = qyy_raw * self.shear_factor
        nxx = safe_float(row.get("nxx", 0.0), 0.0) * self.shear_factor
        nyy = safe_float(row.get("nyy", 0.0), 0.0) * self.shear_factor
        nxy = safe_float(row.get("nxy", 0.0), 0.0) * self.shear_factor

        wa_cols = ["mxx_pos_wa", "mxx_neg_wa", "myy_pos_wa", "myy_neg_wa"]
        wa_present = [(c in row.index) and not bool(row.get(f"__missing_{c}", False)) for c in wa_cols]
        if any(wa_present) and not all(wa_present):
            raise ValueError("Formato Wood-Armer incompleto: fornecer as quatro colunas M+/M-")
        has_explicit_wa = all(wa_present)
        if not has_explicit_wa and any(c not in row.index or bool(row.get(f"__missing_{c}", False)) for c in ("mxx", "myy")):
            raise ValueError("Fornecer MXX e MYY ou as quatro colunas Wood-Armer")
        if has_explicit_wa:
            mx_pos = abs(safe_float(row.get("mxx_pos_wa", 0.0), 0.0) * self.moment_factor)
            mx_neg = abs(safe_float(row.get("mxx_neg_wa", 0.0), 0.0) * self.moment_factor)
            my_pos = abs(safe_float(row.get("myy_pos_wa", 0.0), 0.0) * self.moment_factor)
            my_neg = abs(safe_float(row.get("myy_neg_wa", 0.0), 0.0) * self.moment_factor)
            # Valores apenas para reporte quando a tabela não contém MXX/MYY/MXY originais.
            if bool(row.get("__missing_mxx", False)):
                mxx = mx_pos if mx_pos >= mx_neg else -mx_neg
            if bool(row.get("__missing_myy", False)):
                myy = my_pos if my_pos >= my_neg else -my_neg
            if bool(row.get("__missing_mxy", False)):
                mxy = 0.0
        
        if self.swap_local_axes:
            mxx, myy = myy, mxx
            qxx, qyy = qyy, qxx
            nxx, nyy = nyy, nxx
            if has_explicit_wa:
                mx_pos, my_pos = my_pos, mx_pos
                mx_neg, my_neg = my_neg, mx_neg

        if has_explicit_wa:
            wa_method_used = "Wood-Armer importado (M+/M-)"
            mxy_ratio = 0.0
        else:
            mx_pos, mx_neg, my_pos, my_neg, wa_method_used = self.wood_armer_moments(mxx, myy, mxy)
            m_ref = max(abs(mxx), abs(myy), abs(mxy), 1e-9)
            mxy_ratio = abs(mxy) / m_ref

        role = self.case_role(row.get("case", ""))
        is_service = role.startswith("ELS-")
        elu_factor = 0.0 if is_service else 1.0
        asx_pos_flex = self.flexural_as_required(mx_pos * elu_factor)
        asx_neg_flex = self.flexural_as_required(mx_neg * elu_factor)
        asy_pos_flex = self.flexural_as_required(my_pos * elu_factor)
        asy_neg_flex = self.flexural_as_required(my_neg * elu_factor)

        asv_min_total, ash_min_total, asv_max_total = self.min_wall_reinf_total()
        # Distribuição dos mínimos de parede por duas faces.
        asv_min_face = asv_min_total / 2.0
        ash_min_face = ash_min_total / 2.0
        # Como os momentos são de placa, reforça-se o mínimo com o mínimo de flexão de lajes/faixa de 1 m.
        as_slab_min_face = self.slab_flexural_min_per_face(12.0)
        as_crack_min_face = self.crack_min_as_per_face()

        if self.local_y_is_vertical:
            asx_min_face = max(ash_min_face, as_slab_min_face, as_crack_min_face)
            asy_min_face = max(asv_min_face, as_slab_min_face, as_crack_min_face)
            sx_max = self.max_spacing_for_direction(False)
            sy_max = self.max_spacing_for_direction(True)
        else:
            asx_min_face = max(asv_min_face, as_slab_min_face, as_crack_min_face)
            asy_min_face = max(ash_min_face, as_slab_min_face, as_crack_min_face)
            sx_max = self.max_spacing_for_direction(True)
            sy_max = self.max_spacing_for_direction(False)

        asx_pos_req = max(asx_pos_flex, asx_min_face)
        asx_neg_req = max(asx_neg_flex, asx_min_face)
        asy_pos_req = max(asy_pos_flex, asy_min_face)
        asy_neg_req = max(asy_neg_flex, asy_min_face)

        x_is_vertical = not self.local_y_is_vertical
        y_is_vertical = self.local_y_is_vertical
        nm_enabled = self.axial_convention != "Não definida"
        if adopted is not None:
            sol_x_pos, sol_x_neg, sol_y_pos, sol_y_neg = adopted
        else:
            sol_x_pos = self.optimize_rebar_solution(asx_pos_req, sx_max, x_is_vertical, "X+")
            sol_x_neg = self.optimize_rebar_solution(asx_neg_req, sx_max, x_is_vertical, "X-")
            sol_y_pos = self.optimize_rebar_solution(asy_pos_req, sy_max, y_is_vertical, "Y+")
            sol_y_neg = self.optimize_rebar_solution(asy_neg_req, sy_max, y_is_vertical, "Y-")

            # O corte não é corrigido aumentando automaticamente aço longitudinal:
            # rho_l é limitada e a face traccionada deve ser identificada.
            # Iteração específica para fendilhação com a combinação quase-permanente.
            # A optimização usa a armadura final real da face traccionada e, no modo base + reforços,
            # privilegia reforços intercalados com o mesmo espaçamento da armadura base.
            if self.wk_check_enabled and self.is_qp_case(row.get("case", "")):
                sol_x_pos = self.optimize_solution_for_cracking(mx_pos, sol_x_pos, asx_pos_req, sx_max, x_is_vertical, "X+")
                sol_x_neg = self.optimize_solution_for_cracking(mx_neg, sol_x_neg, asx_neg_req, sx_max, x_is_vertical, "X-")
                sol_y_pos = self.optimize_solution_for_cracking(my_pos, sol_y_pos, asy_pos_req, sy_max, y_is_vertical, "Y+")
                sol_y_neg = self.optimize_solution_for_cracking(my_neg, sol_y_neg, asy_neg_req, sy_max, y_is_vertical, "Y-")

            if nm_enabled and not is_service and adopted is None:
                pairs = []
                for normal, mpos, mneg, plus, minus, vertical, label in (
                    (nxx, mx_pos, mx_neg, sol_x_pos, sol_x_neg, x_is_vertical, "X"),
                    (nyy, my_pos, my_neg, sol_y_pos, sol_y_neg, y_is_vertical, "Y")):
                    if abs(normal) > 1e-9:
                        for _ in range(12):
                            detail, _st = self.composite_detail(normal, mpos, mneg, plus, minus, label)
                            if detail["utilisation"] <= 1:
                                break
                            target = max(plus.as_prov, minus.as_prov) * 1.25
                            try:
                                plus = self.optimize_rebar_solution(target, self.max_spacing_for_direction(vertical), vertical, label+"+")
                                minus = self.optimize_rebar_solution(target, self.max_spacing_for_direction(vertical), vertical, label+"-")
                            except ValueError:
                                break
                    pairs.append((plus, minus))
                (sol_x_pos, sol_x_neg), (sol_y_pos, sol_y_neg) = pairs

        if sizing_only:
            return {"Panel": row.get("panel", ""), "Node": row.get("node", ""), "Case": row.get("case", ""),
                "tensor_ok": nm_enabled and all(c in row.index and not bool(row.get(f"__missing_{c}", False)) for c in ("nxx","nyy","nxy","mxx","myy","mxy")),
                "NXX":nxx,"NYY":nyy,"NXY":nxy,"MXX":mxx,"MYY":myy,"MXY":mxy,
                "Mx_pos":mx_pos,"Mx_neg":mx_neg,"My_pos":my_pos,"My_neg":my_neg,
                "QXX":qxx,"QYY":qyy,"shear_ok":all(c in row.index and not bool(row.get(f"__missing_{c}",False)) for c in ("qxx","qyy","nxx","nyy")) and nm_enabled, **{
                f"As{key}_prov_mm2_m": sol.as_prov
                for key, sol in zip(("x+", "x-", "y+", "y-"),
                                    (sol_x_pos, sol_x_neg, sol_y_pos, sol_y_neg))}}
        if adopted is not None:
            sol_x_pos, sol_x_neg, sol_y_pos, sol_y_neg = adopted

        mrd_x_pos = self.mrd_kNm_per_m(sol_x_pos.as_prov, sol_x_pos.phi)
        mrd_x_neg = self.mrd_kNm_per_m(sol_x_neg.as_prov, sol_x_neg.phi)
        mrd_y_pos = self.mrd_kNm_per_m(sol_y_pos.as_prov, sol_y_pos.phi)
        mrd_y_neg = self.mrd_kNm_per_m(sol_y_neg.as_prov, sol_y_neg.phi)

        nm_x = nm_y = None
        stability_x = stability_y = None
        if nm_enabled and not is_service:
            nm_x, stability_x = self.composite_detail(nxx, mx_pos, mx_neg, sol_x_pos, sol_x_neg, "X", cross=(sol_y_pos,sol_y_neg))
            nm_y, stability_y = self.composite_detail(nyy, my_pos, my_neg, sol_y_pos, sol_y_neg, "Y", cross=(sol_x_pos,sol_x_neg))
        if nm_x is not None:
            util_m = max(nm_x["utilisation"], nm_y["utilisation"])
        else:
            util_m = max(
                mx_pos / mrd_x_pos if mrd_x_pos > 0 else float("inf"),
                mx_neg / mrd_x_neg if mrd_x_neg > 0 else float("inf"),
                my_pos / mrd_y_pos if mrd_y_pos > 0 else float("inf"),
                my_neg / mrd_y_neg if mrd_y_neg > 0 else float("inf"),
            )

        sign_n = 1.0 if self.axial_convention == "Compressão positiva" else -1.0
        sigma_cp_x = sign_n * nxx / self.t if nm_enabled else 0.0
        sigma_cp_y = sign_n * nyy / self.t if nm_enabled else 0.0

        def shear_face_envelope(plus, minus, sigma, other_plus, other_minus, is_vertical):
            candidates = []
            for face, sol, outer in (("+", plus, other_plus), ("-", minus, other_minus)):
                depth = self.shear_face_depth(sol, outer, is_vertical)
                candidates.append((self.shear_vrdc_kN_per_m(sol.as_prov, depth, sigma),
                                   face, sol.as_prov, depth))
            return min(candidates), min(self.shear_vrdmax_kN_per_m(v[3]) for v in candidates)

        (vrdc_x, shear_face_x, asx_for_shear, d_shear_x), vrdmax_x = shear_face_envelope(sol_x_pos, sol_x_neg, sigma_cp_x, sol_y_pos, sol_y_neg, x_is_vertical)
        (vrdc_y, shear_face_y, asy_for_shear, d_shear_y), vrdmax_y = shear_face_envelope(sol_y_pos, sol_y_neg, sigma_cp_y, sol_x_pos, sol_x_neg, y_is_vertical)
        raw_missing_qxx = bool(row.get("__missing_qxx", "qxx" not in row.index))
        raw_missing_qyy = bool(row.get("__missing_qyy", "qyy" not in row.index))
        # Raw columns retain their original identities. Local-axis values and
        # availability must transform together, including absent components.
        missing_qxx, missing_qyy = ((raw_missing_qyy, raw_missing_qxx)
                                    if self.swap_local_axes else (raw_missing_qxx, raw_missing_qyy))
        util_qx = 0.0 if missing_qxx or qxx == 0 else (abs(qxx) / vrdc_x if vrdc_x > 0 else float("inf"))
        util_qy = 0.0 if missing_qyy or qyy == 0 else (abs(qyy) / vrdc_y if vrdc_y > 0 else float("inf"))
        util_qx_max = 0.0 if missing_qxx or qxx == 0 else (abs(qxx) / vrdmax_x if vrdmax_x > 0 else float("inf"))
        util_qy_max = 0.0 if missing_qyy or qyy == 0 else (abs(qyy) / vrdmax_y if vrdmax_y > 0 else float("inf"))
        shear_design = {}
        if not is_service:
            for ax, v, cap, depth, missing in (("X",abs(qxx),vrdc_x,d_shear_x,missing_qxx),("Y",abs(qyy),vrdc_y,d_shear_y,missing_qyy)):
                # Both possible tension faces: use the smaller d for the proposal.
                if ax=="X":
                    d_prop=min(self.shear_face_depth(sol_x_pos,sol_y_pos,x_is_vertical),self.shear_face_depth(sol_x_neg,sol_y_neg,x_is_vertical))
                else:
                    d_prop=min(self.shear_face_depth(sol_y_pos,sol_x_pos,y_is_vertical),self.shear_face_depth(sol_y_neg,sol_x_neg,y_is_vertical))
                vals=shear_reinforcement_trial(v,cap,d_prop,self.fck,self.cp["fcd"],self.fyk,self.fyd,missing=missing)
                shear_design.update({f"ShearDesign_{ax}_{k}":val for k,val in vals.items()})
        if is_service:
            # ELU resistance ratios are undefined for service combinations.
            # In particular MRd=0 for the limited simple-flexure model is not
            # a service failure when a heavily reinforced mesh is adopted.
            util_m = util_qx = util_qy = util_qx_max = util_qy_max = float("nan")
        util = max(util_m, util_qx, util_qy)

        # Controlo de As,max para a armadura vertical total, quando o eixo vertical está definido.
        if self.local_y_is_vertical:
            as_vertical_total = sol_y_pos.as_prov + sol_y_neg.as_prov
            max_vert_phi = max(sol_y_pos.phi, sol_y_neg.phi)
        else:
            as_vertical_total = sol_x_pos.as_prov + sol_x_neg.as_prov
            max_vert_phi = max(sol_x_pos.phi, sol_x_neg.phi)
        max_ok = as_vertical_total <= asv_max_total + 1e-9

        # Armadura transversal de ligação entre faces: EC2 9.6.4.
        transverse_links_required = as_vertical_total > 0.02 * self.ac_per_m + 1e-9
        mesh_exception = (max_vert_phi <= 16.0 and self.cover > 2.0 * max_vert_phi)
        transverse_links_note = ""

        def empty_crack_detail(face: str, direction: str, rebar_text: str, reason: str) -> Dict[str, object]:
            return {
                "Face": face, "Direction": direction, "Rebar": rebar_text,
                "As_total_mm2_m": float("nan"), "As_base_mm2_m": float("nan"), "As_add_mm2_m": float("nan"),
                "phi_control_mm": float("nan"), "s_eff_mm": float("nan"), "n_families": float("nan"),
                "sigma_s_MPa": float("nan"), "phi_lim_EC2_mm": float("nan"), "s_lim_EC2_mm": float("nan"),
                "sr_max_mm": float("nan"), "wk_mm": float("nan"), "wmax_mm": self.wmax_mm,
                "Status": "Não avaliado", "Reason": reason, "Note": reason,
            }

        if self.wk_check_enabled:
            if self.is_qp_case(row.get("case", "")):
                # O cálculo explícito de wk só é feito para a combinação quase-permanente indicada.
                crack_x_pos = self.crack_check_detail(mx_pos, sol_x_pos, "+", "X")
                crack_x_neg = self.crack_check_detail(mx_neg, sol_x_neg, "-", "X")
                crack_y_pos = self.crack_check_detail(my_pos, sol_y_pos, "+", "Y")
                crack_y_neg = self.crack_check_detail(my_neg, sol_y_neg, "-", "Y")
                wk_values = [
                    float(crack_x_pos["wk_mm"]), float(crack_x_neg["wk_mm"]),
                    float(crack_y_pos["wk_mm"]), float(crack_y_neg["wk_mm"]),
                ]
                crack_full_status, crack_full_note = self.crack_full_status(wk_values, row.get("case", ""))
                crack_rank = {"OK": 0, "OK*": 1, "Não avaliado": 1, "Verificar": 2}
                crack_status_faces = max(
                    [crack_x_pos["Status"], crack_x_neg["Status"], crack_y_pos["Status"], crack_y_neg["Status"]],
                    key=lambda st: crack_rank.get(st, 2),
                )
                crack_status = max([crack_status_faces, crack_full_status], key=lambda st: crack_rank.get(st, 2))
                crack_note = " | ".join(sorted(set([
                    str(crack_x_pos["Reason"]), str(crack_x_neg["Reason"]),
                    str(crack_y_pos["Reason"]), str(crack_y_neg["Reason"]),
                    crack_full_note,
                ])))
            else:
                reason = f"wk não avaliado nesta linha; usar apenas a combinação quase-permanente {self.qp_case}"
                crack_x_pos = empty_crack_detail("+", "X", sol_x_pos.text, reason)
                crack_x_neg = empty_crack_detail("-", "X", sol_x_neg.text, reason)
                crack_y_pos = empty_crack_detail("+", "Y", sol_y_pos.text, reason)
                crack_y_neg = empty_crack_detail("-", "Y", sol_y_neg.text, reason)
                crack_status = "Não avaliado"
                crack_note = reason
        else:
            # Sem cálculo explícito de wk: fica apenas o controlo simplificado por diâmetro/espaçamento.
            crack_items = [
                self.crack_simplified_status(sol_x_pos),
                self.crack_simplified_status(sol_x_neg),
                self.crack_simplified_status(sol_y_pos),
                self.crack_simplified_status(sol_y_neg),
            ]
            crack_rank = {"OK": 0, "OK*": 1, "Não avaliado": 1, "Verificar": 2}
            crack_status = max((st for st, _ in crack_items), key=lambda st: crack_rank.get(st, 2))
            crack_note = " | ".join(sorted(set(note for _, note in crack_items)))
            reason = "wk não calculado; controlo simplificado por diâmetro/espaçamento"
            crack_x_pos = empty_crack_detail("+", "X", sol_x_pos.text, reason)
            crack_x_neg = empty_crack_detail("-", "X", sol_x_neg.text, reason)
            crack_y_pos = empty_crack_detail("+", "Y", sol_y_pos.text, reason)
            crack_y_neg = empty_crack_detail("-", "Y", sol_y_neg.text, reason)

        service_x = service_y = None
        composite_wk_evaluated = False
        composite_wk_attempted = False
        membrane_present = max(abs(nxx), abs(nyy), abs(nxy)) > 1e-9
        absent_membrane = [c for c in ("nxx", "nyy", "nxy") if bool(row.get("__missing_"+c, c not in row.index))]
        partial_membrane = 0 < len(absent_membrane) < 3
        original_moments = not any(bool(row.get("__missing_"+c, c not in row.index)) for c in ("mxx", "myy", "mxy"))
        # A partial signed membrane table does not establish zero forces in
        # the missing columns. A Wood-Armer envelope cannot reconstruct the
        # signed bending tensor. Retain the legacy local pure-flexure check
        # only for a moment-only input with actual signed moments.
        incomplete_crack_input = partial_membrane or not original_moments
        if (membrane_present or abs(mxy) > 1e-9 or incomplete_crack_input) and self.is_qp_case(row.get("case", "")):
            # Resolução N-M direccional, sem omitir efeitos NXY/MXY.
            supported = nm_enabled and abs(nxy) <= 1e-9 and abs(mxy) <= 1e-9 and original_moments and not absent_membrane
            if supported and self.wk_check_enabled:
                composite_wk_attempted = True
                (crack_x_pos, crack_x_neg), service_x = self.composite_crack_details(nxx, mxx, sol_x_pos, sol_x_neg, "X", cross=(sol_y_pos,sol_y_neg))
                (crack_y_pos, crack_y_neg), service_y = self.composite_crack_details(nyy, myy, sol_y_pos, sol_y_neg, "Y", cross=(sol_x_pos,sol_x_neg))
                details = (crack_x_pos, crack_x_neg, crack_y_pos, crack_y_neg)
                crack_status = "Verificar" if any(v["Status"] == "Verificar" for v in details) else ("Não avaliado" if any(v["Status"] == "Não avaliado" for v in details) else "OK")
                crack_note = " | ".join(v["Reason"] for v in details)
                composite_wk_evaluated = all(math.isfinite(v["wk_mm"]) for v in details)
            else:
                causes = []
                if not nm_enabled: causes.append("sinal de N por definir")
                if not original_moments: causes.append("faltam momentos originais")
                if absent_membrane: causes.append("membrana incompleta: " + ", ".join(c.upper() for c in absent_membrane))
                if abs(nxy) > 1e-9: causes.append("NXY não nulo (membrana acoplada)")
                if bool(row.get("__missing_mxy", False)): causes.append("falta MXY original")
                if abs(mxy) > 1e-9: causes.append("MXY não nulo (flexão acoplada)")
                if not self.wk_check_enabled: causes.append("verificação desativada")
                reason = "wk N-M não avaliado: " + "; ".join(causes)
                crack_x_pos = empty_crack_detail("+", "X", sol_x_pos.text, reason)
                crack_x_neg = empty_crack_detail("-", "X", sol_x_neg.text, reason)
                crack_y_pos = empty_crack_detail("+", "Y", sol_y_pos.text, reason)
                crack_y_neg = empty_crack_detail("-", "Y", sol_y_neg.text, reason)
                crack_status = "Não avaliado"
                crack_note = reason

        gross = {}
        tensor_complete = all(c in row.index and not bool(row.get(f"__missing_{c}", False))
                              for c in ("nxx", "nyy", "nxy", "mxx", "myy", "mxy"))
        if is_service and nm_enabled and tensor_complete:
            sign = -1 if self.axial_convention == "Compressão positiva" else 1
            faces = gross_face_principal(self.t, (sign*nxx, sign*nyy, sign*nxy), (mxx,myy,mxy))
            for face, (hi, lo, angle) in zip(("plus", "minus"), faces):
                gross[f"Gross_sigma1_{face}_MPa"] = hi
                gross[f"Gross_sigma2_{face}_MPa"] = lo
                gross[f"Gross_theta1_{face}_deg"] = angle
                gross[f"Gross_sigma1_fctm_{face}"] = hi/self.cp["fctm"]
        wk_x_pos = float(crack_x_pos["wk_mm"]); sig_x_pos = float(crack_x_pos["sigma_s_MPa"]); sr_x_pos = float(crack_x_pos["sr_max_mm"])
        wk_x_neg = float(crack_x_neg["wk_mm"]); sig_x_neg = float(crack_x_neg["sigma_s_MPa"]); sr_x_neg = float(crack_x_neg["sr_max_mm"])
        wk_y_pos = float(crack_y_pos["wk_mm"]); sig_y_pos = float(crack_y_pos["sigma_s_MPa"]); sr_y_pos = float(crack_y_pos["sr_max_mm"])
        wk_y_neg = float(crack_y_neg["wk_mm"]); sig_y_neg = float(crack_y_neg["sigma_s_MPa"]); sr_y_neg = float(crack_y_neg["sr_max_mm"])
        wk_candidates = [v for v in [wk_x_pos, wk_x_neg, wk_y_pos, wk_y_neg] if math.isfinite(v)]
        wk_partial_max = max(wk_candidates) if wk_candidates else float("nan")
        wk_max_value = wk_partial_max if len(wk_candidates)==4 else float("nan")

        if transverse_links_required:
            transverse_links_note = "requer estribos/ganchos conforme pilares; verificar 9.5.3"
        elif not mesh_exception:
            transverse_links_note = "prever pelo menos 4 estribos/ganchos por m² se a armadura principal estiver junto às faces"
        else:
            transverse_links_note = "pode dispensar armadura transversal se for rede electrossoldada, Ø≤16 e c>2Ø"

        # Verificação preliminar de tensão normal média, se forem fornecidos esforços de membrana.
        # Convenção: NXX/NYY em kN/m, compressão ou tração por metro. 1 kN/m = 1 N/mm.
        n_vertical = nyy if self.local_y_is_vertical else nxx
        sigma_n_mpa = abs(n_vertical) / self.t if self.t > 0 else 0.0
        axial_prelim_util = sigma_n_mpa / self.cp["fcd"] if self.cp["fcd"] > 0 else 0.0

        notes = []
        if has_explicit_wa:
            notes.append("momentos Wood-Armer M+/M- importados; MXY não é reaplicado")
        if missing_qxx or missing_qyy:
            notes.append("QXX/QYY não fornecido: esforço transverso não verificado nesta linha")
        zero_efforts = max(abs(mxx), abs(myy), abs(mxy), mx_pos, mx_neg, my_pos, my_neg, abs(nxx), abs(nyy), abs(nxy)) < 1e-9 and max(abs(qxx), abs(qyy)) < 1e-9
        if self.moment_factor != 1.0 or self.shear_factor != 1.0:
            notes.append(f"unidades convertidas para kNm/m e kN/m: M x{self.moment_factor:g}, Q x{self.shear_factor:g}")
        if self.wk_check_enabled:
            if not self.qp_case:
                notes.append("wk seleccionado, mas falta indicar a combinação quase-permanente")
            elif self.is_qp_case(row.get("case", "")):
                notes.append(f"wk avaliado para a combinação quase-permanente {self.qp_case}")
        else:
            notes.append("wk não seleccionado: sem cálculo explícito; controlo indirecto por diâmetro/espaçamento")
        if not is_service and axial_prelim_util > 0.60:
            notes.append("tensão normal média elevada; requer verificação de flexão composta/estabilidade")
        elif abs(n_vertical) > 1e-9:
            notes.append("N fornecido: realizada apenas verificação preliminar de tensão média")
        if not max_ok:
            notes.append("As vertical > 0,04 Ac")
        if util_qx > 1.0 or util_qy > 1.0:
            notes.append("VEd > VRd,c; elemento requer verificação adicional ao esforço transverso")
        if util_qx_max > 1.0 or util_qy_max > 1.0:
            notes.append("VEd > VRd,max simplificado; secção não conforme ao limite de esmagamento")
        if transverse_links_required:
            notes.append("As vertical > 0,02 Ac: requer armadura transversal de ligação")
        if mxy_ratio > 0.40:
            notes.append("MXY dominante; confirmar eixos locais e método Wood-Armer")
        if crack_status == "Verificar":
            notes.append("controlo de fendilhação simplificado não satisfeito")
        if self.swap_local_axes:
            notes.append("eixos locais X/Y trocados antes do cálculo")
        if self.optimize_rebar:
            notes.append("optimização base + reforços activada")
        if zero_efforts:
            notes.append("linha sem esforços relevantes")

        if zero_efforts:
            status = "Dados insuficientes"
        elif not max_ok or util_m > 1.0 or util_qx_max > 1.0 or util_qy_max > 1.0:
            status = "Não conforme"
        elif (not is_service and axial_prelim_util > 0.60) or util_qx > 1.0 or util_qy > 1.0 or crack_status == "Verificar":
            status = "Verificar"
        elif mxy_ratio > 0.40 or crack_status == "OK*":
            status = "OK*"
        else:
            status = "OK"

        # Clarificação explícita do estado atribuído.
        reason_items = []
        action_items = []
        if zero_efforts:
            reason_items.append("sem esforços relevantes na linha importada")
            action_items.append("confirmar se a linha deve ser considerada no dimensionamento")
        if not max_ok:
            reason_items.append("As vertical total excede o limite adoptado de 0,04 Ac")
            action_items.append("rever espessura, diâmetros, espaçamentos e eventual necessidade de solução localizada")
        if util_m > 1.0:
            reason_items.append(f"utilização à flexão superior a 1,00 (util_M={util_m:.2f})")
            action_items.append("aumentar a armadura adoptada, reduzir o espaçamento ou rever os esforços de cálculo")
        if util_qx_max > 1.0 or util_qy_max > 1.0:
            reason_items.append("VEd excede VRd,max simplificado")
            action_items.append("aumentar espessura/rever modelo; não adoptar sem verificação específica ao esmagamento")
        elif util_qx > 1.0 or util_qy > 1.0:
            dirs = []
            if util_qx > 1.0:
                dirs.append(f"X (util_Qx={util_qx:.2f})")
            if util_qy > 1.0:
                dirs.append(f"Y (util_Qy={util_qy:.2f})")
            reason_items.append("VEd > VRd,c na direcção " + ", ".join(dirs))
            action_items.append("verificar esforço transverso com maior detalhe, rever espessura ou prever solução específica")
        if crack_status == "Verificar":
            reason_items.append(crack_note if self.wk_check_enabled else "controlo simplificado de fendilhação não satisfeito")
            action_items.append("usar combinação quase-permanente de ELS, reduzir diâmetro/espaçamento ou aumentar a armadura")
        elif crack_status == "OK*":
            if not self.wk_check_enabled:
                reason_items.append("wk não calculado; controlo indirecto por diâmetro/espaçamento")
                action_items.append("confirmar wk com combinação quase-permanente se a fendilhação for condicionante")
            else:
                reason_items.append("controlo de fendilhação preliminar no limite")
                action_items.append("confirmar por wk em ELS se a fendilhação for condicionante")
        if not is_service and axial_prelim_util > 0.60:
            reason_items.append("tensão normal média elevada detectada")
            action_items.append("realizar verificação N-M/estabilidade fora do âmbito desta versão")
        if transverse_links_required:
            reason_items.append("As vertical > 0,02 Ac")
            action_items.append("prever armadura transversal de ligação entre faces conforme pormenorização aplicável")
        if mxy_ratio > 0.40:
            reason_items.append(f"MXY dominante (|MXY|/max(|MXX|,|MYY|,|MXY|)={mxy_ratio:.2f})")
            action_items.append("confirmar eixos locais do painel e método de transformação de momentos")
        if self.moment_factor != 1.0 or self.shear_factor != 1.0:
            reason_items.append("unidades importadas convertidas antes do cálculo")
            action_items.append("confirmar unidades da tabela de origem")

        if not reason_items:
            if status == "OK":
                reason_items.append("cumpre as verificações implementadas")
                action_items.append("validar hipóteses gerais, eixos locais e dados de entrada")
            elif status == "OK*":
                reason_items.append("cumpre, mas com aviso menor")
                action_items.append("rever notas antes de adoptar em projecto")
            else:
                reason_items.append("estado atribuído por combinação de avisos")
                action_items.append("rever notas de cálculo")

        missing_membrane = all(bool(row.get(f"__missing_{c}", c not in row.index)) for c in ("nxx", "nyy", "nxy"))
        nmises_only = not bool(row.get("__missing_nmises", "nmises" not in row.index)) and missing_membrane
        if nmises_only:
            if status in ("OK", "OK*"):
                status = "Verificar"
            reason_items.append("NMises é informativo; fornecer NXX/NYY/NXY assinados para N-M/membrana")
            action_items.append("Importar em conjunto a tabela normal com os mesmos painéis/nós/casos")
        if missing_qxx or missing_qyy or (not has_explicit_wa and bool(row.get("__missing_mxy", False))) or (crack_status == "Não avaliado" and self.is_qp_case(row.get("case", ""))) or (not nm_enabled and max(abs(nxx), abs(nyy)) > 1e-9) or abs(nxy) > 1e-9 or any(abs(safe_float(row.get(c, 0.0), 0.0)) > 1e-9 for c in ("nxx_pos_wa", "nxx_neg_wa", "nyy_pos_wa", "nyy_neg_wa")):
            if status in ("OK", "OK*"):
                status = "Verificar"
            reason_items.append("Verificações incompletas: corte/ELS ou esforços de membrana não verificados")
            action_items.append("Completar verificações em falta antes de adoptar em projecto")
        horizontal_total = (sol_x_pos.as_prov + sol_x_neg.as_prov) if self.local_y_is_vertical else (sol_y_pos.as_prov + sol_y_neg.as_prov)
        if horizontal_total + 1e-9 < max(0.25 * as_vertical_total, 0.001 * self.ac_per_m):
            status = "Não conforme"
            reason_items.append("Armadura horizontal inferior ao mínimo relativo à armadura vertical adoptada (9.6.3)")

        if nm_enabled:
            if is_service:
                sign = 1 if self.axial_convention == "Compressão positiva" else -1
                if original_moments and not partial_membrane:
                    phi_service=(self.stability_params["phi_final"] if self.stability_params is not None else self.creep_effective) if role=="ELS-QP" else 0.0
                    service_x = self.section_for(sol_x_pos, sol_x_neg,"X",(sol_y_pos,sol_y_neg)).service(sign*nxx, mxx, phi_service)
                    service_y = self.section_for(sol_y_pos, sol_y_neg,"Y",(sol_x_pos,sol_x_neg)).service(sign*nyy, myy, phi_service)
                else:
                    reason_items.append("Tensões ELS N-M não avaliadas: fornecer momentos originais assinados e completar a tabela de membrana")
                if role == "ELS-QP" and max(abs(nxx), abs(nyy)) > 1e-9 and not composite_wk_evaluated:
                    status = "Verificar" if status != "Não conforme" else status
                    reason_items.append("wk N-M não avaliado para os dados/hipóteses desta linha")
            else:
                util = max(util, nm_x["utilisation"], nm_y["utilisation"])
                if max(nm_x["utilisation"],nm_y["utilisation"]) > 1:
                    status = "Não conforme"
                    reason_items.append("Interacção N-M/segunda ordem da faixa não satisfeita")
                if max(abs(nxx),abs(nyy)) > 1e-9:
                    reason_items.append("Interacção N-M verificada por compatibilidade de extensões")
        if role in ("ELS-CAR", "ELS-FREQ"):
            if status != "Não conforme":status = "Verificar"
            reason_items.append("Tensões de faixa informativas; faltam critérios completos de aceitação para este ELS")
            action_items.append("Rever tensões e verificações específicas da combinação")
            if role == "ELS-CAR" and service_x and service_y and (not self.sandwich_design or (abs(nxy)<=1e-9 and abs(mxy)<=1e-9)):
                steel = max(0., *(-d[k] for d in (service_x, service_y) for k in ("sigma_plus", "sigma_minus")))
                if steel > 0.8 * self.fyk:
                    status = "Não conforme"
                    reason_items.append("Limite de tensão no aço excedido no modelo de faixa (0,8 fyk)")
        if not is_service and nm_enabled:
            for axis, st in (("X",stability_x),("Y",stability_y)):
                raw_axis = ("Y" if axis=="X" else "X") if self.swap_local_axes else axis
                col="n"+raw_axis.lower()*2
                if st and bool(row.get("__missing_"+col,col not in row.index)):
                    st.update(status="Pendente: N desconhecido",amplification=float("nan"))
                if st and st["status"].startswith("Pendente"):
                    if status in ("OK", "OK*"): status = "Verificar"
                    why={"Pendente: l0":"definir l0 da faixa","Pendente: fluência":"fluência não determinada","Pendente: N desconhecido":"esforço normal não fornecido"}
                    reason_items.append(f"Segunda ordem {axis} não avaliada: " + why[st["status"]])
        if not self.elu_cases:
            if status in ("OK", "OK*"):
                status = "Verificar"
            reason_items.append("Definir conjunto ELU explícito para separar dimensionamento e ELS")

        if status not in ("OK", "OK*"):
            reason_items = [r for r in reason_items if r not in ("cumpre as verificações implementadas", "cumpre, mas com aviso menor")]
        verification_reason = " | ".join(dict.fromkeys(str(x) for x in reason_items if str(x).strip()))
        recommended_action = " | ".join(dict.fromkeys(str(x) for x in action_items if str(x).strip()))

        shell_qp = {}
        if not skip_shell_diagnostic and self.shell_qp_diagnostic and self.wk_check_enabled and role == "ELS-QP" and nm_enabled and tensor_complete and not composite_wk_evaluated:
            try:
                sign = -1 if self.axial_convention == "Compressão positiva" else 1
                sols=(sol_x_pos,sol_x_neg,sol_y_pos,sol_y_neg)
                depth=self.cover+max(self.phi_candidates)+max(v.phi for v in sols)/2
                ec=22000*((self.fck+8)/10)**.3/(1+self.creep_effective)
                shell_qp=diagnose_shell_qp(self.t,(sign*nxx,sign*nyy,sign*nxy),(mxx,myy,mxy),[v.as_prov for v in sols],depth,ec,[self.rebar_crack_geometry(v)[:2] for v in sols])
            except (ValueError, ArithmeticError, np.linalg.LinAlgError) as exc:
                shell_qp={"ShellQP_status":"Diagnóstico indisponível: "+str(exc)}
        return {
            **shell_qp,
            **shear_design,
            **{f"Stability_{a}_{k}": v for a,st in (("X",stability_x),("Y",stability_y)) for k,v in (("status",st["status"] if st else "Não avaliado"),("lambda",st["slenderness"] if st else float("nan")),("lambda_lim",st["limit"] if st else float("nan")),("l0_mm",self.stability_values(a)[0]),("phi_eff",self.stability_values(a)[1]))},
            **({"Auto_"+k:v for k,v in self.stability_params.items()} if self.stability_params else {}),
            "Tensor_complete": tensor_complete,
            "Panel": row.get("panel", ""),
            "Node": row.get("node", ""),
            "Case": row.get("case", ""),
            "MXX_raw": mxx_raw,
            "MYY_raw": myy_raw,
            "MXY_raw": mxy_raw,
            "MXX+_WA_raw": safe_float(row.get("mxx_pos_wa", 0.0), 0.0),
            "MXX-_WA_raw": safe_float(row.get("mxx_neg_wa", 0.0), 0.0),
            "MYY+_WA_raw": safe_float(row.get("myy_pos_wa", 0.0), 0.0),
            "MYY-_WA_raw": safe_float(row.get("myy_neg_wa", 0.0), 0.0),
            "QXX_raw": float("nan") if raw_missing_qxx else qxx_raw,
            "QYY_raw": float("nan") if raw_missing_qyy else qyy_raw,
            "Moment_unit": self.moment_unit,
            "Shear_unit": self.shear_unit,
            **gross,
            "Combo_type": self.case_role(row.get("case", "")),
            "Crack_model": "N-M fendilhado" if composite_wk_evaluated else "N-M fendilhado parcial" if composite_wk_attempted else "Flexão simples" if not membrane_present and abs(mxy) <= 1e-9 and not incomplete_crack_input else "Não avaliado",
            "Crack_k2_x+": crack_x_pos.get("k2", float("nan")),
            "Crack_k2_x-": crack_x_neg.get("k2", float("nan")),
            "Crack_k2_y+": crack_y_pos.get("k2", float("nan")),
            "Crack_k2_y-": crack_y_neg.get("k2", float("nan")),
            "Crack_hceff_x+_mm": crack_x_pos.get("hc_eff_mm", float("nan")),
            "Crack_hceff_x-_mm": crack_x_neg.get("hc_eff_mm", float("nan")),
            "Crack_hceff_y+_mm": crack_y_pos.get("hc_eff_mm", float("nan")),
            "Crack_hceff_y-_mm": crack_y_neg.get("hc_eff_mm", float("nan")),
            "Axial_convention": self.axial_convention,
            "NM_X_NEd": nm_x["ned"] if nm_x else float("nan"),
            "NM_Y_NEd": nm_y["ned"] if nm_y else float("nan"),
            "NM_X_MEd": nm_x["med"] if nm_x else float("nan"),
            "NM_Y_MEd": nm_y["med"] if nm_y else float("nan"),
            "NM_X_util": nm_x["utilisation"] if nm_x else float("nan"),
            "NM_Y_util": nm_y["utilisation"] if nm_y else float("nan"),
            "NM_X_MRd": nm_x["mrd"] if nm_x else float("nan"),
            "NM_Y_MRd": nm_y["mrd"] if nm_y else float("nan"),
            "Stability_l0_mm": self.effective_length_mm if self.stability_params is None else float("nan"),
            "Stability_phi_eff": self.creep_effective if self.stability_params is None else float("nan"),
            "Stability_X_NB_kN_m": stability_x["buckling_load"] if stability_x else float("nan"),
            "Stability_Y_NB_kN_m": stability_y["buckling_load"] if stability_y else float("nan"),
            "Stability_X_amplification": stability_x["amplification"] if stability_x else float("nan"),
            "Stability_Y_amplification": stability_y["amplification"] if stability_y else float("nan"),
            "ELS_X_sigma_c_cracked_MPa": service_x["concrete_max"] if service_x else float("nan"),
            "ELS_Y_sigma_c_cracked_MPa": service_y["concrete_max"] if service_y else float("nan"),
            "ELS_X_sigma_s_cracked_MPa": max(0.,-min(service_x["sigma_layers"])) if service_x else float("nan"),
            "ELS_Y_sigma_s_cracked_MPa": max(0.,-min(service_y["sigma_layers"])) if service_y else float("nan"),
            "ELS_X_sigma_plus_MPa": service_x["sigma_plus"] if service_x else float("nan"),
            "ELS_X_sigma_minus_MPa": service_x["sigma_minus"] if service_x else float("nan"),
            "ELS_Y_sigma_plus_MPa": service_y["sigma_plus"] if service_y else float("nan"),
            "ELS_Y_sigma_minus_MPa": service_y["sigma_minus"] if service_y else float("nan"),
            "Input_moment_format": "Wood-Armer M+/M-" if has_explicit_wa else "MXX/MYY/MXY",
            "QP_crack_case": self.qp_case,
            "wk_check_enabled": "Sim" if self.wk_check_enabled else "Não",
            "is_QP_crack_case": "Sim" if self.is_qp_case(row.get("case", "")) else "Não",
            "MXX_kNm_m": mxx,
            "MYY_kNm_m": myy,
            "MXY_kNm_m": mxy,
            "QXX_kN_m": float("nan") if missing_qxx else qxx,
            "QYY_kN_m": float("nan") if missing_qyy else qyy,
            "NXX_kN_m": nxx,
            "NYY_kN_m": nyy,
            "NXY_kN_m": nxy,
            "NMises_kN_m": safe_float(row.get("nmises", 0.0), 0.0) * self.shear_factor if not bool(row.get("__missing_nmises", "nmises" not in row.index)) else float("nan"),
            "NMises_usage": "Informativo; não substitui NXX/NYY/NXY" if not bool(row.get("__missing_nmises", "nmises" not in row.index)) else "Não fornecido",
            "Source_tables_count": row.get("source_tables_count", 1),
            "Mx+_WA": mx_pos,
            "Mx-_WA": mx_neg,
            "My+_WA": my_pos,
            "My-_WA": my_neg,
            "WA_method": wa_method_used,
            "MXY_ratio": mxy_ratio,
            "Asx+_req_mm2_m": asx_pos_req,
            "Asx-_req_mm2_m": asx_neg_req,
            "Asy+_req_mm2_m": asy_pos_req,
            "Asy-_req_mm2_m": asy_neg_req,
            "Asv_min_total_mm2_m": asv_min_total,
            "Ash_min_total_mm2_m": ash_min_total,
            "As_slab_min_face_mm2_m": as_slab_min_face,
            "As_crack_min_face_mm2_m": as_crack_min_face,
            "sX_max_mm": sx_max,
            "sY_max_mm": sy_max,
            "X+_rebar": sol_x_pos.text,
            "X-_rebar": sol_x_neg.text,
            "Y+_rebar": sol_y_pos.text,
            "Y-_rebar": sol_y_neg.text,
            "X+_base": sol_x_pos.base_text or "-",
            "X-_base": sol_x_neg.base_text or "-",
            "Y+_base": sol_y_pos.base_text or "-",
            "Y-_base": sol_y_neg.base_text or "-",
            "X+_additional": sol_x_pos.add_text or "-",
            "X-_additional": sol_x_neg.add_text or "-",
            "Y+_additional": sol_y_pos.add_text or "-",
            "Y-_additional": sol_y_neg.add_text or "-",
            "X+_optimization": sol_x_pos.optimization_note,
            "X-_optimization": sol_x_neg.optimization_note,
            "Y+_optimization": sol_y_pos.optimization_note,
            "Y-_optimization": sol_y_neg.optimization_note,
            "Optimization_iterations": max(sol_x_pos.n_iterations, sol_x_neg.n_iterations, sol_y_pos.n_iterations, sol_y_neg.n_iterations),
            "Optimization_mode": "Base + reforços" if self.optimize_rebar else "Automática directa",
            "Asx+_prov_mm2_m": sol_x_pos.as_prov,
            "Asx-_prov_mm2_m": sol_x_neg.as_prov,
            "Asy+_prov_mm2_m": sol_y_pos.as_prov,
            "Asy-_prov_mm2_m": sol_y_neg.as_prov,
            "MRd_x+_kNm_m": mrd_x_pos,
            "MRd_x-_kNm_m": mrd_x_neg,
            "MRd_y+_kNm_m": mrd_y_pos,
            "MRd_y-_kNm_m": mrd_y_neg,
            "Shear_X_face_VRdc": shear_face_x,
            "Shear_Y_face_VRdc": shear_face_y,
            "Shear_X_As_mm2_m": asx_for_shear,
            "Shear_Y_As_mm2_m": asy_for_shear,
            "Shear_X_d_mm": d_shear_x,
            "Shear_Y_d_mm": d_shear_y,
            "Shear_X_sigma_cp_MPa": sigma_cp_x,
            "Shear_Y_sigma_cp_MPa": sigma_cp_y,
            "Shear_note": "Faixa: profundidade das famílias adoptadas (vertical exterior); confirmar secção crítica e amarração. Proposta Asw não é armadura instalada.",
            "VRdc_x_kN_m": vrdc_x,
            "VRdc_y_kN_m": vrdc_y,
            "VRdmax_x_kN_m": vrdmax_x,
            "VRdmax_y_kN_m": vrdmax_y,
            "util_M": util_m,
            "util_Qx": float("nan") if missing_qxx else util_qx,
            "util_Qy": float("nan") if missing_qyy else util_qy,
            "util_Qx_VRdmax": float("nan") if missing_qxx else util_qx_max,
            "util_Qy_VRdmax": float("nan") if missing_qyy else util_qy_max,
            "util_max": util,
            "As_vertical_total_mm2_m": as_vertical_total,
            "As_vertical_max_mm2_m": asv_max_total,
            "sigma_N_vertical_MPa": sigma_n_mpa,
            "util_N_prelim": axial_prelim_util,
            "Transverse_links_required": "Sim" if transverse_links_required else "Não",
            "Transverse_links_note": transverse_links_note,
            "wk_x+_mm": wk_x_pos,
            "wk_x-_mm": wk_x_neg,
            "wk_y+_mm": wk_y_pos,
            "wk_y-_mm": wk_y_neg,
            "wk_max_mm": wk_max_value,
            "wk_partial_max_mm": wk_partial_max,
            "wk_faces_evaluated": len(wk_candidates),
            "sigma_s_x+_MPa": sig_x_pos,
            "sigma_s_x-_MPa": sig_x_neg,
            "sigma_s_y+_MPa": sig_y_pos,
            "sigma_s_y-_MPa": sig_y_neg,
            "phi_ctrl_x+_mm": crack_x_pos["phi_control_mm"],
            "phi_ctrl_x-_mm": crack_x_neg["phi_control_mm"],
            "phi_ctrl_y+_mm": crack_y_pos["phi_control_mm"],
            "phi_ctrl_y-_mm": crack_y_neg["phi_control_mm"],
            "s_eff_x+_mm": crack_x_pos["s_eff_mm"],
            "s_eff_x-_mm": crack_x_neg["s_eff_mm"],
            "s_eff_y+_mm": crack_y_pos["s_eff_mm"],
            "s_eff_y-_mm": crack_y_neg["s_eff_mm"],
            "phi_lim_x+_EC2_mm": crack_x_pos["phi_lim_EC2_mm"],
            "phi_lim_x-_EC2_mm": crack_x_neg["phi_lim_EC2_mm"],
            "phi_lim_y+_EC2_mm": crack_y_pos["phi_lim_EC2_mm"],
            "phi_lim_y-_EC2_mm": crack_y_neg["phi_lim_EC2_mm"],
            "s_lim_x+_EC2_mm": crack_x_pos["s_lim_EC2_mm"],
            "s_lim_x-_EC2_mm": crack_x_neg["s_lim_EC2_mm"],
            "s_lim_y+_EC2_mm": crack_y_pos["s_lim_EC2_mm"],
            "s_lim_y-_EC2_mm": crack_y_neg["s_lim_EC2_mm"],
            "sr_max_x+_mm": sr_x_pos,
            "sr_max_x-_mm": sr_x_neg,
            "sr_max_y+_mm": sr_y_pos,
            "sr_max_y-_mm": sr_y_neg,
            "Crack_status_x+": crack_x_pos["Status"],
            "Crack_status_x-": crack_x_neg["Status"],
            "Crack_status_y+": crack_y_pos["Status"],
            "Crack_status_y-": crack_y_neg["Status"],
            "Crack_reason_x+": crack_x_pos["Reason"],
            "Crack_reason_x-": crack_x_neg["Reason"],
            "Crack_reason_y+": crack_y_pos["Reason"],
            "Crack_reason_y-": crack_y_neg["Reason"],
            "wmax_mm": self.wmax_mm,
            "Crack_control_status": crack_status,
            "Crack_control_note": crack_note,
            "Status": status,
            "Verification_reason": verification_reason,
            "Recommended_action": recommended_action,
            "Notes": "; ".join(notes),
        }

    def enforce_horizontal_minimum(self, mesh):
        """EC2 9.6.3: total minimum based on adopted vertical steel.
        Allocate deficits evenly as a conservative face-level detailing rule.
        If no candidate fits, retain the previous mesh and let checks fail.
        """
        v=2 if self.local_y_is_vertical else 0
        h=2-v
        target=max(.25*(mesh[v].as_prov+mesh[v+1].as_prov),.001*self.ac_per_m)/2
        for i in (h,h+1):
            if mesh[i].as_prov+1e-9>=target:continue
            try:
                candidate=self.optimize_rebar_solution(target,self.max_spacing_for_direction(False),False,("X+","X-","Y+","Y-")[i])
            except ValueError:continue
            if candidate.as_prov>=target-1e-9:
                candidate.optimization_note += "; mínimo horizontal relativo ao aço vertical adoptado (9.6.3)"
                mesh[i]=candidate

    def refine_actual_nm_mesh(self, provisional, adopted_by_panel, max_iterations=5):
        """Recheck the complete signed ELU envelope using adopted geometry.

        Preliminary N-M sizing uses a nominal axis; changing centroids can
        reduce capacity for some axial-tension states. Search additional
        reinforcement monotonically, without deleting the base or exceeding
        the vertical maximum. Final design_one always rechecks all actions.
        """
        if self.axial_convention == "Não definida":
            return
        vertical=2 if self.local_y_is_vertical else 0
        for panel,g in provisional.groupby('Panel',sort=False):
            mesh=adopted_by_panel[str(panel)]
            # Preserve concomitant forces and the moment transformation used
            # in the final directional check. Explicit imported WA is stored
            # during sizing as well, so no transformation is applied twice.
            rows=g[['NXX','NYY','Mx_pos','Mx_neg','My_pos','My_neg']].to_numpy(float)
            for _ in range(max_iterations):
                failing=[]
                for j in (0,1):
                    pair=2*j; cross=(mesh[2-pair],mesh[3-pair]); axis='XY'[j]
                    try:
                        checks=[self.composite_detail(r[j],r[2+pair],r[3+pair],mesh[pair],mesh[pair+1],axis,cross=cross)[0]['utilisation'] for r in rows]
                    except ValueError:
                        continue  # final calculation must expose geometry error
                    if max(checks,default=0.)>1+1e-9:
                        failing.append(pair)
                if not failing:break
                candidate=list(mesh)
                for pair in failing:
                    is_vertical=pair==vertical
                    for i in (pair,pair+1):
                        try:
                            sol=self.optimize_rebar_solution(mesh[i].as_prov*1.20,self.max_spacing_for_direction(is_vertical),is_vertical,('X+','X-','Y+','Y-')[i])
                            if sol.as_prov>mesh[i].as_prov+1e-7:candidate[i]=sol
                        except ValueError:pass
                self.enforce_horizontal_minimum(candidate)
                if sum(v.as_prov for v in candidate[vertical:vertical+2])>self.min_wall_reinf_total()[2]+1e-9:
                    break
                if not any(a.as_prov>b.as_prov+1e-9 for a,b in zip(candidate,mesh)):
                    break
                # A stronger mesh must also be physically possible in this
                # trial layer arrangement. Avoid adopting an impossible mesh.
                try:
                    self.section_for(candidate[0],candidate[1],"X",(candidate[2],candidate[3]))
                    self.section_for(candidate[2],candidate[3],"Y",(candidate[0],candidate[1]))
                except ValueError:break
                for a,b in zip(candidate,mesh):
                    if a is not b:a.optimization_note+='; revisão N-M com posição efectiva dos varões'
                mesh[:]=candidate

    def service_candidate_fits(self, mesh, index, candidate):
        """Keep the adopted area and check geometry and vertical maximum."""
        if candidate.as_prov+1e-9<mesh[index].as_prov:return False
        trial=list(mesh);trial[index]=candidate
        v=2 if self.local_y_is_vertical else 0
        if trial[v].as_prov+trial[v+1].as_prov>self.min_wall_reinf_total()[2]+1e-9:return False
        try:
            self.section_for(trial[0],trial[1],"X",(trial[2],trial[3]))
            self.section_for(trial[2],trial[3],"Y",(trial[0],trial[1]))
        except ValueError:return False
        return True

    def refine_service_mesh(self, qp_df, adopted_by_panel):
        """Refine supported local QP checks, including partially evaluated faces.
        Unvalidated inclined crack indicators never drive automatic sizing.
        """
        changed=set()
        if self.wk_check_enabled:
            for _, row in qp_df.iterrows():
                panel = str(row.get("panel", ""))
                if panel not in adopted_by_panel:
                    raise ValueError(f"Painel {panel} sem combinação ELU")
                mesh = adopted_by_panel[panel]
                before = tuple(v.text for v in mesh)
                check = self.design_one(row, mesh, skip_shell_diagnostic=True)
                if check["Crack_model"] in ("N-M fendilhado", "N-M fendilhado parcial"):
                    for _ in range(16):
                        modified = False
                        for j, (normal_key, moment_key, vertical, direction) in enumerate((
                            ("NXX_kN_m", "MXX_kNm_m", not self.local_y_is_vertical, "X"),
                            ("NYY_kN_m", "MYY_kNm_m", self.local_y_is_vertical, "Y"))):
                            pair = 2*j
                            details, _service = self.composite_crack_details(check[normal_key], check[moment_key], mesh[pair], mesh[pair+1], direction,cross=(mesh[2-pair],mesh[3-pair]))
                            for face_index, detail in enumerate(details):
                                if detail["Status"] != "Verificar" or detail["sigma_s_MPa"] <= 1e-9:
                                    continue
                                idx = pair + face_index
                                target = max(mesh[idx].as_prov * 1.2, detail["As_min_nm"])
                                try:
                                    candidate = self.optimize_rebar_solution(target, self.max_spacing_for_direction(vertical), vertical, direction)
                                except ValueError:
                                    continue
                                if candidate.as_prov > mesh[idx].as_prov + 1e-9 and self.service_candidate_fits(mesh, idx, candidate):
                                    mesh[idx] = candidate
                                    modified = True
                        if not modified:
                            break
                elif check["Crack_model"] == "Flexão simples":
                    for j, (label, key, vertical) in enumerate((("X+", "Mx+_WA", not self.local_y_is_vertical),
                        ("X-", "Mx-_WA", not self.local_y_is_vertical), ("Y+", "My+_WA", self.local_y_is_vertical),
                        ("Y-", "My-_WA", self.local_y_is_vertical))):
                        candidate = self.optimize_solution_for_cracking(check[key], mesh[j], mesh[j].as_prov,
                            self.max_spacing_for_direction(vertical), vertical, label)
                        if self.service_candidate_fits(mesh,j,candidate):mesh[j]=candidate
                if tuple(v.text for v in mesh) != before:changed.add(panel)
        return changed

    def design_dataframe(self, df: pd.DataFrame, progress=None) -> pd.DataFrame:
        """Adopta uma malha comum por painel e face para todas as combinações.

        A verificação ELS utiliza a armadura envelope ELU/ELS, preservando cada
        combinação original no relatório. Não se misturam acções entre casos.
        """
        if df.empty:
            return pd.DataFrame()
        if self.auto_stability is not None:
            import copy
            nodes,options=self.auto_stability
            frames=[]; offset=0; total=2*len(df)
            for panel,group in df.groupby("panel",sort=False,dropna=False):
                d=copy.copy(self); d.auto_stability=None
                d.stability_params=panel_parameters(group,nodes,d,*options,ec2_final_creep)
                d.creep_effective=d.stability_params['phi_final']  # final coefficient for QP section stresses
                r=d.design_dataframe(group.reset_index(drop=True),progress=(lambda i,n,off=offset: progress(off+int(2*len(group)*i/max(1,n)),total)) if progress else None)
                frames.append(r); offset+=2*len(group)
            return pd.concat(frames,ignore_index=True)
        if self.wk_check_enabled and not any(df["case"].map(self.is_qp_case)):
            raise ValueError("Combinação quase-permanente não encontrada nos dados")
        expected = self.elu_cases | self.characteristic_cases | self.frequent_cases
        if self.qp_case and self.wk_check_enabled:
            expected = expected | {canonical_case_id(self.qp_case)}
        coverage = case_audit(df, expected, canonical_case_id) if self.elu_cases else pd.DataFrame()
        if self.elu_cases:
            present = set(df["case"].map(canonical_case_id))
            if not present.intersection(self.elu_cases):
                raise ValueError("Nenhuma combinação ELU seleccionada encontrada")
            mask = df["case"].map(lambda c: self.case_role(c) != "Não seleccionado")
            selected_keys = set(zip(df.loc[mask,"panel"].astype(str).str.strip(), df.loc[mask,"node"].astype(str).str.strip()))
            omitted = coverage.loc[[(a.Panel,a.Node) not in selected_keys for a in coverage.itertuples()]]
            if not omitted.empty:
                sample = ", ".join(f"{a.Panel}/{a.Node}" for a in omitted.head(8).itertuples())
                raise ValueError(f"{len(omitted)} associações painel/nó sem qualquer combinação seleccionada: {sample}")
            df = df.loc[mask].copy()
        elu_df = df.loc[df["case"].map(lambda c: self.case_role(c).startswith("ELU"))]
        missing_panels = set(df["panel"].astype(str)) - set(elu_df["panel"].astype(str))
        if missing_panels:
            raise ValueError("Painéis sem combinações ELU: " + ", ".join(sorted(missing_panels)))
        if elu_df.empty:
            raise ValueError("Definir pelo menos uma combinação ELU além da QP")
        initial = []
        for count, (_, row) in enumerate(elu_df.iterrows(), 1):
            initial.append(self.design_one(row, sizing_only=True))
            if progress:
                progress(count, len(elu_df)+len(df))
        provisional = pd.DataFrame(initial)
        # Fixed 45-degree sandwich trial: increase the preliminary mesh, never reduce it.
        # No shell compliance claim: actual lever arms, concrete, modal signs and stability require review.
        for key in ("x+","x-","y+","y-"):
            provisional["trial_"+key] = 0.0
        valid = provisional.tensor_ok & ((provisional.NXY.abs()>1e-9) | (provisional.MXY.abs()>1e-9))
        z_trial = self.t-2*(self.cover+1.5*max(self.phi_candidates))
        if not self.sandwich_design and valid.any() and z_trial>0:
            g=provisional.loc[valid]; sign=1 if self.axial_convention=="Tracção positiva" else -1
            tr=shell_screen(sign*g[["NXX","NYY","NXY"]].to_numpy(),g[["MXX","MYY","MXY"]].to_numpy(),z_trial,np.ones((len(g),4)),self.fyd)
            for key, axis, face in (("x+","x","plus"),("x-","x","minus"),("y+","y","plus"),("y-","y","minus")):
                provisional.loc[valid,"trial_"+key]=tr[f"Screen_As{axis}_{face}_mm2_m"]
        adopted_by_panel = {}
        for panel, group in provisional.groupby("Panel", dropna=False):
            adopted = []
            for label, vertical in (("X+", not self.local_y_is_vertical),
                                    ("X-", not self.local_y_is_vertical),
                                    ("Y+", self.local_y_is_vertical),
                                    ("Y-", self.local_y_is_vertical)):
                target = group[f"As{label.lower()}_prov_mm2_m"].max()
                trial_target = max(target, group["trial_"+label.lower()].max())
                try:
                    candidate=self.optimize_rebar_solution(trial_target, self.max_spacing_for_direction(vertical), vertical, label)
                    if trial_target > target+1e-9:
                        candidate.optimization_note += "; reforço pelo diagnóstico de casca (1.ª ordem, experimental)"
                except ValueError:
                    candidate=self.optimize_rebar_solution(target, self.max_spacing_for_direction(vertical), vertical, label)
                adopted.append(candidate)
            adopted_by_panel[str(panel)] = adopted
        # A changed bar diameter in one direction changes the crossing armature
        # centroid. Recheck local QP after ELU refinement, then recheck ELU on
        # the affected panels only. A bounded search is not a convergence claim.
        qp_df=df.loc[df["case"].map(self.is_qp_case)]
        self.refine_service_mesh(qp_df,adopted_by_panel)
        pending=set(adopted_by_panel)
        for _ in range(3):
            if not pending:break
            before={p:tuple(v.text for v in adopted_by_panel[p]) for p in pending}
            trial_rows=provisional[provisional.Panel.astype(str).isin(pending)]
            if self.sandwich_design:
                refine_sandwich(self, trial_rows, adopted_by_panel)
            else:
                refine_physical_mesh(self, trial_rows, adopted_by_panel)
            for p in pending:self.enforce_horizontal_minimum(adopted_by_panel[p])
            refine_directional_shear_mesh(self, trial_rows, adopted_by_panel)
            refine_resultant_mesh(self, trial_rows, adopted_by_panel)
            for p in pending:self.enforce_horizontal_minimum(adopted_by_panel[p])
            self.refine_actual_nm_mesh(trial_rows,adopted_by_panel)
            changed={p for p in pending if tuple(v.text for v in adopted_by_panel[p])!=before[p]}
            if not changed:break
            pending=self.refine_service_mesh(qp_df[qp_df.panel.astype(str).isin(changed)],adopted_by_panel)
            if self.sandwich_design:pending |= changed
        results = []
        for i, (_, row) in enumerate(df.iterrows(), 1):
            results.append(self.design_one(row, adopted_by_panel[str(row.get("panel", ""))]))
            if progress:
                progress(len(elu_df)+i, len(elu_df)+len(df))
        output = pd.DataFrame(results)
        if self.wk_check_enabled:
            qp_panels = set(df.loc[df["case"].map(self.is_qp_case), "panel"].astype(str))
            for idx in output.index[~output["Panel"].astype(str).isin(qp_panels)]:
                if output.at[idx, "Status"] in ("OK", "OK*"):
                    output.at[idx, "Status"] = "Verificar"
                output.at[idx, "Verification_reason"] += " | Painel sem combinação QP para verificar a malha adoptada"
        output["Case_coverage"] = "Não auditada"
        output["Case_missing"] = ""
        if not coverage.empty:
            lookup = coverage.set_index(["Panel", "Node"])
            keys = pd.MultiIndex.from_arrays([output.Panel.astype(str).str.strip(), output.Node.astype(str).str.strip()])
            matched = lookup.reindex(keys)
            output["Case_coverage"] = matched.Estado.fillna("Não auditada").to_numpy()
            output["Case_missing"] = matched.Casos_em_falta.fillna("").to_numpy()
        if self.sandwich_design:
            from wall_service_loads import attach_service_loads
            return attach_service_loads(attach_sandwich(output, self), self)
        output = attach_shell_screen(output, self.t, self.cover, max(self.phi_candidates), self.fyd, self.axial_convention, fck=self.fck, fcd=self.cp["fcd"])
        output = attach_shell_capacity(output,self.t,self.cover,max(self.phi_candidates),self.fyd,self.fck,self.cp["fcd"],self.axial_convention)
        return attach_physical_layers(output,self)


# ============================================================
# GUI
# ============================================================
class WallsEC2App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title(f"{APP_TITLE} | {APP_VERSION}")
        from wall_app_resources import set_window_icon
        self.icon_loaded = False
        try:
            self.icon_loaded = set_window_icon(self)
        except (OSError, tk.TclError):
            pass  # The source program remains usable if an optional asset is absent.
        self.geometry("1220x720")
        self.minsize(900, 560)

        self.df_geometry = pd.DataFrame()
        self.df_geometry_nodes = pd.DataFrame()
        self.geometry_nodes = None
        self.auto_stability_options = None
        self.geometry_source = None
        self.effort_sources = []
        self.geometry_text = tk.StringVar(value="Importe as coordenadas e os esforços; a ordem é livre.")
        self.df_raw = pd.DataFrame()
        self.df_clean = pd.DataFrame()
        self.df_results = pd.DataFrame()
        self.df_summary = pd.DataFrame()
        self.df_governing = pd.DataFrame()
        self.df_zones = pd.DataFrame()
        self.df_unit_check = pd.DataFrame()
        self.df_detailed = pd.DataFrame()
        self.df_notes = pd.DataFrame()
        self.df_optimization = pd.DataFrame()
        self.df_diagnostic = pd.DataFrame()
        self.df_data_validation = pd.DataFrame()
        self.df_sketches = pd.DataFrame()

        self.var_elu_cases = tk.StringVar(value="")
        self.var_axial_convention = tk.StringVar(value="Não definida")
        self.var_car_cases = tk.StringVar()
        self.var_freq_cases = tk.StringVar()
        self.var_l0 = tk.StringVar(value="0")
        self.var_phi_eff = tk.StringVar(value="0")
        self.var_eps_ud = tk.StringVar(value="0.01")
        self.var_thickness = tk.StringVar(value="250")
        self.var_cover = tk.StringVar(value="35")
        self.var_concrete = tk.StringVar(value="C30/37")
        self.var_steel = tk.StringVar(value="500")
        self.var_y_vertical = tk.BooleanVar(value=True)
        self.var_swap_axes = tk.BooleanVar(value=False)
        self.var_crack_spacing = tk.BooleanVar(value=True)
        self.var_crack_check = tk.BooleanVar(value=False)
        self.var_qp_case = tk.StringVar(value="")
        self.var_combo_type = tk.StringVar(value="ELU")
        self.var_wmax = tk.StringVar(value="0.30")
        self.var_moment_unit = tk.StringVar(value="kNm/m")
        self.var_shear_unit = tk.StringVar(value="kN/m")
        self.var_phi_min = tk.StringVar(value="8")
        self.var_phi_max = tk.StringVar(value="16")
        self.var_optimize_rebar = tk.BooleanVar(value=True)
        self.var_rebar_strategy = tk.StringVar(value="Base + reforços")
        self.var_base_v_phi = tk.StringVar(value="10")
        self.var_base_v_spacing = tk.StringVar(value="200")
        self.var_base_h_phi = tk.StringVar(value="8")
        self.var_base_h_spacing = tk.StringVar(value="200")
        self.var_wa_method = tk.StringVar(value="Conservativo |MXY|")
        self.var_reduce = tk.BooleanVar(value=False)
        self.status_var = tk.StringVar(value="Cole a tabela de esforços ou importe um ficheiro.")
        self.progress_var = tk.DoubleVar(value=0.0)
        self.progress_text_var = tk.StringVar(value="0%")
        self.progress_var.trace_add("write", lambda *args: self.progress_text_var.set(f"{self.progress_var.get():.0f}%"))
        self._cell_popup = None

        self._calculated_signature = None
        self.df_external_stability = pd.DataFrame()
        self.df_interlayer = pd.DataFrame()
        self._build_ui()
        for var in self._config_vars().values():
            var.trace_add('write', self._mark_results_stale)

    def _input_signature(self):
        return (tuple((key,var.get()) for key,var in self._config_vars().items()),
                id(self.df_clean), id(self.geometry_nodes), self.auto_stability_options)

    def _mark_results_stale(self, *_args):
        if self._calculated_signature is not None and self._calculated_signature != self._input_signature():
            self.status_var.set('Dados alterados — resultados anteriores; recalcule antes de exportar.')
            self.progress_var.set(0)

    def _export_current(self):
        if self._calculated_signature != self._input_signature():
            messagebox.showwarning('Resultados desatualizados', 'Recalcule após alterar os dados ou hipóteses.', parent=self)
            return False
        return True

    def _external_scope(self):
        from wall_external_stability import calculation_scope
        return calculation_scope(version=APP_VERSION,
            settings={"variaveis":{k:v.get() for k,v in self._config_vars().items()},"auto_estabilidade":self.auto_stability_options},
            efforts=self.df_clean,nodes=self.geometry_nodes,results=self.df_results)

    def external_stability_template(self):
        if self.df_results.empty or not self._export_current():
            return
        from wall_external_stability import template
        from pathlib import Path
        path=filedialog.asksaveasfilename(title="Ficha de verificação externa",defaultextension=".json",filetypes=[("JSON","*.json")])
        if not path:return
        try:
            record=template(self._external_scope())
            Path(path).write_text(json.dumps(record,ensure_ascii=False,indent=2),encoding="utf-8")
            messagebox.showinfo("Ficha externa","Preencha o JSON com o resultado da verificação global independente e a identificação do responsável e do relatório. Não altere a identidade do cálculo nem os casos ELU.",parent=self)
        except (ValueError,OSError) as exc:messagebox.showerror("Ficha externa",str(exc),parent=self)

    def external_stability_import(self):
        if self.df_results.empty or not self._export_current():
            return
        from wall_external_stability import validate_declaration
        from pathlib import Path
        path=filedialog.askopenfilename(title="Declaração de estabilidade externa",filetypes=[("JSON","*.json")])
        if not path:return
        report=filedialog.askopenfilename(title="Relatório externo de estabilidade",filetypes=[("Relatório PDF","*.pdf"),("Todos","*.*")])
        if not report:return
        try:
            record=validate_declaration(self._external_scope(),json.loads(Path(path).read_text(encoding="utf-8-sig")),report)
            if not messagebox.askyesno("Declaração externa","Confirma a correspondência do relatório com esta declaração e este cálculo? O programa apenas regista a verificação externa: não interpreta nem valida estruturalmente o documento, e não promove os estados locais.",parent=self):return
            self.df_external_stability=record
            self.df_summary=self.build_panel_summary(self.df_results)
            # Keep the local verdict separate from the external declaration.
            mapping=record.set_index("Panel").Estabilidade_global_externa
            self.df_summary["Estabilidade_global_externa"]=self.df_summary.Panel.astype(str).map(mapping).fillna("Pendente")
            self._apply_interlayer_result()
            self.show_df(self.tree_summary,self.df_summary);self.refresh_dashboard()
            self.status_var.set("Declaração externa registada; consultar síntese por painel e relatório.")
        except (ValueError,OSError) as exc:messagebox.showerror("Declaração externa",str(exc),parent=self)

    def _apply_interlayer_result(self):
        record=getattr(self,"df_interlayer",pd.DataFrame())
        if record.empty:return
        mapping=record.set_index("Panel").Estado_intercamadas
        if "Transferencia_faces" in self.df_summary:
            ext=self.df_summary.Panel.astype(str).map(mapping)
            passed=ext.eq("Satisfeito com limite externo")
            self.df_summary.loc[passed,"Transferencia_faces"]="Satisfeito com limite externo*"
            for frame in (self.df_summary,self.df_governing):
                if not frame.empty and "Motivo_estado" in frame:
                    ok=frame.Panel.astype(str).map(mapping).eq("Satisfeito com limite externo")
                    frame.loc[ok,"Motivo_estado"]=frame.loc[ok,"Motivo_estado"].str.replace("Corte adicional intercamadas: requer verificação complementar LL(115)(c)","corte intercamadas: limite externo satisfeito",regex=False)
            self.df_summary["Corte_intercamadas_externo"]=ext.fillna("Condicionado")

    def interlayer_template(self):
        if self.df_results.empty or not self._export_current():return
        from wall_interlayer_check import template
        from pathlib import Path
        path=filedialog.asksaveasfilename(title="Ficha — corte adicional intercamadas",defaultextension=".json",filetypes=[("JSON","*.json")])
        if not path:return
        try:
            Path(path).write_text(json.dumps(template(self._external_scope(),self.df_results),ensure_ascii=False,indent=2,allow_nan=False),encoding="utf-8")
            messagebox.showinfo("Corte intercamadas","Preencha o limite superior do corte adicional (kN/m) demonstrado por uma análise espacial independente, para cada painel. Não introduza a diferença de forças de membrana como corte. A ficha utiliza a menor reserva de corte do painel; consultar a documentação.",parent=self)
        except (ValueError,OSError) as exc:messagebox.showerror("Corte intercamadas",str(exc),parent=self)

    def interlayer_import(self):
        if self.df_results.empty or not self._export_current():return
        from wall_interlayer_check import evaluate
        from pathlib import Path
        path=filedialog.askopenfilename(title="Ficha — corte adicional intercamadas",filetypes=[("JSON","*.json")])
        if not path:return
        report=filedialog.askopenfilename(title="Relatório de análise espacial",filetypes=[("Relatório PDF","*.pdf"),("Todos","*.*")])
        if not report:return
        try:
            record=evaluate(self._external_scope(),self.df_results,json.loads(Path(path).read_text(encoding="utf-8-sig")),report)
            if not messagebox.askyesno("Corte intercamadas","Confirma que o limite superior está fundamentado no relatório e abrange todas as posições e estados de cálculo? O WallsEC2 verifica apenas a reserva de corte, não o conteúdo do relatório.",parent=self):return
            self.df_interlayer=record
            self.df_summary=self.build_panel_summary(self.df_results)
            ext=getattr(self,"df_external_stability",pd.DataFrame())
            if not ext.empty:self.df_summary["Estabilidade_global_externa"]=self.df_summary.Panel.astype(str).map(ext.set_index("Panel").Estabilidade_global_externa).fillna("Pendente")
            self.df_governing=self.build_governing_design(self.df_results)
            self._apply_interlayer_result()
            self.show_df(self.tree_summary,self.df_summary);self.show_df(self.tree_governing,self.df_governing);self.refresh_dashboard()
            self.status_var.set("Corte intercamadas — limite externo comparado com reserva resistente.")
        except (ValueError,OSError) as exc:messagebox.showerror("Corte intercamadas",str(exc),parent=self)

    def _build_ui(self):
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except Exception:
            pass

        # ---- aparência geral ----
        bg = "#eef2f6"
        self.configure(background=bg)
        style.configure("TFrame", background="#eef2f6")
        style.configure("TLabelframe", padding=8, background="#eef2f6")
        style.configure("TLabel", background="#eef2f6", foreground="#203448")
        style.configure("TLabelframe.Label", background="#eef2f6", foreground="#203448")
        style.configure("TLabelframe.Label", font=("Segoe UI", 9, "bold"))
        style.configure("TButton", padding=(8, 6))
        style.configure("Primary.TButton", padding=(14, 8), background="#234f75", foreground="white", font=("Segoe UI", 9, "bold"))
        style.map("Primary.TButton", background=[("active", "#34678e")], foreground=[("active", "white")])
        style.configure("Treeview", rowheight=24, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", font=("Segoe UI", 9, "bold"), background="#dce5ed", foreground="#203448")
        style.configure("TNotebook.Tab", padding=(10, 6), font=("Segoe UI", 9))
        style.configure("Header.TLabel", font=("Segoe UI Semibold", 11))
        style.configure("Subtle.TLabel", font=("Segoe UI", 8), foreground="#5f6b7a")
        style.configure("Status.TLabel", font=("Segoe UI", 9))

        self.rowconfigure(0, weight=1)
        self.rowconfigure(1, weight=0)
        self.columnconfigure(0, weight=1)

        root = ttk.Frame(self, padding=8)
        root.grid(row=0, column=0, sticky="nsew")
        root.rowconfigure(1, weight=1)
        root.columnconfigure(0, weight=1)

        paned = ttk.Panedwindow(root, orient="horizontal")
        paned.grid(row=1, column=0, sticky="nsew")
        toolbar = ttk.Frame(root, padding=(4, 2, 4, 8))
        toolbar.grid(row=0, column=0, sticky="ew")
        for title, cmd in (("Importar esforços", self.import_file), ("Importar nós", self.import_geometry)):
            ttk.Button(toolbar, text=title, command=cmd).pack(side="left", padx=(0, 6))
        ttk.Button(toolbar, text="Calcular", command=self.run_design, style="Primary.TButton").pack(side="left", padx=(0, 12))
        for title, items in (("Exportar", (("Excel (.xlsx)", self.export_excel), ("Relatório PDF", self.export_pdf_report), ("CSV", self.export_csv))),
                             ("Configuração", (("Guardar", self.save_config), ("Carregar", self.load_config), ("Criar ficha de corte intercamadas",self.interlayer_template),("Importar limite de corte intercamadas",self.interlayer_import)))):
            button=ttk.Menubutton(toolbar,text=title)
            menu=tk.Menu(button,tearoff=False)
            for label,cmd in items:menu.add_command(label=label,command=cmd)
            button.configure(menu=menu);button.pack(side="left",padx=(0,6))

        # ---- barra lateral scrollable, mais adequada a ecrãs menores ----
        sidebar_host = ttk.Frame(paned, width=355)
        sidebar_host.pack_propagate(False)
        sidebar_host.rowconfigure(0, weight=1)
        sidebar_host.columnconfigure(0, weight=1)

        self.sidebar_canvas = tk.Canvas(sidebar_host, highlightthickness=0, borderwidth=0, background=bg)
        sb_y = ttk.Scrollbar(sidebar_host, orient="vertical", command=self.sidebar_canvas.yview)
        self.sidebar_canvas.configure(yscrollcommand=sb_y.set)
        self.sidebar_canvas.grid(row=0, column=0, sticky="nsew")
        sb_y.grid(row=0, column=1, sticky="ns")

        sidebar_inner = ttk.Frame(self.sidebar_canvas, padding=(0, 0, 6, 0))
        sidebar_window = self.sidebar_canvas.create_window((0, 0), window=sidebar_inner, anchor="nw")

        def _sync_sidebar(_event=None):
            self.sidebar_canvas.configure(scrollregion=self.sidebar_canvas.bbox("all"))
            width = self.sidebar_canvas.winfo_width()
            self.sidebar_canvas.itemconfigure(sidebar_window, width=width)

        sidebar_inner.bind("<Configure>", _sync_sidebar)
        self.sidebar_canvas.bind("<Configure>", _sync_sidebar)

        def _on_mousewheel(event):
            try:
                self.sidebar_canvas.yview_scroll(int(-1 * (event.delta / 120)), "units")
            except Exception:
                pass

        self.sidebar_canvas.bind("<Enter>", lambda e: self.sidebar_canvas.bind_all("<MouseWheel>", _on_mousewheel))
        self.sidebar_canvas.bind("<Leave>", lambda e: self.sidebar_canvas.unbind_all("<MouseWheel>"))

        right = ttk.Frame(paned)
        right.rowconfigure(1, weight=1)
        right.columnconfigure(0, weight=1)

        paned.add(sidebar_host, weight=0)
        paned.add(right, weight=1)

        # ---- rodapé sempre visível ----
        bottom = ttk.Frame(self, padding=(8, 4, 8, 8))
        bottom.grid(row=1, column=0, sticky="ew")
        bottom.columnconfigure(1, weight=1)
        ttk.Label(bottom, text="Estado:", style="Header.TLabel").grid(row=0, column=0, sticky="w", padx=(0, 8))
        ttk.Label(bottom, textvariable=self.status_var, style="Status.TLabel").grid(row=0, column=1, sticky="ew")
        self.progress_bottom = ttk.Progressbar(bottom, variable=self.progress_var, maximum=100, length=260)
        self.progress_bottom.grid(row=0, column=2, sticky="e", padx=(12, 6))
        ttk.Label(bottom, textvariable=self.progress_text_var, width=6, anchor="e").grid(row=0, column=3, sticky="e")

        # ---- cabeçalho compacto ----
        hero = ttk.LabelFrame(sidebar_inner, text="WallsEC2")
        hero.pack(fill="x", pady=(0, 8))
        program_link = ttk.Label(hero, text="WallsEC2", style="Header.TLabel", cursor="hand2")
        program_link.pack(anchor="w")
        program_link.bind("<Button-1>", lambda _e: webbrowser.open_new(GITHUB_URL))
        ttk.Label(hero, text="Paredes de betão armado · EC2", style="Header.TLabel", justify="left", wraplength=300).pack(anchor="w", pady=(2, 0))

        # ---- secção 1: geometria e materiais ----
        basic = ttk.LabelFrame(sidebar_inner, text="1. Geometria e materiais")
        basic.pack(fill="x", pady=(0, 8))
        self._add_label_entry(basic, "Espessura [mm]", self.var_thickness, 0)
        self._add_label_entry(basic, "Recobrimento [mm]", self.var_cover, 1)
        ttk.Label(basic, text="Classe de Betão").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(
            basic, textvariable=self.var_concrete, width=12, state="readonly",
            values=["C20/25", "C25/30", "C30/37", "C35/45", "C40/50", "C45/55", "C50/60"]
        ).grid(row=2, column=1, sticky="ew", padx=6, pady=4)
        ttk.Label(basic, text="Classe de Aço [MPa]").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(basic, textvariable=self.var_steel, width=12, state="readonly", values=["400", "500"]).grid(
            row=3, column=1, sticky="ew", padx=6, pady=4
        )
        basic.columnconfigure(1, weight=1)

        composite = ttk.LabelFrame(sidebar_inner, text="2. Combinações e estabilidade local")
        composite.pack(fill="x", pady=(0, 8))
        self._add_label_entry(composite, "ELU (ex.: 101-133)", self.var_elu_cases, 0)
        ttk.Label(composite, text="Sinal de N").grid(row=1, column=0, sticky="w", padx=6)
        ttk.Combobox(composite, textvariable=self.var_axial_convention, state="readonly",
            values=["Não definida", "Compressão positiva", "Tracção positiva"], width=20).grid(row=1, column=1, sticky="ew", padx=6)
        self.stability_manual_entries=[self._add_label_entry(composite, "l₀ manual [mm]", self.var_l0, 2),self._add_label_entry(composite, "φef manual", self.var_phi_eff, 3)]
        self._add_label_entry(composite, "Limite de deformação εud", self.var_eps_ud, 4)
        ttk.Label(composite, text="l₀=0 no modo manual: segunda ordem pendente. εud é adimensional (0,01 = 1%). No modo automático são usados os parâmetros por painel.",
            wraplength=300, justify="left").grid(row=5, column=0, columnspan=2, padx=6, pady=4)
        self._add_label_entry(composite, "ELS característica", self.var_car_cases, 6)
        self._add_label_entry(composite, "ELS frequente", self.var_freq_cases, 7)
        self.stability_mode_text=tk.StringVar(value="Modo: manual — l0 e φef")
        ttk.Label(composite,textvariable=self.stability_mode_text,wraplength=290,justify="left").grid(row=8,column=0,columnspan=2,sticky="w",padx=6,pady=6)
        ttk.Button(composite, text="Assistente de l₀ e φef…", command=self.assist_stability).grid(row=9, column=0, columnspan=2, sticky="ew", padx=6,pady=2)
        ttk.Button(composite, text="Modo automático por painel…", command=self.configure_auto_stability).grid(row=10,column=0,columnspan=2,sticky="ew",padx=6,pady=2)
        ttk.Button(composite, text="Usar modo manual", command=self.clear_auto_stability).grid(row=11,column=0,columnspan=2,sticky="ew",padx=6,pady=2)
        composite.columnconfigure(1, weight=1)

        # ---- secção 2: modelação, verificações e unidades ----
        checks = ttk.LabelFrame(sidebar_inner, text="3. Modelação e verificações")
        checks.pack(fill="x", pady=(0, 8))
        ttk.Checkbutton(checks, text="Eixo local Y = vertical", variable=self.var_y_vertical).grid(
            row=0, column=0, columnspan=2, sticky="w", padx=6, pady=3
        )
        ttk.Checkbutton(checks, text="Trocar eixos locais X ↔ Y antes do cálculo", variable=self.var_swap_axes).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=6, pady=3
        )
        ttk.Label(checks, text="Método de flexão").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(checks, textvariable=self.var_wa_method, state="readonly",
                     values=["Conservativo |MXY|", "Wood-Armer optimizado", "Momentos principais"]).grid(
            row=2, column=1, sticky="ew", padx=6, pady=4
        )
        ttk.Checkbutton(
            checks, text="Limitar espaçamento a 250 mm", variable=self.var_crack_spacing
        ).grid(row=3, column=0, columnspan=2, sticky="w", padx=6, pady=3)
        ttk.Checkbutton(
            checks, text="Verificar wk com combinação quase-permanente", variable=self.var_crack_check
        ).grid(row=4, column=0, columnspan=2, sticky="w", padx=6, pady=3)
        ttk.Label(checks, text="Comb. quase-perm.").grid(row=5, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(checks, textvariable=self.var_qp_case, width=14).grid(row=5, column=1, sticky="ew", padx=6, pady=4)
        ttk.Label(checks, text="wmax [mm]").grid(row=6, column=0, sticky="w", padx=6, pady=4)
        ttk.Entry(checks, textvariable=self.var_wmax, width=14).grid(row=6, column=1, sticky="ew", padx=6, pady=4)
        ttk.Label(checks, text="Unid. momentos").grid(row=7, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(checks, textvariable=self.var_moment_unit, state="readonly",
                     values=["kNm/m", "Nmm/mm", "Nm/m", "kNmm/m"]).grid(
            row=7, column=1, sticky="ew", padx=6, pady=4
        )
        ttk.Label(checks, text="Unid. N e Q").grid(row=8, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(checks, textvariable=self.var_shear_unit, state="readonly", values=["kN/m", "N/mm", "N/m"]).grid(
            row=8, column=1, sticky="ew", padx=6, pady=4
        )
        checks.columnconfigure(1, weight=1)

        # ---- secção 3: armaduras e optimização ----
        rebar = ttk.LabelFrame(sidebar_inner, text="4. Armaduras e otimização")
        rebar.pack(fill="x", pady=(0, 8))
        ttk.Label(rebar, text="Ø min / Ø max [mm]").grid(row=0, column=0, sticky="w", padx=6, pady=4)
        phi_frame = ttk.Frame(rebar)
        phi_frame.grid(row=0, column=1, sticky="ew", padx=6, pady=4)
        ttk.Entry(phi_frame, textvariable=self.var_phi_min, width=5).pack(side="left")
        ttk.Label(phi_frame, text="  /  ").pack(side="left")
        ttk.Entry(phi_frame, textvariable=self.var_phi_max, width=5).pack(side="left")
        ttk.Checkbutton(rebar, text="Optimizar armadura", variable=self.var_optimize_rebar).grid(
            row=1, column=0, columnspan=2, sticky="w", padx=6, pady=3
        )
        ttk.Label(rebar, text="Estratégia").grid(row=2, column=0, sticky="w", padx=6, pady=4)
        ttk.Combobox(rebar, textvariable=self.var_rebar_strategy, state="readonly",
                     values=["Base + reforços", "Substituir base"]).grid(
            row=2, column=1, sticky="ew", padx=6, pady=4
        )
        ttk.Label(rebar, text="Base vertical Ø//s").grid(row=3, column=0, sticky="w", padx=6, pady=4)
        basev = ttk.Frame(rebar)
        basev.grid(row=3, column=1, sticky="ew", padx=6, pady=4)
        ttk.Entry(basev, textvariable=self.var_base_v_phi, width=5).pack(side="left")
        ttk.Label(basev, text=" // ").pack(side="left")
        ttk.Entry(basev, textvariable=self.var_base_v_spacing, width=6).pack(side="left")
        ttk.Label(rebar, text="Base horizontal Ø//s").grid(row=4, column=0, sticky="w", padx=6, pady=4)
        baseh = ttk.Frame(rebar)
        baseh.grid(row=4, column=1, sticky="ew", padx=6, pady=4)
        ttk.Entry(baseh, textvariable=self.var_base_h_phi, width=5).pack(side="left")
        ttk.Label(baseh, text=" // ").pack(side="left")
        ttk.Entry(baseh, textvariable=self.var_base_h_spacing, width=6).pack(side="left")
        ttk.Label(rebar, text="Todos os casos selecionados são preservados.", wraplength=290).grid(row=5, column=0, columnspan=2, sticky="w", padx=6, pady=3)
        rebar.columnconfigure(1, weight=1)

        # ---- notas rápidas mais compactas ----
        quick = ttk.LabelFrame(sidebar_inner, text="5. Notas rápidas")
        quick.pack(fill="x", pady=(0, 8))
        quick_text = (
            "Importar esforços assinados e concomitantes por painel, nó e combinação:\n"
            "Nxx, Nyy, Nxy — membrana\n"
            "Mxx, Myy, Mxy — flexão e torção\n"
            "Qxx, Qyy — corte transversal\n"
            "Confirmar unidades e eixos locais. Consultar Instruções para o âmbito e os estados de cálculo."
        )
        ttk.Label(quick, text=quick_text, wraplength=310, justify="left").pack(fill="x", padx=6, pady=6)

        # ---- painel principal com tabs curtas ----
        # One compact navigation selector instead of sixteen overflowing tabs.
        nav=ttk.Frame(right,padding=(6,4,6,6));nav.grid(row=0,column=0,sticky="ew")
        ttk.Label(nav,text="Vista",style="Header.TLabel").pack(side="left",padx=(0,8))
        self.view_selector=ttk.Combobox(nav,state="readonly",width=25)
        self.view_selector.pack(side="left")
        style.layout("Workspace.TNotebook.Tab", [])
        nb = ttk.Notebook(right, style="Workspace.TNotebook")
        nb.grid(row=1, column=0, sticky="nsew")
        try:
            nb.enable_traversal()
        except Exception:
            pass

        overview = ttk.Frame(nb, padding=12)
        nb.add(overview, text="Dashboard")
        self.dashboard_text = tk.StringVar(value="Importe as tabelas de esforços para começar.")
        ttk.Label(overview, textvariable=self.dashboard_text, font=("Segoe UI", 12, "bold")).pack(anchor="w", pady=(0,10))
        bar = ttk.Frame(overview)
        bar.pack(fill="x", pady=(0,8))
        ttk.Label(bar, text="Estado:").pack(side="left", padx=(8,4))
        self.dashboard_filter = ttk.Combobox(bar, state="readonly", width=18,
            values=("Todos", "Não conforme", "Condicionado", "Cumpre sob hipóteses", "Dados insuficientes"))
        self.dashboard_filter.set("Todos")
        self.dashboard_filter.pack(side="left")
        self.dashboard_filter.bind("<<ComboboxSelected>>", lambda _: self.refresh_dashboard())
        table = ttk.Frame(overview)
        table.pack(fill="both", expand=True)
        self.dashboard_tree = self._make_tree(table)
        self.dashboard_tree.bind("<Double-1>", self.open_dashboard_panel)
        self.main_notebook = nb

        self.tab_instructions = ttk.Frame(nb)
        self.tab_paste = ttk.Frame(nb)
        self.tab_input = ttk.Frame(nb)
        self.tab_geometry = ttk.Frame(nb)
        self.tab_results = ttk.Frame(nb)
        self.tab_summary = ttk.Frame(nb)
        self.tab_governing = ttk.Frame(nb)
        self.tab_zones = ttk.Frame(nb)
        self.tab_optimization = ttk.Frame(nb)
        self.tab_diagnostic = ttk.Frame(nb)
        self.tab_validation = ttk.Frame(nb)
        self.tab_sketches = ttk.Frame(nb)
        self.tab_unit = ttk.Frame(nb)
        self.tab_detailed = ttk.Frame(nb)
        self.tab_notes = ttk.Frame(nb)
        tab_defs = [
            (self.tab_summary, "Síntese técnica"),
            (self.tab_governing, "Armaduras"),
            (self.tab_zones, "Zonas"),
            (self.tab_results, "Resultados por nó"),
            (self.tab_input, "Esforços importados"),
            (self.tab_geometry, "Geometria"),
            (self.tab_paste, "Colar"),
            (self.tab_instructions, "Instruções"),
            (self.tab_optimization, "Optimização"),
            (self.tab_diagnostic, "Diagnóstico"),
            (self.tab_validation, "Validação"),
            (self.tab_detailed, "Detalhe"),
        ]
        for frame, title in tab_defs:
            nb.add(frame, text=title)

        views=[(overview,"Dashboard"),*tab_defs]
        self.view_selector.configure(values=[title for _,title in views])
        self.view_selector.current(0)
        self.view_selector.bind("<<ComboboxSelected>>",lambda _e: nb.select(views[self.view_selector.current()][0]))
        def sync_view(_e=None):
            selected=nb.select()
            for i,(frame,_title) in enumerate(views):
                if str(frame)==selected:self.view_selector.current(i);break
        nb.bind("<<NotebookTabChanged>>",sync_view)

        self._build_instructions_tab(self.tab_instructions)
        self._build_paste_tab(self.tab_paste)
        self._build_geometry_tab()
        self.tree_input = self._make_tree(self.tab_input)
        self.tree_results = self._make_tree(self.tab_results)
        self.tree_summary = self._make_tree(self.tab_summary)
        self.tree_governing = self._make_tree(self.tab_governing)
        self.tree_zones = self._make_tree(self.tab_zones)
        self.tree_optimization = self._make_tree(self.tab_optimization)
        self.tree_diagnostic = self._make_tree(self.tab_diagnostic)
        self.tree_validation = self._make_tree(self.tab_validation)
        self.tree_sketches = self._make_tree(self.tab_sketches)
        self.tree_unit = self._make_tree(self.tab_unit)
        self.tree_detailed = self._make_tree(self.tab_detailed)
        self.tree_notes = self._make_tree(self.tab_notes)

        # posição inicial da divisória pensada para ecrãs menores
        self.after(100, lambda: paned.sashpos(0, 370))

    def refresh_dashboard(self):
        summary = self.df_summary
        counts = summary["Status_global"].value_counts() if not summary.empty else {}
        external_nc=int(summary.get("Estabilidade_global_externa",pd.Series(dtype=str)).eq("Não conforme (declaração externa)").sum())
        self.dashboard_text.set(
            f"{len(self.df_clean):,} registos importados  |  {len(summary)} painéis calculados  |  "
            f"{counts.get('OK*', 0)} com limites seccionais satisfeitos sob hipóteses  |  {counts.get('Não conforme', 0)} não conformes  |  {counts.get('Incompleto', 0)} condicionados" + (f"  |  {external_nc} não conformes externos" if external_nc else ""))
        selected = self.dashboard_filter.get()
        if not summary.empty and selected != "Todos":
            summary = summary[summary["Status_global"] == ({"Condicionado":"Incompleto","Cumpre sob hipóteses":"OK*"}.get(selected,selected))]
        cols = ["Panel", "Status_global", "util_max", "casca_experimental_max", "ELS_cargas", "ELS_tensoes", "Segunda_ordem_faixas", "Motivo_estado"]
        if "Sand_status" in self.df_results:
            cols=[c.replace("casca_experimental_max","Sand_util_max").replace("casca_linhas_acima_1","Sand_linhas_acima_1") for c in cols]
        view=summary.reindex(columns=cols).copy()
        if "Status_global" in view:view["Status_global"]=view["Status_global"].replace({"Incompleto":"Condicionado", "OK*":"Cumpre sob hipóteses"})
        self.show_df(self.dashboard_tree, view.rename(columns=ENGINEERING_LABELS))
        for name,width in (("Painel",72),("ELU calculado",220),("η faixa",82),("η sandwich",100),("ELS — cargas",200),("2.ª ordem — faixas",145),("Estado seccional",155),("Condições por confirmar",420)):
            if name in self.dashboard_tree["columns"]:self.dashboard_tree.column(name,width=width,anchor="center")

    def open_dashboard_panel(self, event):
        item = self.dashboard_tree.identify_row(event.y)
        if not item or self.df_results.empty:
            return
        values = self.dashboard_tree.item(item, "values")
        if values:
            self.show_df(self.tree_results, self.df_results[self.df_results["Panel"].astype(str) == str(values[0])])
            self.main_notebook.select(self.tab_results)

    def _add_label_entry(self, parent, label, var, row):
        ttk.Label(parent, text=label).grid(row=row, column=0, sticky="w", padx=6, pady=4)
        entry=ttk.Entry(parent, textvariable=var, width=14)
        entry.grid(row=row, column=1, sticky="ew", padx=6, pady=4)
        return entry

    def _build_instructions_tab(self, parent):
        outer = ttk.Frame(parent, padding=10)
        outer.pack(fill="both", expand=True)
        outer.rowconfigure(1, weight=1)
        outer.columnconfigure(0, weight=1)

        ttk.Label(
            outer,
            text="Instruções de utilização e importação",
            style="Header.TLabel",
        ).grid(row=0, column=0, sticky="w", pady=(0, 8))

        frame = ttk.Frame(outer)
        frame.grid(row=1, column=0, sticky="nsew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        txt = tk.Text(frame, wrap="word", height=22, undo=False)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=txt.yview)
        txt.configure(yscrollcommand=vsb.set)
        txt.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")

        instructions = (
            "UTILIZAÇÃO\n"
            "1. Importar esforços em CSV/XLSX ou colar uma tabela. Cada linha deve conter os oito esforços assinados e concomitantes, o painel, nó e combinação.\n"
            "2. Confirmar materiais, geometria, unidades e eixos locais. Selecionar ELU, CAR, FREQ e QP.\n"
            "3. Definir os comprimentos efetivos e a fluência local. O modo por painel usa a geometria dos nós e fatores de travamento confirmados.\n"
            "4. Definir a malha base, diâmetros disponíveis e estratégia de otimização. Calcular.\n"
            "5. Consultar o Dashboard, as armaduras e os resultados. Exportar PDF resumido ou Excel detalhado.\n\n"
            "ENTRADA RECOMENDADA\n"
            "Panel | Node | Case | NXX | NYY | NXY | MXX | MYY | MXY | QXX | QYY\n"
            "43 | 49 | 101 | -12 | -35 | 2 | -12.40 | 3.80 | 1.25 | 18.50 | 6.20\n"
            "N e Q em kN/m; M em kNm/m (ou unidades equivalentes selecionadas). CSV aceita ponto e vírgula, vírgula, tabulação ou barra vertical. Não combinar envolventes independentes num tensor.\n"
            "Momentos Wood-Armer M+/M− importados são usados nas faixas sem reaplicar Mxy. Para o sandwich, conservar também os oito esforços originais. A ausência de componentes não equivale a zero.\n\n"
            "LEITURA DOS RESULTADOS\n"
            "η faixa: interação N–M, corte e estabilidade local por direção. η sandwich: interação dos esforços da casca; pode governar independentemente da faixa.\n"
            "Cumpre sob hipóteses: limites demonstrados para as hipóteses declaradas. Condicionado: demonstração incompleta ou limite de triagem excedido. Não conforme: limite resistente demonstrado excedido.\n"
            "X/Y indicam direções locais; +/− indicam as faces conforme a normal local.\n"
            "ELS: wₖ convencional no domínio aplicável; ausência de fendas por cargas pressupõe secção íntegra e ausência de coação relevante. A combinação QP deve estar presente.\n"
            "A reserva de corte intercamadas não é o corte adicional atuante. Quando requerido, comparar com um limite independente documentado (menu Configuração).\n\n"
            "HIPÓTESES DE UTILIZAÇÃO\n"
            "Os esforços e travamentos devem provir de uma análise estrutural adequada. O cálculo é seccional; o projetista confirma a pormenorização, a história das ações e a aplicabilidade dos modelos. Requisitos específicos de estanquidade e deformações impostas exigem avaliação própria.\n"
            "Consultar README e documentação técnica. Esta é uma release candidate, não uma certificação regulamentar integral."
        )
        txt.insert("1.0", instructions)
        txt.config(state="disabled")

    def _build_paste_tab(self, parent):
        top = ttk.Frame(parent, padding=6)
        top.pack(fill="x")
        ttk.Label(top, text="Tabela de esforços").pack(side="left")
        ttk.Button(top, text="Colar da área de transferência", command=self.paste_clipboard).pack(side="left", padx=(0, 6))
        ttk.Button(top, text="Ler tabela colada", command=self.load_from_textbox).pack(side="right")
        ttk.Button(top, text="Limpar", command=lambda: self.txt_paste.delete("1.0", "end")).pack(side="right", padx=(0, 6))

        frame = ttk.Frame(parent, padding=(6, 0, 6, 6))
        frame.pack(fill="both", expand=True)
        self.txt_paste = tk.Text(frame, wrap="none", undo=True)
        vsb = ttk.Scrollbar(frame, orient="vertical", command=self.txt_paste.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=self.txt_paste.xview)
        self.txt_paste.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        self.txt_paste.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

    def _make_tree(self, parent):
        frame = ttk.Frame(parent)
        frame.pack(fill="both", expand=True)
        tree = ttk.Treeview(frame, show="headings")
        vsb = ttk.Scrollbar(frame, orient="vertical", command=tree.yview)
        hsb = ttk.Scrollbar(frame, orient="horizontal", command=tree.xview)
        tree.configure(yscrollcommand=vsb.set, xscrollcommand=hsb.set)
        tree.grid(row=0, column=0, sticky="nsew")
        vsb.grid(row=0, column=1, sticky="ns")
        hsb.grid(row=1, column=0, sticky="ew")
        frame.rowconfigure(0, weight=1)
        frame.columnconfigure(0, weight=1)

        # Informação completa de células truncadas: clique simples em texto longo ou duplo clique em qualquer célula.
        tree.bind("<ButtonRelease-1>", self._on_tree_cell_click, add="+")
        tree.bind("<Double-1>", self._on_tree_cell_double_click, add="+")
        tree.bind("<Button-3>", self._on_tree_cell_double_click, add="+")
        return tree

    def _tree_cell_data_from_event(self, event):
        tree = event.widget
        try:
            region = tree.identify("region", event.x, event.y)
        except Exception:
            region = tree.identify_region(event.x, event.y)
        if region not in ("cell", "tree"):
            return None

        row_id = tree.identify_row(event.y)
        col_id = tree.identify_column(event.x)
        if not row_id or not col_id or not col_id.startswith("#"):
            return None

        try:
            col_index = int(col_id[1:]) - 1
        except Exception:
            return None

        cols = list(tree["columns"])
        values = list(tree.item(row_id, "values"))
        if col_index < 0 or col_index >= len(cols) or col_index >= len(values):
            return None

        column = cols[col_index]
        value = str(values[col_index])
        row_data = {str(c): str(values[i]) if i < len(values) else "" for i, c in enumerate(cols)}
        return tree, row_id, column, value, row_data

    def _is_tree_value_visually_truncated(self, tree, column, value: str) -> bool:
        value = str(value or "")
        if not value.strip():
            return False
        if "\n" in value or " | " in value or ";" in value:
            return True
        if len(value) > 28:
            return True
        try:
            import tkinter.font as tkfont
            font = tkfont.nametofont("TkDefaultFont")
            text_width = font.measure(value)
            col_width = int(tree.column(column, option="width") or 0)
            return text_width > max(40, col_width - 16)
        except Exception:
            return len(value) > 28

    def _on_tree_cell_click(self, event):
        data = self._tree_cell_data_from_event(event)
        if not data:
            return
        tree, row_id, column, value, row_data = data
        if self._is_tree_value_visually_truncated(tree, column, value):
            self._show_tree_cell_popup(tree, row_id, column, value, row_data, event)

    def _on_tree_cell_double_click(self, event):
        data = self._tree_cell_data_from_event(event)
        if not data:
            return
        tree, row_id, column, value, row_data = data
        if str(value).strip():
            self._show_tree_cell_popup(tree, row_id, column, value, row_data, event)

    def _destroy_cell_popup(self):
        try:
            if self._cell_popup is not None and self._cell_popup.winfo_exists():
                self._cell_popup.destroy()
        except Exception:
            pass
        self._cell_popup = None

    def _show_tree_cell_popup(self, tree, row_id, column, value, row_data, event):
        self._destroy_cell_popup()

        popup = tk.Toplevel(self)
        self._cell_popup = popup
        popup.title("Detalhe da informação")
        popup.transient(self)
        popup.resizable(True, True)
        popup.attributes("-topmost", True)

        # Posicionamento próximo do cursor, mas dentro do ecrã.
        width = 720
        height = 360
        x = self.winfo_pointerx() + 12
        y = self.winfo_pointery() + 12
        screen_w = self.winfo_screenwidth()
        screen_h = self.winfo_screenheight()
        if x + width > screen_w:
            x = max(10, screen_w - width - 20)
        if y + height > screen_h:
            y = max(10, screen_h - height - 60)
        popup.geometry(f"{width}x{height}+{x}+{y}")

        main = ttk.Frame(popup, padding=10)
        main.pack(fill="both", expand=True)
        main.rowconfigure(2, weight=1)
        main.columnconfigure(0, weight=1)

        # Contexto curto da linha.
        panel = row_data.get("Panel", row_data.get("Painel", row_data.get("panel", "")))
        node = row_data.get("Node", row_data.get("Nó", row_data.get("node", "")))
        case = row_data.get("Case", row_data.get("Caso", row_data.get("case", "")))
        status = row_data.get("Status", row_data.get("Status_global", row_data.get("Estado", "")))
        context_bits = []
        if panel: context_bits.append(f"Painel: {panel}")
        if node: context_bits.append(f"Nó: {node}")
        if case: context_bits.append(f"Caso: {case}")
        if status: context_bits.append(f"Estado: {status}")
        context = " | ".join(context_bits) if context_bits else "Linha seleccionada"

        ttk.Label(main, text=f"Coluna: {column}", style="Header.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Label(main, text=context, style="Subtle.TLabel", wraplength=680).grid(row=1, column=0, sticky="ew", pady=(2, 8))

        nb = ttk.Notebook(main)
        nb.grid(row=2, column=0, sticky="nsew")

        tab_value = ttk.Frame(nb, padding=6)
        tab_row = ttk.Frame(nb, padding=6)
        nb.add(tab_value, text="Valor completo")
        nb.add(tab_row, text="Linha completa")

        def _make_text(parent, content):
            parent.rowconfigure(0, weight=1)
            parent.columnconfigure(0, weight=1)
            txt = tk.Text(parent, wrap="word", height=8, font=("Segoe UI", 10), relief="solid", borderwidth=1)
            vsb = ttk.Scrollbar(parent, orient="vertical", command=txt.yview)
            txt.configure(yscrollcommand=vsb.set)
            txt.grid(row=0, column=0, sticky="nsew")
            vsb.grid(row=0, column=1, sticky="ns")
            txt.insert("1.0", content)
            txt.config(state="disabled")
            return txt

        value_text = _make_text(tab_value, str(value))
        row_lines = [f"{k}: {v}" for k, v in row_data.items()]
        row_text = _make_text(tab_row, "\n".join(row_lines))

        buttons = ttk.Frame(main)
        buttons.grid(row=3, column=0, sticky="ew", pady=(8, 0))
        buttons.columnconfigure(0, weight=1)

        def copy_value():
            self.clipboard_clear()
            self.clipboard_append(str(value))
            self.status_var.set("Valor copiado para a área de transferência.")

        def copy_row():
            self.clipboard_clear()
            self.clipboard_append("\n".join(row_lines))
            self.status_var.set("Linha completa copiada para a área de transferência.")

        ttk.Label(buttons, text="Dica: clique em textos longos, faça duplo clique ou botão direito para abrir este detalhe.", style="Subtle.TLabel").grid(row=0, column=0, sticky="w")
        ttk.Button(buttons, text="Copiar valor", command=copy_value).grid(row=0, column=1, padx=(6, 0))
        ttk.Button(buttons, text="Copiar linha", command=copy_row).grid(row=0, column=2, padx=(6, 0))
        ttk.Button(buttons, text="Fechar", command=self._destroy_cell_popup).grid(row=0, column=3, padx=(6, 0))

        popup.bind("<Escape>", lambda _e: self._destroy_cell_popup())
        popup.protocol("WM_DELETE_WINDOW", self._destroy_cell_popup)
        popup.lift()
        try:
            value_text.focus_set()
        except Exception:
            pass

    def show_df(self, tree: ttk.Treeview, df: pd.DataFrame, limit=MAX_PREVIEW_ROWS):
        tree.delete(*tree.get_children())
        if df is None or df.empty:
            tree["columns"] = []
            return
        # Full internal tables are retained for Excel and the calculation API.
        # Main views show engineering outputs, not numerical implementation fields.
        view_columns = {
            "tree_input": ("panel", "node", "case", "nxx", "nyy", "nxy", "mxx", "myy", "mxy", "qxx", "qyy", "mxx_pos_wa", "mxx_neg_wa", "myy_pos_wa", "myy_neg_wa"),
            "tree_results": ("Panel", "Node", "Case", "Combo_type", "NXX_kN_m", "NYY_kN_m", "NXY_kN_m", "MXX_kNm_m", "MYY_kNm_m", "MXY_kNm_m", "QXX_kN_m", "QYY_kN_m", "util_max", "Sand_util", "Sand_status", "wk_max_mm", "wk_cargas_cond_mm", "ELS_cargas_estado", "ELS_72_estado"),
            "tree_summary": ("Panel", "Status_global", "ELU_modelo", "util_max", "Sand_util_max", "Sand_steel_util_max", "Sand_concrete_util_max", "Sand_shear_util_max", "Sand_no_governante", "Sand_caso_governante", "ELS_cargas", "ELS_tensoes", "Segunda_ordem_faixas", "Compressao_faces", "Transferencia_faces", "Sand_transfer_reserve_min", "Motivo_estado"),
            "tree_governing": ("Panel", "Status", "X+_adopted", "X-_adopted", "Y+_adopted", "Y-_adopted", "util_max", "Transverse_links", "governing_case"),
            "tree_optimization": ("Panel", "Node", "Case", "Optimization_mode", "X+_base", "X+_additional", "X-_base", "X-_additional", "Y+_base", "Y+_additional", "Y-_base", "Y-_additional", "util_max"),
        }
        for name, selected in view_columns.items():
            if tree is getattr(self, name, None):
                cols = [c for c in selected if c in df.columns]
                if cols:
                    df = df[cols]
                break
        # Hide private parsing flags and research-only results in generic detail views.
        if "Sand_status" in getattr(self, "df_results", pd.DataFrame()).columns:
            df = df.loc[:, [c for c in df.columns if not str(c).startswith(("Phys", "__missing_", "ShellQP_", "ShellCap_", "ShellScreen_", "casca_experimental_")) and c != "Estabilidade_global_externa"]]
        cols = list(df.columns)
        tree["columns"] = cols
        for c in cols:
            label = engineering_label(c)
            tree.heading(c, text=label)
            tree.column(c, width=max(78, min(245, len(str(label)) * 8 + 18)), anchor="center")
        tree.tag_configure("row_even", background="#ffffff")
        tree.tag_configure("row_odd", background="#f3f6f9")
        for i, row in enumerate((df if limit is None else df.head(limit)).itertuples(index=False, name=None)):
            vals = []
            for c, v in zip(cols, row):
                if c in ("Status", "Status_global"):
                    v = {"Incompleto":"Condicionado", "OK*":"Cumpre sob hipóteses"}.get(v, v)
                if isinstance(v, float):
                    vals.append("" if not math.isfinite(v) else f"{v:.3f}")
                else:
                    vals.append(str(v))
            tree.insert("", "end", values=vals, tags=("row_even" if i % 2 == 0 else "row_odd",))

    def load_from_textbox(self):
        text = self.txt_paste.get("1.0", "end").strip()
        if not text:
            messagebox.showwarning("Aviso", "Cole primeiro a tabela na caixa de texto.")
            return
        df = parse_pasted_table(text)
        if df.empty:
            messagebox.showwarning("Aviso", "A tabela colada não foi reconhecida.")
            return
        self.load_df(df)

    def paste_clipboard(self):
        try:
            text = self.clipboard_get()
        except Exception:
            messagebox.showwarning("Aviso", "Não foi possível ler a área de transferência.")
            return
        df = parse_pasted_table(text)
        if df.empty:
            messagebox.showwarning("Aviso", "A tabela colada não foi reconhecida.")
            return
        self.txt_paste.delete("1.0", "end")
        self.txt_paste.insert("1.0", text)
        self.load_df(df)

    def import_file(self):
        paths = filedialog.askopenfilenames(
            title="Importar tabela normal e/ou W&A (seleccionar em conjunto)",
            filetypes=[("Excel", "*.xlsx *.xls"), ("CSV", "*.csv"), ("Todos", "*.*")],
        )
        if not paths:
            return
        try:
            tables = []
            for path in paths:
                if path.lower().endswith((".xlsx", ".xls")):
                    tables.append(pd.read_excel(path, dtype=str))
                else:
                    tables.append(read_csv_robust(path))
            df = combine_effort_tables(tables) if len(tables) > 1 else tables[0]
            self.load_df(df)
            self.effort_sources = list(paths)
            self.status_var.set(f"Importação concluída: {len(paths)} tabela(s), {len(self.df_clean)} linhas; pré-visualização até {MAX_PREVIEW_ROWS} linhas. Confirmar unidades e combinações.")
        except Exception as e:
            messagebox.showerror("Erro de importação", str(e))

    def load_df(self, df: pd.DataFrame):
        self.df_external_stability=pd.DataFrame()
        self.df_interlayer=pd.DataFrame()
        cleaned = clean_dataframe(df)
        self.df_raw = df.copy()
        self.df_clean = cleaned
        self.effort_sources = []
        self.df_results = pd.DataFrame()
        self.df_summary = pd.DataFrame()
        self.df_governing = pd.DataFrame()
        self.df_zones = pd.DataFrame()
        self.df_unit_check = pd.DataFrame()
        self.df_detailed = pd.DataFrame()
        self.df_notes = pd.DataFrame()
        self.df_optimization = pd.DataFrame()
        self.df_diagnostic = pd.DataFrame()
        self.df_data_validation = pd.DataFrame()
        self.df_sketches = pd.DataFrame()
        self.show_df(self.tree_input, self.df_clean)
        self.show_df(self.tree_results, self.df_results)
        self.show_df(self.tree_summary, self.df_summary)
        self.show_df(self.tree_governing, self.df_governing)
        self.show_df(self.tree_zones, self.df_zones)
        self.show_df(self.tree_optimization, self.df_optimization)
        self.show_df(self.tree_diagnostic, self.df_diagnostic)
        self.show_df(self.tree_validation, self.df_data_validation)
        self.show_df(self.tree_sketches, self.df_sketches)
        self.show_df(self.tree_unit, self.df_unit_check)
        self.show_df(self.tree_detailed, self.df_detailed)
        self.show_df(self.tree_notes, self.df_notes)
        self.refresh_dashboard()
        self.refresh_geometry()
        self.progress_var.set(0.0)
        format_note = ""
        if not self.df_clean.empty and not self.df_clean["__missing_nmises"].iloc[0]:
            format_note = " NMises é informativo; confirme Nxx, Nyy e Nxy assinados na validação da tabela."
        self.status_var.set(f"Tabela carregada: {len(self.df_clean)} linhas." + format_note)

    def validate_inputs(self) -> Optional[str]:
        if self.df_clean is None or self.df_clean.empty:
            return "Cole ou importe uma tabela de esforços primeiro."
        t = safe_float(self.var_thickness.get(), 0.0)
        c = safe_float(self.var_cover.get(), 0.0)
        if t <= 0:
            return "Espessura inválida."
        if c <= 0 or c >= 0.45 * t:
            return "Recobrimento inválido para a espessura indicada."
        return None

    def build_unit_check(self, df_clean: pd.DataFrame, designer: WallDesigner) -> pd.DataFrame:
        if df_clean is None or df_clean.empty:
            return pd.DataFrame()
        vals_m = []
        vals_q = []
        for c in ["mxx", "myy", "mxy"]:
            if c in df_clean.columns:
                vals_m.extend([abs(v) * designer.moment_factor for v in df_clean[c].dropna().map(lambda x: safe_float(x, 0.0)).tolist()])
        for c in ["qxx", "qyy"]:
            if c in df_clean.columns:
                vals_q.extend([abs(v) * designer.shear_factor for v in df_clean[c].dropna().map(lambda x: safe_float(x, 0.0)).tolist()])
        max_m = max(vals_m) if vals_m else 0.0
        max_q = max(vals_q) if vals_q else 0.0
        notes = []
        if max_m > 1000.0:
            notes.append("Momentos convertidos muito elevados para paredes correntes; confirmar unidades e sinal dos esforços.")
        if 0.0 < max_m < 0.01:
            notes.append("Momentos muito baixos; confirmar se a unidade não deveria ser kNm/m.")
        if max_q > 1500.0:
            notes.append("Esforços transversos muito elevados para paredes correntes; confirmar unidades.")
        if not notes:
            notes.append("Sem anomalias óbvias por ordem de grandeza. Esta verificação não substitui a confirmação das unidades na origem dos resultados.")
        return pd.DataFrame([
            {"Grandeza": "Momentos MXX/MYY/MXY", "Unidade selecionada": designer.moment_unit, "Factor aplicado": designer.moment_factor, "Máximo convertido": max_m, "Unidade interna": "kNm/m", "Nota": notes[0]},
            {"Grandeza": "Corte QXX/QYY", "Unidade selecionada": designer.shear_unit, "Factor aplicado": designer.shear_factor, "Máximo convertido": max_q, "Unidade interna": "kN/m", "Nota": " | ".join(notes)},
            {"Grandeza": "Fendilhação", "Unidade selecionada": "wk seleccionado" if designer.wk_check_enabled else "controlo simplificado", "Factor aplicado": "-", "Máximo convertido": "-", "Unidade interna": "-", "Nota": f"wk só é avaliado para a combinação quase-permanente indicada: {designer.qp_case or 'não indicada'}. Sem selecção, wk não é calculado; fica apenas o controlo indirecto por diâmetro/espaçamento."},
        ])


    def build_data_validation(self, df_clean: pd.DataFrame, designer: WallDesigner) -> pd.DataFrame:
        rows = []
        if df_clean is None or df_clean.empty:
            return pd.DataFrame([{"Categoria": "Tabela", "Item": "linhas", "Estado": "Não conforme", "Resultado": "0", "Nota": "Sem dados importados."}])

        moment_base_cols = ["mxx", "myy", "mxy"]
        moment_wa_cols = ["mxx_pos_wa", "mxx_neg_wa", "myy_pos_wa", "myy_neg_wa"]
        has_base_moments = any(not bool(df_clean.get(f"__missing_{c}", pd.Series([True])).iloc[0]) for c in moment_base_cols if f"__missing_{c}" in df_clean.columns)
        has_wa_moments = all(not bool(df_clean.get(f"__missing_{c}", pd.Series([True])).iloc[0]) for c in moment_wa_cols if f"__missing_{c}" in df_clean.columns)

        required_id = ["panel", "node", "case"]
        for c in required_id:
            estado = "OK" if c in df_clean.columns else "Não conforme"
            rows.append({"Categoria": "Colunas", "Item": c, "Estado": estado, "Resultado": "presente" if estado == "OK" else "em falta", "Nota": "coluna reconhecida" if estado == "OK" else "corrigir cabeçalho ou formato de importação"})

        rows.append({
            "Categoria": "Colunas",
            "Item": "momentos",
            "Estado": "OK" if (has_base_moments or has_wa_moments) else "Não conforme",
            "Resultado": "MXX/MYY/MXY" if has_base_moments else ("Wood-Armer M+/M-" if has_wa_moments else "em falta"),
            "Nota": "se forem importados M+/M- de Wood-Armer, o programa usa esses valores directamente e não reaplica MXY",
        })
        for c in ("nxx", "nyy", "nxy", "mxx", "myy", "mxy", "qxx", "qyy"):
            missing = df_clean.get(f"__missing_{c}", pd.Series(c not in df_clean.columns, index=df_clean.index)).fillna(True).astype(bool)
            if c not in df_clean.columns: missing[:] = True
            absent = int(missing.sum())
            rows.append({"Categoria": "Colunas", "Item": c.upper(), "Estado": "OK" if absent == 0 else "Verificar", "Resultado": "presente" if absent == 0 else f"{absent}/{len(df_clean)} linhas em falta", "Nota": "Componente necessária ao tensor da casca; ausência não equivale a zero" if absent else "coluna reconhecida"})

        n_lines = len(df_clean)
        n_panels = df_clean["panel"].astype(str).nunique() if "panel" in df_clean.columns else 0
        n_cases = df_clean["case_id"].astype(str).nunique() if "case_id" in df_clean.columns else 0
        rows.append({"Categoria": "Tabela", "Item": "linhas", "Estado": "OK" if n_lines > 0 else "Não conforme", "Resultado": n_lines, "Nota": "número de linhas importadas"})
        rows.append({"Categoria": "Tabela", "Item": "painéis", "Estado": "OK" if n_panels > 0 else "Verificar", "Resultado": n_panels, "Nota": "painéis distintos detectados"})
        rows.append({"Categoria": "Tabela", "Item": "combinações", "Estado": "OK" if n_cases > 0 else "Verificar", "Resultado": n_cases, "Nota": "casos/combinações distintos detectados"})

        if designer.wk_check_enabled:
            qp = designer.qp_case
            if not qp:
                rows.append({"Categoria": "ELS", "Item": "combinação quase-permanente", "Estado": "Não conforme", "Resultado": "não indicada", "Nota": "wk seleccionado sem número de combinação quase-permanente"})
            else:
                mask = df_clean["case"].map(designer.is_qp_case) if "case" in df_clean.columns else pd.Series(False, index=df_clean.index)
                n_qp = int(mask.sum())
                panels_qp = df_clean.loc[mask, "panel"].astype(str).nunique() if n_qp else 0
                missing_panels = []
                if "panel" in df_clean.columns and n_qp:
                    all_p = set(df_clean["panel"].astype(str))
                    qp_p = set(df_clean.loc[mask, "panel"].astype(str))
                    missing_panels = sorted(all_p - qp_p)
                estado = "OK" if n_qp > 0 and not missing_panels else ("Verificar" if n_qp > 0 else "Não conforme")
                rows.append({"Categoria": "ELS", "Item": "combinação quase-permanente", "Estado": estado, "Resultado": f"{qp}: {n_qp} linhas; {panels_qp}/{n_panels} painéis", "Nota": ("encontrada em todos os painéis" if not missing_panels and n_qp else f"painéis sem QP: {', '.join(missing_panels[:12])}" if missing_panels else "combinação não encontrada")})

        # Coerência básica de ordem de grandeza, após conversão.
        max_m = max([df_clean[c].abs().max() * designer.moment_factor for c in ["mxx", "myy", "mxy"] if c in df_clean.columns] or [0])
        max_q = max([df_clean[c].abs().max() * designer.shear_factor for c in ["qxx", "qyy"] if c in df_clean.columns] or [0])
        rows.append({"Categoria": "Unidades", "Item": "momentos", "Estado": "Verificar" if max_m > 1000 or (0 < max_m < 0.01) else "OK", "Resultado": f"max |M| = {max_m:.3f} kNm/m", "Nota": "confirmar unidades se valor estiver fora da ordem corrente"})
        rows.append({"Categoria": "Unidades", "Item": "corte", "Estado": "Verificar" if max_q > 1500 else "OK", "Resultado": f"max |Q| = {max_q:.3f} kN/m", "Nota": "confirmar unidades se valor estiver fora da ordem corrente"})
        rows.append({"Categoria": "Eixos locais", "Item": "orientação", "Estado": "OK*" if designer.swap_local_axes else "Verificar", "Resultado": "X/Y trocados" if designer.swap_local_axes else ("Y local = vertical" if designer.local_y_is_vertical else "X local = vertical"), "Nota": "confirmar orientação dos eixos locais e da normal dos painéis antes de desenhar armaduras"})
        return pd.DataFrame(rows)

    def build_diagnostic(self, results: pd.DataFrame, validation: pd.DataFrame) -> pd.DataFrame:
        rows = []
        def add(panel, sev, problem, action, source="Cálculo"):
            rows.append({"Painel": panel, "Severidade": sev, "Problema": problem, "Acção recomendada": action, "Origem": source})

        if validation is not None and not validation.empty:
            for _, r in validation.iterrows():
                estado = str(r.get("Estado", ""))
                if estado in ("Verificar", "Não conforme", "OK*"):
                    sev = "Alta" if estado == "Não conforme" else ("Média" if estado == "Verificar" else "Baixa")
                    add("-", sev, f"{r.get('Categoria','')} - {r.get('Item','')}: {r.get('Resultado','')}", r.get("Nota", ""), source="Validação da tabela")

        if results is None or results.empty:
            return pd.DataFrame(rows)
        for panel, g in results.groupby("Panel", dropna=False):
            # Estado mais gravoso por painel
            statuses = set(str(x) for x in g.get("Status", pd.Series(dtype=str)).dropna())
            if "Não conforme" in statuses:
                r = g.loc[g["Status"].eq("Não conforme")].iloc[0]
                add(panel, "Alta", r.get("Verification_reason", "Não conforme"), r.get("Recommended_action", "rever dimensionamento"))
            elif "Verificar" in statuses and "Sand_status" not in g:
                r = g.loc[g["util_max"].fillna(-1).idxmax()]
                add(panel, "Média", r.get("Verification_reason", "Verificar"), r.get("Recommended_action", "validar manualmente"))
            elif "OK*" in statuses:
                r = g.loc[g["util_max"].fillna(-1).idxmax()]
                add(panel, "Baixa", r.get("Verification_reason", "OK com aviso"), r.get("Recommended_action", "confirmar notas"))

            if "Sand_status" in g:
                e=g[g.Combo_type.eq("ELU")]
                intact=e.get("Sand_intact_candidate",pd.Series(False,index=e.index)).eq(True)
                invalid=~intact & e.Sand_status.str.contains("não satisfeito|Sem equilíbrio|indisponível|Dados insuficientes",regex=True,na=False)
                if invalid.any():
                    r=e.loc[invalid].sort_values("Sand_util",ascending=False).iloc[0];add(panel,"Alta",f"Sandwich: {int(invalid.sum())} linhas sem verificação demonstrada; nó {r.Node}, caso {r.Case}","Rever espessura, classe de betão e distribuição de esforços quando governa o betão; reforçar aço apenas quando governa a armadura.")
                if e.get("Sand_Asw_req_mm2_m2",pd.Series(dtype=float)).gt(0).any():add(panel,"Alta","Sandwich: armadura de corte requerida","Dimensionar e pormenorizar as ligações, confirmar amarração")
                conditional=e.Sand_status.str.contains("6.109 não demonstrado",regex=False,na=False)
                conditional &= ~intact
                if conditional.any():add(panel,"Alta",f"Sandwich: {int(conditional.sum())} linhas com condição 6.109 não demonstrada","Confirmar campo de compressão; limite de triagem não é aprovação")
            if "Sand_status" not in g and "MXY_ratio" in g.columns and g["MXY_ratio"].max() > 0.40:
                add(panel, "Média", f"MXY dominante: ratio máximo = {g['MXY_ratio'].max():.2f}", "confirmar eixos locais, orientação da normal e método adoptado para MXY")
            if "is_QP_crack_case" in g.columns and "Sim" not in set(g["is_QP_crack_case"].astype(str)):
                # Só é problema se wk foi activado; neste caso a coluna QP existe, mas o caso não apareceu no painel.
                if "wk_check_enabled" in g.columns and "Sim" in set(g["wk_check_enabled"].astype(str)):
                    add(panel, "Média", "sem linha da combinação quase-permanente para verificação wk", "exportar/colar também a combinação quase-permanente de ELS")
        if not rows:
            rows.append({"Painel": "-", "Severidade": "Informação", "Problema": "sem problemas críticos detectados", "Acção recomendada": "validar hipóteses gerais, eixos locais e modelo estrutural", "Origem": "Diagnóstico"})
        order = {"Alta": 0, "Média": 1, "Baixa": 2, "Informação": 3}
        out = pd.DataFrame(rows)
        out["_ord"] = out["Severidade"].map(order).fillna(9)
        return out.sort_values(["_ord", "Painel"]).drop(columns=["_ord"]).reset_index(drop=True)

    def build_rebar_sketches(self, zones: pd.DataFrame) -> pd.DataFrame:
        if zones is None or zones.empty:
            return pd.DataFrame()
        rows = []
        for _, r in zones.iterrows():
            sketch = (
                f"Zona {r.get('Zona','')} | Painéis: {r.get('Painéis','')}\n"
                f"Face +: X = {r.get('X+','-')} | Y = {r.get('Y+','-')}\n"
                f"Face -: X = {r.get('X-','-')} | Y = {r.get('Y-','-')}\n"
                f"Nota: armaduras adicionais devem ser intercaladas com a armadura base, mantendo o mesmo espaçamento da base."
            )
            rows.append({"Zona": r.get("Zona", ""), "Painéis": r.get("Painéis", ""), "Croquis_textual": sketch, "Nota_desenho": "Face +/− depende da normal local do painel; confirmar antes de desenhar."})
        return pd.DataFrame(rows)

    def build_detailed_check(self, results: pd.DataFrame) -> pd.DataFrame:
        if results is None or results.empty:
            return pd.DataFrame()
        cols = [
            "Panel", "Node", "Case", "Combo_type", "MXX_kNm_m", "MYY_kNm_m", "MXY_kNm_m",
            "Mx+_WA", "Mx-_WA", "My+_WA", "My-_WA", "WA_method",
            "Asx+_req_mm2_m", "Asx-_req_mm2_m", "Asy+_req_mm2_m", "Asy-_req_mm2_m",
            "As_slab_min_face_mm2_m", "As_crack_min_face_mm2_m", "X+_rebar", "X-_rebar", "Y+_rebar", "Y-_rebar",
            "MRd_x+_kNm_m", "MRd_x-_kNm_m", "MRd_y+_kNm_m", "MRd_y-_kNm_m",
            "QXX_kN_m", "QYY_kN_m", "VRdc_x_kN_m", "VRdc_y_kN_m", "VRdmax_x_kN_m", "VRdmax_y_kN_m",
            "wk_x+_mm", "wk_x-_mm", "wk_y+_mm", "wk_y-_mm", "wk_max_mm", "wk_partial_max_mm", "wk_faces_evaluated", "wmax_mm",
            "sigma_s_x+_MPa", "sigma_s_x-_MPa", "sigma_s_y+_MPa", "sigma_s_y-_MPa",
            "phi_ctrl_x+_mm", "s_eff_x+_mm", "phi_lim_x+_EC2_mm", "s_lim_x+_EC2_mm",
            "phi_ctrl_x-_mm", "s_eff_x-_mm", "phi_lim_x-_EC2_mm", "s_lim_x-_EC2_mm",
            "phi_ctrl_y+_mm", "s_eff_y+_mm", "phi_lim_y+_EC2_mm", "s_lim_y+_EC2_mm",
            "phi_ctrl_y-_mm", "s_eff_y-_mm", "phi_lim_y-_EC2_mm", "s_lim_y-_EC2_mm",
            "Crack_status_x+", "Crack_status_x-", "Crack_status_y+", "Crack_status_y-",
            "util_M", "util_Qx", "util_Qy", "util_max", "Status", "Verification_reason", "Recommended_action", "Notes"
        ]
        if "Sand_status" in results:cols += [c for c in results if c.startswith(("Sand_","ELS_sigma_","ELS_fctk","ELS_historico","ELS_cargas","wk_cargas_cond"))]
        out = results[[c for c in cols if c in results.columns]].copy()
        out["Formula_As"] = "As = MEd/(0,87*fyd*z), z≈0,9d; mínimos EC2 9.6, 9.3.1.1 e 7.3.2 aplicados por face"
        out["Formula_VRdc"] = "VRd,c = [CRdc*k*(100*rho*fck)^(1/3)]*b*d, com vmin; faixa b=1000 mm"
        out["Formula_wk"] = "wk = sr,max*(eps_sm-eps_cm), usando As final real da face traccionada; verificar apenas com ELS quase-permanente"
        return out

    @staticmethod
    def panel_outcome(g):
        elu = g[g["Combo_type"].eq("ELU")]
        qp = g[g["Combo_type"].eq("ELS-QP")]
        states = set(g["Status"].dropna())
        notes = []
        exceeded = []
        for col, name in (("util_M", "Flexão/N–M"), ("util_Qx", "Corte X sem armadura específica"), ("util_Qy", "Corte Y sem armadura específica")):
            if elu[col].gt(1).any():
                exceeded.append(name)
        if qp["wk_max_mm"].gt(qp["wmax_mm"]).any() or ("wk_partial_max_mm" in qp and qp["wk_partial_max_mm"].gt(qp["wmax_mm"]).any()):
            exceeded.append("wk (valor calculado, mesmo com cobertura parcial)")
        if "Não conforme" in states:
            bad=g.loc[g["Status"].eq("Não conforme")]
            first=bad.iloc[0]
            # Do not obscure a service/detailing failure behind the ELU governing row.
            cause=str(first.get("Verification_reason", "não conformidade de linha"))
            exceeded.append(f"{first.get('Combo_type','')} — nó {first.get('Node','?')}, caso {first.get('Case','?')}: {cause}")
        if not len(elu):
            notes.append("ELU por classificar")
        if len(qp):
            if "Sand_status" in elu and (qp.get("Crack_control_status",pd.Series(index=qp.index,dtype=str)).eq("Verificar") & (qp.wk_max_mm.notna() | qp.get("wk_partial_max_mm",pd.Series(index=qp.index,dtype=float)).gt(0))).any():
                notes.append("Controlo de fendilhação convencional: verificar critérios de tensão e armadura mínima")
            n = int(qp["wk_max_mm"].isna().sum())
            if n:
                conditional = int((qp["wk_max_mm"].isna() & qp.get("wk_cargas_cond_mm", pd.Series(index=qp.index,dtype=float)).eq(0)).sum())
                if conditional: notes.append(f"ELS: {conditional}/{len(qp)} QP sem fendilhação por cargas (condicional); confirmar coacção/histórico")
                if n > conditional: notes.append(f"wk pendente ({n-conditional}/{len(qp)} QP)")
        elif "Sand_status" not in elu or g.get("wk_check_enabled",pd.Series(dtype=str)).eq("Sim").any():
            notes.append("Sem QP")
        if "Sand_status" in elu:
            # The elastic LL route is conditional, not proof of the history.
            # Do not let unneeded cracked-model diagnostics govern it.
            intact=elu.get('Sand_intact_candidate',pd.Series(False,index=elu.index)).eq(True)
            cracked=elu.loc[~intact]
            if cracked.Sand_status.str.contains("não satisfeito|Sem equilíbrio|indisponível|Dados insuficientes",regex=True,na=False).any():
                notes.append("modelo sandwich: resistência não demonstrada em todas as linhas")
            if elu.get("Sand_Asw_req_mm2_m2",pd.Series(dtype=float)).gt(0).any():
                notes.append("sandwich: armadura transversal requerida; verificar pormenorização")
            if cracked.Sand_status.str.contains("6.109 não demonstrado",regex=False,na=False).any():
                notes.append("Resistência dos campos comprimidos (6.109) não demonstrada")
            if "Sand_transfer_status" in cracked and cracked.Sand_transfer_status.str.startswith("LL.115",na=False).any():
                notes.append("Corte adicional intercamadas: requer verificação complementar LL(115)(c)")
            if elu.get("Sand_strip_order_status",pd.Series(dtype=str)).eq("Dados locais pendentes").any():
                notes.append("incrementos de segunda ordem por faixa pendentes")
            if elu.util_max.isna().any() or elu.Status.eq('Dados insuficientes').any():
                notes.append('verificação local sem resultado')
            if elu.get('Sand_util',pd.Series(index=elu.index,dtype=float)).isna().any():
                notes.append('modelo sandwich: linhas sem resultado')
        elif elu["NXY_kN_m"].abs().gt(1e-9).any():
            notes.append("membrana Nxy por verificar")
        elif elu["MXY_kNm_m"].abs().gt(1e-9).any():
            notes.append("interacção de casca com Mxy por verificar")
        if "Screen_ratio_max" in elu and elu.Screen_ratio_max.gt(1+1e-9).any():
            notes.append("diagnóstico de tracção da casca > 1")
        if "Screen_ratio_concrete" in elu and elu.Screen_ratio_concrete.gt(1+1e-9).any():
            notes.append("diagnóstico de compressão da casca > 1")
        if "Capacity_trial_status" in elu and elu.Capacity_trial_status.str.contains("Sem solução",regex=False).any():
            notes.append("casca: sem solução no modelo resistente idealizado")
        if "PhysShear_util" in elu and elu.PhysShear_util.gt(1+1e-7).any():
            notes.append("corte resultante sem crédito de compressão: triagem experimental acima de 1")
        if "PhysLL_util" in elu and elu.PhysLL_util.gt(1+1e-7).any():
            notes.append("ensaio LL: armadura específica de corte a verificar")
        if "PhysLL_util" in elu and elu.PhysLL_util.isna().any():
            notes.append("ensaio LL: linhas sem resultado")
        if "Core_status" in elu and elu.Core_status.str.contains("Sem solução|indisponível|Dados insuficientes",regex=True,na=False).any():
            notes.append("ensaio de núcleo/camadas: solução não demonstrada")
        if "PhysELU_util" in elu and elu.PhysELU_util.gt(1+1e-7).any():
            notes.append("casca física: capacidade experimental insuficiente")
        if "PhysELU_util" in elu and elu.PhysELU_util.isna().any():
            notes.append("casca física: linhas sem resultado")
        if any(c in qp and qp[c].gt(1).any() for c in ("PhysELS_ratio_c_045fck","PhysCracked_ratio_c_045fck")):
            notes.append("ensaio ELS: rever fluência não linear")
        if "PhysCracked_ratio_s_08fyk" in g and g.PhysCracked_ratio_s_08fyk.gt(1).any():
            notes.append("ensaio CAR fendilhado: tensão do aço acima de 0,8 fyk")
        if "PhysQP_candidate_max_mm" in qp and qp.PhysQP_candidate_max_mm.gt(qp.wmax_mm).any():
            notes.append("indicador QP de abertura acima de wmax; não é wk")
        if any(c in qp and qp[c].gt(qp.wmax_mm).any() for c in ("PhysQP_Tan31_candidate_plus_mm","PhysQP_Tan31_candidate_minus_mm")):
            notes.append("sensibilidade QP com extensão de corte acima de wmax; não é wk")
        if "PhysShared_status" in elu and elu.PhysShared_status.str.contains("Sem equilíbrio|Sem capacidade|Sem proposta|indisponível",regex=True,na=False).any():
            notes.append("campo partilhado de núcleo: equilíbrio/proposta não demonstrados")
        if "Tensor_complete" in elu and not elu.Tensor_complete.eq(True).all():
            notes.append("tensor assinado ELU incompleto")
        service = g[g["Combo_type"].isin(["ELS-CAR", "ELS-FREQ", "ELS-QP"])]
        if "Tensor_complete" in service and not service.Tensor_complete.eq(True).all():
            notes.append("tensor assinado ELS incompleto")
        if "Case" in g and g.Case.astype(str).str.contains(r"CQC|SRSS", case=False, regex=True).any():
            notes.append("combinações modais: sinais e concomitância por confirmar")
        if "Case_coverage" in g and g.Case_coverage.eq("Incompleto").any():
            missing = sorted({x for v in g.get("Case_missing",pd.Series(dtype=str)).astype(str) for x in v.split()}, key=lambda x:(len(x),x))
            notes.append("cobertura de combinações incompleta: " + format_case_ranges(missing) if missing else "cobertura de combinações incompleta por nó")
        if elu["Verification_reason"].str.contains("definir l0", case=False, na=False).any():
            notes.append("segunda ordem: falta l0")
        if elu["Verification_reason"].str.contains("fluência não determinada",case=False,na=False).any():
            notes.append("segunda ordem: falta fluência")
        if g["Combo_type"].isin(["ELS-CAR", "ELS-FREQ"]).any():
            stress=g[g.Combo_type.isin(["ELS-CAR","ELS-QP"])].get("ELS_72_estado",pd.Series(dtype=str))
            if stress.empty or not stress.str.startswith("Limites satisfeitos").all():
                notes.append("ELS CAR/FREQ parciais")
            else:notes.append("Tensões ELS satisfeitas nos modelos aplicáveis; confirmar histórico/coacção")
        if exceeded:
            return "Não conforme", "; ".join(exceeded + notes)
        if "Sand_status" in elu and len(elu):
            assumptions=[n for n in notes if n.startswith(("ELS: ","Tensões ELS satisfeitas","combinações modais:"))]
            pending=[n for n in notes if n not in assumptions]
            # Scope only: the modal-sign and load-history assumptions are
            # explicit, not mechanically verified by this sectional tool.
            if not pending:
                return "OK*", "Limites seccionais satisfeitos sob hipóteses de cálculo; consultar notas gerais"
            return "Incompleto", "; ".join(pending)
        if notes:
            return "Incompleto", "; ".join(notes)
        for st in ("Dados insuficientes", "Verificar", "OK*"):
            if st in states:
                return st, "Consultar detalhe por linha"
        return "OK*", "Cumpre verificações locais implementadas; estabilidade global não avaliada"

    def build_panel_summary(self, results: pd.DataFrame) -> pd.DataFrame:
        if results is None or results.empty:
            return pd.DataFrame()
        rows = []
        for panel, grp in results.groupby("Panel", dropna=False):
            g = grp.copy()
            elu = g[g["Combo_type"].eq("ELU")]
            def peak(col):
                values = elu[col].dropna()
                return elu.loc[values.idxmax()] if not values.empty else {}
            r_util, r_m, r_qx, r_qy = (peak(c) for c in ("util_max", "util_M", "util_Qx", "util_Qy"))
            status, panel_reason = WallsEC2App.panel_outcome(g)
            notes = sorted({str(x) for x in g.get("Notes", pd.Series(dtype=str)).dropna() if str(x).strip()})
            reasons = sorted({str(x) for x in g.get("Verification_reason", pd.Series(dtype=str)).dropna() if str(x).strip()})
            actions = sorted({str(x) for x in g.get("Recommended_action", pd.Series(dtype=str)).dropna() if str(x).strip()})
            rows.append({
                "Panel": panel,
                "n_linhas_analisadas": len(g),
                "Status_global": status,
                **panel_scope_fields(g),
                "ELU_faixas": ("Não conforme" if elu["util_max"].gt(1).any() or elu.Status.eq("Não conforme").any() else "Limites calculados satisfeitos" if len(elu) and elu["util_max"].notna().all() else "Sem resultado"),
                "wk_cargas_cond_QP": int(g.get("wk_cargas_cond_mm",pd.Series(index=g.index,dtype=float)).eq(0).sum()),
                "Estabilidade_global_externa": "Não avaliada",
                "Motivo_estado": panel_reason,
                "Acção_recomendada": " | ".join(actions[:5]),
                "util_max": elu["util_max"].max(),
                "caso_governante": r_util.get("Case", ""),
                "node_governante": r_util.get("Node", ""),
                "util_M_max": elu["util_M"].max(),
                "caso_governante_M": r_m.get("Case", ""),
                "node_governante_M": r_m.get("Node", ""),
                "util_Qx_max": elu["util_Qx"].max(),
                "caso_governante_Qx": r_qx.get("Case", ""),
                "node_governante_Qx": r_qx.get("Node", ""),
                "util_Qy_max": elu["util_Qy"].max(),
                "util_N_prelim_max": g["util_N_prelim"].max() if "util_N_prelim" in g.columns else 0.0,
                "sigma_N_vertical_max_MPa": g["sigma_N_vertical_MPa"].max() if "sigma_N_vertical_MPa" in g.columns else 0.0,
                "caso_governante_Qy": r_qy.get("Case", ""),
                "node_governante_Qy": r_qy.get("Node", ""),
                "MXX_abs_max_kNm_m": g["MXX_kNm_m"].abs().max(),
                "MYY_abs_max_kNm_m": g["MYY_kNm_m"].abs().max(),
                "MXY_abs_max_kNm_m": g["MXY_kNm_m"].abs().max(),
                "QXX_abs_max_kN_m": g["QXX_kN_m"].abs().max(),
                "QYY_abs_max_kN_m": g["QYY_kN_m"].abs().max(),
                "Asx_req_max_mm2_m": max(g["Asx+_req_mm2_m"].max(), g["Asx-_req_mm2_m"].max()),
                "Asy_req_max_mm2_m": max(g["Asy+_req_mm2_m"].max(), g["Asy-_req_mm2_m"].max()),
                "X+_max_rebar": r_util.get("X+_rebar", ""),
                "X-_max_rebar": r_util.get("X-_rebar", ""),
                "Y+_max_rebar": r_util.get("Y+_rebar", ""),
                "Y-_max_rebar": r_util.get("Y-_rebar", ""),
                "Transverse_links": "Sim" if (g["Transverse_links_required"] == "Sim").any() else "Não",
                "Notas": " | ".join(notes[:4]),
                "Asw_X_req_mm2_m2": elu.get("ShearDesign_X_asw_mm2_m2", pd.Series(dtype=float)).max(),
                "Asw_Y_req_mm2_m2": elu.get("ShearDesign_Y_asw_mm2_m2", pd.Series(dtype=float)).max(),
                "Sand_caso_governante": (elu.loc[elu.Sand_util.idxmax(),"Case"] if "Sand_util" in elu and elu.Sand_util.notna().any() else ""),
                "Sand_no_governante": (elu.loc[elu.Sand_util.idxmax(),"Node"] if "Sand_util" in elu and elu.Sand_util.notna().any() else ""),
                "Sand_util_max": elu.get("Sand_util",pd.Series(dtype=float)).max(),
                "Sand_steel_util_max": elu.get("Sand_steel_util",pd.Series(dtype=float)).max(),
                "Sand_concrete_util_max": elu.get("Sand_concrete_util",pd.Series(dtype=float)).max(),
                "Sand_shear_util_max": elu.get("Sand_shear_util",pd.Series(dtype=float)).max(),
                "Sand_Asw_req_max_mm2_m2": elu.get("Sand_Asw_req_mm2_m2",pd.Series(dtype=float)).max(),
                "Sand_linhas_acima_1": int(elu.get("Sand_util",pd.Series(dtype=float)).gt(1+1e-7).sum()),
                "Sand_linhas_sem_resultado": int(elu.get("Sand_util",pd.Series(index=elu.index,dtype=float)).isna().sum()) if "Sand_status" in elu else 0,
                "Sand_linhas_trelica": int(elu.get("Sand_Asw_req_mm2_m2",pd.Series(dtype=float)).gt(0).sum()),
                "Sand_linhas_6109_pendentes": int(elu.get("Sand_status",pd.Series(dtype=str)).str.contains("6.109 não demonstrado",regex=False,na=False).sum()),
                "Sand_linhas_LL115_pendentes": int(elu.get("Sand_transfer_status",pd.Series(dtype=str)).str.startswith("LL.115",na=False).sum()),
                "LL_util_resultante": elu.get("PhysLL_util", pd.Series(dtype=float)).max(),
                "LL_util_sem_credito": elu.get("PhysLL_util_sem_credito", pd.Series(dtype=float)).max(),
                "LL_Asw_proposta_mm2_m2": elu.get("PhysLL_Asw_req_mm2_m2", pd.Series(dtype=float)).max(),
                "LL_linhas_acima_1": int(elu.get("PhysLL_util", pd.Series(dtype=float)).gt(1+1e-7).sum()),
                "LL_equilibrio_faces_util": elu.get("PhysLL_Face_util_com_trelica", pd.Series(dtype=float)).max(),
                "QP_indicadores_duas_faces": int(g.loc[g.Combo_type.eq("ELS-QP")].get("PhysQP_complete_candidate",pd.Series(dtype=bool)).eq(True).sum()),
                "Core_linhas_ensaiadas": int(elu.get("Core_status",pd.Series(dtype=str)).notna().sum()),
                "Core_linhas_sem_solucao": int(elu.get("Core_status",pd.Series(dtype=str)).str.contains("Sem solução|indisponível|Dados insuficientes",regex=True,na=False).sum()),
                "Core_Asw_proposta_max_mm2_m2": elu.get("Core_asw_proposed",pd.Series(dtype=float)).max(),
                "Asym_linhas_ensaiadas": int(elu.get("Asym_status",pd.Series(dtype=str)).notna().sum()),
                "Asym_util_max": elu.get("Asym_face_util",pd.Series(dtype=float)).max(),
                "AsymTruss_linhas_ensaiadas": int(elu.get("AsymTruss_status",pd.Series(dtype=str)).notna().sum()),
                "AsymTruss_util_max": elu.get("AsymTruss_face_util",pd.Series(dtype=float)).max(),
                "AsymTruss_Asw_proposta_max_mm2_m2": elu.get("AsymTruss_asw_proposed",pd.Series(dtype=float)).max(),
                "QP_sem_excedencia_fctk005_duas_faces": int((g.get("History_plus_wk_conditional_mm",pd.Series(index=g.index,dtype=float)).eq(0)&g.get("History_minus_wk_conditional_mm",pd.Series(index=g.index,dtype=float)).eq(0)&g.Combo_type.eq("ELS-QP")).sum()),
                "casca_experimental_max": elu.get("PhysELU_util", pd.Series(dtype=float)).max(),
                "casca_linhas_acima_1": int(elu.get("PhysELU_util", pd.Series(dtype=float)).gt(1+1e-7).sum()),
                "wk_QP_avaliadas": int(g.loc[g.Combo_type.eq("ELS-QP"),"wk_max_mm"].notna().sum()),
                "wk_QP_total": int(g.Combo_type.eq("ELS-QP").sum()),
                "Diagnostico_casca_ratio_max": elu.get("Screen_ratio_max", pd.Series(dtype=float)).max(),
                "Diagnostico_casca_linhas_acima_1": int(elu.get("Screen_ratio_max", pd.Series(dtype=float)).gt(1).sum()),
            })
        summary=pd.DataFrame(rows).sort_values(["Status_global", "Panel"], ascending=[False, True]).reset_index(drop=True)
        if "Sand_status" in results:
            summary=summary.drop(columns=[c for c in summary if c.startswith(("LL_","Core_","Asym_","AsymTruss_","casca_","Diagnostico_casca_","QP_indicadores_","QP_sem_excedencia_"))])
        return summary

    def build_governing_design(self, results: pd.DataFrame) -> pd.DataFrame:
        if results is None or results.empty:
            return pd.DataFrame()
        rows = []
        for panel, g in results.groupby("Panel", dropna=False):
            gx = g.copy()
            elu = gx[gx["Combo_type"].eq("ELU")]
            def row_at_max(col):
                return elu.loc[elu[col].fillna(-1.0).idxmax()] if not elu.empty else {}
            def adopted_row(col):
                # Keep the final common mesh, including possible ELS reinforcement.
                return gx.loc[gx[col].fillna(-1.0).idxmax()]
            rxp = adopted_row("Asx+_prov_mm2_m")
            rxn = adopted_row("Asx-_prov_mm2_m")
            ryp = adopted_row("Asy+_prov_mm2_m")
            ryn = adopted_row("Asy-_prov_mm2_m")
            r_util = row_at_max("util_max")
            status, panel_reason = WallsEC2App.panel_outcome(gx)
            actions = sorted({str(x) for x in gx.get("Recommended_action", pd.Series(dtype=str)).dropna() if str(x).strip()})
            rows.append({
                "Panel": panel,
                "Status": status,
                "Motivo_estado": panel_reason,
                "Acção_recomendada": " | ".join(actions[:5]),
                "util_max": elu["util_max"].max(),
                "governing_case": r_util.get("Case", ""),
                "governing_node": r_util.get("Node", ""),
                "governing_role": r_util.get("Combo_type", ""),
                **{f"{face}_ELU_{key.lower()}": row_at_max(f"As{face.lower()}_req_mm2_m").get(key, "")
                   for face in ("X+", "X-", "Y+", "Y-") for key in ("Case", "Node")},
                "X+_adopted": rxp.get("X+_rebar", ""),
                "Asx+_req_max_mm2_m": elu["Asx+_req_mm2_m"].max(),
                "Asx+_prov_mm2_m": rxp.get("Asx+_prov_mm2_m", 0.0),
                "X-_adopted": rxn.get("X-_rebar", ""),
                "Asx-_req_max_mm2_m": elu["Asx-_req_mm2_m"].max(),
                "Asx-_prov_mm2_m": rxn.get("Asx-_prov_mm2_m", 0.0),
                "Y+_adopted": ryp.get("Y+_rebar", ""),
                "Asy+_req_max_mm2_m": elu["Asy+_req_mm2_m"].max(),
                "Asy+_prov_mm2_m": ryp.get("Asy+_prov_mm2_m", 0.0),
                "Y-_adopted": ryn.get("Y-_rebar", ""),
                "Asy-_req_max_mm2_m": elu["Asy-_req_mm2_m"].max(),
                "Asy-_prov_mm2_m": ryn.get("Asy-_prov_mm2_m", 0.0),
                "Transverse_links": "Sim" if (gx["Transverse_links_required"] == "Sim").any() else "Não",
                "Transverse_links_note": " | ".join(sorted(set(str(x) for x in gx["Transverse_links_note"].dropna() if str(x).strip()))[:2]),
                "Design_note": "Caso e áreas requeridas: ELU explícitos. A malha final por face pode incluir reforço de serviço."
            })
        return pd.DataFrame(rows).sort_values(["Status", "Panel"], ascending=[False, True]).reset_index(drop=True)

    @staticmethod
    def build_nm_envelope(results):
        columns = ["Panel", "Node", "Case", "Direcção", "NEd [kN/m]", "MEd [kNm/m]",
                   "MRd [kNm/m]", "Util. N-M", "Estado da faixa", "Segunda ordem"]
        rows = []
        elu = results[results["Combo_type"].eq("ELU")]
        for panel, group in elu.groupby("Panel", sort=True):
            for axis in ("X", "Y"):
                u = group[f"NM_{axis}_util"].dropna()
                if u.empty:
                    rows.append(dict(Panel=panel, Direcção=axis, **{"Estado da faixa": "Não avaliado"}))
                    continue
                r = group.loc[u.idxmax()]
                util = r[f"NM_{axis}_util"]
                if f"Stability_{axis}_status" in group:
                    order=str(r[f"Stability_{axis}_status"])
                else:
                    order = "Não requerida (N ≤ 0)" if not group[f"NM_{axis}_NEd"].gt(0).any() else ("Incluída" if r["Stability_l0_mm"] > 0 else "Pendente: l0")
                rows.append(dict(Panel=panel, Node=r.Node, Case=r.Case, Direcção=axis, **{
                    "NEd [kN/m]": r[f"NM_{axis}_NEd"], "MEd [kNm/m]": r[f"NM_{axis}_MEd"],
                    "MRd [kNm/m]": r[f"NM_{axis}_MRd"], "Util. N-M": util,
                    "Estado da faixa": ("Cumpre (1.ª ordem)" if order.startswith("Pendente") else "Cumpre") if util <= 1+1e-6 else "Não conforme",
                    "Segunda ordem": order}))
        return pd.DataFrame(rows, columns=columns)

    @staticmethod
    def build_stability_coverage(results):
        rows=[]
        elu=results[results.Combo_type.eq("ELU")]
        for panel,g in elu.groupby("Panel"):
            for axis in "XY":
                col=f"Stability_{axis}_status"
                if col not in g: continue
                for status,n in g[col].fillna("Não avaliado").value_counts().items():
                    rows.append(dict(Panel=panel,Direcção=axis,Estado=status,Linhas=int(n)))
        return pd.DataFrame(rows)

    def build_rebar_zones(self, governing: pd.DataFrame) -> pd.DataFrame:
        if governing is None or governing.empty:
            return pd.DataFrame()
        keys = ["X+_adopted", "X-_adopted", "Y+_adopted", "Y-_adopted", "Transverse_links"]
        rows = []
        for i, (key_vals, grp) in enumerate(governing.groupby(keys, dropna=False), start=1):
            panels = [str(p) for p in grp["Panel"].tolist()]
            worst_util = grp["util_max"].max() if "util_max" in grp.columns else 0.0
            status_values = set(str(x) for x in grp.get("Status", pd.Series(dtype=str)).dropna())
            if "Não conforme" in status_values:
                status = "Não conforme"
            elif "Incompleto" in status_values:
                status = "Incompleto"
            elif "Verificar" in status_values:
                status = "Verificar"
            elif "OK*" in status_values:
                status = "OK*"
            else:
                status = "OK"
            rows.append({
                "Zona": f"Z{i}",
                "Painéis": ", ".join(panels),
                "n_paineis": len(panels),
                "Status": status,
                "util_max": worst_util,
                "X+": key_vals[0],
                "X-": key_vals[1],
                "Y+": key_vals[2],
                "Y-": key_vals[3],
                "Armadura transversal": key_vals[4],
                "Nota": "Agrupamento por solução adoptada; validar continuidade e compatibilização com desenho de armaduras."
            })
        return pd.DataFrame(rows).sort_values(["Status", "Zona"], ascending=[False, True]).reset_index(drop=True)

    def build_rebar_optimization(self, results: pd.DataFrame) -> pd.DataFrame:
        if results is None or results.empty:
            return pd.DataFrame()
        cols = [
            "Panel", "Node", "Case", "Status", "Optimization_mode", "Optimization_iterations",
            "X+_base", "X+_additional", "X+_rebar", "Asx+_req_mm2_m", "Asx+_prov_mm2_m", "X+_optimization",
            "X-_base", "X-_additional", "X-_rebar", "Asx-_req_mm2_m", "Asx-_prov_mm2_m", "X-_optimization",
            "Y+_base", "Y+_additional", "Y+_rebar", "Asy+_req_mm2_m", "Asy+_prov_mm2_m", "Y+_optimization",
            "Y-_base", "Y-_additional", "Y-_rebar", "Asy-_req_mm2_m", "Asy-_prov_mm2_m", "Y-_optimization",
            "util_M", "util_Qx", "util_Qy", "util_max", "Verification_reason", "Recommended_action"
        ]
        out = results[[c for c in cols if c in results.columns]].copy()
        if "util_max" in out.columns:
            out = out.sort_values(["Status", "util_max"], ascending=[False, False])
        return out.reset_index(drop=True)

    def build_normative_notes(self, designer: WallDesigner) -> pd.DataFrame:
        asv_min, ash_min, asv_max = designer.min_wall_reinf_total()
        sx_vert = designer.max_spacing_for_direction(True)
        sx_hor = designer.max_spacing_for_direction(False)
        notes = [
            ("Âmbito", "Painéis/placas", "Esforços por metro: Nxx, Nyy, Nxy; Mxx, Myy, Mxy; Qxx, Qyy, no referencial local da parede."),
            ("Flexão", designer.wood_armer_method, "MXY é tratado pelo método seleccionado. No modo conservativo, MXY é convertido em acréscimo absoluto nos momentos de dimensionamento nas duas direcções."),
            ("Eixos locais", "Y vertical" if designer.local_y_is_vertical else "X vertical", "Os resultados dependem da orientação dos eixos locais dos painéis. Confirmar esta convenção antes de adoptar as armaduras."),
            ("Troca X/Y", "Activada" if designer.swap_local_axes else "Desactivada", "Quando activada, MXX/MYY, QXX/QYY e NXX/NYY são trocados antes do cálculo."),
            ("Mínimo vertical", f"Asv,min = {asv_min:.1f} mm²/m", "Adoptado 0,002 Ac por metro de parede, distribuído pelas duas faces."),
            ("Máximo vertical", f"Asv,max = {asv_max:.1f} mm²/m", "Adoptado limite de 0,04 Ac para armadura vertical total por metro."),
            ("Mínimo horizontal", f"Ash,min = {ash_min:.1f} mm²/m", "Limite inicial: 0,001 Ac ou 25% do mínimo vertical; malha final reforçada para 25% da armadura vertical adoptada (se superior)."),
            ("Espaçamento vertical", f"smax = {sx_vert:.0f} mm", "Adoptado min(3t; 400 mm), eventualmente limitado a 250 mm quando o controlo de fendilhação está activo."),
            ("Espaçamento horizontal", f"smax = {sx_hor:.0f} mm", "Adoptado 400 mm, eventualmente limitado a 250 mm quando o controlo de fendilhação está activo."),
            ("Distância livre", "Verificada na escolha automática", "A solução automática rejeita combinações em que a distância livre seja inferior a max(Ø; dg+5; 20 mm)."),
            ("Corte", "VRd,c tipo laje + VRd,max", "Verificação da malha sem armadura específica; se VEd>VRd,c, exige reforço ou armadura de corte. Proposta Asw por 6.2.3, cotθ=1, não instalada nem validada. Limite VRd,max simplificado."),
            ("Fendilhação", f"wmax = {designer.wmax_mm:.2f} mm", f"Sem selecção de wk: não é calculada a largura de fenda; fica apenas o controlo indirecto por diâmetro/espaçamento. Com wk seleccionado: cálculo apenas para a combinação quase-permanente indicada ({designer.qp_case or 'não indicada'})."),
            ("Armadura mínima por fendilhação", f"Flexão: {designer.crack_min_as_per_face():.1f} mm²/m/face", "EC2 7.3.2: aproximação em flexão com kc=0,4. Para N-M adopta-se kc=1 e Act=h/2 por face traccionada, conservador."),
            ("Unidades", f"M: {designer.moment_unit}; N e Q: {designer.shear_unit}", "Os valores são convertidos internamente para kNm/m e kN/m. Confirmar sempre as unidades da tabela de origem antes de adoptar os resultados."),
            ("Optimização de armaduras", "Base + reforços" if designer.optimize_rebar else "Automática directa", f"Base vertical Ø{designer.base_vertical_phi:.0f}//{designer.base_vertical_spacing:.0f}; base horizontal Ø{designer.base_horizontal_phi:.0f}//{designer.base_horizontal_spacing:.0f}. Quando a base é insuficiente, o programa tenta adicionar reforço local antes de declarar insuficiência à flexão ou corte."),
            ("Limitação", "Modelo de faixa isolada", "Inclui N-M com sinal de N definido e segunda ordem com l0 fornecido. Não inclui estabilidade global ou membrana NXY. wk N-M exige momentos originais sem NXY/MXY."),
        ]
        if designer.sandwich_design:
            notes[-1]=("Limitação", "Modelo sandwich com envolvente de faixas", "Anexo LL.108–115 (NP EN 1992-2:2018, metodologia complementar) e Anexo F da NP EN 1992-1-1. Forças de face e equilíbrio com posições reais; incrementos locais de momento incluídos na envolvente. Pressupostos: esforços concomitantes, amarração adequada e condições de travamento definidas. wk convencional no domínio aplicável.")
            notes.append(("Resistência dos campos comprimidos", "F.1(3)–(4); 6.109(103)", "Compressão biaxial 6.110 limitada a fcd; 6.111 alinhada sem cedência; 6.112 com cedência e desvio até 15°. Mantém-se o limite F.1. Fora das condições demonstradas: 0,52 ν fcd apenas para triagem, sem aprovação. Ângulo elástico da secção bruta homogénea; confirmar hipótese. LL(115)(c): corte adicional requer cálculo complementar quando aplicável."))
        return pd.DataFrame(notes, columns=["Tema", "Critério adoptado", "Nota"])

    def _refresh_stability_mode(self):
        if not hasattr(self, "stability_mode_text"): return
        opts=self.auto_stability_options
        self.stability_mode_text.set("Modo: manual — l0 e φef" if opts is None else f"Modo: automático por painel · kX={opts[0]:g}, kY={opts[1]:g} · RH={opts[2]:g}%")
        for entry in getattr(self,"stability_manual_entries",[]):
            entry.configure(state="normal" if opts is None else "disabled")

    def clear_auto_stability(self):
        self.auto_stability_options=None
        self._refresh_stability_mode()
        self.status_var.set("Parâmetros manuais de estabilidade activos.")
        self._mark_results_stale()

    def _stability_dialog(self, title, explanation, fields, validate):
        from tkinter.simpledialog import Dialog
        class Parameters(Dialog):
            def body(dialog, master):
                ttk.Label(master,text=explanation,wraplength=420,justify="left").grid(row=0,column=0,columnspan=2,sticky="w",padx=10,pady=(4,12))
                dialog.entries=[]
                for i,(label,value) in enumerate(fields,1):
                    ttk.Label(master,text=label).grid(row=i,column=0,sticky="w",padx=10,pady=5)
                    e=ttk.Entry(master,width=16);e.insert(0,str(value));e.grid(row=i,column=1,sticky="ew",padx=10,pady=5);dialog.entries.append(e)
                return dialog.entries[0]
            def validate(dialog):
                try:
                    vals=tuple(float(e.get().replace(",",".")) for e in dialog.entries)
                    if not all(map(math.isfinite,vals)):raise ValueError("Introduza valores finitos.")
                    dialog.result=validate(vals)
                    return True
                except ValueError as exc:
                    messagebox.showerror("Parâmetros inválidos",str(exc),parent=dialog);return False
        return Parameters(self,title).result

    def configure_auto_stability(self):
        if self.geometry_nodes is None or self.df_geometry.empty or not self.df_geometry.estado.eq("Plano identificado").all():
            messagebox.showwarning("Geometria", "Importe os esforços e a tabela de coordenadas dos nós antes de activar o modo automático.",parent=self); return
        def valid(v):
            if min(v[:2])<0 or not 40<=v[2]<=100 or v[3]<.5 or v[4] not in (1,2):raise ValueError("k ≥ 0; RH 40–100%; t0 ≥ 0,5 dias; faces 1 ou 2.")
            return v
        vals=self._stability_dialog("Estabilidade por painel", "Defina os factores de comprimento efectivo segundo os travamentos. k=0 mantém a direcção pendente. Os valores iniciais são ilustrativos, não uma confirmação dos apoios.", list(zip(["Factor kX","Factor kY","Humidade relativa RH [%]","Idade ajustada t0 [dias]","Faces largas expostas (1 ou 2)"], self.auto_stability_options or (1,1,70,28,2))),valid)
        if vals is not None:
            self.auto_stability_options=vals;self._refresh_stability_mode();self._mark_results_stale()
            self.status_var.set("Modo automático configurado; confirmar travamentos no cálculo.")

    def assist_stability(self):
        def valid(v):
            height,k,rh,h0,age,ratio=v
            if min(height,k,h0)<=0 or ratio<0:raise ValueError("Dimensões e k positivos; razão de momentos não negativa.")
            phi=ec2_final_creep(parse_strength_from_class(self.var_concrete.get()),rh,h0,age)
            return height*k,phi,phi*ratio
        vals=self._stability_dialog("Calcular l0 e fluência efectiva", "Modo manual: introduza os parâmetros da faixa e de fluência segundo EC2 5.8.4 e Anexo B. Os valores iniciais são apenas exemplos.",[("Comprimento livre [mm]",2500),("Factor de comprimento k",1),("Humidade relativa RH [%]",70),("Espessura nocional h0 [mm]",self.var_thickness.get()),("Idade ajustada t0 [dias]",28),("Razão M0Eqp / M0Ed",1)],valid)
        if vals is not None:
            length,phi,eff=vals;self.clear_auto_stability()
            self.var_l0.set(f"{length:.12g}");self.var_phi_eff.set(f"{eff:.12g}")
            self.status_var.set(f"l0 = {length:.1f} mm; φ∞ = {phi:.3f}; φef = {eff:.3f}")

    def run_design(self):
        self.df_external_stability=pd.DataFrame()
        self.df_interlayer=pd.DataFrame()
        self._calculated_signature = None
        err = self.validate_inputs()
        if err:
            messagebox.showwarning("Aviso", err)
            return
        try:
            designer = WallDesigner(
                elu_cases=self.var_elu_cases.get(),
                characteristic_cases=self.var_car_cases.get(),
                frequent_cases=self.var_freq_cases.get(),
                axial_convention=self.var_axial_convention.get(),
                effective_length_mm=safe_float(self.var_l0.get()),
                creep_effective=safe_float(self.var_phi_eff.get()),
                steel_ultimate_strain=safe_float(self.var_eps_ud.get()),
                thickness_mm=safe_float(self.var_thickness.get(), 200.0),
                cover_mm=safe_float(self.var_cover.get(), 35.0),
                concrete_class=self.var_concrete.get(),
                fyk=safe_float(self.var_steel.get(), 500.0),
                local_y_is_vertical=self.var_y_vertical.get(),
                crack_spacing_limit_mm=250.0 if self.var_crack_spacing.get() else None,
                wood_armer_method=self.var_wa_method.get(),
                swap_local_axes=self.var_swap_axes.get(),
                crack_check_enabled=True,
                wk_check_enabled=self.var_crack_check.get(),
                qp_case=self.var_qp_case.get(),
                moment_unit=self.var_moment_unit.get(),
                shear_unit=self.var_shear_unit.get(),
                combo_type=self.var_combo_type.get(),
                wmax_mm=safe_float(self.var_wmax.get(), 0.30),
                phi_min_mm=safe_float(self.var_phi_min.get(), 8.0),
                phi_max_mm=safe_float(self.var_phi_max.get(), 16.0),
                optimize_rebar=self.var_optimize_rebar.get(),
                rebar_strategy=self.var_rebar_strategy.get(),
                base_vertical_phi=safe_float(self.var_base_v_phi.get(), 10.0),
                base_vertical_spacing=safe_float(self.var_base_v_spacing.get(), 200.0),
                base_horizontal_phi=safe_float(self.var_base_h_phi.get(), 8.0),
                base_horizontal_spacing=safe_float(self.var_base_h_spacing.get(), 200.0),
            )
        except ValueError as exc:
            messagebox.showerror("Parâmetros inválidos", str(exc))
            return
        designer.shell_qp_diagnostic=False
        designer.sandwich_design=True
        if self.auto_stability_options is not None:
            if self.geometry_nodes is None or self.df_geometry.empty or not self.df_geometry.estado.eq("Plano identificado").all():
                messagebox.showerror("Geometria", "Modo automático exige nós completos."); return
            if self.var_reduce.get():
                messagebox.showerror("Estabilidade", "Desactive redução de combinações para preservar os pares ELU/QP."); return
            if not messagebox.askyesno("Confirmar modelo de faixa", "Confirma para TODOS os painéis que os limites geométricos das direcções com k>0 representam distâncias livres entre travamentos contínuos, com os factores k introduzidos, e que os eixos locais correspondem às direcções geométricas?\nConfirmar ainda ambiente/idade e análise global independente. Não usar para consolas, aberturas ou travamentos não confirmados.",parent=self): return
            designer.auto_stability=(self.geometry_nodes,self.auto_stability_options)
        elif designer.effective_length_mm>0 and designer.creep_effective==0:
            if not messagebox.askyesno("Fluência nula", "Confirma que φef=0 é justificado segundo EC2 5.8.4? Caso contrário use o assistente.",parent=self): return
        if designer.wk_check_enabled and not designer.qp_case:
            messagebox.showwarning("Aviso", "Foi seleccionada a verificação wk, mas não foi indicado o número da combinação quase-permanente.")
            return
        # Explicitly report absent combinations before the expensive calculation.
        expected=designer.elu_cases | designer.characteristic_cases | designer.frequent_cases
        if designer.wk_check_enabled and designer.qp_case:expected |= {canonical_case_id(designer.qp_case)}
        missing=expected-set(self.df_clean.case.map(canonical_case_id))
        if missing and not messagebox.askyesno("Combinações não importadas", "Não existem no ficheiro as combinações seleccionadas: " + format_case_ranges(missing) + ". Corrija a selecção ou confirme que pretende calcular com cobertura parcial.",parent=self):return
        # Do not reduce concomitant combinations, even for legacy saved settings.
        df_in = self.df_clean.copy()
        try:
            self.progress_var.set(0.0)
            self.status_var.set("A calcular...")
            self.update_idletasks()
            from threading import Event, Thread

            progress = [0, 1]
            result = {}
            cancelled = Event()
            dialog = tk.Toplevel(self)
            dialog.title("WallsEC2 · Cálculo")
            dialog.transient(self)
            label = ttk.Label(dialog, text="A preparar o cálculo…", padding=12)
            label.pack(fill="x")
            ttk.Progressbar(dialog, variable=self.progress_var, maximum=100, length=360).pack(padx=12)
            def cancel():
                cancelled.set()
                label.configure(text="A cancelar…")
            ttk.Button(dialog, text="Cancelar", command=cancel).pack(pady=10)
            dialog.protocol("WM_DELETE_WINDOW", cancel)

            def update_progress(i, total):
                if cancelled.is_set():
                    raise InterruptedError()
                progress[:] = [i, total]

            def calculate():
                try:
                    result["data"] = designer.design_dataframe(df_in, progress=update_progress)
                except Exception as exc:
                    result["error"] = exc

            worker = Thread(target=calculate, daemon=True)
            def poll():
                i, total = progress
                self.progress_var.set(100.0 * i / total)
                if not cancelled.is_set():
                    label.configure(text=f"A dimensionar e verificar · {i:,} / {total:,} passos")
                if worker.is_alive():
                    dialog.after(100, poll)
                else:
                    dialog.destroy()

            dialog.grab_set()
            worker.start()
            dialog.after(100, poll)
            self.wait_window(dialog)
            if cancelled.is_set():
                self.progress_var.set(0.0)
                self.status_var.set("Cálculo cancelado.")
                return
            if "error" in result:
                raise result["error"]
            self.df_results = result["data"]
            self.status_var.set("A preparar resumos...")
            self.update_idletasks()
            self.df_summary = self.build_panel_summary(self.df_results)
            self.df_governing = self.build_governing_design(self.df_results)
            self.df_zones = self.build_rebar_zones(self.df_governing)
            self.df_optimization = self.build_rebar_optimization(self.df_results)
            self.df_unit_check = self.build_unit_check(df_in, designer)
            self.df_data_validation = self.build_data_validation(df_in, designer)
            self.df_diagnostic = self.build_diagnostic(self.df_results, self.df_data_validation)
            self.df_sketches = self.build_rebar_sketches(self.df_zones)
            self.df_detailed = self.build_detailed_check(self.df_results)
            self.df_notes = self.build_normative_notes(designer)
            self.refresh_dashboard()
            self.main_notebook.select(0)
            self.show_df(self.tree_results, self.df_results)
            self.show_df(self.tree_summary, self.df_summary)
            self.show_df(self.tree_governing, self.df_governing)
            self.show_df(self.tree_zones, self.df_zones)
            self.show_df(self.tree_optimization, self.df_optimization)
            self.show_df(self.tree_diagnostic, self.df_diagnostic)
            self.show_df(self.tree_validation, self.df_data_validation)
            self.show_df(self.tree_sketches, self.df_sketches)
            self.show_df(self.tree_unit, self.df_unit_check)
            self.show_df(self.tree_detailed, self.df_detailed)
            self.show_df(self.tree_notes, self.df_notes)
            qp_msg = ""
            if designer.wk_check_enabled:
                n_qp = int((self.df_results.get("is_QP_crack_case", pd.Series(dtype=str)) == "Sim").sum())
                qp_msg = f"; wk QP: {n_qp} linhas"
                if n_qp == 0:
                    messagebox.showwarning("Aviso", f"Não foram encontradas linhas para a combinação quase-permanente indicada: {designer.qp_case}")
            self.progress_var.set(100.0)
            self._calculated_signature = self._input_signature()
            self.status_var.set(f"Cálculo concluído: {len(self.df_results)} linhas analisadas; {len(self.df_summary)} painéis resumidos{qp_msg}.")
        except Exception as e:
            self.progress_var.set(0.0)
            messagebox.showerror("Erro", str(e))
            self.status_var.set("Falha no cálculo.")

    def export_excel(self):
        if self.df_results is None or self.df_results.empty:
            messagebox.showwarning("Aviso", "Não há resultados para exportar.")
            return
        if hasattr(self, '_calculated_signature') and not self._export_current():
            return
        path = filedialog.asksaveasfilename(
            title="Exportar resultados",
            defaultextension=".xlsx",
            filetypes=[("Excel workbook", "*.xlsx")],
        )
        if not path:
            return

        # Garante extensão correcta. Evita ficheiros com extensão inválida,
        # por exemplo .xls ou nomes sem extensão que depois o Excel recusa abrir.
        import os
        root, ext = os.path.splitext(path)
        if ext.lower() != ".xlsx":
            path = root + ".xlsx" if ext else path + ".xlsx"

        def safe_sheet_name(name: str) -> str:
            bad = r'[]:*?/\\'
            out = "".join("_" if ch in bad else ch for ch in str(name))[:31]
            return out or "Sheet"

        def has_df(df):
            return df is not None and isinstance(df, pd.DataFrame) and not df.empty

        def pick_cols(df, cols):
            if not has_df(df):
                return pd.DataFrame()
            present = [c for c in cols if c in df.columns]
            if not present:
                return pd.DataFrame()
            return df[present].copy()

        try:
            self.progress_var.set(0.0)
            self.status_var.set("A preparar exportação Excel...")
            self.update_idletasks()

            # ---- folhas estruturadas, menos densas ----
            export_dt = datetime.now()
            metadata = pd.DataFrame([
                ["Programa", APP_NAME],
                ["Versão", APP_VERSION],
                ["Autor", APP_REPORT_AUTHOR],
                ["Repositório", GITHUB_URL],
                ["Data de exportação", export_dt.strftime("%Y-%m-%d %H:%M")],
                ["Tipo de ficheiro", "Resultados de cálculo"],
                ["Norma de referência", "Eurocódigo 2 / NP EN 1992-1-1"],
                ["Âmbito", "Paredes modeladas como painéis/placas, com esforços por metro"],
                ["Limitações", "N-M e segunda ordem por faixa com l0; estabilidade da estrutura externa. Membrana no modelo sandwich; wk N-M apenas no domínio convencional"],
                ["Unidades internas", "Momentos em kNm/m; corte em kN/m"],
                ["Descrição", APP_XLSX_DESCRIPTION],
            ], columns=["Campo", "Valor"])

            input_params = pd.DataFrame([
                ["Espessura [mm]", self.var_thickness.get()],
                ["Recobrimento [mm]", self.var_cover.get()],
                ["Betão", self.var_concrete.get()],
                ["Aço fyk [MPa]", self.var_steel.get()],
                ["Eixo local Y = vertical", "Sim" if self.var_y_vertical.get() else "Não"],
                ["Trocar eixos X ↔ Y", "Sim" if self.var_swap_axes.get() else "Não"],
                ["Método MXY", self.var_wa_method.get()],
                ["Verificar wk", "Sim" if self.var_crack_check.get() else "Não"],
                ["ELU seleccionadas", self.var_elu_cases.get()],
                ["Convenção N", self.var_axial_convention.get()],
                ["l0 [mm]", "Por painel/direcção (folha 25)" if "Auto_l0_x" in self.df_results else self.var_l0.get()],
                ["Fluência efectiva", "Por painel/direcção (folha 25)" if "Auto_phi_x" in self.df_results else self.var_phi_eff.get()],
                ["ELS-CAR", self.var_car_cases.get()],
                ["ELS-FREQ", self.var_freq_cases.get()],
                ["Extensão última de cálculo do aço", self.var_eps_ud.get()],
                ["Combinação quase-permanente", self.var_qp_case.get()],
                ["wmax [mm]", self.var_wmax.get()],
                ["Unidade dos momentos", self.var_moment_unit.get()],
                ["Unidade do corte", self.var_shear_unit.get()],
                ["Ø min / Ø max [mm]", f"{self.var_phi_min.get()} / {self.var_phi_max.get()}"],
                ["Optimizar armadura", "Sim" if self.var_optimize_rebar.get() else "Não"],
                ["Estratégia", self.var_rebar_strategy.get()],
                ["Base vertical", f"Ø{self.var_base_v_phi.get()}//{self.var_base_v_spacing.get()}"],
                ["Base horizontal", f"Ø{self.var_base_h_phi.get()}//{self.var_base_h_spacing.get()}"],
            ], columns=["Parâmetro", "Valor"] )

            readme = pd.DataFrame([
                ["WallsEC2", "Exportação organizada de resultados de paredes de betão armado"],
                ["Formato", "Workbook .xlsx válido, com resultados separados por tema"],
                ["Linhas analisadas", len(self.df_results) if has_df(self.df_results) else 0],
                ["Painéis resumidos", len(self.df_summary) if has_df(self.df_summary) else 0],
                ["Folhas principais", "Resumo por painel, armaduras adoptadas, zonas, diagnóstico, validação, resultados por tema"],
                ["Nota", "A folha '15_Full_Results' mantém a tabela completa para auditoria; as folhas 09 a 13 separam os resultados por assunto."],
            ], columns=["Item", "Descrição"] )

            row_core = pick_cols(self.df_results, [
                "Panel", "Node", "Case", "is_QP_crack_case", "Status", "Verification_reason", "Recommended_action",
                "util_max", "util_M", "util_Qx", "util_Qy", "wk_max_mm"
            ])
            row_flexure = pick_cols(self.df_results, [
                "Panel", "Node", "Case", "MXX_kNm_m", "MYY_kNm_m", "MXY_kNm_m", "WA_method", "MXY_ratio",
                "Mx+_WA", "Mx-_WA", "My+_WA", "My-_WA",
                "Asx+_req_mm2_m", "Asx-_req_mm2_m", "Asy+_req_mm2_m", "Asy-_req_mm2_m",
                "MRd_x+_kNm_m", "MRd_x-_kNm_m", "MRd_y+_kNm_m", "MRd_y-_kNm_m", "util_M"
            ])
            row_shear = pick_cols(self.df_results, [
                *[c for c in self.df_results if c.startswith("ShearDesign_")],
                "Shear_X_face_VRdc", "Shear_X_As_mm2_m", "Shear_X_d_mm", "Shear_X_sigma_cp_MPa",
                "Shear_Y_face_VRdc", "Shear_Y_As_mm2_m", "Shear_Y_d_mm", "Shear_Y_sigma_cp_MPa", "Shear_note",
                "Panel", "Node", "Case", "QXX_kN_m", "QYY_kN_m", "VRdc_x_kN_m", "VRdc_y_kN_m",
                "VRdmax_x_kN_m", "VRdmax_y_kN_m", "util_Qx", "util_Qy",
                "util_Qx_VRdmax", "util_Qy_VRdmax", "Transverse_links_required", "Transverse_links_note"
            ])
            row_cracking = pick_cols(self.df_results, [
                "Panel", "Node", "Case", "is_QP_crack_case", "wmax_mm", "Crack_model",
                "Crack_k2_x+", "Crack_k2_x-", "Crack_k2_y+", "Crack_k2_y-",
                "Crack_hceff_x+_mm", "Crack_hceff_x-_mm", "Crack_hceff_y+_mm", "Crack_hceff_y-_mm",
                "wk_x+_mm", "wk_x-_mm", "wk_y+_mm", "wk_y-_mm", "wk_max_mm", "wk_cargas_cond_mm", "ELS_historico_ratio", "ELS_sigma_t_upper_MPa", "ELS_fctk005_MPa", "ELS_cargas_estado",
                "sigma_s_x+_MPa", "sigma_s_x-_MPa", "sigma_s_y+_MPa", "sigma_s_y-_MPa",
                "phi_ctrl_x+_mm", "phi_ctrl_x-_mm", "phi_ctrl_y+_mm", "phi_ctrl_y-_mm",
                "s_eff_x+_mm", "s_eff_x-_mm", "s_eff_y+_mm", "s_eff_y-_mm",
                "phi_lim_x+_EC2_mm", "phi_lim_x-_EC2_mm", "phi_lim_y+_EC2_mm", "phi_lim_y-_EC2_mm",
                "s_lim_x+_EC2_mm", "s_lim_x-_EC2_mm", "s_lim_y+_EC2_mm", "s_lim_y-_EC2_mm",
                "Crack_status_x+", "Crack_status_x-", "Crack_status_y+", "Crack_status_y-",
                "Crack_reason_x+", "Crack_reason_x-", "Crack_reason_y+", "Crack_reason_y-",
                "Crack_control_status", "Crack_control_note"
            ])
            row_rebar = pick_cols(self.df_results, [
                "Panel", "Node", "Case",
                "X+_rebar", "X-_rebar", "Y+_rebar", "Y-_rebar",
                "X+_base", "X-_base", "Y+_base", "Y-_base",
                "X+_additional", "X-_additional", "Y+_additional", "Y-_additional",
                "Asx+_prov_mm2_m", "Asx-_prov_mm2_m", "Asy+_prov_mm2_m", "Asy-_prov_mm2_m",
                "sX_max_mm", "sY_max_mm", "Optimization_mode", "Optimization_iterations"
            ])

            sheets = [
                ("00_METADATA", metadata),
                ("00_README", readme),
                ("01_Input_Data", input_params),
                ("02_Panel_Summary", self.df_summary.drop(columns=["Estabilidade_global_externa"],errors="ignore")),
                ("03_Adopted_Rebar", self.df_governing),
                ("04_Rebar_Zones", self.df_zones),
                ("05_Optimization", self.df_optimization),
                ("06_Diagnostic", self.df_diagnostic),
                ("07_Data_Validation", self.df_data_validation),
                ("08_Unit_Check", self.df_unit_check),
                ("09_Row_Core", row_core),
                ("10_Row_Flexure", row_flexure),
                ("11_Row_Shear", row_shear),
                ("19_ELS_Secao_Bruta", pick_cols(
                    self.df_results.loc[self.df_results["Combo_type"].str.startswith("ELS")],
                    ["Panel", "Node", "Case", "Combo_type", "Crack_control_status", "Crack_control_note"] +
                    [f"Gross_{key}_{face}{unit}" for face in ("plus", "minus")
                     for key, unit in (("sigma1","_MPa"), ("sigma2","_MPa"),
                                       ("theta1","_deg"), ("sigma1_fctm",""))])),
                ("12_Row_Cracking", row_cracking),
                ("13_Row_Rebar", row_rebar),
                ("14_Detailed_Check", self.df_detailed),
                ("15_Full_Results", self.df_results),
                ("16_Raw_Table", self.df_clean),
                ("17_EC2_Notes", self.df_notes),
                ("20_ELU_NM_Envelope", WallsEC2App.build_nm_envelope(self.df_results)),
                ("21_ELU_Shell_Screen", shell_screen_envelope(self.df_results) if "Sand_status" not in self.df_results else pd.DataFrame()),
                ("27_ELU_Casca_Equilibrio", shell_capacity_envelope(self.df_results) if "Sand_status" not in self.df_results else pd.DataFrame()),
                ("28_Camadas_Resumo", physical_layers_summary(self.df_results)),
                ("29_Camadas_Detalhe", pick_cols(self.df_results,["Panel","Node","Case","Combo_type"]+[c for c in self.df_results if c.startswith(("Phys","Core_","Asym_","AsymTruss_","History_"))])),
                ("22_Geometria", getattr(self,"df_geometry",pd.DataFrame())),
                ("23_Nos_Paineis", getattr(self,"df_geometry_nodes",pd.DataFrame())),
                ("24_QP_Casca_Diagnostico", pick_cols(self.df_results[self.df_results.Combo_type.eq("ELS-QP")], ["Panel","Node","Case"]+[c for c in self.df_results if c.startswith("ShellQP_")])),
                ("26_Estabilidade_Cobertura", WallsEC2App.build_stability_coverage(self.df_results)),
                ("30_Estabilidade_Externa", getattr(self,"df_external_stability",pd.DataFrame())),
                ("32_Corte_Intercamadas", getattr(self,"df_interlayer",pd.DataFrame())),
                ("25_Estabilidade_Auto", self.df_results[["Panel"]+[c for c in self.df_results if c.startswith("Auto_")]].drop_duplicates()),
                ("18_NM_Stability", pick_cols(self.df_results, ["Panel", "Node", "Case", "Combo_type", "Axial_convention",
                    "NXX_kN_m", "NYY_kN_m", "NXY_kN_m", "NMises_kN_m", "NMises_usage", "Source_tables_count", "NM_X_util", "NM_Y_util", "NM_X_NEd", "NM_Y_NEd", "NM_X_MEd", "NM_Y_MEd", "NM_X_MRd", "NM_Y_MRd",
                    "Stability_l0_mm", "Stability_phi_eff", "Stability_X_l0_mm", "Stability_Y_l0_mm", "Stability_X_phi_eff", "Stability_Y_phi_eff", "Stability_X_status", "Stability_Y_status", "Stability_X_lambda", "Stability_Y_lambda", "Stability_X_lambda_lim", "Stability_Y_lambda_lim", "Stability_X_NB_kN_m", "Stability_Y_NB_kN_m",
                    "Stability_X_amplification", "Stability_Y_amplification", "ELS_X_sigma_plus_MPa", "ELS_X_sigma_minus_MPa",
                    "ELS_Y_sigma_plus_MPa", "ELS_Y_sigma_minus_MPa", "Status", "Verification_reason"])),
            ]

            if "Sand_status" in self.df_results:
                sheets = [pair for pair in sheets if pair[0] not in ("21_ELU_Shell_Screen","27_ELU_Casca_Equilibrio","28_Camadas_Resumo","29_Camadas_Detalhe","24_QP_Casca_Diagnostico","30_Estabilidade_Externa") and not (pair[0]=="32_Corte_Intercamadas" and pair[1].empty)]
                sheets.append(("31_ELS_Tensoes_72",pick_cols(self.df_results[self.df_results.Combo_type.isin(["ELS-CAR","ELS-FREQ","ELS-QP"])],["Panel","Node","Case","Combo_type"]+[c for c in self.df_results if c.startswith(("ELS_72_","ELS_sigma_"))])))
                sheets.append(("21_ELU_Sandwich",pick_cols(self.df_results[self.df_results.Combo_type.eq("ELU")],["Panel","Node","Case"]+[c for c in self.df_results if c.startswith("Sand_")])))
            self.progress_var.set(15.0)
            self.status_var.set("A escrever folhas Excel...")
            self.update_idletasks()

            from tempfile import NamedTemporaryFile
            from xlsxwriter import Workbook

            # Gravar por linha, com memória limitada e formatação por coluna.
            # O destino só é substituído depois de fechar o ZIP com sucesso.
            with NamedTemporaryFile(dir=os.path.dirname(os.path.abspath(path)),
                                    suffix=".xlsx", delete=False) as tmp:
                tmp_path = tmp.name
            try:
                with Workbook(tmp_path, {"constant_memory": True, "strings_to_formulas": False,
                                         "strings_to_urls": False}) as wb:
                    wb.set_properties({"title": f"{APP_NAME} - Resultados de Cálculo",
                        "subject": APP_SUBJECT, "author": APP_REPORT_AUTHOR,
                        "comments": APP_XLSX_DESCRIPTION, "keywords": APP_KEYWORDS,
                        "category": APP_CATEGORY, "created": export_dt})
                    header = wb.add_format({"bg_color": "#1F4E78", "font_color": "#FFFFFF",
                                            "bold": True, "text_wrap": True, "valign": "vcenter"})
                    number = wb.add_format({"num_format": "0.000"})
                    statuses = {name: wb.add_format({"bg_color": color}) for name, color in
                                (("Não conforme", "#F4CCCC"), ("Verificar", "#FFF2CC"), ("Condicionado", "#FFF2CC"),
                                 ("OK", "#D9EAD3"), ("OK*", "#FFF2CC"), ("Cumpre sob hipóteses", "#FFF2CC"))}
                    names = [safe_sheet_name(name) for name, _ in sheets]
                    for i, (name, df) in enumerate(sheets):
                        frame = df if has_df(df) else pd.DataFrame({"Nota": ["Sem dados disponíveis."]})
                        if any(c in frame.columns for c in ("Status","Status_global")):
                            frame=frame.assign(**{c:frame[c].replace({"Incompleto":"Condicionado","OK*":"Cumpre sob hipóteses"}) for c in ("Status","Status_global") if c in frame.columns})
                        if len(frame) > 1048575 or len(frame.columns) > 16384:
                            raise ValueError(f"A folha {name} excede os limites do Excel.")
                        ws = wb.add_worksheet(names[i])
                        ws.freeze_panes(1, 0)
                        ws.hide_gridlines(2)
                        ws.set_row(0, 24)
                        ws.write_row(0, 0, [str(c) for c in frame.columns], header)
                        ws.autofilter(0, 0, len(frame), len(frame.columns)-1)
                        for j, col in enumerate(frame.columns):
                            width = min(44, max(12, len(str(col))+2))
                            if name in {"00_METADATA", "00_README", "01_Input_Data"}:
                                width = 28 if j == 0 else 80
                            ws.set_column(j, j, width, number if pd.api.types.is_float_dtype(frame.dtypes.iloc[j]) else None)
                            if col in {"Status", "Status_global", "Estado", "Crack_control_status"}:
                                for status, fmt in statuses.items():
                                    ws.conditional_format(1, j, len(frame), j, {
                                        "type": "cell", "criteria": "==", "value": f'"{status}"', "format": fmt})
                        for row_index, row in enumerate(frame.itertuples(index=False, name=None), 1):
                            values = [
                                ("inf" if v > 0 else "-inf") if isinstance(v, float) and math.isinf(v)
                                else None if pd.isna(v) else v for v in row
                            ]
                            ws.write_row(row_index, 0, values)
                            if row_index % 2000 == 0:
                                self.progress_var.set(15 + 80 * (i + row_index / len(frame)) / len(sheets))
                                self.update_idletasks()
                        if name == "00_README":
                            start = len(frame) + 3
                            ws.write(start, 0, "Índice de folhas", header)
                            for j, sheet_name in enumerate(names, start+1):
                                ws.write_row(j, 0, [sheet_name, self._excel_sheet_description(sheet_name)])
                        self.progress_var.set(15 + 80 * (i + 1) / len(sheets))
                        self.status_var.set(f"Folha {i+1}/{len(sheets)} concluída: {name}")
                        self.update_idletasks()
                    self.status_var.set("A finalizar o ficheiro Excel…")
                    self.update_idletasks()
                os.replace(tmp_path, path)
            finally:
                if os.path.exists(tmp_path):
                    os.unlink(tmp_path)

            self.progress_var.set(100.0)
            self.status_var.set(f"Excel organizado exportado: {path}")
            messagebox.showinfo("Exportação concluída", f"Excel exportado com sucesso:\n{path}")

        except PermissionError:
            self.progress_var.set(0.0)
            self.status_var.set("Erro ao exportar Excel: ficheiro aberto ou sem permissão.")
            messagebox.showerror(
                "Erro",
                "Não foi possível gravar o ficheiro. Feche o Excel se o ficheiro estiver aberto e tente novamente."
            )
        except Exception as e:
            self.progress_var.set(0.0)
            self.status_var.set("Erro ao exportar Excel.")
            messagebox.showerror("Erro", str(e))

    def _excel_sheet_description(self, sheet_name: str) -> str:
        descriptions = {
            "00_METADATA": "Metadados do ficheiro e identificação da exportação",
            "00_README": "Resumo da exportação e índice do workbook",
            "31_ELS_Tensoes_72": "Limitação de tensões CAR e limiar de fluência QP (EC2 7.2)",
            "32_Corte_Intercamadas": "Comparação com limite de corte adicional externo, quando fornecido",
            "01_Input_Data": "Parâmetros usados no cálculo",
            "02_Panel_Summary": "Resumo governante por painel",
            "03_Adopted_Rebar": "Armadura adoptada por painel",
            "04_Rebar_Zones": "Agrupamento de painéis por zonas de armadura",
            "05_Optimization": "Histórico/resultado da optimização de armaduras",
            "06_Diagnostic": "Avisos e acções recomendadas",
            "07_Data_Validation": "Validação da tabela importada",
            "08_Unit_Check": "Unidades adoptadas e factores de conversão",
            "09_Row_Core": "Resultados essenciais por linha/caso",
            "10_Row_Flexure": "Resultados de flexão e armadura requerida",
            "11_Row_Shear": "Verificação ao esforço transverso",
            "12_Row_Cracking": "Verificação de fendilhação / wk",
            "13_Row_Rebar": "Armadura base, adicional e final por linha",
            "14_Detailed_Check": "Cálculo detalhado de linhas seleccionadas/críticas",
            "15_Full_Results": "Tabela completa de resultados para auditoria",
            "16_Raw_Table": "Tabela importada já normalizada",
            "17_EC2_Notes": "Notas normativas e limitações",
            "18_NM_Stability": "Interacção N-M, segunda ordem da faixa e tensões ELS",
            "21_ELU_Sandwich": "Modelo sandwich: forças de face, aço, betão e corte resultante; condições de aplicação",
            "21_ELU_Shell_Screen": "Diagnóstico de tracção nas faces; não constitui verificação ELU",
            "22_Geometria": "Dimensões da nuvem de nós; não definem altura livre ou l0",
            "23_Nos_Paineis": "Correspondência painel/nó e coordenadas globais em metros",
        }
        return descriptions.get(sheet_name, "")

    def export_pdf_report(self):
        if self.df_results is None or self.df_results.empty:
            messagebox.showwarning("Aviso", "Não há resultados para exportar.")
            return
        if hasattr(self, '_calculated_signature') and not self._export_current():
            return
        path = filedialog.asksaveasfilename(
            title="Exportar relatório PDF",
            defaultextension=".pdf",
            filetypes=[("PDF", "*.pdf")],
        )
        if not path:
            return
        try:
            from datetime import datetime
            from reportlab.lib import colors
            from reportlab.lib.enums import TA_CENTER, TA_LEFT
            from reportlab.lib.pagesizes import A4, landscape
            from reportlab.lib.styles import ParagraphStyle, getSampleStyleSheet
            from reportlab.lib.units import mm
            from reportlab.platypus import BaseDocTemplate, PageTemplate, Frame, NextPageTemplate, Paragraph, Spacer, Table, TableStyle, PageBreak, KeepTogether

            self.progress_var.set(0.0)
            self.status_var.set("A gerar relatório PDF...")
            self.update_idletasks()

            page_size = landscape(A4)
            margin_l = 16 * mm
            margin_r = 16 * mm
            margin_t = 18 * mm
            margin_b = 15 * mm
            doc = BaseDocTemplate(
                path,
                pagesize=page_size,
                rightMargin=margin_r,
                leftMargin=margin_l,
                topMargin=margin_t,
                bottomMargin=margin_b,
            )
            styles = getSampleStyleSheet()
            # Formatação pedida para a memória de ccálculo:
            # texto em Courier 10, subtítulos em Courier-Bold 12, espaçamento 1.5.
            styles.add(ParagraphStyle(name="ReportTitle", parent=styles["Title"], alignment=TA_CENTER, fontName="Courier-Bold", fontSize=14, leading=21, spaceAfter=10))
            styles.add(ParagraphStyle(name="ReportSubtitle", parent=styles["Normal"], alignment=TA_CENTER, fontName="Courier", fontSize=10, leading=15, textColor=colors.HexColor("#444444"), spaceAfter=8))
            styles.add(ParagraphStyle(name="BodyCourier", parent=styles["Normal"], fontName="Courier", fontSize=10, leading=15, spaceAfter=6))
            styles.add(ParagraphStyle(name="Small", parent=styles["Normal"], fontName="Courier", fontSize=8, leading=12))
            styles.add(ParagraphStyle(name="Cell", parent=styles["Small"], alignment=TA_LEFT, fontName="Courier", fontSize=8, leading=11))
            styles.add(ParagraphStyle(name="Section", keepWithNext=True, parent=styles["Heading2"], fontName="Courier-Bold", fontSize=12, leading=18, spaceBefore=9, spaceAfter=10))

            def header_footer(canvas, doc_obj):
                canvas.saveState()
                canvas.setTitle(f"{APP_NAME} - Relatório de Cálculo")
                canvas.setAuthor(APP_REPORT_AUTHOR)
                canvas.setSubject(APP_SUBJECT)
                canvas.setCreator(f"{APP_NAME} {APP_VERSION}")
                canvas.setKeywords(APP_KEYWORDS)
                try:
                    canvas._doc.info.producer = f"{APP_NAME} / ReportLab"
                except Exception:
                    pass
                w, h = canvas._pagesize
                canvas.setFont("Courier", 8)
                canvas.setFillColor(colors.grey)
                header_name = "WallsEC2"
                header_txt = header_name + " | Dimensionamento de Paredes (EC2)"
                canvas.drawString(margin_l, h - 10 * mm, header_txt)
                # Link invisível sobre o nome do programa no cabeçalho.
                header_w = canvas.stringWidth(header_name, "Courier", 8)
                canvas.linkURL(GITHUB_URL, (margin_l, h - 11.5 * mm, margin_l + header_w, h - 8.5 * mm), relative=0)
                canvas.drawRightString(w - margin_r, h - 10 * mm, f"Página {doc_obj.page}")
                canvas.line(margin_l, h - 12 * mm, w - margin_r, h - 12 * mm)
                footer_name = "WallsEC2"
                footer_txt = footer_name + " | " + datetime.now().strftime("%Y-%m-%d %H:%M")
                footer_x = w / 2.0
                canvas.drawCentredString(footer_x, 8 * mm, footer_txt)
                # Link invisível sobre o nome do programa no rodapé.
                footer_name_w = canvas.stringWidth(footer_name, "Courier", 8)
                footer_total_w = canvas.stringWidth(footer_txt, "Courier", 8)
                x0 = footer_x - footer_total_w / 2.0
                canvas.linkURL(GITHUB_URL, (x0, 6.5 * mm, x0 + footer_name_w, 9.5 * mm), relative=0)
                canvas.restoreState()

            # Template único: todo o relatório, incluindo o apêndice, em A4 paisagem.
            frame_a4 = Frame(margin_l, margin_b, page_size[0] - margin_l - margin_r, page_size[1] - margin_t - margin_b, id="A4L_frame")
            doc.addPageTemplates([
                PageTemplate(id="A4L", pagesize=page_size, frames=[frame_a4], onPage=header_footer),
            ])

            def fmt(v):
                if isinstance(v, float):
                    if not math.isfinite(v):
                        return "-"
                    return f"{v:.3f}"
                return "" if pd.isna(v) else str(v)

            def escape_pdf_text(s: str) -> str:
                return str(s).replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

            def simplify_status_reason(value) -> str:
                """Simplifica motivos extensos apenas para apresentação no PDF."""
                s = fmt(value).strip()
                sl = s.lower()
                if not s or s in {"-", "nan"}:
                    return "-"
                if "pendente" in sl or "por verificar" in sl or "parciais" in sl or "não conformidade" in sl:
                    return s
                if "v ed" in sl or "ved" in sl or "vrd" in sl or "corte" in sl:
                    return "Corte"
                if "mxy" in sl:
                    return "MXY dominante"
                if "wk" in sl or "fend" in sl:
                    if "limite" in sl:
                        return "Fendilhação no limite"
                    return "Fendilhação"
                if "unid" in sl or "unit" in sl:
                    return "Confirmar unidades"
                if "eixo" in sl or "axis" in sl:
                    return "Confirmar eixos"
                if "base" in sl and "insuf" in sl:
                    return "Base insuficiente"
                if len(s) > 38:
                    return s[:35].rstrip() + "..."
                return s

            def simplify_recommendation(value) -> str:
                """Gera uma nota curta para o PDF. O detalhe completo fica no Excel."""
                s = fmt(value).strip()
                sl = s.lower()
                if not s or s in {"-", "nan"}:
                    return "-"
                if "unid" in sl or "unit" in sl:
                    return "Confirmar unidades"
                if "eixo" in sl or "axis" in sl:
                    return "Confirmar eixos locais"
                if "fend" in sl or "wk" in sl or "els" in sl:
                    return "Confirmar ELS/fendilhação"
                if "corte" in sl or "vrd" in sl or "ved" in sl:
                    return "Rever corte"
                if "espess" in sl or "geometr" in sl:
                    return "Rever geometria"
                if len(s) > 36:
                    return s[:33].rstrip() + "..."
                return s

            PDF_HEADER_MAP = {
                "NM_X_util": "Util. N-M X", "NM_Y_util": "Util. N-M Y",
                "Stability_l0_mm": "l0 [mm]", "Stability_X_amplification": "Majoração X",
                "Stability_Y_amplification": "Majoração Y",
                "Panel": "Painel",
                "Node": "Nó",
                "Case": "Caso",
                "Status_global": "Estado seccional",
                "ELU_faixas": "ELU local", "wk_cargas_cond_mm": "w cargas* [mm]", "ELS_historico_ratio": "σt/fctk",
                "Status": "Estado",
                "Motivo_estado": "Motivo",
                "Acção_recomendada": "Nota",
                "Acao_recomendada": "Nota",
                "Recommended_action": "Nota",
                "Verification_reason": "Motivo",
                "caso_governante": "Caso gov. ELU",
                "node_governante": "Nó gov.",
                "util_max": "Util.",
                "util_M_max": "Util. M",
                "util_Qx_max": "Util. Qx",
                "util_Qy_max": "Util. Qy",
                "Sand_no_governante": "Nó gov.", "Sand_caso_governante": "Caso gov.", "Sand_util_max": "Sandwich util.", "Sand_steel_util_max": "Util. aço", "Sand_concrete_util_max": "Util. betão", "Sand_shear_util_max": "Util. corte", "Sand_Asw_req_max_mm2_m2": "Asw req. [mm²/m²]", "Sand_linhas_acima_1": "Linhas > 1", "Sand_linhas_sem_resultado": "Sem resultado", "Sand_linhas_trelica": "Com proposta Asw",
                "casca_experimental_max": "Casca (ensaio)",
                "casca_linhas_acima_1": "Casca > 1 (linhas)",
                "wk_QP_avaliadas": "wk avaliadas",
                "wk_QP_total": "QP total",
                "Transverse_links": "Ganchos por As,v > 2% Ac",
                "governing_case": "Caso gov. ELU",
                "is_QP_crack_case": "QP",
                "MXX_kNm_m": "MXX",
                "MYY_kNm_m": "MYY",
                "MXY_kNm_m": "MXY",
                "QXX_kN_m": "QXX",
                "QYY_kN_m": "QYY",
                "wk_x+_mm": "wk X+",
                "wk_x-_mm": "wk X-",
                "wk_y+_mm": "wk Y+",
                "wk_y-_mm": "wk Y-",
                "wk_max_mm": "wk máx.",
                "wmax_mm": "wmax",
                "Estabilidade_global_externa": "Estado externo",
                "responsavel": "Responsável",
                "metodo": "Método",
                "referencia_relatorio": "Referência do relatório",
                "Crack_control_status": "Estado wk",
                "Crack_control_note": "Nota wk",
                "Crack_gov": "wk gov.",
                "Optimization_mode": "Modo",
                "Acção recomendada": "Nota",
                "Acao recomendada": "Nota",
            }

            def display_value(column, value):
                if column in {"Status_global","Status"} and str(value) in {"Incompleto","OK*"}:
                    return {"Incompleto":"Condicionado","OK*":"Cumpre sob hipóteses"}[str(value)]
                if column == "Motivo_estado":
                    if "Sand_status" in self.df_results:
                        return compact_panel_reason(str(value))
                    return simplify_status_reason(value)
                if column == "Verification_reason":
                    return simplify_status_reason(value)
                if column in {"Acção recomendada", "Acao recomendada"}:
                    return fmt(value)
                if column in {"Acção_recomendada", "Acao_recomendada", "Recommended_action"}:
                    return simplify_recommendation(value)
                return fmt(value)

            # ReportLab Courier uses WinAnsi. Greek symbols use its built-in
            # Symbol font and subscripts use native Paragraph markup.
            import re as _re
            def notation(text):
                value=escape_pdf_text(text)
                value=_re.sub(r'[αβγδΔεηθλμνπρσφΦω]',lambda m:'<font name="Symbol">'+m.group(0)+'</font>',value)
                value=value.replace('∞','<font name="Symbol">∞</font>')
                for a,b in {'₀':'0','ₖ':'k','ₛ':'s','꜀':'c'}.items():value=value.replace(a,'<sub>'+b+'</sub>')
                return value
            pdf_labels=dict(PDF_HEADER_MAP,**ENGINEERING_LABELS)
            pdf_labels.update({'Auto_phi_x':'φ<sub>ef,x</sub>','Auto_phi_y':'φ<sub>ef,y</sub>'})
            def pdf_label(c):
                return notation(pdf_labels.get(c,c)).replace('&lt;sub&gt;','<sub>').replace('&lt;/sub&gt;','</sub>')

            def as_par(v, column=None):
                value = display_value(column, v)
                # Permite hyperlinks ReportLab já formatados, mantendo o URL invisível no texto.
                if column not in {"responsavel","metodo","referencia_relatorio","Estabilidade_global_externa"} and isinstance(value, str) and ("<a href=" in value.lower() or "<link href=" in value.lower()):
                    return Paragraph(value, styles["Cell"])
                return Paragraph(notation(value), styles["Cell"])

            def add_table(title, df, cols=None, max_rows=30, widths=None, note_cols=None, note_title="Notas"):
                story.append(Paragraph(title, styles["Section"]))
                if df is None or df.empty:
                    story.append(Paragraph("Sem dados disponíveis.", styles["Small"]))
                    story.append(Spacer(1, 5))
                    return
                show = df.head(max_rows).copy()
                note_cols = note_cols or []
                if cols is None:
                    cols_use = list(show.columns)
                else:
                    cols_use = [c for c in cols if c in show.columns]
                # As colunas definidas em note_cols não entram no quadro principal; são resumidas abaixo.
                main_cols = [c for c in cols_use if c not in note_cols]
                if not main_cols:
                    story.append(Paragraph("Sem colunas disponíveis para este quadro.", styles["Small"]))
                    return
                data = [[Paragraph(pdf_label(c), styles["Cell"]) for c in main_cols]]
                for _, row in show[main_cols].iterrows():
                    data.append([as_par(row[c], c) for c in main_cols])
                if widths is None:
                    widths = [max(18 * mm, min(34 * mm, 6 * mm + len(str(pdf_labels.get(c, c))) * 1.1 * mm)) for c in main_cols]
                    if "Motivo_estado" in main_cols: widths[main_cols.index("Motivo_estado")]=75*mm
                    if "ELU_faixas" in main_cols: widths[main_cols.index("ELU_faixas")]=37*mm
                    if "Crack_control_status" in main_cols: widths[main_cols.index("Crack_control_status")]=38*mm
                usable_width = page_size[0] - margin_l - margin_r
                if sum(widths) > usable_width:
                    widths = [w * usable_width / sum(widths) for w in widths]
                tbl = Table(data, repeatRows=1, colWidths=widths)
                tbl.setStyle(TableStyle([
                    ("BACKGROUND", (0, 0), (-1, 0), colors.HexColor("#D9EAF7")),
                    ("TEXTCOLOR", (0, 0), (-1, 0), colors.HexColor("#1F4E79")),
                    ("GRID", (0, 0), (-1, -1), 0.25, colors.HexColor("#B7B7B7")),
                    ("VALIGN", (0, 0), (-1, -1), "TOP"),
                    ("FONTSIZE", (0, 0), (-1, -1), 8),
                    ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, colors.HexColor("#F7F7F7")]),
                ]))
                story.append(tbl)

                # Notas compactas fora do quadro, para evitar tabelas muito largas.
                notes = []
                for col in note_cols:
                    if col in show.columns:
                        for _, row in show.iterrows():
                            txt = str(row[col]) if col == "Crack_control_note" else simplify_recommendation(row[col])
                            if txt and txt != "-" and txt not in notes:
                                notes.append(txt)
                if notes:
                    story.append(Paragraph(f"{note_title}: " + escape_pdf_text("; ".join(notes[:6])) + ".", styles["Small"]))
                if len(df) > max_rows:
                    story.append(Paragraph(f"Nota: quadro truncado no relatório. Linhas apresentadas: {max_rows} de {len(df)}. Consultar ficheiro Excel para resultados completos.", styles["Small"]))
                story.append(Spacer(1, 6))

            def build_pdf_cracking_summary():
                """Resumo de fendilhação para apresentação no PDF.

                O PDF deve apresentar explicitamente os valores de wk da combinação quase-permanente,
                sem misturar linhas ELU. O detalhe completo continua disponível no Excel.
                """
                if self.df_results is None or self.df_results.empty:
                    return pd.DataFrame()
                df = self.df_results.copy()
                if "is_QP_crack_case" in df.columns:
                    df = df[df["is_QP_crack_case"].astype(str).str.lower().eq("sim")].copy()
                if df.empty:
                    return pd.DataFrame([{
                        "Panel": "-", "Node": "-", "Case": self.var_qp_case.get() or "não indicada",
                        "wk_x+_mm": float("nan"), "wk_x-_mm": float("nan"),
                        "wk_y+_mm": float("nan"), "wk_y-_mm": float("nan"),
                        "wk_max_mm": float("nan"), "wmax_mm": safe_float(self.var_wmax.get(), 0.30),
                        "Crack_gov": "-", "Crack_control_status": "Não avaliado",
                        "Crack_control_note": "Sem cálculo explícito de wk. Seleccionar a combinação quase-permanente para verificação ELS."
                    }])

                wk_cols = ["wk_x+_mm", "wk_x-_mm", "wk_y+_mm", "wk_y-_mm"]
                rows = []
                for panel, grp in df.groupby("Panel", dropna=False):
                    g = grp.copy()
                    if "wk_max_mm" not in g.columns:
                        continue
                    valid = g[pd.to_numeric(g["wk_max_mm"], errors="coerce").map(math.isfinite)].copy()
                    missing_count = len(g) - len(valid)
                    if valid.empty:
                        r = g.iloc[0].copy()
                        r["Crack_control_status"] = "Não avaliado"
                        r["Node"] = "—"
                        if "ELS_historico_ratio" in g and g.ELS_historico_ratio.notna().any():
                            r=g.loc[g.ELS_historico_ratio.idxmax()].copy()
                            r["Crack_control_status"]=f"{int(g.get('wk_cargas_cond_mm',pd.Series(index=g.index,dtype=float)).eq(0).sum())}/{len(g)} QP avaliadas*"
                        r["Crack_control_note"] = f"0/{len(g)} linhas QP com abertura calculada. " + "; ".join(
                            dict.fromkeys(g["Crack_control_note"].dropna().astype(str)))
                        if "wk_cargas_cond_mm" in g and g.wk_cargas_cond_mm.eq(0).all():
                            r = g.loc[g.ELS_historico_ratio.idxmax()].copy()
                            r["Crack_control_status"] = "Sem fendas por cargas*"
                            r["Crack_control_note"] = "* Resultado condicional à secção inicialmente íntegra, história de cargas, idade e ausência de coacção. Não é abertura total regulamentar."
                    else:
                        idx = pd.to_numeric(valid["wk_max_mm"], errors="coerce").idxmax()
                        r = valid.loc[idx].copy()
                        if missing_count:
                            if r["Crack_control_status"] == "OK":
                                r["Crack_control_status"] = "Parcial"
                            r["Crack_control_note"] = (
                                f"{missing_count}/{len(g)} linhas QP sem wk. "
                                + str(r.get("Crack_control_note", ""))
                            )
                    vals = {c: safe_float(r.get(c, float("nan")), float("nan")) for c in wk_cols}
                    finite_vals = {c: v for c, v in vals.items() if math.isfinite(v)}
                    if finite_vals:
                        gov_col = max(finite_vals, key=finite_vals.get)
                        gov_txt = gov_col.replace("wk_", "").replace("_mm", "")
                    else:
                        gov_txt = "-"
                    rows.append({
                        "Panel": r.get("Panel", panel),
                        "Node": r.get("Node", ""),
                        "Case": r.get("Case", ""),
                        "wk_x+_mm": r.get("wk_x+_mm", float("nan")),
                        "wk_x-_mm": r.get("wk_x-_mm", float("nan")),
                        "wk_y+_mm": r.get("wk_y+_mm", float("nan")),
                        "wk_y-_mm": r.get("wk_y-_mm", float("nan")),
                        "wk_max_mm": r.get("wk_max_mm", float("nan")),
                        "wk_cargas_cond_mm": 0.0 if "wk_cargas_cond_mm" in g and g.wk_cargas_cond_mm.eq(0).all() else float("nan"),
                        "ELS_historico_ratio": g.get("ELS_historico_ratio",pd.Series(dtype=float)).max(),
                        "wmax_mm": r.get("wmax_mm", safe_float(self.var_wmax.get(), 0.30)),
                        "Crack_gov": gov_txt,
                        "Crack_control_status": r.get("Crack_control_status", ""),
                        "Crack_control_note": r.get("Crack_control_note", ""),
                    })
                out = pd.DataFrame(rows)
                if out.empty:
                    return out
                return out.sort_values("wk_max_mm", ascending=False).reset_index(drop=True)

            story = []
            story.append(Spacer(1, 18))
            story.append(Paragraph("RELATÓRIO DE CÁLCULO", styles["ReportTitle"]))
            story.append(Paragraph("Dimensionamento de paredes de betão armado segundo EC2", styles["ReportSubtitle"]))
            story.append(Spacer(1, 10))

            project_data = [
                ["Programa", f'<link href="{GITHUB_URL}">WallsEC2</link> - Paredes de Betão Armado (EC2)'],
                ["Versão", APP_VERSION],
                ["Data de emissão", datetime.now().strftime("%Y-%m-%d %H:%M")],
                ["Espessura da parede", f"{self.var_thickness.get()} mm"],
                ["Recobrimento nominal", f"{self.var_cover.get()} mm"],
                ["Classe de betão", self.var_concrete.get()],
                ["Classe de Aço", f"fyk = {self.var_steel.get()} MPa"],
                ["Esforços", self.var_wa_method.get()],
                ["Eixos locais", "Y local vertical" if self.var_y_vertical.get() else "X local vertical"],
                ["Troca X/Y", "Sim" if self.var_swap_axes.get() else "Não"],
                ["Unidades de momentos", self.var_moment_unit.get()],
                ["Unidades de esforço transverso", self.var_shear_unit.get()],
                ["Verificação wk", "Sim" if self.var_crack_check.get() else "Não"],
                ["ELU seleccionadas", self.var_elu_cases.get() or "não indicadas"],
                ["Convenção N", self.var_axial_convention.get()],
                ["l0 da faixa", "Por painel/direcção — ver parâmetros automáticos" if "Auto_l0_x" in self.df_results else self.var_l0.get() + " mm"],
                ["Fluência efectiva", "Por painel/direcção — ver parâmetros automáticos" if "Auto_phi_x" in self.df_results else self.var_phi_eff.get()],
                ["ELS-CAR", self.var_car_cases.get()],
                ["ELS-FREQ", self.var_freq_cases.get()],
                ["Limite de deformação εud", self.var_eps_ud.get()],
                ["Combinação quase-permanente", self.var_qp_case.get() or "não indicada"],
                ["Limite wmax", f"{self.var_wmax.get()} mm"],
                ["Optimização de armaduras", (self.var_rebar_strategy.get() if self.var_optimize_rebar.get() else "Automática directa")],
                ["Base vertical", f"Ø{self.var_base_v_phi.get()}//{self.var_base_v_spacing.get()}"],
                ["Base horizontal", f"Ø{self.var_base_h_phi.get()}//{self.var_base_h_spacing.get()}"],
            ]
            tbl = Table([[Paragraph("Parâmetro", styles["Cell"]), Paragraph("Valor", styles["Cell"])] ] + [[as_par(a), as_par(b)] for a,b in project_data], colWidths=[60*mm, 110*mm])
            tbl.setStyle(TableStyle([
                ("BACKGROUND", (0,0), (-1,0), colors.HexColor("#D9EAF7")),
                ("GRID", (0,0), (-1,-1), 0.25, colors.HexColor("#B7B7B7")),
                ("VALIGN", (0,0), (-1,-1), "TOP"),
                ("TOPPADDING", (0,0), (-1,-1), 1.5),
                ("BOTTOMPADDING", (0,0), (-1,-1), 1.5),
                ("ROWBACKGROUNDS", (0,1), (-1,-1), [colors.white, colors.HexColor("#F7F7F7")]),
            ]))
            story.append(tbl)
            story.append(PageBreak())

            n_panels = len(self.df_summary) if self.df_summary is not None else 0
            n_lines = len(self.df_results) if self.df_results is not None else 0
            status_counts = self.df_summary["Status_global"].value_counts().to_dict() if self.df_summary is not None and "Status_global" in self.df_summary.columns else {}
            resumo_txt = (
                f"Foram analisadas {n_lines} linhas de esforços seleccionadas, correspondentes a {n_panels} painéis. "
                f"Limites seccionais satisfeitos sob hipóteses: {status_counts.get('OK*',0)}; condicionados: {status_counts.get('Incompleto',0)}; não conformes: {status_counts.get('Não conforme',0)}. "
                "O cálculo considera os painéis como elementos de placa/casca, com dimensionamento por faixas de 1 m. "
                "N-M e segunda ordem: faixas X/Y. Os resultados pressupõem validade dos esforços e combinações importados, travamentos e pormenorização compatíveis."
            )
            story.append(Paragraph("Síntese das verificações", styles["Section"]))
            story.append(Paragraph(resumo_txt, styles["BodyCourier"]))
            story.append(Spacer(1, 8))
            self.progress_var.set(20.0); self.update_idletasks()

            add_table("1. Resumo por painel", self.df_summary, cols=[
                "Panel", "ELU_modelo", "util_max", "Sand_util_max", "ELS_cargas", "ELS_tensoes", "Segunda_ordem_faixas", "Status_global"
            ], max_rows=36, widths=[16*mm,48*mm,20*mm,25*mm,44*mm,42*mm,35*mm,33*mm])
            if "Sand_status" in self.df_results:
                conditions=self.df_summary.loc[self.df_summary.Status_global.eq("Incompleto")].copy()
                conditions["Motivo_estado"]=conditions.Motivo_estado.map(lambda v: "; ".join(part for part in str(v).split("; ") if not any(k in part for k in ("condições da secção 6.109","limite conservador de triagem","transferência adicional LL.115"))))
                if not conditions.empty:
                    add_table("Verificações condicionantes",conditions,cols=["Panel","Compressao_faces","Motivo_estado"],max_rows=100,widths=[20*mm,65*mm,175*mm])
                story.append(Paragraph("* Via elástica e ELS por cargas: secção inicialmente íntegra, histórico de ações e ausência de coação relevante. Para as situações condicionadas por LL(115)(c), requer-se verificação complementar.",styles["Small"]))
            inter=getattr(self,"df_interlayer",pd.DataFrame())
            if not inter.empty:
                check=inter.rename(columns={"Estado_intercamadas":"Estado","Limite_adicional_kN_m":"ΔVEd,lim [kN/m]","Reserva_kN_m":"Reserva [kN/m]","Margem_kN_m":"Margem [kN/m]","referencia_relatorio":"Relatório"})
                add_table("Corte adicional por transferência intercamadas — LL(115)(c)",check,cols=["Panel","ΔVEd,lim [kN/m]","Reserva [kN/m]","Margem [kN/m]","Estado","Relatório"],max_rows=100)
                story.append(Paragraph("* Comparação conservadora com limite externo documentado; não constitui validação do relatório espacial. A verificação não considera armadura específica de corte.",styles["Small"]))
            ext=getattr(self,"df_external_stability",pd.DataFrame())
            if not ext.empty and "Sand_status" not in self.df_results:
                story.append(Paragraph("Estabilidade global: declaração externa registada. O WallsEC2 não verifica o conteúdo do relatório e mantém separados os estados locais. Consultar a referência e os identificadores SHA-256 na exportação Excel.",styles["Small"]))
                add_table("Estabilidade global — declaração externa",ext,cols=["Panel","Estabilidade_global_externa","responsavel","metodo","referencia_relatorio"],max_rows=len(ext),widths=[18*mm,42*mm,38*mm,58*mm,68*mm])
            self.progress_var.set(40.0); self.update_idletasks()

            add_table("2. Armadura adoptada por painel", self.df_governing, cols=[
                "Panel", "Status", "Acção_recomendada", "util_max", "X+_adopted", "X-_adopted", "Y+_adopted", "Y-_adopted", "Transverse_links", "governing_case"
            ], max_rows=36, note_cols=["Acção_recomendada"], widths=[18*mm, 26*mm, 18*mm, 31*mm, 31*mm, 31*mm, 31*mm, 24*mm, 24*mm])
            
            self.progress_var.set(52.0); self.update_idletasks()

            df_cracking_pdf = build_pdf_cracking_summary()
            crack_cols=["Panel", "Node", "Case", "wk_x+_mm", "wk_x-_mm", "wk_y+_mm", "wk_y-_mm", "wk_max_mm", "wk_cargas_cond_mm", "ELS_historico_ratio", "wmax_mm", "Crack_control_status", "Crack_control_note"]
            if not df_cracking_pdf.empty and "wk_cargas_cond_mm" in df_cracking_pdf and df_cracking_pdf.wk_max_mm.isna().all():
                # Only the explicitly conditional load-induced result is reported;
                # do not print five redundant blank columns or relabel it as wk.
                crack_cols=["Panel","Node","Case","wk_cargas_cond_mm","ELS_historico_ratio","wmax_mm","Crack_control_status"]
                add_table("3. Fendilhação — avaliação por cargas em ELS-QP",df_cracking_pdf,cols=crack_cols,max_rows=36,widths=[20*mm,24*mm,36*mm,45*mm,42*mm,29*mm,66*mm])
            else:
                add_table("3. Verificação da fendilhação — ELS quase-permanente",df_cracking_pdf,cols=crack_cols,max_rows=36,note_cols=["Crack_control_note"])
            if "wk_cargas_cond_mm" in self.df_results:
                story.append(Paragraph("* Abertura por cargas igual a zero sob as hipóteses indicadas. Não representa a abertura de fendas devida a deformações impostas.",styles["Small"]))
            story.append(Paragraph("O campo de ganchos indica se foi excedido o limiar de armadura vertical total (2% de Ac). Um Não não dispensa a verificação das restantes regras de ligação entre malhas.", styles["Small"]))
            if "wk_x+_mm" in crack_cols:
                story.append(Paragraph("Nota: as larguras de fenda X+, X−, Y+, Y− referem-se às faces e direcções locais do painel. O valor wk máx. é o valor governante para a combinação quase-permanente indicada.", styles["Small"]))
            if "ELS_sigma_t_upper_MPa" in self.df_results:
                stress=self.df_results[self.df_results.Combo_type.isin(["ELS-CAR","ELS-FREQ","ELS-QP"])].groupby(["Panel"],as_index=False)[["ELS_sigma_t_upper_MPa","ELS_sigma_c_upper_MPa","ELS_sigma_s_max_MPa","ELS_fctk005_MPa"]].max()
                stress=stress.rename(columns={"Combo_type":"Combinação","ELS_sigma_t_upper_MPa":"σt sup. [MPa]","ELS_sigma_c_upper_MPa":"σc sup. [MPa]","ELS_sigma_s_max_MPa":"σs el. [MPa]","ELS_fctk005_MPa":"fctk,0.05 [MPa]"})


                if "ELS_72_estado" in self.df_results:
                    check=self.df_results[self.df_results.Combo_type.isin(["ELS-CAR","ELS-QP"])].groupby(["Panel","Combo_type"],as_index=False).agg(eta_c=("ELS_72_eta_c","max"),eta_s=("ELS_72_eta_s","max"),estado=("ELS_72_estado",lambda v: "Satisfeito*" if v.str.startswith("Limites satisfeitos").all() else "Condicionado"))
                    check=check.rename(columns={"Combo_type":"Combinação","eta_c":"ηc","eta_s":"ηs","estado":"Estado"})
                    add_table("ELS — limitação de tensões (7.2)",check,max_rows=120,widths=[23*mm,38*mm,38*mm,38*mm,60*mm])
                    story.append(Paragraph("CAR: 0,60 fck (limite conservador) e 0,80 fyk para ações diretas; QP: 0,45 fck, limiar de fluência não linear. * Condicional às hipóteses do modelo de serviço, história de cargas e coacção. FREQ não tem limite próprio em 7.2.",styles["Small"]))
            add_table("Envolvente ELU — interacção N-M por faixa X/Y", WallsEC2App.build_nm_envelope(self.df_results), max_rows=100)
            shear_cols=["Panel","Asw_X_req_mm2_m2","Asw_Y_req_mm2_m2"]
            if all(c in self.df_summary for c in shear_cols) and self.df_summary[shear_cols[1:]].gt(0).any().any():
                sh=self.df_summary[shear_cols].copy().rename(columns={"Asw_X_req_mm2_m2":"Asw,X [mm²/m²]","Asw_Y_req_mm2_m2":"Asw,Y [mm²/m²]"})
                add_table("Corte — armadura transversal específica requerida por faixa (proposta)",sh,max_rows=100)
                story.append(Paragraph("EC2 6.2.3: cot θ=1, z=0,9d, sem contribuição aditiva de VRd,c. Valores são propostas por direcção, não armadura instalada; verificar tracção adicional, amarração e interacção da casca.",styles["Small"]))
            coverage= WallsEC2App.build_stability_coverage(self.df_results)
            if "Sand_status" in self.df_results and not coverage.empty:
                compact=[]
                for panel,group in self.df_results[self.df_results.Combo_type.eq("ELU")].groupby("Panel"):
                    row={"Panel":panel,"Linhas ELU":len(group)}
                    for a in "XY":
                        st=group[f"Stability_{a}_status"].astype(str)
                        row[f"{a}: dispensadas"]=int(st.str.startswith(("Dispensada","Não requerida")).sum())
                        row[f"{a}: incluídas"]=int(st.str.startswith("Incluída").sum())
                        row[f"{a}: restantes"]=len(st)-row[f"{a}: dispensadas"]-row[f"{a}: incluídas"]
                    compact.append(row)
                add_table("Cobertura de segunda ordem — faixas X/Y",pd.DataFrame(compact),max_rows=100,widths=[18*mm,32*mm,34*mm,34*mm,34*mm,34*mm,34*mm,34*mm])
            else:add_table("Cobertura de segunda ordem — todas as linhas ELU",coverage,max_rows=100)
            if "Auto_l0_x" in self.df_results:
                cols=["Panel","Auto_l0_x","Auto_l0_y","Auto_h0","Auto_phi_final","Auto_phi_x","Auto_phi_y"]
                add_table("Parâmetros de estabilidade por painel",self.df_results[cols].drop_duplicates(),max_rows=36)
            if "Sand_status" in self.df_results:
                cols=["Panel","Sand_util_1ordem_max","Sand_util_max","Sand_no_governante","Sand_caso_governante","Sand_steel_util_max","Sand_concrete_util_max","Sand_shear_util_max","Sand_Asw_req_max_mm2_m2","Sand_linhas_acima_1","Sand_linhas_sem_resultado","Sand_linhas_trelica"]
                add_table("ELU — modelo sandwich (Anexo LL e Anexo F)",self.df_summary,cols=cols,max_rows=100)
                
                story.append(Paragraph("η aço, η betão e η corte: máximos por painel, não necessariamente concomitantes. η sandwich inclui o limite de triagem quando 6.109 não está demonstrada. Se governa o betão, rever espessura, classe de betão ou esforços; acrescentar aço não garante a resolução.",styles["Small"]))
                add_table("Majoração de momentos no modelo sandwich",self.df_summary,cols=["Panel","Sand_delta_Mx_max","Sand_delta_My_max","Sand_2ordem_pendente","Segunda_ordem_faixas"],max_rows=100,widths=[25*mm,49*mm,49*mm,75*mm,64*mm])
                story.append(Paragraph("Envolvente discreta de momentos originais e incrementos por faixa, incluindo imperfeições e segunda ordem quando calculáveis. Preserva N, Mxy e Q concomitantes. Corte resultante pelas secções 6.2.2/6.2.3. Anexo LL: metodologia complementar para edifícios.",styles["Small"]))
            else:
                if "ShellQP_status" in self.df_results:
                    qp=self.df_results[self.df_results.Combo_type.eq("ELS-QP")]
                    diag=qp.groupby(["Panel","ShellQP_status"],dropna=False).size().reset_index(name="Linhas")
                    if "ShellQP_indicator_max_mm" in qp:
                        v=qp.groupby("Panel").ShellQP_indicator_max_mm.agg(["count","max"]).reset_index().rename(columns={"count":"Indicadores finitos","max":"Indicador max [mm]"})
                        diag=diag.merge(v,on="Panel",how="left")
                    add_table("Diagnóstico QP de casca: indicador experimental, não é wk",diag,max_rows=36)
                add_table("Diagnóstico membrana-flexão (1.ª ordem; não é verificação ELU)", shell_screen_envelope(self.df_results), max_rows=36)
                add_table("Casca: equilíbrio e capacidade no modelo idealizado (1.ª ordem)", shell_capacity_envelope(self.df_results), max_rows=36)
                phys=physical_layers_summary(self.df_results)
                add_table("Camadas físicas — ensaios, não verificação regulamentar", phys, cols=["Panel","Combinação","Linhas","PhysELU_util","PhysELU_insuficientes","PhysELU_sem_resultado","PhysShear_util","PhysQP_completas","PhysQP_parciais","PhysELS_ratio_c_06fck","PhysELS_ratio_s_08fyk","PhysELS_ratio_c_045fck","PhysQP_candidate_max_mm","PhysQP_sigma_s_max_MPa"],max_rows=40)
                if "PhysLL_util" in self.df_results:
                    ll=self.df_summary[["Panel","LL_util_resultante","LL_util_sem_credito","LL_Asw_proposta_mm2_m2","LL_linhas_acima_1","LL_equilibrio_faces_util"]].copy().rename(columns={"LL_util_resultante":"vEd/VRdc (com σcp)","LL_util_sem_credito":"Sem crédito comp.","LL_Asw_proposta_mm2_m2":"Asw proposta [mm²/m²]","LL_linhas_acima_1":"Linhas > 1","LL_equilibrio_faces_util":"Util. faces com treliça"})
                    add_table("Corte resultante — ensaio de interacção LL.109–115",ll,max_rows=100)
                    story.append(Paragraph("Compressão concomitante limitada a 0,2 fcd; a alternativa sem crédito de compressão é mantida. Propostas de armadura não são instaladas automaticamente. A treliça acrescenta forças de membrana às faces; pormenorização, amarração, sinais modais e estabilidade global por confirmar.",styles["Small"]))
                if "Core_status" in self.df_results:
                    core=self.df_results[self.df_results.Core_status.notna()]
                    add_table("Casos críticos — ensaio de núcleo e treliça",core,cols=["Panel","Node","Case","Core_status","Core_core_mm","Core_cot_theta","Core_core_util","Core_face_util","Core_asw_required","Core_phi","Core_pitch_x","Core_pitch_y"],max_rows=30)
                    story.append(Paragraph("Propostas de uma perna eficaz normal por célula; não instaladas. O modelo de núcleo é experimental, de primeira ordem, e não substitui a verificação de amarração e de estabilidade.",styles["Small"]))
                if "Asym_status" in self.df_results:
                    asym=self.df_results[self.df_results.Asym_status.notna()]
                    add_table("Casos residuais — sensibilidade a bandas assimétricas",asym,cols=["Panel","Node","Case","Asym_status","Asym_fraction_plus","Asym_fraction_minus","Asym_core_mm","Asym_core_z_mm","Asym_face_util","Asym_core_util","Asym_asw_required"],max_rows=30)
                    story.append(Paragraph("Ensaio alternativo, sem alteração do modelo simétrico. Núcleo de 20% da espessura; bandas disjuntas com área líquida. Quando vEd não excede VRdc, o equilíbrio N-M e o corte são avaliados separadamente. Não demonstra a resistência integral da casca.",styles["Small"]))
                if "AsymTruss_status" in self.df_results:
                    truss=self.df_results[self.df_results.AsymTruss_status.notna()]
                    add_table("Casos residuais — alternativa com treliça explícita",truss,cols=["Panel","Node","Case","AsymTruss_status","AsymTruss_face_util","AsymTruss_core_util","AsymTruss_link_util","AsymTruss_asw_proposed","AsymTruss_tensor_residual"],max_rows=30)
                    story.append(Paragraph("Ensaio adicional com armadura transversal proposta mesmo quando vEd não excede VRdc. Equilíbrio seccional do tensor do núcleo e força normal equilibrada pelas ligações idealizadas. Não comprova amarração, compatibilidade ou resistência integral; nenhuma armadura é assumida instalada.",styles["Small"]))
                if "PhysShared_status" in self.df_results:
                    shared=self.df_results[self.df_results.PhysShared_status.notna()]
                    add_table("Casos críticos — campo partilhado de núcleo (experimental)",shared,cols=["Panel","Node","Case","PhysShared_status","PhysShared_util","PhysShared_core_util","PhysShared_outer_util","PhysShared_asw_proposed","PhysShared_residual"],max_rows=30)
                    story.append(Paragraph("Equilíbrio simultâneo de N, M, Q e Nzz=0, com orçamento de compressão comum no núcleo. Ligações propostas não instaladas; a discretização estática não demonstra compatibilidade, amarração ou resistência regulamentar.",styles["Small"]))
                if "History_plus_status" in self.df_results:
                    hist=[]
                    for panel,g in self.df_results[self.df_results.Combo_type.eq("ELS-QP")].groupby("Panel"):
                        a=g.History_plus_wk_conditional_mm.eq(0);b=g.History_minus_wk_conditional_mm.eq(0)
                        hist.append({"Panel":panel,"QP":len(g),"Ambas meias espessuras sem excedência":int((a&b).sum()),"Restantes":int((~(a&b)).sum())})
                    add_table("ELS — triagem elástica face a fctk,0.05",pd.DataFrame(hist),max_rows=100)
                    story.append(Paragraph("Não atribui wk regulamentar. Triagem das meias espessuras com tensões no plano e distribuição parabólica elástica de Qx/Qy na secção bruta. Limite de discretização numérica incluído; não é solução elástica 3D junto a descontinuidades. Ausência de excedência de 0,7 fctm exige confirmar história, idade e ausência de deformações impostas.",styles["Small"]))
                add_table("ELS — tensões no modelo experimental sem tracção do betão", phys[phys["Combinação"].str.startswith("ELS")] if not phys.empty else phys, cols=["Panel","Combinação","Linhas","PhysCracked_ratio_c_06fck","PhysCracked_ratio_s_08fyk","PhysCracked_ratio_c_045fck"],max_rows=40)
                if "PhysCompat_status" in self.df_results:
                    ct=self.df_results[self.df_results.PhysCompat_status.notna()]
                    add_table("Casos críticos — equilíbrio compatível experimental em toda a espessura",ct,cols=["Panel","Node","Case","PhysELU_util","PhysCompat_status","PhysCompat_strain_ratio","PhysCompat_compression_ratio","PhysCompat_residual_mpa"],max_rows=36)
                    story.append(Paragraph("A análise compatível é independente e de primeira ordem, sem reserva para corte transversal. O rácio de extensão e o rácio de compressão não substituem a utilização do modelo anterior nem a verificação de casca.",styles["Small"]))
                story.append(Paragraph("Hipótese: armadura vertical exterior, duas bandas exteriores de 0,35h, cada uma dividida em três subcamadas, e 16 direcções discretas. ELS: CAR/FREQ com Ecm instantâneo, QP com módulo efectivo; área e centroide líquidos de betão nos modelos de bandas e fendilhado. Histórico elástico limitado às combinações importadas; sem retracção. 0,6 fck em CAR é referência para XD/XF/XS; 0,45 fck em QP é critério de fluência linear, não limite de rotura. Valores de abertura são candidatos experimentais, não wk.",styles["Small"]))
            story.append(Paragraph("NEd positivo em compressão; MEd inclui os incrementos de faixa aplicáveis.", styles["Small"]))
            self.progress_var.set(58.0); self.update_idletasks()

            add_table("4. Zonas de armadura", self.df_zones, cols=[
                "Zona", "Painéis", "Status", "util_max", "X+", "X-", "Y+", "Y-", "Armadura transversal", "Nota"
            ], max_rows=40, note_cols=["Nota"])

            if "Sand_status" not in self.df_results: add_table("5. Optimização de armaduras — síntese por painel", self.df_optimization.sort_values("util_max", ascending=False).drop_duplicates("Panel") if not self.df_optimization.empty else self.df_optimization, cols=[
                "Panel", "Status", "Optimization_mode", "X+_base", "X+_additional", "X+_rebar", "Y+_base", "Y+_additional", "Y+_rebar", "util_max"
            ], max_rows=36)
            if "Sand_status" not in self.df_results: add_table("6. Diagnóstico", self.df_diagnostic, cols=[
                "Painel", "Severidade", "Problema", "Acção recomendada", "Origem"
            ], max_rows=40, widths=[17*mm,22*mm,110*mm,86*mm,27*mm])
            self.progress_var.set(68.0); self.update_idletasks()

            if "Sand_status" not in self.df_results: add_table("7. Validação da tabela importada", self.df_data_validation, cols=[
                "Categoria", "Item", "Estado", "Resultado", "Nota"
            ], max_rows=50, widths=[35*mm, 45*mm, 28*mm, 50*mm, 95*mm])
            if "Sand_status" not in self.df_results: add_table("8. Croquis textual por zona", self.df_sketches, cols=[
                "Zona", "Painéis", "Croquis_textual", "Nota_desenho"
            ], max_rows=20, widths=[18*mm, 50*mm, 125*mm, 72*mm])

            if "Sand_status" not in self.df_results: add_table("9. Verificação de unidades e consistência", self.df_unit_check, cols=[
                "Grandeza", "Unidade selecionada", "Factor aplicado", "Máximo convertido", "Unidade interna", "Nota"
            ], max_rows=10, widths=[38*mm,35*mm,20*mm,28*mm,25*mm,119*mm])
            add_table("5. Notas normativas e hipóteses de cálculo" if "Sand_status" in self.df_results else "10. Notas normativas e hipóteses de cálculo", self.df_notes, cols=[
                "Tema", "Critério adoptado", "Nota"
            ], max_rows=30, widths=[40*mm, 55*mm, 155*mm])
            self.progress_var.set(80.0); self.update_idletasks()

            # Apêndice reduzido com linhas críticas em A4 paisagem, com colunas compactas.
            if self.df_results is not None and not self.df_results.empty and "Sand_status" not in self.df_results:
                story.append(PageBreak())
                crit = self.df_results.sort_values("util_max", ascending=False).head(20)
                add_table("11. Apêndice - linhas críticas por utilização", crit, cols=[
                    "Panel", "Node", "Case", "is_QP_crack_case", "MXX_kNm_m", "MYY_kNm_m", "MXY_kNm_m", "QXX_kN_m", "QYY_kN_m", "wk_max_mm", "Status", "Recommended_action"
                ], max_rows=20, note_cols=["Recommended_action"], widths=[15*mm, 16*mm, 22*mm, 14*mm, 21*mm, 21*mm, 21*mm, 21*mm, 21*mm, 16*mm, 18*mm])
            self.progress_var.set(90.0); self.update_idletasks()

            doc.build(story)
            self.progress_var.set(100.0)
            self.status_var.set(f"Relatório PDF exportado: {path}")
        except ImportError:
            self.progress_var.set(0.0)
            messagebox.showerror("Erro", "A biblioteca reportlab não está instalada. Instale com: pip install reportlab")
        except Exception as e:
            self.progress_var.set(0.0)
            messagebox.showerror("Erro", str(e))



    def _config_vars(self) -> Dict[str, tk.Variable]:
        return {
            "thickness_mm": self.var_thickness,
            "cover_mm": self.var_cover,
            "concrete_class": self.var_concrete,
            "steel_fyk": self.var_steel,
            "local_y_is_vertical": self.var_y_vertical,
            "swap_axes": self.var_swap_axes,
            "limit_spacing_250": self.var_crack_spacing,
            "wk_check": self.var_crack_check,
            "elu_cases": self.var_elu_cases,
            "axial_convention": self.var_axial_convention,
            "characteristic_cases": self.var_car_cases,
            "frequent_cases": self.var_freq_cases,
            "effective_length_mm": self.var_l0,
            "creep_effective": self.var_phi_eff,
            "steel_ultimate_strain": self.var_eps_ud,
            "qp_case": self.var_qp_case,
            "combo_type": self.var_combo_type,
            "wmax_mm": self.var_wmax,
            "moment_unit": self.var_moment_unit,
            "shear_unit": self.var_shear_unit,
            "phi_min": self.var_phi_min,
            "phi_max": self.var_phi_max,
            "optimize_rebar": self.var_optimize_rebar,
            "rebar_strategy": self.var_rebar_strategy,
            "base_vertical_phi": self.var_base_v_phi,
            "base_vertical_spacing": self.var_base_v_spacing,
            "base_horizontal_phi": self.var_base_h_phi,
            "base_horizontal_spacing": self.var_base_h_spacing,
            "mxy_method": self.var_wa_method,
            "reduce_governing_cases": self.var_reduce,
        }

    def save_config(self):
        path = filedialog.asksaveasfilename(
            title="Guardar configurações",
            defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
        if not path:
            return
        try:
            data = {k: v.get() for k, v in self._config_vars().items()}
            data["auto_stability_options"] = self.auto_stability_options
            with open(path, "w", encoding="utf-8") as f:
                json.dump(data, f, ensure_ascii=False, indent=2)
            self.status_var.set(f"Configurações guardadas: {path}")
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def load_config(self):
        path = filedialog.askopenfilename(
            title="Carregar configurações",
            filetypes=[("JSON", "*.json"), ("Todos", "*.*")],
        )
        if not path:
            return
        try:
            with open(path, "r", encoding="utf-8") as f:
                data = json.load(f)
            opts=data.get("auto_stability_options")
            if opts is not None:
                if not isinstance(opts,(tuple,list)) or len(opts)!=5: raise ValueError("Configuração automática inválida.")
                opts=tuple(float(v) for v in opts)
                if not all(map(math.isfinite,opts)) or min(opts[:2])<0 or not 40<=opts[2]<=100 or opts[3]<.5 or opts[4] not in (1,2): raise ValueError("Configuração automática inválida.")
            self.auto_stability_options=opts
            self._refresh_stability_mode()
            data["reduce_governing_cases"]=False
            vars_map = self._config_vars()
            for k, val in data.items():
                if k in vars_map:
                    vars_map[k].set(val)
            self.status_var.set(f"Configurações carregadas: {path}")
            self._mark_results_stale()
        except Exception as e:
            messagebox.showerror("Erro", str(e))

    def _build_geometry_tab(self):
        bar = ttk.Frame(self.tab_geometry, padding=6)
        bar.pack(fill="x")
        for label, command in (("Exportar geometria", self.export_geometry),
                               ("Limpar nós", self.clear_geometry)):
            ttk.Button(bar, text=label, command=command).pack(side="left", padx=(0, 5))
        ttk.Label(self.tab_geometry, textvariable=self.geometry_text, wraplength=700,
                  justify="left", padding=6).pack(fill="x")
        ttk.Label(self.tab_geometry, text="Dimensões da nuvem de nós [m]; não equivalem a alturas livres ou a l0. Eixos MEF inalterados.",
                  wraplength=700, padding=6).pack(fill="x")
        panes = ttk.Panedwindow(self.tab_geometry, orient="vertical")
        panes.pack(fill="both", expand=True)
        top = ttk.LabelFrame(panes, text="Painéis — selecione uma linha para consultar os nós")
        bottom = ttk.LabelFrame(panes, text="Nós do painel selecionado (pré-visualização até 250)")
        panes.add(top, weight=2); panes.add(bottom, weight=1)
        self.tree_geometry = self._make_tree(top)
        self.tree_geometry_nodes = self._make_tree(bottom)
        self.tree_geometry.bind("<<TreeviewSelect>>", self._show_geometry_nodes)

    def _show_geometry_nodes(self, event=None):
        selected = self.tree_geometry.selection()
        if not selected or self.df_geometry_nodes.empty:
            self.show_df(self.tree_geometry_nodes, pd.DataFrame())
            return
        panel = self.tree_geometry.item(selected[0], "values")[0]
        self.show_df(self.tree_geometry_nodes, self.df_geometry_nodes[self.df_geometry_nodes.Painel.eq(panel)])

    def refresh_geometry(self):
        from wall_geometry import geometry_tables
        self.auto_stability_options = None # never silently reuse confirmations on new inputs
        self._refresh_stability_mode()
        self.df_geometry, self.df_geometry_nodes = pd.DataFrame(), pd.DataFrame()
        if self.geometry_nodes is None:
            text = "Importe as coordenadas dos nós (CSV, TXT ou XLSX)."
        elif self.df_clean.empty:
            text = f"{len(self.geometry_nodes):,} nós importados. Importe os esforços para associar os painéis."
        else:
            self.df_geometry, self.df_geometry_nodes = geometry_tables(self.df_clean, self.geometry_nodes)
            complete = int(self.df_geometry.estado.eq("Plano identificado").sum())
            text = (f"{len(self.geometry_nodes):,} nós na origem | {complete}/{len(self.df_geometry)} painéis com plano identificado | "
                    f"{len(self.df_geometry)-complete} a rever. Confirme que os ficheiros correspondem ao mesmo modelo.")
        if self.geometry_source:
            from pathlib import Path
            text += "\nOrigem: " + str(Path(self.geometry_source))
        self.geometry_text.set(text)
        self.show_df(self.tree_geometry, self.df_geometry, limit=None)
        children = self.tree_geometry.get_children()
        if children:
            self.tree_geometry.selection_set(children[0])
        self._show_geometry_nodes()

    def import_geometry(self):
        from wall_geometry import read_nodes, MissingCoordinateUnits
        self.main_notebook.select(self.tab_geometry)
        src = filedialog.askopenfilename(parent=self, title="Coordenadas dos nós",
                filetypes=[("Tabelas de nós", "*.csv *.txt *.tsv *.xlsx *.xlsm"), ("Todos", "*.*")])
        if not src:
            return
        try:
            try:
                nodes = read_nodes(src)
            except MissingCoordinateUnits:
                from tkinter.simpledialog import askstring
                units = askstring("Unidades das coordenadas", "Unidade das colunas X/Y/Z sem unidade (m, cm ou mm):", parent=self)
                if units is None:
                    return
                nodes = read_nodes(src, units.strip().lower())
            self.geometry_nodes, self.geometry_source = nodes, src
            self.refresh_geometry()
            self.status_var.set("Coordenadas importadas. Consulte o separador Geometria.")
            self._mark_results_stale()
        except Exception as exc:
            messagebox.showerror("Importação da geometria", str(exc), parent=self)

    def clear_geometry(self):
        self.geometry_nodes = self.geometry_source = None
        self.refresh_geometry()
        self.status_var.set("Coordenadas removidas.")
        self._mark_results_stale()

    def export_geometry(self):
        from pathlib import Path
        import os
        from tempfile import NamedTemporaryFile
        if self.df_geometry.empty:
            messagebox.showinfo("Geometria", "Importe os esforços e as coordenadas dos nós primeiro.", parent=self)
            return
        dest = filedialog.asksaveasfilename(parent=self, title="Guardar geometria dos painéis", defaultextension=".xlsx",
                  filetypes=[("Excel (painéis e nós)", "*.xlsx"), ("CSV (resumo)", "*.csv")])
        if not dest:
            return
        target = Path(dest)
        try:
            if target.suffix.lower() not in (".xlsx", ".csv"):
                raise ValueError("Escolha a extensão .xlsx ou .csv.")
            protected = [self.geometry_source, *self.effort_sources]
            if any(p and Path(p).resolve() == target.resolve() for p in protected):
                raise ValueError("Escolha um destino diferente dos ficheiros de entrada.")
            with NamedTemporaryFile(dir=target.resolve().parent, suffix=target.suffix, delete=False) as tmp:
                temp = Path(tmp.name)
            try:
                if target.suffix.lower() == ".xlsx":
                    with pd.ExcelWriter(temp, engine="xlsxwriter", engine_kwargs={"options":{"strings_to_formulas":False,"strings_to_urls":False}}) as writer:
                        self.df_geometry.to_excel(writer, sheet_name="Paineis", index=False)
                        self.df_geometry_nodes.to_excel(writer, sheet_name="Nos", index=False)
                        pd.DataFrame({"Nota":["Dimensões geométricas da nuvem de nós; não definem altura livre, apoios contínuos ou l0.", "Origem: "+str(self.geometry_source)]}).to_excel(writer,sheet_name="Notas",index=False)
                        for ws in writer.sheets.values():
                            ws.freeze_panes(1,0)
                            ws.set_column(0,30,20)
                else:
                    self.df_geometry.to_csv(temp, sep=";", decimal=",", index=False, encoding="utf-8-sig")
                os.replace(temp,target)
            finally:
                temp.unlink(missing_ok=True)
            self.status_var.set(f"Geometria exportada: {len(self.df_geometry)} painéis.")
        except Exception as exc:
            messagebox.showerror("Exportação da geometria", str(exc), parent=self)

    def export_csv(self):
        if self.df_results is None or self.df_results.empty:
            messagebox.showwarning("Aviso", "Não há resultados para exportar.")
            return
        if hasattr(self, '_calculated_signature') and not self._export_current():
            return
        path = filedialog.asksaveasfilename(
            title="Exportar CSV",
            defaultextension=".csv",
            filetypes=[("CSV", "*.csv")],
        )
        if not path:
            return
        try:
            self.df_results.to_csv(path, index=False, sep=";")
            self.status_var.set(f"Exportado: {path}")
        except Exception as e:
            messagebox.showerror("Erro", str(e))


if __name__ == "__main__":
    import multiprocessing
    import sys
    multiprocessing.freeze_support()
    if len(sys.argv)==3 and sys.argv[1]=="--smoke-test":
        from wall_smoke_test import run
        run(sys.argv[2])
    else:
        app = WallsEC2App()
        app.mainloop()

"""Cálculo por painel a partir de CSV e perfil JSON; usa o motor da interface."""
import argparse
from wall_geometry import read_nodes, panel_geometry, node_id, confirmed_restraint_spacing
import json
import math
from pathlib import Path
from datetime import datetime
from tempfile import TemporaryDirectory
import pandas as pd
from wall_shell_screen import envelope as shell_screen_envelope
from wall_shell_capacity import envelope as shell_capacity_envelope
from WallsEC2 import (WallDesigner, WallsEC2App, read_csv_robust, clean_dataframe,
                      ec2_final_creep, parse_strength_from_class, APP_VERSION)


def derive(params, concrete):
    names = {"altura_mm", "k", "rh", "h0_mm", "idade_ajustada_dias", "razao_momentos"}
    if set(params) - names:
        raise ValueError("Parâmetro de estabilidade desconhecido: " + str(set(params)-names))
    vals = {k: float(v) for k, v in params.items() if v is not None}
    if not all(math.isfinite(v) for v in vals.values()):
        raise ValueError("Parâmetros não finitos")
    if any(vals[k] <= 0 for k in ("altura_mm","k","h0_mm") if k in vals):
        raise ValueError("Geometria não positiva")
    if ("rh" in vals and not 40 <= vals["rh"] <= 100 or
        vals.get("idade_ajustada_dias",1) < .5 or vals.get("razao_momentos",0) < 0):
        raise ValueError("RH, idade ajustada ou razão fora do domínio do lote")
    length = vals["altura_mm"]*vals["k"] if {"altura_mm","k"} <= vals.keys() else None
    phi = None
    if {"rh","h0_mm","idade_ajustada_dias","razao_momentos"} <= vals.keys():
        phi = ec2_final_creep(parse_strength_from_class(concrete), vals["rh"], vals["h0_mm"],
                              vals["idade_ajustada_dias"])*vals["razao_momentos"]
    return length, phi, sorted(names-vals.keys())


def run(source, profile, target, nodes_path=None):
    cfg = json.loads(Path(profile).read_text(encoding="utf-8-sig"))
    default = cfg["estabilidade_comum"]
    overrides = cfg["estabilidade_por_painel"]
    df = clean_dataframe(read_csv_robust(str(source)))
    if set(overrides) - set(df.panel.astype(str)):
        raise ValueError("O perfil contém painéis inexistentes no CSV")
    nodes = read_nodes(nodes_path) if nodes_path else None
    confirmed = set(map(str,cfg.get("paineis_altura_livre_confirmada", [])))
    if confirmed and (nodes is None or confirmed - set(df.panel.astype(str))):
        raise ValueError("A altura automática exige nós e painéis correspondentes.")
    restraints = cfg.get("travamentos_por_painel", {})
    if set(restraints) - set(df.panel.astype(str)) or set(restraints) & confirmed or (restraints and nodes is None):
        raise ValueError("Travamentos: painel inexistente, nós em falta ou altura automática concorrente")
    common_confirmed = set(map(str,cfg.get("paineis_l0_comum_confirmado", [])))
    if common_confirmed - set(restraints):
        raise ValueError("Confirmação de l0 comum exige travamentos definidos no painel")
    geometry = []
    target = Path(target)
    target.mkdir(parents=True,exist_ok=True)
    summaries, envelopes, inputs, shell, shell_details, capacities = [], [], [], [], [], []
    with TemporaryDirectory(dir=target) as tmp:
        temp = Path(tmp)
        for panel, group in df.groupby("panel",sort=False):
            args = dict(cfg["calculo"])
            if {"effective_length_mm","creep_effective"} & args.keys():
                raise ValueError("Use apenas os campos de estabilidade do perfil")
            params = {**default, **overrides.get(str(panel),{})}
            geo = None
            if nodes is not None:
                geo = panel_geometry(group.node, nodes)
                if str(panel) in confirmed:
                    if geo["estado"] != "Plano identificado" or params.get("altura_mm") is not None:
                        raise ValueError(f"Painel {panel}: altura geométrica indisponível ou altura manual também definida.")
                    params["altura_mm"] = 1000*geo["altura_no_plano_m"]
            spacing = None
            if str(panel) in restraints:
                if params.get("altura_mm") is not None:
                    raise ValueError(f"Painel {panel}: altura manual e travamentos concorrentes")
                spacing = confirmed_restraint_spacing(group.node, nodes, restraints[str(panel)])
                params["altura_mm"] = spacing["altura_mm"]
            length, phi, missing = derive(params,args["concrete_class"])
            if spacing and str(panel) not in common_confirmed:
                missing.append("l0_comum_XY_por_confirmar")
            ready = not missing
            d = WallDesigner(**args,effective_length_mm=length if ready else 0.,
                             creep_effective=phi if phi is not None else 0.)
            d.sandwich_design=True
            r = d.design_dataframe(group)
            summary = WallsEC2App.build_panel_summary(None,r)
            if geo is not None:
                gov = summary.iloc[0]["node_governante"]
                loc = nodes.get(node_id(gov)) if str(gov).strip() else None
                geometry.append(dict(Painel=panel, **geo, no_governante=gov,
                                     **{f"{a}_gov_m": loc[i] if loc else None for i,a in enumerate("XYZ")},
                                     altura_livre_confirmada=str(panel) in confirmed))
            if missing:
                summary["Dados de estabilidade em falta"] = ", ".join(missing)
            summaries.append(summary)
            envelopes.append(WallsEC2App.build_nm_envelope(r))
            shell.append(summary[[c for c in summary if c=="Panel" or c.startswith("Sand_")]])
            capacities.append(pd.DataFrame())
            shell_details.append(r.loc[r.Combo_type.eq("ELU"), ["Panel","Node","Case"] + [c for c in r if c.startswith("Sand_")]])
            inputs.append(dict(Painel=panel, **params, l0_calculado_mm=length, phi_ef_calculada=phi,
                               l0_aplicado_mm=d.effective_length_mm, phi_aplicada=d.creep_effective,
                               dados_em_falta=", ".join(missing), versao=APP_VERSION,
                               origem_altura="Travamentos confirmados" if spacing else "Geometria confirmada" if str(panel) in confirmed else "Manual / não definida",
                               distancias_travamentos_mm=json.dumps(spacing["distancias_mm"]) if spacing else ""))
            print(f"Painel {panel}: {len(r)} linhas", flush=True)
        for name,table in (("Resumo",pd.concat(summaries)),("Envolvente_NM",pd.concat(envelopes)),
                           ("Parametros",pd.DataFrame(inputs)),("Sandwich_Resumo",pd.concat(shell)),
                           ("Sandwich_Detalhe",pd.concat(shell_details))):
            table.to_csv(temp/(name+".csv"),sep=";",decimal=",",encoding="utf-8-sig",index=False)
        if geometry:
            pd.DataFrame(geometry).to_csv(temp/"Geometria.csv", sep=";", decimal=",", index=False, encoding="utf-8-sig")
        (temp/"perfil.json").write_text(json.dumps(cfg,ensure_ascii=False,indent=2),encoding="utf-8")
        dest = target/datetime.now().strftime("WallsEC2_%Y%m%d_%H%M%S_%f")
        temp.rename(dest)
    print(dest)
    return dest


if __name__ == "__main__":
    p = argparse.ArgumentParser(description=__doc__)
    for arg in ("source","profile","target"):
        p.add_argument(arg)
    p.add_argument("--nos")
    ns = p.parse_args()
    run(ns.source, ns.profile, ns.target, ns.nos)

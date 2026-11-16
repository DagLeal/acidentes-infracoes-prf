"""Análise exploratória e inferencial dos dados processados.

Responde às três perguntas de pesquisa do artigo:

* **RQ1 (quando)** — como acidentes e letalidade variam no tempo e se a noite é mais letal;
* **RQ2 (por quê / com quem)** — causas (principal × todas), tipos e perfis associados à gravidade;
* **RQ3 (onde / fiscalização)** — se a fiscalização (infrações) acompanha a geografia dos acidentes.

Tudo é calculado a partir de ``data/processed`` (nada é fixo no código): ao adicionar
CSVs de outros anos em ``data/raw`` e rodar o pipeline, todos os números, gráficos e
textos do artigo são recalculados.
"""
from __future__ import annotations

import datetime as dt
import json
import math
from pathlib import Path

import numpy as np
import pandas as pd
from scipy import stats

from . import etl

DIAS = ["segunda-feira", "terça-feira", "quarta-feira", "quinta-feira", "sexta-feira", "sábado", "domingo"]
DIAS_ABREV = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]
FASES = ["Amanhecer", "Pleno dia", "Anoitecer", "Plena Noite"]
MESES = ["janeiro", "fevereiro", "março", "abril", "maio", "junho", "julho",
         "agosto", "setembro", "outubro", "novembro", "dezembro"]
FAIXAS_IDADE = [(0, 9), (10, 19), (20, 29), (30, 39), (40, 49), (50, 59), (60, 69), (70, 79), (80, 200)]

# --------------------------------------------------------------------------
# Estatística auxiliar
# --------------------------------------------------------------------------


def wilson(k: float, n: float, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    den = 1 + z**2 / n
    centre = (p + z**2 / (2 * n)) / den
    half = z * math.sqrt(p * (1 - p) / n + z**2 / (4 * n**2)) / den
    return (centre - half, centre + half)


def odds_ratio(a: float, b: float, c: float, d: float) -> dict:
    """OR de [[a, b], [c, d]] com IC95% (Woolf) e qui-quadrado."""
    a, b, c, d = (x + 0.5 if min(a, b, c, d) == 0 else x for x in (a, b, c, d))
    orr = (a * d) / (b * c)
    se = math.sqrt(1 / a + 1 / b + 1 / c + 1 / d)
    chi2, p, _, _ = stats.chi2_contingency(np.array([[a, b], [c, d]]), correction=False)
    return {"or": orr, "lo": math.exp(math.log(orr) - 1.96 * se), "hi": math.exp(math.log(orr) + 1.96 * se),
            "chi2": float(chi2), "p": float(p)}


def mantel_haenszel(tables: list[tuple[float, float, float, float]]) -> dict | None:
    """OR de Mantel-Haenszel com IC95% (Robins–Breslow–Greenland)."""
    R = S = PR = PSQR = QS = 0.0
    for a, b, c, d in tables:
        n = a + b + c + d
        if n == 0:
            continue
        r, s_ = a * d / n, b * c / n
        p_, q_ = (a + d) / n, (b + c) / n
        R += r
        S += s_
        PR += p_ * r
        PSQR += p_ * s_ + q_ * r
        QS += q_ * s_
    if R == 0 or S == 0:
        return None
    orr = R / S
    var = PR / (2 * R**2) + PSQR / (2 * R * S) + QS / (2 * S**2)
    se = math.sqrt(var)
    return {"or": orr, "lo": math.exp(math.log(orr) - 1.96 * se), "hi": math.exp(math.log(orr) + 1.96 * se)}


def spearman(x, y) -> dict:
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = np.isfinite(x) & np.isfinite(y)
    if ok.sum() < 4:
        return {"rho": None, "p": None, "n": int(ok.sum())}
    rho, p = stats.spearmanr(x[ok], y[ok])
    return {"rho": float(rho), "p": float(p), "n": int(ok.sum())}


def loglog_fit(x, y) -> dict | None:
    x, y = np.asarray(x, float), np.asarray(y, float)
    ok = (x > 0) & (y > 0)
    if ok.sum() < 4:
        return None
    res = stats.linregress(np.log10(x[ok]), np.log10(y[ok]))
    return {"slope": float(res.slope), "intercept": float(res.intercept), "r2": float(res.rvalue**2), "p": float(res.pvalue)}


def pct(a, b, nd=1):
    return round(100 * a / b, nd) if b else None


def month_label(ano_mes: str) -> str:
    y, m = ano_mes.split("-")
    return f"{MESES[int(m) - 1]} de {y}"


def periodo_label(meses: list[str]) -> str:
    if not meses:
        return "—"
    a, b = meses[0], meses[-1]
    if a == b:
        return month_label(a)
    ya, ma = a.split("-")
    yb, mb = b.split("-")
    if ya == yb:
        return f"{MESES[int(ma) - 1]} a {MESES[int(mb) - 1]} de {ya}"
    return f"{MESES[int(ma) - 1]} de {ya} a {MESES[int(mb) - 1]} de {yb}"


def to_jsonable(o):
    if isinstance(o, dict):
        return {str(k): to_jsonable(v) for k, v in o.items()}
    if isinstance(o, (list, tuple)):
        return [to_jsonable(v) for v in o]
    if isinstance(o, (np.integer,)):
        return int(o)
    if isinstance(o, (np.floating, float)):
        f = float(o)
        return None if (math.isnan(f) or math.isinf(f)) else round(f, 4)
    if isinstance(o, (np.bool_,)):
        return bool(o)
    if o is pd.NA or o is None:
        return None
    if isinstance(o, (pd.Timestamp, dt.date)):
        return str(o)[:10]
    return o


# --------------------------------------------------------------------------
# Agregação em blocos das infrações (aditiva → escala para vários anos)
# --------------------------------------------------------------------------

INF_COLS = ["ano_mes", "data", "hora", "uf", "br", "km", "grupo_veiculo", "descricao_infracao", "enquadramento",
            "grupo_infracao", "excesso_velocidade", "abordagem", "pais_veiculo", "veiculo_estrangeiro",
            "excesso_verificado", "limite_via_kmh"]


def _agg(part: pd.DataFrame, keys: list[str], **named) -> pd.DataFrame:
    return part.groupby(keys, observed=True, dropna=True).agg(**named).reset_index()


def aggregate_infracoes(processed: Path = etl.PROCESSED_DIR) -> dict[str, pd.DataFrame] | None:
    """Lê as partições mensais UMA A UMA e acumula tabelas agregadas (somáveis)."""
    acc: dict[str, list[pd.DataFrame]] = {}
    for part in etl.iter_table("infracoes", INF_COLS, processed):
        part = part.copy()
        part["vel"] = part["excesso_velocidade"].fillna(0).astype(int)
        part["sem_abord"] = (part["abordagem"] == 0).fillna(False).astype(int)
        part["com_abord"] = (part["abordagem"] == 1).fillna(False).astype(int)
        part["n"] = 1
        part["bloco_km"] = (part["km"] // 10 * 10)
        part["exc_int"] = np.where(part["vel"] == 1, part["excesso_verificado"].round(), np.nan)
        part["lim_int"] = np.where(part["vel"] == 1, part["limite_via_kmh"].round(), np.nan)
        part["estrangeiro"] = (part["veiculo_estrangeiro"] == 1).fillna(False).astype(int)
        for c in ("uf", "grupo_veiculo", "descricao_infracao", "enquadramento", "grupo_infracao", "pais_veiculo", "ano_mes"):
            part[c] = part[c].astype("object")
        sums = dict(n=("n", "sum"), vel=("vel", "sum"), sem_abord=("sem_abord", "sum"), com_abord=("com_abord", "sum"))
        acc.setdefault("total", []).append(_agg(part, ["ano_mes"], **sums))
        acc.setdefault("uf", []).append(_agg(part, ["ano_mes", "uf"], **sums))
        acc.setdefault("br", []).append(_agg(part, ["ano_mes", "uf", "br"], **sums))
        acc.setdefault("hora", []).append(_agg(part, ["ano_mes", "hora"], **sums))
        acc.setdefault("grupo", []).append(_agg(part, ["ano_mes", "grupo_infracao"], **sums))
        acc.setdefault("uf_grupo", []).append(_agg(part, ["ano_mes", "uf", "grupo_infracao"], n=("n", "sum")))
        acc.setdefault("desc", []).append(_agg(part, ["ano_mes", "descricao_infracao", "enquadramento", "grupo_infracao"], n=("n", "sum")))
        acc.setdefault("veic", []).append(_agg(part, ["ano_mes", "grupo_veiculo"], **sums))
        acc.setdefault("trecho", []).append(_agg(part, ["ano_mes", "br", "bloco_km"], n=("n", "sum"), vel=("vel", "sum")))
        acc.setdefault("dia", []).append(_agg(part, ["data"], n=("n", "sum"), vel=("vel", "sum")))
        acc.setdefault("exc", []).append(_agg(part, ["ano_mes", "exc_int"], n=("n", "sum")))
        acc.setdefault("lim", []).append(_agg(part, ["ano_mes", "lim_int"], n=("n", "sum")))
        acc.setdefault("pais", []).append(_agg(part[part["estrangeiro"] == 1], ["ano_mes", "pais_veiculo"], n=("n", "sum")))
        acc.setdefault("nulos", []).append(pd.DataFrame({
            "ano_mes": part["ano_mes"].dropna().unique(),
        }).assign(sem_br=int(part["br"].isna().sum()), sem_hora=int(part["hora"].isna().sum())))
    if not acc:
        return None
    out = {}
    for k, frames in acc.items():
        df = pd.concat(frames, ignore_index=True)
        keys = [c for c in df.columns if c not in ("n", "vel", "sem_abord", "com_abord", "sem_br", "sem_hora")]
        vals = [c for c in df.columns if c not in keys]
        out[k] = df.groupby(keys, dropna=True, observed=True)[vals].sum().reset_index() if keys else df
    return out


# --------------------------------------------------------------------------
# RQ1 — Quando?
# --------------------------------------------------------------------------


def rq1(oc: pd.DataFrame) -> dict:
    out: dict = {}
    g = (oc.groupby("ano_mes", observed=True)
         .agg(acidentes=("id", "size"), fatais=("fatal", "sum"), mortos=("mortos", "sum"),
              feridos=("feridos", "sum"), graves=("feridos_graves", "sum"), ultimo_dia=("data", "max"))
         .reset_index())
    g = g[g["acidentes"] > 0]
    mensal = []
    for _, r in g.iterrows():
        y, m = r["ano_mes"].split("-")
        fim = (pd.Timestamp(int(y), int(m), 1) + pd.offsets.MonthEnd(0)).date()
        mensal.append({
            "ano_mes": r["ano_mes"], "ano": int(y), "mes": int(m),
            "acidentes": int(r["acidentes"]), "fatais": int(r["fatais"]), "mortos": int(r["mortos"]),
            "feridos": int(r["feridos"]), "graves": int(r["graves"]),
            "letalidade": round(100 * r["mortos"] / r["acidentes"], 2),
            "pct_fatais": round(100 * r["fatais"] / r["acidentes"], 2),
            "parcial": bool(pd.Timestamp(r["ultimo_dia"]).date() < fim),
        })
    out["mensal"] = mensal

    # mapa de calor dia da semana × hora
    h = (oc.dropna(subset=["hora"]).groupby(["dia_semana", "hora"], observed=True)
         .agg(n=("id", "size"), f=("fatal", "sum"), m=("mortos", "sum")).reset_index())
    cells = {(d, int(hh)): (int(n), int(f), int(m)) for d, hh, n, f, m in h[["dia_semana", "hora", "n", "f", "m"]].itertuples(index=False)}
    heat = []
    for di, d in enumerate(DIAS):
        for hh in range(24):
            n, f, m = cells.get((d, hh), (0, 0, 0))
            heat.append({"d": di, "h": hh, "n": n, "f": f, "m": m})
    out["heat"] = heat
    out["dias"] = DIAS_ABREV

    por_hora = (oc.dropna(subset=["hora"]).groupby("hora", observed=True)
                .agg(n=("id", "size"), f=("fatal", "sum"), m=("mortos", "sum")).reset_index())
    ph = []
    for _, r in por_hora.iterrows():
        lo, hi = wilson(r["f"], r["n"])
        ph.append({"h": int(r["hora"]), "n": int(r["n"]), "f": int(r["f"]), "m": int(r["m"]),
                   "pct_fatais": round(100 * r["f"] / r["n"], 2), "lo": round(100 * lo, 2), "hi": round(100 * hi, 2)})
    out["por_hora"] = ph
    elig = [p for p in ph if p["n"] >= 200]
    out["hora_mais_letal"] = max(elig, key=lambda p: p["pct_fatais"]) if elig else None
    out["hora_mais_acidentes"] = max(ph, key=lambda p: p["n"]) if ph else None

    # fase do dia
    fase = (oc.groupby("fase_dia", observed=True)
            .agg(n=("id", "size"), f=("fatal", "sum"), m=("mortos", "sum")).reindex(FASES).dropna().reset_index())
    fl = []
    for _, r in fase.iterrows():
        lo, hi = wilson(r["f"], r["n"])
        fl.append({"fase": r["fase_dia"], "n": int(r["n"]), "f": int(r["f"]), "m": int(r["m"]),
                   "pct_fatais": round(100 * r["f"] / r["n"], 2), "lo": round(100 * lo, 2), "hi": round(100 * hi, 2),
                   "letalidade": round(100 * r["m"] / r["n"], 2)})
    out["fase"] = fl

    sub = oc[oc["fase_dia"].isin(["Plena Noite", "Pleno dia"])]
    a = int(((sub["fase_dia"] == "Plena Noite") & (sub["fatal"] == 1)).sum())
    b = int(((sub["fase_dia"] == "Plena Noite") & (sub["fatal"] == 0)).sum())
    c = int(((sub["fase_dia"] == "Pleno dia") & (sub["fatal"] == 1)).sum())
    d = int(((sub["fase_dia"] == "Pleno dia") & (sub["fatal"] == 0)).sum())
    out["noite_vs_dia"] = {"noite_fatais": a, "noite_nao": b, "dia_fatais": c, "dia_nao": d, **odds_ratio(a, b, c, d)}
    strata = []
    for _, s in sub.dropna(subset=["tipo_pista", "area_urbana"]).groupby(["tipo_pista", "area_urbana"], observed=True):
        strata.append((float(((s["fase_dia"] == "Plena Noite") & (s["fatal"] == 1)).sum()),
                       float(((s["fase_dia"] == "Plena Noite") & (s["fatal"] == 0)).sum()),
                       float(((s["fase_dia"] == "Pleno dia") & (s["fatal"] == 1)).sum()),
                       float(((s["fase_dia"] == "Pleno dia") & (s["fatal"] == 0)).sum())))
    out["noite_vs_dia"]["ajustado_mh"] = mantel_haenszel(strata)
    out["noite_vs_dia"]["estratos"] = "tipo de pista × área urbana/rural"

    # fim de semana × dias úteis
    fds = oc["dia_semana"].isin(["sábado", "domingo"])
    a, b = int(((fds) & (oc["fatal"] == 1)).sum()), int(((fds) & (oc["fatal"] == 0)).sum())
    c, d = int(((~fds) & (oc["fatal"] == 1)).sum()), int(((~fds) & (oc["fatal"] == 0)).sum())
    out["fds_vs_util"] = {"fds_n": a + b, "util_n": c + d, "fds_pct_fatais": pct(a, a + b, 2), "util_pct_fatais": pct(c, c + d, 2),
                          "media_diaria_fds": None, "media_diaria_util": None, **odds_ratio(a, b, c, d)}
    dias = oc.groupby("data").size()
    wk = dias.index.dayofweek
    out["fds_vs_util"]["media_diaria_fds"] = round(float(dias[wk >= 5].mean()), 1) if (wk >= 5).any() else None
    out["fds_vs_util"]["media_diaria_util"] = round(float(dias[wk < 5].mean()), 1) if (wk < 5).any() else None

    # dia da semana
    dsem = (oc.groupby("dia_semana", observed=True).agg(n=("id", "size"), f=("fatal", "sum"), m=("mortos", "sum"))
            .reindex(DIAS).reset_index())
    out["dia_semana"] = [{"dia": r["dia_semana"], "n": int(r["n"]), "pct_fatais": pct(r["f"], r["n"], 2), "m": int(r["m"])}
                         for _, r in dsem.iterrows()]

    # comparação entre anos (só se houver mais de um ano)
    anos = sorted({m["ano"] for m in mensal})
    out["anos"] = anos
    return out


# --------------------------------------------------------------------------
# RQ2 — Causas, tipos e perfis
# --------------------------------------------------------------------------


def _min_n(total: int) -> int:
    return max(50, int(round(0.001 * total)))


def rq2(oc: pd.DataFrame, pe: pd.DataFrame, ca: pd.DataFrame, ti: pd.DataFrame) -> dict:
    out: dict = {}
    total = len(oc)
    out["min_n"] = _min_n(total)
    fat = oc.set_index("id")["fatal"]
    mor = oc.set_index("id")["mortos"]

    # --- causas: principal (datatran) × citada em qualquer posição (todas as causas)
    pri = (oc.groupby("causa_acidente", observed=True)
           .agg(n_principal=("id", "size"), fatais_principal=("fatal", "sum"), mortos_principal=("mortos", "sum")))
    if len(ca):
        cit = ca.drop_duplicates(["id", "causa_acidente"]).copy()
        cit["fatal"] = cit["id"].map(fat)
        cit["mortos"] = cit["id"].map(mor)
        cit = cit.dropna(subset=["fatal"])
        citg = (cit.groupby("causa_acidente", observed=True)
                .agg(n_citada=("id", "nunique"), fatais_citada=("fatal", "sum"), mortos_citada=("mortos", "sum")))
        tab = pri.join(citg, how="outer").fillna(0)
    else:
        tab = pri.assign(n_citada=0, fatais_citada=0, mortos_citada=0)
    tab = tab.reset_index().rename(columns={"index": "causa"})
    tab["pct_fatais_principal"] = np.where(tab["n_principal"] > 0, 100 * tab["fatais_principal"] / tab["n_principal"].replace(0, np.nan), np.nan)
    tab["pct_fatais_citada"] = np.where(tab["n_citada"] > 0, 100 * tab["fatais_citada"] / tab["n_citada"].replace(0, np.nan), np.nan)
    tab["letalidade_principal"] = np.where(tab["n_principal"] > 0, 100 * tab["mortos_principal"] / tab["n_principal"].replace(0, np.nan), np.nan)
    tab["pct_como_principal"] = np.where(tab["n_citada"] > 0, 100 * tab["n_principal"] / tab["n_citada"].replace(0, np.nan), np.nan)
    tab = tab.sort_values("n_citada", ascending=False)
    out["causas_tabela_completa"] = tab  # DataFrame (exportada em CSV; removida do JSON)
    top = tab.head(16)
    out["causas"] = [{
        "causa": r["causa_acidente"], "n_principal": int(r["n_principal"]), "n_citada": int(r["n_citada"]),
        "pct_fatais_principal": None if pd.isna(r["pct_fatais_principal"]) else round(r["pct_fatais_principal"], 2),
        "pct_fatais_citada": None if pd.isna(r["pct_fatais_citada"]) else round(r["pct_fatais_citada"], 2),
        "pct_como_principal": None if pd.isna(r["pct_como_principal"]) else round(r["pct_como_principal"], 1),
    } for _, r in top.iterrows()]
    letal = tab[tab["n_principal"] >= out["min_n"]].sort_values("pct_fatais_principal", ascending=False).head(12)
    out["causas_letais"] = [{"causa": r["causa_acidente"], "n": int(r["n_principal"]), "pct_fatais": round(r["pct_fatais_principal"], 2),
                             "letalidade": round(r["letalidade_principal"], 2)} for _, r in letal.iterrows()]

    # --- número de causas por acidente
    if len(ca):
        k = ca.drop_duplicates(["id", "causa_acidente"]).groupby("id").size().rename("k")
        j = pd.concat([k, fat], axis=1, join="inner")
        j["faixa"] = np.where(j["k"] >= 4, "4+", j["k"].astype(str))
        kk = j.groupby("faixa").agg(n=("fatal", "size"), f=("fatal", "sum")).reindex(["1", "2", "3", "4+"]).dropna()
        out["multi_causa"] = {
            "media": round(float(j["k"].mean()), 2), "pct_mais_de_uma": pct(int((j["k"] > 1).sum()), len(j)),
            "n_acidentes": int(len(j)),
            "faixas": [{"k": i, "n": int(r["n"]), "pct_fatais": pct(r["f"], r["n"], 2)} for i, r in kk.iterrows()],
        }
        if len(kk) >= 2:
            one = j[j["k"] == 1]
            many = j[j["k"] > 1]
            out["multi_causa"]["or_mais_de_uma"] = odds_ratio(
                int(many["fatal"].sum()), int((many["fatal"] == 0).sum()),
                int(one["fatal"].sum()), int((one["fatal"] == 0).sum()))
        # pares causa principal → causa concorrente
        p = ca[ca["causa_principal"] == 1][["id", "causa_acidente"]].rename(columns={"causa_acidente": "principal"})
        s = ca[ca["causa_principal"] == 0][["id", "causa_acidente"]].rename(columns={"causa_acidente": "concorrente"})
        pares = (s.merge(p, on="id").groupby(["principal", "concorrente"], observed=True).size()
                 .sort_values(ascending=False).head(10).reset_index(name="n"))
        out["pares_causas"] = [{"principal": r["principal"], "concorrente": r["concorrente"], "n": int(r["n"])} for _, r in pares.iterrows()]
    else:
        out["multi_causa"], out["pares_causas"] = None, []

    # --- tipos de acidente
    tp = (oc.groupby("tipo_acidente", observed=True)
          .agg(n=("id", "size"), f=("fatal", "sum"), m=("mortos", "sum")).reset_index().sort_values("n", ascending=False))
    out["tipos"] = [{"tipo": r["tipo_acidente"], "n": int(r["n"]), "f": int(r["f"]), "m": int(r["m"]),
                     "pct_fatais": pct(r["f"], r["n"], 2), "letalidade": pct(r["m"], r["n"], 2)} for _, r in tp.iterrows()]
    if len(ti):
        nt = ti.drop_duplicates(["id", "tipo_acidente"]).groupby("id").size().rename("k")
        j = pd.concat([nt, fat], axis=1, join="inner")
        multi = j[j["k"] > 1]
        single = j[j["k"] == 1]
        out["multi_tipo"] = {
            "pct_encadeados": pct(len(multi), len(j)), "n_acidentes": int(len(j)),
            "pct_fatais_encadeados": pct(multi["fatal"].sum(), len(multi), 2),
            "pct_fatais_simples": pct(single["fatal"].sum(), len(single), 2),
            "or": odds_ratio(int(multi["fatal"].sum()), int((multi["fatal"] == 0).sum()),
                             int(single["fatal"].sum()), int((single["fatal"] == 0).sum())) if len(multi) and len(single) else None,
        }
        o1 = ti[ti["ordem_tipo_acidente"] == 1].drop_duplicates("id")[["id", "tipo_acidente"]].rename(columns={"tipo_acidente": "primeiro"})
        o2 = ti[ti["ordem_tipo_acidente"] == 2].drop_duplicates("id")[["id", "tipo_acidente"]].rename(columns={"tipo_acidente": "segundo"})
        seq = (o1.merge(o2, on="id").groupby(["primeiro", "segundo"], observed=True).size()
               .sort_values(ascending=False).head(8).reset_index(name="n"))
        out["sequencias_tipos"] = [{"primeiro": r["primeiro"], "segundo": r["segundo"], "n": int(r["n"])} for _, r in seq.iterrows()]
    else:
        out["multi_tipo"], out["sequencias_tipos"] = None, []

    # --- perfis de envolvidos (pessoa × veículo)
    pp = pe[(pe["pessoa_presente"] == 1)].copy()
    pp["perfil"] = np.where(pp["tipo_envolvido"] == "Pedestre", "Pedestres", pp["grupo_veiculo"].astype("object"))
    pp = pp[pp["tipo_envolvido"].isin(["Condutor", "Passageiro", "Pedestre", "Cavaleiro"])]
    pp["perfil"] = pp["perfil"].fillna("Outros")
    inf_ = pp[pp["estado_fisico"].isin(["Ileso", "Lesões Leves", "Lesões Graves", "Óbito"])]
    perf = (inf_.groupby("perfil").agg(n=("id", "size"),
                                       obitos=("estado_fisico", lambda s: int((s == "Óbito").sum())),
                                       graves=("estado_fisico", lambda s: int((s == "Lesões Graves").sum())))
            .reset_index())
    tot_n, tot_ob = perf["n"].sum(), perf["obitos"].sum()
    rows = []
    for _, r in perf.sort_values("n", ascending=False).iterrows():
        lo, hi = wilson(r["obitos"], r["n"])
        rows.append({"perfil": r["perfil"], "n": int(r["n"]), "obitos": int(r["obitos"]), "graves": int(r["graves"]),
                     "pct_obito": round(100 * r["obitos"] / r["n"], 2), "lo": round(100 * lo, 2), "hi": round(100 * hi, 2),
                     "pct_obito_grave": round(100 * (r["obitos"] + r["graves"]) / r["n"], 2),
                     "share_envolvidos": round(100 * r["n"] / tot_n, 1), "share_obitos": round(100 * r["obitos"] / tot_ob, 1) if tot_ob else None})
    out["perfis"] = rows
    out["perfis_total"] = {"n": int(tot_n), "obitos": int(tot_ob)}
    moto = next((r for r in rows if r["perfil"] == "Motocicletas"), None)
    auto = next((r for r in rows if r["perfil"] == "Automóvel e utilitários"), None)
    if moto and auto:
        out["moto_vs_auto"] = odds_ratio(moto["obitos"], moto["n"] - moto["obitos"], auto["obitos"], auto["n"] - auto["obitos"])

    envol = (inf_.groupby("tipo_envolvido").agg(n=("id", "size"), o=("estado_fisico", lambda s: int((s == "Óbito").sum()))).reset_index())
    out["tipo_envolvido"] = [{"tipo": r["tipo_envolvido"], "n": int(r["n"]), "obitos": int(r["o"]), "pct_obito": pct(r["o"], r["n"], 2)} for _, r in envol.iterrows()]

    # sexo × faixa etária (óbitos)
    ob = pp[(pp["estado_fisico"] == "Óbito") & pp["sexo"].isin(["Masculino", "Feminino"]) & pp["idade"].notna()].copy()
    idade = ob["idade"].astype(int)
    faixas = []
    for lo_, hi_ in FAIXAS_IDADE:
        lab = f"{lo_}+" if hi_ >= 200 else f"{lo_}–{hi_}"
        sel = (idade >= lo_) & (idade <= hi_)
        faixas.append({"faixa": lab, "M": int((sel & (ob["sexo"] == "Masculino")).sum()), "F": int((sel & (ob["sexo"] == "Feminino")).sum())})
    out["piramide"] = faixas
    sx = inf_[inf_["sexo"].isin(["Masculino", "Feminino"])]
    out["sexo"] = {
        "pct_homens_envolvidos": pct(int((sx["sexo"] == "Masculino").sum()), len(sx)),
        "pct_homens_obitos": pct(int((ob["sexo"] == "Masculino").sum()), len(ob)),
        "n_obitos_com_sexo_idade": int(len(ob)),
        "mediana_idade_obitos": float(idade.median()) if len(ob) else None,
    }

    # idade do veículo × letalidade do condutor (tabela auxiliar)
    cd = inf_[(inf_["tipo_envolvido"] == "Condutor") & inf_["idade_veiculo"].notna()].copy()
    if len(cd):
        cd["faixa_veic"] = pd.cut(cd["idade_veiculo"].astype(int), [-1, 5, 10, 15, 200], labels=["0–5", "6–10", "11–15", "16+"])
        out["idade_veiculo_tabela"] = (cd.groupby(["perfil", "faixa_veic"], observed=True)
                                       .agg(n=("id", "size"), obitos=("estado_fisico", lambda s: int((s == "Óbito").sum()))).reset_index()
                                       .assign(pct_obito=lambda d: 100 * d["obitos"] / d["n"]))
    return out


# --------------------------------------------------------------------------
# RQ3 — Fiscalização × acidentes
# --------------------------------------------------------------------------


def rq3(oc: pd.DataFrame, pe: pd.DataFrame, inf: dict | None) -> tuple[dict | None, dict]:
    extra: dict = {}
    if inf is None or inf["total"].empty:
        return None, extra
    out: dict = {}
    meses_inf = sorted(inf["total"]["ano_mes"].unique())
    meses_oc = sorted(oc["ano_mes"].dropna().astype(str).unique())
    overlap = sorted(set(meses_inf) & set(meses_oc))
    out["meses_infracoes"] = meses_inf
    out["meses_acidentes"] = meses_oc
    out["meses_comuns"] = overlap
    out["periodo_infracoes"] = periodo_label(meses_inf)
    out["periodo_comum"] = periodo_label(overlap)

    tot = inf["total"]
    out["totais"] = {
        "infracoes": int(tot["n"].sum()), "velocidade": int(tot["vel"].sum()),
        "pct_velocidade": pct(tot["vel"].sum(), tot["n"].sum()),
        "pct_sem_abordagem": pct(tot["sem_abord"].sum(), tot["sem_abord"].sum() + tot["com_abord"].sum()),
        "por_mes": [{"ano_mes": r["ano_mes"], "n": int(r["n"]), "vel": int(r["vel"])} for _, r in tot.sort_values("ano_mes").iterrows()],
    }
    grupo = inf["grupo"].groupby("grupo_infracao")[["n", "vel", "sem_abord", "com_abord"]].sum().sort_values("n", ascending=False).reset_index()
    out["grupos"] = [{"grupo": r["grupo_infracao"], "n": int(r["n"]), "pct": pct(r["n"], grupo["n"].sum(), 2),
                      "pct_sem_abordagem": pct(r["sem_abord"], r["sem_abord"] + r["com_abord"])} for _, r in grupo.iterrows()]
    desc = inf["desc"].groupby(["descricao_infracao", "enquadramento", "grupo_infracao"])["n"].sum().sort_values(ascending=False).head(10).reset_index()
    out["top_infracoes"] = [{"descricao": r["descricao_infracao"], "enquadramento": r["enquadramento"], "grupo": r["grupo_infracao"],
                             "n": int(r["n"]), "pct": pct(r["n"], tot["n"].sum(), 2)} for _, r in desc.iterrows()]
    exc = inf["exc"].groupby("exc_int")["n"].sum().sort_index()
    if exc.sum():
        cum = exc.cumsum() / exc.sum()
        out["excesso"] = {
            "n": int(exc.sum()), "media": round(float((exc.index.to_numpy(float) * exc.to_numpy(float)).sum() / exc.sum()), 1),
            "mediana": float(exc.index[np.searchsorted(cum.values, 0.5)]),
            "p90": float(exc.index[np.searchsorted(cum.values, 0.9)]),
            "hist": [{"x0": int(a), "n": int(exc[(exc.index >= a) & (exc.index < a + 5)].sum())} for a in range(0, 100, 5)],
            "pct_acima_30": pct(exc[exc.index > 30].sum(), exc.sum()),
        }
    lim = inf["lim"].groupby("lim_int")["n"].sum().sort_values(ascending=False)
    if lim.sum():
        out["limites"] = [{"limite": int(k), "n": int(v), "pct": pct(v, lim.sum())} for k, v in lim.head(6).items()]
    out["estrangeiros"] = {"n": int(inf["pais"]["n"].sum()) if len(inf["pais"]) else 0,
                           "pct": pct(inf["pais"]["n"].sum(), tot["n"].sum(), 2) if len(inf["pais"]) else 0}

    if not overlap:
        out["sem_sobreposicao"] = True
        return out, extra
    out["sem_sobreposicao"] = False

    oc_o = oc[oc["ano_mes"].astype(str).isin(overlap)]
    pe_o = pe[pe["ano_mes"].astype(str).isin(overlap)]
    out["acidentes_periodo_comum"] = {"acidentes": int(len(oc_o)), "mortos": int(oc_o["mortos"].sum()),
                                      "infracoes": int(inf["total"][inf["total"]["ano_mes"].isin(overlap)]["n"].sum())}
    out["infracoes_por_acidente"] = round(out["acidentes_periodo_comum"]["infracoes"] / max(1, out["acidentes_periodo_comum"]["acidentes"]), 1)

    # --- UF
    uf_i = inf["uf"][inf["uf"]["ano_mes"].isin(overlap)].groupby("uf")[["n", "vel"]].sum().rename(columns={"n": "infracoes", "vel": "vel"})
    uf_a = oc_o.groupby("uf", observed=True).agg(acidentes=("id", "size"), mortos=("mortos", "sum"), fatais=("fatal", "sum"))
    uf = uf_a.join(uf_i, how="outer").fillna(0).reset_index().rename(columns={"index": "uf"})
    uf["inf_por_100_acid"] = np.where(uf["acidentes"] > 0, 100 * uf["infracoes"] / uf["acidentes"].replace(0, np.nan), np.nan)
    out["uf"] = [{"uf": r["uf"], "acidentes": int(r["acidentes"]), "mortos": int(r["mortos"]), "infracoes": int(r["infracoes"]),
                  "vel": int(r["vel"]), "inf_por_100_acid": None if pd.isna(r["inf_por_100_acid"]) else round(r["inf_por_100_acid"], 1)}
                 for _, r in uf.sort_values("acidentes", ascending=False).iterrows()]
    out["corr_uf_acidentes"] = spearman(uf["acidentes"], uf["infracoes"])
    out["corr_uf_mortos"] = spearman(uf["mortos"], uf["infracoes"])
    out["fit_uf"] = loglog_fit(uf["acidentes"], uf["infracoes"])
    pos = uf[(uf["acidentes"] > 0) & (uf["infracoes"] > 0)]
    if len(pos):
        out["uf_mais_fiscalizada"] = pos.sort_values("inf_por_100_acid", ascending=False).iloc[0][["uf", "inf_por_100_acid"]].to_dict()
        out["uf_menos_fiscalizada"] = pos.sort_values("inf_por_100_acid").iloc[0][["uf", "inf_por_100_acid"]].to_dict()

    # --- BR
    br_i = inf["br"][inf["br"]["ano_mes"].isin(overlap)].groupby("br")[["n"]].sum().rename(columns={"n": "infracoes"})
    br_a = oc_o.dropna(subset=["br"]).assign(br=lambda d: d["br"].astype(int)).groupby("br").agg(acidentes=("id", "size"), mortos=("mortos", "sum"))
    br = br_a.join(br_i, how="outer").fillna(0).reset_index()
    br["br"] = br["br"].astype(int)
    big = br[(br["acidentes"] >= 30)]
    out["corr_br"] = spearman(big["acidentes"], big["infracoes"])
    out["corr_br_mortos"] = spearman(big["mortos"], big["infracoes"])
    out["br_n_corr"] = int(len(big))
    topbr = br.sort_values("acidentes", ascending=False).head(15)
    out["br_top"] = [{"br": int(r["br"]), "acidentes": int(r["acidentes"]), "mortos": int(r["mortos"]), "infracoes": int(r["infracoes"]),
                      "inf_por_100_acid": round(100 * r["infracoes"] / r["acidentes"], 1) if r["acidentes"] else None} for _, r in topbr.iterrows()]
    extra["br"] = br

    # --- perfil horário (participação % por hora)
    hi = inf["hora"][inf["hora"]["ano_mes"].isin(overlap)].groupby("hora")[["n", "vel"]].sum()
    ha = oc_o.dropna(subset=["hora"]).groupby("hora", observed=True).agg(a=("id", "size"), f=("fatal", "sum"))
    hh = pd.DataFrame(index=range(24)).join(hi).join(ha).fillna(0)
    out["horario"] = [{"h": int(h), "acid": round(100 * r["a"] / hh["a"].sum(), 2), "fatais": round(100 * r["f"] / hh["f"].sum(), 2) if hh["f"].sum() else 0,
                       "infr": round(100 * r["n"] / hh["n"].sum(), 2), "vel": round(100 * r["vel"] / hh["vel"].sum(), 2) if hh["vel"].sum() else 0}
                      for h, r in hh.iterrows()]
    out["corr_hora_acid"] = spearman(hh["a"], hh["n"])
    out["corr_hora_fatais"] = spearman(hh["f"], hh["n"])
    out["pico_infracoes_hora"] = int(hh["n"].idxmax())
    out["pico_acidentes_hora"] = int(hh["a"].idxmax())
    out["pico_fatais_hora"] = int(hh["f"].idxmax())
    noite = [h for h in range(24) if h >= 18 or h < 6]
    out["pct_infracoes_noite"] = pct(hh.loc[noite, "n"].sum(), hh["n"].sum())
    out["pct_fatais_noite"] = pct(hh.loc[noite, "f"].sum(), hh["f"].sum())
    out["pct_acidentes_noite"] = pct(hh.loc[noite, "a"].sum(), hh["a"].sum())

    # --- série diária
    di = inf["dia"].copy()
    di["data"] = pd.to_datetime(di["data"])
    di = di[di["data"].dt.strftime("%Y-%m").isin(overlap)].set_index("data")["n"]
    da = oc_o.groupby("data").size()
    dj = pd.concat([da.rename("a"), di.rename("i")], axis=1).dropna()
    out["corr_diaria"] = spearman(dj["a"], dj["i"])
    out["dias_comuns"] = int(len(dj))

    # --- trechos de 10 km
    ti_ = inf["trecho"][inf["trecho"]["ano_mes"].isin(overlap)].groupby(["br", "bloco_km"])["n"].sum().rename("infracoes")
    ta = (oc_o.dropna(subset=["br", "km"]).assign(br=lambda d: d["br"].astype(int), bloco_km=lambda d: d["km"] // 10 * 10)
          .groupby(["br", "bloco_km"]).agg(acidentes=("id", "size"), mortos=("mortos", "sum")))
    tr = ta.join(ti_, how="outer").fillna(0).reset_index()
    out["n_trechos"] = int(len(tr))
    elig = tr[tr["acidentes"] >= 3]
    out["corr_trecho"] = spearman(elig["acidentes"], elig["infracoes"])
    out["n_trechos_corr"] = int(len(elig))
    top_a = tr.sort_values(["acidentes", "mortos"], ascending=False).head(100)
    top_i = tr.sort_values("infracoes", ascending=False).head(100)
    ka = set(zip(top_a["br"], top_a["bloco_km"]))
    ki = set(zip(top_i["br"], top_i["bloco_km"]))
    out["overlap_top100"] = len(ka & ki)
    # base de comparação: quantos trechos do top-100 de acidentes teriam alguma fiscalização
    out["pct_top100_acid_com_fiscalizacao"] = pct(int((top_a["infracoes"] > 0).sum()), len(top_a))
    mediana_inf = float(tr[tr["infracoes"] > 0]["infracoes"].median()) if (tr["infracoes"] > 0).any() else 0
    out["top_trechos_acidentes"] = [{"br": int(r["br"]), "km": int(r["bloco_km"]), "acidentes": int(r["acidentes"]), "mortos": int(r["mortos"]),
                                     "infracoes": int(r["infracoes"])} for _, r in tr.sort_values(["acidentes", "mortos"], ascending=False).head(10).iterrows()]
    out["mediana_infracoes_trecho_com_fiscalizacao"] = mediana_inf
    extra["trechos"] = tr

    # --- sub/sobrerrepresentação por grupo de veículo
    vi = inf["veic"][inf["veic"]["ano_mes"].isin(overlap)].groupby("grupo_veiculo")[["n"]].sum()
    pv = pe_o.dropna(subset=["id_veiculo"]).drop_duplicates("id_veiculo")
    pv = pv.assign(g=pv["grupo_veiculo"].astype("object")).dropna(subset=["g"])
    pv = pv[pv["g"].isin(vi.index)]
    va = pv.groupby("g").size()
    vv = pd.DataFrame({"infr": vi["n"], "veic_acid": va}).dropna()
    vv = vv[vv["veic_acid"] > 0]
    if len(vv):
        vv["share_infr"] = 100 * vv["infr"] / vv["infr"].sum()
        vv["share_acid"] = 100 * vv["veic_acid"] / vv["veic_acid"].sum()
        vv["razao"] = vv["share_infr"] / vv["share_acid"]
        out["veiculos"] = [{"grupo": g, "share_infr": round(r["share_infr"], 1), "share_acid": round(r["share_acid"], 1),
                            "razao": round(r["razao"], 2), "infr": int(r["infr"]), "veic_acid": int(r["veic_acid"])}
                           for g, r in vv.sort_values("razao").iterrows()]
    return out, extra


# --------------------------------------------------------------------------
# Metadados, qualidade e orquestração
# --------------------------------------------------------------------------


def quality_summary(manifest: dict) -> dict:
    by_kind: dict = {}
    trat: dict = {}
    for ing in manifest["ingestions"]:
        k = by_kind.setdefault(ing["tipo"], {"arquivos": [], "linhas_lidas": 0, "periodos": set(), "linhas_por_tabela": {}})
        k["arquivos"].append(ing["arquivo"])
        k["linhas_lidas"] += ing["linhas_lidas"]
        k["periodos"].update(ing["periodos"])
        for t, n in ing["linhas_por_tabela"].items():
            k["linhas_por_tabela"][t] = k["linhas_por_tabela"].get(t, 0) + n
        for rule, n in ing["tratamentos"].items():
            trat[rule] = trat.get(rule, 0) + n
    for k in by_kind.values():
        p = sorted(x for x in k["periodos"] if x != "sem-data")
        k["periodos"] = p
        k["periodo_label"] = periodo_label(p)
    return {"fontes": by_kind, "tratamentos": dict(sorted(trat.items())), "n_ingestoes": len(manifest["ingestions"])}


def run_analysis(processed: Path = etl.PROCESSED_DIR) -> tuple[dict, dict]:
    oc = etl.read_table("ocorrencias", processed=processed)
    if oc.empty:
        raise SystemExit("Não há dados processados de ocorrências. Coloque os CSVs em data/raw/ e rode `python -m src.etl`.")
    pe = etl.read_table("pessoas", processed=processed)
    ca = etl.read_table("causas", processed=processed)
    ti = etl.read_table("tipos", processed=processed)
    oc["ano_mes"] = oc["ano_mes"].astype(str)
    inf = aggregate_infracoes(processed)
    manifest = etl.load_manifest(processed)

    meses = sorted(oc["ano_mes"].dropna().unique())
    res: dict = {
        "gerado_em": dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC"),
        "periodo_acidentes": periodo_label(meses),
        "meses_acidentes": meses,
        "data_min": str(oc["data"].min().date()), "data_max": str(oc["data"].max().date()),
        "kpis": {
            "acidentes": int(len(oc)), "mortos": int(oc["mortos"].sum()), "feridos": int(oc["feridos"].sum()),
            "feridos_graves": int(oc["feridos_graves"].sum()), "acidentes_fatais": int(oc["fatal"].sum()),
            "pct_fatais": pct(oc["fatal"].sum(), len(oc), 2), "pessoas": int(oc["pessoas"].sum()),
            "veiculos": int(oc["veiculos"].sum()),
            "letalidade": round(100 * oc["mortos"].sum() / len(oc), 2),
            "media_dia": round(len(oc) / max(1, oc["data"].nunique()), 1),
            "n_pessoas_registros": int(len(pe)), "n_causas": int(len(ca)), "n_tipos": int(len(ti)),
            "n_ufs": int(oc["uf"].nunique()), "n_brs": int(oc["br"].nunique()), "n_municipios": int(oc["municipio"].nunique()),
        },
    }
    res["rq1"] = rq1(oc)
    r2 = rq2(oc, pe, ca, ti)
    tabela_causas = r2.pop("causas_tabela_completa")
    idade_veic = r2.pop("idade_veiculo_tabela", None)
    res["rq2"] = r2
    r3, extra3 = rq3(oc, pe, inf)
    res["rq3"] = r3
    res["quality"] = quality_summary(manifest)
    extra = {"oc": oc, "tabela_causas": tabela_causas, "idade_veiculo": idade_veic, **extra3}
    return res, extra


def export_json(res: dict, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(to_jsonable(res), ensure_ascii=False, separators=(",", ":")), encoding="utf-8")

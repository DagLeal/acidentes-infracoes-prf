"""Gera o artigo acadêmico (docs/index.html) e todos os artefatos de docs/assets.

O texto do artigo é um *template* (src/templates/article.html.j2); todos os números,
rankings e frases condicionais vêm de ``analysis.run_analysis``. Assim, ao adicionar
dados de outros anos, o artigo inteiro é recalculado.
"""
from __future__ import annotations

import collections
import html
import inspect
import json
import platform
import re
from pathlib import Path

import pandas as pd
from jinja2 import Environment, FileSystemLoader, select_autoescape

from . import analysis as an
from . import etl, figures

ROOT = Path(__file__).resolve().parents[1]
DOCS = ROOT / "docs"
ASSETS = DOCS / "assets"
TEMPLATES = Path(__file__).resolve().parent / "templates"

TRATAMENTOS = {
    "ajuste:id_em_notacao_cientifica_convertido": "Identificadores em notação científica (ex.: 8e+05) convertidos em inteiro",
    "ajuste:br_zero_convertido_em_nulo": "BR = 0 (local não informado) convertida em nulo",
    "ajuste:classificacao_derivada_das_contagens": "Classificação de gravidade ausente derivada de mortos/feridos",
    "ajuste:linha_de_veiculo_sem_pessoa": "Linhas de veículo sem pessoa registrada (pesid = 0) sinalizadas",
    "ajuste:ano_fabricacao_zero_(sem_veiculo)_anulado": "Ano de fabricação 0 (sem veículo) anulado",
    "ajuste:ano_fabricacao_invalido_anulado": "Ano de fabricação impossível anulado",
    "ajuste:idade_sentinela_zero_anulada": "Idade 0 usada como sentinela (estado físico “Não Informado”) anulada",
    "ajuste:idade_acima_de_110_anulada": "Idade acima de 110 anos anulada",
    "ajuste:coordenada_fora_do_brasil_anulada": "Coordenadas fora do território brasileiro anuladas",
    "ajuste:data_invalida_ou_ausente": "Datas inválidas ou ausentes",
    "alerta:classificacao_incoerente_com_mortos": "Alerta: classificação “sem fatais” com mortos registrados (mantida)",
    "descartado:sem_id": "Linhas descartadas por ausência de identificador",
    "descartado:id_duplicado": "Ocorrências duplicadas removidas",
    "descartado:linha_duplicada": "Linhas de pessoa/veículo duplicadas removidas",
    "descartado:auto_duplicado": "Autos de infração duplicados removidos",
    "info:chave_sintetica_do_auto_(layout_antigo)": "Informação: autos do layout antigo sem número do auto receberam chave sintética",
    "info:assinatura_do_auto_nao_informada": "Informação: campo “assinatura do auto” sem valor (N/I) em todos os registros",
}
FONTES = {
    "ocorrencias": ("Ocorrências (datatran)", "1 linha = 1 acidente"),
    "pessoas": ("Pessoas e veículos envolvidos", "1 linha = 1 pessoa × veículo"),
    "causas_tipos": ("Todas as causas e tipos", "1 linha = pessoa × causa × tipo (reduzida a acidente × causa e acidente × tipo)"),
    "infracoes": ("Infrações (autos)", "1 linha = 1 auto de infração"),
}
REFS = [
    "AGRESTI, A. <b>Categorical data analysis</b>. 3. ed. Hoboken: Wiley, 2013.",
    "BOSTOCK, M.; OGIEVETSKY, V.; HEER, J. D³: data-driven documents. <b>IEEE Transactions on Visualization and Computer Graphics</b>, v. 17, n. 12, p. 2301–2309, 2011.",
    "BRASIL. Lei nº 9.503, de 23 de setembro de 1997. Institui o Código de Trânsito Brasileiro. <b>Diário Oficial da União</b>, Brasília, 24 set. 1997.",
    "BRASIL. Polícia Rodoviária Federal. <b>Dados abertos: acidentes</b>. Brasília: PRF, [s.d.]a. Disponível em: <a href=\"https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-acidentes\">https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-acidentes</a>. Acesso em: {acesso}.",
    "BRASIL. Polícia Rodoviária Federal. <b>Dados abertos da PRF</b> (infrações/multas). Brasília: PRF, [s.d.]b. Disponível em: <a href=\"https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-da-prf\">https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-da-prf</a>. Acesso em: {acesso}.",
    "BRASIL. Polícia Rodoviária Federal. <b>Dicionário de variáveis – Infrações</b>. Brasília: PRF, set. 2016.",
    "HARRIS, C. R. <i>et al.</i> Array programming with NumPy. <b>Nature</b>, v. 585, p. 357–362, 2020.",
    "HUNTER, J. D. Matplotlib: a 2D graphics environment. <b>Computing in Science &amp; Engineering</b>, v. 9, n. 3, p. 90–95, 2007.",
    "McKINNEY, W. Data structures for statistical computing in Python. In: PYTHON IN SCIENCE CONFERENCE, 9., 2010, Austin. <b>Proceedings</b> […]. Austin: SciPy, 2010. p. 56–61.",
    "ROBINS, J.; BRESLOW, N.; GREENLAND, S. Estimators of the Mantel-Haenszel variance consistent in both sparse data and large-strata limiting models. <b>Biometrics</b>, v. 42, n. 2, p. 311–323, 1986.",
    "VIRTANEN, P. <i>et al.</i> SciPy 1.0: fundamental algorithms for scientific computing in Python. <b>Nature Methods</b>, v. 17, p. 261–272, 2020.",
    "WILKINSON, M. D. <i>et al.</i> The FAIR Guiding Principles for scientific data management and stewardship. <b>Scientific Data</b>, v. 3, art. 160018, 2016.",
    "WILSON, E. B. Probable inference, the law of succession, and statistical inference. <b>Journal of the American Statistical Association</b>, v. 22, n. 158, p. 209–212, 1927.",
    "WORLD HEALTH ORGANIZATION. <b>Global status report on road safety 2023</b>. Geneva: WHO, 2023.",
]

TRI = ('<svg class="{cls}" viewBox="0 0 100 90" role="img" aria-label="Emblema de três triângulos">'
       '<g fill="#f0cf6a" stroke="#8a6410" stroke-width="2" stroke-linejoin="round">'
       '<path d="M50 4 L73 44 H27Z"/><path d="M27 48 L50 88 H4Z"/><path d="M73 48 L96 88 H50Z"/></g></svg>')


# ------------------------------- formatação pt-BR -------------------------------

def _num(x, nd):
    if x is None or (isinstance(x, float) and x != x):
        return "—"
    s = f"{x:,.{nd}f}"
    return s.replace(",", "§").replace(".", ",").replace("§", ".")


def f_n(x):
    return _num(round(x), 0) if x is not None else "—"


def f_d1(x):
    return _num(x, 1)


def f_d2(x):
    return _num(x, 2)


def f_hh(h):
    return f"{int(h):02d}h"


def f_p(p):
    if p is None:
        return "p = —"
    return "p &lt; 0,001" if p < 0.001 else "p = " + _num(p, 3)


def f_ci(d):
    if not isinstance(d, dict) or d.get("or") is None:
        return "—"
    return f"{_num(d['or'], 2)} (IC 95%: {_num(d['lo'], 2)}–{_num(d['hi'], 2)})"


# ------------------------------- fatos e textos -------------------------------

def _month_name(ano_mes: str) -> str:
    y, m = ano_mes.split("-")
    return f"{an.MESES[int(m) - 1]}/{y}"


def build_facts(res: dict) -> dict:
    r1, r2, r3 = res["rq1"], res["rq2"], res["rq3"]
    f: dict = {}
    full = [m for m in r1["mensal"] if not m["parcial"]]
    f["tem_parcial"] = any(m["parcial"] for m in r1["mensal"])
    if full:
        hi, lo = max(full, key=lambda m: m["acidentes"]), min(full, key=lambda m: m["acidentes"])
        f["mes_pico"] = {"nome": _month_name(hi["ano_mes"]), "acidentes": hi["acidentes"]}
        f["mes_min"] = {"nome": _month_name(lo["ano_mes"]), "acidentes": lo["acidentes"]}
    else:
        f["mes_pico"] = f["mes_min"] = None
    zero_fase = {"pct_fatais": 0.0, "n": 0}
    f["fase"] = collections.defaultdict(lambda: dict(zero_fase), {d["fase"]: d for d in r1["fase"]})
    f["fase_max"] = max(r1["fase"], key=lambda d: d["pct_fatais"]) if r1["fase"] else {"fase": "—", "pct_fatais": 0}
    zero_perfil = {"pct_obito": 0.0, "share_envolvidos": 0.0, "share_obitos": 0.0, "n": 0, "obitos": 0}
    f["perfil"] = collections.defaultdict(lambda: dict(zero_perfil), {d["perfil"]: d for d in r2["perfis"]})
    auto, ped = f["perfil"]["Automóvel e utilitários"]["pct_obito"], f["perfil"]["Pedestres"]["pct_obito"]
    f["ratio_ped_auto"] = ped / auto if auto else 0.0
    f["causas_top3"] = [c["causa"] for c in sorted(r2["causas"], key=lambda c: -c["n_citada"])[:3]]
    tipos = r2["tipos"]
    f["tipo_top"] = max(tipos, key=lambda t: t["n"])
    elig = [t for t in tipos if t["n"] >= r2["min_n"]] or tipos
    f["tipo_letal"] = max(elig, key=lambda t: t["pct_fatais"] or 0)
    if r3 and not r3.get("sem_sobreposicao"):
        ufs = {u["uf"]: u for u in r3["uf"]}
        a, b = r3.get("uf_mais_fiscalizada"), r3.get("uf_menos_fiscalizada")
        f["uf_mais"] = {**a, "acidentes": ufs[a["uf"]]["acidentes"]}
        f["uf_menos"] = {**b, "acidentes": ufs[b["uf"]]["acidentes"]}
    return f


def build_abstract(res: dict, f: dict) -> tuple[str, str, str]:
    k, r1, r2, r3 = res["kpis"], res["rq1"], res["rq2"], res["rq3"]
    nd = r1["noite_vs_dia"]
    adj = (nd.get("ajustado_mh") or nd)["or"]
    ped = f["perfil"]["Pedestres"]
    moto = f["perfil"]["Motocicletas"]
    n, d1, d2 = f_n, f_d1, f_d2
    inf_txt = ""
    cross = ""
    inf_en = cross_en = ""
    if r3 and not r3.get("sem_sobreposicao"):
        inf_txt = f" e {n(r3['totais']['infracoes'])} autos de infração ({r3['periodo_infracoes']})"
        cross = (f" Entre as UFs, infrações e acidentes são fortemente associados (ρ de Spearman = {d2(r3['corr_uf_acidentes']['rho'])}), "
                 f"mas {d1(r3['pct_fatais_noite'])}% dos acidentes fatais ocorrem entre 18h e 6h, janela com apenas {d1(r3['pct_infracoes_noite'])}% das infrações.")
        inf_en = f" and {n(r3['totais']['infracoes'])} traffic-violation records"
        cross_en = (f" Across states, violations track accident counts closely (Spearman ρ = {d2(r3['corr_uf_acidentes']['rho'])}), "
                    f"yet {d1(r3['pct_fatais_noite'])}% of fatal accidents happen between 6 pm and 6 am, when only {d1(r3['pct_infracoes_noite'])}% of violations are issued.")
    pt = (f"Este estudo analisa {n(k['acidentes'])} acidentes registrados pela Polícia Rodoviária Federal (PRF) nas rodovias federais brasileiras "
          f"({res['periodo_acidentes']}), que deixaram {n(k['mortos'])} mortos{inf_txt}. Um pipeline determinístico em Python (pandas, NumPy, SciPy) "
          f"integra quatro bases abertas — ocorrências, envolvidos, todas as causas e tipos e infrações —, trata inconsistências de forma rastreável e "
          f"alimenta visualizações interativas. Três perguntas orientam a análise: quando a gravidade se concentra, quais causas e perfis se associam a "
          f"mais mortes e se a fiscalização acompanha a geografia dos acidentes. Acidentes em plena noite têm {d1(nd['or'])}× a chance de serem fatais "
          f"em relação aos diurnos ({d1(adj)}× após ajuste por tipo de pista e área urbana/rural); pedestres morrem em {d1(ped['pct_obito'])}% dos casos "
          f"e motociclistas respondem por {d1(moto['share_obitos'])}% dos óbitos com {d1(moto['share_envolvidos'])}% dos envolvidos.{cross} "
          f"Os resultados indicam associações, não causalidade, e o repositório incorpora novos anos apenas com a adição de CSVs à pasta de dados brutos.")
    def en_(txt: str) -> str:  # 1.234,5 -> 1,234.5 (apenas números formatados em pt-BR)
        return re.sub(r"\d[\d.,]*", lambda m: m.group(0).translate(str.maketrans(".,", ",.")) if re.fullmatch(r"\d{1,3}(\.\d{3})*(,\d+)?|\d+,\d+", m.group(0)) else m.group(0), txt)

    en = (f"We analyse {n(k['acidentes'])} road accidents recorded by Brazil's Federal Highway Police (PRF) between {res['data_min']} and {res['data_max']}, "
          f"with {n(k['mortos'])} deaths{inf_en}. A deterministic Python pipeline (pandas, NumPy, SciPy) integrates four open datasets — accidents, people involved, "
          f"all causes and types, and violations — and logs every cleaning rule. Three research questions guide the study: when severity concentrates, which causes and "
          f"road-user profiles are linked to more deaths, and whether enforcement follows the geography of accidents. Night-time accidents are {d1(nd['or'])} times as "
          f"likely to be fatal as daytime ones ({d1(adj)} after adjustment for road type and urban/rural setting); pedestrians die in {d1(ped['pct_obito'])}% of cases, and "
          f"motorcyclists account for {d1(moto['share_obitos'])}% of deaths while making up {d1(moto['share_envolvidos'])}% of those involved.{cross_en} "
          f"Findings are associations, not causal effects; new years can be added by dropping CSVs into the raw-data folder.")
    en = en_(en).replace(res["data_min"], res["data_min"]).replace(res["data_max"], res["data_max"])
    short = f"{n(k['acidentes'])} acidentes e {n(k['mortos'])} mortos nas rodovias federais ({res['periodo_acidentes']}): quando, por quê e onde — e como a fiscalização acompanha."
    return pt, en, short


# ------------------------------- artefatos -------------------------------

def _src(func) -> str:
    return html.escape(inspect.getsource(func).rstrip())


def export_tables(res: dict, extra: dict, outdir: Path) -> list[str]:
    outdir.mkdir(parents=True, exist_ok=True)
    written = []

    def save(name, df):
        df.to_csv(outdir / name, index=False, encoding="utf-8", lineterminator="\n")
        written.append(name)

    save("rq1_mensal.csv", pd.DataFrame(res["rq1"]["mensal"]))
    save("rq1_dia_hora.csv", pd.DataFrame(res["rq1"]["heat"]).rename(columns={"d": "dia_semana_idx", "h": "hora", "n": "acidentes", "f": "fatais", "m": "mortos"}))
    save("rq1_fase_dia.csv", pd.DataFrame(res["rq1"]["fase"]))
    tc = extra["tabela_causas"].copy()
    save("rq2_causas.csv", tc.round(3))
    save("rq2_tipos.csv", pd.DataFrame(res["rq2"]["tipos"]))
    save("rq2_perfis.csv", pd.DataFrame(res["rq2"]["perfis"]))
    save("rq2_obitos_sexo_idade.csv", pd.DataFrame(res["rq2"]["piramide"]))
    if extra.get("idade_veiculo") is not None:
        save("rq2_idade_veiculo.csv", extra["idade_veiculo"].round(3))
    r3 = res["rq3"]
    if r3:
        save("rq3_grupos_infracao.csv", pd.DataFrame(r3["grupos"]))
        save("rq3_top_infracoes.csv", pd.DataFrame(r3["top_infracoes"]))
        if not r3.get("sem_sobreposicao"):
            save("rq3_uf.csv", pd.DataFrame(r3["uf"]))
            save("rq3_br.csv", extra["br"].sort_values("acidentes", ascending=False))
            save("rq3_horario.csv", pd.DataFrame(r3["horario"]))
            save("rq3_trechos_top.csv", pd.DataFrame(r3["top_trechos_acidentes"]))
            if "veiculos" in r3:
                save("rq3_veiculos.csv", pd.DataFrame(r3["veiculos"]))
    return written


def build_site(cfg_path: Path = ROOT / "config.json", processed: Path = etl.PROCESSED_DIR) -> Path:
    cfg = json.loads(cfg_path.read_text(encoding="utf-8"))
    res, extra = an.run_analysis(processed)
    f = build_facts(res)

    # --- saídas de dados e figuras
    an.export_json(res, ASSETS / "data" / "results.json")
    export_tables(res, extra, ASSETS / "tables")
    (ASSETS / "figures").mkdir(parents=True, exist_ok=True)
    figures.mapa_densidade(extra["oc"], ASSETS / "figures" / "mapa_densidade.png", res["periodo_acidentes"])
    r3 = res["rq3"]
    if r3 and not r3.get("sem_sobreposicao"):
        figures.trechos_scatter(extra["trechos"], ASSETS / "figures" / "trechos_acidentes_infracoes.png", r3["periodo_comum"], r3["corr_trecho"]["rho"])

    # --- robustez a bases ausentes
    res["rq1"]["noite_vs_dia"].setdefault("ajustado_mh", None)
    if not res["rq1"]["noite_vs_dia"]["ajustado_mh"]:
        res["rq1"]["noite_vs_dia"]["ajustado_mh"] = {k: res["rq1"]["noite_vs_dia"][k] for k in ("or", "lo", "hi")}
    res["rq2"].setdefault("moto_vs_auto", {"or": 0, "lo": 0, "hi": 0, "p": 1})
    res["rq2"]["multi_causa"] = res["rq2"]["multi_causa"] or {"media": 0, "pct_mais_de_uma": 0, "faixas": [], "or_mais_de_uma": None}

    pt, en, short = build_abstract(res, f)
    for label, txt in (("resumo", pt), ("abstract", en)):
        words = len(re.findall(r"\w+", txt))
        if not 150 <= words <= 250:
            print(f"[aviso] {label} tem {words} palavras (diretriz: 150 a 250)")

    q = res["quality"]
    fontes = []
    for kind in ("ocorrencias", "pessoas", "causas_tipos", "infracoes"):
        s = q["fontes"].get(kind)
        if not s:
            continue
        nome, grao = FONTES[kind]
        fontes.append({"nome": nome, "grao": grao, "arquivos": s["arquivos"], "linhas": s["linhas_lidas"], "periodo": s["periodo_label"],
                       "tabelas": "; ".join(f"{t} {f_n(n)}" for t, n in s["linhas_por_tabela"].items())})
    trat = [{"rotulo": TRATAMENTOS.get(k, k), "n": v} for k, v in q["tratamentos"].items()]
    acesso = "16 nov. 2026"
    repo_url = f"https://github.com/{cfg['github_usuario']}/{cfg['github_repositorio']}"
    jsonld = json.dumps({
        "@context": "https://schema.org", "@type": "ScholarlyArticle", "headline": cfg["titulo"],
        "author": [{"@type": "Person", "name": a} for a in cfg["autores"]], "inLanguage": "pt-BR",
        "keywords": cfg["palavras_chave"], "abstract": pt, "license": "https://creativecommons.org/licenses/by/4.0/",
        "isBasedOn": "https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-acidentes", "codeRepository": repo_url,
    }, ensure_ascii=False).replace("</", "<\\/")
    data_json = json.dumps(an.to_jsonable({k: res[k] for k in ("rq1", "rq2", "rq3", "kpis")}), ensure_ascii=False, separators=(",", ":")).replace("</", "<\\/")

    env = Environment(loader=FileSystemLoader(TEMPLATES), autoescape=select_autoescape(["html", "j2"]))
    env.filters.update({"n": f_n, "d1": f_d1, "d2": f_d2, "hh": f_hh, "p_fmt": lambda p: f_p(p), "ci": f_ci})
    env.policies["json.dumps_kwargs"] = {"ensure_ascii": False}
    tpl = env.get_template("article.html.j2")
    from markupsafe import Markup
    out = tpl.render(
        cfg=cfg, res=res, k=res["kpis"], r1=res["rq1"], r2=res["rq2"], r3=r3, f=f, per=res["periodo_acidentes"],
        resumo_pt=pt, resumo_en=en, resumo_curto=short, keywords_en=cfg.get("palavras_chave_en", []),
        fontes=fontes, tratamentos=trat, refs=[Markup(r.format(acesso=acesso)) for r in REFS], repo_url=repo_url,
        py_version=platform.python_version(), jsonld=Markup(jsonld), data_json=Markup(data_json),
        tri_big=Markup(TRI.format(cls="tri")), tri_small=Markup(TRI.format(cls="tri").replace('class="tri"', 'class="tri" style="width:30px;height:27px;vertical-align:middle"')),
        code_to_num=Markup(_src(etl.to_num)), code_parse_dates=Markup(_src(etl.parse_dates)), code_detect_kind=Markup(_src(etl.detect_kind)),
    )
    dest = DOCS / "index.html"
    dest.write_text(out, encoding="utf-8")
    placeholders = [a for a in cfg["autores"] if a.startswith("Nome do Autor")] + (["instituição"] if cfg["instituicao"].startswith("Nome da") else []) + (["usuário GitHub"] if cfg["github_usuario"] == "SEU-USUARIO" else [])
    if placeholders:
        print(f"[aviso] edite config.json: ainda há campos de exemplo ({', '.join(placeholders)}).")
    return dest

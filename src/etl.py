"""ETL dos dados abertos da PRF (acidentes e infrações em rodovias federais).

Uso (a partir da raiz do repositório)::

    python -m src.etl              # ingere os CSVs novos de data/raw/
    python -m src.etl --rebuild    # refaz tudo a partir do zero
    python -m src.etl --dictionary # regenera data/data_dictionary.md

Princípios de projeto
---------------------
* **Basta soltar CSVs em ``data/raw/``.** O tipo de cada arquivo é detectado
  pelo *cabeçalho* (não pelo nome), de modo que arquivos de outros anos
  (``datatran2025.csv``, ``acidentes2024.csv`` …) entram sem configuração.
  Cabeçalhos antigos (dicionário PRF de 2016) e novos são reconhecidos.
* **Idempotente.** Cada arquivo bruto é identificado pelo SHA-256; reprocessar
  a pasta não duplica dados.
* **Sem operações destrutivas sem rastro.** Os dados tratados são gravados em
  partições ``data/processed/<tabela>/<AAAA-MM>/``. Se um novo arquivo cobre
  um mês já existente, as partições antigas desse mês são *arquivadas* em
  ``data/processed/_superseded/`` (não apagadas) e a troca é registrada em
  ``data/processed/manifest.json``. Toda correção aplicada aos dados é
  contabilizada no manifesto.
* **Memória limitada.** O arquivo de infrações (centenas de MB) é lido em
  blocos; as demais tabelas são pequenas após a limpeza.
"""
from __future__ import annotations

import argparse
import csv
import datetime as dt
import gzip
import hashlib
import json
import logging
import re
import shutil
import sys
import unicodedata
from collections import Counter
from pathlib import Path
from typing import Callable, Iterator

import numpy as np
import pandas as pd

from .schemas import CAUSAS, INFRACOES, OCORRENCIAS, PESSOAS, TABLES, TIPOS, Table

log = logging.getLogger("etl")

ROOT = Path(__file__).resolve().parents[1]
RAW_DIR = ROOT / "data" / "raw"
PROCESSED_DIR = ROOT / "data" / "processed"
MANIFEST = "manifest.json"
CHUNK_ROWS = 250_000
SCHEMA_VERSION = 1

NA_TOKENS = ["NA", "NaN", "nan", "NULL", "null", ""]
BRAZIL_LAT = (-34.0, 6.0)
BRAZIL_LON = (-75.0, -33.0)

# --------------------------------------------------------------------------
# Utilitários de texto e números
# --------------------------------------------------------------------------


def unaccent(text: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", text) if not unicodedata.combining(c))


def norm_header(name: str) -> str:
    """'Data da Infração (DD/MM/AAAA)' -> 'data_da_infracao_dd_mm_aaaa'."""
    name = unaccent(str(name).replace("\ufeff", "")).lower().strip()
    return re.sub(r"[^a-z0-9]+", "_", name).strip("_")


def na_series(index) -> pd.Series:
    return pd.Series(np.nan, index=index, dtype="object")


def col(df: pd.DataFrame, name: str) -> pd.Series:
    """Coluna do bruto ou série vazia se ausente (tolera layouts de anos antigos)."""
    if name in df.columns:
        return df[name]
    return na_series(df.index)


def clean_text(s: pd.Series) -> pd.Series:
    s = s.astype("object")
    out = s.where(s.isna(), s.astype(str).str.strip().str.replace(r"\s+", " ", regex=True))
    return out.replace({"": np.nan})


def to_num(s: pd.Series) -> pd.Series:
    """Converte para float aceitando vírgula decimal e notação científica."""
    txt = s.astype("object")
    txt = txt.where(txt.isna(), txt.astype(str).str.replace(",", ".", regex=False).str.strip())
    return pd.to_numeric(txt, errors="coerce").astype("float64")


def to_int(s: pd.Series, dtype: str = "Int64") -> pd.Series:
    n = to_num(s)
    n = n.where(np.isfinite(n))
    return n.round().astype(dtype)


def parse_dates(s: pd.Series) -> pd.Series:
    """Aceita AAAA-MM-DD (padrão atual) e DD/MM/AAAA (arquivos antigos)."""
    head = s.astype("object")
    head = head.where(head.isna(), head.astype(str).str.slice(0, 10))
    out = pd.to_datetime(head, format="%Y-%m-%d", errors="coerce")
    missing = out.isna() & head.notna()
    if missing.any():
        out2 = pd.to_datetime(head[missing], format="%d/%m/%Y", errors="coerce")
        out = out.copy()
        out[missing] = out2
    return out


def map_unique(s: pd.Series, func: Callable) -> pd.Series:
    """Aplica func só aos valores únicos (rápido em colunas com poucas categorias)."""
    uniques = s.dropna().unique()
    mapping = {u: func(u) for u in uniques}
    return s.map(mapping)


def to_category(s: pd.Series) -> pd.Series:
    return s.astype("object").astype("category")


# --------------------------------------------------------------------------
# Padronização semântica compartilhada entre tabelas
# --------------------------------------------------------------------------

_TIPO_VEICULO = {
    "automovel": "Automóvel", "caminhonete": "Caminhonete", "camioneta": "Camioneta",
    "caminhao": "Caminhão", "caminhao trator": "Caminhão-trator", "caminhao-trator": "Caminhão-trator",
    "caminhao tanque": "Caminhão-tanque", "motocicleta": "Motocicleta", "motoneta": "Motoneta",
    "ciclomotor": "Ciclomotor", "utilitario": "Utilitário", "semi-reboque": "Semireboque",
    "semireboque": "Semireboque", "reboque": "Reboque", "onibus": "Ônibus",
    "microonibus": "Micro-ônibus", "micro-onibus": "Micro-ônibus", "motor-casa": "Motor-casa",
    "triciclo": "Triciclo", "quadriciclo": "Quadriciclo", "bicicleta": "Bicicleta",
    "trator de rodas": "Trator de rodas", "trator misto": "Trator misto",
    "trator de esteiras": "Trator de esteiras", "carro de mao": "Carro de mão",
    "charrete": "Charrete", "carroca": "Carroça", "bonde": "Bonde",
}
_NOT_INFORMED = {"nao informado", "n/i", "ignorado", "nao se aplica"}


def std_tipo_veiculo(value: str):
    key = unaccent(str(value)).lower().strip()
    if key in _NOT_INFORMED or not key:
        return np.nan
    return _TIPO_VEICULO.get(key, str(value).strip().capitalize())


def grupo_veiculo(value: str):
    key = unaccent(str(value)).lower()
    if "bicicleta" in key or "ciclo" in key and "motociclo" not in key and "ciclomotor" not in key:
        return "Bicicletas"
    if "moto" in key and "motor-casa" not in key:  # motocicleta, motoneta, ciclomotor
        return "Motocicletas"
    if "onibus" in key:
        return "Ônibus"
    if any(k in key for k in ("caminhao", "reboque", "trator")):
        return "Caminhões e reboques"
    if any(k in key for k in ("automovel", "camioneta", "caminhonete", "utilitario", "jipe", "motor-casa")):
        return "Automóvel e utilitários"
    return "Outros"


def _artigo(enq) -> tuple[int | None, str]:
    """'art. 165-a' -> (165, '165-a'); 'art. 230, xiii' -> (230, '230')."""
    m = re.search(r"art[.,]?\s*(\d+)(?:\s*-\s*([a-z]))?", str(enq).lower())
    if not m:
        return None, ""
    return int(m.group(1)), m.group(1) + (f"-{m.group(2)}" if m.group(2) else "")


GRUPOS_INFRACAO = (
    "Excesso de velocidade", "Álcool e drogas", "Cinto, capacete e retenção",
    "Distração e atenção ao volante", "Manobras e sinalização", "Documentação e licenciamento",
    "Veículo e carga", "Transporte profissional", "Outras",
)


def grupo_infracao(pair):
    """Agrupa a infração pelo artigo do CTB (robusto às abreviações da PRF),
    usando o texto da descrição apenas para desempatar o art. 230 (que mistura temas)."""
    desc, enq = pair
    d = unaccent(str(desc)).lower() if isinstance(desc, str) else ""
    if "produtos perigosos" in d:
        return "Transporte profissional"
    n, full = _artigo(enq)
    if n is None:
        return "Excesso de velocidade" if "velocidade superior" in d else "Outras"
    if n == 218 or "velocidade superior" in d:
        return "Excesso de velocidade"
    if n in (165, 277, 306) or "alc/sub psic" in d or "embriaguez" in d:
        return "Álcool e drogas"
    if n in (167, 168, 244):
        return "Cinto, capacete e retenção"
    if n in (169, 252):
        return "Distração e atenção ao volante"
    if "produtos perigosos" in d or "toxicolog" in d or "67-c" in d or "tempo de direcao" in d or "descanso" in d:
        return "Transporte profissional"
    if n in (162, 163, 164, 166, 221, 232, 233) or (n == 230 and ("licenciad" in d or "placa" in d)):
        return "Documentação e licenciamento"
    if full == "209-a":
        return "Outras"
    if 170 <= n <= 220:
        return "Manobras e sinalização"
    if n in (222, 223, 224, 225, 226, 227, 228, 229, 230, 231, 234, 235, 236, 237, 238, 239, 240, 241, 242, 243, 245, 246, 247, 248, 249, 250, 251):
        return "Veículo e carga"
    return "Outras"


def std_especie(value: str):
    key = unaccent(str(value)).lower().strip()
    if key in _NOT_INFORMED or not key:
        return np.nan
    return str(value).strip().capitalize()


# --------------------------------------------------------------------------
# Detecção do tipo de arquivo (pelo cabeçalho) e leitura de arquivos brutos
# --------------------------------------------------------------------------

INFRACAO_ALIASES = {
    "numero_do_auto": "auto",
    "data_da_infracao_dd_mm_aaaa": "data", "data_da_infracao": "data", "dat_infracao": "data",
    "indicador_de_abordagem": "abordagem", "tip_abordagem": "abordagem",
    "assinatura_do_auto": "assinatura", "ind_assinou_auto": "assinatura",
    "sentido_trafego": "sentido", "ind_sentido_trafego": "sentido",
    "uf_infracao": "uf",
    "br_infracao": "br", "num_br_infracao": "br",
    "km_infracao": "km", "num_km_infracao": "km",
    "municipio": "municipio", "nom_municipio": "municipio",
    "indicador_veiculo_estrangeiro": "ind_estrangeiro", "ind_veiculo_estrangeiro": "ind_estrangeiro",
    "uf_placa": "uf_placa",
    "descricao_especie_veiculo": "especie", "especie": "especie",
    "descricao_marca_veiculo": "marca", "nome_veiculo_marca": "marca",
    "descricao_tipo_veiculo": "tipo_veiculo",
    "descricao_modelo_veiculo": "modelo", "nom_modelo_veiculo": "modelo",
    "codigo_da_infracao": "codigo_infracao", "cod_infracao": "codigo_infracao",
    "descricao_abreviada_infracao": "descricao", "descricao_abreviada": "descricao",
    "enquadramento_da_infracao": "enquadramento", "enquadramento": "enquadramento",
    "inicio_vigencia_da_infracao": "inicio_vigencia", "data_inicio_vigencia": "inicio_vigencia",
    "fim_vigencia_infracao": "fim_vigencia", "data_fim_vigencia": "fim_vigencia",
    "medicao_infracao": "medicao_tipo", "med_realizada": "medicao_tipo",
    "hora_infracao": "hora",
    "medicao_considerada": "medicao_considerada", "med_considerada": "medicao_considerada",
    "excesso_verificado": "excesso_verificado", "exc_verificado": "excesso_verificado",
    "qtd_infracoes": "qtd",
}
ACIDENTE_ALIASES = {"condicao_meteorologica": "condicao_metereologica"}


def sniff_encoding(path: Path) -> str:
    """utf-8 → cp1252 → latin-1 (nesta ordem), avaliando uma amostra inteira de linhas."""
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rb") as fh:
        sample = fh.read(4_000_000)
    cut = sample.rfind(b"\n")
    sample = sample[: cut + 1] if cut > 0 else sample
    for enc in ("utf-8-sig", "cp1252"):
        try:
            sample.decode(enc)
            return enc
        except UnicodeDecodeError:
            continue
    return "latin-1"


def sniff_delimiter(path: Path, encoding: str) -> str:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding=encoding, errors="replace", newline="") as fh:
        header = fh.readline()
    counts = {d: header.count(d) for d in (";", ",", "\t", "|")}
    return max(counts, key=counts.get)


def read_header(path: Path, encoding: str, delimiter: str) -> list[str]:
    opener = gzip.open if path.suffix == ".gz" else open
    with opener(path, "rt", encoding=encoding, errors="replace", newline="") as fh:
        row = next(csv.reader(fh, delimiter=delimiter))
    return [norm_header(c) for c in row]


def detect_kind(columns: list[str]) -> str | None:
    cols = set(columns)
    if len(cols & set(INFRACAO_ALIASES)) >= 8:
        return "infracoes"
    if {"causa_principal", "ordem_tipo_acidente"} & cols and "causa_acidente" in cols:
        return "causas_tipos"
    if "pesid" in cols and "id_veiculo" in cols:
        return "pessoas"
    if {"pessoas", "veiculos", "mortos", "causa_acidente"} <= cols:
        return "ocorrencias"
    return None


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with open(path, "rb") as fh:
        for block in iter(lambda: fh.read(1 << 20), b""):
            h.update(block)
    return h.hexdigest()


def read_raw_chunks(path: Path, encoding: str, delimiter: str, kind: str) -> Iterator[pd.DataFrame]:
    """Lê o bruto em blocos, tudo como texto, com cabeçalho normalizado."""
    reader = pd.read_csv(
        path, sep=delimiter, encoding=encoding, encoding_errors="replace", dtype=str,
        keep_default_na=False, na_values=NA_TOKENS, chunksize=CHUNK_ROWS, low_memory=False,
    )
    aliases = INFRACAO_ALIASES if kind == "infracoes" else ACIDENTE_ALIASES
    for chunk in reader:
        chunk.columns = [aliases.get(norm_header(c), norm_header(c)) for c in chunk.columns]
        yield chunk


# --------------------------------------------------------------------------
# Limpeza por tipo de arquivo
# --------------------------------------------------------------------------


def _within(s: pd.Series, lo: float, hi: float) -> pd.Series:
    return s.where((s >= lo) & (s <= hi))


def _context(raw: pd.DataFrame, stats: Counter) -> pd.DataFrame:
    """Colunas comuns a todas as tabelas de acidentes (id, data, período, UF)."""
    sci = col(raw, "id").astype("object").astype(str).str.contains(r"\d[eE][+-]?\d", na=False)
    stats["ajuste:id_em_notacao_cientifica_convertido"] += int(sci.sum())
    out = pd.DataFrame(index=raw.index)
    out["id"] = to_int(col(raw, "id"))
    data = parse_dates(col(raw, "data_inversa"))
    stats["ajuste:data_invalida_ou_ausente"] += int(data.isna().sum())
    out["data"] = data
    out["ano_mes"] = data.dt.strftime("%Y-%m")
    out["uf"] = clean_text(col(raw, "uf")).str.upper()
    return out


def clean_ocorrencias(raw: pd.DataFrame, stats: Counter) -> dict[str, pd.DataFrame]:
    out = _context(raw, stats)
    out["ano"] = out["data"].dt.year.astype("Int16")
    out["mes"] = out["data"].dt.month.astype("Int8")
    out["dia_semana"] = clean_text(col(raw, "dia_semana")).str.lower()
    hora = to_num(col(raw, "horario").astype("object").astype(str).str.slice(0, 2).replace({"nan": np.nan}))
    out["hora"] = _within(hora, 0, 23).astype("Int8")
    br = to_int(col(raw, "br"), "Int64")
    zero_br = br == 0
    stats["ajuste:br_zero_convertido_em_nulo"] += int(zero_br.sum())
    out["br"] = br.mask(zero_br).astype("Int16")
    km = to_num(col(raw, "km"))
    out["km"] = km.where(km >= 0)
    for c in ("municipio", "causa_acidente", "tipo_acidente", "fase_dia", "sentido_via",
              "condicao_metereologica", "tipo_pista", "tracado_via", "regional", "delegacia", "uop"):
        out[c] = clean_text(col(raw, c))
    out = out.rename(columns={"condicao_metereologica": "condicao_meteorologica"})
    uso = clean_text(col(raw, "uso_solo")).str.lower().map({"sim": 1, "nao": 0, "não": 0})
    out["area_urbana"] = uso.astype("Int8")
    for c in ("pessoas", "mortos", "feridos_leves", "feridos_graves", "feridos", "ilesos", "ignorados", "veiculos"):
        out[c] = to_int(col(raw, c), "Int16")
    if out["feridos"].isna().all():
        out["feridos"] = (out["feridos_leves"].fillna(0) + out["feridos_graves"].fillna(0)).astype("Int16")
    lat, lon = to_num(col(raw, "latitude")), to_num(col(raw, "longitude"))
    ok = lat.between(*BRAZIL_LAT) & lon.between(*BRAZIL_LON) & ~((lat == 0) & (lon == 0))
    bad = (lat.notna() | lon.notna()) & ~ok
    stats["ajuste:coordenada_fora_do_brasil_anulada"] += int(bad.sum())
    out["latitude"], out["longitude"] = lat.where(ok), lon.where(ok)

    # classificação: preenche ausências a partir das contagens
    cls = out["classificacao_acidente"] if "classificacao_acidente" in out else clean_text(col(raw, "classificacao_acidente"))
    cls = clean_text(col(raw, "classificacao_acidente"))
    derived = pd.Series(np.nan, index=out.index, dtype="object")
    derived[out["feridos"].fillna(0) > 0] = "Com Vítimas Feridas"
    derived[out["mortos"].fillna(0) > 0] = "Com Vítimas Fatais"
    derived[(out["mortos"].fillna(-1) == 0) & (out["feridos"].fillna(-1) == 0)] = "Sem Vítimas"
    fill = cls.isna() & derived.notna()
    stats["ajuste:classificacao_derivada_das_contagens"] += int(fill.sum())
    out["classificacao_acidente"] = cls.where(~fill, derived)
    out["fatal"] = (out["mortos"].fillna(0) > 0).astype("Int8")
    incons = (out["fatal"] == 1) & (out["classificacao_acidente"] != "Com Vítimas Fatais")
    stats["alerta:classificacao_incoerente_com_mortos"] += int(incons.sum())

    n0 = len(out)
    out = out[out["id"].notna()]
    stats["descartado:sem_id"] += n0 - len(out)
    n1 = len(out)
    out = out.drop_duplicates(subset=["id"], keep="last")
    stats["descartado:id_duplicado"] += n1 - len(out)
    return {"ocorrencias": out[OCORRENCIAS.names()]}


def clean_pessoas(raw: pd.DataFrame, stats: Counter) -> dict[str, pd.DataFrame]:
    out = _context(raw, stats)
    pesid = to_int(col(raw, "pesid"))
    idv = to_int(col(raw, "id_veiculo"))
    presente = (pesid.fillna(0) > 0)
    stats["ajuste:linha_de_veiculo_sem_pessoa"] += int((~presente).sum())
    out["pesid"] = pesid.mask(~presente)
    out["id_veiculo"] = idv.mask(idv.fillna(0) <= 0)
    out["pessoa_presente"] = presente.astype("Int8")
    tv = map_unique(clean_text(col(raw, "tipo_veiculo")), std_tipo_veiculo)
    out["tipo_veiculo"] = tv
    out["grupo_veiculo"] = map_unique(tv, grupo_veiculo)
    out["marca"] = clean_text(col(raw, "marca"))
    ano_fab = to_int(col(raw, "ano_fabricacao_veiculo"), "Int64")
    ano_acid = out["data"].dt.year
    zero = ano_fab == 0
    stats["ajuste:ano_fabricacao_zero_(sem_veiculo)_anulado"] += int(zero.fillna(False).sum())
    inval = ano_fab.notna() & ~zero & ((ano_fab < 1900) | (ano_fab > (ano_acid + 1)))
    stats["ajuste:ano_fabricacao_invalido_anulado"] += int(inval.sum())
    ano_fab = ano_fab.mask(inval | zero)
    out["ano_fabricacao_veiculo"] = ano_fab.astype("Int16")
    idade_v = (ano_acid - ano_fab).astype("Float64")
    out["idade_veiculo"] = idade_v.where(idade_v >= 0).astype("Int16")
    out["tipo_envolvido"] = clean_text(col(raw, "tipo_envolvido"))
    out["estado_fisico"] = clean_text(col(raw, "estado_fisico"))
    idade = to_int(col(raw, "idade"), "Int64")
    sentinela = (out["estado_fisico"] == "Não Informado") & (idade == 0)
    stats["ajuste:idade_sentinela_zero_anulada"] += int(sentinela.sum())
    absurda = idade > 110
    stats["ajuste:idade_acima_de_110_anulada"] += int(absurda.fillna(False).sum())
    idade = idade.mask(sentinela | absurda | ~presente)
    out["idade"] = idade.astype("Int16")
    out["sexo"] = clean_text(col(raw, "sexo"))
    for c in ("ilesos", "feridos_leves", "feridos_graves", "mortos"):
        out[c] = to_int(col(raw, c), "Int8")
    out = out[out["id"].notna()]
    n1 = len(out)
    out = out.drop_duplicates(subset=["id", "pesid", "id_veiculo"], keep="last")
    stats["descartado:linha_duplicada"] += n1 - len(out)
    return {"pessoas": out[PESSOAS.names()]}


def clean_causas_tipos(raw: pd.DataFrame, stats: Counter) -> dict[str, pd.DataFrame]:
    """O arquivo 'todas as causas e tipos' repete cada pessoa × causa × tipo.
    Reduzimos às relações distintas (acidente×causa) e (acidente×tipo)."""
    ctx = _context(raw, stats)
    ctx["causa_acidente"] = clean_text(col(raw, "causa_acidente"))
    principal = clean_text(col(raw, "causa_principal")).str.lower().map({"sim": 1, "nao": 0, "não": 0})
    ctx["causa_principal"] = principal.astype("Int8")
    ctx["tipo_acidente"] = clean_text(col(raw, "tipo_acidente"))
    ctx["ordem_tipo_acidente"] = to_int(col(raw, "ordem_tipo_acidente"), "Int8")
    ctx = ctx[ctx["id"].notna()]
    causas = (ctx[["id", "data", "ano_mes", "uf", "causa_acidente", "causa_principal"]]
              .dropna(subset=["causa_acidente"]).drop_duplicates())
    causas = (causas.sort_values("causa_principal", ascending=False, na_position="last")
              .drop_duplicates(subset=["id", "causa_acidente"], keep="first"))
    tipos = (ctx[["id", "data", "ano_mes", "uf", "ordem_tipo_acidente", "tipo_acidente"]]
             .dropna(subset=["tipo_acidente"]).drop_duplicates()
             .drop_duplicates(subset=["id", "tipo_acidente", "ordem_tipo_acidente"], keep="first"))
    return {"causas": causas[CAUSAS.names()], "tipos": tipos[TIPOS.names()]}


def clean_infracoes(raw: pd.DataFrame, stats: Counter) -> dict[str, pd.DataFrame]:
    out = pd.DataFrame(index=raw.index)
    if "auto" in raw.columns:
        out["auto"] = clean_text(col(raw, "auto"))
    else:  # layout antigo (dicionário de 2016) não traz número do auto: chave sintética por posição no arquivo
        out["auto"] = "linha-" + raw.index.astype(str)
        stats["info:chave_sintetica_do_auto_(layout_antigo)"] += len(raw)
    data = parse_dates(col(raw, "data"))
    stats["ajuste:data_invalida_ou_ausente"] += int(data.isna().sum())
    out["data"] = data
    out["ano_mes"] = data.dt.strftime("%Y-%m")
    out["hora"] = _within(to_num(col(raw, "hora")), 0, 23).astype("Int8")
    out["uf"] = clean_text(col(raw, "uf")).str.upper()
    br = to_int(col(raw, "br"), "Int64")
    stats["ajuste:br_zero_convertido_em_nulo"] += int((br == 0).sum())
    out["br"] = br.mask(br == 0).astype("Int16")
    km = to_num(col(raw, "km"))
    out["km"] = km.where(km >= 0)
    out["municipio"] = clean_text(col(raw, "municipio"))
    out["sentido"] = clean_text(col(raw, "sentido")).str.upper().where(lambda s: s.isin(["C", "D"]))
    ab = clean_text(col(raw, "abordagem")).str.upper().map({"C": 1, "S": 0})
    out["abordagem"] = ab.astype("Int8")

    # 'Indicador Veiculo Estrangeiro' traz, nos arquivos atuais, o código do país
    # da placa (BR, PY, AR, 99=desconhecido); no dicionário antigo era S/N.
    ind = clean_text(col(raw, "ind_estrangeiro")).str.upper()

    def estrangeiro(v):
        if v in ("N", "BR", "NAO", "NÃO"):
            return 0
        if v in ("S", "SIM"):
            return 1
        if v == "99":
            return np.nan
        return 1 if len(v) == 2 and v.isalpha() else np.nan

    out["veiculo_estrangeiro"] = map_unique(ind, estrangeiro).astype("Int8")
    out["pais_veiculo"] = ind.where(ind.str.fullmatch(r"[A-Z]{2}", na=False))
    out["uf_placa"] = clean_text(col(raw, "uf_placa")).str.upper()
    out["especie_veiculo"] = map_unique(clean_text(col(raw, "especie")), std_especie)
    tv = map_unique(clean_text(col(raw, "tipo_veiculo")), std_tipo_veiculo)
    out["tipo_veiculo"] = tv
    out["grupo_veiculo"] = map_unique(tv, grupo_veiculo)
    out["marca"] = clean_text(col(raw, "marca"))
    out["modelo"] = clean_text(col(raw, "modelo"))
    out["codigo_infracao"] = to_int(col(raw, "codigo_infracao"), "Int32")
    desc = clean_text(col(raw, "descricao"))
    out["descricao_infracao"] = desc
    out["enquadramento"] = clean_text(col(raw, "enquadramento")).str.lower()
    enq = out["enquadramento"]
    pares = pd.Series(list(zip(desc.astype(object), enq.astype(object))), index=out.index, dtype="object")
    out["grupo_infracao"] = map_unique(pares, grupo_infracao)
    vel = desc.fillna("").map(lambda d: "velocidade superior" in unaccent(d).lower())
    out["excesso_velocidade"] = vel.astype("Int8")
    med = clean_text(col(raw, "medicao_tipo"))
    out["medicao_tipo"] = med.where(~med.str.upper().isin(["N/I", "NI"]))
    # unifica grafias ("CMT GRAVISIMA" / "CMT Gravíssima")
    out["medicao_tipo"] = map_unique(out["medicao_tipo"], lambda v: unaccent(v).upper().replace("GRAVISIMA", "GRAVISSIMA"))
    considerada = to_num(col(raw, "medicao_considerada"))
    excesso = to_num(col(raw, "excesso_verificado"))
    out["medicao_considerada"] = considerada
    out["excesso_verificado"] = excesso
    limite = (considerada - excesso).where(vel & (considerada > 0) & (excesso > 0))
    out["limite_via_kmh"] = limite.where((limite >= 10) & (limite <= 140))
    ass = clean_text(col(raw, "assinatura"))
    stats["info:assinatura_do_auto_nao_informada"] += int((ass.isna() | ass.str.upper().isin(["N/I"])).sum())
    out = out[out["auto"].notna()]
    return {"infracoes": out[INFRACOES.names()]}


CLEANERS = {
    "ocorrencias": clean_ocorrencias,
    "pessoas": clean_pessoas,
    "causas_tipos": clean_causas_tipos,
    "infracoes": clean_infracoes,
}

# --------------------------------------------------------------------------
# Persistência: partições por tabela/mês + manifesto
# --------------------------------------------------------------------------


def _to_csv(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    df.to_csv(path, index=False, compression={"method": "gzip", "mtime": 0},
              date_format="%Y-%m-%d", lineterminator="\n")


class Sink:
    """Grava DataFrames limpos em partições ``<staging>/<tabela>/<período>/``."""

    def __init__(self, staging: Path, tag: str):
        self.staging, self.tag = staging, tag
        self.seq: Counter = Counter()
        self.rows: Counter = Counter()  # (tabela, período) -> linhas

    def write(self, table: str, df: pd.DataFrame) -> None:
        if df.empty:
            return
        periodo = df["ano_mes"].astype("object").fillna("sem-data")
        for per, part in df.groupby(periodo, sort=True):
            self.seq[(table, per)] += 1
            path = self.staging / table / per / f"{self.tag}-{self.seq[(table, per)]:03d}.csv.gz"
            _to_csv(part, path)
            self.rows[(table, per)] += len(part)


def load_manifest(processed: Path) -> dict:
    path = processed / MANIFEST
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return {"schema_version": SCHEMA_VERSION, "ingestions": []}


def save_manifest(processed: Path, manifest: dict) -> None:
    processed.mkdir(parents=True, exist_ok=True)
    (processed / MANIFEST).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2, sort_keys=False), encoding="utf-8")


def ingest_file(path: Path, processed: Path = PROCESSED_DIR, manifest: dict | None = None) -> dict | None:
    """Ingere um CSV bruto. Retorna o registro do manifesto (ou None se já ingerido/ignorado)."""
    manifest = manifest if manifest is not None else load_manifest(processed)
    digest = sha256_file(path)
    if any(i["sha256"] == digest for i in manifest["ingestions"]):
        log.info("• %s: já ingerido (sha256 conhecido) — ignorado", path.name)
        return None
    enc = sniff_encoding(path)
    delim = sniff_delimiter(path, enc)
    kind = detect_kind(read_header(path, enc, delim))
    if kind is None:
        log.warning("• %s: cabeçalho não reconhecido — arquivo ignorado", path.name)
        return None
    log.info("• %s: tipo=%s encoding=%s separador=%r", path.name, kind, enc, delim)

    tag = digest[:8]
    staging = processed / "_staging" / tag
    if staging.exists():
        shutil.rmtree(staging)
    sink = Sink(staging, tag)
    stats: Counter = Counter()
    cleaner = CLEANERS[kind]
    acc: dict[str, list[pd.DataFrame]] = {}
    seen_hashes = np.array([], dtype="uint64")
    for chunk in read_raw_chunks(path, enc, delim, kind):
        stats["linhas_lidas"] += len(chunk)
        tables = cleaner(chunk, stats)
        if kind == "infracoes":
            df = tables["infracoes"]
            h = pd.util.hash_pandas_object(df["auto"], index=False).to_numpy()
            dup = np.isin(h, seen_hashes) | pd.Series(h).duplicated().to_numpy()
            stats["descartado:auto_duplicado"] += int(dup.sum())
            seen_hashes = np.concatenate([seen_hashes, h[~dup]])
            sink.write("infracoes", df[~dup])
        else:
            for name, df in tables.items():
                acc.setdefault(name, []).append(df)
    if kind != "infracoes":
        for name, frames in acc.items():
            df = pd.concat(frames, ignore_index=True)
            df = df.drop_duplicates(subset=list(TABLES[name].keys), keep="last")
            sink.write(name, df)

    # commit: arquiva partições antigas dos mesmos (tabela, período) e move as novas
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    superseded = []
    for (table, per) in sorted(sink.rows):
        dest = processed / table / per
        if dest.exists():
            for old in sorted(dest.glob("*.csv.gz")):
                arch = processed / "_superseded" / table / per / f"{now}-{old.name}"
                arch.parent.mkdir(parents=True, exist_ok=True)
                shutil.move(str(old), arch)
                superseded.append(str(arch.relative_to(processed)))
        dest.mkdir(parents=True, exist_ok=True)
        for new in sorted((staging / table / per).glob("*.csv.gz")):
            shutil.move(str(new), dest / new.name)
    shutil.rmtree(processed / "_staging", ignore_errors=True)

    periods = sorted({per for (_, per) in sink.rows})
    record = {
        "arquivo": path.name,
        "sha256": digest,
        "bytes": path.stat().st_size,
        "tipo": kind,
        "encoding": enc,
        "separador": delim,
        "ingerido_em": now,
        "linhas_lidas": int(stats.pop("linhas_lidas")),
        "linhas_por_tabela": {t: int(sum(n for (tt, _), n in sink.rows.items() if tt == t))
                              for t in sorted({t for (t, _) in sink.rows})},
        "periodos": periods,
        "tratamentos": {k: int(v) for k, v in sorted(stats.items()) if v},
        "particoes_arquivadas": superseded,
    }
    manifest["ingestions"].append(record)
    save_manifest(processed, manifest)
    log.info("  ✓ %s → %s | períodos %s…%s", kind, record["linhas_por_tabela"],
             periods[0] if periods else "-", periods[-1] if periods else "-")
    return record


def run_etl(raw_dir: Path = RAW_DIR, processed: Path = PROCESSED_DIR, rebuild: bool = False) -> dict:
    processed.mkdir(parents=True, exist_ok=True)
    if rebuild:
        log.info("Reconstrução completa: removendo dados derivados em %s", processed)
        for sub in list(TABLES) + ["_staging", "_superseded"]:
            shutil.rmtree(processed / sub, ignore_errors=True)
        (processed / MANIFEST).unlink(missing_ok=True)
    manifest = load_manifest(processed)
    files = sorted(p for p in raw_dir.glob("*") if p.suffix.lower() == ".csv" or p.name.lower().endswith(".csv.gz"))
    if not files:
        log.warning("Nenhum CSV em %s — nada a ingerir (usando o que já existe em %s).", raw_dir, processed)
    for f in files:
        ingest_file(f, processed, manifest)
    return manifest


# --------------------------------------------------------------------------
# Leitura dos dados processados
# --------------------------------------------------------------------------


def list_parts(table: str, processed: Path = PROCESSED_DIR) -> list[Path]:
    manifest = load_manifest(processed)
    order = {i["sha256"][:8]: n for n, i in enumerate(manifest["ingestions"])}
    parts = sorted((processed / table).glob("*/*.csv.gz"))
    return sorted(parts, key=lambda p: (order.get(p.name.split("-")[0], 0), p.parent.name, p.name))


def _read_part(path: Path, spec: Table, columns: list[str] | None) -> pd.DataFrame:
    wanted = columns or spec.names()
    dtypes = {k: v for k, v in spec.dtypes().items() if k in wanted}
    # categorias são lidas como texto e convertidas depois: evita que o parser
    # infira tipos diferentes (int × str) em blocos distintos da mesma coluna.
    cats = [k for k, v in dtypes.items() if v == "category"]
    for k in cats:
        dtypes[k] = "str"
    parse = [c for c in spec.date_cols() if c in wanted]
    df = pd.read_csv(path, usecols=wanted, dtype=dtypes, parse_dates=parse or False, low_memory=False)[wanted]
    for k in cats:
        df[k] = df[k].astype("category")
    return df


def iter_table(table: str, columns: list[str] | None = None, processed: Path = PROCESSED_DIR) -> Iterator[pd.DataFrame]:
    spec = TABLES[table]
    for part in list_parts(table, processed):
        yield _read_part(part, spec, columns)


def read_table(table: str, columns: list[str] | None = None, processed: Path = PROCESSED_DIR) -> pd.DataFrame:
    """Lê todas as partições de uma tabela (mantém dtype 'category' unindo categorias)."""
    spec = TABLES[table]
    frames = list(iter_table(table, columns, processed))
    if not frames:
        return pd.DataFrame(columns=columns or spec.names())
    for c in frames[0].columns:
        if isinstance(frames[0][c].dtype, pd.CategoricalDtype):
            cats = pd.api.types.union_categoricals([f[c] for f in frames], sort_categories=True).categories
            dtype = pd.CategoricalDtype(cats)
            frames = [f.assign(**{c: f[c].astype(dtype)}) for f in frames]
    df = pd.concat(frames, ignore_index=True)
    keys = [k for k in spec.keys if k in df.columns]
    if keys and len(keys) == len(spec.keys) and table != "infracoes":
        df = df.drop_duplicates(subset=keys, keep="last", ignore_index=True)
    return df


# --------------------------------------------------------------------------
# Dicionário de dados (gerado a partir de schemas.py)
# --------------------------------------------------------------------------

_DTYPE_LABEL = {
    "Int64": "inteiro (anulável)", "Int32": "inteiro (anulável)", "Int16": "inteiro (anulável)",
    "Int8": "inteiro pequeno (anulável)", "float64": "decimal", "category": "categórico (texto)",
    "string": "texto", "date": "data",
}


def build_dictionary(path: Path | None = None) -> str:
    lines = [
        "# Dicionário de dados — tabelas processadas",
        "",
        "> Gerado automaticamente por `python -m src.etl --dictionary` a partir de `src/schemas.py`.",
        "> Não edite este arquivo à mão: altere o esquema e gere novamente.",
        "",
        "Fonte primária: dados abertos da Polícia Rodoviária Federal (PRF) — ver `README.md`.",
        "Valores ausentes são gravados como campo vazio nos `.csv.gz`. Datas em ISO 8601 (AAAA-MM-DD).",
        "Codificação UTF-8, separador vírgula, ponto como separador decimal.",
        "Cada tabela é particionada por mês: `data/processed/<tabela>/<AAAA-MM>/*.csv.gz`.",
        "",
        "## Tabelas",
        "",
        "| Tabela | Granularidade | Chave lógica | Arquivo bruto de origem |",
        "|---|---|---|---|",
    ]
    origem = {"ocorrencias": "`datatran*.csv` (acidentes por ocorrência)",
              "pessoas": "`acidentes*.csv` (por pessoa × veículo)",
              "causas": "`acidentes*_todas_causas_tipos.csv`",
              "tipos": "`acidentes*_todas_causas_tipos.csv`",
              "infracoes": "`infra*.csv` (autos de infração)"}
    for t in TABLES.values():
        lines.append(f"| `{t.name}` | {t.grain} | {', '.join(f'`{k}`' for k in t.keys)} | {origem[t.name]} |")
    for t in TABLES.values():
        lines += ["", f"## `{t.name}` — {t.title}", "", f"**Granularidade:** {t.grain}.", "",
                  "| Variável | Tipo | Formato / domínio | Significado | Origem no bruto |",
                  "|---|---|---|---|---|"]
        for c in t.cols:
            lines.append(f"| `{c.name}` | {_DTYPE_LABEL[c.dtype]} | {c.fmt} | {c.desc} | {c.origin} |")
    lines += [
        "",
        "## Regras de tratamento aplicadas (todas contabilizadas em `data/processed/manifest.json`)",
        "",
        "| Regra | Justificativa |",
        "|---|---|",
        "| Cabeçalhos normalizados (sem acentos, minúsculos) e mapeados por *alias* (layout novo e antigo). | Permite ingerir anos diferentes sem configuração. |",
        "| Encoding detectado (UTF-8 → CP1252 → Latin-1) e separador detectado pelo cabeçalho. | Arquivos da PRF variam entre anos. |",
        "| Vírgula decimal e notação científica (`8e+05` → 800000) convertidas em número. | Identificadores corrompidos por exportação com notação científica. |",
        "| `br = 0` → nulo. | 0 não é uma rodovia; indica local não informado. |",
        "| Coordenadas fora do retângulo do Brasil (ou 0,0) → nulas. | Erros de digitação/troca de sinal. |",
        "| `classificacao_acidente` ausente → derivada de `mortos`/`feridos`. | Registros recentes ainda sem classificação final. |",
        "| `pesid = 0` → `pesid` nulo e `pessoa_presente = 0`. | Linha descreve só o veículo (sem pessoa registrada). |",
        "| `idade`: nula se > 110, se não há pessoa, ou se `estado_fisico = 'Não Informado'` com idade 0 (sentinela). | Valores impossíveis/sentinelas distorceriam médias. |",
        "| `ano_fabricacao_veiculo` nulo se 0, < 1900 ou > ano do acidente + 1. | Sentinelas e erros de digitação. |",
        "| Indicador de veículo estrangeiro: `BR`→0, `99`→nulo, outro código de país→1. | O campo traz o código do país, divergindo do dicionário PRF de 2016 (S/N). |",
        "| Velocidade: `limite_via_kmh = medicao_considerada − excesso_verificado`, aceito se entre 10 e 140. | Reconstrói o limite da via; valores fora da faixa são tratados como inconsistentes. |",
        "| Duplicatas removidas pela chave lógica de cada tabela; a contagem fica no manifesto. | Idempotência e consistência. |",
        "| Nenhum registro é descartado por valor inválido de atributo — o valor é anulado, não a linha (exceto linhas sem chave). | Evita viés de seleção e perda silenciosa. |",
        "",
        "## Limitações conhecidas da fonte",
        "",
        "* `ignorados` não é aditivo: em parte das ocorrências, `mortos + feridos + ilesos + ignorados ≠ pessoas`.",
        "* `idade = 0` pode representar tanto menores de 1 ano quanto idade desconhecida em pessoas com estado físico informado; esses valores foram mantidos.",
        "* `assinatura do auto` vem como 'N/I' em todos os registros de infração e não é carregada.",
        "* `início/fim de vigência` das infrações vêm vazios nos arquivos atuais e não são carregados.",
        "* Os arquivos de infrações e de acidentes podem cobrir períodos diferentes; as análises que os cruzam usam apenas os meses em comum.",
        "",
    ]
    text = "\n".join(lines)
    if path:
        path.write_text(text, encoding="utf-8")
    return text


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description="ETL dos dados abertos da PRF")
    ap.add_argument("--raw-dir", type=Path, default=RAW_DIR)
    ap.add_argument("--processed-dir", type=Path, default=PROCESSED_DIR)
    ap.add_argument("--rebuild", action="store_true", help="apaga os dados derivados e reprocessa tudo")
    ap.add_argument("--dictionary", action="store_true", help="apenas regenera data/data_dictionary.md")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if args.dictionary:
        build_dictionary(ROOT / "data" / "data_dictionary.md")
        log.info("data/data_dictionary.md atualizado")
        return 0
    run_etl(args.raw_dir, args.processed_dir, args.rebuild)
    build_dictionary(ROOT / "data" / "data_dictionary.md")
    return 0


if __name__ == "__main__":
    sys.exit(main())

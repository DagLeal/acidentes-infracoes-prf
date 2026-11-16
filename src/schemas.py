"""Esquemas das tabelas processadas.

Este módulo é a *fonte única da verdade* sobre as tabelas produzidas pelo ETL:
é usado (i) para ler os arquivos processados com os tipos corretos e
(ii) para gerar automaticamente ``data/data_dictionary.md`` (princípio FAIR
"Interoperable"), de modo que código e documentação nunca divergem.
"""
from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Col:
    name: str          # nome da coluna na tabela processada
    dtype: str         # Int64 | Int8 | float64 | category | string | date
    desc: str          # significado de negócio/pesquisa
    fmt: str           # formato / domínio de valores
    origin: str        # coluna(s) de origem nos CSVs brutos (ou "derivada")


@dataclass(frozen=True)
class Table:
    name: str
    title: str
    grain: str         # granularidade (o que representa cada linha)
    source_kind: str   # tipo de CSV bruto que alimenta a tabela
    keys: tuple        # chave primária lógica
    cols: tuple

    def dtypes(self) -> dict:
        out = {}
        for c in self.cols:
            if c.dtype == "date":
                continue
            out[c.name] = c.dtype
        return out

    def date_cols(self) -> list:
        return [c.name for c in self.cols if c.dtype == "date"]

    def names(self) -> list:
        return [c.name for c in self.cols]


_CTX = (
    Col("id", "Int64", "Identificador único da ocorrência (acidente) atribuído pela PRF.", "inteiro", "id"),
    Col("data", "date", "Data da ocorrência.", "AAAA-MM-DD", "data_inversa"),
    Col("ano_mes", "category", "Período (ano-mês) da ocorrência; também é a chave de partição dos arquivos.", "AAAA-MM", "derivada de data_inversa"),
    Col("uf", "category", "Unidade da Federação onde ocorreu o acidente.", "sigla de 2 letras", "uf"),
)

OCORRENCIAS = Table(
    name="ocorrencias",
    title="Ocorrências (acidentes) — uma linha por acidente",
    grain="1 linha = 1 acidente registrado pela PRF (arquivo 'datatran')",
    source_kind="ocorrencias",
    keys=("id",),
    cols=_CTX + (
        Col("ano", "Int16", "Ano da ocorrência.", "AAAA", "derivada de data_inversa"),
        Col("mes", "Int8", "Mês da ocorrência.", "1–12", "derivada de data_inversa"),
        Col("dia_semana", "category", "Dia da semana da ocorrência.", "segunda-feira … domingo", "dia_semana"),
        Col("hora", "Int8", "Hora cheia (0–23) do registro do acidente.", "0–23", "derivada de horario"),
        Col("br", "Int16", "Número da BR (rodovia federal). Valor 0 do bruto vira nulo.", "inteiro (ex.: 101)", "br"),
        Col("km", "float64", "Quilômetro da rodovia onde ocorreu o acidente.", "decimal, ≥ 0 (ponto como separador)", "km"),
        Col("municipio", "category", "Município do acidente (caixa alta, sem acentos, como na fonte).", "texto", "municipio"),
        Col("causa_acidente", "category", "Causa principal atribuída ao acidente.", "texto (≈70 categorias)", "causa_acidente"),
        Col("tipo_acidente", "category", "Tipo do acidente (colisão traseira, tombamento etc.).", "texto (≈17 categorias)", "tipo_acidente"),
        Col("classificacao_acidente", "category", "Gravidade: Sem Vítimas, Com Vítimas Feridas ou Com Vítimas Fatais. Quando ausente na fonte, é derivada das contagens de mortos/feridos.", "3 categorias", "classificacao_acidente (+ derivação)"),
        Col("fase_dia", "category", "Fase do dia: Amanhecer, Pleno dia, Anoitecer, Plena Noite.", "4 categorias", "fase_dia"),
        Col("sentido_via", "category", "Sentido da via (Crescente/Decrescente/Não Informado).", "3 categorias", "sentido_via"),
        Col("condicao_meteorologica", "category", "Condição meteorológica no momento (grafia corrigida: a fonte usa 'condicao_metereologica').", "texto", "condicao_metereologica"),
        Col("tipo_pista", "category", "Tipo de pista: Simples, Dupla ou Múltipla.", "3 categorias", "tipo_pista"),
        Col("tracado_via", "category", "Traçado da via (reta, curva, aclive, declive, interseção; pode combinar valores separados por ';').", "texto", "tracado_via"),
        Col("area_urbana", "Int8", "1 se o trecho é urbano; 0 se rural (variável 'uso_solo' da PRF: Sim = urbano).", "0/1", "uso_solo"),
        Col("pessoas", "Int16", "Total de pessoas envolvidas no acidente.", "inteiro ≥ 1", "pessoas"),
        Col("mortos", "Int16", "Número de mortos.", "inteiro ≥ 0", "mortos"),
        Col("feridos_leves", "Int16", "Número de feridos leves.", "inteiro ≥ 0", "feridos_leves"),
        Col("feridos_graves", "Int16", "Número de feridos graves.", "inteiro ≥ 0", "feridos_graves"),
        Col("feridos", "Int16", "Feridos leves + feridos graves.", "inteiro ≥ 0", "feridos"),
        Col("ilesos", "Int16", "Número de ilesos.", "inteiro ≥ 0", "ilesos"),
        Col("ignorados", "Int16", "Número de pessoas com estado físico ignorado (na fonte, a soma mortos+feridos+ilesos+ignorados nem sempre é igual a 'pessoas').", "inteiro ≥ 0", "ignorados"),
        Col("veiculos", "Int16", "Número de veículos envolvidos.", "inteiro ≥ 1", "veiculos"),
        Col("latitude", "float64", "Latitude (graus decimais). Nula se fora do retângulo do Brasil.", "decimal, −34 a 6", "latitude"),
        Col("longitude", "float64", "Longitude (graus decimais). Nula se fora do retângulo do Brasil.", "decimal, −75 a −33", "longitude"),
        Col("regional", "category", "Superintendência regional da PRF (SPRF-UF).", "texto", "regional"),
        Col("delegacia", "category", "Delegacia da PRF responsável.", "texto", "delegacia"),
        Col("uop", "category", "Unidade operacional da PRF.", "texto", "uop"),
        Col("fatal", "Int8", "1 se houve ao menos um morto no acidente.", "0/1", "derivada de mortos"),
    ),
)

PESSOAS = Table(
    name="pessoas",
    title="Pessoas e veículos envolvidos — uma linha por pessoa×veículo",
    grain="1 linha = 1 pessoa em 1 veículo (ou 1 veículo sem pessoa registrada) dentro de um acidente",
    source_kind="pessoas",
    keys=("id", "pesid", "id_veiculo"),
    cols=(
        Col("id", "Int64", "Identificador da ocorrência (chave estrangeira para 'ocorrencias').", "inteiro", "id"),
        Col("pesid", "Int64", "Identificador da pessoa. Nulo quando a linha descreve apenas o veículo (valor 0 na fonte).", "inteiro", "pesid"),
        Col("id_veiculo", "Int64", "Identificador do veículo. Nulo se não informado (0 na fonte).", "inteiro", "id_veiculo"),
        Col("data", "date", "Data da ocorrência.", "AAAA-MM-DD", "data_inversa"),
        Col("ano_mes", "category", "Período (ano-mês); chave de partição.", "AAAA-MM", "derivada de data_inversa"),
        Col("uf", "category", "UF do acidente.", "sigla de 2 letras", "uf"),
        Col("pessoa_presente", "Int8", "1 se a linha descreve uma pessoa; 0 se apenas o veículo (pesid = 0 na fonte).", "0/1", "derivada de pesid"),
        Col("tipo_veiculo", "category", "Tipo do veículo (Automóvel, Motocicleta etc.). Nulo para pedestres.", "texto", "tipo_veiculo"),
        Col("grupo_veiculo", "category", "Agrupamento de tipo_veiculo: Automóvel e utilitários, Motocicletas, Caminhões e reboques, Ônibus, Bicicletas, Outros.", "6 categorias", "derivada de tipo_veiculo"),
        Col("marca", "string", "Marca/modelo do veículo conforme registro.", "texto livre", "marca"),
        Col("ano_fabricacao_veiculo", "Int16", "Ano de fabricação. Nulo se 0, < 1900 ou posterior ao ano do acidente + 1.", "AAAA", "ano_fabricacao_veiculo"),
        Col("idade_veiculo", "Int16", "Idade do veículo no ano do acidente (ano do acidente − ano de fabricação).", "anos ≥ 0", "derivada"),
        Col("tipo_envolvido", "category", "Condutor, Passageiro, Pedestre, Testemunha ou Cavaleiro.", "texto", "tipo_envolvido"),
        Col("estado_fisico", "category", "Estado físico: Ileso, Lesões Leves, Lesões Graves, Óbito ou Não Informado.", "texto", "estado_fisico"),
        Col("idade", "Int16", "Idade da pessoa em anos. Nula se não há pessoa, se > 110 ou se o estado físico é 'Não Informado' (0 era valor-sentinela).", "0–110", "idade"),
        Col("sexo", "category", "Masculino, Feminino, Não Informado ou Ignorado.", "texto", "sexo"),
        Col("ilesos", "Int8", "1 se a pessoa saiu ilesa.", "0/1", "ilesos"),
        Col("feridos_leves", "Int8", "1 se ferida levemente.", "0/1", "feridos_leves"),
        Col("feridos_graves", "Int8", "1 se ferida gravemente.", "0/1", "feridos_graves"),
        Col("mortos", "Int8", "1 se faleceu.", "0/1", "mortos"),
    ),
)

CAUSAS = Table(
    name="causas",
    title="Causas por acidente — todas as causas registradas",
    grain="1 linha = 1 causa registrada em 1 acidente (um acidente pode ter várias causas)",
    source_kind="causas_tipos",
    keys=("id", "causa_acidente"),
    cols=(
        Col("id", "Int64", "Identificador da ocorrência.", "inteiro", "id"),
        Col("data", "date", "Data da ocorrência.", "AAAA-MM-DD", "data_inversa"),
        Col("ano_mes", "category", "Período (ano-mês); chave de partição.", "AAAA-MM", "derivada de data_inversa"),
        Col("uf", "category", "UF do acidente.", "sigla de 2 letras", "uf"),
        Col("causa_acidente", "category", "Causa registrada (principal ou concorrente).", "texto", "causa_acidente"),
        Col("causa_principal", "Int8", "1 se é a causa principal do acidente; 0 se é causa concorrente.", "0/1", "causa_principal (Sim/Não)"),
    ),
)

TIPOS = Table(
    name="tipos",
    title="Tipos por acidente — todos os tipos registrados",
    grain="1 linha = 1 tipo de acidente registrado em 1 acidente, na ordem em que ocorreu",
    source_kind="causas_tipos",
    keys=("id", "tipo_acidente", "ordem_tipo_acidente"),
    cols=(
        Col("id", "Int64", "Identificador da ocorrência.", "inteiro", "id"),
        Col("data", "date", "Data da ocorrência.", "AAAA-MM-DD", "data_inversa"),
        Col("ano_mes", "category", "Período (ano-mês); chave de partição.", "AAAA-MM", "derivada de data_inversa"),
        Col("uf", "category", "UF do acidente.", "sigla de 2 letras", "uf"),
        Col("ordem_tipo_acidente", "Int8", "Ordem do tipo na sequência do acidente (1 = primeiro evento).", "inteiro ≥ 1", "ordem_tipo_acidente"),
        Col("tipo_acidente", "category", "Tipo do acidente naquela posição da sequência.", "texto", "tipo_acidente"),
    ),
)

INFRACOES = Table(
    name="infracoes",
    title="Infrações de trânsito autuadas pela PRF — uma linha por auto",
    grain="1 linha = 1 auto de infração (campo 'Qtd Infrações' é sempre 1 na fonte)",
    source_kind="infracoes",
    keys=("auto",),
    cols=(
        Col("auto", "string", "Identificador anonimizado (hash) do auto de infração.", "texto hexadecimal", "Número do Auto"),
        Col("data", "date", "Data da infração.", "AAAA-MM-DD", "Data da Infração / dat_infracao"),
        Col("ano_mes", "category", "Período (ano-mês); chave de partição.", "AAAA-MM", "derivada de data"),
        Col("hora", "Int8", "Hora cheia da infração.", "0–23", "Hora Infração"),
        Col("uf", "category", "UF onde ocorreu a infração.", "sigla de 2 letras", "UF Infração / uf_infracao"),
        Col("br", "Int16", "Número da BR da infração (0 vira nulo).", "inteiro", "BR Infração / num_br_infracao"),
        Col("km", "float64", "Quilômetro da infração.", "decimal ≥ 0", "Km Infração / num_km_infracao"),
        Col("municipio", "category", "Município da infração.", "texto", "Município / nom_municipio"),
        Col("sentido", "category", "Sentido da via: C = crescente, D = decrescente.", "C/D", "Sentido Trafego / ind_sentido_trafego"),
        Col("abordagem", "Int8", "1 se houve abordagem do veículo (C na fonte); 0 se não (S). Conforme dicionário PRF.", "0/1", "Indicador de Abordagem / tip_abordagem"),
        Col("veiculo_estrangeiro", "Int8", "1 se o veículo é estrangeiro; 0 se nacional; nulo se desconhecido (código 99).", "0/1", "Indicador Veiculo Estrangeiro"),
        Col("pais_veiculo", "category", "Código do país da placa quando a fonte o informa (BR, PY, AR…).", "código de 2 letras", "Indicador Veiculo Estrangeiro"),
        Col("uf_placa", "category", "UF da placa do veículo.", "sigla de 2 letras", "UF Placa / uf_placa"),
        Col("especie_veiculo", "category", "Espécie do veículo (Passageiro, Carga, Misto…), em formato padronizado.", "texto", "Descrição Especie Veículo / especie"),
        Col("tipo_veiculo", "category", "Tipo do veículo, padronizado com acentos e a mesma grafia da tabela 'pessoas'.", "texto", "Descrição Tipo Veículo"),
        Col("grupo_veiculo", "category", "Agrupamento de tipo_veiculo (mesmas categorias da tabela 'pessoas').", "6 categorias", "derivada de tipo_veiculo"),
        Col("marca", "string", "Marca do veículo.", "texto", "Descrição Marca Veículo / nome_veiculo_marca"),
        Col("modelo", "string", "Modelo do veículo.", "texto", "Descrição Modelo Veiculo / nom_modelo_veiculo"),
        Col("codigo_infracao", "Int32", "Código da infração no CTB/Contran.", "inteiro", "Código da Infração"),
        Col("descricao_infracao", "category", "Descrição abreviada da infração.", "texto", "Descrição Abreviada Infração / descricao_abreviada"),
        Col("enquadramento", "category", "Enquadramento legal no CTB (caixa baixa).", "ex.: art. 218, I", "Enquadramento da Infração / enquadramento"),
        Col("grupo_infracao", "category", "Agrupamento temático da infração, definido pelo artigo do CTB (velocidade, álcool e drogas, cinto/capacete/retenção, distração, manobras e sinalização, documentação, veículo e carga, transporte profissional, outras).", "9 categorias", "derivada de enquadramento e descricao"),
        Col("excesso_velocidade", "Int8", "1 se a infração é por excesso de velocidade (art. 218 do CTB).", "0/1", "derivada de descricao_infracao"),
        Col("medicao_tipo", "category", "Tipo de medição quando há equipamento (PBT, Dimensão, Alcoolemia…); nulo se 'N/I'.", "texto", "Medição Infração / med_realizada"),
        Col("medicao_considerada", "float64", "Medição considerada para o registro da infração. Em infrações de velocidade é a velocidade considerada (km/h); nas demais a unidade depende de medicao_tipo (kg, cm, g/L…). 0 = sem medição.", "numérico ≥ 0", "Medição Considerada / med_considerada"),
        Col("excesso_verificado", "float64", "Excesso verificado sobre o limite. Em infrações de velocidade é o excesso em km/h; nas demais depende de medicao_tipo. 0 = sem medição.", "numérico ≥ 0", "Excesso Verificado / exc_verificado"),
        Col("limite_via_kmh", "float64", "Limite de velocidade implícito (medicao_considerada − excesso_verificado), apenas para infrações de velocidade.", "km/h", "derivada"),
    ),
)

TABLES = {t.name: t for t in (OCORRENCIAS, PESSOAS, CAUSAS, TIPOS, INFRACOES)}

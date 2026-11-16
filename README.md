# Acidentes e fiscalização nas rodovias federais brasileiras (PRF)

> **Quando, por quê e onde?** Análise integrada dos dados abertos da Polícia Rodoviária Federal:
> ocorrências, pessoas envolvidas, todas as causas e tipos de cada acidente e autos de infração.

📄 **Artigo (GitHub Pages):** `https://DagLeal.github.io/acidentes-infracoes-prf/` &nbsp;·&nbsp; 💻 **Código:** MIT &nbsp;·&nbsp; 📚 **Texto e dados derivados:** CC BY 4.0

**Disciplina:** Linguagem de Programação (Python) · **Autores, instituição e semestre:** edite `config.json` (aparecem no artigo).

## Perguntas de pesquisa

| | Pergunta | Bases usadas |
|---|---|---|
| **RQ1** | **Quando?** Como acidentes e letalidade variam por mês, dia e hora? Acidentes noturnos são mais letais, mesmo ajustando por tipo de pista e área urbana/rural? | ocorrências |
| **RQ2** | **Por quê e com quem?** Quais causas (principal × todas as citadas), tipos e perfis de envolvidos se associam a maior gravidade? | ocorrências, pessoas, causas, tipos |
| **RQ3** | **Onde e fiscalização?** A fiscalização acompanha a geografia, o horário e o perfil dos acidentes e das mortes? | infrações × ocorrências × pessoas |

## Início rápido

```bash
git clone https://github.com/DagLeal/acidentes-infracoes-prf.git
cd acidentes-infracoes-prf
python -m venv .venv && source .venv/bin/activate      # Windows: .venv\Scripts\activate
pip install -r requirements.txt                         # versões congeladas (Python 3.12)

# coloque os CSVs da PRF em data/raw/  (ver data/raw/README.md)
python -m src.pipeline                                  # ETL + análise + artigo (docs/index.html)
```

Abra `docs/index.html` no navegador (funciona também por duplo clique, sem servidor).

### ➕ Adicionando mais dados (inclusive de outros anos)

1. Copie os novos CSVs para `data/raw/` — **o tipo de cada arquivo é detectado pelo cabeçalho**, não pelo nome
   (`datatran2025.csv`, `acidentes2024.csv`, `infracoes2026_08.csv`…). Cabeçalhos do layout antigo de infrações
   (dicionário PRF de 2016) também são reconhecidos.
2. Rode `python -m src.pipeline`.

O que acontece: arquivos já ingeridos são ignorados (SHA-256); os novos são limpos e gravados em
`data/processed/<tabela>/<AAAA-MM>/`; se um arquivo cobre um mês que já existia, a partição antiga é
**arquivada** em `data/processed/_superseded/` (nunca apagada); e **todos os números, gráficos e textos do artigo
são recalculados** — séries mensais passam a cobrir os novos anos, ganham o modo “Comparar anos”, e a RQ3 usa
automaticamente os meses em comum entre acidentes e infrações.

> Mantenha em `data/raw/` todos os CSVs que quiser ver no artigo. Para reprocessar tudo do zero: `python -m src.pipeline --rebuild`.

## Estrutura do repositório

```
├── README.md · LICENSE (MIT) · LICENSE-DATA.md (CC BY 4.0) · requirements.txt · config.json
├── data/
│   ├── raw/                     # CSVs originais da PRF (não versionados; ver README interno)
│   ├── processed/               # tabelas tratadas (.csv.gz por tabela/mês) + manifest.json (rastreabilidade)
│   ├── data_dictionary.md       # dicionário gerado a partir de src/schemas.py
│   └── dicionario-de-variaveis-infracoes-PRF-2016.pdf
├── notebooks/analise_exploratoria.ipynb   # EDA: nulos, outliers, distribuições, correlações
├── src/
│   ├── schemas.py   # fonte única dos esquemas (alimenta ETL e dicionário)
│   ├── etl.py       # ingestão incremental, limpeza, partição, manifesto
│   ├── analysis.py  # métricas e testes estatísticos (RQ1–RQ3)
│   ├── figures.py   # figuras estáticas (matplotlib)
│   ├── build_site.py + templates/article.html.j2   # gera o artigo
│   └── pipeline.py  # orquestra tudo
├── tests/test_etl.py            # testes do ETL com dados sintéticos
└── docs/                        # site (GitHub Pages)
    ├── index.html · .nojekyll
    └── assets/ (style.css, app.js, vendor/d3.min.js, figures/, tables/, data/results.json)
```

## Decisões de projeto

* **Detecção por cabeçalho + aliases:** robustez a anos diferentes e a mudanças de layout (ex.: o campo “Indicador Veículo Estrangeiro” hoje traz o código do país, não S/N).
* **Valores inválidos viram nulos, linhas são preservadas** (sem viés de seleção); toda correção é contada no manifesto e listada no artigo (Tabela 2).
* **Escala:** infrações (~785 mil linhas/mês) são lidas em blocos e agregadas partição por partição; um ano inteiro cabe em memória modesta.
* **Gráficos interativos em D3 (local, sem CDN)** e figuras estáticas em matplotlib; o JSON dos resultados é embutido na página, então ela abre offline.
* **Tema visual** inspirado em Hyrule (pergaminho, floresta, ouro, brilho Sheikah) — paleta em `src/theme.py` e `docs/assets/style.css`. Projeto acadêmico sem vínculo com a Nintendo.

## Publicando no GitHub Pages

*Settings → Pages → Source: Deploy from a branch → Branch `main`, pasta `/docs`.*

## Testes

```bash
python -m unittest discover -s tests
```

## Fontes

* PRF — Dados abertos (acidentes): <https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-acidentes>
* PRF — Dados abertos (infrações): <https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-da-prf>
* PRF — *Dicionário de variáveis – Infrações* (set. 2016): `data/dicionario-de-variaveis-infracoes-PRF-2016.pdf`

## Limitações

Dados restritos à rede federal; sem medidas de exposição (tráfego, população); infrações cobrem períodos diferentes dos
acidentes (a RQ3 usa só o período comum); associações não são causais; campo `idade` contém sentinelas. Detalhes no artigo.

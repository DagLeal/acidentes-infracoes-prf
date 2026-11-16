# data/raw — dados brutos da PRF

Coloque aqui os CSVs originais (somente leitura; o ETL nunca os altera). **Basta soltar os arquivos**:
o tipo de cada um é detectado pelo cabeçalho, de modo que arquivos de outros anos entram sem configuração.

| Tipo | Exemplo de nome | Fonte |
|---|---|---|
| Ocorrências (datatran) | `datatran2026.csv` | https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-acidentes |
| Pessoas e veículos | `acidentes2026.csv` | idem |
| Todas as causas e tipos | `acidentes2026_todas_causas_tipos.csv` | idem |
| Infrações | `infracoes2026_07.csv` | https://www.gov.br/prf/pt-br/acesso-a-informacao/dados-abertos/dados-abertos-da-prf |

Depois: `python -m src.pipeline`. Os arquivos são grandes (centenas de MB), por isso estão no `.gitignore`;
o repositório guarda os dados **tratados** em `data/processed/`.

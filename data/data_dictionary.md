# Dicionário de dados — tabelas processadas

> Gerado automaticamente por `python -m src.etl --dictionary` a partir de `src/schemas.py`.
> Não edite este arquivo à mão: altere o esquema e gere novamente.

Fonte primária: dados abertos da Polícia Rodoviária Federal (PRF) — ver `README.md`.
Valores ausentes são gravados como campo vazio nos `.csv.gz`. Datas em ISO 8601 (AAAA-MM-DD).
Codificação UTF-8, separador vírgula, ponto como separador decimal.
Cada tabela é particionada por mês: `data/processed/<tabela>/<AAAA-MM>/*.csv.gz`.

## Tabelas

| Tabela | Granularidade | Chave lógica | Arquivo bruto de origem |
|---|---|---|---|
| `ocorrencias` | 1 linha = 1 acidente registrado pela PRF (arquivo 'datatran') | `id` | `datatran*.csv` (acidentes por ocorrência) |
| `pessoas` | 1 linha = 1 pessoa em 1 veículo (ou 1 veículo sem pessoa registrada) dentro de um acidente | `id`, `pesid`, `id_veiculo` | `acidentes*.csv` (por pessoa × veículo) |
| `causas` | 1 linha = 1 causa registrada em 1 acidente (um acidente pode ter várias causas) | `id`, `causa_acidente` | `acidentes*_todas_causas_tipos.csv` |
| `tipos` | 1 linha = 1 tipo de acidente registrado em 1 acidente, na ordem em que ocorreu | `id`, `tipo_acidente`, `ordem_tipo_acidente` | `acidentes*_todas_causas_tipos.csv` |
| `infracoes` | 1 linha = 1 auto de infração (campo 'Qtd Infrações' é sempre 1 na fonte) | `auto` | `infra*.csv` (autos de infração) |

## `ocorrencias` — Ocorrências (acidentes) — uma linha por acidente

**Granularidade:** 1 linha = 1 acidente registrado pela PRF (arquivo 'datatran').

| Variável | Tipo | Formato / domínio | Significado | Origem no bruto |
|---|---|---|---|---|
| `id` | inteiro (anulável) | inteiro | Identificador único da ocorrência (acidente) atribuído pela PRF. | id |
| `data` | data | AAAA-MM-DD | Data da ocorrência. | data_inversa |
| `ano_mes` | categórico (texto) | AAAA-MM | Período (ano-mês) da ocorrência; também é a chave de partição dos arquivos. | derivada de data_inversa |
| `uf` | categórico (texto) | sigla de 2 letras | Unidade da Federação onde ocorreu o acidente. | uf |
| `ano` | inteiro (anulável) | AAAA | Ano da ocorrência. | derivada de data_inversa |
| `mes` | inteiro pequeno (anulável) | 1–12 | Mês da ocorrência. | derivada de data_inversa |
| `dia_semana` | categórico (texto) | segunda-feira … domingo | Dia da semana da ocorrência. | dia_semana |
| `hora` | inteiro pequeno (anulável) | 0–23 | Hora cheia (0–23) do registro do acidente. | derivada de horario |
| `br` | inteiro (anulável) | inteiro (ex.: 101) | Número da BR (rodovia federal). Valor 0 do bruto vira nulo. | br |
| `km` | decimal | decimal, ≥ 0 (ponto como separador) | Quilômetro da rodovia onde ocorreu o acidente. | km |
| `municipio` | categórico (texto) | texto | Município do acidente (caixa alta, sem acentos, como na fonte). | municipio |
| `causa_acidente` | categórico (texto) | texto (≈70 categorias) | Causa principal atribuída ao acidente. | causa_acidente |
| `tipo_acidente` | categórico (texto) | texto (≈17 categorias) | Tipo do acidente (colisão traseira, tombamento etc.). | tipo_acidente |
| `classificacao_acidente` | categórico (texto) | 3 categorias | Gravidade: Sem Vítimas, Com Vítimas Feridas ou Com Vítimas Fatais. Quando ausente na fonte, é derivada das contagens de mortos/feridos. | classificacao_acidente (+ derivação) |
| `fase_dia` | categórico (texto) | 4 categorias | Fase do dia: Amanhecer, Pleno dia, Anoitecer, Plena Noite. | fase_dia |
| `sentido_via` | categórico (texto) | 3 categorias | Sentido da via (Crescente/Decrescente/Não Informado). | sentido_via |
| `condicao_meteorologica` | categórico (texto) | texto | Condição meteorológica no momento (grafia corrigida: a fonte usa 'condicao_metereologica'). | condicao_metereologica |
| `tipo_pista` | categórico (texto) | 3 categorias | Tipo de pista: Simples, Dupla ou Múltipla. | tipo_pista |
| `tracado_via` | categórico (texto) | texto | Traçado da via (reta, curva, aclive, declive, interseção; pode combinar valores separados por ';'). | tracado_via |
| `area_urbana` | inteiro pequeno (anulável) | 0/1 | 1 se o trecho é urbano; 0 se rural (variável 'uso_solo' da PRF: Sim = urbano). | uso_solo |
| `pessoas` | inteiro (anulável) | inteiro ≥ 1 | Total de pessoas envolvidas no acidente. | pessoas |
| `mortos` | inteiro (anulável) | inteiro ≥ 0 | Número de mortos. | mortos |
| `feridos_leves` | inteiro (anulável) | inteiro ≥ 0 | Número de feridos leves. | feridos_leves |
| `feridos_graves` | inteiro (anulável) | inteiro ≥ 0 | Número de feridos graves. | feridos_graves |
| `feridos` | inteiro (anulável) | inteiro ≥ 0 | Feridos leves + feridos graves. | feridos |
| `ilesos` | inteiro (anulável) | inteiro ≥ 0 | Número de ilesos. | ilesos |
| `ignorados` | inteiro (anulável) | inteiro ≥ 0 | Número de pessoas com estado físico ignorado (na fonte, a soma mortos+feridos+ilesos+ignorados nem sempre é igual a 'pessoas'). | ignorados |
| `veiculos` | inteiro (anulável) | inteiro ≥ 1 | Número de veículos envolvidos. | veiculos |
| `latitude` | decimal | decimal, −34 a 6 | Latitude (graus decimais). Nula se fora do retângulo do Brasil. | latitude |
| `longitude` | decimal | decimal, −75 a −33 | Longitude (graus decimais). Nula se fora do retângulo do Brasil. | longitude |
| `regional` | categórico (texto) | texto | Superintendência regional da PRF (SPRF-UF). | regional |
| `delegacia` | categórico (texto) | texto | Delegacia da PRF responsável. | delegacia |
| `uop` | categórico (texto) | texto | Unidade operacional da PRF. | uop |
| `fatal` | inteiro pequeno (anulável) | 0/1 | 1 se houve ao menos um morto no acidente. | derivada de mortos |

## `pessoas` — Pessoas e veículos envolvidos — uma linha por pessoa×veículo

**Granularidade:** 1 linha = 1 pessoa em 1 veículo (ou 1 veículo sem pessoa registrada) dentro de um acidente.

| Variável | Tipo | Formato / domínio | Significado | Origem no bruto |
|---|---|---|---|---|
| `id` | inteiro (anulável) | inteiro | Identificador da ocorrência (chave estrangeira para 'ocorrencias'). | id |
| `pesid` | inteiro (anulável) | inteiro | Identificador da pessoa. Nulo quando a linha descreve apenas o veículo (valor 0 na fonte). | pesid |
| `id_veiculo` | inteiro (anulável) | inteiro | Identificador do veículo. Nulo se não informado (0 na fonte). | id_veiculo |
| `data` | data | AAAA-MM-DD | Data da ocorrência. | data_inversa |
| `ano_mes` | categórico (texto) | AAAA-MM | Período (ano-mês); chave de partição. | derivada de data_inversa |
| `uf` | categórico (texto) | sigla de 2 letras | UF do acidente. | uf |
| `pessoa_presente` | inteiro pequeno (anulável) | 0/1 | 1 se a linha descreve uma pessoa; 0 se apenas o veículo (pesid = 0 na fonte). | derivada de pesid |
| `tipo_veiculo` | categórico (texto) | texto | Tipo do veículo (Automóvel, Motocicleta etc.). Nulo para pedestres. | tipo_veiculo |
| `grupo_veiculo` | categórico (texto) | 6 categorias | Agrupamento de tipo_veiculo: Automóvel e utilitários, Motocicletas, Caminhões e reboques, Ônibus, Bicicletas, Outros. | derivada de tipo_veiculo |
| `marca` | texto | texto livre | Marca/modelo do veículo conforme registro. | marca |
| `ano_fabricacao_veiculo` | inteiro (anulável) | AAAA | Ano de fabricação. Nulo se 0, < 1900 ou posterior ao ano do acidente + 1. | ano_fabricacao_veiculo |
| `idade_veiculo` | inteiro (anulável) | anos ≥ 0 | Idade do veículo no ano do acidente (ano do acidente − ano de fabricação). | derivada |
| `tipo_envolvido` | categórico (texto) | texto | Condutor, Passageiro, Pedestre, Testemunha ou Cavaleiro. | tipo_envolvido |
| `estado_fisico` | categórico (texto) | texto | Estado físico: Ileso, Lesões Leves, Lesões Graves, Óbito ou Não Informado. | estado_fisico |
| `idade` | inteiro (anulável) | 0–110 | Idade da pessoa em anos. Nula se não há pessoa, se > 110 ou se o estado físico é 'Não Informado' (0 era valor-sentinela). | idade |
| `sexo` | categórico (texto) | texto | Masculino, Feminino, Não Informado ou Ignorado. | sexo |
| `ilesos` | inteiro pequeno (anulável) | 0/1 | 1 se a pessoa saiu ilesa. | ilesos |
| `feridos_leves` | inteiro pequeno (anulável) | 0/1 | 1 se ferida levemente. | feridos_leves |
| `feridos_graves` | inteiro pequeno (anulável) | 0/1 | 1 se ferida gravemente. | feridos_graves |
| `mortos` | inteiro pequeno (anulável) | 0/1 | 1 se faleceu. | mortos |

## `causas` — Causas por acidente — todas as causas registradas

**Granularidade:** 1 linha = 1 causa registrada em 1 acidente (um acidente pode ter várias causas).

| Variável | Tipo | Formato / domínio | Significado | Origem no bruto |
|---|---|---|---|---|
| `id` | inteiro (anulável) | inteiro | Identificador da ocorrência. | id |
| `data` | data | AAAA-MM-DD | Data da ocorrência. | data_inversa |
| `ano_mes` | categórico (texto) | AAAA-MM | Período (ano-mês); chave de partição. | derivada de data_inversa |
| `uf` | categórico (texto) | sigla de 2 letras | UF do acidente. | uf |
| `causa_acidente` | categórico (texto) | texto | Causa registrada (principal ou concorrente). | causa_acidente |
| `causa_principal` | inteiro pequeno (anulável) | 0/1 | 1 se é a causa principal do acidente; 0 se é causa concorrente. | causa_principal (Sim/Não) |

## `tipos` — Tipos por acidente — todos os tipos registrados

**Granularidade:** 1 linha = 1 tipo de acidente registrado em 1 acidente, na ordem em que ocorreu.

| Variável | Tipo | Formato / domínio | Significado | Origem no bruto |
|---|---|---|---|---|
| `id` | inteiro (anulável) | inteiro | Identificador da ocorrência. | id |
| `data` | data | AAAA-MM-DD | Data da ocorrência. | data_inversa |
| `ano_mes` | categórico (texto) | AAAA-MM | Período (ano-mês); chave de partição. | derivada de data_inversa |
| `uf` | categórico (texto) | sigla de 2 letras | UF do acidente. | uf |
| `ordem_tipo_acidente` | inteiro pequeno (anulável) | inteiro ≥ 1 | Ordem do tipo na sequência do acidente (1 = primeiro evento). | ordem_tipo_acidente |
| `tipo_acidente` | categórico (texto) | texto | Tipo do acidente naquela posição da sequência. | tipo_acidente |

## `infracoes` — Infrações de trânsito autuadas pela PRF — uma linha por auto

**Granularidade:** 1 linha = 1 auto de infração (campo 'Qtd Infrações' é sempre 1 na fonte).

| Variável | Tipo | Formato / domínio | Significado | Origem no bruto |
|---|---|---|---|---|
| `auto` | texto | texto hexadecimal | Identificador anonimizado (hash) do auto de infração. | Número do Auto |
| `data` | data | AAAA-MM-DD | Data da infração. | Data da Infração / dat_infracao |
| `ano_mes` | categórico (texto) | AAAA-MM | Período (ano-mês); chave de partição. | derivada de data |
| `hora` | inteiro pequeno (anulável) | 0–23 | Hora cheia da infração. | Hora Infração |
| `uf` | categórico (texto) | sigla de 2 letras | UF onde ocorreu a infração. | UF Infração / uf_infracao |
| `br` | inteiro (anulável) | inteiro | Número da BR da infração (0 vira nulo). | BR Infração / num_br_infracao |
| `km` | decimal | decimal ≥ 0 | Quilômetro da infração. | Km Infração / num_km_infracao |
| `municipio` | categórico (texto) | texto | Município da infração. | Município / nom_municipio |
| `sentido` | categórico (texto) | C/D | Sentido da via: C = crescente, D = decrescente. | Sentido Trafego / ind_sentido_trafego |
| `abordagem` | inteiro pequeno (anulável) | 0/1 | 1 se houve abordagem do veículo (C na fonte); 0 se não (S). Conforme dicionário PRF. | Indicador de Abordagem / tip_abordagem |
| `veiculo_estrangeiro` | inteiro pequeno (anulável) | 0/1 | 1 se o veículo é estrangeiro; 0 se nacional; nulo se desconhecido (código 99). | Indicador Veiculo Estrangeiro |
| `pais_veiculo` | categórico (texto) | código de 2 letras | Código do país da placa quando a fonte o informa (BR, PY, AR…). | Indicador Veiculo Estrangeiro |
| `uf_placa` | categórico (texto) | sigla de 2 letras | UF da placa do veículo. | UF Placa / uf_placa |
| `especie_veiculo` | categórico (texto) | texto | Espécie do veículo (Passageiro, Carga, Misto…), em formato padronizado. | Descrição Especie Veículo / especie |
| `tipo_veiculo` | categórico (texto) | texto | Tipo do veículo, padronizado com acentos e a mesma grafia da tabela 'pessoas'. | Descrição Tipo Veículo |
| `grupo_veiculo` | categórico (texto) | 6 categorias | Agrupamento de tipo_veiculo (mesmas categorias da tabela 'pessoas'). | derivada de tipo_veiculo |
| `marca` | texto | texto | Marca do veículo. | Descrição Marca Veículo / nome_veiculo_marca |
| `modelo` | texto | texto | Modelo do veículo. | Descrição Modelo Veiculo / nom_modelo_veiculo |
| `codigo_infracao` | inteiro (anulável) | inteiro | Código da infração no CTB/Contran. | Código da Infração |
| `descricao_infracao` | categórico (texto) | texto | Descrição abreviada da infração. | Descrição Abreviada Infração / descricao_abreviada |
| `enquadramento` | categórico (texto) | ex.: art. 218, I | Enquadramento legal no CTB (caixa baixa). | Enquadramento da Infração / enquadramento |
| `grupo_infracao` | categórico (texto) | 9 categorias | Agrupamento temático da infração, definido pelo artigo do CTB (velocidade, álcool e drogas, cinto/capacete/retenção, distração, manobras e sinalização, documentação, veículo e carga, transporte profissional, outras). | derivada de enquadramento e descricao |
| `excesso_velocidade` | inteiro pequeno (anulável) | 0/1 | 1 se a infração é por excesso de velocidade (art. 218 do CTB). | derivada de descricao_infracao |
| `medicao_tipo` | categórico (texto) | texto | Tipo de medição quando há equipamento (PBT, Dimensão, Alcoolemia…); nulo se 'N/I'. | Medição Infração / med_realizada |
| `medicao_considerada` | decimal | numérico ≥ 0 | Medição considerada para o registro da infração. Em infrações de velocidade é a velocidade considerada (km/h); nas demais a unidade depende de medicao_tipo (kg, cm, g/L…). 0 = sem medição. | Medição Considerada / med_considerada |
| `excesso_verificado` | decimal | numérico ≥ 0 | Excesso verificado sobre o limite. Em infrações de velocidade é o excesso em km/h; nas demais depende de medicao_tipo. 0 = sem medição. | Excesso Verificado / exc_verificado |
| `limite_via_kmh` | decimal | km/h | Limite de velocidade implícito (medicao_considerada − excesso_verificado), apenas para infrações de velocidade. | derivada |

## Regras de tratamento aplicadas (todas contabilizadas em `data/processed/manifest.json`)

| Regra | Justificativa |
|---|---|
| Cabeçalhos normalizados (sem acentos, minúsculos) e mapeados por *alias* (layout novo e antigo). | Permite ingerir anos diferentes sem configuração. |
| Encoding detectado (UTF-8 → CP1252 → Latin-1) e separador detectado pelo cabeçalho. | Arquivos da PRF variam entre anos. |
| Vírgula decimal e notação científica (`8e+05` → 800000) convertidas em número. | Identificadores corrompidos por exportação com notação científica. |
| `br = 0` → nulo. | 0 não é uma rodovia; indica local não informado. |
| Coordenadas fora do retângulo do Brasil (ou 0,0) → nulas. | Erros de digitação/troca de sinal. |
| `classificacao_acidente` ausente → derivada de `mortos`/`feridos`. | Registros recentes ainda sem classificação final. |
| `pesid = 0` → `pesid` nulo e `pessoa_presente = 0`. | Linha descreve só o veículo (sem pessoa registrada). |
| `idade`: nula se > 110, se não há pessoa, ou se `estado_fisico = 'Não Informado'` com idade 0 (sentinela). | Valores impossíveis/sentinelas distorceriam médias. |
| `ano_fabricacao_veiculo` nulo se 0, < 1900 ou > ano do acidente + 1. | Sentinelas e erros de digitação. |
| Indicador de veículo estrangeiro: `BR`→0, `99`→nulo, outro código de país→1. | O campo traz o código do país, divergindo do dicionário PRF de 2016 (S/N). |
| Velocidade: `limite_via_kmh = medicao_considerada − excesso_verificado`, aceito se entre 10 e 140. | Reconstrói o limite da via; valores fora da faixa são tratados como inconsistentes. |
| Duplicatas removidas pela chave lógica de cada tabela; a contagem fica no manifesto. | Idempotência e consistência. |
| Nenhum registro é descartado por valor inválido de atributo — o valor é anulado, não a linha (exceto linhas sem chave). | Evita viés de seleção e perda silenciosa. |

## Limitações conhecidas da fonte

* `ignorados` não é aditivo: em parte das ocorrências, `mortos + feridos + ilesos + ignorados ≠ pessoas`.
* `idade = 0` pode representar tanto menores de 1 ano quanto idade desconhecida em pessoas com estado físico informado; esses valores foram mantidos.
* `assinatura do auto` vem como 'N/I' em todos os registros de infração e não é carregada.
* `início/fim de vigência` das infrações vêm vazios nos arquivos atuais e não são carregados.
* Os arquivos de infrações e de acidentes podem cobrir períodos diferentes; as análises que os cruzam usam apenas os meses em comum.

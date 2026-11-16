"""Paleta visual do projeto, inspirada em Hyrule (campos, florestas, ouro e brilho Sheikah).

Fonte única de cores: usada pelas figuras estáticas (matplotlib), pelo CSS e pelos
gráficos D3 do artigo (via variáveis CSS geradas em ``build_site.py``).
"""

PALETTE = {
    # superfícies
    "parchment": "#f3e6c4",      # papel de mapa
    "parchment_dark": "#e4d09b",
    "parchment_deep": "#cdb677",
    "slate": "#0f1f24",          # tablet Sheikah
    "slate_soft": "#17323a",
    "forest": "#1f3b2a",         # floresta
    "forest_mid": "#2f5d3a",
    # destaques
    "moss": "#3f7d3a",           # campo de Hyrule
    "field": "#9bc26b",
    "gold": "#d9a520",           # ouro
    "gold_light": "#f0cf6a",
    "sheikah": "#2fb6c4",        # brilho Sheikah
    "sheikah_soft": "#8fe3ea",
    "ember": "#c4421a",          # Montanha da Perdição
    "ember_dark": "#7d2210",
    "malice": "#5b3a78",         # noite / ameaça
    "ink": "#2a2417",            # texto
    "ink_soft": "#5b523a",
}

# categorias (ordem estável) para gráficos com várias séries
CATEGORICAL = [
    PALETTE["moss"], PALETTE["gold"], PALETTE["sheikah"], PALETTE["ember"],
    PALETTE["malice"], PALETTE["field"], PALETTE["forest_mid"], PALETTE["parchment_deep"],
]

# escala sequencial (pergaminho → ouro → brasa → noite)
SEQUENTIAL = ["#f6ecd0", "#efd98c", "#e0a929", "#c4421a", "#6e1d0f", "#2a0f20"]

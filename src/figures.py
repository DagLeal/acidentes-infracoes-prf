"""Figuras estáticas de alta resolução (matplotlib) — usadas no artigo e no README."""
from __future__ import annotations

from pathlib import Path

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402
import numpy as np  # noqa: E402
import pandas as pd  # noqa: E402
from matplotlib.colors import LinearSegmentedColormap  # noqa: E402

from .theme import PALETTE as P  # noqa: E402
from .theme import SEQUENTIAL  # noqa: E402

CMAP = LinearSegmentedColormap.from_list("hyrule", SEQUENTIAL)
DPI = 200


def _style():
    plt.rcParams.update({
        "figure.facecolor": P["parchment"], "axes.facecolor": P["parchment"], "savefig.facecolor": P["parchment"],
        "axes.edgecolor": P["ink_soft"], "axes.labelcolor": P["ink"], "text.color": P["ink"],
        "xtick.color": P["ink_soft"], "ytick.color": P["ink_soft"], "font.family": "serif",
        "axes.titleweight": "bold", "axes.grid": True, "grid.color": P["parchment_deep"], "grid.alpha": 0.45,
        "grid.linestyle": ":", "axes.spines.top": False, "axes.spines.right": False,
    })


def mapa_densidade(oc: pd.DataFrame, path: Path, periodo: str) -> Path:
    """Densidade de acidentes (hexbin) com os acidentes fatais sobrepostos: a malha viária emerge dos dados."""
    _style()
    d = oc.dropna(subset=["latitude", "longitude"])
    fig, ax = plt.subplots(figsize=(8.2, 8.6))
    hb = ax.hexbin(d["longitude"], d["latitude"], gridsize=95, bins="log", cmap=CMAP, mincnt=1, linewidths=0.0)
    f = d[d["fatal"] == 1]
    ax.scatter(f["longitude"], f["latitude"], s=3.2, c=P["slate"], alpha=0.55, linewidths=0, label=f"Acidentes fatais (n = {len(f):,})".replace(",", "."))
    ax.set_aspect(1 / np.cos(np.deg2rad(15)))
    ax.set_xlabel("Longitude (°)")
    ax.set_ylabel("Latitude (°)")
    ax.set_title(f"Mapa de calor dos acidentes nas rodovias federais\n{periodo} (n = {len(d):,})".replace(",", "."), fontsize=12)
    cb = fig.colorbar(hb, ax=ax, shrink=0.72, pad=0.02)
    cb.set_label("Acidentes por célula (escala log)")
    ax.legend(loc="lower left", frameon=True, facecolor=P["parchment_dark"], edgecolor=P["parchment_deep"])
    fig.text(0.01, 0.005, "Fonte: PRF — dados abertos. Elaboração própria.", fontsize=7, color=P["ink_soft"])
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path


def trechos_scatter(tr: pd.DataFrame, path: Path, periodo: str, rho: float | None) -> Path:
    """Acidentes × infrações por trecho de 10 km (BR × bloco). Densidade em hexbin, escala log–log."""
    _style()
    d = tr[(tr["acidentes"] > 0)].copy()
    d["infracoes"] = d["infracoes"].clip(lower=0.8)  # trechos sem infração aparecem na base do gráfico
    fig, ax = plt.subplots(figsize=(7.4, 5.6))
    hb = ax.hexbin(d["acidentes"], d["infracoes"], xscale="log", yscale="log", gridsize=34, bins="log",
                   cmap=CMAP, mincnt=1, linewidths=0.2, edgecolors=P["parchment"])
    ax.set_xlabel("Acidentes no trecho de 10 km")
    ax.set_ylabel("Infrações no trecho de 10 km")
    sub = f"{periodo} — {len(d):,} trechos com acidentes".replace(",", ".")
    ttl = "Fiscalização e acidentes por trecho"
    if rho is not None:
        sub += " — ρ de Spearman = " + f"{rho:.2f}".replace(".", ",")
    ax.set_title(f"{ttl}\n{sub}", fontsize=11)
    cb = fig.colorbar(hb, ax=ax, pad=0.02)
    cb.set_label("Trechos por célula (escala log)")
    fig.text(0.01, 0.005, "Trechos sem infração registrada aparecem na base do gráfico. Fonte: PRF — dados abertos.", fontsize=7, color=P["ink_soft"])
    fig.tight_layout()
    fig.savefig(path, dpi=DPI)
    plt.close(fig)
    return path

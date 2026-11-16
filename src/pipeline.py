"""Pipeline completo: ETL → análise → artigo HTML.

    python -m src.pipeline            # ingere CSVs novos de data/raw e regenera docs/
    python -m src.pipeline --rebuild  # reprocessa tudo do zero
    python -m src.pipeline --skip-etl # só regenera a análise e o artigo a partir de data/processed
"""
from __future__ import annotations

import argparse
import logging
import sys

from . import etl
from .build_site import build_site


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--rebuild", action="store_true", help="apaga os dados derivados e reprocessa tudo")
    ap.add_argument("--skip-etl", action="store_true", help="pula a ingestão (usa data/processed como está)")
    args = ap.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    if not args.skip_etl:
        etl.run_etl(rebuild=args.rebuild)
        etl.build_dictionary(etl.ROOT / "data" / "data_dictionary.md")
    dest = build_site()
    print(f"✔ Artigo gerado em {dest}")
    return 0


if __name__ == "__main__":
    sys.exit(main())

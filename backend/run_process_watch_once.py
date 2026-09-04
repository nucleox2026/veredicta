from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Executa uma rodada do monitoramento "
            "DataJud sem chamar IA."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=None,
        help=(
            "Limita quantos processos serão consultados. "
            "Útil para teste."
        ),
    )

    args = parser.parse_args()

    backend = Path(__file__).resolve().parent
    sys.path.insert(
        0,
        str(backend),
    )

    from app.db import SessionLocal
    from app.services.datajud_watch_adapter import (
        build_datajud_client,
        fetch_process_from_datajud,
    )
    from app.services.process_watch_worker import (
        run_watch_cycle,
    )

    client = build_datajud_client()

    def fetch(
        tribunal: str,
        numero_processo: str,
    ):
        return fetch_process_from_datajud(
            client,
            tribunal,
            numero_processo,
        )

    with SessionLocal() as db:
        stats = run_watch_cycle(
            db,
            fetch,
            limit=args.limit,
        )

    print(
        json.dumps(
            stats,
            ensure_ascii=False,
            indent=2,
            default=str,
        )
    )

    print()
    print(
        "RODADA DE MONITORAMENTO: OK"
    )
    print(
        "Chamadas automáticas de IA: 0"
    )


if __name__ == "__main__":
    main()

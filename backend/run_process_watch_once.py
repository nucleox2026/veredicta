from __future__ import annotations

import argparse
import json
from pathlib import Path
import sys


DEFAULT_BATCH_SIZE = 3


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Executa uma rodada do monitoramento "
            "DataJud."
        )
    )

    parser.add_argument(
        "--limit",
        type=int,
        default=DEFAULT_BATCH_SIZE,
        help=(
            "Quantidade máxima de processos nesta "
            "rodada. Padrão: 3."
        ),
    )

    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Consulta todos os watches ativos. "
            "Use apenas para diagnóstico."
        ),
    )

    parser.add_argument(
        "--enable-ai",
        action="store_true",
        help=(
            "Permite IA SOMENTE para processos "
            "que já completaram a janela de "
            "10 minutos sem mudança."
        ),
    )

    args = parser.parse_args()

    backend = Path(
        __file__
    ).resolve().parent

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

    analyze_callback = None

    if args.enable_ai:
        from app.settings import (
            get_settings,
        )
        from app.services.process_auto_analysis import (
            analyze_source_and_persist,
        )

        settings = get_settings()

        def analyze_callback(
            db,
            watch,
            source,
        ):
            return analyze_source_and_persist(
                db,
                settings,
                watch.tribunal,
                watch.numero_processo,
                source,
            )

    limit = (
        None
        if args.all
        else args.limit
    )

    with SessionLocal() as db:
        stats = run_watch_cycle(
            db,
            fetch,
            analyze_process=(
                analyze_callback
            ),
            limit=limit,
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

    if args.enable_ai:
        print(
            "IA automática: habilitada "
            "somente para elegíveis."
        )
    else:
        print(
            "Chamadas automáticas de IA: 0 "
            "(use --enable-ai para habilitar)."
        )


if __name__ == "__main__":
    main()

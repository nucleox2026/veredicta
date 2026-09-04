from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import time


DEFAULT_BATCH_SIZE = 3
DEFAULT_INTERVAL_SECONDS = 120


def _env_bool(
    name: str,
    default: bool = False,
) -> bool:
    value = os.getenv(
        name
    )

    if value is None:
        return default

    return value.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
        "sim",
    }


def _env_int(
    name: str,
    default: int,
    minimum: int,
) -> int:
    raw = os.getenv(
        name
    )

    if raw is None:
        return default

    try:
        value = int(
            raw
        )
    except ValueError as exc:
        raise RuntimeError(
            f"{name} deve ser inteiro."
        ) from exc

    if value < minimum:
        raise RuntimeError(
            f"{name} deve ser >= {minimum}."
        )

    return value


def main() -> None:
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

    batch_size = _env_int(
        "AUTO_WATCH_BATCH_SIZE",
        DEFAULT_BATCH_SIZE,
        1,
    )

    interval_seconds = _env_int(
        "AUTO_WATCH_INTERVAL_SECONDS",
        DEFAULT_INTERVAL_SECONDS,
        60,
    )

    ai_enabled = _env_bool(
        "AUTO_ANALYSIS_ENABLED",
        False,
    )

    analyze_callback = None

    if ai_enabled:
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

    print(
        "Veredicta monitor iniciado."
    )
    print(
        f"Lote por rodada: {batch_size}"
    )
    print(
        f"Intervalo: {interval_seconds}s"
    )
    print(
        "IA automática: "
        + (
            "ATIVA"
            if ai_enabled
            else "DESATIVADA"
        )
    )

    while True:
        started = time.time()

        try:
            with SessionLocal() as db:
                stats = run_watch_cycle(
                    db,
                    fetch,
                    analyze_process=(
                        analyze_callback
                    ),
                    limit=batch_size,
                )

            print(
                json.dumps(
                    stats,
                    ensure_ascii=False,
                    default=str,
                ),
                flush=True,
            )

        except Exception as exc:
            print(
                json.dumps(
                    {
                        "evento": (
                            "erro_rodada"
                        ),
                        "erro": (
                            f"{type(exc).__name__}: "
                            f"{exc}"
                        ),
                    },
                    ensure_ascii=False,
                ),
                flush=True,
            )

        elapsed = (
            time.time()
            - started
        )

        sleep_for = max(
            1.0,
            interval_seconds
            - elapsed,
        )

        time.sleep(
            sleep_for
        )


if __name__ == "__main__":
    main()

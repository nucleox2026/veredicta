from __future__ import annotations

import hmac
import json
import os
import threading
from typing import Any, Callable


TOKEN_ENV = "VEREDICTA_MONITOR_TOKEN"
AI_ENABLED_ENV = "AUTO_ANALYSIS_ENABLED"
DEFAULT_BATCH_SIZE = 3

_MONITOR_LOCK = threading.Lock()


def _env_bool(
    name: str,
    default: bool = False,
) -> bool:
    value = os.getenv(name)

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
    minimum: int = 1,
) -> int:
    raw = os.getenv(name)

    if raw is None:
        return default

    try:
        value = int(raw)
    except ValueError as exc:
        raise RuntimeError(
            f"{name} deve ser inteiro."
        ) from exc

    if value < minimum:
        raise RuntimeError(
            f"{name} deve ser >= {minimum}."
        )

    return value


def monitor_token_configured() -> bool:
    expected = os.getenv(
        TOKEN_ENV,
        "",
    ).strip()

    return bool(expected)


def validate_monitor_token(
    provided: str | None,
) -> bool:
    expected = os.getenv(
        TOKEN_ENV,
        "",
    ).strip()

    if not expected:
        return False

    if not provided:
        return False

    return hmac.compare_digest(
        provided.strip(),
        expected,
    )


def monitor_is_running() -> bool:
    return _MONITOR_LOCK.locked()


def _run_real_cycle() -> dict[str, Any]:
    """
    Executa uma rodada real.

    Esta função é chamada apenas no background da API.
    """
    from ..db import SessionLocal
    from ..settings import get_settings
    from .datajud_watch_adapter import (
        build_datajud_client,
        fetch_process_from_datajud,
    )
    from .process_watch_worker import (
        run_watch_cycle,
    )

    batch_size = _env_int(
        "AUTO_WATCH_BATCH_SIZE",
        DEFAULT_BATCH_SIZE,
        1,
    )

    ai_enabled = _env_bool(
        AI_ENABLED_ENV,
        False,
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

    if ai_enabled:
        from .process_auto_analysis import (
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

    with SessionLocal() as db:
        stats = run_watch_cycle(
            db,
            fetch,
            analyze_process=(
                analyze_callback
            ),
            limit=batch_size,
        )

    stats["ia_automatica_habilitada"] = (
        ai_enabled
    )

    return stats


def run_monitor_task(
    runner: Callable[
        [],
        dict[str, Any],
    ] | None = None,
) -> dict[str, Any]:
    """
    Executa uma rodada com trava process-local.

    No plano Free do Render há uma única instância.
    O start command do Veredicta usa um único worker
    Uvicorn, portanto esta trava impede sobreposição
    das chamadas HTTP do agendador externo.

    Se uma rodada ainda estiver em andamento, a nova
    chamada é ignorada. A fila permanece no banco e
    será retomada na próxima execução.
    """
    acquired = _MONITOR_LOCK.acquire(
        blocking=False
    )

    if not acquired:
        result = {
            "status": "ignored",
            "reason": "monitor_already_running",
        }

        print(
            json.dumps(
                result,
                ensure_ascii=False,
            ),
            flush=True,
        )

        return result

    try:
        actual_runner = (
            runner
            if runner is not None
            else _run_real_cycle
        )

        stats = actual_runner()

        result = {
            "status": "ok",
            "stats": stats,
        }

        print(
            json.dumps(
                result,
                ensure_ascii=False,
                default=str,
            ),
            flush=True,
        )

        return result

    except Exception as exc:
        result = {
            "status": "error",
            "error": (
                f"{type(exc).__name__}: "
                f"{exc}"
            ),
        }

        print(
            json.dumps(
                result,
                ensure_ascii=False,
            ),
            flush=True,
        )

        return result

    finally:
        _MONITOR_LOCK.release()

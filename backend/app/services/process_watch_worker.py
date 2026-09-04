from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ProcessWatch
from .process_monitor import observe_process_snapshot
from .process_watch import sync_watches_from_analyses


FetchProcess = Callable[[str, str], dict[str, Any]]


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def run_watch_cycle(
    db: Session,
    fetch_process: FetchProcess,
    *,
    limit: int | None = None,
) -> dict[str, Any]:
    """
    Executa UMA rodada de monitoramento.

    Fluxo:
    1. sincroniza process_watches com process_analyses;
    2. consulta somente watches ativos;
    3. busca o processo na fonte fornecida;
    4. cria baseline ou detecta mudança;
    5. aplica a janela de silêncio de 10 minutos;
    6. persiste o estado.

    IMPORTANTE:
    - não chama IA;
    - não cria ProcessAnalysis;
    - não analisa automaticamente;
    - não consulta processos fora de process_watches.
    """
    created_watches = sync_watches_from_analyses(db)

    stmt = (
        select(ProcessWatch)
        .where(ProcessWatch.ativo.is_(True))
        .order_by(ProcessWatch.id)
    )

    if limit is not None:
        if limit <= 0:
            raise ValueError(
                "limit deve ser maior que zero."
            )
        stmt = stmt.limit(limit)

    watches = list(
        db.scalars(stmt).all()
    )

    stats: dict[str, Any] = {
        "watches_criados": created_watches,
        "monitorados": len(watches),
        "baseline_criada": 0,
        "mudanca_detectada": 0,
        "aguardando": 0,
        "elegiveis_para_ia": 0,
        "sem_mudanca": 0,
        "erros": 0,
        "detalhes": [],
    }

    for watch in watches:
        detail: dict[str, Any] = {
            "tribunal": watch.tribunal,
            "numero_processo": watch.numero_processo,
        }

        try:
            payload = fetch_process(
                watch.tribunal,
                watch.numero_processo,
            )

            if not isinstance(payload, dict):
                raise TypeError(
                    "A consulta do processo deve retornar dict."
                )

            result = observe_process_snapshot(
                watch,
                payload,
            )

            watch.erro_ultimo = None

            if result["baseline_criada"]:
                stats["baseline_criada"] += 1
                detail["evento"] = "baseline_criada"

            elif result["mudanca_detectada"]:
                stats["mudanca_detectada"] += 1
                stats["aguardando"] += 1
                detail["evento"] = "mudanca_detectada"

            elif result["reanalisar_agora"]:
                stats["elegiveis_para_ia"] += 1
                detail["evento"] = "elegivel_para_ia"

            else:
                stats["sem_mudanca"] += 1
                detail["evento"] = "sem_mudanca"

            detail["reanalisar_apos"] = (
                result["reanalisar_apos"].isoformat()
                if result["reanalisar_apos"] is not None
                else None
            )

            db.commit()

        except Exception as exc:
            db.rollback()

            # Recarrega a entidade após rollback e registra o erro,
            # sem desativar o monitoramento.
            current = db.get(
                ProcessWatch,
                watch.id,
            )

            if current is not None:
                current.ultima_verificacao = utc_now()
                current.updated_at = utc_now()
                current.erro_ultimo = (
                    f"{type(exc).__name__}: {exc}"
                )[:2000]
                db.commit()

            stats["erros"] += 1
            detail["evento"] = "erro"
            detail["erro"] = (
                f"{type(exc).__name__}: {exc}"
            )

        stats["detalhes"].append(detail)

    return stats

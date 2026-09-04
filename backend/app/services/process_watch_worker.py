from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timedelta, timezone
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ProcessWatch
from .process_monitor import observe_process_snapshot
from .process_watch import sync_watches_from_analyses


FetchProcess = Callable[
    [str, str],
    dict[str, Any],
]

AnalyzeProcess = Callable[
    [
        Session,
        ProcessWatch,
        dict[str, Any],
    ],
    Any,
]


AI_RETRY_MINUTES = 10

STATUS_MONITORANDO = "monitorando"
STATUS_AGUARDANDO = "aguardando"
STATUS_ANALISANDO = "analisando"


def utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _datetime_timestamp(
    value: datetime | None,
    *,
    none_value: float,
) -> float:
    if value is None:
        return none_value

    if value.tzinfo is None:
        value = value.replace(
            tzinfo=timezone.utc
        )

    return value.timestamp()


def _watch_priority(
    watch: ProcessWatch,
) -> tuple[float, float, int]:
    """
    Ordem da fila:

    1. processos aguardando confirmação da janela;
    2. demais processos;
    3. dentro de cada grupo, quem foi verificado há
       mais tempo vem primeiro.

    Assim, processos aguardando movimento adicional
    são acompanhados de perto sem abandonar a rotação
    dos demais.
    """
    if (
        watch.status
        == STATUS_AGUARDANDO
    ):
        group = 0.0

        deadline = _datetime_timestamp(
            watch.reanalisar_apos,
            none_value=0.0,
        )

        return (
            group,
            deadline,
            int(watch.id or 0),
        )

    group = 1.0

    last_check = _datetime_timestamp(
        watch.ultima_verificacao,
        none_value=0.0,
    )

    return (
        group,
        last_check,
        int(watch.id or 0),
    )


def _select_watches(
    db: Session,
    *,
    limit: int | None,
) -> tuple[list[ProcessWatch], int]:
    watches = list(
        db.scalars(
            select(
                ProcessWatch
            )
            .where(
                ProcessWatch.ativo.is_(
                    True
                )
            )
        ).all()
    )

    total_active = len(
        watches
    )

    watches.sort(
        key=_watch_priority
    )

    if limit is not None:
        if limit <= 0:
            raise ValueError(
                "limit deve ser maior que zero."
            )

        watches = watches[
            :limit
        ]

    return (
        watches,
        total_active,
    )


def _record_monitoring_error(
    db: Session,
    watch_id: int,
    exc: Exception,
) -> None:
    current = db.get(
        ProcessWatch,
        watch_id,
    )

    if current is None:
        return

    now = utc_now()

    current.ultima_verificacao = now
    current.updated_at = now
    current.erro_ultimo = (
        f"{type(exc).__name__}: {exc}"
    )[:2000]

    db.commit()


def _record_ai_failure(
    db: Session,
    watch_id: int,
    exc: Exception,
) -> None:
    current = db.get(
        ProcessWatch,
        watch_id,
    )

    if current is None:
        return

    now = utc_now()

    current.status = (
        STATUS_AGUARDANDO
    )
    current.reanalisar_apos = (
        now
        + timedelta(
            minutes=AI_RETRY_MINUTES
        )
    )
    current.updated_at = now
    current.erro_ultimo = (
        "Falha na análise automática: "
        f"{type(exc).__name__}: {exc}"
    )[:2000]

    db.commit()


def _finish_auto_analysis(
    db: Session,
    watch_id: int,
) -> None:
    current = db.get(
        ProcessWatch,
        watch_id,
    )

    if current is None:
        raise RuntimeError(
            "ProcessWatch desapareceu "
            "durante a análise."
        )

    now = utc_now()

    current.status = (
        STATUS_MONITORANDO
    )
    current.atividade_detectada_em = None
    current.reanalisar_apos = None
    current.ultima_analise_automatica = (
        now
    )
    current.updated_at = now
    current.erro_ultimo = None

    db.commit()


def run_watch_cycle(
    db: Session,
    fetch_process: FetchProcess,
    *,
    analyze_process: AnalyzeProcess | None = None,
    limit: int | None = 3,
) -> dict[str, Any]:
    """
    Executa UMA rodada do monitoramento.

    A fila é rotativa e prioriza processos aguardando.
    O padrão é consultar no máximo 3 processos por
    rodada para reduzir pressão sobre o DataJud.

    analyze_process=None:
    - detecta mudanças;
    - aplica debounce;
    - ZERO chamadas à IA.

    analyze_process fornecido:
    - somente elegíveis após 10 minutos são analisados.
    """
    created_watches = (
        sync_watches_from_analyses(
            db
        )
    )

    (
        watches,
        total_active,
    ) = _select_watches(
        db,
        limit=limit,
    )

    stats: dict[str, Any] = {
        "watches_criados": (
            created_watches
        ),
        "ativos_disponiveis": (
            total_active
        ),
        "monitorados": len(
            watches
        ),
        "baseline_criada": 0,
        "mudanca_detectada": 0,
        "aguardando": 0,
        "elegiveis_para_ia": 0,
        "analisados_automaticamente": 0,
        "sem_mudanca": 0,
        "erros": 0,
        "erros_ia": 0,
        "detalhes": [],
    }

    for watch in watches:
        watch_id = watch.id

        detail: dict[str, Any] = {
            "tribunal": (
                watch.tribunal
            ),
            "numero_processo": (
                watch.numero_processo
            ),
        }

        try:
            payload = fetch_process(
                watch.tribunal,
                watch.numero_processo,
            )

            if not isinstance(
                payload,
                dict,
            ):
                raise TypeError(
                    "A consulta do processo "
                    "deve retornar dict."
                )

            result = (
                observe_process_snapshot(
                    watch,
                    payload,
                )
            )

            watch.erro_ultimo = None

            if result[
                "baseline_criada"
            ]:
                stats[
                    "baseline_criada"
                ] += 1

                detail[
                    "evento"
                ] = "baseline_criada"

                db.commit()

            elif result[
                "mudanca_detectada"
            ]:
                stats[
                    "mudanca_detectada"
                ] += 1

                stats[
                    "aguardando"
                ] += 1

                detail[
                    "evento"
                ] = "mudanca_detectada"

                db.commit()

            elif result[
                "reanalisar_agora"
            ]:
                stats[
                    "elegiveis_para_ia"
                ] += 1

                if analyze_process is None:
                    detail[
                        "evento"
                    ] = "elegivel_para_ia"

                    db.commit()

                else:
                    watch.status = (
                        STATUS_ANALISANDO
                    )
                    watch.updated_at = (
                        utc_now()
                    )
                    db.commit()

                    try:
                        analyze_process(
                            db,
                            watch,
                            payload,
                        )

                        _finish_auto_analysis(
                            db,
                            watch_id,
                        )

                        stats[
                            "analisados_automaticamente"
                        ] += 1

                        detail[
                            "evento"
                        ] = "analisado_automaticamente"

                    except Exception as exc:
                        db.rollback()

                        _record_ai_failure(
                            db,
                            watch_id,
                            exc,
                        )

                        stats[
                            "erros"
                        ] += 1
                        stats[
                            "erros_ia"
                        ] += 1

                        detail[
                            "evento"
                        ] = "erro_ia"

                        detail[
                            "erro"
                        ] = (
                            f"{type(exc).__name__}: "
                            f"{exc}"
                        )

            else:
                stats[
                    "sem_mudanca"
                ] += 1

                detail[
                    "evento"
                ] = "sem_mudanca"

                db.commit()

            current = db.get(
                ProcessWatch,
                watch_id,
            )

            detail[
                "reanalisar_apos"
            ] = (
                current.reanalisar_apos.isoformat()
                if (
                    current is not None
                    and current.reanalisar_apos
                    is not None
                )
                else None
            )

        except Exception as exc:
            db.rollback()

            _record_monitoring_error(
                db,
                watch_id,
                exc,
            )

            stats[
                "erros"
            ] += 1

            detail[
                "evento"
            ] = "erro"

            detail[
                "erro"
            ] = (
                f"{type(exc).__name__}: "
                f"{exc}"
            )

        stats[
            "detalhes"
        ].append(
            detail
        )

    return stats

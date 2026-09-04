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
STALE_ANALYZING_MINUTES = 20

STATUS_MONITORANDO = "monitorando"
STATUS_AGUARDANDO = "aguardando"
STATUS_ANALISANDO = "analisando"


def utc_now() -> datetime:
    return datetime.now(
        timezone.utc
    )


def _aware(
    value: datetime | None,
) -> datetime | None:
    if value is None:
        return None

    if value.tzinfo is None:
        return value.replace(
            tzinfo=timezone.utc
        )

    return value.astimezone(
        timezone.utc
    )


def _timestamp(
    value: datetime | None,
    *,
    none_value: float,
) -> float:
    value = _aware(
        value
    )

    if value is None:
        return none_value

    return value.timestamp()


def _deadline_due(
    watch: ProcessWatch,
    now: datetime,
) -> bool:
    deadline = _aware(
        watch.reanalisar_apos
    )

    return bool(
        watch.status == STATUS_AGUARDANDO
        and deadline is not None
        and deadline <= now
    )


def _watch_priority(
    watch: ProcessWatch,
    now: datetime,
) -> tuple[float, float, float, int]:
    """
    Fila justa por processo.

    Grupo 0:
      aguardando com prazo já vencido.
      Deve confirmar e analisar o quanto antes.

    Grupo 1:
      aguardando, mas ainda dentro dos 10 minutos.
      Rotaciona por ultima_verificacao para que um
      processo movimentado não monopolize a fila.

    Grupo 2:
      monitoramento normal, também rotativo.

    STATUS_ANALISANDO recente é excluído da seleção.
    """
    watch_id = int(
        watch.id or 0
    )

    if _deadline_due(
        watch,
        now,
    ):
        return (
            0.0,
            _timestamp(
                watch.reanalisar_apos,
                none_value=0.0,
            ),
            _timestamp(
                watch.ultima_verificacao,
                none_value=0.0,
            ),
            watch_id,
        )

    if (
        watch.status
        == STATUS_AGUARDANDO
    ):
        return (
            1.0,
            _timestamp(
                watch.ultima_verificacao,
                none_value=0.0,
            ),
            _timestamp(
                watch.reanalisar_apos,
                none_value=0.0,
            ),
            watch_id,
        )

    return (
        2.0,
        _timestamp(
            watch.ultima_verificacao,
            none_value=0.0,
        ),
        0.0,
        watch_id,
    )


def recover_stale_analyzing(
    db: Session,
    *,
    now: datetime | None = None,
    stale_minutes: int = STALE_ANALYZING_MINUTES,
) -> int:
    """
    Recupera watches que ficaram presos em "analisando"
    após queda/restart do processo entre o claim e o
    término da chamada de IA.

    Um watch recente em "analisando" NÃO é tocado.
    """
    if stale_minutes <= 0:
        raise ValueError(
            "stale_minutes deve ser maior que zero."
        )

    now = now or utc_now()

    threshold = (
        now
        - timedelta(
            minutes=stale_minutes
        )
    )

    candidates = list(
        db.scalars(
            select(
                ProcessWatch
            ).where(
                ProcessWatch.ativo.is_(
                    True
                ),
                ProcessWatch.status
                == STATUS_ANALISANDO,
            )
        ).all()
    )

    recovered = 0

    for watch in candidates:
        updated_at = _aware(
            watch.updated_at
        )

        if (
            updated_at is not None
            and updated_at > threshold
        ):
            continue

        watch.status = (
            STATUS_AGUARDANDO
        )
        watch.reanalisar_apos = now
        watch.updated_at = now
        watch.erro_ultimo = (
            "Recuperado automaticamente de "
            "status 'analisando' interrompido."
        )

        recovered += 1

    if recovered:
        db.commit()

    return recovered


def _select_watches(
    db: Session,
    *,
    limit: int | None,
    now: datetime,
) -> tuple[list[ProcessWatch], int]:
    all_active = list(
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
        all_active
    )

    # Watches analisando recentemente não são
    # consultados por outra rodada.
    watches = [
        watch
        for watch in all_active
        if watch.status
        != STATUS_ANALISANDO
    ]

    watches.sort(
        key=lambda watch: (
            _watch_priority(
                watch,
                now,
            )
        )
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

    - lote padrão de 3;
    - fila justa;
    - processos aguardando vencidos têm prioridade;
    - aguardando não vencidos também rotacionam;
    - status analisando interrompido é recuperado
      depois de 20 minutos;
    - analyze_process=None mantém ZERO IA.
    """
    created_watches = (
        sync_watches_from_analyses(
            db
        )
    )

    cycle_now = utc_now()

    recovered = (
        recover_stale_analyzing(
            db,
            now=cycle_now,
        )
    )

    (
        watches,
        total_active,
    ) = _select_watches(
        db,
        limit=limit,
        now=cycle_now,
    )

    stats: dict[str, Any] = {
        "watches_criados": (
            created_watches
        ),
        "ativos_disponiveis": (
            total_active
        ),
        "analisando_recuperados": (
            recovered
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
                    # Claim persistido antes da chamada externa.
                    # Se o processo cair aqui, a próxima rodada
                    # recupera o watch após STALE_ANALYZING_MINUTES.
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
                        ] = (
                            "analisado_automaticamente"
                        )

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

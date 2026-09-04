from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ProcessAnalysis, ProcessWatch


STATUS_MONITORANDO = "monitorando"
STATUS_AGUARDANDO = "aguardando"
STATUS_ANALISANDO = "analisando"
STATUS_ERRO = "erro"


def normalize_tribunal(value: str | None) -> str | None:
    if value is None:
        return None

    normalized = value.strip().upper()
    return normalized or None


def ensure_process_watch(
    db: Session,
    tribunal: str,
    numero_processo: str,
) -> ProcessWatch:
    tribunal = normalize_tribunal(tribunal)

    if not tribunal:
        raise ValueError("Tribunal obrigatório.")

    numero_processo = numero_processo.strip()

    if not numero_processo:
        raise ValueError("Número do processo obrigatório.")

    watch = db.scalar(
        select(ProcessWatch).where(
            ProcessWatch.tribunal == tribunal,
            ProcessWatch.numero_processo == numero_processo,
        )
    )

    if watch is not None:
        return watch

    watch = ProcessWatch(
        tribunal=tribunal,
        numero_processo=numero_processo,
        ativo=True,
        status=STATUS_MONITORANDO,
    )

    db.add(watch)
    db.flush()

    return watch


def sync_watches_from_analyses(db: Session) -> int:
    """
    Garante monitoramento para todo processo persistido
    em process_analyses.

    Não consulta DataJud e não chama IA.
    """
    rows = db.execute(
        select(
            ProcessAnalysis.tribunal,
            ProcessAnalysis.numero_processo,
        ).where(
            ProcessAnalysis.tribunal.is_not(None)
        )
    ).all()

    created = 0

    for tribunal, numero_processo in rows:
        tribunal = normalize_tribunal(tribunal)

        if not tribunal or not numero_processo:
            continue

        numero_processo = numero_processo.strip()

        exists = db.scalar(
            select(ProcessWatch.id).where(
                ProcessWatch.tribunal == tribunal,
                ProcessWatch.numero_processo == numero_processo,
            )
        )

        if exists is not None:
            continue

        db.add(
            ProcessWatch(
                tribunal=tribunal,
                numero_processo=numero_processo,
                ativo=True,
                status=STATUS_MONITORANDO,
            )
        )
        created += 1

    db.commit()
    return created

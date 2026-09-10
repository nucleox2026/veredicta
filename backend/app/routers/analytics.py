from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime, timezone
from statistics import median
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import ProcessAnalysis


router = APIRouter(
    prefix="/api/v1/analytics",
    tags=["analytics"],
)


def _value_cents(analysis: ProcessAnalysis) -> int | None:
    for value in (
        analysis.valor_final_centavos,
        analysis.valor_primeiro_grau_centavos,
        analysis.valor_arbitrado_juiz_centavos,
        analysis.valor_indenizacao_centavos,
    ):
        if value is not None:
            return int(value)
    return None


def _safe_condutas(analysis: ProcessAnalysis) -> list[str]:
    value = analysis.condutas
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _item(analysis: ProcessAnalysis) -> dict[str, Any]:
    return {
        "tribunal": analysis.tribunal,
        "numero_processo": analysis.numero_processo,
        "empresa_re": analysis.empresa_re,
        "empresa_re_normalizada": analysis.empresa_re_normalizada,
        "resultado": analysis.resultado,
        "tem_sentenca": analysis.tem_sentenca,
        "condutas": _safe_condutas(analysis),
        "valor_centavos": _value_cents(analysis),
        "confianca_resultado": analysis.confianca_resultado,
        "confianca_valor": analysis.confianca_valor,
        "lida": bool(analysis.lida),
        "lida_em": analysis.lida_em,
        "analyzed_at": analysis.analyzed_at,
        "capacidade_economica_faixa": analysis.capacidade_economica_faixa,
        "capacidade_economica_fonte": analysis.capacidade_economica_fonte,
        "capacidade_economica_referencia": analysis.capacidade_economica_referencia,
    }


def _company_stats(analyses):
    groups = defaultdict(list)
    display_names = {}

    for analysis in analyses:
        key = analysis.empresa_re_normalizada
        if not key:
            continue

        groups[key].append(analysis)
        display_names.setdefault(key, analysis.empresa_re or key)

    result = []

    for key, rows in groups.items():
        values = [
            value
            for value in (_value_cents(row) for row in rows)
            if value is not None
        ]

        result.append({
            "empresa": display_names[key],
            "empresa_normalizada": key,
            "processos": len(rows),
            "com_sentenca": sum(
                1 for row in rows if row.tem_sentenca is True
            ),
            "valor_medio_centavos": (
                round(sum(values) / len(values)) if values else None
            ),
            "valor_mediano_centavos": (
                round(median(values)) if values else None
            ),
        })

    result.sort(key=lambda item: (-item["processos"], item["empresa"]))
    return result


def _conduct_stats(analyses):
    counter = Counter()
    values_by_conduct = defaultdict(list)

    for analysis in analyses:
        value = _value_cents(analysis)

        for conduct in _safe_condutas(analysis):
            counter[conduct] += 1

            if value is not None:
                values_by_conduct[conduct].append(value)

    result = []

    for conduct, count in counter.most_common():
        values = values_by_conduct[conduct]

        result.append({
            "conduta": conduct,
            "processos": count,
            "valor_mediano_centavos": (
                round(median(values)) if values else None
            ),
        })

    return result


def _capacity_stats(analyses):
    groups = defaultdict(list)
    source_count = 0

    for analysis in analyses:
        faixa = analysis.capacidade_economica_faixa
        fonte = analysis.capacidade_economica_fonte
        value = _value_cents(analysis)

        if not faixa or not fonte:
            continue

        source_count += 1

        if value is not None:
            groups[faixa].append(value)

    rows = []

    for faixa, values in sorted(groups.items()):
        rows.append({
            "faixa": faixa,
            "processos_com_valor": len(values),
            "valor_medio_centavos": (
                round(sum(values) / len(values)) if values else None
            ),
            "valor_mediano_centavos": (
                round(median(values)) if values else None
            ),
        })

    return {
        "registros_com_fonte_objetiva": source_count,
        "grupos": rows,
        "observacao": (
            "Capacidade econômica só é relacionada quando existe "
            "fonte objetiva registrada. O Veredicta não infere porte "
            "econômico pelo nome da empresa."
        ),
    }


@router.get("/analyses")
def list_analyses(
    somente_sentenca: bool = Query(default=False),
    leitura: str = Query(default="todas"),
    empresa: str | None = Query(default=None),
    conduta: str | None = Query(default=None),
    somente_reincidentes: bool = Query(default=False),
    min_reincidencia: int = Query(default=2, ge=2, le=1000),
    limit: int = Query(default=200, ge=1, le=1000),
    offset: int = Query(default=0, ge=0),
    _user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    leitura = (leitura or "todas").lower()

    if leitura not in {"todas", "lidas", "nao_lidas"}:
        raise HTTPException(
            status_code=400,
            detail="Filtro leitura inválido.",
        )

    analyses = list(
        db.scalars(
            select(ProcessAnalysis).order_by(
                ProcessAnalysis.analyzed_at.desc().nullslast(),
                ProcessAnalysis.id.desc(),
            )
        ).all()
    )

    company_counts = Counter(
        analysis.empresa_re_normalizada
        for analysis in analyses
        if analysis.empresa_re_normalizada
    )

    filtered = []

    for analysis in analyses:
        if somente_sentenca and analysis.tem_sentenca is not True:
            continue

        if leitura == "lidas" and not analysis.lida:
            continue

        if leitura == "nao_lidas" and analysis.lida:
            continue

        if empresa and analysis.empresa_re_normalizada != empresa:
            continue

        condutas = _safe_condutas(analysis)

        if conduta and conduta not in condutas:
            continue

        if somente_reincidentes:
            key = analysis.empresa_re_normalizada

            if not key or company_counts[key] < min_reincidencia:
                continue

        filtered.append(analysis)

    total = len(filtered)
    page = filtered[offset:offset + limit]

    filtered_values = [
        value
        for value in (_value_cents(a) for a in filtered)
        if value is not None
    ]

    companies_all = _company_stats(analyses)
    conducts_all = _conduct_stats(analyses)
    companies_filtered = _company_stats(filtered)
    conducts_filtered = _conduct_stats(filtered)

    return {
        "total": total,
        "items": [_item(analysis) for analysis in page],

        # Métricas respondem aos filtros atuais.
        "metrics": {
            "analisadas": len(filtered),
            "com_sentenca": sum(
                1 for analysis in filtered
                if analysis.tem_sentenca is True
            ),
            "lidas": sum(
                1 for analysis in filtered
                if analysis.lida
            ),
            "empresas_reincidentes": sum(
                1 for item in companies_filtered
                if item["processos"] >= 2
            ),
            "valor_mediano_centavos": (
                round(median(filtered_values))
                if filtered_values else None
            ),
        },

        # Facetas completas para os selects.
        "companies": companies_all,
        "conducts": conducts_all,

        # Estatísticas já respeitando a combinação de filtros.
        "filtered_companies": companies_filtered,
        "filtered_conducts": conducts_filtered,
        "capacity_relation": _capacity_stats(filtered),
    }


@router.post("/analyses/{tribunal}/{numero_processo}/read")
@router.patch("/analyses/{tribunal}/{numero_processo}/read")
def set_read_state(
    tribunal: str,
    numero_processo: str,
    value: bool = Query(default=True),
    _user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    analysis = db.scalar(
        select(ProcessAnalysis).where(
            ProcessAnalysis.tribunal == tribunal.upper(),
            ProcessAnalysis.numero_processo == numero_processo,
        )
    )

    if analysis is None:
        raise HTTPException(
            status_code=404,
            detail="Análise não encontrada.",
        )

    analysis.lida = value
    analysis.lida_em = (
        datetime.now(timezone.utc) if value else None
    )
    db.commit()

    return {
        "tribunal": analysis.tribunal,
        "numero_processo": analysis.numero_processo,
        "lida": bool(analysis.lida),
        "lida_em": analysis.lida_em,
    }

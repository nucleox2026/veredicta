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


def _djen_moral_evidence(analysis: ProcessAnalysis) -> dict[str, Any] | None:
    snapshot = analysis.djen_valores
    if not isinstance(snapshot, dict):
        return None

    awards = snapshot.get("awards")
    if not isinstance(awards, dict):
        return None

    history = awards.get("historico_dano_moral")
    if not isinstance(history, list):
        return None

    # A jurimetria usa a última fixação documental forte de dano moral.
    # Documento posterior sem quantia (ex.: quitação) não apaga o histórico.
    for item in reversed(history):
        if not isinstance(item, dict):
            continue

        evidence = item.get("evidencia")
        if not isinstance(evidence, dict):
            continue

        value = item.get("valor_centavos")
        if value is None:
            continue

        if (
            evidence.get("secao") == "dispositivo"
            and evidence.get("confianca") == "alta"
        ):
            return {
                "valor_centavos": int(value),
                "fonte": "DJEN/CNJ",
                "origem": "djen_documental",
                "data": item.get("data"),
                "tipo_documento": item.get("tipo_documento"),
                "link": item.get("link") or evidence.get("link"),
                "trecho": evidence.get("trecho"),
                "confianca": evidence.get("confianca"),
                "secao": evidence.get("secao"),
            }

    return None


def _value_info(analysis: ProcessAnalysis) -> dict[str, Any]:
    djen = _djen_moral_evidence(analysis)
    if djen is not None:
        return djen

    # Fallback compatível com a jurimetria anterior. Só é usado quando não
    # existe evidência documental forte do DJEN para dano moral.
    for field, value in (
        ("valor_final_centavos", analysis.valor_final_centavos),
        ("valor_primeiro_grau_centavos", analysis.valor_primeiro_grau_centavos),
        ("valor_arbitrado_juiz_centavos", analysis.valor_arbitrado_juiz_centavos),
        ("valor_indenizacao_centavos", analysis.valor_indenizacao_centavos),
    ):
        if value is not None:
            return {
                "valor_centavos": int(value),
                "fonte": (
                    analysis.fonte_valor
                    or analysis.fonte_valor_arbitrado
                    or "Análise salva"
                ),
                "origem": "analise_salva",
                "campo": field,
                "confianca": analysis.confianca_valor,
            }

    return {
        "valor_centavos": None,
        "fonte": None,
        "origem": "sem_valor",
    }


def _value_cents(analysis: ProcessAnalysis) -> int | None:
    return _value_info(analysis).get("valor_centavos")


def _safe_condutas(analysis: ProcessAnalysis) -> list[str]:
    value = analysis.condutas
    if not isinstance(value, list):
        return []
    return [str(item) for item in value if str(item).strip()]


def _item(analysis: ProcessAnalysis) -> dict[str, Any]:
    value_info = _value_info(analysis)

    return {
        "tribunal": analysis.tribunal,
        "numero_processo": analysis.numero_processo,
        "empresa_re": analysis.empresa_re,
        "empresa_re_normalizada": analysis.empresa_re_normalizada,
        "resultado": analysis.resultado,
        "tem_sentenca": analysis.tem_sentenca,
        "condutas": _safe_condutas(analysis),
        "valor_centavos": value_info.get("valor_centavos"),
        "valor_fonte": value_info.get("fonte"),
        "valor_origem": value_info.get("origem"),
        "valor_evidencia": (
            value_info if value_info.get("origem") == "djen_documental" else None
        ),
        "confianca_resultado": analysis.confianca_resultado,
        "confianca_valor": analysis.confianca_valor,
        "valor_confianca": value_info.get("confianca"),
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
        value_infos = [_value_info(row) for row in rows]
        values = [
            info["valor_centavos"]
            for info in value_infos
            if info.get("valor_centavos") is not None
        ]
        djen_values = sum(
            1 for info in value_infos
            if info.get("origem") == "djen_documental"
        )

        result.append({
            "empresa": display_names[key],
            "empresa_normalizada": key,
            "processos": len(rows),
            "com_sentenca": sum(
                1 for row in rows if row.tem_sentenca is True
            ),
            "valores_djen": djen_values,
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
    djen_by_conduct = Counter()

    for analysis in analyses:
        value_info = _value_info(analysis)
        value = value_info.get("valor_centavos")

        for conduct in _safe_condutas(analysis):
            counter[conduct] += 1

            if value is not None:
                values_by_conduct[conduct].append(value)
            if value_info.get("origem") == "djen_documental":
                djen_by_conduct[conduct] += 1

    result = []

    for conduct, count in counter.most_common():
        values = values_by_conduct[conduct]

        result.append({
            "conduta": conduct,
            "processos": count,
            "valores_djen": djen_by_conduct[conduct],
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

    filtered_value_infos = [_value_info(a) for a in filtered]
    filtered_values = [
        info["valor_centavos"]
        for info in filtered_value_infos
        if info.get("valor_centavos") is not None
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
            "valor_medio_centavos": (
                round(sum(filtered_values) / len(filtered_values))
                if filtered_values else None
            ),
            "valor_mediano_centavos": (
                round(median(filtered_values))
                if filtered_values else None
            ),
            "processos_com_valor": len(filtered_values),
            "valores_djen": sum(
                1 for info in filtered_value_infos
                if info.get("origem") == "djen_documental"
            ),
            "valores_fallback": sum(
                1 for info in filtered_value_infos
                if info.get("origem") == "analise_salva"
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

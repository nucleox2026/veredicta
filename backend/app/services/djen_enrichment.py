from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from sqlalchemy.orm import Session

from .djen_client import (
    DjenClient,
    DjenError,
    DjenRateLimitError,
)
from .djen_value_extractor import extract_process_awards
from .djen_value_persistence import persist_djen_snapshot


@dataclass(frozen=True)
class DjenEnrichmentOutcome:
    ok: bool
    status: str
    error_code: str | None = None
    retry_after_seconds: int | None = None
    preview: dict[str, Any] | None = None


def enrich_analysis_with_djen(
    *,
    db: Session,
    analysis: Any,
    numero_processo: str,
    client: DjenClient | None = None,
) -> DjenEnrichmentOutcome:
    """Enriquece UMA análise manual com publicações oficiais do DJEN.

    Regras desta etapa:
    - só é chamado pelo fluxo manual "Analisar com IA" / reanálise manual;
    - falha do DJEN não desfaz uma análise de IA já salva;
    - valores canônicos valor_* não são alterados;
    - o snapshot oficial fica em djen_*;
    - nenhuma chamada DataJud/Gemini é feita por este serviço.
    """
    djen_client = client or DjenClient()

    try:
        result = djen_client.get_communications(
            numero_processo,
            itens_por_pagina=100,
            max_pages=5,
        )
    except DjenRateLimitError as exc:
        return DjenEnrichmentOutcome(
            ok=False,
            status="rate_limit",
            error_code="djen_rate_limit",
            retry_after_seconds=exc.retry_after_seconds,
        )
    except DjenError:
        return DjenEnrichmentOutcome(
            ok=False,
            status="indisponivel_temporariamente",
            error_code="djen_indisponivel",
        )
    except Exception:
        # A consulta documental é complementar: não transforma uma análise
        # jurídica já concluída em erro 500/502.
        return DjenEnrichmentOutcome(
            ok=False,
            status="indisponivel_temporariamente",
            error_code="djen_erro_inesperado",
        )

    awards = extract_process_awards(result.items)
    preview = persist_djen_snapshot(
        analysis,
        result,
        awards,
    )

    try:
        db.commit()
        db.refresh(analysis)
    except Exception:
        db.rollback()
        return DjenEnrichmentOutcome(
            ok=False,
            status="erro_persistencia",
            error_code="djen_persistencia",
        )

    return DjenEnrichmentOutcome(
        ok=True,
        status=preview.status,
        preview=asdict(preview),
    )


def _strong_history_item(
    snapshot: dict[str, Any],
    history_key: str,
    *,
    last: bool,
) -> dict[str, Any] | None:
    awards = snapshot.get("awards")
    if not isinstance(awards, dict):
        return None

    history = awards.get(history_key)
    if not isinstance(history, list):
        return None

    iterable = reversed(history) if last else history

    for item in iterable:
        if not isinstance(item, dict):
            continue

        evidence = item.get("evidencia")
        if not isinstance(evidence, dict):
            continue

        if (
            item.get("valor_centavos") is not None
            and evidence.get("secao") == "dispositivo"
            and evidence.get("confianca") == "alta"
        ):
            return {
                "valor_centavos": int(item["valor_centavos"]),
                "data": item.get("data"),
                "tipo_documento": item.get("tipo_documento"),
                "link": item.get("link") or evidence.get("link"),
                "trecho": evidence.get("trecho"),
                "confianca": evidence.get("confianca"),
                "secao": evidence.get("secao"),
                "comunicacao_id": evidence.get("comunicacao_id"),
                "comunicacao_hash": evidence.get("comunicacao_hash"),
            }

    return None


def serialize_djen_analysis(analysis: Any) -> dict[str, Any]:
    snapshot = (
        analysis.djen_valores
        if isinstance(getattr(analysis, "djen_valores", None), dict)
        else {}
    )

    preview = snapshot.get("preview")
    if not isinstance(preview, dict):
        preview = {}

    moral_first = _strong_history_item(
        snapshot,
        "historico_dano_moral",
        last=False,
    )
    moral_final = _strong_history_item(
        snapshot,
        "historico_dano_moral",
        last=True,
    )
    esthetic_first = _strong_history_item(
        snapshot,
        "historico_dano_estetico",
        last=False,
    )
    material_first = _strong_history_item(
        snapshot,
        "historico_dano_material",
        last=False,
    )

    relevant_documents = snapshot.get("documentos_relevantes")
    if not isinstance(relevant_documents, list):
        relevant_documents = []

    principal_document = snapshot.get("documento_principal")
    if not isinstance(principal_document, dict):
        principal_document = None

    # Compatibilidade com snapshots anteriores: documentos decisórios só
    # existem após uma nova consulta DJEN feita a partir desta etapa.
    return {
        "status": getattr(analysis, "djen_status", None),
        "checked_at": getattr(analysis, "djen_checked_at", None),
        "fonte": snapshot.get("fonte") or "DJEN/CNJ",
        "valor_dano_moral_primeiro_grau_centavos": (
            moral_first.get("valor_centavos")
            if moral_first
            else preview.get("valor_dano_moral_primeiro_grau_centavos")
        ),
        "valor_dano_moral_final_centavos": (
            moral_final.get("valor_centavos")
            if moral_final
            else preview.get("valor_dano_moral_final_centavos")
        ),
        "valor_dano_estetico_primeiro_grau_centavos": (
            esthetic_first.get("valor_centavos")
            if esthetic_first
            else preview.get("valor_dano_estetico_primeiro_grau_centavos")
        ),
        "valor_dano_material_primeiro_grau_centavos": (
            material_first.get("valor_centavos")
            if material_first
            else preview.get("valor_dano_material_primeiro_grau_centavos")
        ),
        "evidencia_dano_moral": moral_final or moral_first,
        "evidencia_dano_estetico": esthetic_first,
        "evidencia_dano_material": material_first,
        "documento_principal": principal_document,
        "documentos_relevantes": relevant_documents,
        "publicacao_decisoria_localizada": bool(relevant_documents),
        "comunicacoes": preview.get("comunicacoes"),
        "ultima_comunicacao_hash": getattr(
            analysis,
            "djen_ultima_comunicacao_hash",
            None,
        ),
    }

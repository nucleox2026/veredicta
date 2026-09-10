from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from .djen_client import DjenResult
from .djen_document_summary import build_relevant_documents


DJEN_SOURCE = "DJEN/CNJ"


@dataclass(frozen=True)
class DjenPersistencePreview:
    status: str
    valor_dano_moral_primeiro_grau_centavos: int | None
    valor_dano_moral_final_centavos: int | None
    valor_dano_estetico_primeiro_grau_centavos: int | None
    valor_dano_material_primeiro_grau_centavos: int | None
    comunicacoes: int
    ultima_comunicacao_hash: str | None


def _strong_moral_history(awards: dict[str, Any]) -> list[dict[str, Any]]:
    strong: list[dict[str, Any]] = []
    for item in awards.get("historico_dano_moral") or []:
        evidence = item.get("evidencia") or {}
        if (
            evidence.get("secao") == "dispositivo"
            and evidence.get("confianca") == "alta"
            and item.get("valor_centavos") is not None
        ):
            strong.append(item)
    return strong


def _first_material_value(awards: dict[str, Any]) -> int | None:
    history = awards.get("historico_dano_material") or []
    for item in history:
        evidence = item.get("evidencia") or {}
        if (
            evidence.get("secao") == "dispositivo"
            and evidence.get("confianca") == "alta"
            and item.get("valor_centavos") is not None
        ):
            return int(item["valor_centavos"])
    return None


def _latest_communication_hash(result: DjenResult) -> str | None:
    candidates: list[tuple[str, str]] = []
    for item in result.items:
        value = item.get("hash")
        if not value:
            continue
        date_value = str(
            item.get("data_disponibilizacao")
            or item.get("datadisponibilizacao")
            or ""
        )
        candidates.append((date_value, str(value)))

    if not candidates:
        return None

    candidates.sort(key=lambda pair: pair[0])
    return candidates[-1][1]


def build_djen_persistence_preview(
    result: DjenResult,
    awards: dict[str, Any],
) -> DjenPersistencePreview:
    strong_moral = _strong_moral_history(awards)

    if strong_moral:
        status = "valor_moral_encontrado"
        first_moral = int(strong_moral[0]["valor_centavos"])
        final_moral = int(strong_moral[-1]["valor_centavos"])
    elif result.items:
        status = "sem_valor_moral"
        first_moral = None
        final_moral = None
    else:
        status = "sem_comunicacoes"
        first_moral = None
        final_moral = None

    esthetic = awards.get("historico_dano_estetico") or []
    first_esthetic = None
    for item in esthetic:
        evidence = item.get("evidencia") or {}
        if (
            evidence.get("secao") == "dispositivo"
            and evidence.get("confianca") == "alta"
            and item.get("valor_centavos") is not None
        ):
            first_esthetic = int(item["valor_centavos"])
            break

    return DjenPersistencePreview(
        status=status,
        valor_dano_moral_primeiro_grau_centavos=first_moral,
        valor_dano_moral_final_centavos=final_moral,
        valor_dano_estetico_primeiro_grau_centavos=first_esthetic,
        valor_dano_material_primeiro_grau_centavos=_first_material_value(awards),
        comunicacoes=len(result.items),
        ultima_comunicacao_hash=_latest_communication_hash(result),
    )


def build_djen_snapshot(
    result: DjenResult,
    awards: dict[str, Any],
    *,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    checked_at = checked_at or datetime.now(timezone.utc)
    preview = build_djen_persistence_preview(result, awards)
    documents = build_relevant_documents(
        result.items,
        awards,
    )

    return {
        "fonte": DJEN_SOURCE,
        "metodo": "extracao_deterministica_dispositivo",
        "checked_at": checked_at.isoformat(),
        "numero_processo": result.numero_processo,
        "count_djen": result.count,
        "comunicacoes_processadas": len(result.items),
        "status": preview.status,
        "rate_limit_limit": result.rate_limit_limit,
        "rate_limit_remaining": result.rate_limit_remaining,
        "ultima_comunicacao_hash": preview.ultima_comunicacao_hash,
        "preview": asdict(preview),
        "awards": awards,
        "documentos_relevantes": documents["documentos"],
        "documento_principal": documents["documento_principal"],
    }


def persist_djen_snapshot(
    analysis: Any,
    result: DjenResult,
    awards: dict[str, Any],
    *,
    checked_at: datetime | None = None,
) -> DjenPersistencePreview:
    """
    Persiste SOMENTE o namespace DJEN no ProcessAnalysis.

    Deliberadamente NÃO altera os campos canônicos valor_* nesta etapa.
    Isso evita que uma reanálise Gemini posterior apague ou misture a
    evidência documental oficial antes de implementarmos a regra de precedência.
    """
    checked_at = checked_at or datetime.now(timezone.utc)
    preview = build_djen_persistence_preview(result, awards)
    snapshot = build_djen_snapshot(result, awards, checked_at=checked_at)

    analysis.djen_status = preview.status
    analysis.djen_checked_at = checked_at
    analysis.djen_ultima_comunicacao_hash = preview.ultima_comunicacao_hash
    analysis.djen_valores = snapshot

    return preview

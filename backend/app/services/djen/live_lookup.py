from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from .client import DjenClient, DjenError, DjenRateLimitError
from .document_summary import build_relevant_documents
from .party_extractor import extract_process_parties
from .value_extractor import extract_document_values, extract_process_awards


def _latest_value_da_causa_from_communications(
    communications: list[dict[str, Any]],
) -> dict[str, Any] | None:
    """Localiza valor da causa inclusive em despachos/intimações não decisórias."""
    candidates: list[dict[str, Any]] = []

    for item in communications or []:
        if not isinstance(item, dict):
            continue
        extracted = extract_document_values(item)
        for candidate in extracted.get("candidatos_nao_verificados") or []:
            if not isinstance(candidate, dict):
                continue
            if candidate.get("categoria") != "valor_da_causa":
                continue
            if candidate.get("valor_centavos") is None:
                continue
            candidates.append(candidate)

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            str(item.get("data_documento") or ""),
            str(item.get("comunicacao_id") or ""),
        )
    )
    chosen = candidates[-1]
    return {
        "valor_centavos": int(chosen["valor_centavos"]),
        "valor_texto": chosen.get("valor_texto"),
        "data": chosen.get("data_documento"),
        "tipo_documento": chosen.get("tipo_documento"),
        "link": chosen.get("link"),
        "trecho": chosen.get("trecho"),
        "confianca": chosen.get("confianca"),
    }


def _latest_value_da_causa(awards: dict[str, Any]) -> dict[str, Any] | None:
    candidates = []
    for item in awards.get("candidatos_nao_verificados") or []:
        if not isinstance(item, dict):
            continue
        if item.get("categoria") != "valor_da_causa":
            continue
        if item.get("valor_centavos") is None:
            continue
        candidates.append(item)

    if not candidates:
        return None

    candidates.sort(
        key=lambda item: (
            str(item.get("data_documento") or ""),
            str(item.get("comunicacao_id") or ""),
        )
    )
    chosen = candidates[-1]
    return {
        "valor_centavos": int(chosen["valor_centavos"]),
        "valor_texto": chosen.get("valor_texto"),
        "data": chosen.get("data_documento"),
        "tipo_documento": chosen.get("tipo_documento"),
        "link": chosen.get("link"),
        "trecho": chosen.get("trecho"),
        "confianca": chosen.get("confianca"),
    }


def _history_value(
    awards: dict[str, Any],
    key: str,
    *,
    last: bool,
) -> dict[str, Any] | None:
    history = awards.get(key)
    if not isinstance(history, list) or not history:
        return None

    iterable = reversed(history) if last else history
    for item in iterable:
        if not isinstance(item, dict):
            continue
        if item.get("valor_centavos") is None:
            continue
        evidence = item.get("evidencia") or {}
        return {
            "valor_centavos": int(item["valor_centavos"]),
            "data": item.get("data"),
            "tipo_documento": item.get("tipo_documento"),
            "link": item.get("link") or evidence.get("link"),
            "trecho": evidence.get("trecho"),
            "confianca": evidence.get("confianca"),
            "secao": evidence.get("secao"),
        }
    return None


def _public_party_rows(rows: Any) -> list[dict[str, Any]]:
    if not isinstance(rows, list):
        return []

    output: list[dict[str, Any]] = []
    for item in rows:
        if not isinstance(item, dict):
            continue
        name = str(item.get("nome") or "").strip()
        if not name:
            continue
        output.append(
            {
                "nome": name,
                "documento": item.get("documento"),
                "tipo_pessoa": item.get("tipo_pessoa"),
                "fonte": item.get("fonte") or "DJEN/CNJ",
                "papel": item.get("papel"),
            }
        )
    return output


def lookup_live_djen(
    numero_processo: str,
    *,
    client: DjenClient | None = None,
) -> dict[str, Any]:
    """Consulta documental leve para a ficha processual.

    Não chama IA e não persiste nada. Serve para preencher automaticamente
    partes e valores documentais sempre que a ficha for aberta.
    """
    djen_client = client or DjenClient()
    checked_at = datetime.now(timezone.utc).isoformat()

    try:
        result = djen_client.get_communications(
            numero_processo,
            itens_por_pagina=50,
            max_pages=5,
        )
    except DjenRateLimitError as exc:
        return {
            "ok": False,
            "status": "rate_limit",
            "checked_at": checked_at,
            "retry_after_seconds": exc.retry_after_seconds,
            "partes": {"ativo": [], "passivo": []},
        }
    except DjenError:
        return {
            "ok": False,
            "status": "indisponivel_temporariamente",
            "checked_at": checked_at,
            "partes": {"ativo": [], "passivo": []},
        }
    except Exception:
        return {
            "ok": False,
            "status": "indisponivel_temporariamente",
            "checked_at": checked_at,
            "partes": {"ativo": [], "passivo": []},
        }

    awards = extract_process_awards(result.items)
    parties = extract_process_parties(result.items)
    documents = build_relevant_documents(result.items, awards)

    moral_first = _history_value(awards, "historico_dano_moral", last=False)
    moral_final = _history_value(awards, "historico_dano_moral", last=True)
    esthetic_first = _history_value(awards, "historico_dano_estetico", last=False)
    material_first = _history_value(awards, "historico_dano_material", last=False)
    cause_value = (
        _latest_value_da_causa_from_communications(result.items)
        or _latest_value_da_causa(awards)
    )

    if moral_first or moral_final:
        status = "valor_moral_encontrado"
    elif result.items:
        status = "sem_valor_moral"
    else:
        status = "sem_comunicacoes"

    return {
        "ok": True,
        "status": status,
        "checked_at": checked_at,
        "fonte": "DJEN/CNJ",
        "comunicacoes": len(result.items),
        "partes": {
            "ativo": _public_party_rows(parties.get("ativo")),
            "passivo": _public_party_rows(parties.get("passivo")),
        },
        "empresas_re_identificadas": parties.get("empresas_re") or [],
        "valor_dano_moral_primeiro_grau_centavos": (
            moral_first.get("valor_centavos") if moral_first else None
        ),
        "valor_dano_moral_final_centavos": (
            moral_final.get("valor_centavos") if moral_final else None
        ),
        "valor_dano_estetico_primeiro_grau_centavos": (
            esthetic_first.get("valor_centavos") if esthetic_first else None
        ),
        "valor_dano_material_primeiro_grau_centavos": (
            material_first.get("valor_centavos") if material_first else None
        ),
        "valor_da_causa_centavos": (
            cause_value.get("valor_centavos") if cause_value else None
        ),
        "evidencia_valor_da_causa": cause_value,
        "evidencia_dano_moral": moral_final or moral_first,
        "evidencia_dano_estetico": esthetic_first,
        "evidencia_dano_material": material_first,
        "documento_principal": documents.get("documento_principal"),
        "documentos_relevantes": documents.get("documentos") or [],
        "publicacao_decisoria_localizada": bool(documents.get("documentos")),
    }

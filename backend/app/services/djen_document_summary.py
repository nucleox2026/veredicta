from __future__ import annotations

import re
import unicodedata
from typing import Any


MAX_RELEVANT_DOCUMENTS = 12
MAX_DISPOSITIVE_EXCERPT = 1800


def _fold(value: Any) -> str:
    text = str(value or "")
    normalized = unicodedata.normalize("NFKD", text)
    return "".join(
        char
        for char in normalized
        if not unicodedata.combining(char)
    ).casefold()


def _safe_date(item: dict[str, Any]) -> str | None:
    value = (
        item.get("data_disponibilizacao")
        or item.get("datadisponibilizacao")
        or item.get("dataDisponibilizacao")
    )
    if not value:
        return None
    return str(value)[:10]


def _effective_document_type(item: dict[str, Any]) -> str | None:
    original = str(item.get("tipoDocumento") or "").strip()
    folded_original = _fold(original)

    if any(
        token in folded_original
        for token in ("sentenca", "acordao", "decisao")
    ):
        return original or None

    text = _fold(item.get("texto"))
    if re.search(r"\bsentenca\b", text):
        return (
            "Sentença"
            if not original
            else f"Sentença (publicada em {original})"
        )
    if re.search(r"\bacordao\b", text):
        return (
            "Acórdão"
            if not original
            else f"Acórdão (publicado em {original})"
        )
    if re.search(r"\bdecisao\b", text):
        return (
            "Decisão"
            if not original
            else f"Decisão (publicada em {original})"
        )

    return original or None


def _is_relevant_judicial_document(item: dict[str, Any]) -> bool:
    doc_type = _fold(item.get("tipoDocumento"))
    text = _fold(item.get("texto"))

    formal = any(
        token in doc_type
        for token in ("sentenca", "acordao", "decisao")
    )

    embedded = (
        any(
            re.search(rf"\b{token}\b", text)
            for token in ("sentenca", "acordao")
        )
        and any(
            marker in text
            for marker in (
                "dispositivo",
                "ante o exposto",
                "diante do exposto",
            )
        )
    )

    return formal or embedded


def _dispositive_excerpt(text: Any) -> str | None:
    raw = re.sub(r"\s+", " ", str(text or "")).strip()
    if not raw:
        return None

    folded = _fold(raw)

    # Pegamos o ÚLTIMO marcador para reduzir o risco de usar ementa,
    # precedente citado ou decisão reproduzida na fundamentação.
    positions = [
        folded.rfind("ante o exposto"),
        folded.rfind("diante do exposto"),
        folded.rfind("dispositivo"),
    ]
    start = max(positions)

    if start < 0:
        return raw[:MAX_DISPOSITIVE_EXCERPT]

    excerpt = raw[start : start + MAX_DISPOSITIVE_EXCERPT].strip()
    return excerpt or None


def _document_result(excerpt: str | None) -> str | None:
    folded = _fold(excerpt)
    if not folded:
        return None

    if re.search(
        r"julga?\w*\s+parcialmente\s+procedent",
        folded,
    ):
        return "Procedência parcial"

    if re.search(
        r"julga?\w*\s+improcedent",
        folded,
    ):
        return "Improcedência"

    if re.search(
        r"julga?\w*\s+procedent",
        folded,
    ):
        return "Procedência"

    if (
        "extingo" in folded
        and "sem resolucao do merito" in folded
    ):
        return "Extinção sem resolução do mérito"

    if (
        "extingo" in folded
        and "com resolucao do merito" in folded
    ):
        return "Extinção com resolução do mérito"

    if (
        "rejeito" in folded
        and "embarg" in folded
    ):
        return "Embargos rejeitados"

    return None


def _document_value_links(
    awards: dict[str, Any],
) -> set[str]:
    links: set[str] = set()

    for item in awards.get("documentos_com_valor") or []:
        if not isinstance(item, dict):
            continue
        link = item.get("link")
        if link:
            links.add(str(link))

    return links


def build_relevant_documents(
    communications: list[dict[str, Any]],
    awards: dict[str, Any],
) -> dict[str, Any]:
    """Resume decisões/publicações sem transformar o DJEN em autos integrais.

    O `link` é copiado exatamente da comunicação do DJEN. Ele pode apontar
    para TJMT, TJMG ou outro tribunal e contém o identificador opaco do
    documento (`x=...`, pjekz/visualizacao/... etc.). O Veredicta NÃO tenta
    fabricar esse identificador.
    """
    value_links = _document_value_links(awards)
    documents: list[dict[str, Any]] = []

    for item in communications or []:
        if (
            not isinstance(item, dict)
            or not _is_relevant_judicial_document(item)
        ):
            continue

        text = item.get("texto")
        excerpt = _dispositive_excerpt(text)
        link = item.get("link")

        documents.append(
            {
                "data": _safe_date(item),
                "tipo_documento": _effective_document_type(item),
                "tipo_documento_original": item.get("tipoDocumento"),
                "resultado_documental": _document_result(excerpt),
                "link": str(link) if link else None,
                "hash": (
                    str(item.get("hash"))
                    if item.get("hash")
                    else None
                ),
                "comunicacao_id": item.get("id"),
                "trecho_dispositivo": excerpt,
                "possui_valor_extraido": (
                    bool(link)
                    and str(link) in value_links
                ),
            }
        )

    documents.sort(
        key=lambda doc: (
            doc.get("data") or "9999-12-31",
            str(doc.get("comunicacao_id") or ""),
        )
    )

    if len(documents) > MAX_RELEVANT_DOCUMENTS:
        documents = documents[-MAX_RELEVANT_DOCUMENTS:]

    with_value = [
        doc
        for doc in documents
        if doc.get("possui_valor_extraido")
    ]

    principal = (
        with_value[-1]
        if with_value
        else (documents[-1] if documents else None)
    )

    return {
        "documentos": documents,
        "documento_principal": principal,
    }

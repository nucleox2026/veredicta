from __future__ import annotations

from dataclasses import asdict, dataclass
import threading
import time
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ...models import ProcessAnalysis
from .client import DjenClient
from .party_extractor import extract_defendant_parties


_CACHE_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}

FOUND_TTL_SECONDS = 6 * 60 * 60
NOT_FOUND_TTL_SECONDS = 60 * 60


@dataclass(frozen=True)
class SearchCompanyResult:
    tribunal: str
    numero_processo: str
    status: str
    empresas_re: list[str]
    fonte: str | None = None
    link: str | None = None
    rate_limit_remaining: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def _unique_names(
    rows: Any,
) -> tuple[list[str], str | None]:
    if not isinstance(rows, list):
        return [], None

    names: list[str] = []
    link: str | None = None

    for item in rows:
        if not isinstance(item, dict):
            continue

        name = str(
            item.get("nome")
            or ""
        ).strip()

        if name and name not in names:
            names.append(name)

        if not link:
            raw_link = str(
                item.get("link")
                or ""
            ).strip()
            if raw_link:
                link = raw_link

    return names, link


def _saved_company(
    db: Session,
    numero_processo: str,
) -> SearchCompanyResult | None:
    analysis = db.scalar(
        select(ProcessAnalysis)
        .where(
            ProcessAnalysis.numero_processo
            == numero_processo
        )
        .limit(1)
    )

    if analysis is None:
        return None

    snapshot = (
        analysis.djen_valores
        if isinstance(
            analysis.djen_valores,
            dict,
        )
        else {}
    )

    partes = (
        snapshot.get("partes")
        if isinstance(snapshot, dict)
        else None
    )

    if isinstance(partes, dict):
        names, link = _unique_names(
            partes.get("empresas_re")
        )

        if names:
            return SearchCompanyResult(
                tribunal=str(
                    analysis.tribunal or ""
                ),
                numero_processo=numero_processo,
                status="found",
                empresas_re=names,
                fonte="DJEN/CNJ (salvo)",
                link=link,
            )

    # Fallback apenas para análises antigas que já têm empresa_re
    # persistida, mas ainda não têm o snapshot de partes.
    old_name = str(
        analysis.empresa_re
        or ""
    ).strip()

    if old_name:
        return SearchCompanyResult(
            tribunal=str(
                analysis.tribunal or ""
            ),
            numero_processo=numero_processo,
            status="found",
            empresas_re=[old_name],
            fonte="Análise salva",
        )

    return None


def _cache_get(
    tribunal: str,
    numero_processo: str,
) -> SearchCompanyResult | None:
    key = f"{tribunal}:{numero_processo}"

    with _CACHE_LOCK:
        cached = _CACHE.get(key)

        if not cached:
            return None

        expires_at, payload = cached

        if expires_at <= time.time():
            _CACHE.pop(key, None)
            return None

    return SearchCompanyResult(
        **payload
    )


def _cache_put(
    result: SearchCompanyResult,
) -> None:
    ttl = (
        FOUND_TTL_SECONDS
        if result.status == "found"
        else NOT_FOUND_TTL_SECONDS
    )

    key = (
        f"{result.tribunal}:"
        f"{result.numero_processo}"
    )

    with _CACHE_LOCK:
        _CACHE[key] = (
            time.time() + ttl,
            result.to_dict(),
        )


def lookup_company_for_search(
    *,
    db: Session,
    tribunal: str,
    numero_processo: str,
    client: DjenClient,
) -> SearchCompanyResult:
    """
    Resolve a empresa ré ANTES de abrir a ficha.

    Ordem:
    1. evidência já persistida em ProcessAnalysis;
    2. cache transitório do servidor;
    3. consulta DJEN/CNJ de uma única página.

    A pesquisa não cria ProcessAnalysis novo e não chama IA.
    """
    tribunal = str(
        tribunal or ""
    ).strip().upper()

    numero = str(
        numero_processo or ""
    ).strip()

    saved = _saved_company(
        db,
        numero,
    )

    if saved is not None:
        return SearchCompanyResult(
            tribunal=tribunal or saved.tribunal,
            numero_processo=numero,
            status=saved.status,
            empresas_re=saved.empresas_re,
            fonte=saved.fonte,
            link=saved.link,
        )

    cached = _cache_get(
        tribunal,
        numero,
    )

    if cached is not None:
        return cached

    djen_result = client.get_communications(
        numero,
        itens_por_pagina=100,
        max_pages=1,
        pause_between_pages_seconds=0,
    )

    parties = extract_defendant_parties(
        djen_result.items
    )

    names, link = _unique_names(
        parties.get("empresas_re")
        if isinstance(parties, dict)
        else []
    )

    result = SearchCompanyResult(
        tribunal=tribunal,
        numero_processo=numero,
        status=(
            "found"
            if names
            else "not_found"
        ),
        empresas_re=names,
        fonte=(
            "DJEN/CNJ"
            if names
            else None
        ),
        link=link,
        rate_limit_remaining=(
            djen_result.rate_limit_remaining
        ),
    )

    _cache_put(result)

    return result

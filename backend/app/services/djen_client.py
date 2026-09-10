from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

DJEN_BASE_URL = "https://comunicaapi.pje.jus.br/api/v1"
DEFAULT_TIMEOUT_SECONDS = 20
DEFAULT_ITEMS_PER_PAGE = 100
DEFAULT_MAX_PAGES = 5


class DjenError(RuntimeError):
    pass


class DjenRateLimitError(DjenError):
    def __init__(self, message: str, retry_after_seconds: int = 60):
        super().__init__(message)
        self.retry_after_seconds = retry_after_seconds


@dataclass(frozen=True)
class DjenResult:
    numero_processo: str
    count: int
    items: list[dict[str, Any]]
    rate_limit_limit: int | None = None
    rate_limit_remaining: int | None = None


def normalize_process_number(numero_processo: str) -> str:
    digits = re.sub(r"\D", "", str(numero_processo or ""))
    if len(digits) != 20:
        raise ValueError("O número CNJ deve conter exatamente 20 dígitos.")
    return digits


def _int_header(value: str | None) -> int | None:
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


class DjenClient:
    """Cliente mínimo da consulta pública do DJEN/CNJ."""

    def __init__(
        self,
        base_url: str = DJEN_BASE_URL,
        timeout_seconds: int = DEFAULT_TIMEOUT_SECONDS,
        user_agent: str = "Veredicta/1.0 (DJEN public consultation)",
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.timeout_seconds = timeout_seconds
        self.user_agent = user_agent

    def _request_page(
        self,
        numero_processo: str,
        *,
        pagina: int,
        itens_por_pagina: int,
    ) -> tuple[dict[str, Any], int | None, int | None]:
        params = {
            "numeroProcesso": normalize_process_number(numero_processo),
            "pagina": pagina,
            "itensPorPagina": itens_por_pagina,
        }
        url = f"{self.base_url}/comunicacao?{urlencode(params)}"
        request = Request(
            url,
            method="GET",
            headers={"Accept": "application/json", "User-Agent": self.user_agent},
        )

        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                payload = json.loads(response.read().decode("utf-8"))
                return (
                    payload,
                    _int_header(response.headers.get("x-ratelimit-limit")),
                    _int_header(response.headers.get("x-ratelimit-remaining")),
                )
        except HTTPError as exc:
            if exc.code == 429:
                retry_after = _int_header(exc.headers.get("Retry-After")) or 60
                raise DjenRateLimitError(
                    "DJEN respondeu HTTP 429; aguarde antes de tentar novamente.",
                    retry_after_seconds=retry_after,
                ) from exc
            body = ""
            try:
                body = exc.read().decode("utf-8", errors="replace")
            except Exception:
                pass
            raise DjenError(f"DJEN respondeu HTTP {exc.code}. {body[:500]}".strip()) from exc
        except URLError as exc:
            raise DjenError(f"Falha de rede ao consultar DJEN: {exc.reason}") from exc
        except json.JSONDecodeError as exc:
            raise DjenError("DJEN retornou resposta que não é JSON válido.") from exc

    def get_communications(
        self,
        numero_processo: str,
        *,
        itens_por_pagina: int = DEFAULT_ITEMS_PER_PAGE,
        max_pages: int = DEFAULT_MAX_PAGES,
        pause_between_pages_seconds: float = 0.15,
    ) -> DjenResult:
        if itens_por_pagina not in (5, 100):
            raise ValueError("itens_por_pagina deve ser 5 ou 100.")
        if max_pages < 1:
            raise ValueError("max_pages deve ser >= 1.")

        numero = normalize_process_number(numero_processo)
        all_items: list[dict[str, Any]] = []
        total_count = 0
        last_limit: int | None = None
        last_remaining: int | None = None

        for pagina in range(1, max_pages + 1):
            payload, limit, remaining = self._request_page(
                numero, pagina=pagina, itens_por_pagina=itens_por_pagina
            )
            last_limit = limit if limit is not None else last_limit
            last_remaining = remaining if remaining is not None else last_remaining
            items = payload.get("items") or []
            if not isinstance(items, list):
                raise DjenError("Campo 'items' do DJEN não é uma lista.")

            try:
                total_count = int(payload.get("count") or 0)
            except (TypeError, ValueError):
                total_count = len(items)

            all_items.extend(item for item in items if isinstance(item, dict))
            if not items or len(items) < itens_por_pagina:
                break
            if total_count and len(all_items) >= total_count:
                break
            if pause_between_pages_seconds > 0:
                time.sleep(pause_between_pages_seconds)

        return DjenResult(
            numero_processo=numero,
            count=total_count if total_count else len(all_items),
            items=all_items,
            rate_limit_limit=last_limit,
            rate_limit_remaining=last_remaining,
        )

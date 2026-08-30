from datetime import date

import httpx
from fastapi import HTTPException

from ..settings import Settings


class DataJudClient:
    def __init__(self, settings: Settings):
        self.settings = settings

    def _build_query(
        self,
        date_from: date,
        date_to: date,
        subject_text: str | None,
        limit: int,
        search_after: list | None = None,
    ) -> dict:
        filters: list[dict] = [
            {
                "range": {
                    "dataAjuizamento": {
                        "gte": int(date_from.strftime("%Y%m%d") + "000000"),
                        "lte": int(date_to.strftime("%Y%m%d") + "235959"),
                    }
                }
            }
        ]

        must: list[dict] = []

        if subject_text:
            normalized = subject_text.strip().lower()

            if normalized in {
                "dano moral",
                "indenização por dano moral",
                "indenizacao por dano moral",
            }:
                filters.append(
                    {
                        "term": {
                            "assuntos.codigo": 9992
                        }
                    }
                )
            else:
                must.append(
                    {
                        "match_phrase": {
                            "assuntos.nome": subject_text
                        }
                    }
                )

        query = {
            "size": limit,
            "track_total_hits": True,
            "sort": [
                {
                    "@timestamp": {
                        "order": "desc"
                    }
                }
            ],
            "_source": [
                "numeroProcesso",
                "dataAjuizamento",
                "grau",
                "classe",
                "assuntos",
                "orgaoJulgador",
                "movimentos",
            ],
            "query": {
                "bool": {
                    "filter": filters,
                    "must": must,
                }
            },
        }

        if search_after is not None:
            query["search_after"] = search_after

        return query

    async def _execute_query(self, query: dict) -> dict:
        if not self.settings.datajud_api_key:
            raise HTTPException(
                status_code=503,
                detail="DATAJUD_API_KEY não configurada no backend.",
            )

        headers = {
            "Authorization": f"APIKey {self.settings.datajud_api_key}",
            "Content-Type": "application/json",
        }

        try:
            async with httpx.AsyncClient(timeout=45.0) as client:
                response = await client.post(
                    self.settings.datajud_tjmt_url,
                    headers=headers,
                    json=query,
                )

        except httpx.HTTPError as exc:
            raise HTTPException(
                status_code=502,
                detail=f"Falha de comunicação com o DataJud: {exc}",
            ) from exc

        if response.status_code >= 400:
            raise HTTPException(
                status_code=502,
                detail=(
                    f"DataJud respondeu HTTP {response.status_code}: "
                    f"{response.text[:500]}"
                ),
            )

        return response.json()

    async def fetch_tjmt_page(
        self,
        date_from: date,
        date_to: date,
        subject_text: str | None,
        limit: int,
        search_after: list | None = None,
    ) -> dict:
        query = self._build_query(
            date_from=date_from,
            date_to=date_to,
            subject_text=subject_text,
            limit=limit,
            search_after=search_after,
        )

        payload = await self._execute_query(query)

        hits_container = payload.get("hits", {})
        raw_hits = hits_container.get("hits", [])

        total_obj = hits_container.get("total")

        if isinstance(total_obj, dict):
            total = total_obj.get("value", 0)
        else:
            total = total_obj or 0

        items = [
            hit.get("_source", {})
            for hit in raw_hits
        ]

        next_search_after = None

        if raw_hits:
            next_search_after = raw_hits[-1].get("sort")

        return {
            "total": total,
            "items": items,
            "next_search_after": next_search_after,
        }

    async def preview_tjmt(
        self,
        date_from: date,
        date_to: date,
        subject_text: str | None,
        limit: int,
    ) -> dict:
        page = await self.fetch_tjmt_page(
            date_from=date_from,
            date_to=date_to,
            subject_text=subject_text,
            limit=limit,
        )

        return {
            "total": page["total"],
            "items": page["items"],
        }
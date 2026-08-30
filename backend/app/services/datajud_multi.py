import json
from concurrent.futures import ThreadPoolExecutor, as_completed
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.settings import get_settings
from app.services.tribunals import (
    get_datajud_endpoint,
    normalize_tribunal,
)


MAX_WORKERS = 5
DEFAULT_PAGE_SIZE = 20
MAX_PAGE_SIZE = 100


class DataJudError(RuntimeError):
    pass


def _compact_date(
    value: str,
    end_of_day: bool = False,
) -> int:
    """
    Converte YYYY-MM-DD para o formato numérico
    usado pelo DataJud: YYYYMMDDHHMMSS.
    """
    cleaned = value.strip().replace("-", "")

    if len(cleaned) != 8 or not cleaned.isdigit():
        raise ValueError(
            f"Data inválida: {value}. "
            "Use o formato YYYY-MM-DD."
        )

    suffix = "235959" if end_of_day else "000000"

    return int(cleaned + suffix)


def _normalize_process_number(
    value: str,
) -> str:
    """
    Converte número CNJ formatado ou não
    para somente dígitos.
    """
    digits = "".join(
        char
        for char in str(value)
        if char.isdigit()
    )

    if not digits:
        raise ValueError(
            "Número de processo inválido."
        )

    return digits


def _safe_name(value):
    if isinstance(value, dict):
        return value.get("nome")

    if isinstance(value, str):
        return value

    return None


def _normalize_hit(
    tribunal: str,
    hit: dict,
) -> dict:
    source = hit.get("_source") or {}

    classe = source.get("classe") or {}

    orgao = (
        source.get("orgaoJulgador")
        or source.get("orgao_julgador")
        or {}
    )

    return {
        "tribunal": tribunal,
        "numero_processo": source.get(
            "numeroProcesso"
        ),
        "data_ajuizamento": source.get(
            "dataAjuizamento"
        ),
        "grau": source.get("grau"),
        "classe_nome": _safe_name(classe),
        "orgao_julgador_nome": _safe_name(
            orgao
        ),
        "assuntos": (
            source.get("assuntos")
            or []
        ),
        "sort": hit.get("sort"),
        "raw_source": source,
    }


class DataJudMultiClient:
    def __init__(self):
        settings = get_settings()

        self.api_key = (
            settings.datajud_api_key
        )

        if not self.api_key:
            raise DataJudError(
                "DATAJUD_API_KEY não configurada."
            )

    def _post(
        self,
        tribunal: str,
        payload: dict,
    ) -> dict:
        endpoint = get_datajud_endpoint(
            tribunal
        )

        body = json.dumps(
            payload
        ).encode("utf-8")

        request = Request(
            endpoint,
            data=body,
            method="POST",
            headers={
                "Authorization": (
                    f"APIKey {self.api_key}"
                ),
                "Content-Type": (
                    "application/json"
                ),
                "Accept": (
                    "application/json"
                ),
            },
        )

        try:
            with urlopen(
                request,
                timeout=30,
            ) as response:
                return json.loads(
                    response
                    .read()
                    .decode("utf-8")
                )

        except HTTPError as exc:
            try:
                detail = (
                    exc.read()
                    .decode("utf-8")
                    [:1000]
                )

            except Exception:
                detail = str(exc)

            raise DataJudError(
                f"{tribunal}: DataJud retornou "
                f"HTTP {exc.code}. {detail}"
            ) from exc

        except URLError as exc:
            raise DataJudError(
                f"{tribunal}: erro de conexão "
                f"com DataJud: {exc.reason}"
            ) from exc

        except TimeoutError as exc:
            raise DataJudError(
                f"{tribunal}: timeout ao "
                "consultar o DataJud."
            ) from exc

    def get_process(
        self,
        tribunal: str,
        numero_processo: str,
    ) -> dict:
        tribunal = normalize_tribunal(
            tribunal
        )

        numero = (
            _normalize_process_number(
                numero_processo
            )
        )

        payload = {
            "size": 50,
            "track_total_hits": True,

            "query": {
                "bool": {
                    "should": [
                        {
                            "term": {
                                "numeroProcesso.keyword": (
                                    numero
                                )
                            }
                        },
                        {
                            "match_phrase": {
                                "numeroProcesso": (
                                    numero
                                )
                            }
                        },
                    ],

                    "minimum_should_match": 1,
                }
            },

            "sort": [
                {
                    "@timestamp": {
                        "order": "desc"
                    }
                },
                {
                    "id.keyword": {
                        "order": "asc"
                    }
                },
            ],
        }

        data = self._post(
            tribunal,
            payload,
        )

        hits_data = (
            data.get("hits")
            or {}
        )

        hits = (
            hits_data.get("hits")
            or []
        )

        if not hits:
            return {
                "found": False,

                "tribunal": tribunal,

                "numero_processo": (
                    numero
                ),

                "total_ocorrencias": 0,

                "raw_source": None,
            }

        sources = [
            hit.get("_source") or {}
            for hit in hits
        ]

        # Usa a ocorrência mais recente
        # como base.
        primary_source = dict(
            sources[0]
        )

        # Junta movimentações de eventuais
        # ocorrências duplicadas do processo.
        movimentos = []

        movimentos_vistos = set()

        for source in sources:
            for movimento in (
                source.get("movimentos")
                or []
            ):
                try:
                    movement_key = json.dumps(
                        movimento,
                        sort_keys=True,
                        ensure_ascii=False,
                    )

                except TypeError:
                    movement_key = str(
                        movimento
                    )

                if (
                    movement_key
                    in movimentos_vistos
                ):
                    continue

                movimentos_vistos.add(
                    movement_key
                )

                movimentos.append(
                    movimento
                )

        def movement_date(
            movimento: dict,
        ) -> str:
            return str(
                movimento.get("dataHora")
                or movimento.get("data")
                or ""
            )

        movimentos.sort(
            key=movement_date,
            reverse=True,
        )

        primary_source[
            "movimentos"
        ] = movimentos

        return {
            "found": True,

            "tribunal": tribunal,

            "numero_processo": numero,

            "total_ocorrencias": len(
                hits
            ),

            "raw_source": primary_source,
        }

    def search_tribunal(
        self,
        tribunal: str,
        date_from: str,
        date_to: str,
        subject_code: int = 9992,
        page_size: int = (
            DEFAULT_PAGE_SIZE
        ),
        search_after: list | None = None,
    ) -> dict:
        tribunal = normalize_tribunal(
            tribunal
        )

        page_size = max(
            1,
            min(
                page_size,
                MAX_PAGE_SIZE,
            ),
        )

        filters = [
            {
                "range": {
                    "dataAjuizamento": {
                        "gte": _compact_date(
                            date_from
                        ),
                        "lte": _compact_date(
                            date_to,
                            end_of_day=True,
                        ),
                    }
                }
            }
        ]

        if subject_code:
            filters.append(
                {
                    "term": {
                        "assuntos.codigo": (
                            subject_code
                        )
                    }
                }
            )

        payload = {
            "size": page_size,

            "track_total_hits": True,

            "_source": [
                "numeroProcesso",
                "dataAjuizamento",
                "grau",
                "classe",
                "orgaoJulgador",
                "assuntos",
            ],

            "query": {
                "bool": {
                    "filter": filters
                }
            },

            "sort": [
                {
                    "dataAjuizamento": {
                        "order": "desc"
                    }
                },
                {
                    "id.keyword": {
                        "order": "asc"
                    }
                },
            ],
        }

        if search_after:
            payload["search_after"] = (
                search_after
            )

        data = self._post(
            tribunal,
            payload,
        )

        hits_data = (
            data.get("hits")
            or {}
        )

        total_data = (
            hits_data.get("total")
            or 0
        )

        if isinstance(
            total_data,
            dict,
        ):
            total = total_data.get(
                "value",
                0,
            )

        else:
            total = total_data or 0

        hits = (
            hits_data.get("hits")
            or []
        )

        items = [
            _normalize_hit(
                tribunal,
                hit,
            )
            for hit in hits
        ]

        next_search_after = None

        if hits:
            next_search_after = (
                hits[-1].get("sort")
            )

        return {
            "tribunal": tribunal,

            "ok": True,

            "total": total,

            "items": items,

            "next_search_after": (
                next_search_after
            ),

            "error": None,
        }

    def search_many(
        self,
        tribunais: list[str],
        date_from: str,
        date_to: str,
        subject_code: int = 9992,
        page_size_per_tribunal: int = 20,
        search_after_by_tribunal: dict[
            str,
            list,
        ] | None = None,
    ) -> dict:
        """
        Pesquisa vários tribunais em paralelo.

        Cada tribunal possui seu próprio
        cursor search_after.

        Nenhum resultado é persistido
        no banco de dados.
        """

        tribunais = list(
            dict.fromkeys(
                normalize_tribunal(t)
                for t in tribunais
            )
        )

        if not tribunais:
            raise ValueError(
                "Informe ao menos um tribunal."
            )

        search_after_by_tribunal = (
            search_after_by_tribunal
            or {}
        )

        results = []

        workers = min(
            MAX_WORKERS,
            len(tribunais),
        )

        with ThreadPoolExecutor(
            max_workers=workers
        ) as executor:

            futures = {}

            for tribunal in tribunais:
                cursor = (
                    search_after_by_tribunal.get(
                        tribunal
                    )
                )

                future = executor.submit(
                    self.search_tribunal,
                    tribunal,
                    date_from,
                    date_to,
                    subject_code,
                    page_size_per_tribunal,
                    cursor,
                )

                futures[
                    future
                ] = tribunal

            for future in as_completed(
                futures
            ):
                tribunal = (
                    futures[future]
                )

                try:
                    result = (
                        future.result()
                    )

                except Exception as exc:
                    result = {
                        "tribunal": tribunal,
                        "ok": False,
                        "total": 0,
                        "items": [],
                        "next_search_after": None,
                        "error": str(exc),
                    }

                results.append(
                    result
                )

        # -----------------------------------------------------
        # Junta os resultados
        # -----------------------------------------------------

        all_items = []

        for result in results:
            all_items.extend(
                result["items"]
            )

        # Ordena os resultados dos vários TJs
        # pela data de ajuizamento.
        all_items.sort(
            key=lambda item: str(
                item.get(
                    "data_ajuizamento"
                )
                or ""
            ),
            reverse=True,
        )

        # -----------------------------------------------------
        # Total informado pelo DataJud
        # -----------------------------------------------------

        total_found = sum(
            result["total"]
            for result in results
            if result["ok"]
        )

        # -----------------------------------------------------
        # Erros parciais
        # -----------------------------------------------------

        errors = [
            {
                "tribunal": (
                    result["tribunal"]
                ),
                "error": (
                    result["error"]
                ),
            }
            for result in results
            if not result["ok"]
        ]

        # -----------------------------------------------------
        # Resumo por tribunal
        # -----------------------------------------------------

        summary = sorted(
            [
                {
                    "tribunal": (
                        result["tribunal"]
                    ),

                    "total": (
                        result["total"]
                    ),

                    "ok": (
                        result["ok"]
                    ),

                    "resultados_recebidos": (
                        len(
                            result["items"]
                        )
                    ),
                }
                for result in results
            ],
            key=lambda item: (
                item["tribunal"]
            ),
        )

        # -----------------------------------------------------
        # Próximos cursores
        # -----------------------------------------------------

        next_search_after_by_tribunal = {}

        for result in results:
            tribunal = (
                result["tribunal"]
            )

            cursor = (
                result.get(
                    "next_search_after"
                )
            )

            if (
                result["ok"]
                and cursor
            ):
                next_search_after_by_tribunal[
                    tribunal
                ] = cursor

        return {
            "total_found": (
                total_found
            ),

            "tribunais_solicitados": (
                len(tribunais)
            ),

            "tribunais_ok": sum(
                1
                for result in results
                if result["ok"]
            ),

            "tribunais_com_erro": (
                len(errors)
            ),

            "por_tribunal": (
                summary
            ),

            "items": (
                all_items
            ),

            "errors": (
                errors
            ),

            "next_search_after_by_tribunal": (
                next_search_after_by_tribunal
            ),
        }
from datetime import date

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..services.datajud.client import (
    DataJudError,
    DataJudMultiClient,
)

from ..services.djen.client import (
    DjenClient,
    DjenError,
    DjenRateLimitError,
)
from ..services.djen.search_company_enrichment import (
    lookup_company_for_search,
)

from ..services.tribunals import (
    get_tribunal,
    list_tribunais,
    normalize_tribunal,
)

router = APIRouter(
    prefix="/api/v1/searches",
    tags=["searches"],
)

class MultiTribunalSearchRequest(
        BaseModel
    ):
        tribunais: list[str] = Field(
            min_length=1,
            max_length=27,
        )

        date_from: date

        date_to: date

        subject_code: int | None = 9992

        health_plans_only: bool = True

        page_size_per_tribunal: int = Field(
            default=10,
            ge=1,
            le=50,
        )

        search_after_by_tribunal: dict[
            str,
            list,
        ] | None = None

        @field_validator("tribunais")
        @classmethod
        def validate_tribunais(
            cls,
            value: list[str],
        ) -> list[str]:

            normalized = []

            for tribunal in value:
                sigla = (
                    normalize_tribunal(
                        tribunal
                    )
                )

                try:
                    get_tribunal(
                        sigla
                    )

                except ValueError as exc:
                    raise ValueError(
                        str(exc)
                    ) from exc

                if sigla not in normalized:
                    normalized.append(
                        sigla
                    )

            return normalized



class SearchCompanyItem(
    BaseModel
):
    tribunal: str
    numero_processo: str


class SearchCompanyRequest(
    BaseModel
):
    items: list[SearchCompanyItem] = Field(
        min_length=1,
        max_length=8,
    )


@router.get("/tribunals")
async def get_available_tribunals(
    _user: dict = Depends(current_user),
):
    tribunais = list_tribunais()

    return {
        "total": len(tribunais),
        "items": tribunais,
    }



@router.post("/companies")
def search_result_companies(
    request: SearchCompanyRequest,

    db: Session = Depends(
        get_db
    ),

    _user: dict = Depends(
        current_user
    ),
):
    client = DjenClient()
    output = []
    retry_after_seconds = None
    items = list(request.items)

    for index, item in enumerate(items):
        try:
            tribunal = normalize_tribunal(
                item.tribunal
            )

            result = lookup_company_for_search(
                db=db,
                tribunal=tribunal,
                numero_processo=item.numero_processo,
                client=client,
            )

            output.append(result.to_dict())

            if (
                result.rate_limit_remaining
                is not None
                and result.rate_limit_remaining <= 1
                and index < len(items) - 1
            ):
                retry_after_seconds = 60

                for pending in items[index + 1:]:
                    output.append(
                        {
                            "tribunal": normalize_tribunal(
                                pending.tribunal
                            ),
                            "numero_processo": (
                                pending.numero_processo
                            ),
                            "status": "rate_limited",
                            "empresas_re": [],
                            "fonte": None,
                            "link": None,
                            "rate_limit_remaining": (
                                result.rate_limit_remaining
                            ),
                        }
                    )

                break

        except DjenRateLimitError as exc:
            retry_after_seconds = max(
                int(exc.retry_after_seconds or 60),
                5,
            )

            for pending in items[index:]:
                output.append(
                    {
                        "tribunal": normalize_tribunal(
                            pending.tribunal
                        ),
                        "numero_processo": (
                            pending.numero_processo
                        ),
                        "status": "rate_limited",
                        "empresas_re": [],
                        "fonte": None,
                        "link": None,
                        "rate_limit_remaining": 0,
                    }
                )

            break

        except (
            DjenError,
            ValueError,
        ) as exc:
            output.append(
                {
                    "tribunal": str(
                        item.tribunal or ""
                    ).upper(),
                    "numero_processo": (
                        item.numero_processo
                    ),
                    "status": "error",
                    "empresas_re": [],
                    "fonte": None,
                    "link": None,
                    "error": str(exc),
                }
            )

    return {
        "items": output,
        "retry_after_seconds": retry_after_seconds,
    }


@router.post("/multi")
def multi_tribunal_search(
    request: MultiTribunalSearchRequest,

    _user: dict = Depends(
        current_user
    ),
):
    if (
        request.date_from
        > request.date_to
    ):
        raise HTTPException(
            status_code=400,
            detail=(
                "A data inicial não pode "
                "ser posterior à data final."
            ),
        )

    try:
        client = (
            DataJudMultiClient()
        )

        result = client.search_many(
            tribunais=(
                request.tribunais
            ),

            date_from=(
                request
                .date_from
                .isoformat()
            ),

            date_to=(
                request
                .date_to
                .isoformat()
            ),

            subject_code=(
                request.subject_code
            ),

            health_plans_only=(
                request.health_plans_only
            ),

            page_size_per_tribunal=(
                request
                .page_size_per_tribunal
            ),

            search_after_by_tribunal=(
                request
                .search_after_by_tribunal
            ),
        )

    except DataJudError as exc:
        raise HTTPException(
            status_code=502,
            detail=str(exc),
        ) from exc

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    # -----------------------------------------------------
    # Monta versão pública dos resultados.
    #
    # Não devolvemos raw_source porque a listagem
    # deve continuar leve.
    # -----------------------------------------------------

    public_items = []

    for item in result["items"]:

        public_items.append(
            {
                "tribunal": (
                    item.get(
                        "tribunal"
                    )
                ),

                "numero_processo": (
                    item.get(
                        "numero_processo"
                    )
                ),

                "data_ajuizamento": (
                    item.get(
                        "data_ajuizamento"
                    )
                ),

                "grau": (
                    item.get(
                        "grau"
                    )
                ),

                "classe_nome": (
                    item.get(
                        "classe_nome"
                    )
                ),

                "orgao_julgador_nome": (
                    item.get(
                        "orgao_julgador_nome"
                    )
                ),

                "assuntos": (
                    item.get(
                        "assuntos"
                    )
                    or []
                ),
            }
        )

    # IMPORTANTE:
    # este return fica FORA do for acima.
    return {
        "total_found": (
            result[
                "total_found"
            ]
        ),

        "tribunais_solicitados": (
            result[
                "tribunais_solicitados"
            ]
        ),

        "tribunais_ok": (
            result[
                "tribunais_ok"
            ]
        ),

        "tribunais_com_erro": (
            result[
                "tribunais_com_erro"
            ]
        ),

        "por_tribunal": (
            result[
                "por_tribunal"
            ]
        ),

        "resultados_recebidos": (
            len(
                public_items
            )
        ),

        "items": (
            public_items
        ),

        "errors": (
            result[
                "errors"
            ]
        ),

        "next_search_after_by_tribunal": (
            result[
                "next_search_after_by_tribunal"
            ]
        ),

        "health_plans_only": bool(
            request.health_plans_only
        ),
    }

from datetime import date, datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import ProcessRecord, SearchRun
from ..schemas import (
    CollectSearchRequest,
    CollectSearchResponse,
    PreviewSearchRequest,
    PreviewSearchResponse,
)
from ..services.datajud import DataJudClient
from ..settings import Settings, get_settings

from ..services.datajud_multi import (
    DataJudError,
    DataJudMultiClient,
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

class MultiTribunalSearchRequest(BaseModel):
    tribunais: list[str] = Field(
        min_length=1,
        max_length=27,
    )

    date_from: date
    date_to: date

    subject_code: int | None = 9992

    page_size_per_tribunal: int = Field(
        default=10,
        ge=1,
        le=50,
    )

    @field_validator("tribunais")
    @classmethod
    def validate_tribunais(
        cls,
        value: list[str],
    ) -> list[str]:

        normalized = []

        for tribunal in value:
            sigla = normalize_tribunal(
                tribunal
            )

            try:
                get_tribunal(sigla)

            except ValueError as exc:
                raise ValueError(
                    str(exc)
                ) from exc

            if sigla not in normalized:
                normalized.append(sigla)

        if not normalized:
            raise ValueError(
                "Informe ao menos um tribunal."
            )

        return normalized

def parse_data_ajuizamento(value) -> datetime | None:
    if value is None:
        return None

    text = str(value)

    if len(text) >= 14 and text[:14].isdigit():
        try:
            return datetime.strptime(
                text[:14],
                "%Y%m%d%H%M%S",
            )
        except ValueError:
            return None

    return None

@router.get("/tribunals")
async def get_available_tribunals(
    _user: dict = Depends(current_user),
):
    tribunais = list_tribunais()

    return {
        "total": len(tribunais),
        "items": tribunais,
    }

@router.post("/multi")
def multi_tribunal_search(
    request: MultiTribunalSearchRequest,
    _user: dict = Depends(current_user),
):
    if request.date_from > request.date_to:
        raise HTTPException(
            status_code=400,
            detail=(
                "A data inicial não pode ser "
                "posterior à data final."
            ),
        )

    try:
        client = DataJudMultiClient()

        result = client.search_many(
            tribunais=request.tribunais,
            date_from=request.date_from.isoformat(),
            date_to=request.date_to.isoformat(),
            subject_code=request.subject_code,
            page_size_per_tribunal=(
                request.page_size_per_tribunal
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

    public_items = []

    for item in result["items"]:
        public_items.append(
            {
                "tribunal": item.get(
                    "tribunal"
                ),
                "numero_processo": item.get(
                    "numero_processo"
                ),
                "data_ajuizamento": item.get(
                    "data_ajuizamento"
                ),
                "grau": item.get(
                    "grau"
                ),
                "classe_nome": item.get(
                    "classe_nome"
                ),
                "orgao_julgador_nome": item.get(
                    "orgao_julgador_nome"
                ),
                "assuntos": item.get(
                    "assuntos"
                ),
            }
        )

    return {
        "total_found": result[
            "total_found"
        ],
        "tribunais_solicitados": result[
            "tribunais_solicitados"
        ],
        "tribunais_ok": result[
            "tribunais_ok"
        ],
        "tribunais_com_erro": result[
            "tribunais_com_erro"
        ],
        "por_tribunal": result[
            "por_tribunal"
        ],
        "resultados_recebidos": len(
            public_items
        ),
        "items": public_items,
        "errors": result[
            "errors"
        ],
    }

def save_process_page(
    db: Session,
    items: list[dict],
) -> tuple[int, int]:
    # O DataJud pode devolver mais de um registro
    # com o mesmo numeroProcesso no mesmo lote.
    #
    # Como os resultados vêm ordenados por @timestamp desc,
    # preservamos a primeira ocorrência encontrada.
    unique_items: dict[str, dict] = {}

    for item in items:
        numero = item.get("numeroProcesso")

        if not numero:
            continue

        numero = str(numero)

        if numero not in unique_items:
            unique_items[numero] = item

    valid_items = list(unique_items.values())

    if not valid_items:
        return 0, 0

    process_numbers = list(unique_items.keys())

    existing_records = db.scalars(
        select(ProcessRecord).where(
            ProcessRecord.numero_processo.in_(
                process_numbers
            )
        )
    ).all()

    existing_by_number = {
        record.numero_processo: record
        for record in existing_records
    }

    saved_new = 0
    updated = 0

    for item in valid_items:
        numero_processo = str(
            item["numeroProcesso"]
        )

        classe = item.get("classe") or {}
        orgao_julgador = (
            item.get("orgaoJulgador") or {}
        )

        values = {
            "tribunal": "TJMT",
            "data_ajuizamento": parse_data_ajuizamento(
                item.get("dataAjuizamento")
            ),
            "grau": item.get("grau"),
            "classe_nome": classe.get("nome"),
            "orgao_julgador_nome": (
                orgao_julgador.get("nome")
            ),
            "assuntos": item.get("assuntos"),
            "raw_source": item,
        }

        existing = existing_by_number.get(
            numero_processo
        )

        if existing:
            existing.tribunal = values["tribunal"]
            existing.data_ajuizamento = (
                values["data_ajuizamento"]
            )
            existing.grau = values["grau"]
            existing.classe_nome = (
                values["classe_nome"]
            )
            existing.orgao_julgador_nome = (
                values["orgao_julgador_nome"]
            )
            existing.assuntos = values["assuntos"]
            existing.raw_source = (
                values["raw_source"]
            )

            updated += 1

        else:
            record = ProcessRecord(
                numero_processo=numero_processo,
                **values,
            )

            db.add(record)

            # Também registra imediatamente no mapa local.
            # Assim evitamos duplicidade durante o mesmo lote.
            existing_by_number[numero_processo] = record

            saved_new += 1

    db.commit()

    return saved_new, updated


@router.post(
    "/preview",
    response_model=PreviewSearchResponse,
)
async def preview_search(
    request: PreviewSearchRequest,
    _user: dict = Depends(current_user),
    settings: Settings = Depends(get_settings),
):
    client = DataJudClient(settings)

    return await client.preview_tjmt(
        date_from=request.date_from,
        date_to=request.date_to,
        subject_text=request.subject_text,
        limit=request.limit,
    )


@router.post(
    "/collect",
    response_model=CollectSearchResponse,
)
async def collect_search(
    request: CollectSearchRequest,
    _user: dict = Depends(current_user),
    settings: Settings = Depends(get_settings),
    db: Session = Depends(get_db),
):
    search_run = SearchRun(
        tribunal="TJMT",
        date_from=request.date_from,
        date_to=request.date_to,
        subject_text=request.subject_text,
        status="running",
    )

    db.add(search_run)
    db.commit()
    db.refresh(search_run)

    client = DataJudClient(settings)

    search_after = None

    total_found = 0
    saved_new = 0
    updated = 0
    pages = 0

    try:
        while True:
            page = await client.fetch_tjmt_page(
                date_from=request.date_from,
                date_to=request.date_to,
                subject_text=request.subject_text,
                limit=request.batch_size,
                search_after=search_after,
            )

            if pages == 0:
                total_found = page["total"]

                search_run.total_found = (
                    total_found
                )

                db.commit()

            items = page["items"]

            if not items:
                break

            new_count, updated_count = (
                save_process_page(
                    db=db,
                    items=items,
                )
            )

            saved_new += new_count
            updated += updated_count
            pages += 1

            next_search_after = page[
                "next_search_after"
            ]

            if not next_search_after:
                break

            if next_search_after == search_after:
                raise RuntimeError(
                    "A paginação do DataJud "
                    "não avançou."
                )

            search_after = next_search_after

            if len(items) < request.batch_size:
                break

        search_run.status = "completed"
        search_run.total_found = total_found

        db.commit()

        return {
            "search_run_id": search_run.id,
            "status": "completed",
            "total_found": total_found,
            "saved_new": saved_new,
            "updated": updated,
            "pages": pages,
        }

    except Exception as exc:
        # Qualquer erro de banco deixa a transação atual inválida.
        # Precisamos desfazê-la antes de continuar usando a sessão.
        db.rollback()

        search_run.status = "failed"
        db.commit()

        if isinstance(exc, HTTPException):
            raise

        raise HTTPException(
            status_code=500,
            detail=(
                "Falha durante a coleta: "
                f"{exc}"
            ),
        ) from exc
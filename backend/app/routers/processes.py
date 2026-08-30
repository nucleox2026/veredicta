from datetime import date, datetime, time

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import ProcessAnalysis, ProcessRecord

from ..services.legal_ai import VeredictaLegalAI
from ..settings import Settings, get_settings


router = APIRouter(
    prefix="/api/v1/processes",
    tags=["processes"],
)

def extract_parties(
    raw_source: dict,
) -> dict:
    result = {
        "ativo": [],
        "passivo": [],
        "outros": [],
    }

    if not isinstance(
        raw_source,
        dict,
    ):
        return result

    def normalize_party(
        item,
        default_polo=None,
    ):
        if isinstance(item, str):
            return {
                "nome": item,
                "documento": None,
                "tipo_pessoa": None,
            }

        if not isinstance(item, dict):
            return None

        nome = (
            item.get("nome")
            or item.get("nomeParte")
            or item.get("razaoSocial")
            or item.get("nomePessoa")
        )

        documento = (
            item.get("cpfCnpj")
            or item.get("cnpj")
            or item.get("cpf")
            or item.get("documento")
        )

        tipo_pessoa = (
            item.get("tipoPessoa")
            or item.get("tipo_pessoa")
        )

        if not nome and not documento:
            return None

        return {
            "nome": nome,
            "documento": documento,
            "tipo_pessoa": tipo_pessoa,
        }

    key_map = {
        "poloAtivo": "ativo",
        "polo_ativo": "ativo",
        "ativo": "ativo",

        "poloPassivo": "passivo",
        "polo_passivo": "passivo",
        "passivo": "passivo",

        "partes": "outros",
        "participantes": "outros",
    }

    for source_key, target_key in key_map.items():
        value = raw_source.get(
            source_key
        )

        if not value:
            continue

        if not isinstance(
            value,
            list,
        ):
            value = [value]

        for item in value:
            normalized = normalize_party(
                item
            )

            if normalized:
                result[target_key].append(
                    normalized
                )

    return result

@router.get("")
def list_processes(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=25, ge=1, le=100),

    search: str | None = Query(
        default=None,
        description="Busca por número, classe ou órgão julgador",
    ),

    date_from: date | None = Query(
        default=None,
        description="Data inicial de ajuizamento",
    ),

    date_to: date | None = Query(
        default=None,
        description="Data final de ajuizamento",
    ),

    grau: str | None = Query(
        default=None,
        description="Ex.: G1, G2, JE",
    ),

    classe: str | None = Query(
        default=None,
        description="Parte do nome da classe processual",
    ),

    orgao_julgador: str | None = Query(
        default=None,
        description="Parte do nome do órgão julgador",
    ),

    _user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    filters = []

    if search:
        term = f"%{search.strip()}%"

        filters.append(
            or_(
                ProcessRecord.numero_processo.ilike(term),
                ProcessRecord.classe_nome.ilike(term),
                ProcessRecord.orgao_julgador_nome.ilike(term),
            )
        )

    if date_from:
        filters.append(
            ProcessRecord.data_ajuizamento
            >= datetime.combine(
                date_from,
                time.min,
            )
        )

    if date_to:
        filters.append(
            ProcessRecord.data_ajuizamento
            <= datetime.combine(
                date_to,
                time.max,
            )
        )

    if grau:
        filters.append(
            ProcessRecord.grau == grau.strip()
        )

    if classe:
        filters.append(
            ProcessRecord.classe_nome.ilike(
                f"%{classe.strip()}%"
            )
        )

    if orgao_julgador:
        filters.append(
            ProcessRecord.orgao_julgador_nome.ilike(
                f"%{orgao_julgador.strip()}%"
            )
        )

    query = select(ProcessRecord)

    count_query = select(
        func.count(ProcessRecord.id)
    )

    if filters:
        query = query.where(*filters)
        count_query = count_query.where(*filters)

    total = db.scalar(count_query) or 0

    offset = (page - 1) * page_size

    records = db.scalars(
        query
        .order_by(
            ProcessRecord.data_ajuizamento.desc()
        )
        .offset(offset)
        .limit(page_size)
    ).all()

    items = []

    for record in records:
        items.append(
            {
                "id": record.id,
                "numero_processo": (
                    record.numero_processo
                ),
                "tribunal": record.tribunal,
                "data_ajuizamento": (
                    record.data_ajuizamento
                ),
                "grau": record.grau,
                "classe": record.classe_nome,
                "orgao_julgador": (
                    record.orgao_julgador_nome
                ),
                "assuntos": record.assuntos,
            }
        )

    pages = (
        (total + page_size - 1)
        // page_size
        if total
        else 0
    )

    return {
        "total": total,
        "page": page,
        "page_size": page_size,
        "pages": pages,
        "filters": {
            "search": search,
            "date_from": date_from,
            "date_to": date_to,
            "grau": grau,
            "classe": classe,
            "orgao_julgador": orgao_julgador,
        },
        "items": items,
    }

@router.get("/{process_id}")
def get_process(
    process_id: int,
    _user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    record = db.get(
        ProcessRecord,
        process_id,
    )

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Processo não encontrado.",
        )

    raw_source = (
        record.raw_source
        if isinstance(
            record.raw_source,
            dict,
        )
        else {}
    )

    return {
        "id": record.id,
        "numero_processo": (
            record.numero_processo
        ),
        "tribunal": record.tribunal,
        "data_ajuizamento": (
            record.data_ajuizamento
        ),
        "grau": record.grau,
        "classe": (
            record.classe_nome
        ),
        "orgao_julgador": (
            record.orgao_julgador_nome
        ),
        "assuntos": (
            record.assuntos or []
        ),
        "partes": extract_parties(
            raw_source
        ),
        "movimentos": (
            raw_source.get(
                "movimentos",
                [],
            )
        ),
        "dados_datajud": (
            raw_source
        ),
    }

def analysis_to_dict(
    analysis: ProcessAnalysis,
):
    return {
        "id":
            analysis.id,

        "numero_processo":
            analysis.numero_processo,

        "dano_moral":
            analysis.dano_moral,

        "direito_personalidade":
            analysis.direito_personalidade,

        "empresa_re":
            analysis.empresa_re,

        "resultado":
            analysis.resultado,

        "valor_indenizacao_centavos":
            analysis.valor_indenizacao_centavos,

        "resumo":
            analysis.resumo,

        "fundamentos":
            analysis.fundamentos,

        "confianca":
            analysis.confianca,

        "model_name":
            analysis.model_name,

        "created_at":
            analysis.created_at,
    }

@router.get("/{process_id}/analysis")
def get_process_analysis(
    process_id: int,
    _user: dict = Depends(current_user),
    db: Session = Depends(get_db),
):
    record = db.get(
        ProcessRecord,
        process_id,
    )

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Processo não encontrado.",
        )

    analysis = db.scalar(
        select(ProcessAnalysis)
        .where(
            ProcessAnalysis.numero_processo
            == record.numero_processo
        )
    )

    if not analysis:
        raise HTTPException(
            status_code=404,
            detail="Processo ainda não analisado.",
        )

    return analysis_to_dict(
        analysis
    )

@router.post("/{process_id}/analyze")
def analyze_process(
    process_id: int,

    force: bool = Query(
        default=False
    ),

    _user: dict = Depends(current_user),

    db: Session = Depends(get_db),

    settings: Settings = Depends(
        get_settings
    ),
):
    # 1. Localiza o processo
    record = db.get(
        ProcessRecord,
        process_id,
    )

    if not record:
        raise HTTPException(
            status_code=404,
            detail="Processo não encontrado.",
        )

    # 2. Verifica se já existe análise
    existing = db.scalar(
        select(ProcessAnalysis)
        .where(
            ProcessAnalysis.numero_processo
            == record.numero_processo
        )
    )

    # Se já existe e force=false,
    # devolvemos o banco sem chamar IA.
    if existing and not force:
        return analysis_to_dict(
            existing
        )

    # 3. Escolhe o provedor de IA
    if settings.ai_provider == "gemini":

        if not settings.gemini_api_key:
            raise HTTPException(
                status_code=503,
                detail=(
                    "GEMINI_API_KEY "
                    "não configurada."
                ),
            )

        ai_api_key = (
            settings.gemini_api_key
        )

        ai_model = (
            settings.gemini_model
        )

    elif settings.ai_provider == "openai":

        if not settings.openai_api_key:
            raise HTTPException(
                status_code=503,
                detail=(
                    "OPENAI_API_KEY "
                    "não configurada."
                ),
            )

        ai_api_key = (
            settings.openai_api_key
        )

        ai_model = (
            settings.openai_model
        )

    else:
        raise HTTPException(
            status_code=500,
            detail=(
                "Provedor de IA não suportado: "
                f"{settings.ai_provider}"
            ),
        )

    # 4. Prepara os dados
    raw_source = (
        record.raw_source
        if isinstance(
            record.raw_source,
            dict,
        )
        else {}
    )

    movimentos = raw_source.get(
        "movimentos",
        [],
    )

    ai_payload = {
        "numero_processo":
            record.numero_processo,

        "tribunal":
            record.tribunal,

        "data_ajuizamento":
            record.data_ajuizamento,

        "grau":
            record.grau,

        "classe":
            record.classe_nome,

        "orgao_julgador":
            record.orgao_julgador_nome,

        "assuntos":
            record.assuntos or [],

        "partes":
            extract_parties(
                raw_source
            ),

        "movimentos":
            movimentos[:100],
    }

    # 5. Executa o agente
    agent = VeredictaLegalAI(
        api_key=ai_api_key,
        model=ai_model,
    )

    try:
        result = agent.analyze_process(
            ai_payload
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Falha na análise com IA: "
                f"{exc}"
            ),
        ) from exc

    # 6. Dados que serão persistidos
    values = {
        "dano_moral":
            result.dano_moral,

        "direito_personalidade":
            result.direito_personalidade,

        "empresa_re":
            result.empresa_re,

        "resultado":
            result.resultado,

        "valor_indenizacao_centavos":
            result.valor_indenizacao_centavos,

        "resumo":
            result.resumo,

        "fundamentos": {
            "itens":
                result.fundamentos,

            "limitacoes":
                result.limitacoes,
        },

        "confianca":
            result.confianca,

        "model_name":
            ai_model,
    }

    # 7. Atualiza ou cria a análise
    if existing:

        for key, value in values.items():
            setattr(
                existing,
                key,
                value,
            )

        analysis = existing

    else:
        analysis = ProcessAnalysis(
            numero_processo=
                record.numero_processo,

            **values,
        )

        db.add(analysis)

    db.commit()
    db.refresh(analysis)

    return analysis_to_dict(
        analysis
    )
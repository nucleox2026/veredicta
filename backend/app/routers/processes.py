from datetime import date, datetime, time, timezone

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import (
    ProcessAnalysis,
    ProcessRecord,
)
from ..services.datajud_multi import (
    DataJudError,
    DataJudMultiClient,
)
from ..services.legal_ai import (
    PROMPT_VERSION,
    VeredictaLegalAI,
)
from ..services.legal_evidence import (
    extract_legal_evidence,
)
from ..services.tribunals import (
    get_tribunal,
    normalize_tribunal,
)
from ..settings import (
    Settings,
    get_settings,
)


router = APIRouter(
    prefix="/api/v1/processes",
    tags=["processes"],
)


# =========================================================
# UTILITÁRIOS
# =========================================================


def extract_parties(
    raw_source: dict,
) -> dict:
    """
    Tenta extrair polos e participantes
    quando essas informações estiverem
    disponíveis no retorno do DataJud.
    """

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
    ):
        if isinstance(
            item,
            str,
        ):
            return {
                "nome": item,
                "documento": None,
                "tipo_pessoa": None,
            }

        if not isinstance(
            item,
            dict,
        ):
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

    for (
        source_key,
        target_key,
    ) in key_map.items():

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
            normalized = (
                normalize_party(
                    item
                )
            )

            if normalized:
                result[
                    target_key
                ].append(
                    normalized
                )

    return result


def compact_movements(
    movements: list[dict],
    limit: int = 30,
) -> list[dict]:
    """
    Compacta movimentações para
    exibição na interface.

    O DataJud continua fornecendo
    todas as movimentações para o
    backend, mas a ficha exibe apenas
    as mais recentes.
    """

    compacted = []

    for movement in movements[:limit]:

        if not isinstance(
            movement,
            dict,
        ):
            continue

        orgao = (
            movement.get(
                "orgaoJulgador"
            )
            or {}
        )

        complements = []

        for complemento in (
            movement.get(
                "complementosTabelados"
            )
            or []
        ):
            if not isinstance(
                complemento,
                dict,
            ):
                continue

            complements.append(
                {
                    "nome": (
                        complemento.get(
                            "nome"
                        )
                    ),
                    "descricao": (
                        complemento.get(
                            "descricao"
                        )
                    ),
                }
            )

        compacted.append(
            {
                "codigo": (
                    movement.get(
                        "codigo"
                    )
                ),

                "data_hora": (
                    movement.get(
                        "dataHora"
                    )
                ),

                "nome": (
                    movement.get(
                        "nome"
                    )
                ),

                "orgao_julgador": (
                    orgao.get("nome")
                    if isinstance(
                        orgao,
                        dict,
                    )
                    else None
                ),

                "complementos": (
                    complements
                ),
            }
        )

    return compacted


def normalize_process_number(
    value: str,
) -> str:
    """
    Converte número CNJ formatado
    ou não para somente dígitos.
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


def analysis_to_dict(
    analysis: ProcessAnalysis,
) -> dict:
    """
    Converte uma análise armazenada
    no banco para resposta JSON.
    """

    fundamentos = (
        analysis.fundamentos
    )

    limitacoes = []

    if isinstance(
        fundamentos,
        dict,
    ):
        limitacoes = (
            fundamentos.get(
                "limitacoes"
            )
            or []
        )

        fundamentos_publicos = (
            fundamentos.get(
                "itens"
            )
            or []
        )

    else:
        fundamentos_publicos = (
            fundamentos
            or []
        )

    return {
        "id": (
            analysis.id
        ),

        "tribunal": (
            analysis.tribunal
        ),

        "numero_processo": (
            analysis.numero_processo
        ),

        "dano_moral": (
            analysis.dano_moral
        ),

        "direito_personalidade": (
            analysis.direito_personalidade
        ),

        "empresa_re": (
            analysis.empresa_re
        ),

        "resultado": (
            analysis.resultado
        ),

        "valor_indenizacao_centavos": (
            analysis
            .valor_indenizacao_centavos
        ),

        "valor_arbitrado_juiz_centavos": (
            analysis
            .valor_arbitrado_juiz_centavos
        ),

        "fonte_valor_arbitrado": (
            analysis
            .fonte_valor_arbitrado
        ),

        "confianca_resultado": (
            analysis
            .confianca_resultado
        ),

        "confianca_valor": (
            analysis
            .confianca_valor
        ),

        "valor_primeiro_grau_centavos": (
            analysis
            .valor_primeiro_grau_centavos
        ),

        "valor_final_centavos": (
            analysis
            .valor_final_centavos
        ),

        "situacao_valor": (
            analysis
            .situacao_valor
        ),

        "fonte_valor": (
            analysis
            .fonte_valor
        ),

        "evidencias_resultado": (
            analysis
            .evidencias_resultado
            or []
        ),

        "evidencias_valor": (
            analysis
            .evidencias_valor
            or []
        ),

        "prompt_version": (
            analysis
            .prompt_version
        ),

        "analyzed_at": (
            analysis
            .analyzed_at
        ),

        "resumo": (
            analysis.resumo
        ),

        "fundamentos": (
            fundamentos_publicos
        ),

        "limitacoes": (
            limitacoes
        ),

        "confianca": (
            analysis.confianca
        ),

        "model_name": (
            analysis.model_name
        ),

        "created_at": (
            analysis.created_at
        ),
    }


def get_ai_configuration(
    settings: Settings,
) -> tuple[str, str]:
    """
    Resolve chave e modelo conforme
    o provedor configurado.
    """

    if (
        settings.ai_provider
        == "gemini"
    ):
        if not settings.gemini_api_key:
            raise HTTPException(
                status_code=503,
                detail=(
                    "GEMINI_API_KEY "
                    "não configurada."
                ),
            )

        return (
            settings.gemini_api_key,
            settings.gemini_model,
        )

    if (
        settings.ai_provider
        == "openai"
    ):
        if not settings.openai_api_key:
            raise HTTPException(
                status_code=503,
                detail=(
                    "OPENAI_API_KEY "
                    "não configurada."
                ),
            )

        return (
            settings.openai_api_key,
            settings.openai_model,
        )

    raise HTTPException(
        status_code=500,
        detail=(
            "Provedor de IA não suportado: "
            f"{settings.ai_provider}"
        ),
    )


# =========================================================
# ROTAS ANTIGAS — PROCESSOS SALVOS
# =========================================================
#
# Mantidas temporariamente para não quebrar
# a versão anterior durante a migração.
# =========================================================


@router.get("")
def list_processes(
    page: int = Query(
        default=1,
        ge=1,
    ),

    page_size: int = Query(
        default=25,
        ge=1,
        le=100,
    ),

    search: str | None = Query(
        default=None,
        description=(
            "Busca por número, classe "
            "ou órgão julgador"
        ),
    ),

    date_from: date | None = Query(
        default=None,
        description=(
            "Data inicial de ajuizamento"
        ),
    ),

    date_to: date | None = Query(
        default=None,
        description=(
            "Data final de ajuizamento"
        ),
    ),

    grau: str | None = Query(
        default=None,
        description="Ex.: G1, G2, JE",
    ),

    classe: str | None = Query(
        default=None,
        description=(
            "Parte do nome da "
            "classe processual"
        ),
    ),

    orgao_julgador: str | None = Query(
        default=None,
        description=(
            "Parte do nome do "
            "órgão julgador"
        ),
    ),

    _user: dict = Depends(
        current_user
    ),

    db: Session = Depends(
        get_db
    ),
):
    filters = []

    if search:
        term = (
            f"%{search.strip()}%"
        )

        filters.append(
            or_(
                ProcessRecord
                .numero_processo
                .ilike(term),

                ProcessRecord
                .classe_nome
                .ilike(term),

                ProcessRecord
                .orgao_julgador_nome
                .ilike(term),
            )
        )

    if date_from:
        filters.append(
            ProcessRecord
            .data_ajuizamento
            >= datetime.combine(
                date_from,
                time.min,
            )
        )

    if date_to:
        filters.append(
            ProcessRecord
            .data_ajuizamento
            <= datetime.combine(
                date_to,
                time.max,
            )
        )

    if grau:
        filters.append(
            ProcessRecord.grau
            == grau.strip()
        )

    if classe:
        filters.append(
            ProcessRecord
            .classe_nome
            .ilike(
                f"%{classe.strip()}%"
            )
        )

    if orgao_julgador:
        filters.append(
            ProcessRecord
            .orgao_julgador_nome
            .ilike(
                f"%{orgao_julgador.strip()}%"
            )
        )

    query = select(
        ProcessRecord
    )

    count_query = select(
        func.count(
            ProcessRecord.id
        )
    )

    if filters:
        query = query.where(
            *filters
        )

        count_query = (
            count_query.where(
                *filters
            )
        )

    total = (
        db.scalar(
            count_query
        )
        or 0
    )

    offset = (
        page - 1
    ) * page_size

    records = db.scalars(
        query
        .order_by(
            ProcessRecord
            .data_ajuizamento
            .desc()
        )
        .offset(offset)
        .limit(page_size)
    ).all()

    items = []

    for record in records:
        items.append(
            {
                "id": (
                    record.id
                ),

                "numero_processo": (
                    record
                    .numero_processo
                ),

                "tribunal": (
                    record.tribunal
                ),

                "data_ajuizamento": (
                    record
                    .data_ajuizamento
                ),

                "grau": (
                    record.grau
                ),

                "classe": (
                    record.classe_nome
                ),

                "orgao_julgador": (
                    record
                    .orgao_julgador_nome
                ),

                "assuntos": (
                    record.assuntos
                ),
            }
        )

    pages = (
        (
            total
            + page_size
            - 1
        )
        // page_size

        if total
        else 0
    )

    return {
        "total": total,

        "page": page,

        "page_size": (
            page_size
        ),

        "pages": pages,

        "filters": {
            "search": search,
            "date_from": date_from,
            "date_to": date_to,
            "grau": grau,
            "classe": classe,
            "orgao_julgador": (
                orgao_julgador
            ),
        },

        "items": items,
    }


# =========================================================
# NOVA ARQUITETURA — CONSULTA SOB DEMANDA
# =========================================================


@router.get(
    "/lookup/{tribunal}/{numero_processo}"
)
def lookup_process(
    tribunal: str,
    numero_processo: str,

    _user: dict = Depends(
        current_user
    ),
):
    """
    Consulta o processo diretamente
    no DataJud.

    Não salva ProcessRecord.
    """

    sigla = normalize_tribunal(
        tribunal
    )

    try:
        get_tribunal(
            sigla
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    try:
        client = (
            DataJudMultiClient()
        )

        result = (
            client.get_process(
                tribunal=sigla,
                numero_processo=(
                    numero_processo
                ),
            )
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

    if not result["found"]:
        raise HTTPException(
            status_code=404,
            detail=(
                "Processo não encontrado "
                "no DataJud."
            ),
        )

    source = (
        result["raw_source"]
        or {}
    )

    classe = (
        source.get("classe")
        or {}
    )

    orgao = (
        source.get(
            "orgaoJulgador"
        )
        or source.get(
            "orgao_julgador"
        )
        or {}
    )

    if isinstance(
        classe,
        dict,
    ):
        classe_nome = (
            classe.get("nome")
        )

    elif isinstance(
        classe,
        str,
    ):
        classe_nome = classe

    else:
        classe_nome = None

    if isinstance(
        orgao,
        dict,
    ):
        orgao_nome = (
            orgao.get("nome")
        )

    elif isinstance(
        orgao,
        str,
    ):
        orgao_nome = orgao

    else:
        orgao_nome = None

    movimentos = (
        source.get(
            "movimentos"
        )
        or []
    )

    return {
        "id": None,

        "tribunal": sigla,

        "numero_processo": (
            result[
                "numero_processo"
            ]
        ),

        "data_ajuizamento": (
            source.get(
                "dataAjuizamento"
            )
        ),

        "grau": (
            source.get("grau")
        ),

        "classe_nome": (
            classe_nome
        ),

        "orgao_julgador_nome": (
            orgao_nome
        ),

        "assuntos": (
            source.get(
                "assuntos"
            )
            or []
        ),

        "partes": (
            extract_parties(
                source
            )
        ),

        "movimentos_total": (
            len(movimentos)
        ),

        "movimentos_exibidos": (
            min(
                len(movimentos),
                30,
            )
        ),

        "movimentos": (
            compact_movements(
                movimentos,
                limit=30,
            )
        ),

        "total_ocorrencias_datajud": (
            result[
                "total_ocorrencias"
            ]
        ),

        "fonte": "DataJud",
    }


# =========================================================
# NOVA ARQUITETURA — CONSULTA ANÁLISE SALVA
# =========================================================


@router.get(
    "/lookup/{tribunal}/{numero_processo}/analysis"
)
def get_lookup_process_analysis(
    tribunal: str,
    numero_processo: str,

    _user: dict = Depends(
        current_user
    ),

    db: Session = Depends(
        get_db
    ),
):
    """
    Consulta somente o banco.

    Não chama DataJud.
    Não chama IA.
    """

    sigla = normalize_tribunal(
        tribunal
    )

    try:
        get_tribunal(
            sigla
        )

        numero = (
            normalize_process_number(
                numero_processo
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    analysis = db.scalar(
        select(
            ProcessAnalysis
        )
        .where(
            ProcessAnalysis.tribunal
            == sigla,

            ProcessAnalysis.numero_processo
            == numero,
        )
    )

    if not analysis:
        raise HTTPException(
            status_code=404,
            detail=(
                "Processo ainda "
                "não analisado."
            ),
        )

    return analysis_to_dict(
        analysis
    )


# =========================================================
# NOVA ARQUITETURA — ANÁLISE IA SOB DEMANDA
# =========================================================


@router.post(
    "/lookup/{tribunal}/{numero_processo}/analyze"
)
def analyze_lookup_process(
    tribunal: str,
    numero_processo: str,

    force: bool = Query(
        default=False
    ),

    _user: dict = Depends(
        current_user
    ),

    db: Session = Depends(
        get_db
    ),

    settings: Settings = Depends(
        get_settings
    ),
):
    """
    Analisa um processo sob demanda.

    Se já existir análise e force=False:
    retorna a análise armazenada.

    Se não existir:
    consulta DataJud, chama IA e
    salva somente ProcessAnalysis.
    """

    # -----------------------------------------------------
    # 1. Validação
    # -----------------------------------------------------

    sigla = normalize_tribunal(
        tribunal
    )

    try:
        get_tribunal(
            sigla
        )

        numero = (
            normalize_process_number(
                numero_processo
            )
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    # -----------------------------------------------------
    # 2. Cache
    # -----------------------------------------------------

    existing = db.scalar(
        select(
            ProcessAnalysis
        )
        .where(
            ProcessAnalysis.tribunal
            == sigla,

            ProcessAnalysis.numero_processo
            == numero,
        )
    )

    if (
        existing
        and not force
    ):
        return analysis_to_dict(
            existing
        )

    # -----------------------------------------------------
    # 3. Consulta DataJud
    # -----------------------------------------------------

    try:
        client = (
            DataJudMultiClient()
        )

        datajud_result = (
            client.get_process(
                tribunal=sigla,
                numero_processo=numero,
            )
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

    if not datajud_result[
        "found"
    ]:
        raise HTTPException(
            status_code=404,
            detail=(
                "Processo não encontrado "
                "no DataJud."
            ),
        )

    source = (
        datajud_result[
            "raw_source"
        ]
        or {}
    )

    # -----------------------------------------------------
    # 4. Configuração IA
    # -----------------------------------------------------

    (
        ai_api_key,
        ai_model,
    ) = get_ai_configuration(
        settings
    )

    # -----------------------------------------------------
    # 5. Dados processuais
    # -----------------------------------------------------

    classe = (
        source.get("classe")
        or {}
    )

    orgao = (
        source.get(
            "orgaoJulgador"
        )
        or source.get(
            "orgao_julgador"
        )
        or {}
    )

    if isinstance(
        classe,
        dict,
    ):
        classe_nome = (
            classe.get("nome")
        )

    elif isinstance(
        classe,
        str,
    ):
        classe_nome = classe

    else:
        classe_nome = None

    if isinstance(
        orgao,
        dict,
    ):
        orgao_nome = (
            orgao.get("nome")
        )

    elif isinstance(
        orgao,
        str,
    ):
        orgao_nome = orgao

    else:
        orgao_nome = None

    movimentos = (
        source.get(
            "movimentos"
        )
        or []
    )

    # -----------------------------------------------------
    # 6. Contexto para IA
    # -----------------------------------------------------

    ai_payload = {
        "numero_processo": (
            numero
        ),

        "tribunal": (
            sigla
        ),

        "data_ajuizamento": (
            source.get(
                "dataAjuizamento"
            )
        ),

        "grau": (
            source.get("grau")
        ),

        "classe": (
            classe_nome
        ),

        "orgao_julgador": (
            orgao_nome
        ),

        "assuntos": (
            source.get(
                "assuntos"
            )
            or []
        ),

        "partes": (
            extract_parties(
                source
            )
        ),

        # A ficha mostra apenas 30,
        # mas a IA pode receber até 100.
        "movimentos": (
            movimentos[:100]
        ),

        "evidencias_veredicta": (
            extract_legal_evidence(
                source
            )
        ),
    }

    # -----------------------------------------------------
    # 7. Executa IA
    # -----------------------------------------------------

    agent = VeredictaLegalAI(
        api_key=ai_api_key,
        model=ai_model,
    )

    try:
        ai_result = (
            agent.analyze_process(
                ai_payload
            )
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Falha na análise "
                "com IA: "
                f"{exc}"
            ),
        ) from exc

    # -----------------------------------------------------
    # 8. Dados persistidos
    # -----------------------------------------------------

    values = {
        "tribunal": (
            sigla
        ),

        "dano_moral": (
            ai_result.dano_moral
        ),

        "direito_personalidade": (
            ai_result
            .direito_personalidade
        ),

        "empresa_re": (
            ai_result.empresa_re
        ),

        "resultado": (
            ai_result.resultado
        ),

        # Compatibilidade temporária com os
        # campos da interface anterior.
        "valor_indenizacao_centavos": (
            ai_result
            .valor_primeiro_grau_centavos
        ),

        "valor_arbitrado_juiz_centavos": (
            ai_result
            .valor_primeiro_grau_centavos
        ),

        "fonte_valor_arbitrado": (
            ai_result
            .fonte_valor
        ),

        "confianca_resultado": (
            ai_result
            .confianca_resultado
        ),

        "confianca_valor": (
            ai_result
            .confianca_valor
        ),

        "valor_primeiro_grau_centavos": (
            ai_result
            .valor_primeiro_grau_centavos
        ),

        "valor_final_centavos": (
            ai_result
            .valor_final_centavos
        ),

        "situacao_valor": (
            ai_result
            .situacao_valor
        ),

        "fonte_valor": (
            ai_result
            .fonte_valor
        ),

        "evidencias_resultado": (
            ai_payload[
                "evidencias_veredicta"
            ].get(
                "evidencias_resultado",
                [],
            )
        ),

        "evidencias_valor": (
            ai_payload[
                "evidencias_veredicta"
            ].get(
                "mencoes_monetarias",
                [],
            )
        ),

        "prompt_version": (
            PROMPT_VERSION
        ),

        "analyzed_at": (
            datetime.now(
                timezone.utc
            )
        ),

        "resumo": (
            ai_result.resumo
        ),

        "fundamentos": {
            "itens": (
                ai_result.fundamentos
            ),

            "limitacoes": (
                ai_result.limitacoes
            ),
        },

        "confianca": (
            ai_result.confianca
        ),

        "model_name": (
            ai_model
        ),
    }

    # -----------------------------------------------------
    # 9. Salva SOMENTE ProcessAnalysis
    # -----------------------------------------------------

    try:
        if existing:

            for (
                key,
                value,
            ) in values.items():

                setattr(
                    existing,
                    key,
                    value,
                )

            analysis = existing

        else:
            analysis = (
                ProcessAnalysis(
                    numero_processo=(
                        numero
                    ),
                    **values,
                )
            )

            db.add(
                analysis
            )

        db.commit()

        db.refresh(
            analysis
        )

    except Exception:
        db.rollback()
        raise

    return analysis_to_dict(
        analysis
    )


# =========================================================
# ROTAS ANTIGAS — DETALHE POR ID
# =========================================================


@router.get(
    "/{process_id}"
)
def get_process(
    process_id: int,

    _user: dict = Depends(
        current_user
    ),

    db: Session = Depends(
        get_db
    ),
):
    record = db.get(
        ProcessRecord,
        process_id,
    )

    if not record:
        raise HTTPException(
            status_code=404,
            detail=(
                "Processo não encontrado."
            ),
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
        "id": (
            record.id
        ),

        "numero_processo": (
            record.numero_processo
        ),

        "tribunal": (
            record.tribunal
        ),

        "data_ajuizamento": (
            record.data_ajuizamento
        ),

        "grau": (
            record.grau
        ),

        "classe": (
            record.classe_nome
        ),

        "orgao_julgador": (
            record
            .orgao_julgador_nome
        ),

        "assuntos": (
            record.assuntos
            or []
        ),

        "partes": (
            extract_parties(
                raw_source
            )
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


# =========================================================
# ROTA ANTIGA — ANÁLISE POR ID
# =========================================================


@router.get(
    "/{process_id}/analysis"
)
def get_process_analysis(
    process_id: int,

    _user: dict = Depends(
        current_user
    ),

    db: Session = Depends(
        get_db
    ),
):
    record = db.get(
        ProcessRecord,
        process_id,
    )

    if not record:
        raise HTTPException(
            status_code=404,
            detail=(
                "Processo não encontrado."
            ),
        )

    analysis = db.scalar(
        select(
            ProcessAnalysis
        )
        .where(
            ProcessAnalysis.tribunal
            == record.tribunal,

            ProcessAnalysis.numero_processo
            == record.numero_processo,
        )
    )

    if not analysis:
        raise HTTPException(
            status_code=404,
            detail=(
                "Processo ainda "
                "não analisado."
            ),
        )

    return analysis_to_dict(
        analysis
    )


# =========================================================
# ROTA ANTIGA — ANALISAR PROCESSO SALVO
# =========================================================


@router.post(
    "/{process_id}/analyze"
)
def analyze_process(
    process_id: int,

    force: bool = Query(
        default=False
    ),

    _user: dict = Depends(
        current_user
    ),

    db: Session = Depends(
        get_db
    ),

    settings: Settings = Depends(
        get_settings
    ),
):
    # -----------------------------------------------------
    # 1. Localiza processo salvo
    # -----------------------------------------------------

    record = db.get(
        ProcessRecord,
        process_id,
    )

    if not record:
        raise HTTPException(
            status_code=404,
            detail=(
                "Processo não encontrado."
            ),
        )

    # -----------------------------------------------------
    # 2. Procura análise
    # -----------------------------------------------------

    existing = db.scalar(
        select(
            ProcessAnalysis
        )
        .where(
            ProcessAnalysis.tribunal
            == record.tribunal,

            ProcessAnalysis.numero_processo
            == record.numero_processo,
        )
    )

    if (
        existing
        and not force
    ):
        return analysis_to_dict(
            existing
        )

    # -----------------------------------------------------
    # 3. Configuração IA
    # -----------------------------------------------------

    (
        ai_api_key,
        ai_model,
    ) = get_ai_configuration(
        settings
    )

    # -----------------------------------------------------
    # 4. Dados antigos armazenados
    # -----------------------------------------------------

    raw_source = (
        record.raw_source
        if isinstance(
            record.raw_source,
            dict,
        )
        else {}
    )

    movimentos = (
        raw_source.get(
            "movimentos"
        )
        or []
    )

    ai_payload = {
        "numero_processo": (
            record.numero_processo
        ),

        "tribunal": (
            record.tribunal
        ),

        "data_ajuizamento": (
            record.data_ajuizamento
        ),

        "grau": (
            record.grau
        ),

        "classe": (
            record.classe_nome
        ),

        "orgao_julgador": (
            record
            .orgao_julgador_nome
        ),

        "assuntos": (
            record.assuntos
            or []
        ),

        "partes": (
            extract_parties(
                raw_source
            )
        ),

        "movimentos": (
            movimentos[:100]
        ),

        "evidencias_veredicta": (
            extract_legal_evidence(
                raw_source
            )
        ),
    }

    # -----------------------------------------------------
    # 5. Executa IA
    # -----------------------------------------------------

    agent = VeredictaLegalAI(
        api_key=ai_api_key,
        model=ai_model,
    )

    try:
        result = (
            agent.analyze_process(
                ai_payload
            )
        )

    except Exception as exc:
        raise HTTPException(
            status_code=502,
            detail=(
                "Falha na análise "
                "com IA: "
                f"{exc}"
            ),
        ) from exc

    # -----------------------------------------------------
    # 6. Dados persistidos
    # -----------------------------------------------------

    values = {
        "tribunal": (
            record.tribunal
        ),

        "dano_moral": (
            result.dano_moral
        ),

        "direito_personalidade": (
            result
            .direito_personalidade
        ),

        "empresa_re": (
            result.empresa_re
        ),

        "resultado": (
            result.resultado
        ),

        # Compatibilidade temporária com os
        # campos da interface anterior.
        "valor_indenizacao_centavos": (
            result
            .valor_primeiro_grau_centavos
        ),

        "valor_arbitrado_juiz_centavos": (
            result
            .valor_primeiro_grau_centavos
        ),

        "fonte_valor_arbitrado": (
            result
            .fonte_valor
        ),

        "confianca_resultado": (
            result
            .confianca_resultado
        ),

        "confianca_valor": (
            result
            .confianca_valor
        ),

        "valor_primeiro_grau_centavos": (
            result
            .valor_primeiro_grau_centavos
        ),

        "valor_final_centavos": (
            result
            .valor_final_centavos
        ),

        "situacao_valor": (
            result
            .situacao_valor
        ),

        "fonte_valor": (
            result
            .fonte_valor
        ),

        "evidencias_resultado": (
            ai_payload[
                "evidencias_veredicta"
            ].get(
                "evidencias_resultado",
                [],
            )
        ),

        "evidencias_valor": (
            ai_payload[
                "evidencias_veredicta"
            ].get(
                "mencoes_monetarias",
                [],
            )
        ),

        "prompt_version": (
            PROMPT_VERSION
        ),

        "analyzed_at": (
            datetime.now(
                timezone.utc
            )
        ),

        "resumo": (
            result.resumo
        ),

        "fundamentos": {
            "itens": (
                result.fundamentos
            ),

            "limitacoes": (
                result.limitacoes
            ),
        },

        "confianca": (
            result.confianca
        ),

        "model_name": (
            ai_model
        ),
    }

    # -----------------------------------------------------
    # 7. Atualiza/cria análise
    # -----------------------------------------------------

    try:
        if existing:

            for (
                key,
                value,
            ) in values.items():

                setattr(
                    existing,
                    key,
                    value,
                )

            analysis = existing

        else:
            analysis = (
                ProcessAnalysis(
                    numero_processo=(
                        record
                        .numero_processo
                    ),
                    **values,
                )
            )

            db.add(
                analysis
            )

        db.commit()

        db.refresh(
            analysis
        )

    except Exception:
        db.rollback()
        raise

    return analysis_to_dict(
        analysis
    )
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from fastapi import (
    APIRouter,
    Depends,
    HTTPException,
    Query,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..auth import current_user
from ..db import get_db
from ..models import ProcessAnalysis
from ..services.analysis.enrichment import build_analysis_metadata
from ..services.datajud.client import (
    DataJudError,
    DataJudMultiClient,
)
from ..services.analysis.legal_ai import (
    PROMPT_VERSION,
    VeredictaLegalAI,
)
from ..services.analysis.legal_evidence import (
    extract_legal_evidence,
)
from ..services.djen.enrichment import (
    enrich_analysis_with_djen,
    serialize_djen_analysis,
)
from ..services.djen.live_lookup import (
    lookup_live_djen,
    parse_djen_communications,
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


def merge_parties(
    primary: dict,
    secondary: dict,
) -> dict:
    """Mescla partes de DataJud e DJEN sem duplicar nomes."""
    output = {
        "ativo": [],
        "passivo": [],
        "outros": [],
    }

    for key in ("ativo", "passivo", "outros"):
        seen: set[str] = set()
        for source in (primary, secondary):
            rows = source.get(key) if isinstance(source, dict) else None
            if not isinstance(rows, list):
                continue

            for row in rows:
                if isinstance(row, str):
                    item = {
                        "nome": row,
                        "documento": None,
                        "tipo_pessoa": None,
                    }
                elif isinstance(row, dict):
                    item = {
                        "nome": row.get("nome"),
                        "documento": row.get("documento"),
                        "tipo_pessoa": row.get("tipo_pessoa"),
                        "fonte": row.get("fonte"),
                        "papel": row.get("papel"),
                    }
                else:
                    continue

                name = str(item.get("nome") or "").strip()
                if not name:
                    continue

                dedupe_key = " ".join(name.upper().split())
                if dedupe_key in seen:
                    continue

                seen.add(dedupe_key)
                output[key].append(item)

    return output


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


def money_to_centavos(value) -> int | None:
    """Converte valor monetário do DataJud (double/reais) para centavos."""
    if value is None or value == "":
        return None

    try:
        if isinstance(value, str):
            raw = value.strip().replace("R$", "").strip()
            if "," in raw:
                raw = raw.replace(".", "").replace(",", ".")
            amount = Decimal(raw)
        else:
            amount = Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None

    if amount < 0:
        return None

    return int((amount * 100).quantize(Decimal("1")))


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

    Quando o DJEN/CNJ identificou empresa(s) do polo réu com confiança
    alta, a resposta da ficha usa essa evidência oficial como prioridade.
    """
    djen_payload = serialize_djen_analysis(
        analysis
    )

    official_companies = (
        djen_payload.get(
            "empresas_re_identificadas"
        )
        if isinstance(
            djen_payload,
            dict,
        )
        else []
    ) or []

    official_company_names = []

    for item in official_companies:
        if not isinstance(
            item,
            dict,
        ):
            continue

        name = str(
            item.get("nome")
            or ""
        ).strip()

        if (
            name
            and name
            not in official_company_names
        ):
            official_company_names.append(
                name
            )

    empresa_re_resposta = (
        " / ".join(
            official_company_names
        )
        if official_company_names
        else analysis.empresa_re
    )

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
            empresa_re_resposta
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

        # Valor documental oficial, separado da inferência da IA.
        "djen": (
            djen_payload
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

    Não persiste o processo consultado.
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

    datajud_parties = extract_parties(source)
    datajud_cause_value = money_to_centavos(
        source.get("valorCausa")
        or source.get("valor_causa")
    )

    djen_live = lookup_live_djen(
        result["numero_processo"]
    )

    if (
        datajud_cause_value is not None
        and djen_live.get("valor_da_causa_centavos") is None
    ):
        djen_live["valor_da_causa_centavos"] = datajud_cause_value
        djen_live["fonte_valor_da_causa"] = "DataJud"
    djen_parties = (
        djen_live.get("partes")
        if isinstance(djen_live, dict)
        else {}
    ) or {}
    merged_parties = merge_parties(
        datajud_parties,
        djen_parties,
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

        "partes": merged_parties,

        "valor_causa_centavos": datajud_cause_value,

        "djen": djen_live,

        "djen_consulta": {
            "ok": bool(djen_live.get("ok")),
            "status": djen_live.get("status"),
            "retry_after_seconds": djen_live.get(
                "retry_after_seconds"
            ),
        },

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



@router.post(
    "/lookup/{tribunal}/{numero_processo}/djen/parse"
)
def parse_lookup_djen_communications(
    tribunal: str,
    numero_processo: str,
    payload: dict,
    _user: dict = Depends(current_user),
):
    """Interpreta comunicações do DJEN obtidas pelo próprio navegador.

    O frontend usa esta rota como fallback quando o Render não consegue acessar
    o Worker. Nenhuma chamada externa é feita aqui; apenas extração determinística
    de partes, empresa ré e valores do JSON recebido.
    """
    sigla = normalize_tribunal(tribunal)
    try:
        get_tribunal(sigla)
        numero = normalize_process_number(numero_processo)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        raise HTTPException(
            status_code=400,
            detail="Campo 'items' deve ser uma lista de comunicações DJEN.",
        )

    if len(items) > 250:
        raise HTTPException(
            status_code=400,
            detail="Máximo de 250 comunicações por interpretação.",
        )

    filtered: list[dict] = []
    for item in items:
        if not isinstance(item, dict):
            continue
        item_numero = normalize_process_number(
            str(item.get("numero_processo") or numero)
        )
        if item_numero != numero:
            continue
        filtered.append(item)

    return parse_djen_communications(filtered)


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


    analysis.lida = True
    analysis.lida_em = datetime.now(
        timezone.utc
    )
    db.commit()

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
    consulta DataJud, chama IA, salva ProcessAnalysis
    e então tenta enriquecer a análise com o DJEN/CNJ.

    Falha temporária do DJEN não invalida a análise de IA.
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
        # O botão "Analisar com IA" é uma ação manual. Mesmo quando a
        # análise jurídica já está em cache, ainda precisamos executar o
        # enriquecimento documental DJEN/CNJ para vincular empresa ré,
        # documento principal e evidências oficiais sem gastar nova chamada
        # de IA. A simples abertura da ficha continua sem consultar o DJEN.
        djen_outcome = enrich_analysis_with_djen(
            db=db,
            analysis=existing,
            numero_processo=numero,
        )

        payload = analysis_to_dict(
            existing
        )

        payload["djen_consulta"] = {
            "ok": djen_outcome.ok,
            "status": djen_outcome.status,
            "error_code": (
                djen_outcome.error_code
            ),
            "retry_after_seconds": (
                djen_outcome
                .retry_after_seconds
            ),
        }

        return payload

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


    metadata = build_analysis_metadata(
        source=source,
        empresa_re=ai_result.empresa_re,
        resumo=ai_result.resumo,
        fundamentos=ai_result.fundamentos,
        evidencias_resultado=(
            ai_payload["evidencias_veredicta"].get(
                "evidencias_resultado", []
            )
        ),
    )

    metadata_values = {
        **metadata,
        "lida": False,
        "lida_em": None,
    }

    # -----------------------------------------------------
    # 8. Dados persistidos
    # -----------------------------------------------------

    values = {
        **metadata_values,
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

    # -----------------------------------------------------
    # 10. Enriquecimento documental DJEN/CNJ
    # -----------------------------------------------------

    djen_outcome = enrich_analysis_with_djen(
        db=db,
        analysis=analysis,
        numero_processo=numero,
    )

    payload = analysis_to_dict(
        analysis
    )

    payload["djen_consulta"] = {
        "ok": djen_outcome.ok,
        "status": djen_outcome.status,
        "error_code": djen_outcome.error_code,
        "retry_after_seconds": (
            djen_outcome.retry_after_seconds
        ),
    }

    return payload

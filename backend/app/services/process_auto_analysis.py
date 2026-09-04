from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ProcessAnalysis
from ..settings import Settings
from .legal_ai import (
    PROMPT_VERSION,
    VeredictaLegalAI,
)
from .legal_evidence import (
    extract_legal_evidence,
)


AgentFactory = Callable[..., Any]


def _extract_parties(
    raw_source: dict[str, Any],
) -> dict[str, list[dict[str, Any]]]:
    result: dict[str, list[dict[str, Any]]] = {
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
        item: Any,
    ) -> dict[str, Any] | None:
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
            normalized = normalize_party(
                item
            )

            if normalized:
                result[
                    target_key
                ].append(
                    normalized
                )

    return result


def _get_ai_configuration(
    settings: Settings,
) -> tuple[str, str]:
    if (
        settings.ai_provider
        == "gemini"
    ):
        if not settings.gemini_api_key:
            raise RuntimeError(
                "GEMINI_API_KEY não configurada."
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
            raise RuntimeError(
                "OPENAI_API_KEY não configurada."
            )

        return (
            settings.openai_api_key,
            settings.openai_model,
        )

    raise RuntimeError(
        "Provedor de IA não suportado: "
        f"{settings.ai_provider}"
    )


def _name_from_value(
    value: Any,
) -> str | None:
    if isinstance(
        value,
        dict,
    ):
        return value.get(
            "nome"
        )

    if isinstance(
        value,
        str,
    ):
        return value

    return None


def build_ai_payload(
    tribunal: str,
    numero_processo: str,
    source: dict[str, Any],
) -> dict[str, Any]:
    if not isinstance(
        source,
        dict,
    ):
        source = {}

    classe_nome = _name_from_value(
        source.get("classe")
        or {}
    )

    orgao_nome = _name_from_value(
        source.get(
            "orgaoJulgador"
        )
        or source.get(
            "orgao_julgador"
        )
        or {}
    )

    movimentos = (
        source.get(
            "movimentos"
        )
        or []
    )

    if not isinstance(
        movimentos,
        list,
    ):
        movimentos = []

    return {
        "numero_processo": (
            numero_processo
        ),
        "tribunal": tribunal,
        "data_ajuizamento": (
            source.get(
                "dataAjuizamento"
            )
        ),
        "grau": (
            source.get("grau")
        ),
        "classe": classe_nome,
        "orgao_julgador": orgao_nome,
        "assuntos": (
            source.get(
                "assuntos"
            )
            or []
        ),
        "partes": _extract_parties(
            source
        ),
        "movimentos": (
            movimentos[:100]
        ),
        "evidencias_veredicta": (
            extract_legal_evidence(
                source
            )
        ),
    }


def analyze_source_and_persist(
    db: Session,
    settings: Settings,
    tribunal: str,
    numero_processo: str,
    source: dict[str, Any],
    *,
    agent_factory: AgentFactory = VeredictaLegalAI,
) -> ProcessAnalysis:
    """
    Executa a mesma modelagem jurídica usada pela análise
    sob demanda, mas recebe o raw_source que o worker já
    consultou no DataJud.

    Esta função NÃO faz commit. O worker confirma a análise
    e o estado do monitoramento na mesma transação final.
    """
    existing = db.scalar(
        select(
            ProcessAnalysis
        ).where(
            ProcessAnalysis.tribunal
            == tribunal,
            ProcessAnalysis.numero_processo
            == numero_processo,
        )
    )

    if existing is None:
        raise RuntimeError(
            "Análise automática permitida somente para "
            "processos que já existem em process_analyses."
        )

    (
        ai_api_key,
        ai_model,
    ) = _get_ai_configuration(
        settings
    )

    ai_payload = build_ai_payload(
        tribunal,
        numero_processo,
        source,
    )

    agent = agent_factory(
        api_key=ai_api_key,
        model=ai_model,
    )

    ai_result = agent.analyze_process(
        ai_payload
    )

    values = {
        "tribunal": tribunal,
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

        # Compatibilidade com a interface anterior.
        "valor_indenizacao_centavos": (
            ai_result
            .valor_primeiro_grau_centavos
        ),
        "valor_arbitrado_juiz_centavos": (
            ai_result
            .valor_primeiro_grau_centavos
        ),
        "fonte_valor_arbitrado": (
            ai_result.fonte_valor
        ),

        "confianca_resultado": (
            ai_result.confianca_resultado
        ),
        "confianca_valor": (
            ai_result.confianca_valor
        ),
        "valor_primeiro_grau_centavos": (
            ai_result
            .valor_primeiro_grau_centavos
        ),
        "valor_final_centavos": (
            ai_result.valor_final_centavos
        ),
        "situacao_valor": (
            ai_result.situacao_valor
        ),
        "fonte_valor": (
            ai_result.fonte_valor
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

    for (
        key,
        value,
    ) in values.items():
        setattr(
            existing,
            key,
            value,
        )

    db.flush()

    return existing

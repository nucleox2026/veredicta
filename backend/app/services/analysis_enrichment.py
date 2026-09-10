from __future__ import annotations

from datetime import datetime, timezone
import re
import unicodedata
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import ProcessAnalysis


CONDUCT_PATTERNS = [
    ("Negativação indevida", (
        "negativacao indevida",
        "inscricao indevida",
        "cadastro de inadimplentes",
        "serasa",
        "spc",
        "restricao indevida",
    )),
    ("Cobrança indevida", (
        "cobranca indevida",
        "cobranca abusiva",
        "debito indevido",
        "desconto indevido",
    )),
    ("Fraude", (
        "fraude",
        "fraudulento",
        "contratacao nao reconhecida",
        "contrato nao reconhecido",
        "operacao nao reconhecida",
        "golpe",
    )),
    ("Falha na prestação do serviço", (
        "falha na prestacao",
        "falha do servico",
        "falha no servico",
        "defeito na prestacao",
        "ma prestacao",
    )),
    ("Atraso ou cancelamento", (
        "atraso",
        "cancelamento",
        "voo cancelado",
        "voo atrasado",
        "entrega atrasada",
    )),
    ("Produto defeituoso", (
        "produto defeituoso",
        "produto com defeito",
        "vicio do produto",
        "defeito do produto",
    )),
    ("Vazamento ou uso indevido de dados", (
        "vazamento de dados",
        "dados pessoais",
        "uso indevido de dados",
        "lgpd",
    )),
    ("Descumprimento contratual", (
        "descumprimento contratual",
        "inadimplemento contratual",
        "quebra contratual",
    )),
]

# Códigos observados nos próprios dados DataJud já armazenados
# pelo Veredicta para decisões de mérito:
# 219 = Procedência, 220 = Improcedência,
# 221 = Procedência em Parte.
SENTENCE_MOVEMENT_CODES = {"219", "220", "221"}

SENTENCE_MOVEMENT_TERMS = (
    "sentenca",
    "procedencia",
    "improcedencia",
    "julgamento com resolucao de merito",
    "julgamento sem resolucao de merito",
    "extincao com resolucao de merito",
    "extincao sem resolucao de merito",
)


def normalize_text(value: Any) -> str:
    text = str(value if value is not None else "")
    text = unicodedata.normalize("NFKD", text)
    text = "".join(
        char for char in text
        if not unicodedata.combining(char)
    )
    text = re.sub(r"\s+", " ", text.lower())
    return text.strip()


def flatten_text(value: Any) -> str:
    parts: list[str] = []

    def walk(item: Any) -> None:
        if item is None:
            return
        if isinstance(item, dict):
            for child in item.values():
                walk(child)
            return
        if isinstance(item, (list, tuple, set)):
            for child in item:
                walk(child)
            return
        parts.append(str(item))

    walk(value)
    return normalize_text(" ".join(parts))


def normalize_company_name(name: str | None) -> str | None:
    text = normalize_text(name)
    if not text:
        return None

    text = re.sub(r"[^a-z0-9\s]", " ", text)
    text = re.sub(r"\s+", " ", text).strip()

    suffixes = (
        " sociedade anonima",
        " companhia",
        " eireli",
        " limitada",
        " ltda",
        " s a",
        " sa",
        " me",
        " epp",
    )

    changed = True
    while changed:
        changed = False
        for suffix in suffixes:
            if text.endswith(suffix):
                text = text[:-len(suffix)].strip()
                changed = True
                break

    return text.upper() if text else None


def _movement_code(movement: dict[str, Any]) -> str:
    for key in ("codigo", "code", "codigoMovimento", "codigo_movimento"):
        value = movement.get(key)
        if value is not None:
            return str(value).strip()
    return ""


def _movement_name(movement: dict[str, Any]) -> str:
    for key in ("nome", "name", "movimento", "descricao"):
        value = movement.get(key)
        if value:
            return normalize_text(value)
    return ""


def detect_sentence(source: dict[str, Any] | None) -> bool:
    if not isinstance(source, dict):
        return False

    movements = source.get("movimentos") or []

    if not isinstance(movements, list):
        return False

    for movement in movements:
        if not isinstance(movement, dict):
            continue

        if _movement_code(movement) in SENTENCE_MOVEMENT_CODES:
            return True

        name = _movement_name(movement)

        if any(term in name for term in SENTENCE_MOVEMENT_TERMS):
            return True

    return False


def classify_conducts(
    *,
    source: dict[str, Any] | None = None,
    resumo: Any = None,
    fundamentos: Any = None,
    evidencias_resultado: Any = None,
) -> list[str]:
    text = flatten_text({
        "source": source or {},
        "resumo": resumo,
        "fundamentos": fundamentos,
        "evidencias_resultado": evidencias_resultado,
    })

    found = []

    for label, patterns in CONDUCT_PATTERNS:
        if any(pattern in text for pattern in patterns):
            found.append(label)

    return found


def build_analysis_metadata(
    *,
    source: dict[str, Any] | None,
    empresa_re: str | None,
    resumo: Any = None,
    fundamentos: Any = None,
    evidencias_resultado: Any = None,
) -> dict[str, Any]:
    return {
        "tem_sentenca": detect_sentence(source),
        "empresa_re_normalizada": normalize_company_name(empresa_re),
        "condutas": classify_conducts(
            source=source,
            resumo=resumo,
            fundamentos=fundamentos,
            evidencias_resultado=evidencias_resultado,
        ),
        "enrichment_at": datetime.now(timezone.utc),
    }


def refresh_analysis_metadata_for_process(
    db: Session,
    tribunal: str,
    numero_processo: str,
    source: dict[str, Any],
) -> ProcessAnalysis | None:
    analysis = db.scalar(
        select(ProcessAnalysis).where(
            ProcessAnalysis.tribunal == tribunal,
            ProcessAnalysis.numero_processo == numero_processo,
        )
    )

    if analysis is None:
        return None

    metadata = build_analysis_metadata(
        source=source,
        empresa_re=analysis.empresa_re,
        resumo=analysis.resumo,
        fundamentos=analysis.fundamentos,
        evidencias_resultado=analysis.evidencias_resultado,
    )

    for key, value in metadata.items():
        setattr(analysis, key, value)

    db.flush()
    return analysis

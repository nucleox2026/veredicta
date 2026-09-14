import re
from typing import Any


_RESULT_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "parcialmente_procedente",
        re.compile(
            r"\bproced[eê]ncia\s+(?:em\s+)?parte\b"
            r"|\bparcialmente\s+procedente\b",
            re.IGNORECASE,
        ),
    ),
    (
        "improcedente",
        re.compile(
            r"\bimproced[eê]ncia\b|\bimprocedente\b",
            re.IGNORECASE,
        ),
    ),
    (
        "procedente",
        re.compile(
            r"\bproced[eê]ncia\b|\bprocedente\b",
            re.IGNORECASE,
        ),
    ),
    (
        "acordo",
        re.compile(
            r"\bhomologa(?:ç|c)[aã]o\s+(?:de\s+)?(?:acordo|transa[cç][aã]o)\b"
            r"|\bacordo\b|\btransa[cç][aã]o\b",
            re.IGNORECASE,
        ),
    ),
    (
        "extinto",
        re.compile(
            r"\bextin[cç][aã]o\b|\bextinto\b",
            re.IGNORECASE,
        ),
    ),
]

_APPEAL_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    (
        "confirmado_em_parte",
        re.compile(
            r"\bsenten[cç]a\s+confirmada\s+em\s+parte\b"
            r"|\bdecis[aã]o\s+confirmada\s+em\s+parte\b",
            re.IGNORECASE,
        ),
    ),
    (
        "confirmado",
        re.compile(
            r"\bsenten[cç]a\s+confirmada\b"
            r"|\bdecis[aã]o\s+confirmada\b"
            r"|\bac[oó]rd[aã]o\s+mantido\b"
            r"|\bsenten[cç]a\s+mantida\b",
            re.IGNORECASE,
        ),
    ),
    (
        "reformado",
        re.compile(
            r"\bsenten[cç]a\s+reformada\b"
            r"|\bdecis[aã]o\s+reformada\b"
            r"|\breforma(?:da|do)?\b",
            re.IGNORECASE,
        ),
    ),
    (
        "majorado",
        re.compile(
            r"\bmajorad[oa]\b|\bmajora[cç][aã]o\b|\beleva(?:do|da)\b",
            re.IGNORECASE,
        ),
    ),
    (
        "reduzido",
        re.compile(
            r"\breduzid[oa]\b|\bredu[cç][aã]o\b|\bminora(?:do|da|ç[aã]o)\b",
            re.IGNORECASE,
        ),
    ),
]

_JUDICIAL_VALUE_CONTEXT = re.compile(
    r"\b(indeniza(?:ç|c)[aã]o|dano(?:s)?\s+moral(?:is)?|condena(?:ç|c)[aã]o|"
    r"condenad[oa]|arbitrad[oa]|arbitro|fixad[oa]|fixo|quantum|majorad[oa]|reduzid[oa])\b",
    re.IGNORECASE,
)

_MONEY_PATTERN = re.compile(
    r"(?ix)(?:"
    r"R\$\s*\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?(?:\s*(?:mil|milh(?:ão|ões)))?"
    r"|\b\d{1,3}(?:\.\d{3})*(?:,\d{1,2})?\s*(?:mil\s+|milh(?:ão|ões)\s+)?reais\b"
    r")"
)

_SKIP_KEYS = {"valor"}


def _shorten(value: str, limit: int = 600) -> str:
    text = " ".join(str(value).split())
    return text if len(text) <= limit else text[: limit - 1] + "…"


def _movement_date(movement: dict[str, Any]) -> str | None:
    value = movement.get("dataHora") or movement.get("data_hora") or movement.get("data")
    return None if value is None else str(value)


def _movement_name(movement: dict[str, Any]) -> str | None:
    value = movement.get("nome") or movement.get("descricao")
    return None if value is None else _shorten(str(value), 250)


def _extract_text_fragments(
    value: Any,
    path: str = "",
    *,
    max_fragments: int = 300,
) -> list[dict[str, str]]:
    fragments: list[dict[str, str]] = []

    def walk(item: Any, current_path: str) -> None:
        if len(fragments) >= max_fragments:
            return
        if isinstance(item, str):
            text = _shorten(item)
            if text:
                fragments.append({"path": current_path, "text": text})
            return
        if isinstance(item, dict):
            for key, child in item.items():
                if str(key).strip().lower() in _SKIP_KEYS:
                    continue
                child_path = f"{current_path}.{key}" if current_path else str(key)
                walk(child, child_path)
            return
        if isinstance(item, list):
            for index, child in enumerate(item):
                walk(child, f"{current_path}[{index}]")

    walk(value, path)
    return fragments


def _deduplicate(
    items: list[dict[str, Any]],
    *,
    keys: tuple[str, ...],
) -> list[dict[str, Any]]:
    seen: set[tuple[Any, ...]] = set()
    result: list[dict[str, Any]] = []
    for item in items:
        signature = tuple(item.get(key) for key in keys)
        if signature in seen:
            continue
        seen.add(signature)
        result.append(item)
    return result


def extract_legal_evidence(raw_source: dict[str, Any] | None) -> dict[str, Any]:
    """
    Extrai evidências determinísticas dos metadados/movimentos do DataJud.

    Não chama IA, não consulta fontes externas e não persiste dados.
    O campo numérico "valor" dos complementos do DataJud é ignorado para
    fins monetários; dinheiro só é reconhecido quando existe marcador
    textual explícito, como "R$" ou "reais".
    """
    source = raw_source if isinstance(raw_source, dict) else {}
    movements = source.get("movimentos") or []
    if isinstance(movements, dict):
        movements = [movements]
    if not isinstance(movements, list):
        movements = []

    result_evidence: list[dict[str, Any]] = []
    appeal_evidence: list[dict[str, Any]] = []
    money_mentions: list[dict[str, Any]] = []

    for index, movement in enumerate(movements):
        if not isinstance(movement, dict):
            continue
        movement_name = _movement_name(movement)
        movement_date = _movement_date(movement)
        fragments = _extract_text_fragments(movement, path=f"movimentos[{index}]")

        for fragment in fragments:
            text = fragment["text"]

            for label, pattern in _RESULT_PATTERNS:
                if pattern.search(text):
                    result_evidence.append({
                        "resultado": label,
                        "data": movement_date,
                        "movimento": movement_name,
                        "caminho": fragment["path"],
                        "texto": text,
                    })
                    break

            for label, pattern in _APPEAL_PATTERNS:
                if pattern.search(text):
                    appeal_evidence.append({
                        "evento": label,
                        "data": movement_date,
                        "movimento": movement_name,
                        "caminho": fragment["path"],
                        "texto": text,
                    })
                    break

            for match in _MONEY_PATTERN.finditer(text):
                money_mentions.append({
                    "valor_textual": match.group(0).strip(),
                    "contexto_judicial": bool(_JUDICIAL_VALUE_CONTEXT.search(text)),
                    "data": movement_date,
                    "movimento": movement_name,
                    "caminho": fragment["path"],
                    "texto": text,
                })

    result_evidence = _deduplicate(
        result_evidence,
        keys=("resultado", "data", "texto"),
    )
    appeal_evidence = _deduplicate(
        appeal_evidence,
        keys=("evento", "data", "texto"),
    )
    money_mentions = _deduplicate(
        money_mentions,
        keys=("valor_textual", "data", "texto"),
    )

    result_candidate = result_evidence[0]["resultado"] if result_evidence else None
    strong_money_mentions = [
        item for item in money_mentions if item["contexto_judicial"]
    ]

    if not movements:
        data_quality = "muito_limitada"
    elif result_evidence or appeal_evidence or money_mentions:
        data_quality = "moderada"
    else:
        data_quality = "limitada"

    return {
        "resultado_candidato": result_candidate,
        "evidencias_resultado": result_evidence[:20],
        "eventos_recursais": appeal_evidence[:20],
        "mencoes_monetarias": money_mentions[:20],
        "mencoes_monetarias_com_contexto_judicial": strong_money_mentions[:20],
        "qualidade_dados": data_quality,
        "observacoes": [
            "Nenhum número cru do campo 'valor' do DataJud é tratado como dinheiro.",
            "Uma menção monetária é apenas evidência candidata; a natureza jurídica do valor ainda deve ser validada.",
        ],
    }

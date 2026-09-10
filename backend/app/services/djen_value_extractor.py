from __future__ import annotations

import hashlib
import re
import unicodedata
from dataclasses import asdict, dataclass
from datetime import date
from typing import Any


MONEY_RE = re.compile(
    r"R\$\s*(\d{1,3}(?:\.\d{3})*(?:,\d{2})?|\d+(?:,\d{2})?)",
    flags=re.IGNORECASE,
)

CATEGORY_TERMS: dict[str, tuple[str, ...]] = {
    "dano_moral": (
        "dano moral",
        "danos morais",
    ),
    "dano_estetico": (
        "dano estetico",
        "danos esteticos",
    ),
    "dano_material": (
        "dano material",
        "danos materiais",
    ),
    "honorarios": (
        "honorario",
        "honorarios",
    ),
    "multa": (
        "multa",
        "astreinte",
        "astreintes",
    ),
    "valor_da_causa": (
        "valor da causa",
    ),
}

POSITIVE_ACTION_TERMS = (
    "condeno",
    "condenar",
    "fixo",
    "fixa-se",
    "arbitro",
    "arbitra-se",
    "majoro",
    "majora-se",
    "reduzo",
    "reduz-se",
    "mantenho",
)

NEGATIVE_CITATION_TERMS = (
    "ementa:",
    "jurisprudencia",
    "precedente",
    "tese de julgamento",
    "recursos desprovidos",
    "dispositivos relevantes citados",
)

CLAUSE_SEPARATORS = (";", "\n", "•")
LOCAL_RADIUS = 150


@dataclass(frozen=True)
class ValueEvidence:
    categoria: str
    valor_centavos: int
    valor_texto: str
    confianca: str
    secao: str
    trecho: str
    data_documento: str | None
    tipo_documento: str | None
    link: str | None
    comunicacao_id: int | str | None
    comunicacao_hash: str | None
    distancia_categoria: int
    pareamento: str


def _fold(text: str) -> str:
    normalized = unicodedata.normalize("NFKD", text or "")
    return "".join(
        ch for ch in normalized if not unicodedata.combining(ch)
    ).lower()


def parse_brl_centavos(value: str) -> int:
    raw = str(value or "").strip()
    raw = re.sub(r"(?i)R\$\s*", "", raw)
    raw = raw.replace(".", "").replace(",", ".")
    if not re.fullmatch(r"\d+(?:\.\d{1,2})?", raw):
        raise ValueError(f"Valor monetário brasileiro inválido: {value!r}")
    return int(round(float(raw) * 100))


def _safe_iso_date(value: Any) -> str:
    text = str(value or "")
    try:
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return ""


def _communication_hash(item: dict[str, Any]) -> str:
    supplied = item.get("hash")
    if supplied:
        return str(supplied)

    material = "|".join(
        [
            str(item.get("id") or ""),
            str(item.get("data_disponibilizacao") or ""),
            str(item.get("tipoDocumento") or ""),
            str(item.get("texto") or ""),
        ]
    )
    return hashlib.sha256(material.encode("utf-8")).hexdigest()


def _context(text: str, start: int, end: int, radius: int = 170) -> str:
    left = max(0, start - radius)
    right = min(len(text), end + radius)
    return " ".join(text[left:right].split())


def _has_term(text: str, terms: tuple[str, ...]) -> bool:
    folded = _fold(text)
    return any(_fold(term) in folded for term in terms)


def _find_dispositive_start(text: str) -> int | None:
    folded = _fold(text)

    explicit = list(re.finditer(r"\bdispositivo\b", folded))
    if explicit:
        return explicit[-1].start()

    halfway = len(folded) // 2
    for header in ("diante do exposto", "ante o exposto"):
        positions = [m.start() for m in re.finditer(re.escape(header), folded)]
        positions = [pos for pos in positions if pos >= halfway]
        if positions:
            return positions[-1]

    return None


def _clause_bounds(text: str, amount_start: int, amount_end: int) -> tuple[int, int]:
    """
    Isola a oração/item que contém a quantia.

    O ponto-chave desta revisão é NÃO permitir que:
      R$ 5.000,00 ... danos morais; R$ 5.000,00 ... danos estéticos
    seja tratado como uma única janela sem estrutura.
    """
    left = 0
    for sep in CLAUSE_SEPARATORS:
        pos = text.rfind(sep, 0, amount_start)
        if pos >= 0:
            left = max(left, pos + len(sep))

    right = len(text)
    for sep in CLAUSE_SEPARATORS:
        pos = text.find(sep, amount_end)
        if pos >= 0:
            right = min(right, pos)

    return left, right


def _category_hits(segment: str) -> list[tuple[int, int, str]]:
    """
    Retorna (inicio, fim, categoria) dentro do segmento.

    Índices são calculados no texto normalizado apenas para comparação local;
    não são reutilizados como índices no documento original.
    """
    folded = _fold(segment)
    hits: list[tuple[int, int, str]] = []

    for category, terms in CATEGORY_TERMS.items():
        for term in terms:
            needle = _fold(term)
            for match in re.finditer(re.escape(needle), folded):
                hits.append((match.start(), match.end(), category))

    return hits


def _pair_category(
    text: str,
    amount_start: int,
    amount_end: int,
) -> tuple[str | None, int | None, str]:
    """
    Pareia a quantia com sua categoria.

    Prioridade:
    1. categoria dentro da mesma oração/item delimitado por ;, quebra de
       linha ou bullet;
    2. fallback local, mas sem atravessar mais que uma pequena janela.

    Dentro da mesma oração:
    - categoria depois do valor é preferida quando próxima
      ("R$ 5.000,00, a título de danos estéticos");
    - categoria antes do valor também funciona
      ("danos morais fixados em R$ 5.000,00").
    """
    clause_left, clause_right = _clause_bounds(text, amount_start, amount_end)
    clause = text[clause_left:clause_right]

    rel_start = amount_start - clause_left
    rel_end = amount_end - clause_left
    hits = _category_hits(clause)

    scored: list[tuple[int, int, str]] = []
    for hit_start, hit_end, category in hits:
        if hit_start >= rel_end:
            distance = hit_start - rel_end
            direction_penalty = 0
        elif hit_end <= rel_start:
            distance = rel_start - hit_end
            direction_penalty = 4
        else:
            distance = 0
            direction_penalty = 0

        scored.append((distance + direction_penalty, distance, category))

    if scored:
        scored.sort(key=lambda item: (item[0], item[1], item[2]))
        _, distance, category = scored[0]
        return category, distance, "mesma_oracao"

    # Fallback controlado para frases sem ;/quebra estrutural.
    local_left = max(0, amount_start - LOCAL_RADIUS)
    local_right = min(len(text), amount_end + LOCAL_RADIUS)
    local = text[local_left:local_right]
    local_rel_start = amount_start - local_left
    local_rel_end = amount_end - local_left

    fallback: list[tuple[int, int, str]] = []
    for hit_start, hit_end, category in _category_hits(local):
        if hit_start >= local_rel_end:
            distance = hit_start - local_rel_end
            direction_penalty = 0
        elif hit_end <= local_rel_start:
            distance = local_rel_start - hit_end
            direction_penalty = 8
        else:
            distance = 0
            direction_penalty = 0
        fallback.append((distance + direction_penalty, distance, category))

    if fallback:
        fallback.sort(key=lambda item: (item[0], item[1], item[2]))
        _, distance, category = fallback[0]
        return category, distance, "janela_local"

    return None, None, "sem_categoria"


def _candidate_score(
    *,
    section_name: str,
    context: str,
    category: str,
    distance: int,
    pairing: str,
) -> int:
    score = 0

    if section_name == "dispositivo":
        score += 120
    else:
        score += 30

    if pairing == "mesma_oracao":
        score += 35
    else:
        score += 10

    score += max(0, 30 - min(distance, 30))

    if _has_term(context, POSITIVE_ACTION_TERMS):
        score += 30

    if _has_term(context, NEGATIVE_CITATION_TERMS):
        score -= 100

    if category in {"dano_moral", "dano_estetico", "dano_material"}:
        score += 20
    else:
        score -= 10

    return score


def _confidence(score: int) -> str:
    if score >= 150:
        return "alta"
    if score >= 80:
        return "media"
    return "baixa"


def _extract_candidates(
    text: str,
    *,
    section_name: str,
    data_documento: str | None,
    tipo_documento: str | None,
    link: str | None,
    comunicacao_id: int | str | None,
    comunicacao_hash: str | None,
) -> list[tuple[int, ValueEvidence]]:
    results: list[tuple[int, ValueEvidence]] = []

    for match in MONEY_RE.finditer(text):
        category, distance, pairing = _pair_category(
            text,
            match.start(),
            match.end(),
        )
        if category is None or distance is None:
            continue

        ctx = _context(text, match.start(), match.end())
        score = _candidate_score(
            section_name=section_name,
            context=ctx,
            category=category,
            distance=distance,
            pairing=pairing,
        )

        evidence = ValueEvidence(
            categoria=category,
            valor_centavos=parse_brl_centavos(match.group(0)),
            valor_texto=match.group(0),
            confianca=_confidence(score),
            secao=section_name,
            trecho=ctx,
            data_documento=data_documento,
            tipo_documento=tipo_documento,
            link=link,
            comunicacao_id=comunicacao_id,
            comunicacao_hash=comunicacao_hash,
            distancia_categoria=distance,
            pareamento=pairing,
        )
        results.append((score, evidence))

    return results


def extract_document_values(item: dict[str, Any]) -> dict[str, Any]:
    """
    Extrai valores de um documento com prioridade ao dispositivo.

    Segurança:
    - categorias resolvidas no dispositivo não são substituídas pela
      fundamentação;
    - cada quantia é pareada primeiro dentro da sua própria oração/item;
    - valores de precedentes ficam apenas como candidatos descartados quando
      o dispositivo do caso já resolve a categoria.
    """
    text = str(item.get("texto") or "")
    if not text.strip():
        return {
            "values": {},
            "evidencias": [],
            "candidatos_descartados": [],
        }

    metadata = {
        "data_documento": item.get("data_disponibilizacao")
        or item.get("datadisponibilizacao"),
        "tipo_documento": item.get("tipoDocumento"),
        "link": item.get("link"),
        "comunicacao_id": item.get("id") or item.get("numeroComunicacao"),
        "comunicacao_hash": _communication_hash(item),
    }

    selected: dict[str, tuple[int, ValueEvidence]] = {}
    discarded: list[ValueEvidence] = []

    dispositive_start = _find_dispositive_start(text)
    if dispositive_start is not None:
        dispositive = text[dispositive_start:]
        for score, evidence in _extract_candidates(
            dispositive,
            section_name="dispositivo",
            **metadata,
        ):
            current = selected.get(evidence.categoria)
            if current is None or score > current[0]:
                if current is not None:
                    discarded.append(current[1])
                selected[evidence.categoria] = (score, evidence)
            else:
                discarded.append(evidence)

    categories_from_dispositive = set(selected)

    for score, evidence in _extract_candidates(
        text,
        section_name="texto_integral",
        **metadata,
    ):
        if evidence.categoria in categories_from_dispositive:
            discarded.append(evidence)
            continue

        current = selected.get(evidence.categoria)
        if current is None or score > current[0]:
            if current is not None:
                discarded.append(current[1])
            selected[evidence.categoria] = (score, evidence)
        else:
            discarded.append(evidence)

    values: dict[str, int] = {}
    evidences: list[dict[str, Any]] = []

    for category, (_, evidence) in selected.items():
        if evidence.confianca == "baixa":
            discarded.append(evidence)
            continue
        values[category] = evidence.valor_centavos
        evidences.append(asdict(evidence))

    evidences.sort(key=lambda ev: ev["categoria"])

    return {
        "values": values,
        "evidencias": evidences,
        "candidatos_descartados": [asdict(ev) for ev in discarded],
    }


def _is_judicial_value_document(item: dict[str, Any]) -> bool:
    """
    Aceita tanto documentos classificados formalmente como Sentença/Acórdão/
    Decisão quanto comunicações do tipo "Intimação" que EMBUTEM o inteiro teor
    de uma sentença.

    Alguns tribunais publicam a sentença dentro de uma comunicação cuja
    classificação externa é "Intimação". Nesses casos, exigir apenas
    tipoDocumento == "Sentença" descartaria valores expressos no dispositivo.

    Para comunicação não classificada formalmente como decisão, exigimos:
    - marcador textual de SENTENÇA ou ACÓRDÃO; e
    - estrutura decisória forte (DISPOSITIVO, ANTE O EXPOSTO ou DIANTE DO EXPOSTO).
    """
    tipo = _fold(str(item.get("tipoDocumento") or ""))
    if any(token in tipo for token in ("sentenca", "acordao", "decisao")):
        return True

    text = _fold(str(item.get("texto") or ""))
    if not text.strip():
        return False

    has_judicial_header = (
        re.search(r"\bsentenca\b", text) is not None
        or re.search(r"\bacordao\b", text) is not None
    )
    has_dispositive_structure = any(
        marker in text
        for marker in ("dispositivo", "ante o exposto", "diante do exposto")
    )

    return has_judicial_header and has_dispositive_structure


def _effective_document_type(item: dict[str, Any]) -> str | None:
    original = str(item.get("tipoDocumento") or "").strip()
    folded_original = _fold(original)
    if any(token in folded_original for token in ("sentenca", "acordao", "decisao")):
        return original or None

    text = _fold(str(item.get("texto") or ""))
    if re.search(r"\bsentenca\b", text):
        return "Sentença (publicada em Intimação)"
    if re.search(r"\bacordao\b", text):
        return "Acórdão (publicado em Intimação)"
    return original or None


def extract_process_awards(
    communications: list[dict[str, Any]],
) -> dict[str, Any]:
    """
    Extrai histórico monetário do processo.

    - documento posterior sem quantia não apaga valor anterior;
    - dano moral, estético e material ficam separados;
    - primeiro grau = primeira fixação monetária encontrada;
    - final = última fixação monetária encontrada.
    """
    documents: list[dict[str, Any]] = []

    for item in communications or []:
        if not _is_judicial_value_document(item):
            continue

        extracted = extract_document_values(item)
        if extracted["values"]:
            documents.append(
                {
                    "data": _safe_iso_date(
                        item.get("data_disponibilizacao")
                        or item.get("datadisponibilizacao")
                    ),
                    "tipo_documento": _effective_document_type(item),
                    "tipo_documento_original": item.get("tipoDocumento"),
                    "link": item.get("link"),
                    "values": extracted["values"],
                    "evidencias": extracted["evidencias"],
                }
            )

    documents.sort(key=lambda doc: doc["data"] or "9999-12-31")

    def history_for(category: str) -> list[dict[str, Any]]:
        history: list[dict[str, Any]] = []
        for doc in documents:
            if category not in doc["values"]:
                continue

            evidence = next(
                (
                    ev
                    for ev in doc["evidencias"]
                    if ev["categoria"] == category
                ),
                None,
            )
            history.append(
                {
                    "data": doc["data"],
                    "valor_centavos": doc["values"][category],
                    "tipo_documento": doc["tipo_documento"],
                    "link": doc["link"],
                    "evidencia": evidence,
                }
            )
        return history

    moral_history = history_for("dano_moral")
    esthetic_history = history_for("dano_estetico")
    material_history = history_for("dano_material")

    first_moral = moral_history[0]["valor_centavos"] if moral_history else None
    final_moral = moral_history[-1]["valor_centavos"] if moral_history else None
    first_esthetic = (
        esthetic_history[0]["valor_centavos"] if esthetic_history else None
    )
    final_esthetic = (
        esthetic_history[-1]["valor_centavos"] if esthetic_history else None
    )

    total_first = None
    if first_moral is not None or first_esthetic is not None:
        total_first = (first_moral or 0) + (first_esthetic or 0)

    return {
        "valor_dano_moral_primeiro_grau_centavos": first_moral,
        "valor_dano_moral_final_centavos": final_moral,
        "valor_dano_estetico_primeiro_grau_centavos": first_esthetic,
        "valor_dano_estetico_final_centavos": final_esthetic,
        "valor_total_indenizacao_primeiro_grau_centavos": total_first,
        "historico_dano_moral": moral_history,
        "historico_dano_estetico": esthetic_history,
        "historico_dano_material": material_history,
        "documentos_com_valor": documents,
    }

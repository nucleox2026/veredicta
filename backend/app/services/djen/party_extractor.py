from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from ..analysis.enrichment import normalize_company_name


MAX_HEADER_CHARS = 5000


_DOCUMENT_TERMINATORS = (
    r"AUTOR(?:A)?",
    r"REQUERENTE",
    r"RECLAMANTE",
    r"EXEQUENTE",
    r"DEMANDANTE",
    r"IMPETRANTE",
    r"R[ÉE]U",
    r"R[ÉE]",
    r"REQUERID[OA]",
    r"RECLAMAD[OA]",
    r"VISTOS?",
    r"RELAT[ÓO]RIO",
    r"FUNDAMENTO",
    r"DECIDO",
    r"SENTEN[ÇC]A",
    r"DECIS[ÃA]O",
    r"DESPACHO",
    r"AC[ÓO]RD[ÃA]O",
    r"DISPOSITIVO",
    r"INTIMA[ÇC][ÃA]O",
    r"MANDADO",
    r"CERTID[ÃA]O",
    r"EDITAL",
    r"PROCESSO",
    r"ADVOGAD[OA]",
)

_TERMINATOR_GROUP = "|".join(_DOCUMENT_TERMINATORS)


def _role_pattern(label: str) -> re.Pattern[str]:
    return re.compile(
        rf"\b{label}\s*:\s*"
        rf"(?P<name>.+?)"
        rf"(?=\s+(?:{_TERMINATOR_GROUP})\b|$)",
        re.IGNORECASE,
    )


_ACTIVE_ROLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("autor", _role_pattern(r"AUTOR(?:A)?")),
    ("requerente", _role_pattern(r"REQUERENTE")),
    ("reclamante", _role_pattern(r"RECLAMANTE")),
    ("exequente", _role_pattern(r"EXEQUENTE")),
    ("demandante", _role_pattern(r"DEMANDANTE")),
    ("impetrante", _role_pattern(r"IMPETRANTE")),
)

_PASSIVE_ROLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("reu", _role_pattern(r"(?:R[ÉE]U|R[ÉE])")),
    ("requerido", _role_pattern(r"REQUERID[OA]")),
    ("reclamado", _role_pattern(r"RECLAMAD[OA]")),
    ("executado", _role_pattern(r"EXECUTAD[OA]")),
)


_COMPANY_MARKERS = (
    " S.A",
    " S/A",
    " SA",
    " LTDA",
    " LIMITADA",
    " EIRELI",
    " COMPANHIA",
    " CIA ",
    " BANCO ",
    " BANCO",
    " FINANCEIRA",
    " SEGURADORA",
    " SEGUROS",
    " COOPERATIVA",
    " TELECOM",
    " TELEFONICA",
    " TELEFÔNICA",
    " ENERGIA",
    " DISTRIBUIDORA",
    " CONCESSIONARIA",
    " CONCESSIONÁRIA",
    " TRANSPORTES",
    " AIRLINES",
    " LINHAS AEREAS",
    " LINHAS AÉREAS",
    " COMERCIO",
    " COMÉRCIO",
    " SERVICOS",
    " SERVIÇOS",
    " INDUSTRIA",
    " INDÚSTRIA",
    " TECNOLOGIA",
    " EMPREENDIMENTOS",
    " CONSTRUTORA",
    " INCORPORADORA",
    " HOSPITAL",
    " CLINICA",
    " CLÍNICA",
    " UNIVERSIDADE",
    " FACULDADE",
    " ASSOCIACAO",
    " ASSOCIAÇÃO",
    " FUNDACAO",
    " FUNDAÇÃO",
    " CAIXA ECONOMICA",
    " CAIXA ECONÔMICA",
    " CORRETORA",
    " ADMINISTRADORA",
    " OPERADORA",
    " SUPERMERCADO",
    " MAGAZINE",
    " LOJAS ",
    " MERCANTIL",
    # Operadoras/administradoras de saúde que muitas vezes aparecem no DJEN
    # somente pela marca, sem LTDA/S.A. no nome exibido.
    " UNIMED",
    "UNIMED ",
    " HAPVIDA",
    "HAPVIDA ",
    " AMIL",
    "AMIL ",
    " SULAMERICA",
    " SUL AMERICA",
    " NOTREDAME",
    " INTERMEDICA",
    " INTERMÉDICA",
    " BRADESCO SAUDE",
    " BRADESCO SAÚDE",
    " PREVENT SENIOR",
    " MEDSENIOR",
    " CARE PLUS",
    " CASSI",
    " GEAP",
    " ASSEFAZ",
)

_PUBLIC_ENTITY_PREFIXES = (
    "UNIÃO",
    "UNIAO",
    "ESTADO DE ",
    "MUNICÍPIO DE ",
    "MUNICIPIO DE ",
    "PREFEITURA ",
    "SECRETARIA DE ",
    "MINISTÉRIO ",
    "MINISTERIO ",
    "PROCURADORIA ",
    "DEFENSORIA ",
    "TRIBUNAL ",
    "CÂMARA MUNICIPAL",
    "CAMARA MUNICIPAL",
    "ASSEMBLEIA LEGISLATIVA",
)

_ONLY_DOCUMENT_RE = re.compile(
    r"^(?:"
    r"(?:CPF|CNPJ)\s*:\s*)?"
    r"\d{2,3}\.?\d{3}\.?\d{3}"
    r"(?:/|-)?\d{2,4}-?\d{0,2}$",
    re.IGNORECASE,
)

_TRAILING_METADATA_RE = re.compile(
    r"\s+(?:"
    r"DESPACHO|DECIS[ÃA]O|SENTEN[ÇC]A|INTIMA[ÇC][ÃA]O|"
    r"MANDADO|CERTID[ÃA]O|EDITAL|VISTOS?|PROCESSO"
    r")\b.*$",
    re.IGNORECASE,
)

_TRAILING_ID_RE = re.compile(
    r"\s+(?:CPF|CNPJ)\s*:\s*[\d./-]+(?:\s+e\s+outros)?\s*$",
    re.IGNORECASE,
)

_TRAILING_OTHERS_RE = re.compile(
    r"\s+(?:e\s+outros|e\s+outr[oa]s)\s*$",
    re.IGNORECASE,
)


def _clean_spaces(value: Any) -> str:
    return re.sub(r"\s+", " ", str(value or "")).strip()


def _safe_date(item: dict[str, Any]) -> str | None:
    value = (
        item.get("data_disponibilizacao")
        or item.get("datadisponibilizacao")
        or item.get("dataDisponibilizacao")
    )
    if not value:
        return None
    return str(value)[:10]


def _clean_party_name(name: str) -> str:
    cleaned = _clean_spaces(name)

    # Remove cabeçalhos/documentos que ficaram colados ao nome.
    cleaned = _TRAILING_METADATA_RE.sub("", cleaned)

    # CPF/CNPJ anexado ao fim é metadado, não parte da razão social.
    cleaned = _TRAILING_ID_RE.sub("", cleaned)
    cleaned = _TRAILING_OTHERS_RE.sub("", cleaned)

    cleaned = re.sub(
        r"^[\-–—:;,.\s]+|[\-–—:;,\s]+$",
        "",
        cleaned,
    )

    return cleaned.strip()


def _is_public_entity(name: str) -> bool:
    upper = _clean_spaces(name).upper()
    return upper.startswith(_PUBLIC_ENTITY_PREFIXES)


def _looks_like_company(name: str) -> bool:
    clean = _clean_party_name(name)
    upper = f" {clean.upper()} "

    # Um CNPJ/CPF sem razão social não é "nome da empresa".
    if not clean or _ONLY_DOCUMENT_RE.fullmatch(clean):
        return False

    # Órgãos públicos podem estar no polo réu, mas não são empresas.
    if _is_public_entity(clean):
        return False

    return any(
        marker in upper
        for marker in _COMPANY_MARKERS
    )


_ACTIVE_POLES = {
    "A",
    "ATIVO",
    "POLO ATIVO",
    "AUTOR",
    "AUTORA",
    "REQUERENTE",
    "RECLAMANTE",
    "EXEQUENTE",
    "DEMANDANTE",
    "IMPETRANTE",
}

_PASSIVE_POLES = {
    "P",
    "PASSIVO",
    "POLO PASSIVO",
    "REU",
    "RÉU",
    "REQUERIDO",
    "RECLAMADO",
    "EXECUTADO",
}


def _is_active_pole(value: Any) -> bool:
    normalized = _clean_spaces(value).upper()
    return normalized in _ACTIVE_POLES


def _is_passive_pole(value: Any) -> bool:
    normalized = _clean_spaces(value).upper()
    return normalized in _PASSIVE_POLES


def _structured_recipients(
    item: dict[str, Any],
    *,
    active: bool,
) -> list[str]:
    """Lê destinatários estruturados do DJEN por polo."""
    rows = item.get("destinatarios")
    if not isinstance(rows, list):
        return []

    output: list[str] = []
    matcher = _is_active_pole if active else _is_passive_pole

    for row in rows:
        if not isinstance(row, dict):
            continue
        if not matcher(row.get("polo")):
            continue

        name = _clean_party_name(row.get("nome") or "")
        if not name or len(name) < 3 or len(name) > 300:
            continue

        output.append(name)

    return output


def _structured_active_recipients(item: dict[str, Any]) -> list[str]:
    return _structured_recipients(item, active=True)


def _structured_passive_recipients(item: dict[str, Any]) -> list[str]:
    return _structured_recipients(item, active=False)

def _party_evidence(
    *,
    name: str,
    role: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    clean_name = _clean_party_name(name)

    return {
        "nome": clean_name,
        "nome_normalizado": normalize_company_name(clean_name),
        "papel": role,
        "eh_empresa": _looks_like_company(clean_name),
        "documento": None,
        "tipo_pessoa": (
            "Pessoa jurídica"
            if _looks_like_company(clean_name)
            else None
        ),
        "confianca": "alta",
        "fonte": "DJEN/CNJ",
        "data_documento": _safe_date(item),
        "tipo_documento": item.get("tipoDocumento"),
        "link": item.get("link"),
        "comunicacao_id": item.get("id"),
        "comunicacao_hash": item.get("hash"),
    }


def _dedupe_parties(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    ordered = sorted(
        rows,
        key=lambda row: (
            row.get("data_documento") or "",
            str(row.get("comunicacao_id") or ""),
        ),
    )

    by_name: dict[str, dict[str, Any]] = {}
    for row in ordered:
        normalized = (
            row.get("nome_normalizado")
            or _clean_spaces(row.get("nome")).upper()
        )
        if normalized:
            by_name[str(normalized)] = row

    return list(by_name.values())


def _build_result(
    partes_re: list[dict[str, Any]],
    partes_ativo: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    partes_re = _dedupe_parties(partes_re)
    partes_ativo = _dedupe_parties(partes_ativo or [])

    empresas_by_name: dict[str, dict[str, Any]] = {}

    for row in partes_re:
        if not row.get("eh_empresa"):
            continue

        normalized = row.get("nome_normalizado")
        if not normalized:
            continue

        empresas_by_name[str(normalized)] = row

    empresas_re = sorted(
        empresas_by_name.values(),
        key=lambda row: str(row.get("nome_normalizado") or ""),
    )

    principal = empresas_re[0] if len(empresas_re) == 1 else None

    return {
        "metodo": "destinatarios_djen_ou_rotulo_textual",
        "verificado": True,
        "verificado_em": datetime.now(timezone.utc).isoformat(),
        # Formato usado pela ficha processual.
        "ativo": partes_ativo,
        "passivo": partes_re,
        # Compatibilidade com snapshots anteriores.
        "partes_ativo": partes_ativo,
        "partes_re": partes_re,
        "empresas_re": empresas_re,
        "empresa_re_principal": principal,
    }


def _extract_text_roles(
    item: dict[str, Any],
    patterns: tuple[tuple[str, re.Pattern[str]], ...],
) -> list[dict[str, Any]]:
    raw = _clean_spaces(item.get("texto"))
    if not raw:
        return []

    header = raw[:MAX_HEADER_CHARS]
    found: list[dict[str, Any]] = []

    for role, pattern in patterns:
        for match in pattern.finditer(header):
            name = _clean_party_name(match.group("name"))
            if not name or len(name) < 3 or len(name) > 300:
                continue
            found.append(
                _party_evidence(
                    name=name,
                    role=role,
                    item=item,
                )
            )

    return found


def extract_process_parties(
    communications: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extrai polo ativo e polo passivo das comunicações públicas do DJEN.

    Prioridade:
    1. `destinatarios[].polo` estruturado pelo próprio DJEN;
    2. rótulos textuais explícitos (Autor, Requerente, Réu, Requerido etc.).

    Nenhuma parte é inventada quando a comunicação não expõe o nome.
    """
    active: list[dict[str, Any]] = []
    passive: list[dict[str, Any]] = []

    for item in communications or []:
        if not isinstance(item, dict):
            continue

        structured_active = _structured_active_recipients(item)
        structured_passive = _structured_passive_recipients(item)

        for name in structured_active:
            active.append(
                _party_evidence(
                    name=name,
                    role="polo_ativo_djen",
                    item=item,
                )
            )

        for name in structured_passive:
            passive.append(
                _party_evidence(
                    name=name,
                    role="polo_passivo_djen",
                    item=item,
                )
            )

        # Quando o DJEN já informa o polo de forma estruturada, ele é a fonte
        # prioritária e evitamos duplicar nomes abreviados/qualificados do texto.
        if not structured_active:
            active.extend(_extract_text_roles(item, _ACTIVE_ROLE_PATTERNS))

        if not structured_passive:
            passive.extend(_extract_text_roles(item, _PASSIVE_ROLE_PATTERNS))

    return _build_result(passive, active)


def extract_defendant_parties(
    communications: list[dict[str, Any]],
) -> dict[str, Any]:
    """Compatibilidade: agora retorna o snapshot completo de partes."""
    return extract_process_parties(communications)


def sanitize_saved_party_snapshot(
    value: Any,
) -> dict[str, Any]:
    """Reclassifica um snapshot já salvo sem fazer nova consulta ao DJEN."""
    if not isinstance(value, dict):
        return _build_result([])

    passive_rows = value.get("partes_re")
    if not isinstance(passive_rows, list):
        passive_rows = value.get("passivo")
    if not isinstance(passive_rows, list):
        passive_rows = []

    active_rows = value.get("partes_ativo")
    if not isinstance(active_rows, list):
        active_rows = value.get("ativo")
    if not isinstance(active_rows, list):
        active_rows = []

    def clean(rows: list[Any]) -> list[dict[str, Any]]:
        cleaned: list[dict[str, Any]] = []
        for original in rows:
            if not isinstance(original, dict):
                continue

            row = dict(original)
            name = _clean_party_name(str(row.get("nome") or ""))
            if not name:
                continue

            row["nome"] = name
            row["nome_normalizado"] = normalize_company_name(name)
            row["eh_empresa"] = _looks_like_company(name)
            row.setdefault("documento", None)
            row.setdefault(
                "tipo_pessoa",
                "Pessoa jurídica" if row["eh_empresa"] else None,
            )
            cleaned.append(row)
        return cleaned

    return _build_result(clean(passive_rows), clean(active_rows))


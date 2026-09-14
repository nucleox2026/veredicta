from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import Any

from ..analysis.enrichment import normalize_company_name


MAX_HEADER_CHARS = 5000


_DOCUMENT_TERMINATORS = (
    r"AUTOR(?:A)?",
    r"REQUERENTE",
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


_ROLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    ("reu", _role_pattern(r"(?:R[ÉE]U|R[ÉE])")),
    ("requerido", _role_pattern(r"REQUERID[OA]")),
    ("reclamado", _role_pattern(r"RECLAMAD[OA]")),
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


_PASSIVE_POLES = {
    "P",
    "PASSIVO",
    "POLO PASSIVO",
    "REU",
    "RÉU",
    "REQUERIDO",
    "RECLAMADO",
}


def _is_passive_pole(value: Any) -> bool:
    normalized = _clean_spaces(value).upper()
    return normalized in _PASSIVE_POLES


def _structured_passive_recipients(
    item: dict[str, Any],
) -> list[str]:
    """Lê o polo passivo estruturado retornado pelo DJEN.

    O endpoint público retorna `destinatarios` com `nome` e `polo`.
    Esse dado é mais confiável do que depender de o texto conter literalmente
    "RÉU:" / "REQUERIDO:".
    """
    rows = item.get("destinatarios")
    if not isinstance(rows, list):
        return []

    output: list[str] = []

    for row in rows:
        if not isinstance(row, dict):
            continue
        if not _is_passive_pole(row.get("polo")):
            continue

        name = _clean_party_name(row.get("nome") or "")
        if not name or len(name) < 3 or len(name) > 300:
            continue

        output.append(name)

    return output


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
        "confianca": "alta",
        "fonte": "DJEN/CNJ",
        "data_documento": _safe_date(item),
        "tipo_documento": item.get("tipoDocumento"),
        "link": item.get("link"),
        "comunicacao_id": item.get("id"),
        "comunicacao_hash": item.get("hash"),
    }


def _build_result(
    partes_re: list[dict[str, Any]],
) -> dict[str, Any]:
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
        key=lambda row: str(
            row.get("nome_normalizado") or ""
        ),
    )

    principal = (
        empresas_re[0]
        if len(empresas_re) == 1
        else None
    )

    return {
        "metodo": "destinatarios_djen_ou_rotulo_polo_reu",
        "verificado": True,
        "verificado_em": datetime.now(timezone.utc).isoformat(),
        "partes_re": partes_re,
        "empresas_re": empresas_re,
        "empresa_re_principal": principal,
    }


def extract_defendant_parties(
    communications: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extrai empresas do polo réu com evidência explícita no DJEN/CNJ.

    Regras:
    - exige rótulo de polo: RÉU, REQUERIDO ou RECLAMADO;
    - remove metadados/cabeçalhos colados ao nome;
    - CNPJ/CPF isolado não vira nome empresarial;
    - órgão público não é classificado como empresa;
    - sem inferência por nome solto.
    """
    found: list[dict[str, Any]] = []

    for item in communications or []:
        if not isinstance(item, dict):
            continue

        # 1) Primeiro usa a estrutura oficial do próprio DJEN.
        # Ex.: destinatarios=[{"nome": "BANCO ...", "polo": "P"}].
        for name in _structured_passive_recipients(item):
            found.append(
                _party_evidence(
                    name=name,
                    role="polo_passivo_djen",
                    item=item,
                )
            )

        # 2) Mantém o parser textual como fallback para comunicações antigas
        # ou documentos em que o polo não venha estruturado.
        raw = _clean_spaces(item.get("texto"))
        if not raw:
            continue

        header = raw[:MAX_HEADER_CHARS]

        for role, pattern in _ROLE_PATTERNS:
            for match in pattern.finditer(header):
                name = _clean_party_name(
                    match.group("name")
                )

                if (
                    not name
                    or len(name) < 3
                    or len(name) > 300
                ):
                    continue

                found.append(
                    _party_evidence(
                        name=name,
                        role=role,
                        item=item,
                    )
                )

    found.sort(
        key=lambda row: (
            row.get("data_documento") or "",
            str(row.get("comunicacao_id") or ""),
        )
    )

    by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for row in found:
        normalized = (
            row.get("nome_normalizado")
            or _clean_spaces(row.get("nome")).upper()
        )

        by_key[
            (
                str(row.get("papel") or ""),
                str(normalized),
            )
        ] = row

    return _build_result(
        list(by_key.values())
    )


def sanitize_saved_party_snapshot(
    value: Any,
) -> dict[str, Any]:
    """Reclassifica um snapshot já salvo sem fazer nova consulta ao DJEN."""
    if not isinstance(value, dict):
        return _build_result([])

    rows = value.get("partes_re")
    if not isinstance(rows, list):
        rows = []

    cleaned_rows: list[dict[str, Any]] = []
    by_key: dict[tuple[str, str], dict[str, Any]] = {}

    for original in rows:
        if not isinstance(original, dict):
            continue

        row = dict(original)
        name = _clean_party_name(
            str(row.get("nome") or "")
        )

        if not name:
            continue

        row["nome"] = name
        row["nome_normalizado"] = normalize_company_name(name)
        row["eh_empresa"] = _looks_like_company(name)

        normalized = (
            row.get("nome_normalizado")
            or name.upper()
        )

        by_key[
            (
                str(row.get("papel") or ""),
                str(normalized),
            )
        ] = row

    cleaned_rows.extend(by_key.values())
    return _build_result(cleaned_rows)

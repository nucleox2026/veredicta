from __future__ import annotations

from collections import Counter
from datetime import datetime
import re
from typing import Any

from ..analysis.enrichment import normalize_company_name


MAX_HEADER_CHARS = 5000


_ROLE_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "reu",
        re.compile(
            r"\b(?:R[ÉE]U|R[ÉE])\s*:\s*"
            r"(?P<name>.+?)"
            r"(?=\s+(?:"
            r"AUTOR(?:A)?|REQUERENTE|R[ÉE]U|R[ÉE]|"
            r"REQUERID[OA]|RECLAMAD[OA]|"
            r"VISTOS?|RELAT[ÓO]RIO|FUNDAMENTO|DECIDO|"
            r"SENTEN[ÇC]A|DECIS[ÃA]O|AC[ÓO]RD[ÃA]O|"
            r"DISPOSITIVO"
            r")\b|$)",
            re.IGNORECASE,
        ),
    ),
    (
        "requerido",
        re.compile(
            r"\bREQUERID[OA]\s*:\s*"
            r"(?P<name>.+?)"
            r"(?=\s+(?:"
            r"AUTOR(?:A)?|REQUERENTE|R[ÉE]U|R[ÉE]|"
            r"REQUERID[OA]|RECLAMAD[OA]|"
            r"VISTOS?|RELAT[ÓO]RIO|FUNDAMENTO|DECIDO|"
            r"SENTEN[ÇC]A|DECIS[ÃA]O|AC[ÓO]RD[ÃA]O|"
            r"DISPOSITIVO"
            r")\b|$)",
            re.IGNORECASE,
        ),
    ),
    (
        "reclamado",
        re.compile(
            r"\bRECLAMAD[OA]\s*:\s*"
            r"(?P<name>.+?)"
            r"(?=\s+(?:"
            r"AUTOR(?:A)?|REQUERENTE|R[ÉE]U|R[ÉE]|"
            r"REQUERID[OA]|RECLAMAD[OA]|"
            r"VISTOS?|RELAT[ÓO]RIO|FUNDAMENTO|DECIDO|"
            r"SENTEN[ÇC]A|DECIS[ÃA]O|AC[ÓO]RD[ÃA]O|"
            r"DISPOSITIVO"
            r")\b|$)",
            re.IGNORECASE,
        ),
    ),
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


def _looks_like_company(name: str) -> bool:
    upper = f" {_clean_spaces(name).upper()} "

    if re.search(
        r"\b\d{2}\.?\d{3}\.?\d{3}/?\d{4}-?\d{2}\b",
        upper,
    ):
        return True

    return any(
        marker in upper
        for marker in _COMPANY_MARKERS
    )


def _clean_party_name(name: str) -> str:
    cleaned = _clean_spaces(name)
    cleaned = re.sub(
        r"^[\-–—:;,.\s]+|[\-–—:;,\s]+$",
        "",
        cleaned,
    )
    return cleaned.strip()


def _party_evidence(
    *,
    name: str,
    role: str,
    item: dict[str, Any],
) -> dict[str, Any]:
    return {
        "nome": name,
        "nome_normalizado": normalize_company_name(name),
        "papel": role,
        "eh_empresa": _looks_like_company(name),
        "confianca": "alta",
        "fonte": "DJEN/CNJ",
        "data_documento": _safe_date(item),
        "tipo_documento": item.get("tipoDocumento"),
        "link": item.get("link"),
        "comunicacao_id": item.get("id"),
        "comunicacao_hash": item.get("hash"),
    }


def extract_defendant_parties(
    communications: list[dict[str, Any]],
) -> dict[str, Any]:
    """Extrai partes do polo réu apenas com rótulo explícito no DJEN.

    Não inferimos polo a partir de um nome solto. Só aceitamos cabeçalhos
    explícitos como RÉU:, REQUERIDO: ou RECLAMADO:. A classificação como
    empresa exige marcador empresarial objetivo no próprio nome.
    """
    found: list[dict[str, Any]] = []

    for item in communications or []:
        if not isinstance(item, dict):
            continue

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

    # Deduplica preservando a evidência mais recente.
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

    partes_re = list(by_key.values())

    empresas_by_name: dict[str, dict[str, Any]] = {}

    for row in partes_re:
        if not row.get("eh_empresa"):
            continue

        normalized = row.get("nome_normalizado")

        if not normalized:
            continue

        empresas_by_name[
            str(normalized)
        ] = row

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
        "metodo": "rotulo_explicito_polo_reu",
        "partes_re": partes_re,
        "empresas_re": empresas_re,
        "empresa_re_principal": principal,
    }

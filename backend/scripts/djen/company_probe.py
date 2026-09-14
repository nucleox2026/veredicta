from __future__ import annotations

from pathlib import Path
import json
import re
import sys


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.services.djen.client import DjenClient
from app.services.djen.party_extractor import extract_defendant_parties


def normalize_number(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 20:
        raise ValueError(
            "O número CNJ deve conter 20 dígitos."
        )
    return digits


def main() -> None:
    if len(sys.argv) != 2:
        raise SystemExit(
            "Uso: python company_probe.py NUMERO_CNJ"
        )

    numero = normalize_number(
        sys.argv[1]
    )

    result = DjenClient().get_communications(
        numero,
        itens_por_pagina=100,
        max_pages=5,
    )

    parties = extract_defendant_parties(
        result.items
    )

    print("Processo:", numero)
    print(
        "Comunicações DJEN:",
        len(result.items),
    )
    print()

    empresas = parties.get(
        "empresas_re"
    ) or []

    print("Empresas rés identificadas:")

    if not empresas:
        print("- nenhuma com confiança alta")
    else:
        for item in empresas:
            print(
                f"- {item.get('nome')} "
                f"| {item.get('papel')} "
                f"| {item.get('fonte')} "
                f"| {item.get('link') or '—'}"
            )

    print()
    print("JSON estruturado:")
    print(
        json.dumps(
            parties,
            ensure_ascii=False,
            indent=2,
        )
    )


if __name__ == "__main__":
    main()

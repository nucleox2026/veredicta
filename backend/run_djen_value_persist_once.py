from __future__ import annotations

import argparse
import json
import re
from dataclasses import asdict

from sqlalchemy import select

from app.db import SessionLocal
from app.models import ProcessAnalysis
from app.services.djen_client import DjenClient, DjenRateLimitError
from app.services.djen_value_extractor import extract_process_awards
from app.services.djen_value_persistence import (
    build_djen_persistence_preview,
    persist_djen_snapshot,
)


def normalize_number(value: str) -> str:
    digits = re.sub(r"\D", "", value or "")
    if len(digits) != 20:
        raise ValueError("O número CNJ deve conter 20 dígitos.")
    return digits


def brl(centavos: int | None) -> str:
    if centavos is None:
        return "—"
    value = centavos / 100
    formatted = f"{value:,.2f}".replace(",", "_").replace(".", ",").replace("_", ".")
    return f"R$ {formatted}"


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Consulta DJEN e persiste snapshot oficial em ProcessAnalysis."
    )
    parser.add_argument("tribunal", help="Ex.: TJMG")
    parser.add_argument("numero_processo", help="Número CNJ, com ou sem pontuação")
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persiste no banco. Sem esta flag, executa somente preview.",
    )
    args = parser.parse_args()

    tribunal = args.tribunal.strip().upper()
    numero = normalize_number(args.numero_processo)

    db = SessionLocal()
    try:
        analysis = db.execute(
            select(ProcessAnalysis).where(
                ProcessAnalysis.tribunal == tribunal,
                ProcessAnalysis.numero_processo == numero,
            )
        ).scalar_one_or_none()

        if analysis is None:
            raise SystemExit(
                "Processo não existe em process_analyses. "
                "A Etapa 8.2 não cria análise automaticamente."
            )

        client = DjenClient()
        try:
            result = client.get_communications(numero)
        except DjenRateLimitError as exc:
            raise SystemExit(
                f"DJEN rate limit: aguarde {exc.retry_after_seconds}s."
            ) from exc

        awards = extract_process_awards(result.items)
        preview = build_djen_persistence_preview(result, awards)

        print(f"Processo: {tribunal} {numero}")
        print(f"Comunicações DJEN: {len(result.items)}")
        print(f"Status: {preview.status}")
        print(
            "Dano moral (1º grau):",
            brl(preview.valor_dano_moral_primeiro_grau_centavos),
        )
        print(
            "Dano moral (final):",
            brl(preview.valor_dano_moral_final_centavos),
        )
        print(
            "Dano estético (1º grau):",
            brl(preview.valor_dano_estetico_primeiro_grau_centavos),
        )
        print(
            "Dano material (1º grau):",
            brl(preview.valor_dano_material_primeiro_grau_centavos),
        )
        print("Última comunicação hash:", preview.ultima_comunicacao_hash or "—")
        print()
        print("Preview estruturado:")
        print(json.dumps(asdict(preview), ensure_ascii=False, indent=2))

        if not args.apply:
            print()
            print("PREVIEW APENAS — nada foi gravado no banco.")
            print("Use --apply somente após conferir este resultado.")
            return

        persist_djen_snapshot(analysis, result, awards)
        db.commit()
        db.refresh(analysis)

        print()
        print("PERSISTÊNCIA DJEN: OK")
        print(f"djen_status = {analysis.djen_status}")
        print(f"djen_checked_at = {analysis.djen_checked_at}")
        print(
            "Campos canônicos valor_* permanecem inalterados nesta etapa."
        )
    finally:
        db.close()


if __name__ == "__main__":
    main()

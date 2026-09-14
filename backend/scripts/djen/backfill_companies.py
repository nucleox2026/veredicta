from __future__ import annotations

from pathlib import Path
import argparse
import sys
import time

from sqlalchemy import select


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import SessionLocal
from app.models import ProcessAnalysis
from app.services.djen.client import (
    DjenClient,
    DjenRateLimitError,
)
from app.services.djen.value_extractor import (
    extract_process_awards,
)
from app.services.djen.value_persistence import (
    persist_djen_snapshot,
)


def _already_checked(
    analysis: ProcessAnalysis,
) -> bool:
    snapshot = (
        analysis.djen_valores
        if isinstance(analysis.djen_valores, dict)
        else {}
    )

    return "partes" in snapshot


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Identifica empresas rés pelo DJEN em análises já salvas, "
            "sem repetir processos já verificados."
        )
    )
    parser.add_argument(
        "--limit",
        type=int,
        default=5,
        help=(
            "Quantidade máxima nesta execução. "
            "Padrão seguro: 5; máximo: 20."
        ),
    )
    parser.add_argument(
        "--tribunal",
        default=None,
        help="Opcional, ex.: TJMT",
    )
    parser.add_argument(
        "--all",
        action="store_true",
        help=(
            "Reprocessa inclusive registros cujo snapshot DJEN já contém "
            "verificação de partes."
        ),
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persiste. Sem esta flag, faz preview.",
    )
    args = parser.parse_args()

    limit = max(1, min(args.limit, 20))
    tribunal = (
        args.tribunal.strip().upper()
        if args.tribunal
        else None
    )

    db = SessionLocal()
    client = DjenClient()

    processed = 0
    identified = 0
    without_company = 0
    failed = 0

    try:
        query = select(
            ProcessAnalysis
        ).order_by(
            ProcessAnalysis.analyzed_at.desc().nullslast(),
            ProcessAnalysis.id.desc(),
        )

        if tribunal:
            query = query.where(
                ProcessAnalysis.tribunal == tribunal
            )

        analyses = list(
            db.scalars(query).all()
        )

        selected = []

        for analysis in analyses:
            if (
                not args.all
                and _already_checked(analysis)
            ):
                continue

            selected.append(analysis)

            if len(selected) >= limit:
                break

        if not selected:
            print(
                "Nenhuma análise pendente de verificação de empresa."
            )
            return

        print(
            f"Lote: {len(selected)} processo(s)"
        )
        print(
            "Modo:",
            "APLICAR" if args.apply else "PREVIEW",
        )
        print()

        for index, analysis in enumerate(
            selected,
            start=1,
        ):
            numero = analysis.numero_processo
            tribunal_item = (
                analysis.tribunal or "—"
            )

            print(
                f"[{index}/{len(selected)}] "
                f"{tribunal_item} {numero}"
            )

            try:
                result = client.get_communications(
                    numero,
                    itens_por_pagina=100,
                    max_pages=5,
                )
            except DjenRateLimitError as exc:
                print(
                    "DJEN rate limit. Pare o lote e "
                    f"aguarde {exc.retry_after_seconds}s."
                )
                break
            except Exception as exc:
                failed += 1
                print(
                    "Falha DJEN:",
                    type(exc).__name__,
                )
                continue

            awards = extract_process_awards(
                result.items
            )

            persist_djen_snapshot(
                analysis,
                result,
                awards,
            )

            snapshot = (
                analysis.djen_valores
                if isinstance(analysis.djen_valores, dict)
                else {}
            )
            partes = (
                snapshot.get("partes")
                if isinstance(snapshot, dict)
                else {}
            )
            empresas = (
                partes.get("empresas_re")
                if isinstance(partes, dict)
                else []
            ) or []

            processed += 1

            if empresas:
                identified += 1
                nomes = [
                    str(item.get("nome") or "")
                    for item in empresas
                    if isinstance(item, dict)
                    and item.get("nome")
                ]
                print(
                    "Empresa(s) oficial(is):",
                    " / ".join(nomes) or "—",
                )
            else:
                without_company += 1
                print(
                    "Empresa oficial: —"
                )

            if args.apply:
                db.commit()
                print("Persistido: OK")
            else:
                db.rollback()
                print(
                    "Preview: nada gravado"
                )

            if index < len(selected):
                time.sleep(0.5)

        print()
        print("Resumo do lote:")
        print(
            f"- verificados: {processed}"
        )
        print(
            f"- empresa identificada: {identified}"
        )
        print(
            f"- sem empresa oficial: {without_company}"
        )
        print(
            f"- falhas: {failed}"
        )

        if not args.apply:
            print()
            print(
                "PREVIEW APENAS. "
                "Use --apply para gravar."
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()

from __future__ import annotations

from pathlib import Path
import argparse
import sys

from sqlalchemy import select


BACKEND_ROOT = Path(__file__).resolve().parents[2]
if str(BACKEND_ROOT) not in sys.path:
    sys.path.insert(0, str(BACKEND_ROOT))

from app.db import SessionLocal
from app.models import ProcessAnalysis
from app.services.djen.party_extractor import (
    sanitize_saved_party_snapshot,
)
from app.services.analysis.enrichment import (
    normalize_company_name,
)


def _company_names(partes: dict) -> list[str]:
    empresas = partes.get("empresas_re") or []
    return [
        str(item.get("nome") or "").strip()
        for item in empresas
        if isinstance(item, dict)
        and str(item.get("nome") or "").strip()
    ]


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Corrige nomes de empresas já persistidos pelo primeiro extrator, "
            "sem nova consulta ao DJEN."
        )
    )
    parser.add_argument(
        "--apply",
        action="store_true",
        help="Persiste. Sem esta flag, mostra preview.",
    )
    args = parser.parse_args()

    db = SessionLocal()

    changed = 0
    examined = 0

    try:
        analyses = list(
            db.scalars(
                select(ProcessAnalysis).order_by(
                    ProcessAnalysis.id.asc()
                )
            ).all()
        )

        for analysis in analyses:
            snapshot = (
                analysis.djen_valores
                if isinstance(analysis.djen_valores, dict)
                else None
            )

            if not snapshot or "partes" not in snapshot:
                continue

            original_partes = snapshot.get("partes")
            cleaned_partes = sanitize_saved_party_snapshot(
                original_partes
            )

            examined += 1

            old_names = _company_names(
                original_partes
                if isinstance(original_partes, dict)
                else {}
            )
            new_names = _company_names(
                cleaned_partes
            )

            snapshot_changed = (
                original_partes != cleaned_partes
            )

            # Só corrige empresa_re quando o valor atual foi produzido
            # pelo snapshot antigo. Não apaga um nome independente da IA.
            old_joined = " / ".join(old_names)
            current = str(
                analysis.empresa_re or ""
            ).strip()

            company_field_changed = False

            if current and old_joined and current == old_joined:
                if new_names:
                    analysis.empresa_re = " / ".join(
                        new_names
                    )
                    analysis.empresa_re_normalizada = (
                        normalize_company_name(new_names[0])
                        if len(new_names) == 1
                        else None
                    )
                else:
                    analysis.empresa_re = None
                    analysis.empresa_re_normalizada = None

                company_field_changed = True

            if snapshot_changed:
                new_snapshot = dict(snapshot)
                new_snapshot["partes"] = cleaned_partes
                analysis.djen_valores = new_snapshot

            if not (
                snapshot_changed
                or company_field_changed
            ):
                continue

            changed += 1

            print(
                f"{analysis.tribunal or '—'} "
                f"{analysis.numero_processo}"
            )
            print(
                "  antes:",
                old_joined or "—",
            )
            print(
                "  depois:",
                " / ".join(new_names) or "—",
            )

            if args.apply:
                db.commit()
                print("  persistido: OK")
            else:
                db.rollback()
                print("  preview: nada gravado")

        print()
        print(
            f"Snapshots examinados: {examined}"
        )
        print(
            f"Registros a corrigir/corrigidos: {changed}"
        )

        if not args.apply:
            print(
                "PREVIEW APENAS. Rode novamente com --apply."
            )
    finally:
        db.close()


if __name__ == "__main__":
    main()

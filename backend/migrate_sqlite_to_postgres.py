import json
import sqlite3

from datetime import date, datetime

from sqlalchemy import func, select, text
from sqlalchemy.orm import Session

from app.db import Base, engine
from app.models import (
    ProcessAnalysis,
    ProcessRecord,
    SearchRun,
)


SQLITE_PATH = "veredicta_dev.db"


def parse_json(value):
    if value is None:
        return None

    if isinstance(
        value,
        (dict, list),
    ):
        return value

    try:
        return json.loads(value)
    except (json.JSONDecodeError, TypeError):
        return None


def parse_date(value):
    if not value:
        return None

    if isinstance(value, date):
        return value

    return date.fromisoformat(
        str(value)[:10]
    )


def parse_datetime(value):
    if not value:
        return None

    if isinstance(value, datetime):
        return value

    text_value = str(value)

    try:
        return datetime.fromisoformat(
            text_value
        )

    except ValueError:
        return None


def get_sqlite_connection():
    connection = sqlite3.connect(
        SQLITE_PATH
    )

    connection.row_factory = (
        sqlite3.Row
    )

    return connection


def ensure_target_is_empty(
    session: Session,
):
    counts = {
        "search_runs":
            session.scalar(
                select(
                    func.count(
                        SearchRun.id
                    )
                )
            ) or 0,

        "process_records":
            session.scalar(
                select(
                    func.count(
                        ProcessRecord.id
                    )
                )
            ) or 0,

        "process_analyses":
            session.scalar(
                select(
                    func.count(
                        ProcessAnalysis.id
                    )
                )
            ) or 0,
    }

    if any(counts.values()):
        raise RuntimeError(
            "O PostgreSQL não está vazio. "
            f"Contagens atuais: {counts}. "
            "Migração cancelada para evitar duplicidade."
        )


def migrate_search_runs(
    sqlite_conn,
    session: Session,
):
    rows = sqlite_conn.execute(
        """
        SELECT *
        FROM search_runs
        ORDER BY id
        """
    ).fetchall()

    for row in rows:
        session.add(
            SearchRun(
                id=row["id"],
                tribunal=row["tribunal"],
                date_from=parse_date(
                    row["date_from"]
                ),
                date_to=parse_date(
                    row["date_to"]
                ),
                subject_text=(
                    row["subject_text"]
                ),
                status=row["status"],
                total_found=(
                    row["total_found"]
                ),
                created_at=parse_datetime(
                    row["created_at"]
                ),
            )
        )

    session.commit()

    print(
        f"search_runs: {len(rows)} migrados"
    )


def migrate_process_records(
    sqlite_conn,
    session: Session,
):
    rows = sqlite_conn.execute(
        """
        SELECT *
        FROM process_records
        ORDER BY id
        """
    ).fetchall()

    total = len(rows)

    for index, row in enumerate(
        rows,
        start=1,
    ):
        session.add(
            ProcessRecord(
                id=row["id"],

                numero_processo=(
                    row["numero_processo"]
                ),

                tribunal=row["tribunal"],

                data_ajuizamento=
                    parse_datetime(
                        row[
                            "data_ajuizamento"
                        ]
                    ),

                grau=row["grau"],

                classe_nome=(
                    row["classe_nome"]
                ),

                orgao_julgador_nome=(
                    row[
                        "orgao_julgador_nome"
                    ]
                ),

                assuntos=parse_json(
                    row["assuntos"]
                ),

                raw_source=(
                    parse_json(
                        row["raw_source"]
                    )
                    or {}
                ),

                created_at=parse_datetime(
                    row["created_at"]
                ),
            )
        )

        if index % 100 == 0:
            session.commit()

            print(
                f"process_records: "
                f"{index}/{total}"
            )

    session.commit()

    print(
        f"process_records: "
        f"{total}/{total} migrados"
    )


def migrate_process_analyses(
    sqlite_conn,
    session: Session,
):
    rows = sqlite_conn.execute(
        """
        SELECT *
        FROM process_analyses
        ORDER BY id
        """
    ).fetchall()

    for row in rows:
        session.add(
            ProcessAnalysis(
                id=row["id"],

                numero_processo=(
                    row["numero_processo"]
                ),

                dano_moral=(
                    row["dano_moral"]
                ),

                direito_personalidade=(
                    row[
                        "direito_personalidade"
                    ]
                ),

                empresa_re=(
                    row["empresa_re"]
                ),

                resultado=(
                    row["resultado"]
                ),

                valor_indenizacao_centavos=(
                    row[
                        "valor_indenizacao_centavos"
                    ]
                ),

                resumo=row["resumo"],

                fundamentos=parse_json(
                    row["fundamentos"]
                ),

                confianca=(
                    row["confianca"]
                ),

                model_name=(
                    row["model_name"]
                ),

                created_at=parse_datetime(
                    row["created_at"]
                ),
            )
        )

    session.commit()

    print(
        f"process_analyses: "
        f"{len(rows)} migrados"
    )


def reset_postgres_sequences():
    tables = [
        "search_runs",
        "process_records",
        "process_analyses",
    ]

    with engine.begin() as conn:
        for table in tables:
            conn.execute(
                text(
                    f"""
                    SELECT setval(
                        pg_get_serial_sequence(
                            '{table}',
                            'id'
                        ),
                        COALESCE(
                            (
                                SELECT MAX(id)
                                FROM {table}
                            ),
                            1
                        ),
                        true
                    )
                    """
                )
            )

    print(
        "Sequências PostgreSQL atualizadas."
    )


def main():
    print(
        "Criando/verificando tabelas..."
    )

    Base.metadata.create_all(
        bind=engine
    )

    sqlite_conn = (
        get_sqlite_connection()
    )

    try:
        with Session(engine) as session:
            ensure_target_is_empty(
                session
            )

            print(
                "Iniciando migração..."
            )

            migrate_search_runs(
                sqlite_conn,
                session,
            )

            migrate_process_records(
                sqlite_conn,
                session,
            )

            migrate_process_analyses(
                sqlite_conn,
                session,
            )

        reset_postgres_sequences()

        print()
        print(
            "MIGRAÇÃO CONCLUÍDA."
        )

    finally:
        sqlite_conn.close()


if __name__ == "__main__":
    main()
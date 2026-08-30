from datetime import date, datetime
from sqlalchemy import Date, DateTime, Integer, JSON, String, Text
from sqlalchemy.orm import Mapped, mapped_column
from .db import Base


class SearchRun(Base):
    __tablename__ = "search_runs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tribunal: Mapped[str] = mapped_column(String(20), default="TJMT", index=True)
    date_from: Mapped[date] = mapped_column(Date)
    date_to: Mapped[date] = mapped_column(Date)
    subject_text: Mapped[str | None] = mapped_column(String(255), nullable=True)
    status: Mapped[str] = mapped_column(String(30), default="created", index=True)
    total_found: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProcessRecord(Base):
    __tablename__ = "process_records"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    numero_processo: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    tribunal: Mapped[str] = mapped_column(String(20), default="TJMT", index=True)
    data_ajuizamento: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    grau: Mapped[str | None] = mapped_column(String(20), nullable=True)
    classe_nome: Mapped[str | None] = mapped_column(String(255), nullable=True)
    orgao_julgador_nome: Mapped[str | None] = mapped_column(String(500), nullable=True)
    assuntos: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    raw_source: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)


class ProcessAnalysis(Base):
    __tablename__ = "process_analyses"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    tribunal: Mapped[str | None] = mapped_column(String(20), nullable=True, index=True)
    numero_processo: Mapped[str] = mapped_column(String(40), unique=True, index=True)
    dano_moral: Mapped[str | None] = mapped_column(String(30), nullable=True)
    direito_personalidade: Mapped[str | None] = mapped_column(String(255), nullable=True)
    empresa_re: Mapped[str | None] = mapped_column(String(500), nullable=True)
    resultado: Mapped[str | None] = mapped_column(String(100), nullable=True)
    valor_indenizacao_centavos: Mapped[int | None] = mapped_column(Integer, nullable=True)
    resumo: Mapped[str | None] = mapped_column(Text, nullable=True)
    fundamentos: Mapped[dict | list | None] = mapped_column(JSON, nullable=True)
    confianca: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_name: Mapped[str | None] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=datetime.utcnow)

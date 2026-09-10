from __future__ import annotations
from typing import Any
from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import select
from sqlalchemy.orm import Session
from ..db import get_db
from ..models import ProcessAnalysis

router = APIRouter(prefix="/api/v1/djen-values", tags=["djen-values"])

def _evidence(snapshot: dict[str, Any], key: str):
    awards = snapshot.get("awards") if isinstance(snapshot, dict) else None
    if not isinstance(awards, dict):
        return None
    for item in reversed(awards.get(key) or []):
        if not isinstance(item, dict):
            continue
        ev = item.get("evidencia") or {}
        if ev.get("secao") == "dispositivo" and ev.get("confianca") == "alta":
            return {
                "valor_centavos": item.get("valor_centavos"),
                "data": item.get("data"),
                "tipo_documento": item.get("tipo_documento"),
                "link": item.get("link") or ev.get("link"),
                "trecho": ev.get("trecho"),
                "confianca": ev.get("confianca"),
                "secao": ev.get("secao"),
            }
    return None

def _serialize(a: ProcessAnalysis):
    snap = a.djen_valores if isinstance(a.djen_valores, dict) else {}
    preview = snap.get("preview") if isinstance(snap.get("preview"), dict) else {}
    return {
        "tribunal": a.tribunal,
        "numero_processo": a.numero_processo,
        "djen_status": a.djen_status,
        "djen_checked_at": a.djen_checked_at.isoformat() if a.djen_checked_at else None,
        "fonte": snap.get("fonte") or "DJEN/CNJ",
        "valor_dano_moral_primeiro_grau_centavos": preview.get("valor_dano_moral_primeiro_grau_centavos"),
        "valor_dano_moral_final_centavos": preview.get("valor_dano_moral_final_centavos"),
        "valor_dano_estetico_primeiro_grau_centavos": preview.get("valor_dano_estetico_primeiro_grau_centavos"),
        "valor_dano_material_primeiro_grau_centavos": preview.get("valor_dano_material_primeiro_grau_centavos"),
        "evidencia_dano_moral": _evidence(snap, "historico_dano_moral"),
        "evidencia_dano_estetico": _evidence(snap, "historico_dano_estetico"),
        "evidencia_dano_material": _evidence(snap, "historico_dano_material"),
        "documento_principal": (
            snap.get("documento_principal")
            if isinstance(snap.get("documento_principal"), dict)
            else None
        ),
        "documentos_relevantes": (
            snap.get("documentos_relevantes")
            if isinstance(snap.get("documentos_relevantes"), list)
            else []
        ),
        "publicacao_decisoria_localizada": bool(
            snap.get("documentos_relevantes")
            if isinstance(snap.get("documentos_relevantes"), list)
            else []
        ),
    }

@router.get("/analyses")
def list_values(
    somente_com_valor_moral: bool = Query(False),
    limit: int = Query(100, ge=1, le=500),
    db: Session = Depends(get_db),
):
    rows = db.execute(
        select(ProcessAnalysis)
        .where(ProcessAnalysis.djen_valores.is_not(None))
        .order_by(ProcessAnalysis.djen_checked_at.desc().nullslast())
    ).scalars().all()
    items = [_serialize(x) for x in rows]
    if somente_com_valor_moral:
        items = [x for x in items if x["valor_dano_moral_final_centavos"] is not None]
    return {
        "total": len(items),
        "metrics": {
            "com_snapshot_djen": len(items),
            "com_valor_dano_moral": sum(x["valor_dano_moral_final_centavos"] is not None for x in items),
        },
        "items": items[:limit],
    }

@router.get("/analyses/{tribunal}/{numero_processo}")
def get_value(tribunal: str, numero_processo: str, db: Session = Depends(get_db)):
    numero = "".join(c for c in numero_processo if c.isdigit())
    a = db.execute(select(ProcessAnalysis).where(
        ProcessAnalysis.tribunal == tribunal.upper(),
        ProcessAnalysis.numero_processo == numero,
    )).scalar_one_or_none()
    if a is None:
        raise HTTPException(404, "Análise não encontrada.")
    if a.djen_valores is None:
        raise HTTPException(404, "Sem snapshot DJEN.")
    return _serialize(a)

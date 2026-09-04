from __future__ import annotations

from datetime import datetime, timedelta, timezone
import hashlib
import json
from typing import Any

from ..models import ProcessWatch


QUIET_WINDOW_MINUTES = 10

STATUS_MONITORANDO = "monitorando"
STATUS_AGUARDANDO = "aguardando"


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _normalize_for_hash(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): _normalize_for_hash(item)
            for key, item in sorted(
                value.items(),
                key=lambda pair: str(pair[0]),
            )
            if item is not None
        }

    if isinstance(value, list):
        normalized = [
            _normalize_for_hash(item)
            for item in value
        ]

        return sorted(
            normalized,
            key=lambda item: json.dumps(
                item,
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                default=str,
            ),
        )

    if isinstance(value, str):
        return value.strip()

    return value


def _unwrap_source(
    process_payload: dict[str, Any] | None,
) -> dict[str, Any]:
    if not isinstance(process_payload, dict):
        return {}

    raw_source = process_payload.get(
        "raw_source"
    )

    if isinstance(raw_source, dict):
        return raw_source

    source = process_payload.get(
        "_source"
    )

    if isinstance(source, dict):
        return source

    return process_payload


def extract_movements(
    process_payload: dict[str, Any] | None,
) -> list[Any]:
    source = _unwrap_source(
        process_payload
    )

    movements = source.get(
        "movimentos"
    )

    if isinstance(movements, list):
        return movements

    return []


def movements_hash(
    process_payload: dict[str, Any] | None,
) -> str:
    normalized = _normalize_for_hash(
        extract_movements(process_payload)
    )

    encoded = json.dumps(
        normalized,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        default=str,
    ).encode("utf-8")

    return hashlib.sha256(
        encoded
    ).hexdigest()


def _parse_datetime(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None

    text = value.strip()

    if not text:
        return None

    try:
        parsed = datetime.fromisoformat(
            text.replace("Z", "+00:00")
        )
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


def _walk_datetimes(value: Any) -> list[datetime]:
    found: list[datetime] = []

    if isinstance(value, dict):
        for key, item in value.items():
            key_lower = str(
                key
            ).lower()

            if (
                "data" in key_lower
                or "date" in key_lower
                or "hora" in key_lower
            ):
                parsed = _parse_datetime(
                    item
                )

                if parsed is not None:
                    found.append(
                        parsed
                    )

            found.extend(
                _walk_datetimes(
                    item
                )
            )

    elif isinstance(value, list):
        for item in value:
            found.extend(
                _walk_datetimes(
                    item
                )
            )

    return found


def latest_movement_datetime(
    process_payload: dict[str, Any] | None,
) -> datetime | None:
    dates = _walk_datetimes(
        extract_movements(
            process_payload
        )
    )

    if not dates:
        return None

    return max(
        dates
    )


def is_due_for_auto_analysis(
    watch: ProcessWatch,
    *,
    now: datetime | None = None,
) -> bool:
    now = now or utc_now()

    return bool(
        watch.ativo
        and watch.status == STATUS_AGUARDANDO
        and watch.reanalisar_apos is not None
        and watch.reanalisar_apos <= now
    )


def observe_process_snapshot(
    watch: ProcessWatch,
    process_payload: dict[str, Any],
    *,
    now: datetime | None = None,
    quiet_minutes: int = QUIET_WINDOW_MINUTES,
) -> dict[str, Any]:
    if quiet_minutes <= 0:
        raise ValueError(
            "quiet_minutes deve ser maior que zero."
        )

    now = now or utc_now()

    current_hash = movements_hash(
        process_payload
    )

    latest_date = latest_movement_datetime(
        process_payload
    )

    previous_hash = (
        watch.ultimo_hash_movimentos
    )

    first_observation = (
        previous_hash is None
    )

    changed = (
        previous_hash is not None
        and previous_hash != current_hash
    )

    watch.ultima_verificacao = now
    watch.updated_at = now

    if latest_date is not None:
        watch.ultima_data_movimento = (
            latest_date
        )

    if first_observation:
        watch.ultimo_hash_movimentos = (
            current_hash
        )
        watch.status = (
            STATUS_MONITORANDO
        )
        watch.atividade_detectada_em = None
        watch.reanalisar_apos = None
        watch.erro_ultimo = None

        return {
            "baseline_criada": True,
            "mudanca_detectada": False,
            "reanalisar_agora": False,
            "reanalisar_apos": None,
            "hash_movimentos": current_hash,
        }

    if changed:
        deadline = now + timedelta(
            minutes=quiet_minutes
        )

        watch.ultimo_hash_movimentos = (
            current_hash
        )
        watch.atividade_detectada_em = (
            now
        )
        watch.reanalisar_apos = (
            deadline
        )
        watch.status = (
            STATUS_AGUARDANDO
        )
        watch.erro_ultimo = None

        return {
            "baseline_criada": False,
            "mudanca_detectada": True,
            "reanalisar_agora": False,
            "reanalisar_apos": deadline,
            "hash_movimentos": current_hash,
        }

    due = is_due_for_auto_analysis(
        watch,
        now=now,
    )

    return {
        "baseline_criada": False,
        "mudanca_detectada": False,
        "reanalisar_agora": due,
        "reanalisar_apos": (
            watch.reanalisar_apos
        ),
        "hash_movimentos": current_hash,
    }

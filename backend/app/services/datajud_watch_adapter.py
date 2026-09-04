from __future__ import annotations

import inspect
from typing import Any

from .datajud_multi import DataJudMultiClient


def _settings():
    from ..settings import get_settings
    return get_settings()


def _api_key_from_settings(settings: Any) -> str | None:
    candidates = (
        "datajud_api_key",
        "DATAJUD_API_KEY",
        "datajud_key",
    )

    for name in candidates:
        value = getattr(
            settings,
            name,
            None,
        )

        if isinstance(value, str) and value.strip():
            return value.strip()

    return None


def build_datajud_client() -> DataJudMultiClient:
    """
    Monta DataJudMultiClient sem expor credenciais.

    O projeto já possui esse cliente; este adaptador existe
    apenas para o worker reutilizar a mesma integração.
    """
    signature = inspect.signature(
        DataJudMultiClient
    )

    required = [
        param
        for param in signature.parameters.values()
        if param.default is inspect._empty
        and param.kind
        in (
            inspect.Parameter.POSITIONAL_ONLY,
            inspect.Parameter.POSITIONAL_OR_KEYWORD,
            inspect.Parameter.KEYWORD_ONLY,
        )
    ]

    if not required:
        return DataJudMultiClient()

    settings = _settings()
    api_key = _api_key_from_settings(
        settings
    )

    kwargs: dict[str, Any] = {}

    for param in required:
        name = param.name.lower()

        if name in {
            "settings",
            "config",
            "configuration",
        }:
            kwargs[param.name] = settings
            continue

        if (
            "api" in name
            and "key" in name
        ):
            if not api_key:
                raise RuntimeError(
                    "DataJud API key não encontrada "
                    "nas configurações."
                )

            kwargs[param.name] = api_key
            continue

        raise RuntimeError(
            "Não foi possível montar automaticamente "
            "DataJudMultiClient. Parâmetro obrigatório "
            f"desconhecido: {param.name}. "
            f"Assinatura: {signature}"
        )

    return DataJudMultiClient(
        **kwargs
    )


def fetch_process_from_datajud(
    client: DataJudMultiClient,
    tribunal: str,
    numero_processo: str,
) -> dict[str, Any]:
    method = client.get_process

    # Primeiro usa a assinatura nominal esperada.
    try:
        result = method(
            tribunal=tribunal,
            numero_processo=numero_processo,
        )
    except TypeError:
        # Compatibilidade com implementação posicional.
        result = method(
            tribunal,
            numero_processo,
        )

    if inspect.isawaitable(result):
        raise RuntimeError(
            "get_process retornou awaitable. "
            "O worker atual espera cliente síncrono."
        )

    if not isinstance(result, dict):
        raise TypeError(
            "DataJud get_process deve retornar dict; "
            f"recebido: {type(result).__name__}"
        )

    return result

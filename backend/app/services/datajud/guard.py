import copy
import hashlib
import json
import threading
import time
from collections import OrderedDict, deque
from typing import Any


# =========================================================
# PROTEÇÃO LOCAL DA API PÚBLICA DATAJUD
# =========================================================
#
# O CNJ estabelece limite externo de requisições.
# A Veredicta trabalha abaixo dele, com margem.
#
# Este controle é por processo Python. No deploy atual,
# com um único processo Uvicorn, funciona como proteção
# global do backend.
#
# Se futuramente houver múltiplas instâncias/workers,
# este componente deve migrar para um controle distribuído
# (por exemplo, Redis).
# =========================================================

MAX_REQUESTS_PER_MINUTE = 100
RATE_WINDOW_SECONDS = 60.0

CACHE_TTL_SECONDS = 45.0
CACHE_MAX_ENTRIES = 64


class DataJudRequestGuard:
    def __init__(
        self,
        max_requests: int = (
            MAX_REQUESTS_PER_MINUTE
        ),
        window_seconds: float = (
            RATE_WINDOW_SECONDS
        ),
        cache_ttl_seconds: float = (
            CACHE_TTL_SECONDS
        ),
        cache_max_entries: int = (
            CACHE_MAX_ENTRIES
        ),
    ):
        self.max_requests = max(
            1,
            int(max_requests),
        )

        self.window_seconds = max(
            0.01,
            float(window_seconds),
        )

        self.cache_ttl_seconds = max(
            0.0,
            float(cache_ttl_seconds),
        )

        self.cache_max_entries = max(
            1,
            int(cache_max_entries),
        )

        self._lock = threading.Lock()

        self._request_times: deque[
            float
        ] = deque()

        self._cache: OrderedDict[
            str,
            tuple[float, Any],
        ] = OrderedDict()

        self._cache_hits = 0
        self._cache_misses = 0
        self._requests_released = 0
        self._wait_count = 0


    @staticmethod
    def make_cache_key(
        tribunal: str,
        payload: dict,
    ) -> str:
        """
        Gera uma chave sem armazenar conteúdo sensível.

        A chave depende apenas do tribunal + payload.
        A API key nunca entra no cache.
        """

        serialized = json.dumps(
            {
                "tribunal": tribunal,
                "payload": payload,
            },
            ensure_ascii=False,
            sort_keys=True,
            separators=(
                ",",
                ":",
            ),
            default=str,
        )

        return hashlib.sha256(
            serialized.encode(
                "utf-8"
            )
        ).hexdigest()


    def _purge_expired_cache_locked(
        self,
        now: float,
    ) -> None:
        expired = [
            key
            for key, (
                expires_at,
                _value,
            ) in self._cache.items()
            if expires_at <= now
        ]

        for key in expired:
            self._cache.pop(
                key,
                None,
            )


    def get_cached(
        self,
        key: str,
    ):
        if (
            self.cache_ttl_seconds
            <= 0
        ):
            return None

        now = time.monotonic()

        with self._lock:
            self._purge_expired_cache_locked(
                now
            )

            item = self._cache.get(
                key
            )

            if item is None:
                self._cache_misses += 1
                return None

            expires_at, value = item

            if expires_at <= now:
                self._cache.pop(
                    key,
                    None,
                )

                self._cache_misses += 1
                return None

            self._cache.move_to_end(
                key
            )

            self._cache_hits += 1

            return copy.deepcopy(
                value
            )


    def set_cached(
        self,
        key: str,
        value,
    ) -> None:
        if (
            self.cache_ttl_seconds
            <= 0
        ):
            return

        now = time.monotonic()

        expires_at = (
            now
            + self.cache_ttl_seconds
        )

        with self._lock:
            self._purge_expired_cache_locked(
                now
            )

            self._cache[
                key
            ] = (
                expires_at,
                copy.deepcopy(
                    value
                ),
            )

            self._cache.move_to_end(
                key
            )

            while (
                len(self._cache)
                > self.cache_max_entries
            ):
                self._cache.popitem(
                    last=False
                )


    def acquire(self) -> float:
        """
        Reserva uma chamada real ao DataJud.

        Quando o teto interno é atingido, aguarda
        até existir espaço na janela móvel.

        Retorna quantos segundos esta chamada
        precisou aguardar.
        """

        started = time.monotonic()

        waited = False

        while True:
            now = time.monotonic()

            with self._lock:
                cutoff = (
                    now
                    - self.window_seconds
                )

                while (
                    self._request_times
                    and self
                    ._request_times[0]
                    <= cutoff
                ):
                    self._request_times.popleft()

                if (
                    len(
                        self._request_times
                    )
                    < self.max_requests
                ):
                    self._request_times.append(
                        now
                    )

                    self._requests_released += 1

                    if waited:
                        self._wait_count += 1

                    return (
                        time.monotonic()
                        - started
                    )

                wait_for = max(
                    0.01,
                    (
                        self._request_times[0]
                        + self.window_seconds
                        - now
                    ),
                )

            waited = True

            # Dorme fora do lock para não impedir
            # outras threads de consultar o cache.
            time.sleep(
                min(
                    wait_for,
                    1.0,
                )
            )


    def snapshot(self) -> dict:
        """
        Métricas locais úteis para diagnóstico.
        Não são persistidas.
        """

        now = time.monotonic()

        with self._lock:
            cutoff = (
                now
                - self.window_seconds
            )

            while (
                self._request_times
                and self
                ._request_times[0]
                <= cutoff
            ):
                self._request_times.popleft()

            self._purge_expired_cache_locked(
                now
            )

            return {
                "max_requests": (
                    self.max_requests
                ),
                "window_seconds": (
                    self.window_seconds
                ),
                "requests_in_window": (
                    len(
                        self._request_times
                    )
                ),
                "requests_released": (
                    self._requests_released
                ),
                "wait_count": (
                    self._wait_count
                ),
                "cache_ttl_seconds": (
                    self.cache_ttl_seconds
                ),
                "cache_entries": (
                    len(
                        self._cache
                    )
                ),
                "cache_hits": (
                    self._cache_hits
                ),
                "cache_misses": (
                    self._cache_misses
                ),
            }


DATAJUD_GUARD = (
    DataJudRequestGuard()
)

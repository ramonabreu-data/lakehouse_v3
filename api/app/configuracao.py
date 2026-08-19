"""Configuracao por ambiente.

Tudo e lido na criacao da aplicacao (nao no import) para que o processo suba
com o .env do compose e a suite consiga montar variantes sem recarregar modulo.
"""

from __future__ import annotations

import os
from dataclasses import dataclass


def _inteiro(nome: str, padrao: int) -> int:
    try:
        return int(os.getenv(nome, str(padrao)))
    except ValueError:
        return padrao


@dataclass(frozen=True)
class Configuracao:
    dremio_endpoint: str
    dremio_flight: str
    dremio_usuario: str
    dremio_senha: str
    consulta_tempo_limite: float
    redis_url: str
    cache_ttl: int
    limite_por_minuto: int
    cors_origens: tuple[str, ...]

    @property
    def cors_liberado_para_todos(self) -> bool:
        return "*" in self.cors_origens


def carregar() -> Configuracao:
    origens = tuple(
        origem.strip()
        for origem in os.getenv("API_CORS_ORIGENS", "*").split(",")
        if origem.strip()
    ) or ("*",)
    return Configuracao(
        dremio_endpoint=os.getenv("DREMIO_ENDPOINT", "dremio:9047"),
        dremio_flight=os.getenv("DREMIO_FLIGHT_ENDPOINT", "dremio:32010"),
        dremio_usuario=os.getenv("DREMIO_USERNAME", ""),
        dremio_senha=os.getenv("DREMIO_PASSWORD", ""),
        consulta_tempo_limite=float(os.getenv("API_TEMPO_LIMITE_CONSULTA", "60")),
        redis_url=os.getenv("API_REDIS_URL", os.getenv("CELERY_BROKER_URL", "")),
        cache_ttl=_inteiro("API_CACHE_TTL", 300),
        limite_por_minuto=_inteiro("API_LIMITE_POR_MINUTO", 120),
        cors_origens=origens,
    )

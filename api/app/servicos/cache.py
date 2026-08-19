"""Cache das respostas no Redis que a stack ja usa para o Celery.

Duas decisoes que valem registro:

1. A chave inclui a versao do dado (o carimbo do refinamento). Dado novo troca
   todas as chaves de uma vez — mesma logica do `@st.cache_data` do painel.
2. Falha do Redis nunca derruba a requisicao. Cache aqui e otimizacao; sem ele
   a API responde mais devagar, e so.
"""

from __future__ import annotations

import hashlib
import json
import logging
from typing import Any

registrador = logging.getLogger(__name__)


class Cache:
    def __init__(self, cliente: Any | None, ttl: int) -> None:
        self.cliente = cliente
        self.ttl = ttl

    def chave(self, *partes: str) -> str:
        digestao = hashlib.sha256("\x00".join(partes).encode("utf-8")).hexdigest()
        return f"api:resposta:{digestao}"

    def obter(self, chave: str) -> Any | None:
        if self.cliente is None or self.ttl <= 0:
            return None
        try:
            guardado = self.cliente.get(chave)
        except Exception:  # noqa: BLE001 — Redis fora do ar nao e erro do cliente
            registrador.warning("Cache indisponivel na leitura; seguindo sem ele.", exc_info=True)
            return None
        return json.loads(guardado) if guardado else None

    def guardar(self, chave: str, valor: Any) -> None:
        if self.cliente is None or self.ttl <= 0:
            return
        try:
            self.cliente.setex(chave, self.ttl, json.dumps(valor, ensure_ascii=False))
        except Exception:  # noqa: BLE001
            registrador.warning("Cache indisponivel na escrita; seguindo sem ele.", exc_info=True)

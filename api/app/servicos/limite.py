"""Limite de requisicoes por minuto, por identidade.

Uma API publicada na internet sem isto e um SELECT do lakehouse a cada clique de
quem quiser. A janela e fixa por minuto — grosseira, mas suficiente para conter
laco descontrolado no cliente, e barata (uma chave por minuto).

Com Redis o limite vale para a stack inteira; sem ele, cai para memoria do
processo (ainda util, mas conta separado por worker do uvicorn).
"""

from __future__ import annotations

import logging
import time
from collections import defaultdict
from threading import Lock
from typing import Any

registrador = logging.getLogger(__name__)


class Limitador:
    def __init__(self, por_minuto: int, cliente: Any | None = None) -> None:
        self.por_minuto = por_minuto
        self.cliente = cliente
        self._memoria: dict[tuple[str, int], int] = defaultdict(int)
        self._trava = Lock()

    def permitir(self, identidade: str) -> bool:
        if self.por_minuto <= 0:      # 0 desliga o limite
            return True
        janela = int(time.time() // 60)
        if self.cliente is not None:
            try:
                return self._contar_no_redis(identidade, janela) <= self.por_minuto
            except Exception:  # noqa: BLE001 — Redis fora do ar nao bloqueia a API
                registrador.warning("Limitador sem Redis; usando contagem local.", exc_info=True)
        return self._contar_na_memoria(identidade, janela) <= self.por_minuto

    def _contar_no_redis(self, identidade: str, janela: int) -> int:
        chave = f"api:limite:{identidade}:{janela}"
        transacao = self.cliente.pipeline()
        transacao.incr(chave)
        transacao.expire(chave, 120)
        return int(transacao.execute()[0])

    def _contar_na_memoria(self, identidade: str, janela: int) -> int:
        with self._trava:
            for chave in [c for c in self._memoria if c[1] < janela]:
                del self._memoria[chave]
            self._memoria[(identidade, janela)] += 1
            return self._memoria[(identidade, janela)]

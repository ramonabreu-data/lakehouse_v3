"""Servicos — a orquestracao entre o pedido e a fonte.

E aqui que as pecas se encontram: valida o pedido contra o catalogo (nucleo),
escolhe o motor pela `Fonte` do conjunto, guarda a resposta no cache. Nenhuma
linha de HTTP e nenhuma linha de SQL.

Quem consome e `web/`; quem e consumido e `motores/`.
"""

from __future__ import annotations

from app.servicos.dados import Servico

__all__ = ["Servico"]

"""Arrow -> estruturas que o `json` da biblioteca padrao aceita.

Fica em `motores/` porque Arrow e o formato de troca entre motor e servico (ver
`motores/base.py`), e nao um detalhe do Dremio.

O ponto delicado sao data, decimal e NaN: o pyarrow devolve objetos Python
(datetime.date, Decimal) e floats nao finitos que virariam `NaN` literal no
corpo — JSON invalido, que o `fetch` do navegador recusa.
"""

from __future__ import annotations

import base64
import datetime as dt
import math
from decimal import Decimal
from typing import Any

import pyarrow as pa


def _valor(bruto: Any) -> Any:
    if bruto is None:
        return None
    if isinstance(bruto, bool):
        return bruto
    if isinstance(bruto, float):
        # NaN e infinito nao existem em JSON.
        return bruto if math.isfinite(bruto) else None
    if isinstance(bruto, Decimal):
        return float(bruto)
    # datetime e subclasse de date: precisa vir antes.
    if isinstance(bruto, (dt.datetime, dt.date, dt.time)):
        return bruto.isoformat()
    if isinstance(bruto, dt.timedelta):
        return bruto.total_seconds()
    if isinstance(bruto, bytes):
        return base64.b64encode(bruto).decode("ascii")
    if isinstance(bruto, dict):
        return {chave: _valor(valor) for chave, valor in bruto.items()}
    if isinstance(bruto, (list, tuple)):
        return [_valor(item) for item in bruto]
    return bruto


def tabela_para_registros(tabela: pa.Table) -> list[dict[str, Any]]:
    """Uma lista de dicionarios, um por linha, na ordem das colunas."""
    return [{chave: _valor(valor) for chave, valor in linha.items()} for linha in tabela.to_pylist()]


def primeiro_escalar(tabela: pa.Table) -> Any:
    """Primeira celula da tabela — usado no COUNT(*) da paginacao."""
    if tabela.num_rows == 0 or tabela.num_columns == 0:
        return None
    return _valor(tabela.column(0)[0].as_py())

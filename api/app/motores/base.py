"""O contrato que toda fonte de dados precisa cumprir.

Um motor sabe responder tres perguntas sobre um conjunto — os registros, a
contagem e a agregacao — recebendo o pedido JA validado pelo nucleo. Como ele
faz isso e problema dele: SQL, chamada HTTP, driver proprio.

O formato de troca e uma tabela Arrow. Nao e detalhe do Dremio: e a moeda do
lakehouse (o Flight fala Arrow, o Spark grava Iceberg lido como Arrow) e evita
uma conversao a toa no meio do caminho. Um motor que nao fale Arrow nativamente
converte ao devolver — a fronteira e clara.

Para acrescentar uma fonte, crie `app/motores/<nome>/` expondo:

    NOME             identificador usado em Fonte(motor=...)
    conferir_fonte   valida o endereco no import do catalogo
    construir        recebe a Configuracao e devolve o motor pronto
"""

from __future__ import annotations

from typing import Protocol

import pyarrow as pa

from app.nucleo import Conjunto, Consulta, Resumo


class Motor(Protocol):
    """O que `servicos/` espera de qualquer fonte."""

    nome: str

    def dados(self, conjunto: Conjunto, consulta: Consulta) -> pa.Table:
        """Registros do conjunto, ja filtrados, ordenados e paginados."""

    def total(self, conjunto: Conjunto, consulta: Consulta) -> int | None:
        """Quantos registros atendem aos filtros, ignorando a paginacao."""

    def resumo(self, conjunto: Conjunto, resumo: Resumo) -> pa.Table:
        """Agregacao calculada na propria fonte, nao em memoria aqui."""

    def verificar(self) -> None:
        """Estoura se a fonte nao estiver respondendo. Usado na prontidao."""

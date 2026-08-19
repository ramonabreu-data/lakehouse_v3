"""Motor Dremio — a fonte de hoje.

Amarra as duas metades: `sql.py` decide o comando, `cliente.py` leva ate o
Dremio por Arrow Flight. Quem chama (em `servicos/`) nao sabe que existe SQL no
meio — so pede dados, total ou resumo.
"""

from __future__ import annotations

import pyarrow as pa

from app.configuracao import Configuracao
from app.motores.arrow import primeiro_escalar
from app.motores.dremio import sql
from app.motores.dremio.cliente import ClienteDremio, ErroDremio
from app.nucleo import CatalogoInvalido, Conjunto, Consulta, Fonte, Resumo

__all__ = ["NOME", "ErroDremio", "MotorDremio", "conferir_fonte", "construir", "fonte"]

NOME = "dremio"

# A API le exclusivamente views curadas. Tabela Iceberg crua e fonte conectada
# (Postgres, Mongo) ficam de fora — sao camadas internas do lakehouse.
ESPACO_PERMITIDO = "refinamento."


def fonte(endereco: str) -> Fonte:
    """Atalho para o catalogo: `fonte("refinamento.espaco.view")`."""
    return Fonte(NOME, endereco)


def conferir_fonte(alvo: Fonte) -> None:
    if not alvo.endereco.startswith(ESPACO_PERMITIDO):
        raise CatalogoInvalido(
            f"fonte `{alvo.endereco}` fora do space `{ESPACO_PERMITIDO.rstrip('.')}`."
        )
    if ".." in alvo.endereco or alvo.endereco.endswith("."):
        raise CatalogoInvalido(f"fonte `{alvo.endereco}` tem caminho malformado.")


class MotorDremio:
    """Implementa o contrato de `motores/base.py` para o Dremio."""

    nome = NOME

    def __init__(self, cliente: ClienteDremio) -> None:
        self.cliente = cliente

    def dados(self, conjunto: Conjunto, consulta: Consulta) -> pa.Table:
        return self.cliente.consultar(sql.dados(conjunto, consulta))

    def total(self, conjunto: Conjunto, consulta: Consulta) -> int | None:
        return primeiro_escalar(self.cliente.consultar(sql.total(conjunto, consulta)))

    def resumo(self, conjunto: Conjunto, pedido: Resumo) -> pa.Table:
        return self.cliente.consultar(sql.resumo(conjunto, pedido))

    def verificar(self) -> None:
        self.cliente.consultar("SELECT 1")


def construir(config: Configuracao) -> MotorDremio:
    return MotorDremio(
        ClienteDremio(
            endpoint=config.dremio_endpoint,
            endpoint_flight=config.dremio_flight,
            usuario=config.dremio_usuario,
            senha=config.dremio_senha,
            tempo_limite=config.consulta_tempo_limite,
        )
    )

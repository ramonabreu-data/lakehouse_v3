"""Fixtures da suite. Nada aqui toca o Dremio, o Redis ou a rede.

A API e montada com um **motor falso** no lugar do Dremio. Isso testa duas
coisas de uma vez: o comportamento HTTP, e o fato de a camada de rotas nao
saber de onde o dado vem — se soubesse, o motor falso nao funcionaria.

Os testes de rota verificam o PEDIDO que chegou ao motor (colunas, filtros,
paginacao), nao o SQL. SQL e assunto do motor Dremio, testado em
`test_sql_dremio.py`.
"""

from __future__ import annotations

import datetime as dt
import sys
from pathlib import Path

import pyarrow as pa
import pytest
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

CHAVE_VALIDA = "chave-de-teste-com-tamanho-suficiente"
SEGREDO_JWT = "segredo-de-teste-com-tamanho-suficiente-para-hs256"


class MotorFalso:
    """Cumpre o contrato de `motores/base.py` guardando o que lhe pediram."""

    nome = "falso"

    def __init__(self) -> None:
        self.pedidos: list[tuple[str, object, object]] = []
        self.erro: Exception | None = None
        self.tabela = pa.table(
            {
                "municipio": pa.array(["Fortaleza", "Sobral"]),
                "cod_ibge": pa.array([2304400, 2312908], pa.int32()),
                "pontos": pa.array([87.5, 64.0]),
                "tem_selo": pa.array([True, False]),
                "primeira_visita": pa.array(
                    [dt.date(2025, 3, 1), dt.date(2025, 7, 14)], pa.date64()
                ),
            }
        )

    def _registrar(self, operacao, conjunto, pedido):
        self.pedidos.append((operacao, conjunto, pedido))
        if self.erro is not None:
            raise self.erro

    def dados(self, conjunto, consulta) -> pa.Table:
        self._registrar("dados", conjunto, consulta)
        return self.tabela

    def total(self, conjunto, consulta) -> int:
        self._registrar("total", conjunto, consulta)
        return self.tabela.num_rows

    def resumo(self, conjunto, pedido) -> pa.Table:
        self._registrar("resumo", conjunto, pedido)
        return self.tabela

    def verificar(self) -> None:
        return None

    # -- ajudas de leitura nos testes ---------------------------------------

    @property
    def ultimo(self):
        return self.pedidos[-1][2]

    @property
    def operacoes(self) -> list[str]:
        return [p[0] for p in self.pedidos]

    def filtro(self, nome: str):
        return next((f for f in self.ultimo.filtros if f.campo.nome == nome), None)


@pytest.fixture
def ambiente(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("API_AUTH_ATIVA", "true")
    monkeypatch.setenv("API_CHAVES", f"app-teste:{CHAVE_VALIDA}")
    monkeypatch.setenv("JWT_SECRET", SEGREDO_JWT)
    monkeypatch.setenv("API_CORS_ORIGENS", "https://app.exemplo.gov.br")
    monkeypatch.setenv("API_LIMITE_POR_MINUTO", "0")
    monkeypatch.setenv("DREMIO_USERNAME", "conta-servico")
    monkeypatch.setenv("DREMIO_PASSWORD", "senha")


@pytest.fixture
def motor() -> MotorFalso:
    return MotorFalso()


def montar(motor: MotorFalso) -> TestClient:
    """Aplicacao com o motor falso no lugar de todos os motores reais."""
    from app.principal import criar_app

    aplicacao = criar_app()
    for nome in list(aplicacao.state.motores):
        aplicacao.state.motores[nome] = motor
    return TestClient(aplicacao)


@pytest.fixture
def cliente(ambiente: None, motor: MotorFalso) -> TestClient:
    return montar(motor)


@pytest.fixture
def cabecalho() -> dict[str, str]:
    return {"X-API-Key": CHAVE_VALIDA}

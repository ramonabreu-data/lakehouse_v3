"""Orquestracao: valida -> escolhe o motor -> consulta -> cacheia.

O servico e a unica peca que conhece o catalogo E os motores; por isso e aqui
que se testa a escolha da fonte, o cache e a traducao de falha da origem.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from app import catalogo
from app.nucleo import ErroDeValidacao, FonteIndisponivel
from app.servicos import Servico
from app.servicos.cache import Cache
from tests.conftest import MotorFalso


class RedisFalso:
    def __init__(self):
        self.dados: dict[str, str] = {}

    def get(self, chave):
        return self.dados.get(chave)

    def setex(self, chave, ttl, valor):
        self.dados[chave] = valor


@pytest.fixture
def conjunto():
    return catalogo.obter("acoes-secretario")


@pytest.fixture
def motor() -> MotorFalso:
    return MotorFalso()


def servico(motor, cache=None) -> Servico:
    return Servico({"dremio": motor}, cache or Cache(None, ttl=0))


# --- escolha do motor ------------------------------------------------------

def test_usa_o_motor_declarado_na_fonte_do_conjunto(conjunto, motor):
    outro = MotorFalso()
    Servico({"dremio": motor, "outro": outro}, Cache(None, 0)).dados(conjunto, {})
    assert motor.pedidos and not outro.pedidos


def test_motor_ausente_vira_fonte_indisponivel(conjunto):
    with pytest.raises(FonteIndisponivel):
        Servico({}, Cache(None, 0)).dados(conjunto, {})


# --- corpo da resposta -----------------------------------------------------

def test_resposta_descreve_origem_e_paginacao(conjunto, motor):
    corpo = servico(motor).dados(conjunto, {"limite": ["2"]})
    assert corpo["conjunto"] == conjunto.slug
    assert corpo["fonte"] == conjunto.fonte.endereco
    assert corpo["motor"] == "dremio"
    assert corpo["paginacao"]["retornados"] == 2
    assert corpo["paginacao"]["total"] is None      # so com incluir_total


def test_total_so_e_pedido_quando_solicitado(conjunto, motor):
    servico(motor).dados(conjunto, {})
    assert motor.operacoes == ["dados"]
    servico(motor).dados(conjunto, {"incluir_total": ["true"]})
    assert motor.operacoes[-2:] == ["dados", "total"]


def test_pedido_invalido_nem_chega_ao_motor(conjunto, motor):
    with pytest.raises(ErroDeValidacao):
        servico(motor).dados(conjunto, {"populacao": ["muitas"]})
    assert motor.pedidos == []


# --- falha da origem -------------------------------------------------------

def test_falha_do_motor_vira_fonte_indisponivel(conjunto, motor):
    motor.erro = RuntimeError("Flight unauthenticated: senha=segredo")
    with pytest.raises(FonteIndisponivel) as capturado:
        servico(motor).dados(conjunto, {})
    # A mensagem original nao viaja junto: fica so no log.
    assert "senha" not in str(capturado.value)


# --- cache -----------------------------------------------------------------

def test_segunda_chamada_igual_nao_consulta_a_fonte(conjunto, motor):
    cache = Cache(RedisFalso(), ttl=60)
    alvo = servico(motor, cache)
    primeiro = alvo.dados(conjunto, {"municipio": ["Parnaiba"]})
    segundo = alvo.dados(conjunto, {"municipio": ["Parnaiba"]})
    assert primeiro == segundo
    assert motor.operacoes == ["dados"]


def test_parametros_diferentes_nao_compartilham_cache(conjunto, motor):
    alvo = servico(motor, Cache(RedisFalso(), ttl=60))
    alvo.dados(conjunto, {"municipio": ["Parnaiba"]})
    alvo.dados(conjunto, {"municipio": ["Teresina"]})
    assert motor.operacoes == ["dados", "dados"]


def test_conjuntos_diferentes_nao_compartilham_cache(motor):
    alvo = servico(motor, Cache(RedisFalso(), ttl=60))
    alvo.dados(catalogo.obter("acoes-secretario"), {})
    alvo.dados(catalogo.obter("municipios-acoes"), {})
    assert motor.operacoes == ["dados", "dados"]


def test_dados_e_resumo_nao_compartilham_cache(conjunto, motor):
    alvo = servico(motor, Cache(RedisFalso(), ttl=60))
    alvo.dados(conjunto, {"municipio": ["Parnaiba"]})
    alvo.resumo(conjunto, {"agrupar_por": ["municipio"]})
    assert alvo.dados(conjunto, {"municipio": ["Parnaiba"]})["conjunto"] == conjunto.slug
    assert motor.operacoes == ["dados", "resumo"]


def test_carga_nova_invalida_o_cache(conjunto, motor, monkeypatch):
    # A chave carrega o carimbo da ultima carga: quando o refinamento publica
    # dado novo, tudo o que estava guardado deixa de valer na hora.
    from app.servicos import estado

    cache = Cache(RedisFalso(), ttl=60)
    alvo = servico(motor, cache)
    monkeypatch.setattr(estado, "versao_do_dado", lambda: "2026-08-19T08:00:00")
    alvo.dados(conjunto, {})
    monkeypatch.setattr(estado, "versao_do_dado", lambda: "2026-08-20T07:00:00")
    alvo.dados(conjunto, {})
    assert motor.operacoes == ["dados", "dados"]


def test_verificar_passa_por_todos_os_motores():
    class Motor(MotorFalso):
        def __init__(self):
            super().__init__()
            self.verificado = False

        def verificar(self):
            self.verificado = True

    a, b = Motor(), Motor()
    Servico({"a": a, "b": b}, Cache(None, 0)).verificar()
    assert a.verificado and b.verificado

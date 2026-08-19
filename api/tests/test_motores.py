"""Registro de motores — o ponto de extensao para outras fontes de dados.

O teste que importa aqui e o ultimo: um motor inventado, registrado na hora,
serve um conjunto de ponta a ponta. Se isso passa, acrescentar Postgres, Mongo
ou uma API externa amanha e escrever um pacote em `app/motores/` — nao mexer em
rota, validacao ou catalogo.
"""

from __future__ import annotations

import pyarrow as pa
import pytest

from app import motores
from app.motores import dremio
from app.nucleo import CatalogoInvalido, Fonte


# --- registro --------------------------------------------------------------

def test_dremio_esta_registrado():
    assert "dremio" in motores.NOMES
    assert motores.REGISTRO["dremio"].NOME == "dremio"


def test_fonte_com_motor_inexistente_e_recusada():
    with pytest.raises(CatalogoInvalido, match="nao registrado"):
        motores.conferir_fonte(Fonte("mongodb", "qualquer.coisa"))


def test_cada_motor_expoe_o_contrato_do_registro():
    for modulo in motores.MODULOS:
        assert isinstance(modulo.NOME, str) and modulo.NOME
        assert callable(modulo.conferir_fonte)
        assert callable(modulo.construir)


# --- o motor Dremio valida os proprios enderecos ---------------------------

def test_dremio_so_aceita_endereco_no_space_refinamento():
    dremio.conferir_fonte(dremio.fonte("refinamento.espaco.view"))
    for invalido in ("entrada.bruta.tabela", "armazem.x.y", "postgres.public.usuarios"):
        with pytest.raises(CatalogoInvalido, match="refinamento"):
            dremio.conferir_fonte(dremio.fonte(invalido))


def test_dremio_recusa_caminho_malformado():
    for invalido in ("refinamento..view", "refinamento.espaco."):
        with pytest.raises(CatalogoInvalido, match="malformado"):
            dremio.conferir_fonte(dremio.fonte(invalido))


def test_atalho_fonte_marca_o_motor():
    assert dremio.fonte("refinamento.a.b") == Fonte("dremio", "refinamento.a.b")


# --- o motor Dremio traduz o pedido em SQL e delega ao cliente --------------

class ClienteFalso:
    def __init__(self):
        self.comandos: list[str] = []

    def consultar(self, comando: str) -> pa.Table:
        self.comandos.append(comando)
        return pa.table({"total": pa.array([7], pa.int64())})


def test_motor_dremio_manda_o_sql_ao_cliente():
    from app import catalogo
    from app.nucleo import analisar_parametros

    cliente = ClienteFalso()
    motor = dremio.MotorDremio(cliente)
    conjunto = catalogo.obter("acoes-secretario")
    consulta = analisar_parametros(conjunto, {"municipio": ["Parnaiba"], "limite": ["5"]})

    motor.dados(conjunto, consulta)
    assert """"municipio" = 'Parnaiba'""" in cliente.comandos[-1]

    assert motor.total(conjunto, consulta) == 7
    assert cliente.comandos[-1].startswith("SELECT COUNT(*)")

    motor.verificar()
    assert cliente.comandos[-1] == "SELECT 1"


# --- extensao: uma fonte que nao e o Dremio --------------------------------

def test_um_motor_novo_serve_um_conjunto_de_ponta_a_ponta(monkeypatch):
    """Simula a chegada de outra fonte de dados, sem tocar em arquivo nenhum."""
    from app import catalogo
    from app.nucleo import Campo, Conjunto
    from app.servicos import Servico
    from app.servicos.cache import Cache

    class ModuloFalso:
        NOME = "planilha"

        @staticmethod
        def conferir_fonte(alvo: Fonte) -> None:
            if not alvo.endereco.endswith(".csv"):
                raise CatalogoInvalido("endereco de planilha precisa terminar em .csv")

        @staticmethod
        def construir(config):
            return MotorPlanilha()

    class MotorPlanilha:
        nome = "planilha"

        def dados(self, conjunto, consulta):
            return pa.table({"nome": pa.array(["linha da planilha"])})

        def total(self, conjunto, consulta):
            return 1

        def resumo(self, conjunto, pedido):
            return pa.table({"nome": pa.array(["grupo"]), "registros": pa.array([1])})

        def verificar(self):
            return None

    monkeypatch.setitem(motores.REGISTRO, "planilha", ModuloFalso)

    conjunto = Conjunto(
        slug="planilha-de-exemplo",
        area=catalogo.AREAS[0],
        fonte=Fonte("planilha", "compartilhado/lista.csv"),
        titulo="Planilha de exemplo",
        descricao="Conjunto que nao vem do Dremio.",
        campos=(Campo("nome", "texto"),),
    )

    # 1. o catalogo aceita a fonte nova, validada pelo proprio motor...
    catalogo.conferir((conjunto,))
    with pytest.raises(CatalogoInvalido, match="csv"):
        catalogo.conferir((Conjunto(**{**conjunto.__dict__, "fonte": Fonte("planilha", "x.txt")}),))

    # 2. ...e o servico entrega o pedido ao motor certo, sem saber o que ele e.
    servico = Servico({"planilha": MotorPlanilha()}, Cache(None, ttl=0))
    corpo = servico.dados(conjunto, {"nome": ["algo"]})
    assert corpo["motor"] == "planilha"
    assert corpo["dados"] == [{"nome": "linha da planilha"}]

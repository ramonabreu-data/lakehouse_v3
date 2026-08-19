"""Cada conjunto tem de aparecer no /docs com uma descricao do que entrega.

Sem isto, quem integra ve dez secoes chamadas "conjuntos" e nao sabe qual pedir.
"""

from __future__ import annotations

import pytest

from app import catalogo


@pytest.fixture
def esquema(cliente):
    return cliente.get("/openapi.json").json()


def test_cada_conjunto_publica_suas_tres_rotas(esquema):
    for slug in catalogo.CATALOGO:
        base = f"/v1/conjuntos/{slug}"
        assert base in esquema["paths"], f"faltou a rota de campos de {slug}"
        assert f"{base}/dados" in esquema["paths"]
        assert f"{base}/resumo" in esquema["paths"]


def test_cada_conjunto_e_uma_secao_com_descricao(esquema):
    secoes = {tag["name"]: tag["description"] for tag in esquema["tags"]}
    for conjunto in catalogo.CONJUNTOS:
        assert conjunto.titulo in secoes, f"conjunto `{conjunto.slug}` sem secao no /docs"
        descricao = secoes[conjunto.titulo]
        assert conjunto.area.titulo in descricao      # de que area e
        assert conjunto.descricao in descricao        # o que entrega


def test_a_secao_de_descoberta_vem_primeiro(esquema):
    assert esquema["tags"][0]["name"] == "Descoberta e acesso"
    assert esquema["tags"][0]["description"]


def test_rota_de_dados_documenta_os_filtros_do_proprio_conjunto(esquema):
    conjunto = catalogo.obter("acoes-secretario")
    descricao = esquema["paths"][f"/v1/conjuntos/{conjunto.slug}/dados"]["get"]["description"]
    assert conjunto.fonte.endereco in descricao
    assert f"motor `{conjunto.fonte.motor}`" in descricao
    for campo in conjunto.campos:
        assert f"`{campo.nome}`" in descricao
    # Exemplos usam campo real do conjunto, nao placeholder generico.
    assert "?municipio=" in descricao and "?data__gte=" in descricao


def test_rota_de_resumo_lista_agrupaveis_e_metricas(esquema):
    conjunto = catalogo.obter("selo-ambiental-2026")
    descricao = esquema["paths"][f"/v1/conjuntos/{conjunto.slug}/resumo"]["get"]["description"]
    assert "`territorio_desenvolvimento`" in descricao
    assert "`pontos`" in descricao
    assert "`media`" in descricao


def test_toda_rota_tem_resumo_curto(esquema):
    for caminho, metodos in esquema["paths"].items():
        for metodo, rota in metodos.items():
            assert rota.get("summary"), f"{metodo.upper()} {caminho} sem summary"


def test_operacoes_tem_identificadores_unicos(esquema):
    ids = [r["operationId"] for m in esquema["paths"].values() for r in m.values()]
    assert len(ids) == len(set(ids))

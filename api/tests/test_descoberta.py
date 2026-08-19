"""Rotas por onde uma integracao comeca: identidade, areas e catalogo."""

from __future__ import annotations

from tests.conftest import CHAVE_VALIDA


def test_identidade_confirma_a_chave_de_aplicacao(cliente, cabecalho):
    # E o teste mais barato que quem integra tem para saber se a credencial vale.
    corpo = cliente.get("/v1/identidade", headers=cabecalho).json()
    assert corpo == {"tipo": "aplicacao", "nome": "app-teste"}


def test_identidade_com_credencial_invalida_responde_401(cliente):
    assert cliente.get("/v1/identidade", headers={"X-API-Key": "errada"}).status_code == 401


def test_identidade_reconhece_o_usuario_do_supabase(cliente, ambiente):
    import time

    import jwt

    from tests.conftest import SEGREDO_JWT

    token = jwt.encode(
        {"sub": "1", "email": "pessoa@exemplo.gov.br", "aud": "", "exp": int(time.time()) + 300},
        SEGREDO_JWT,
        algorithm="HS256",
    )
    corpo = cliente.get("/v1/identidade", headers={"Authorization": f"Bearer {token}"}).json()
    assert corpo == {"tipo": "usuario", "nome": "pessoa@exemplo.gov.br"}


def test_areas_listam_seus_conjuntos(cliente, cabecalho):
    from app import catalogo

    areas = cliente.get("/v1/areas", headers=cabecalho).json()["areas"]
    assert [a["slug"] for a in areas] == [a.slug for a in catalogo.AREAS]
    for area in areas:
        assert area["titulo"] and area["descricao"]
        assert area["conjuntos"]


def test_catalogo_traz_o_caminho_de_cada_conjunto(cliente, cabecalho):
    conjuntos = cliente.get("/v1/conjuntos", headers=cabecalho).json()["conjuntos"]
    exemplo = next(c for c in conjuntos if c["slug"] == "acoes-secretario")
    assert exemplo["dados"] == "/v1/conjuntos/acoes-secretario/dados"
    assert exemplo["resumo"] == "/v1/conjuntos/acoes-secretario/resumo"
    assert exemplo["campos"] == "/v1/conjuntos/acoes-secretario"
    assert exemplo["area"] == "chefia-de-gabinete"


def test_limite_conta_uma_vez_por_requisicao(monkeypatch, motor):
    # A dependencia de acesso aparece no roteador E como parametro de /identidade.
    # Se o FastAPI a executasse duas vezes, o limite cairia pela metade.
    monkeypatch.setenv("API_AUTH_ATIVA", "true")
    monkeypatch.setenv("API_CHAVES", f"app-teste:{CHAVE_VALIDA}")
    monkeypatch.setenv("API_LIMITE_POR_MINUTO", "3")
    from tests.conftest import montar

    cliente = montar(motor)
    cabecalho = {"X-API-Key": CHAVE_VALIDA}
    codigos = [cliente.get("/v1/identidade", headers=cabecalho).status_code for _ in range(4)]
    assert codigos == [200, 200, 200, 429]

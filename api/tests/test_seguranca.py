"""Autenticacao: chave de API (app servidor-a-servidor) e JWT do Supabase
(app com usuario logado). Sao os dois modos que a stack ja consegue emitir.
"""

from __future__ import annotations

import time

import jwt
import pytest

from app import seguranca
from tests.conftest import CHAVE_VALIDA, SEGREDO_JWT


def token(**claims) -> str:
    base = {
        "sub": "3f1c9a6e-0000-4000-8000-000000000001",
        "email": "pessoa@exemplo.gov.br",
        "aud": "authenticated",
        "role": "authenticated",
        "exp": int(time.time()) + 300,
    }
    base.update(claims)
    return jwt.encode(base, SEGREDO_JWT, algorithm="HS256")


# --- chaves de API ---------------------------------------------------------

def test_chaves_sao_lidas_do_ambiente(ambiente):
    assert seguranca.chaves_configuradas() == {CHAVE_VALIDA: "app-teste"}


def test_chave_valida_identifica_a_aplicacao(ambiente):
    identidade = seguranca.verificar_chave(CHAVE_VALIDA)
    assert identidade is not None and identidade.nome == "app-teste"
    assert identidade.tipo == "aplicacao"


def test_chave_errada_ou_ausente_nao_identifica(ambiente):
    assert seguranca.verificar_chave("chave-errada") is None
    assert seguranca.verificar_chave(None) is None
    assert seguranca.verificar_chave("") is None


def test_chave_valida_com_prefixo_nao_passa(ambiente):
    # Comparacao e por igualdade total, nao por prefixo/startswith.
    assert seguranca.verificar_chave(CHAVE_VALIDA[:-1]) is None
    assert seguranca.verificar_chave(CHAVE_VALIDA + "x") is None


# --- JWT do Supabase -------------------------------------------------------

def test_jwt_valido_identifica_o_usuario(ambiente):
    identidade = seguranca.verificar_jwt(token())
    assert identidade is not None
    assert identidade.tipo == "usuario"
    assert identidade.nome == "pessoa@exemplo.gov.br"


def test_jwt_expirado_e_recusado(ambiente):
    assert seguranca.verificar_jwt(token(exp=int(time.time()) - 10)) is None


def test_jwt_assinado_com_outro_segredo_e_recusado(ambiente):
    forjado = jwt.encode({"sub": "x", "aud": "authenticated"}, "outro-segredo", algorithm="HS256")
    assert seguranca.verificar_jwt(forjado) is None


def test_jwt_sem_assinatura_e_recusado(ambiente):
    # Ataque classico: alg=none. A verificacao fixa HS256.
    nenhum = jwt.encode({"sub": "x", "aud": "authenticated"}, key="", algorithm="none")
    assert seguranca.verificar_jwt(nenhum) is None


def test_jwt_do_gotrue_desta_stack_e_aceito(ambiente):
    # O GoTrue configurado aqui NAO define GOTRUE_JWT_AUD, entao emite `aud`
    # e `role` vazios. Descoberto autenticando de verdade contra a stack: a
    # versao anterior exigia aud="authenticated" e recusava token legitimo.
    identidade = seguranca.verificar_jwt(token(aud="", role=""))
    assert identidade is not None and identidade.tipo == "usuario"


def test_publico_e_conferido_quando_configurado(ambiente, monkeypatch):
    # Numa instalacao com GOTRUE_JWT_AUD definido, basta apontar aqui.
    monkeypatch.setenv("API_JWT_PUBLICO", "authenticated")
    assert seguranca.verificar_jwt(token(aud="authenticated")) is not None
    assert seguranca.verificar_jwt(token(aud="outra-coisa")) is None
    assert seguranca.verificar_jwt(token(aud="")) is None


def test_jwt_sem_prazo_de_validade_e_recusado(ambiente):
    eterno = jwt.encode({"sub": "x", "aud": ""}, SEGREDO_JWT, algorithm="HS256")
    assert seguranca.verificar_jwt(eterno) is None


def test_texto_qualquer_nao_derruba_a_verificacao(ambiente):
    assert seguranca.verificar_jwt("nao-e-um-jwt") is None


# --- porta de entrada ------------------------------------------------------

def test_sem_credencial_a_api_responde_401(cliente):
    resposta = cliente.get("/v1/conjuntos")
    assert resposta.status_code == 401


def test_chave_valida_no_cabecalho_libera(cliente, cabecalho):
    assert cliente.get("/v1/conjuntos", headers=cabecalho).status_code == 200


def test_bearer_com_jwt_valido_libera(cliente, ambiente):
    resposta = cliente.get("/v1/conjuntos", headers={"Authorization": f"Bearer {token()}"})
    assert resposta.status_code == 200


def test_bearer_com_chave_de_api_tambem_libera(cliente):
    # Conveniencia: muito cliente HTTP so sabe mandar Authorization.
    resposta = cliente.get("/v1/conjuntos", headers={"Authorization": f"Bearer {CHAVE_VALIDA}"})
    assert resposta.status_code == 200


def test_credencial_invalida_responde_401_sem_vazar_detalhe(cliente):
    resposta = cliente.get("/v1/conjuntos", headers={"X-API-Key": "errada"})
    assert resposta.status_code == 401
    assert "errada" not in resposta.text


def test_saude_nao_exige_credencial(cliente):
    assert cliente.get("/saude").status_code == 200


def test_auth_desligada_libera_tudo(monkeypatch, motor):
    # Modo dev, espelhando o AUTH_ENABLED do painel.
    monkeypatch.setenv("API_AUTH_ATIVA", "false")
    monkeypatch.setenv("API_LIMITE_POR_MINUTO", "0")
    from tests.conftest import montar

    assert montar(motor).get("/v1/conjuntos").status_code == 200


def test_auth_ativa_sem_nenhuma_credencial_configurada_e_erro_de_partida(monkeypatch):
    # Falha no boot, nao em silencio: sem chaves nem JWT_SECRET a API ficaria
    # aberta ou inutil, e as duas coisas sao piores que nao subir.
    monkeypatch.setenv("API_AUTH_ATIVA", "true")
    monkeypatch.delenv("API_CHAVES", raising=False)
    monkeypatch.delenv("JWT_SECRET", raising=False)
    from app.principal import criar_app

    with pytest.raises(RuntimeError):
        criar_app()

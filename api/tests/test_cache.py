"""Cache das respostas. A chave carrega a versao do dado, entao o refinamento
publicar dado novo invalida tudo sem esperar o TTL — mesma logica do painel.
"""

from __future__ import annotations

import pytest

from app.servicos.cache import Cache


class RedisFalso:
    def __init__(self) -> None:
        self.dados: dict[str, str] = {}
        self.quebrado = False

    def get(self, chave):
        if self.quebrado:
            raise ConnectionError("redis fora do ar")
        return self.dados.get(chave)

    def setex(self, chave, ttl, valor):
        if self.quebrado:
            raise ConnectionError("redis fora do ar")
        self.dados[chave] = valor


@pytest.fixture
def redis() -> RedisFalso:
    return RedisFalso()


def test_guarda_e_recupera(redis):
    cache = Cache(redis, ttl=60)
    chave = cache.chave("selos", "SELECT 1", "v1")
    assert cache.obter(chave) is None
    cache.guardar(chave, {"dados": [1, 2]})
    assert cache.obter(chave) == {"dados": [1, 2]}


def test_versao_do_dado_diferente_gera_chave_diferente(redis):
    cache = Cache(redis, ttl=60)
    assert cache.chave("selos", "SELECT 1", "v1") != cache.chave("selos", "SELECT 1", "v2")


def test_sql_diferente_gera_chave_diferente(redis):
    cache = Cache(redis, ttl=60)
    assert cache.chave("selos", "SELECT 1", "v1") != cache.chave("selos", "SELECT 2", "v1")


def test_redis_fora_do_ar_nao_derruba_a_requisicao(redis):
    # Cache e otimizacao, nao dependencia: sem Redis a API responde mais devagar.
    cache = Cache(redis, ttl=60)
    redis.quebrado = True
    chave = cache.chave("selos", "SELECT 1", "v1")
    assert cache.obter(chave) is None
    cache.guardar(chave, {"dados": []})


def test_sem_redis_configurado_o_cache_e_um_no_op():
    cache = Cache(None, ttl=60)
    chave = cache.chave("selos", "SELECT 1", "v1")
    cache.guardar(chave, {"dados": [1]})
    assert cache.obter(chave) is None


def test_ttl_zero_desliga_a_gravacao(redis):
    cache = Cache(redis, ttl=0)
    chave = cache.chave("selos", "SELECT 1", "v1")
    cache.guardar(chave, {"dados": [1]})
    assert redis.dados == {}

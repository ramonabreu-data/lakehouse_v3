"""Montagem da aplicacao — o unico lugar que conhece todas as camadas.

Aqui as pecas sao construidas e ligadas: configuracao -> motores -> cache ->
servico -> rotas. Nenhuma camada se instancia sozinha, entao trocar qualquer
uma (outro motor, outro cache) e mexer neste arquivo, e so nele.

Tudo acontece dentro de `criar_app()`, nada em tempo de import, para que o
processo leia o ambiente do compose na subida e a suite consiga montar variantes
— auth ligada, desligada, com limite — sem recarregar modulo.
"""

from __future__ import annotations

import logging
import os

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from app import configuracao, motores, seguranca, web
from app.servicos import Servico
from app.servicos.cache import Cache
from app.servicos.estado import versao_do_dado
from app.servicos.limite import Limitador

registrador = logging.getLogger(__name__)

DESCRICAO = """
API de leitura dos dados **refinados** do lakehouse (space `refinamento` do
Dremio). Serve qualquer aplicacao web: respostas JSON, CORS configuravel,
paginacao, filtros e agregacao pronta.

**Autenticacao** — uma das duas em toda chamada:

* `X-API-Key: <chave>` para aplicacao servidor-a-servidor;
* `Authorization: Bearer <jwt>` com o token do Supabase da propria stack.

Comece por `GET /v1/identidade` (confere a credencial) e `GET /v1/conjuntos`
(o que esta publicado).
"""


def _redis(url: str):
    """Cliente Redis, ou None se a stack nao expuser um.

    Sem Redis a API funciona: o cache vira no-op e o limite passa a contar na
    memoria do processo. E o modo em que a suite roda.
    """
    if not url:
        return None
    try:
        import redis

        return redis.Redis.from_url(url, decode_responses=True)
    except Exception:  # noqa: BLE001
        registrador.warning("Redis indisponivel em %s; seguindo sem cache.", url, exc_info=True)
        return None


def _conferir_credenciais() -> None:
    """Falha na subida em vez de subir uma API aberta ou impossivel de usar."""
    if not seguranca.auth_ativa():
        registrador.warning("API_AUTH_ATIVA=false: a API esta ABERTA. Use so em desenvolvimento.")
        return
    if not seguranca.chaves_configuradas() and not os.getenv("JWT_SECRET"):
        raise RuntimeError(
            "Autenticacao ativa e nenhuma credencial configurada: defina API_CHAVES "
            "e/ou JWT_SECRET no .env, ou API_AUTH_ATIVA=false em desenvolvimento."
        )


def criar_app() -> FastAPI:
    _conferir_credenciais()
    config = configuracao.carregar()

    aplicacao = FastAPI(
        title="API de dados refinados",
        description=DESCRICAO,
        version="1.0.0",
        docs_url="/docs",
        redoc_url=None,
        # persistAuthorization: quem esta integrando cola a chave uma vez no
        # botao "Authorize", e ela sobrevive ao F5 da pagina.
        swagger_ui_parameters={"persistAuthorization": True, "tryItOutEnabled": True},
        # Uma secao por conjunto, cada uma com a descricao do que entrega.
        openapi_tags=web.TAGS_OPENAPI,
    )

    cliente_redis = _redis(config.redis_url)
    aplicacao.state.config = config
    aplicacao.state.motores = motores.construir(config)
    aplicacao.state.limitador = Limitador(config.limite_por_minuto, cliente_redis)
    aplicacao.state.servico = Servico(
        aplicacao.state.motores, Cache(cliente_redis, ttl=config.cache_ttl)
    )

    # CORS: com origem coringa o navegador proibe credencial de cookie, e esta
    # API nao usa cookie nenhum — a credencial vai em cabecalho.
    aplicacao.add_middleware(
        CORSMiddleware,
        allow_origins=list(config.cors_origens),
        allow_credentials=not config.cors_liberado_para_todos,
        allow_methods=["GET", "OPTIONS"],
        allow_headers=["Authorization", "X-API-Key", "Content-Type"],
        max_age=600,
    )

    web.registrar_tratadores(aplicacao)

    @aplicacao.get("/saude", tags=["operacao"], summary="Vivacidade (nao toca as fontes)")
    def saude() -> dict:
        """Usada pelo healthcheck do compose: responde mesmo com a fonte fora."""
        return {"status": "ok", "versao_do_dado": versao_do_dado() or None}

    @aplicacao.get("/saude/pronto", tags=["operacao"], summary="Prontidao (consulta as fontes)")
    def pronto(request: Request):
        try:
            request.app.state.servico.verificar()
        except Exception:  # noqa: BLE001
            registrador.exception("Verificacao de prontidao falhou.")
            return JSONResponse(
                status_code=503,
                content={"erro": {"codigo": "fonte_indisponivel", "mensagem": "A fonte nao respondeu."}},
            )
        return {"status": "pronto"}

    aplicacao.include_router(web.roteador)
    return aplicacao


app = None  # preenchido pelo uvicorn via fabrica (`--factory app.principal:criar_app`)

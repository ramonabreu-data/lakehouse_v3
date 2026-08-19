"""Camada HTTP: rotas, autenticacao, erros e documentacao.

E a unica camada que conhece FastAPI. Ordem de registro importa: os caminhos
literais de cada conjunto entram ANTES do roteador de caminhos parametrizados,
senao `/conjuntos/{slug}` capturaria tudo e nenhum conjunto real seria
alcancado.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.web.acesso import exigir_acesso
from app.web.erros import registrar_tratadores
from app.web.rotas import conjuntos, descoberta

__all__ = ["TAGS_OPENAPI", "exigir_acesso", "registrar_tratadores", "roteador"]

roteador = APIRouter(prefix="/v1", dependencies=[Depends(exigir_acesso)])

roteador.include_router(descoberta.roteador)
for _roteador_do_conjunto in conjuntos.roteadores():
    roteador.include_router(_roteador_do_conjunto)
roteador.include_router(conjuntos.desconhecidos)

# Secoes do /docs, na ordem em que aparecem.
TAGS_OPENAPI: list[dict[str, str]] = [
    {"name": descoberta.TAG, "description": descoberta.DESCRICAO_DA_TAG},
    *conjuntos.secoes(),
]

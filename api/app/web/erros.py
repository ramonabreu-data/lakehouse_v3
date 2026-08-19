"""Traducao de erro em resposta HTTP.

Todo erro sai no mesmo formato:

    {"erro": {"codigo": "parametro_invalido", "mensagem": "..."}}

O `codigo` e estavel e serve para o cliente decidir o que fazer; a `mensagem` e
para quem esta integrando ler. Nenhum dos dois carrega SQL, credencial ou stack
trace — isso fica no log do servidor.

Os tratadores registrados aqui sao o que permite as rotas ficarem sem
`try/except`: elas chamam o servico, e a excecao de negocio (`ErroDeValidacao`,
`ConjuntoDesconhecido`, `FonteIndisponivel`) vira status code neste arquivo.
"""

from __future__ import annotations

import logging

from fastapi import FastAPI, HTTPException, Request
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as ErroHTTPStarlette

from app.nucleo import ConjuntoDesconhecido, ErroDeValidacao, FonteIndisponivel

registrador = logging.getLogger(__name__)

CODIGOS_PADRAO = {
    400: "requisicao_invalida",
    401: "nao_autenticado",
    404: "nao_encontrado",
    405: "metodo_nao_permitido",
    422: "parametro_invalido",
    429: "limite_excedido",
    500: "erro_interno",
    502: "fonte_indisponivel",
}


class ErroApi(HTTPException):
    def __init__(self, status: int, codigo: str, mensagem: str) -> None:
        super().__init__(status_code=status, detail=mensagem)
        self.codigo = codigo


def nao_autenticado() -> ErroApi:
    return ErroApi(401, "nao_autenticado", "Envie uma chave em X-API-Key ou um token em Authorization.")


def excedeu_o_limite(por_minuto: int) -> ErroApi:
    return ErroApi(429, "limite_excedido", f"Limite de {por_minuto} requisicoes por minuto atingido.")


def _resposta(status: int, codigo: str, mensagem: str, cabecalhos=None) -> JSONResponse:
    return JSONResponse(
        status_code=status,
        content={"erro": {"codigo": codigo, "mensagem": mensagem}},
        headers=cabecalhos,
    )


def registrar_tratadores(aplicacao: FastAPI) -> None:
    @aplicacao.exception_handler(ErroDeValidacao)
    def _pedido_invalido(request: Request, exc: ErroDeValidacao) -> JSONResponse:
        return _resposta(400, "parametro_invalido", str(exc))

    @aplicacao.exception_handler(ConjuntoDesconhecido)
    def _conjunto_desconhecido(request: Request, exc: ConjuntoDesconhecido) -> JSONResponse:
        slug = exc.args[0] if exc.args else "?"
        return _resposta(404, "conjunto_desconhecido", f"Nao existe conjunto publicado com o slug `{slug}`.")

    @aplicacao.exception_handler(FonteIndisponivel)
    def _fonte_indisponivel(request: Request, exc: FonteIndisponivel) -> JSONResponse:
        # A causa ja foi registrada com detalhe em `servicos/dados.py`.
        return _resposta(502, "fonte_indisponivel", "A origem do dado nao respondeu. Tente novamente.")

    @aplicacao.exception_handler(ErroHTTPStarlette)
    def _erro_http(request: Request, exc: ErroHTTPStarlette) -> JSONResponse:
        codigo = getattr(exc, "codigo", None) or CODIGOS_PADRAO.get(exc.status_code, "erro")
        return _resposta(exc.status_code, codigo, str(exc.detail), getattr(exc, "headers", None))

    @aplicacao.exception_handler(Exception)
    def _erro_inesperado(request: Request, exc: Exception) -> JSONResponse:
        registrador.exception("Erro nao tratado em %s", request.url.path)
        return _resposta(500, "erro_interno", "Erro interno na API.")

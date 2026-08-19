"""Nucleo — o que a API **e**, sem depender de nada de fora.

Nada aqui importa FastAPI, pyarrow, Redis ou driver de banco. Sao os tipos do
catalogo (Area, Conjunto, Campo, Fonte), o modelo de um pedido do cliente
(Consulta, Resumo, Filtro) e os erros de negocio.

A regra que sustenta o resto: **o nucleo entende a pergunta, nunca a resposta.**
Traduzir a pergunta para SQL (ou para o que a fonte falar) e trabalho de
`motores/`. E o que permite publicar amanha um conjunto que nao vem do Dremio
sem reescrever validacao nenhuma.
"""

from __future__ import annotations

from app.nucleo.erros import (
    CatalogoInvalido,
    ConjuntoDesconhecido,
    ErroDeValidacao,
    FonteIndisponivel,
)
from app.nucleo.pedido import (
    FUNCOES,
    LIMITE_MAXIMO,
    LIMITE_PADRAO,
    LIMITE_RESUMO,
    OPERADORES,
    Consulta,
    Filtro,
    Resumo,
    analisar_parametros,
    analisar_resumo,
)
from app.nucleo.tipos import NUMERICOS, TIPOS, Area, Campo, Conjunto, Fonte

__all__ = [
    "FUNCOES",
    "LIMITE_MAXIMO",
    "LIMITE_PADRAO",
    "LIMITE_RESUMO",
    "NUMERICOS",
    "OPERADORES",
    "TIPOS",
    "Area",
    "Campo",
    "CatalogoInvalido",
    "Conjunto",
    "ConjuntoDesconhecido",
    "Consulta",
    "ErroDeValidacao",
    "Filtro",
    "FonteIndisponivel",
    "Fonte",
    "Resumo",
    "analisar_parametros",
    "analisar_resumo",
]

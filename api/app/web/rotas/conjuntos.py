"""Fabrica das rotas de cada conjunto.

As rotas NAO sao escritas a mao: sao geradas a partir do catalogo, uma trinca
por conjunto (`campos`, `dados`, `resumo`). Acrescentar um Conjunto publica as
tres rotas, ja documentadas — venha ele do Dremio ou de qualquer motor futuro.

Os caminhos sao literais (`/v1/conjuntos/selo-ambiental-2026/dados`, e nao
`/v1/conjuntos/{slug}/dados`) por causa da documentacao: assim cada conjunto
vira uma secao propria no /docs, com a descricao do que ele e e a lista dos
filtros que aceita. A URL para o cliente e exatamente a mesma.

No fim entra um roteador com os caminhos parametrizados, fora do schema, so
para que slug inexistente responda `conjunto_desconhecido` em vez do 404 seco
do FastAPI.
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.catalogo import CONJUNTOS, Conjunto, obter
from app.web import documentacao


def _descrever(conjunto: Conjunto) -> dict:
    """Metadados do conjunto: e o que o cliente le para saber o que pode pedir."""
    return {
        "slug": conjunto.slug,
        "titulo": conjunto.titulo,
        "descricao": conjunto.descricao,
        "area": {"slug": conjunto.area.slug, "titulo": conjunto.area.titulo},
        "fonte": conjunto.fonte.endereco,
        "motor": conjunto.fonte.motor,
        "ordem_padrao": list(conjunto.ordem_padrao),
        "campos": [
            {
                "nome": campo.nome,
                "tipo": campo.tipo,
                "descricao": campo.descricao,
                "filtravel": campo.filtravel,
                "agrupavel": campo.agrupavel,
            }
            for campo in conjunto.campos
        ],
    }


def _parametros(request: Request) -> dict[str, list[str]]:
    """Query string em multimapa: `?a=1&a=2` vira {'a': ['1','2']}."""
    agrupados: dict[str, list[str]] = {}
    for chave, valor in request.query_params.multi_items():
        agrupados.setdefault(chave, []).append(valor)
    return agrupados


def rotas_do_conjunto(conjunto: Conjunto) -> APIRouter:
    """As tres rotas de um conjunto, ja com a descricao dele na documentacao."""
    roteador = APIRouter(tags=[conjunto.titulo])
    base = f"/conjuntos/{conjunto.slug}"
    ident = conjunto.slug.replace("-", "_")

    @roteador.get(
        base,
        summary="Campos, tipos e filtros aceitos",
        description=documentacao.campos(conjunto),
        operation_id=f"campos_{ident}",
    )
    def campos() -> dict:
        return _descrever(conjunto)

    @roteador.get(
        f"{base}/dados",
        summary="Registros, com filtro e paginacao",
        description=documentacao.dados(conjunto),
        operation_id=f"dados_{ident}",
    )
    def dados(request: Request) -> dict:
        return request.app.state.servico.dados(conjunto, _parametros(request))

    @roteador.get(
        f"{base}/resumo",
        summary="Agregacao calculada na fonte",
        description=documentacao.resumo(conjunto),
        operation_id=f"resumo_{ident}",
    )
    def resumo(request: Request) -> dict:
        return request.app.state.servico.resumo(conjunto, _parametros(request))

    return roteador


def roteadores() -> list[APIRouter]:
    return [rotas_do_conjunto(conjunto) for conjunto in CONJUNTOS]


def secoes() -> list[dict[str, str]]:
    return [documentacao.secao(conjunto) for conjunto in CONJUNTOS]


# Registrado DEPOIS dos literais: so cai aqui slug que nao existe. `obter`
# levanta ConjuntoDesconhecido, que o tratador de `web/erros.py` vira 404.
desconhecidos = APIRouter(include_in_schema=False)


@desconhecidos.get("/conjuntos/{slug}")
@desconhecidos.get("/conjuntos/{slug}/dados")
@desconhecidos.get("/conjuntos/{slug}/resumo")
def conjunto_desconhecido(slug: str) -> dict:
    return _descrever(obter(slug))

"""Descoberta e acesso — por onde uma integracao comeca.

Tres perguntas que todo cliente novo faz, nesta ordem: minha credencial vale?
que areas existem? que conjuntos posso consultar?
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app import catalogo, seguranca
from app.web.acesso import exigir_acesso

TAG = "Descoberta e acesso"

DESCRICAO_DA_TAG = (
    "Ponto de partida da integracao: confira se a credencial esta valida, veja as areas "
    "publicadas e liste os conjuntos disponiveis com o caminho de cada um."
)

roteador = APIRouter(tags=[TAG])


@roteador.get("/identidade", summary="Confere a credencial e diz quem voce e")
def identidade(identidade: seguranca.Identidade = Depends(exigir_acesso)) -> dict:
    """Teste rapido de credencial.

    Responde **200** com a identidade reconhecida se a chave ou o token valem, e
    **401** se nao valem. E o jeito mais barato de descobrir se o problema esta na
    credencial ou na consulta.

    `tipo` diz por onde voce entrou: `aplicacao` (chave de API) ou `usuario`
    (token do Supabase).
    """
    return {"tipo": identidade.tipo, "nome": identidade.nome}


@roteador.get("/areas", summary="Areas que publicam conjuntos")
def listar_areas() -> dict:
    """As areas (setores) donas dos conjuntos, na mesma divisao do painel."""
    return {
        "areas": [
            {
                "slug": area.slug,
                "titulo": area.titulo,
                "descricao": area.descricao,
                "conjuntos": [c.slug for c in catalogo.conjuntos_da_area(area.slug)],
            }
            for area in catalogo.AREAS
        ]
    }


@roteador.get("/conjuntos", summary="Lista os conjuntos publicados")
def listar_conjuntos() -> dict:
    """Tudo que esta publicado, com o caminho de dados e de resumo de cada um."""
    return {
        "conjuntos": [
            {
                "slug": conjunto.slug,
                "titulo": conjunto.titulo,
                "descricao": conjunto.descricao,
                "area": conjunto.area.slug,
                "campos": f"/v1/conjuntos/{conjunto.slug}",
                "dados": f"/v1/conjuntos/{conjunto.slug}/dados",
                "resumo": f"/v1/conjuntos/{conjunto.slug}/resumo",
            }
            for conjunto in catalogo.CONJUNTOS
        ]
    }

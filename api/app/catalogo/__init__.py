"""Catalogo — **o que** e publicado. So declaracao, nenhum comportamento.

Cada `Conjunto` amarra um slug estavel a uma `Fonte` (motor + endereco) e diz
quais campos podem sair, quais aceitam filtro e quais servem de agrupamento.
Fora daqui nada e alcancavel.

E de proposito que o endereco da origem nao apareca na URL: o slug e o contrato
publico, e a view por tras pode ser renomeada, reparticionada — ou trocada por
outra fonte inteira — sem quebrar ninguem.

O catalogo e conferido no import (`conferir`): slug repetido, campo com tipo
desconhecido, motor inexistente ou `ordem_padrao` apontando para coluna que nao
existe derrubam a subida, em vez de virarem erro na primeira consulta do
cliente.
"""

from __future__ import annotations

import re

from app import motores
from app.catalogo.areas import AREAS, CONJUNTOS
from app.nucleo import TIPOS, Area, Campo, CatalogoInvalido, Conjunto, ConjuntoDesconhecido

__all__ = [
    "AREAS",
    "CATALOGO",
    "CONJUNTOS",
    "Area",
    "Campo",
    "Conjunto",
    "ConjuntoDesconhecido",
    "conferir",
    "conjuntos_da_area",
    "obter",
]

SLUG_VALIDO = re.compile(r"^[a-z0-9]+(-[a-z0-9]+)*$")


def conferir(conjuntos: tuple[Conjunto, ...], areas: tuple[Area, ...] = AREAS) -> None:
    """Recusa catalogo malformado. Chamado no import e pelos testes."""
    vistos: set[str] = set()
    registradas = {area.slug for area in areas}
    for conjunto in conjuntos:
        onde = f"conjunto `{conjunto.slug}`"
        if not SLUG_VALIDO.match(conjunto.slug):
            raise CatalogoInvalido(f"{onde}: slug deve ser minusculo, separado por hifen.")
        if conjunto.slug in vistos:
            raise CatalogoInvalido(f"{onde}: slug repetido.")
        vistos.add(conjunto.slug)

        if conjunto.area.slug not in registradas:
            raise CatalogoInvalido(f"{onde}: area `{conjunto.area.slug}` nao esta em AREAS.")
        # Cada motor valida o proprio formato de endereco.
        try:
            motores.conferir_fonte(conjunto.fonte)
        except CatalogoInvalido as exc:
            raise CatalogoInvalido(f"{onde}: {exc}") from exc
        if not conjunto.titulo or not conjunto.descricao:
            raise CatalogoInvalido(f"{onde}: falta titulo ou descricao.")
        if not conjunto.campos:
            raise CatalogoInvalido(f"{onde}: nenhum campo declarado.")

        nomes = [campo.nome for campo in conjunto.campos]
        if len(nomes) != len(set(nomes)):
            raise CatalogoInvalido(f"{onde}: campo repetido.")
        for campo in conjunto.campos:
            if campo.tipo not in TIPOS:
                raise CatalogoInvalido(f"{onde}: campo `{campo.nome}` tem tipo `{campo.tipo}`.")
        for coluna, _ in conjunto.ordenacao_padrao:
            if coluna not in nomes:
                raise CatalogoInvalido(f"{onde}: ordem_padrao cita `{coluna}`, que nao e campo.")


conferir(CONJUNTOS)

CATALOGO: dict[str, Conjunto] = {conjunto.slug: conjunto for conjunto in CONJUNTOS}


def obter(slug: str) -> Conjunto:
    try:
        return CATALOGO[slug]
    except KeyError as exc:
        raise ConjuntoDesconhecido(slug) from exc


def conjuntos_da_area(slug: str) -> tuple[Conjunto, ...]:
    return tuple(c for c in CONJUNTOS if c.area.slug == slug)

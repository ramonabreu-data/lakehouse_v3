"""Tipos do catalogo.

`Conjunto` e a unidade de publicacao: um slug estavel apontando para UMA origem
de dados, com a lista do que pode sair, do que aceita filtro e do que serve de
agrupamento. `Area` agrupa conjuntos do mesmo setor — e o que vira secao na
documentacao.

`Fonte` e o ponto de extensao para outras origens: em vez de guardar o caminho
do Dremio numa string, o conjunto declara QUAL motor sabe le-lo e QUAL o
endereco dentro dele. Publicar um conjunto que venha de outro lugar e trocar o
motor da fonte — nenhuma outra camada muda.
"""

from __future__ import annotations

from dataclasses import dataclass, field

TIPOS = ("texto", "inteiro", "decimal", "booleano", "data")
NUMERICOS = ("inteiro", "decimal")


@dataclass(frozen=True)
class Fonte:
    """De onde o conjunto vem.

    motor: nome registrado em `app/motores` (hoje so "dremio").
    endereco: como o motor identifica o dado — para o Dremio, o caminho da view;
        para um motor HTTP seria a URL; para um Postgres, schema.tabela.
    """

    motor: str
    endereco: str

    def __str__(self) -> str:
        return self.endereco


@dataclass(frozen=True)
class Area:
    """Setor dono dos conjuntos. Vira uma secao no /docs."""

    slug: str
    titulo: str
    descricao: str


@dataclass(frozen=True)
class Campo:
    """Uma coluna exposta.

    filtravel: aceita filtro na query string. Deixe False no que nao faz sentido
        peneirar (latitude/longitude) — cada filtro e superficie de consulta.
    agrupavel: pode ser dimensao do endpoint /resumo.
    """

    nome: str
    tipo: str
    descricao: str = ""
    filtravel: bool = True
    agrupavel: bool = False

    @property
    def numerico(self) -> bool:
        return self.tipo in NUMERICOS


@dataclass(frozen=True)
class Conjunto:
    """O contrato de um conjunto publicado.

    ordem_padrao aceita o prefixo `-` para ordem decrescente, como no Django:
    `("-n_municipios",)` ordena do maior para o menor. E so o padrao — o cliente
    sempre pode pedir outra coisa com `ordenar_por` e `ordem`.
    """

    slug: str
    area: Area
    fonte: Fonte
    titulo: str
    descricao: str
    campos: tuple[Campo, ...]
    ordem_padrao: tuple[str, ...] = field(default=())

    def campo(self, nome: str) -> Campo | None:
        return next((c for c in self.campos if c.nome == nome), None)

    @property
    def nomes(self) -> tuple[str, ...]:
        return tuple(c.nome for c in self.campos)

    @property
    def agrupaveis(self) -> tuple[str, ...]:
        return tuple(c.nome for c in self.campos if c.agrupavel)

    @property
    def numericos(self) -> tuple[str, ...]:
        return tuple(c.nome for c in self.campos if c.numerico)

    @property
    def ordenacao_padrao(self) -> tuple[tuple[str, str], ...]:
        """`("-n_municipios",)` -> `(("n_municipios", "DESC"),)`."""
        return tuple(
            (coluna.lstrip("-"), "DESC" if coluna.startswith("-") else "ASC")
            for coluna in self.ordem_padrao
        )

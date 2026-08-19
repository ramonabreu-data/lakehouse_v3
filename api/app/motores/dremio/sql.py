"""Montagem do SQL do Dremio a partir do pedido ja validado.

O nucleo garante que identificador nunca veio do cliente e que todo valor ja e
um objeto Python do tipo declarado. Sobra para este modulo uma responsabilidade
so — e ela e critica: **transformar valor Python em literal SQL sem deixar o
literal escapar**. Aspa simples vira aspa dobrada; data vira `DATE '...'`;
booleano vira TRUE/FALSE.

Se um dia entrar um motor que fale outra coisa (Postgres direto, Mongo, HTTP),
ele escreve o proprio tradutor aqui do lado. O nucleo nao muda.
"""

from __future__ import annotations

import datetime as dt
from typing import Any

from app.nucleo import Conjunto, Consulta, ErroDeValidacao, Filtro, Resumo

COMPARADORES = {"gte": ">=", "lte": "<=", "gt": ">", "lt": "<", "ne": "<>", "eq": "="}
AGREGACOES = {"soma": "SUM", "media": "AVG", "minimo": "MIN", "maximo": "MAX"}


# ---------------------------------------------------------------------------
# Identificadores e literais
# ---------------------------------------------------------------------------

def identificador(nome: str) -> str:
    """Cita um identificador ja validado contra o catalogo.

    A checagem e redundante de proposito: se um dia alguem acrescentar ao
    catalogo um nome esquisito, a falha aparece aqui e nao no Dremio.
    """
    if not nome.replace("_", "").isalnum():
        raise ErroDeValidacao(f"Identificador invalido no catalogo: {nome}")
    return f'"{nome}"'


def caminho(conjunto: Conjunto) -> str:
    """`refinamento.espaco.view` -> `"refinamento"."espaco"."view"`."""
    return ".".join(identificador(parte) for parte in conjunto.fonte.endereco.split("."))


def texto(valor: str) -> str:
    """Literal de texto, com a aspa simples dobrada."""
    return "'" + valor.replace("'", "''") + "'"


def literal(valor: Any) -> str:
    """Valor Python -> literal SQL. Booleano antes de inteiro (bool e int)."""
    if valor is None:
        return "NULL"
    if isinstance(valor, bool):
        return "TRUE" if valor else "FALSE"
    if isinstance(valor, dt.date):
        return f"DATE {texto(valor.isoformat())}"
    if isinstance(valor, (int, float)):
        return str(valor)
    return texto(str(valor))


# ---------------------------------------------------------------------------
# WHERE
# ---------------------------------------------------------------------------

def expressao(filtro: Filtro) -> str:
    coluna = identificador(filtro.campo.nome)
    if filtro.operador in COMPARADORES:
        return f"{coluna} {COMPARADORES[filtro.operador]} {literal(filtro.valor)}"
    if filtro.operador == "in":
        return f"{coluna} IN ({', '.join(literal(v) for v in filtro.valores)})"
    if filtro.operador == "contem":
        # LOWER nos dois lados: o LIKE do Dremio diferencia maiuscula de
        # minuscula, e quem digita numa caixa de busca nao espera isso.
        return f"LOWER({coluna}) LIKE {texto('%' + str(filtro.valor).lower() + '%')}"
    if filtro.operador == "nulo":
        return f"{coluna} IS {'NULL' if filtro.valor else 'NOT NULL'}"
    raise ErroDeValidacao(f"Operador `{filtro.operador}` sem traducao para SQL.")


def _onde(filtros: tuple[Filtro, ...]) -> str:
    return " WHERE " + " AND ".join(expressao(f) for f in filtros) if filtros else ""


# ---------------------------------------------------------------------------
# Comandos
# ---------------------------------------------------------------------------

def dados(conjunto: Conjunto, consulta: Consulta) -> str:
    """SELECT paginado. Sem `SELECT *`: coluna nova na view nao vaza sem revisao."""
    projecao = ", ".join(identificador(coluna) for coluna in consulta.colunas)
    comando = f"SELECT {projecao} FROM {caminho(conjunto)}{_onde(consulta.filtros)}"
    if consulta.ordenacao:
        ordem = ", ".join(f"{identificador(c)} {d}" for c, d in consulta.ordenacao)
        comando += f" ORDER BY {ordem}"
    return f"{comando} LIMIT {consulta.limite} OFFSET {consulta.deslocamento}"


def total(conjunto: Conjunto, consulta: Consulta) -> str:
    """Contagem com os MESMOS filtros, sem ordenar nem paginar."""
    return f'SELECT COUNT(*) AS "total" FROM {caminho(conjunto)}{_onde(consulta.filtros)}'


def resumo(conjunto: Conjunto, pedido: Resumo) -> str:
    grupos = ", ".join(identificador(g) for g in pedido.agrupar_por)
    projecao = [grupos, 'COUNT(*) AS "registros"']
    if pedido.metrica:
        projecao.append(
            f"{AGREGACOES[pedido.funcao]}({identificador(pedido.metrica)}) "
            f"AS {identificador(pedido.apelido_da_metrica)}"
        )
    return (
        f"SELECT {', '.join(projecao)} FROM {caminho(conjunto)}{_onde(pedido.filtros)}"
        f' GROUP BY {grupos} ORDER BY "registros" DESC LIMIT {pedido.limite}'
    )

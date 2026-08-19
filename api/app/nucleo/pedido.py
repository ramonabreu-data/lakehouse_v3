"""O pedido do cliente, validado contra o catalogo — e ainda **sem SQL**.

Aqui a query string vira um objeto tipado: quais colunas, quais filtros (com os
valores ja convertidos para int/float/date/bool), como ordenar e quanto trazer.
Traduzir isso para a linguagem da fonte e trabalho do motor.

Essa separacao e o que fecha a porta da injecao **e** abre a porta para outras
fontes ao mesmo tempo:

* identificador (coluna, campo de filtro, agrupamento) nunca vem do cliente —
  ele escolhe *entre* os que o catalogo declara;
* valor vem de fora, mas so passa depois de convertido ao tipo declarado. O que
  chega ao motor e um `int`, um `datetime.date` — nao um pedaco de texto.

Um motor que fale SQL escapa na hora de montar a string; um motor que fale HTTP
manda o mesmo valor como parametro. Nenhum dos dois refaz esta validacao.
"""

from __future__ import annotations

import datetime as dt
from dataclasses import dataclass, field
from typing import Any

from app.nucleo.erros import ErroDeValidacao
from app.nucleo.tipos import Campo, Conjunto

LIMITE_PADRAO = 100
LIMITE_MAXIMO = 5_000
LIMITE_RESUMO = 1_000
TAMANHO_MAXIMO_DO_VALOR = 500
MAXIMO_DE_VALORES_EM_LISTA = 200
MAXIMO_DE_AGRUPAMENTOS = 3

# Parametros que a API interpreta; o resto da query string e tratado como filtro.
RESERVADOS = frozenset({"colunas", "ordenar_por", "ordem", "limite", "deslocamento", "incluir_total"})
RESERVADOS_RESUMO = frozenset({"agrupar_por", "metrica", "funcao", "limite"})

OPERADORES = ("eq", "gte", "lte", "gt", "lt", "ne", "in", "contem", "nulo")
FUNCOES = ("soma", "media", "minimo", "maximo")

VERDADEIROS = ("true", "1", "sim")
FALSOS = ("false", "0", "nao")


# ---------------------------------------------------------------------------
# Conversao de valores
# ---------------------------------------------------------------------------

def _texto(valor: str) -> str:
    if len(valor) > TAMANHO_MAXIMO_DO_VALOR:
        raise ErroDeValidacao(f"Valor longo demais (maximo {TAMANHO_MAXIMO_DO_VALOR} caracteres).")
    if any(caractere < " " or caractere == "\x7f" for caractere in valor):
        raise ErroDeValidacao("Valor contem caractere de controle.")
    return valor


def _booleano(bruto: str) -> bool:
    normalizado = bruto.strip().lower()
    if normalizado in VERDADEIROS:
        return True
    if normalizado in FALSOS:
        return False
    raise ErroDeValidacao(f"Esperado true/false; veio {bruto!r}.")


def converter(campo: Campo, bruto: str) -> Any:
    """Texto cru -> valor Python do tipo declarado. Falhar aqui e o correto."""
    try:
        if campo.tipo == "inteiro":
            return int(bruto)
        if campo.tipo == "decimal":
            return float(bruto)
        if campo.tipo == "booleano":
            return _booleano(bruto)
        if campo.tipo == "data":
            return dt.date.fromisoformat(bruto.strip())
        return _texto(bruto)
    except ErroDeValidacao as exc:
        raise ErroDeValidacao(f"Valor invalido para `{campo.nome}`: {exc}") from exc
    except (TypeError, ValueError) as exc:
        raise ErroDeValidacao(
            f"Valor invalido para `{campo.nome}` (esperado {campo.tipo}): {bruto!r}"
        ) from exc


# ---------------------------------------------------------------------------
# Filtros
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Filtro:
    """Um filtro ja validado. `valores` sao objetos Python, nunca texto cru."""

    campo: Campo
    operador: str
    valores: tuple[Any, ...]

    @property
    def valor(self) -> Any:
        return self.valores[0]


def _filtro(campo: Campo, operador: str, bruto: str) -> Filtro:
    if operador not in OPERADORES:
        raise ErroDeValidacao(f"Operador desconhecido em `{campo.nome}__{operador}`.")
    if operador == "contem" and campo.tipo != "texto":
        raise ErroDeValidacao(f"`contem` so vale para campo de texto; `{campo.nome}` e {campo.tipo}.")

    if operador == "nulo":
        return Filtro(campo, operador, (_booleano(bruto),))
    if operador == "in":
        itens = [parte.strip() for parte in bruto.split(",") if parte.strip()]
        if not itens:
            raise ErroDeValidacao(f"Filtro `{campo.nome}__in` veio vazio.")
        if len(itens) > MAXIMO_DE_VALORES_EM_LISTA:
            raise ErroDeValidacao(
                f"Filtro `{campo.nome}__in` aceita no maximo {MAXIMO_DE_VALORES_EM_LISTA} valores."
            )
        return Filtro(campo, operador, tuple(converter(campo, item) for item in itens))
    return Filtro(campo, operador, (converter(campo, bruto),))


def _filtros(
    conjunto: Conjunto, params: dict[str, list[str]], reservados: frozenset[str]
) -> tuple[Filtro, ...]:
    filtros: list[Filtro] = []
    for chave, valores in params.items():
        if chave in reservados:
            continue
        nome, _, operador = chave.partition("__")
        campo = conjunto.campo(nome)
        if campo is None:
            raise ErroDeValidacao(f"Campo `{nome}` nao existe em `{conjunto.slug}`.")
        if not campo.filtravel:
            raise ErroDeValidacao(f"Campo `{nome}` nao aceita filtro.")
        filtros.extend(_filtro(campo, operador or "eq", valor) for valor in valores)
    return tuple(filtros)


# ---------------------------------------------------------------------------
# Listagem
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Consulta:
    colunas: tuple[str, ...]
    filtros: tuple[Filtro, ...] = ()
    ordenacao: tuple[tuple[str, str], ...] = ()
    limite: int = LIMITE_PADRAO
    deslocamento: int = 0
    incluir_total: bool = False


def _inteiro(params: dict[str, list[str]], chave: str, padrao: int) -> int:
    if chave not in params:
        return padrao
    bruto = params[chave][-1]
    try:
        return int(bruto)
    except (TypeError, ValueError) as exc:
        raise ErroDeValidacao(f"`{chave}` deve ser um numero inteiro; veio {bruto!r}.") from exc


def _bandeira(params: dict[str, list[str]], chave: str) -> bool:
    return params.get(chave, ["false"])[-1].strip().lower() in VERDADEIROS


def _lista(params: dict[str, list[str]], chave: str) -> list[str]:
    return [item.strip() for item in params.get(chave, [""])[-1].split(",") if item.strip()]


def analisar_parametros(conjunto: Conjunto, params: dict[str, list[str]]) -> Consulta:
    """Valida a query string inteira contra o catalogo do conjunto."""
    pedidas = _lista(params, "colunas") if "colunas" in params else []
    desconhecidas = [c for c in pedidas if conjunto.campo(c) is None]
    if desconhecidas:
        raise ErroDeValidacao(f"Coluna(s) fora do conjunto: {', '.join(desconhecidas)}.")
    colunas = tuple(pedidas) or conjunto.nomes

    if "ordenar_por" in params:
        coluna = params["ordenar_por"][-1].strip()
        if conjunto.campo(coluna) is None:
            raise ErroDeValidacao(f"Nao da para ordenar por `{coluna}`: campo inexistente.")
        decrescente = params.get("ordem", ["asc"])[-1].strip().lower() in ("desc", "descendente")
        ordenacao = ((coluna, "DESC" if decrescente else "ASC"),)
    else:
        # O catalogo aceita `-coluna` para decrescente; `ordenacao_padrao` resolve.
        ordenacao = conjunto.ordenacao_padrao

    limite = _inteiro(params, "limite", LIMITE_PADRAO)
    if not 1 <= limite <= LIMITE_MAXIMO:
        raise ErroDeValidacao(f"`limite` deve ficar entre 1 e {LIMITE_MAXIMO}; veio {limite}.")
    deslocamento = _inteiro(params, "deslocamento", 0)
    if deslocamento < 0:
        raise ErroDeValidacao("`deslocamento` nao pode ser negativo.")

    return Consulta(
        colunas=colunas,
        filtros=_filtros(conjunto, params, RESERVADOS),
        ordenacao=ordenacao,
        limite=limite,
        deslocamento=deslocamento,
        incluir_total=_bandeira(params, "incluir_total"),
    )


# ---------------------------------------------------------------------------
# Resumo (agregacao)
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Resumo:
    agrupar_por: tuple[str, ...]
    metrica: str | None = None
    funcao: str = "soma"
    filtros: tuple[Filtro, ...] = field(default=())
    limite: int = LIMITE_RESUMO

    @property
    def apelido_da_metrica(self) -> str:
        return f"{self.metrica}_{self.funcao}"


def analisar_resumo(conjunto: Conjunto, params: dict[str, list[str]]) -> Resumo:
    """Agrupamento e metrica, ambos escolhidos dentro do catalogo."""
    grupos = _lista(params, "agrupar_por")
    if not grupos:
        raise ErroDeValidacao("Informe `agrupar_por` com ao menos um campo agrupavel.")
    if len(grupos) > MAXIMO_DE_AGRUPAMENTOS:
        raise ErroDeValidacao(f"`agrupar_por` aceita no maximo {MAXIMO_DE_AGRUPAMENTOS} campos.")
    for grupo in grupos:
        campo = conjunto.campo(grupo)
        if campo is None or not campo.agrupavel:
            raise ErroDeValidacao(f"Campo `{grupo}` nao pode ser usado como agrupamento.")

    metrica = params.get("metrica", [""])[-1].strip() or None
    funcao = params.get("funcao", ["soma"])[-1].strip().lower()
    if metrica is not None:
        campo = conjunto.campo(metrica)
        if campo is None or not campo.numerico:
            raise ErroDeValidacao(f"Metrica `{metrica}` precisa ser um campo numerico do conjunto.")
        if funcao not in FUNCOES:
            raise ErroDeValidacao(f"Funcao `{funcao}` nao suportada; use {', '.join(FUNCOES)}.")

    limite = _inteiro(params, "limite", LIMITE_RESUMO)
    if not 1 <= limite <= LIMITE_RESUMO:
        raise ErroDeValidacao(f"`limite` do resumo deve ficar entre 1 e {LIMITE_RESUMO}.")

    return Resumo(
        agrupar_por=tuple(grupos),
        metrica=metrica,
        funcao=funcao,
        filtros=_filtros(conjunto, params, RESERVADOS_RESUMO),
        limite=limite,
    )

"""Textos do /docs, gerados a partir do catalogo.

Fica separado das rotas porque e outro assunto: as rotas amarram caminho a
servico; aqui so se escreve o que a pessoa que integra vai ler. Como o texto sai
do proprio catalogo, conjunto novo ja nasce documentado — e documentacao nao
envelhece em relacao ao contrato.
"""

from __future__ import annotations

from app.nucleo import FUNCOES, LIMITE_MAXIMO, LIMITE_PADRAO, Conjunto


def tabela_de_campos(conjunto: Conjunto) -> str:
    linhas = ["| Campo | Tipo | Filtro | Agrupa | Descricao |", "|---|---|:-:|:-:|---|"]
    for campo in conjunto.campos:
        linhas.append(
            f"| `{campo.nome}` | {campo.tipo} | {'sim' if campo.filtravel else '—'} "
            f"| {'sim' if campo.agrupavel else '—'} | {campo.descricao} |"
        )
    return "\n".join(linhas)


def exemplos_de_filtro(conjunto: Conjunto) -> str:
    """Exemplos com os campos REAIS do conjunto — vale mais que exemplo generico."""
    def primeiro(condicao):
        return next((c for c in conjunto.campos if c.filtravel and condicao(c)), None)

    texto = primeiro(lambda c: c.tipo == "texto")
    numero = primeiro(lambda c: c.numerico)
    data = primeiro(lambda c: c.tipo == "data")
    booleano = primeiro(lambda c: c.tipo == "booleano")

    exemplos = []
    if texto:
        exemplos.append(f"?{texto.nome}=valor exato")
        exemplos.append(f"?{texto.nome}__contem=parte  (ignora maiuscula/minuscula)")
    if numero:
        exemplos.append(f"?{numero.nome}__gte=10&{numero.nome}__lt=100")
        exemplos.append(f"?{numero.nome}__in=1,2,3")
    if data:
        exemplos.append(f"?{data.nome}__gte=2025-01-01")
    if booleano:
        exemplos.append(f"?{booleano.nome}=true")
    return "\n".join(exemplos)


def campos(conjunto: Conjunto) -> str:
    return (
        f"{conjunto.descricao}\n\n**Fonte:** `{conjunto.fonte.endereco}` "
        f"(motor `{conjunto.fonte.motor}`)\n\n"
        "Devolve o contrato do conjunto em JSON: cada campo com tipo, se aceita filtro e se "
        "serve de agrupamento. Util para montar tela ou validar integracao sem chutar nome."
    )


def dados(conjunto: Conjunto) -> str:
    return f"""{conjunto.descricao}

**Fonte:** `{conjunto.fonte.endereco}` (motor `{conjunto.fonte.motor}`)

**Paginacao e ordenacao** — `limite` (padrao {LIMITE_PADRAO}, teto {LIMITE_MAXIMO}),
`deslocamento`, `ordenar_por`, `ordem` (`asc`/`desc`), `colunas` (lista separada por
virgula) e `incluir_total=true` para receber a contagem total junto.

**Filtros** — qualquer campo marcado como filtravel abaixo vira parametro na URL.
Operadores: `__gte`, `__lte`, `__gt`, `__lt`, `__ne`, `__in`, `__contem`, `__nulo`.

```
{exemplos_de_filtro(conjunto)}
```

{tabela_de_campos(conjunto)}
"""


def resumo(conjunto: Conjunto) -> str:
    agrupaveis = conjunto.agrupaveis
    numericos = conjunto.numericos
    exemplo = f"?agrupar_por={agrupaveis[0]}" if agrupaveis else ""
    if agrupaveis and numericos:
        exemplo += f"\n?agrupar_por={agrupaveis[0]}&metrica={numericos[0]}&funcao=media"
    return f"""Contagem de registros agrupada por ate 3 campos, calculada **na fonte**.

Existe para a aplicacao nao precisar baixar a tabela inteira so para contar.

**Agrupamento** (`agrupar_por`): {', '.join(f'`{n}`' for n in agrupaveis) or 'nenhum campo agrupavel'}.

**Metrica** (`metrica` + `funcao`): qualquer campo numerico —
{', '.join(f'`{n}`' for n in numericos) or 'nenhum'}. Funcoes: {', '.join(f'`{f}`' for f in FUNCOES)}.

Os mesmos filtros de `/dados` valem aqui.

```
{exemplo}
```
"""


def secao(conjunto: Conjunto) -> dict[str, str]:
    """A secao do conjunto no /docs: o nome que aparece e o que ele entrega."""
    return {
        "name": conjunto.titulo,
        "description": f"**{conjunto.area.titulo}** — {conjunto.descricao}",
    }

"""Ajustes comuns aos gráficos Altair do painel.

Aqui moram duas correções que existem por causa de como o **Streamlit** trata o
spec do Vega-Lite antes de embuti-lo. Sem elas o console do navegador enche de
`WARN` a cada rerun — e o `logLevel` não resolve: o Streamlit apaga tudo o que
não seja `theme`, `renderer` ou `padding` de `usermeta.embedOptions`
(`ArrowVegaLiteChart`, função que sanitiza o spec).

**1. `selecao()` declara `encodings` explicitamente.** Numa seleção de ponto sem
`encodings`, o Streamlit preenche o campo com TODOS os canais do gráfico
(`select.encodings = Object.keys(spec.encoding)`) — inclusive `opacity` e
`tooltip`, que não têm campo. Daí os avisos *"Cannot project a selection on
encoding channel opacity/tooltip, which has no field"*. Declarando a lista
(vazia, porque quem identifica a barra é o `fields`), o Streamlit não mexe.

**2. Barra sem empilhamento (`stack=None`, nos gráficos).** Com um valor por
categoria não há o que empilhar, mas o Vega-Lite ainda cria os campos
`<campo>_start`/`_end` e calcula a extensão deles — e como o Streamlit manda os
dados à parte (em Arrow), a primeira avaliação acontece com o conjunto vazio e
sai *"Infinite extent for field ...: [Infinity, -Infinity]"*. Sem empilhamento,
os campos não existem e o aviso não tem como aparecer.

Pela mesma razão o eixo do tempo é **ordinal** (`"2026-08"`), e não temporal: o
`yearmonth(...)` também gera campos derivados cuja extensão é calculada no
vazio.

**3. `escala()` fixa o domínio do eixo numérico.** Mesmo sem empilhamento, um
eixo quantitativo sem domínio manda o Vega calcular a extensão a partir dos
dados — que, de novo, ainda não chegaram na primeira avaliação. Com o domínio
declarado (o máximo já é conhecido em Python) não há extensão a calcular, e o
eixo passa a ser o mesmo em qualquer ordem de chegada.
"""

import altair as alt


def selecao(nome: str, campo: str):
    """Seleção de ponto por um campo — clicar numa marca escolhe aquele valor."""
    return alt.selection_point(name=nome, fields=[campo], encodings=[])


def escala(maximo, minimo=0):
    """Domínio explícito de um eixo numérico, a partir do valor já conhecido."""
    return alt.Scale(domain=[float(minimo), float(maximo or 1)])

"""Tabela do painel: todas as linhas, todo o texto — desenhada em HTML.

Compartilhada pelas abas que mostram uma lista ao lado do mapa. Existe por uma
razao so: o `st.dataframe` CORTA o texto que nao cabe na celula e rola por
dentro de um quadro de altura fixa. Quando a lista E o conteudo (as acoes do
secretario, a pontuacao dos municipios), o que ele esconde e justamente o que
se quer ler. Aqui a celula quebra a linha e todas as linhas do recorte sao
renderizadas.

`altura` limita o quadro em pixels e rola por dentro: e o que permite a tabela
ficar ao LADO do mapa sem esticar a pagina, com o cabecalho grudado no topo. Sem
altura, a tabela cresce a vontade e quem rola e a pagina.

O preco de nao usar o `st.dataframe` e perder a ordenacao por clique no
cabecalho — daí `ordenar`, que troca o clique por um seletor explicito.

O estilo vive em `estilo.py`, na classe `.tabela-completa`.
"""

import html

import pandas as pd
import streamlit as st

# Altura do quadro quando a tabela divide a linha com o mapa: a mesma do mapa
# (`mapa.pontos`), para as duas metades terminarem juntas.
ALTURA_AO_LADO_DO_MAPA = 620


def celula(valor, classe: str, maximo: float = 0) -> str:
    """Uma célula formatada do jeito que a coluna pede.

    As classes: `data` e `num` nao quebram, `nome` e a coluna de referencia,
    `texto` quebra a linha (a que carrega a descricao longa), `decimal` mostra
    uma casa, `sim_nao` traduz o booleano e `barra` desenha a comparacao
    proporcional (a largura conta, o numero fica ao lado).
    """
    if valor is None or pd.isna(valor):
        return f'<td class="{classe}">—</td>'
    if classe == "data":
        return f'<td class="data">{pd.Timestamp(valor):%d/%m/%Y}</td>'
    if classe == "barra":
        largura = 100 * float(valor) / (maximo or 1)
        return ('<td class="num"><span class="barra">'
                f'<b class="trilho"><i style="width:{largura:.0f}%"></i></b>'
                f"<span>{int(valor)}</span></span></td>")
    if classe == "num":
        return f'<td class="num">{int(valor):,}</td>'.replace(",", ".")
    if classe == "decimal":
        return f'<td class="num">{float(valor):.1f}</td>'.replace(".", ",", 1)
    if classe == "sim_nao":
        return f'<td class="data">{"Sim" if valor else "Não"}</td>'
    return f'<td class="{classe}">{html.escape(str(valor))}</td>'


def completa(df: pd.DataFrame, colunas: list[tuple[str, str, str]],
             altura: int | None = None) -> None:
    """Desenha a tabela inteira. `colunas` é uma lista de (campo, rótulo, classe)."""
    maximos = {campo: (pd.to_numeric(df[campo], errors="coerce").max() or 1)
               for campo, _, classe in colunas if classe == "barra"}
    cabecalho = "".join(f"<th>{html.escape(rotulo)}</th>" for _, rotulo, _ in colunas)
    linhas = "".join(
        "<tr>" + "".join(celula(registro[campo], classe, maximos.get(campo, 0))
                         for campo, _, classe in colunas) + "</tr>"
        for registro in df.to_dict("records")
    )
    estilo = f' style="max-height:{altura}px;overflow-y:auto"' if altura else ""
    st.markdown(
        f'<div class="tabela-completa"{estilo}><table><thead><tr>{cabecalho}</tr></thead>'
        f"<tbody>{linhas}</tbody></table></div>",
        unsafe_allow_html=True,
    )


def buscar(df: pd.DataFrame, colunas: list[str], termo: str) -> pd.DataFrame:
    """Filtra as linhas em que o termo aparece em qualquer uma das colunas."""
    termo = (termo or "").strip().lower()
    if not termo:
        return df
    achou = False
    for coluna in colunas:
        acha = df[coluna].fillna("").astype(str).str.lower().str.contains(termo, regex=False)
        achou = acha if achou is False else (achou | acha)
    return df[achou]


def ordenar(df: pd.DataFrame, ordens: dict, chave: str, container=None) -> pd.DataFrame:
    """Seletor de ordem + o DataFrame já ordenado.

    `ordens` mapeia o rotulo -> (coluna, crescente). Estavel de proposito: o
    criterio anterior (o nome do municipio, por exemplo) sobrevive como
    desempate dentro da ordem escolhida.
    """
    alvo = container if container is not None else st
    escolha = alvo.selectbox("Ordenar por", list(ordens), key=f"ordem_{chave}")
    coluna, crescente = ordens[escolha]
    return df.sort_values(coluna, ascending=crescente, kind="stable",
                          na_position="last").reset_index(drop=True)


def baixar(df: pd.DataFrame, arquivo: str, chave: str) -> None:
    """Botão de CSV do que está na tela (com filtro, busca e ordem aplicados)."""
    st.download_button(
        "Baixar CSV",
        df.to_csv(index=False).encode("utf-8"),
        file_name=f"{arquivo}.csv",
        mime="text/csv",
        key=f"csv_{chave}",
    )


def largura_inteira(chave: str) -> bool:
    """Interruptor "Largura inteira" — e o estado dele, lido da sessão.

    Quem desenha a tela precisa saber ANTES de montar as colunas se a tabela vai
    ao lado do mapa ou embaixo dele; o interruptor e desenhado depois, junto da
    tabela. Por isso o valor mora na sessao: `estado()` le, `interruptor()`
    desenha, e mudar um dispara o rerun que reorganiza o layout.
    """
    return st.session_state.get(f"tabela_larga_{chave}", False)


def interruptor_largura(chave: str) -> bool:
    """Desenha o interruptor e devolve se a tabela deve ocupar a página toda."""
    return st.toggle(
        "Largura inteira", key=f"tabela_larga_{chave}",
        help="Move a tabela para baixo do mapa, ocupando a página toda e sem limite "
             "de altura — bom para ler os textos longos.",
    )

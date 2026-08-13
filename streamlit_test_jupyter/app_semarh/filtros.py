"""Filtros que sobrevivem ao refresh, espelhando o estado na URL.

O estado dos multiselects vai para `st.query_params`, que persiste no reload —
ao atualizar a pagina o filtro volta ao ultimo estado. "|" separa os valores
(nao ocorre nos nomes). Use `url_key` distinto por aba para nao colidir.
"""

import streamlit as st


def _ler(qp, url_key, opcoes):
    if url_key not in qp:
        return list(opcoes)          # ausente na URL => tudo selecionado
    valor = qp[url_key]
    if valor == "":
        return []                    # presente e vazio => nada selecionado
    escolhidos = valor.split("|")
    return [x for x in opcoes if x in escolhidos]


def multiselect_url(rotulo, opcoes, url_key, container=None):
    """Multiselect cujo estado e persistido na URL (sobrevive ao refresh)."""
    alvo = container if container is not None else st
    widget_key = f"filtro_{url_key}"
    qp = st.query_params

    def _sincronizar():
        sel = st.session_state.get(widget_key, list(opcoes))
        if set(sel) == set(opcoes):
            if url_key in qp:
                del qp[url_key]      # tudo selecionado => mantem a URL limpa
        elif not sel:
            qp[url_key] = ""
        else:
            qp[url_key] = "|".join(sel)

    return alvo.multiselect(
        rotulo, opcoes,
        default=_ler(qp, url_key, opcoes),
        key=widget_key,
        on_change=_sincronizar,
    )


def selectbox_url(rotulo, opcoes, url_key, container=None, padrao=None, formato=str,
                  ajuda=None):
    """Escolha unica persistida na URL (sobrevive ao refresh e vai no link).

    Diferente dos multiselects: aqui sempre ha um valor. `padrao` e usado quando
    a URL nao traz nada (ou traz algo fora das opcoes).
    """
    alvo = container if container is not None else st
    widget_key = f"filtro_{url_key}"
    qp = st.query_params
    padrao = opcoes[0] if padrao is None else padrao

    def _sincronizar():
        escolhido = st.session_state.get(widget_key, padrao)
        if escolhido == padrao:
            if url_key in qp:
                del qp[url_key]      # padrao => mantem a URL limpa
        else:
            qp[url_key] = str(escolhido)

    da_url = qp.get(url_key)
    inicial = next((o for o in opcoes if str(o) == da_url), padrao)
    return alvo.selectbox(
        rotulo, opcoes,
        index=opcoes.index(inicial),
        key=widget_key,
        on_change=_sincronizar,
        format_func=formato,
        help=ajuda,
    )


def multiselect_opcional_url(rotulo, opcoes, url_key, container=None, ajuda=None,
                             placeholder="Todos"):
    """Multiselect onde **vazio = sem filtro** (todos os valores).

    Para listas longas (municipios): o `multiselect_url` comeca com tudo
    marcado, o que encheria a tela de chips. Aqui a selecao comeca vazia e o
    filtro so entra em acao quando o usuario escolhe um ou mais valores.
    Tambem persiste na URL, com a mesma convencao de "|".
    """
    alvo = container if container is not None else st
    widget_key = f"filtro_{url_key}"
    qp = st.query_params

    def _sincronizar():
        sel = st.session_state.get(widget_key, [])
        if sel:
            qp[url_key] = "|".join(sel)
        elif url_key in qp:
            del qp[url_key]          # nenhum escolhido => URL limpa

    escolhidos = qp.get(url_key, "").split("|") if url_key in qp else []
    return alvo.multiselect(
        rotulo, opcoes,
        default=[x for x in opcoes if x in escolhidos],
        key=widget_key,
        on_change=_sincronizar,
        help=ajuda,
        placeholder=placeholder,
    )

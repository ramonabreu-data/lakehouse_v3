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

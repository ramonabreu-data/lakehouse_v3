"""BI placeholder: uma fabrica que devolve um `render(user)` de "em construcao".

Use para registrar BIs ainda nao implementados em `setores.py`, mantendo a aba
visivel. Quando o BI existir, troque pelo modulo real.
"""

import streamlit as st


def render_para(titulo: str):
    def render(user: dict | None = None) -> None:
        st.markdown(f"#### {titulo}")
        st.info("BI em construção. O conteúdo será adicionado aqui.")

    return render

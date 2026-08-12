"""Navegacao do painel SEMARH.

Dois niveis, ambos espelhados na URL (sobrevivem ao refresh):
  1. Setor  -> botoes arredondados na sidebar (?setor=...)
  2. BI     -> cartoes na area principal; ao abrir um, ?bi=...

Um setor pode ter varios BIs; hoje so a Chefia de Gabinete tem um
(Selo Ambiental 2026). Setor sem BI abre vazio.
"""

import streamlit as st

from app_semarh.setores import SETORES


def render(user: dict | None) -> None:
    # O estilo global (botoes, sidebar, responsividade) e aplicado em app.py.
    qp = st.query_params
    por_slug = {s["slug"]: s for s in SETORES}

    setor_atual = qp.get("setor")
    if setor_atual not in por_slug:
        # padrao: primeiro setor que tem BI (senao o primeiro da lista)
        setor_atual = next((s["slug"] for s in SETORES if s["bis"]), SETORES[0]["slug"])

    # --- sidebar: botoes dos setores ------------------------------------
    st.sidebar.markdown("### Áreas")
    for s in SETORES:
        ativo = s["slug"] == setor_atual
        if st.sidebar.button(
            s["titulo"],
            key=f"setor_{s['slug']}",
            use_container_width=True,
            type="primary" if ativo else "secondary",
        ):
            st.query_params["setor"] = s["slug"]
            if "bi" in st.query_params:
                del st.query_params["bi"]
            st.rerun()

    setor = por_slug[setor_atual]

    # --- cabecalho ------------------------------------------------------
    st.title("Painel SEMARH")
    st.caption("Secretaria de Estado do Meio Ambiente e Recursos Hídricos — Piauí")
    st.subheader(setor["titulo"])

    bis = setor["bis"]
    if not bis:
        st.info("Nenhum BI disponível para esta área ainda.")
        return

    # --- BIs como abas (segmented_control), persistidas na URL (?bi=...) ---
    por_bi = {b["slug"]: b for b in bis}
    slugs = [b["slug"] for b in bis]
    bi_atual = qp.get("bi")
    if bi_atual not in por_bi:
        bi_atual = slugs[0]

    # key por setor para nao carregar selecao de um setor para outro
    bi_key = f"bi_sel_{setor['slug']}"

    def _sincronizar_bi():
        escolha = st.session_state.get(bi_key)
        if escolha:
            st.query_params["bi"] = escolha

    escolhido = st.segmented_control(
        "BI",
        slugs,
        format_func=lambda s: por_bi[s]["titulo"],
        default=bi_atual,
        key=bi_key,
        on_change=_sincronizar_bi,
        label_visibility="collapsed",
    )
    st.divider()
    por_bi[escolhido or bi_atual]["render"](user)

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

    por_bi = {b["slug"]: b for b in bis}
    bi_atual = qp.get("bi")

    if bi_atual in por_bi:
        # --- BI aberto ---
        if st.button("← Voltar aos BIs", key="voltar_bi"):
            del st.query_params["bi"]
            st.rerun()
        st.divider()
        por_bi[bi_atual]["render"](user)
    else:
        # --- lista de BIs do setor ---
        st.caption("Selecione um BI para abrir:")
        colunas = st.columns(min(3, len(bis)))
        for i, b in enumerate(bis):
            if colunas[i % len(colunas)].button(
                f"📊 {b['titulo']}", key=f"bi_{b['slug']}", use_container_width=True
            ):
                st.query_params["bi"] = b["slug"]
                st.rerun()

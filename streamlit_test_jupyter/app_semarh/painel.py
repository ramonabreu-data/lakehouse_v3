"""Monta o painel SEMARH: cabecalho + navegacao entre as 4 areas.

A aba ativa e espelhada na URL (`?aba=...`) para sobreviver ao refresh — por
isso usamos `st.segmented_control` (controlavel) em vez de `st.tabs` (cuja aba
ativa e estado so do navegador e reseta no reload). So a area selecionada e
renderizada.

Cada area e um modulo em `app_semarh/abas/` com uma funcao `render(user)`.
"""

import streamlit as st

from app_semarh.abas import chefia_gabinete, gestao, meio_ambiente, psi_pilares

# (slug na URL, titulo exibido, modulo)
ABAS = [
    ("gestao", "Superintendência de Gestão", gestao),
    ("meio_ambiente", "Superintendência de Meio Ambiente", meio_ambiente),
    ("chefia", "Chefia de Gabinete", chefia_gabinete),
    ("psi_pilares", "PSI&Pilares II", psi_pilares),
]


def render(user: dict | None) -> None:
    st.title("Painel SEMARH")
    st.caption("Secretaria de Estado do Meio Ambiente e Recursos Hídricos — Piauí")

    slugs = [s for s, _, _ in ABAS]
    titulos = {s: t for s, t, _ in ABAS}
    modulos = {s: m for s, _, m in ABAS}

    qp = st.query_params
    atual = qp.get("aba")
    if atual not in slugs:
        atual = slugs[0]

    def _sincronizar_aba():
        escolha = st.session_state.get("aba_ativa")
        if escolha:
            st.query_params["aba"] = escolha

    escolhido = st.segmented_control(
        "Área",
        slugs,
        format_func=lambda s: titulos[s],
        default=atual,
        key="aba_ativa",
        on_change=_sincronizar_aba,
        label_visibility="collapsed",
    )

    # segmented_control permite desmarcar (retorna None) — nesse caso mantem a
    # ultima aba da URL.
    modulos[escolhido or atual].render(user)

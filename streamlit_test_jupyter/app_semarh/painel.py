"""Monta o painel SEMARH: um cabecalho e as 4 abas.

Cada aba e um modulo em `app_semarh/abas/` com uma funcao `render(user)`.
"""

import streamlit as st

from app_semarh.abas import chefia_gabinete, gestao, meio_ambiente, psi_pilares

ABAS = [
    ("Superintendência de Gestão", gestao),
    ("Superintendência de Meio Ambiente", meio_ambiente),
    ("Chefia de Gabinete", chefia_gabinete),
    ("PSI&Pilares II", psi_pilares),
]


def render(user: dict | None) -> None:
    st.title("Painel SEMARH")
    st.caption("Secretaria de Estado do Meio Ambiente e Recursos Hídricos — Piauí")

    guias = st.tabs([titulo for titulo, _ in ABAS])
    for guia, (_, modulo) in zip(guias, ABAS):
        with guia:
            modulo.render(user)

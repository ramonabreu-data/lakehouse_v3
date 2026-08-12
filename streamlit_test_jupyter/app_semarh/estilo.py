"""Estilo global responsivo do painel SEMARH.

Aplicado uma vez no `app.py` (antes do login), entao cobre a tela de login e o
dashboard. Usa unidades relativas + `clamp()` + `flex-wrap` para caber bem em
celular, tablet e desktop, e cores em rgba (theme-aware: claro e escuro).
"""

import streamlit as st

_CSS = """
<style>
/* ---- container principal: paddings enxutos e responsivos ---- */
.block-container { padding-top: 1.1rem; padding-bottom: 2.2rem; max-width: 1300px; }
@media (max-width: 640px) {
    .block-container { padding-left: .7rem; padding-right: .7rem; padding-top: .7rem; }
}

/* ---- titulos escalam com a tela ---- */
h1, [data-testid="stHeading"] h1 { font-size: clamp(1.35rem, 3.6vw, 2rem) !important; line-height: 1.2 !important; }
h2, [data-testid="stHeading"] h2 { font-size: clamp(1.15rem, 3vw, 1.55rem) !important; }
h3, [data-testid="stHeading"] h3 { font-size: clamp(1.02rem, 2.6vw, 1.28rem) !important; }
[data-testid="stCaptionContainer"] { font-size: clamp(.75rem, 2vw, .9rem); }

/* ---- colunas quebram em telas estreitas (KPIs/graficos/filtros empilham) ---- */
[data-testid="stHorizontalBlock"] { flex-wrap: wrap; gap: .6rem; }
[data-testid="stColumn"] { min-width: 12rem; }

/* ---- botoes compactos e arredondados ---- */
.stButton > button, .stDownloadButton > button {
    border-radius: 12px;
    padding: .36rem .85rem;
    font-size: clamp(.8rem, 2.1vw, .92rem);
    min-height: 0;
    line-height: 1.3;
}
/* botoes de navegacao (setores) na sidebar */
section[data-testid="stSidebar"] .stButton > button {
    border: 1px solid rgba(128, 128, 128, .35);
    justify-content: flex-start;
    text-align: left;
    font-weight: 500;
    margin-bottom: .15rem;
}

/* ---- BIs como abas (segmented_control): compactas e quebram na tela ---- */
[data-testid="stSegmentedControl"] { flex-wrap: wrap; gap: .3rem; }
[data-testid="stSegmentedControl"] button {
    padding: .28rem .72rem;
    font-size: clamp(.72rem, 1.9vw, .86rem);
    border-radius: 10px;
    min-height: 0;
}

/* ---- formularios (login/cadastro) compactos ---- */
[data-testid="stForm"] {
    max-width: 400px;
    margin: 0 auto;
    border-radius: 14px;
    padding: 1rem 1.1rem;
}

/* ---- grade de KPIs responsiva (auto-fit) ---- */
.kpi-grid {
    display: grid;
    grid-template-columns: repeat(auto-fit, minmax(88px, 1fr));
    gap: .5rem;
    margin: .3rem 0 1rem;
}
.kpi {
    background: rgba(128, 128, 128, .08);
    border: 1px solid rgba(128, 128, 128, .18);
    border-radius: 12px;
    padding: .55rem .7rem;
}
.kpi-v { font-size: clamp(1.05rem, 3.4vw, 1.55rem); font-weight: 700; line-height: 1.15; }
.kpi-l { font-size: clamp(.62rem, 1.9vw, .78rem); opacity: .72; margin-top: .12rem; }

/* ---- tabela/mapa ocupam a largura e rolam se preciso ---- */
[data-testid="stDataFrame"] { width: 100%; }
[data-testid="stElementToolbar"] { display: none; }
</style>
"""


def aplicar() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

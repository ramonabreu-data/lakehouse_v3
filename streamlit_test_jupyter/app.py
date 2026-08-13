"""Ponto de entrada do painel SEMARH.

Responsabilidade minima: carregar config, aplicar o gate de autenticacao e
delegar todo o resto para o pacote `app_semarh` (uma aba por area). Toda a
logica do painel vive em `app_semarh/`.

Sobe sozinho com a stack: e o servico `dashboard` do docker-compose.yml
(mesma imagem do spark, entrypoint `streamlit run app.py` na porta 8501).
Nao precisa rodar nada a mao.

    docker compose up -d dashboard     # subir
    docker compose restart dashboard   # aplicar vars.env
    docker compose logs -f dashboard   # log

Acesse https://dashboard.localhost (via proxy).
"""

import streamlit as st
from dotenv import load_dotenv

from auth.authentication import require_auth
from app_semarh.estilo import aplicar as aplicar_estilo
from app_semarh.painel import render

load_dotenv("vars.env")

st.set_page_config(page_title="Painel SEMARH", layout="wide")

# Estilo responsivo (celular/tablet/desktop). Antes do login, cobre as 2 telas.
aplicar_estilo()

# Gate de autenticacao (Supabase). Devolve o usuario logado.
user = require_auth()

# Todo o painel (as 4 abas) vive em app_semarh.
render(user)

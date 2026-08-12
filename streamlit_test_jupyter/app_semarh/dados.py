"""Acesso ao Dremio (Arrow Flight) — conexao e consulta, com cache.

Compartilhado por todas as abas do painel.
"""

import os

import pandas as pd
import streamlit as st
from dremio_simple_query.connect import DremioConnection, get_token


@st.cache_resource
def conectar() -> DremioConnection:
    """Uma conexao por sessao do Streamlit (o cache evita reabrir a cada rerun)."""
    endpoint = os.getenv("DREMIO_ENDPOINT")
    token = get_token(
        uri=f"http://{endpoint}/apiv2/login",
        payload={
            "userName": os.getenv("DREMIO_USERNAME"),
            "password": os.getenv("DREMIO_PASSWORD"),
        },
    )
    return DremioConnection(token, f"grpc://{os.getenv('DREMIO_FLIGHT_ENDPOINT')}")


@st.cache_data(ttl=300, show_spinner="Consultando o Dremio...")
def consultar(sql: str) -> pd.DataFrame:
    """Resultado em cache por 5 minutos (evita reconsultar a cada interacao)."""
    return conectar().toPandas(sql)

"""Acesso ao Dremio (Arrow Flight) — conexao e consulta, com cache.

Compartilhado por todas as abas do painel.

O cache tem TTL de 5 min, mas a chave inclui o carimbo da ultima atualizacao
automatica (gravado pelo servico Celery em /estado/atualizacao.json). Assim o
dado novo aparece assim que o refinamento termina, sem esperar o TTL vencer — e
sem consultar o Dremio a cada rerun quando nada mudou.
"""

import json
import os
from pathlib import Path

import pandas as pd
import streamlit as st
from dremio_simple_query.connect import DremioConnection, get_token

ARQUIVO_ESTADO = Path(os.getenv("ARQUIVO_ESTADO", "/estado/atualizacao.json"))


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


def estado_atualizacao() -> dict:
    """Carimbo da ultima atualizacao automatica. Vazio se o serviço não rodou."""
    try:
        return json.loads(ARQUIVO_ESTADO.read_text())
    except Exception:
        return {}


@st.cache_data(ttl=300, show_spinner="Consultando o Dremio...")
def _consultar(sql: str, versao: str) -> pd.DataFrame:
    """Resultado em cache por 5 minutos, ou até o dado ser atualizado."""
    return conectar().toPandas(sql)


def consultar(sql: str) -> pd.DataFrame:
    return _consultar(sql, estado_atualizacao().get("atualizado_em", ""))

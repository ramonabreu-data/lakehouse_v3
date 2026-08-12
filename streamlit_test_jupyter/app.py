"""
Dashboard-modelo: le a camada de refinamento do lakehouse via Dremio (Arrow Flight).

Rode de dentro do container do Spark:

    docker compose exec -w /workspace/streamlit spark \
      streamlit run app.py --server.port 8501 --server.address 0.0.0.0

Acesse http://localhost:8502 (a 8501 e a porta interna do container).

O dashboard NAO transforma dado. Ele exibe o que os notebooks ja deixaram pronto em
nessie.refinamento.*. Agregacao e regra de negocio pertencem ao notebook 10_tratamento:
la ficam versionadas e reaproveitaveis, aqui virariam codigo de tela.
"""

import os

import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from dremio_simple_query.connect import DremioConnection, get_token

from auth.authentication import require_auth

# --------------------------------------------------------------------------
# Configuracao
# --------------------------------------------------------------------------

load_dotenv("vars.env")

# Tabela que alimenta a tela. Troque pela sua tabela do refinamento.
TABELA = "nessie.refinamento.clientes_por_dominio"
TITULO = "Clientes por domínio de e-mail"

st.set_page_config(page_title=TITULO, layout="wide")

# Gate de autenticacao (Supabase): para o run e mostra login/cadastro se preciso.
# Quem consulta o Dremio e a conta de servico do vars.env; o Supabase apenas
# controla quem pode acessar o painel.
user = require_auth()


# --------------------------------------------------------------------------
# Conexao e consulta
# --------------------------------------------------------------------------

@st.cache_resource
def conectar() -> DremioConnection:
    """Uma conexao por sessao do Streamlit. Sem o cache, cada rerun abriria outra."""
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
    """Resultado em cache por 5 minutos.

    Sem isso, cada interacao na tela (filtro, clique) refaz a consulta inteira.
    """
    return conectar().toPandas(sql)


# --------------------------------------------------------------------------
# Tela
# --------------------------------------------------------------------------

st.title(TITULO)

try:
    df = consultar(f"SELECT * FROM {TABELA}")
except Exception as erro:
    st.error(f"Falha ao consultar o Dremio: {erro}")
    st.caption(
        "Confira: a stack está no ar (`docker compose ps`), as credenciais em `vars.env` "
        f"estão corretas, e a tabela `{TABELA}` existe — rode o notebook `10_tratamento`."
    )
    st.stop()

if df.empty:
    st.warning(f"A tabela `{TABELA}` está vazia.")
    st.stop()

# --- filtros -------------------------------------------------------------
# Um multiselect por coluna de texto. Adapte para os filtros que fizerem sentido.
st.sidebar.header("Filtros")
filtrado = df.copy()
for coluna in df.select_dtypes(include="object").columns:
    opcoes = sorted(df[coluna].dropna().unique())
    if 1 < len(opcoes) <= 50:
        escolhido = st.sidebar.multiselect(coluna, opcoes, default=opcoes)
        filtrado = filtrado[filtrado[coluna].isin(escolhido)]

# --- indicadores ---------------------------------------------------------
numericas = filtrado.select_dtypes(include="number").columns.tolist()
colunas = st.columns(1 + len(numericas[:3]))
colunas[0].metric("Registros", f"{len(filtrado):,}".replace(",", "."))
for coluna_ui, nome in zip(colunas[1:], numericas[:3]):
    total = filtrado[nome].sum()
    coluna_ui.metric(f"Total de {nome}", f"{total:,.2f}".replace(",", "@").replace(".", ",").replace("@", "."))

st.divider()

# --- grafico e tabela ----------------------------------------------------
esquerda, direita = st.columns([2, 3])

with esquerda:
    st.subheader("Distribuição")
    categorias = filtrado.select_dtypes(include="object").columns.tolist()
    if categorias and numericas:
        eixo_x = st.selectbox("Categoria", categorias, key="eixo_x")
        eixo_y = st.selectbox("Medida", numericas, key="eixo_y")
        st.bar_chart(filtrado.groupby(eixo_x)[eixo_y].sum())
    else:
        st.caption("Sem par categoria/medida para gerar o gráfico.")

with direita:
    st.subheader("Dados")
    st.dataframe(filtrado, use_container_width=True, hide_index=True)
    st.download_button(
        "Baixar CSV",
        filtrado.to_csv(index=False).encode("utf-8"),
        file_name="dados.csv",
        mime="text/csv",
    )

st.caption(f"Fonte: `{TABELA}` — via Dremio Arrow Flight. Cache de 5 min.")

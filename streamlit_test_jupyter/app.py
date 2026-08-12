"""
Painel do Selo Ambiental 2026 (SEMARH-PI).

Le a camada de refinamento do lakehouse via Dremio (Arrow Flight) e monta o
painel: indicadores, distribuicao por tipo de selo e por criterios, mapa dos
municipios com selo e a tabela de pontuacao/resultado.

Rode de dentro do container do Spark:

    docker compose exec -w /workspace/streamlit spark \
      streamlit run app.py --server.port 8501 --server.address 0.0.0.0

Acesse https://dashboard.localhost (via proxy).

O painel NAO transforma dado: exibe o que o notebook
`semarh_painel/refinamento_selo_ambiental.ipynb` deixou pronto em
`nessie.refinamento.semarh_painel` (+ resumos).
"""

import os

import altair as alt
import pandas as pd
import streamlit as st
from dotenv import load_dotenv
from dremio_simple_query.connect import DremioConnection, get_token

from auth.authentication import require_auth

# --------------------------------------------------------------------------
# Configuracao
# --------------------------------------------------------------------------

load_dotenv("vars.env")

TABELA = "nessie.refinamento.semarh_painel"
TITULO = "Selo Ambiental 2026 — Piauí"

# Selo A/B/C e ordinal (A melhor -> C): rampa sequencial de verde (ColorBrewer
# Greens, segura para daltonismo, a ordem vem da luminosidade). Situacoes
# negativas em cinza, claramente separaveis dos verdes.
COR_SELO = {"A": "#1a9850", "B": "#66bd63", "C": "#a6d96a"}
ORDEM_RESULTADO = ["Selo A", "Selo B", "Selo C", "Não elegível", "Não habilitado"]
COR_RESULTADO = ["#1a9850", "#66bd63", "#a6d96a", "#9e9e9e", "#616161"]

st.set_page_config(page_title=TITULO, layout="wide")

# Gate de autenticacao (Supabase): para o run e mostra login se preciso.
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
    """Resultado em cache por 5 minutos (evita reconsultar a cada interacao)."""
    return conectar().toPandas(sql)


# --------------------------------------------------------------------------
# Dados
# --------------------------------------------------------------------------

st.title(TITULO)
st.caption("SEMARH · resultado final por município (edição 2026)")

try:
    df = consultar(f"SELECT * FROM {TABELA}")
except Exception as erro:
    st.error(f"Falha ao consultar o Dremio: {erro}")
    st.caption(
        "Confira: a stack está no ar, as credenciais em `vars.env` estão corretas, e a tabela "
        f"`{TABELA}` existe — rode o notebook `semarh_painel/refinamento_selo_ambiental`."
    )
    st.stop()

if df.empty:
    st.warning(f"A tabela `{TABELA}` está vazia.")
    st.stop()

df["tem_selo"] = df["tem_selo"].astype(bool)
df["criterios_atendidos"] = pd.to_numeric(df["criterios_atendidos"], errors="coerce")

# --------------------------------------------------------------------------
# Filtros
# --------------------------------------------------------------------------

st.sidebar.header("Filtros")
territorios = sorted(df["territorio_desenvolvimento"].dropna().unique())
sel_terr = st.sidebar.multiselect("Território de desenvolvimento", territorios, default=territorios)
situacoes = sorted(df["situacao"].dropna().unique())
sel_sit = st.sidebar.multiselect("Situação", situacoes, default=situacoes)

f = df[df["territorio_desenvolvimento"].isin(sel_terr) & df["situacao"].isin(sel_sit)].copy()
if f.empty:
    st.warning("Nenhum município para os filtros selecionados.")
    st.stop()

# --------------------------------------------------------------------------
# Indicadores
# --------------------------------------------------------------------------

k = st.columns(6)
k[0].metric("Municípios", len(f))
k[1].metric("Com selo", int(f["tem_selo"].sum()))
k[2].metric("Selo A", int((f["selo"] == "A").sum()))
k[3].metric("Selo B", int((f["selo"] == "B").sum()))
k[4].metric("Selo C", int((f["selo"] == "C").sum()))
k[5].metric("Não elegíveis / não hab.", int(f["situacao"].isin(["Não elegível", "Não habilitado"]).sum()))

st.divider()

# --------------------------------------------------------------------------
# Distribuicoes
# --------------------------------------------------------------------------

esq, dir = st.columns(2)

with esq:
    st.subheader("Municípios por tipo de selo")
    por_selo = (
        f.groupby("resultado").size().reindex(ORDEM_RESULTADO).dropna()
        .reset_index(name="municipios")
    )
    grafico_selo = (
        alt.Chart(por_selo)
        .mark_bar(cornerRadiusEnd=4)
        .encode(
            x=alt.X("municipios:Q", title="municípios"),
            y=alt.Y("resultado:N", sort=ORDEM_RESULTADO, title=None),
            color=alt.Color(
                "resultado:N",
                scale=alt.Scale(domain=ORDEM_RESULTADO, range=COR_RESULTADO),
                legend=None,
            ),
            tooltip=[alt.Tooltip("resultado:N", title="resultado"),
                     alt.Tooltip("municipios:Q", title="municípios")],
        )
        .properties(height=260)
    )
    st.altair_chart(grafico_selo, use_container_width=True)

with dir:
    st.subheader("Municípios por critérios atendidos")
    hab = f.dropna(subset=["criterios_atendidos"]).copy()
    hab["criterios_atendidos"] = hab["criterios_atendidos"].astype(int)
    por_crit = hab.groupby("criterios_atendidos").size().reset_index(name="municipios")
    grafico_crit = (
        alt.Chart(por_crit)
        .mark_bar(cornerRadiusEnd=4, color="#1a9850")
        .encode(
            x=alt.X("criterios_atendidos:O", title="critérios atendidos"),
            y=alt.Y("municipios:Q", title="municípios"),
            tooltip=[alt.Tooltip("criterios_atendidos:O", title="critérios"),
                     alt.Tooltip("municipios:Q", title="municípios")],
        )
        .properties(height=260)
    )
    st.altair_chart(grafico_crit, use_container_width=True)

st.divider()

# --------------------------------------------------------------------------
# Mapa dos municipios com selo
# --------------------------------------------------------------------------

st.subheader("Mapa — municípios com selo ambiental")
com_selo = f[f["tem_selo"]].dropna(subset=["latitude", "longitude"]).copy()
if com_selo.empty:
    st.caption("Nenhum município com selo nos filtros atuais.")
else:
    com_selo["_cor"] = com_selo["selo"].map(COR_SELO)
    st.map(com_selo, latitude="latitude", longitude="longitude", color="_cor", size=600)
    legenda = "  ".join(
        f"<span style='color:{COR_SELO[s]};font-size:18px'>●</span> Selo {s}"
        for s in ["A", "B", "C"]
    )
    st.markdown(f"**Legenda:** {legenda}", unsafe_allow_html=True)

st.divider()

# --------------------------------------------------------------------------
# Pontuacao e resultado
# --------------------------------------------------------------------------

st.subheader("Pontuação e resultado dos municípios")
tabela = (
    f[["municipio", "resultado", "pontos", "criterios_atendidos",
       "territorio_desenvolvimento", "pacto_ambiental"]]
    .sort_values("pontos", ascending=False, na_position="last")
    .reset_index(drop=True)
)
st.dataframe(
    tabela,
    use_container_width=True,
    hide_index=True,
    column_config={
        "municipio": "Município",
        "resultado": "Resultado",
        "pontos": st.column_config.NumberColumn("Pontos", format="%.1f"),
        "criterios_atendidos": st.column_config.NumberColumn("Critérios", format="%d"),
        "territorio_desenvolvimento": "Território",
        "pacto_ambiental": st.column_config.CheckboxColumn("Pacto ambiental"),
    },
)
st.download_button(
    "Baixar CSV",
    tabela.to_csv(index=False).encode("utf-8"),
    file_name="selo_ambiental_2026.csv",
    mime="text/csv",
)

st.caption(f"Fonte: `{TABELA}` — via Dremio Arrow Flight. Cache de 5 min.")

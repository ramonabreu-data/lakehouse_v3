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
    border-left: 4px solid rgba(128, 128, 128, .45);
    border-radius: 12px;
    padding: .55rem .7rem;
}
.kpi-v { font-size: clamp(1.05rem, 3.4vw, 1.55rem); font-weight: 700; line-height: 1.15; }
.kpi-l { font-size: clamp(.62rem, 1.9vw, .78rem); opacity: .72; margin-top: .12rem; }

/* Cor por SIGNIFICADO, não por enfeite: a mesma paleta dos gráficos e do mapa,
   para o cartão e o ponto no mapa dizerem a mesma coisa. A faixa colorida fica
   na borda e o número herda a cor; o fundo continua quase neutro, senão três
   blocos coloridos disputariam a atenção com o próprio dado.
     azul  = volume/contagem (a mesma cor das barras)
     verde = já aconteceu     (o "Visitado" do mapa)
     âmbar = ainda falta      (pendência, não erro — por isso não é vermelho) */
/* Todas as cores saem da MESMA paleta categórica do mapa (`mapa.CATEGORICAS`),
   por isso conversam entre si e com o resto da tela. São matizes bem separados
   — e não tons de um mesmo cinza —, para o olho distinguir um cartão do outro
   de longe. */
.kpi-azul     { border-left-color: #4269d0; background: rgba(66, 105, 208, .08); }
.kpi-verde    { border-left-color: #3ca951; background: rgba(60, 169, 81, .09); }
.kpi-ambar    { border-left-color: #f4901e; background: rgba(244, 144, 30, .09); }
.kpi-roxo     { border-left-color: #a463f2; background: rgba(164, 99, 242, .09); }
.kpi-turquesa { border-left-color: #12a5b3; background: rgba(18, 165, 179, .09); }
.kpi-vermelho { border-left-color: #e45756; background: rgba(228, 87, 86, .09); }
.kpi-cinza    { border-left-color: #9e9e9e; background: rgba(128, 128, 128, .07); }
.kpi-azul     .kpi-v { color: #4269d0; }
.kpi-verde    .kpi-v { color: #3ca951; }
.kpi-ambar    .kpi-v { color: #f4901e; }
.kpi-roxo     .kpi-v { color: #a463f2; }
.kpi-turquesa .kpi-v { color: #12a5b3; }
.kpi-vermelho .kpi-v { color: #e45756; }
.kpi-cinza    .kpi-v { color: #9e9e9e; }
/* a barra de progresso conta a mesma coisa que o cartão verde: use a cor dele */
[data-testid="stProgress"] div[role="progressbar"] > div > div { background-color: #3ca951; }

/* ---- legenda do mapa (chips categoricos ou barra de gradiente) ---- */
.legenda {
    display: flex;
    flex-wrap: wrap;
    align-items: center;
    gap: .3rem .8rem;
    font-size: clamp(.7rem, 1.9vw, .82rem);
    margin: .45rem 0 .2rem;
}
.legenda .leg-item { display: inline-flex; align-items: center; gap: .32rem; white-space: nowrap; }
.legenda .leg-item i {
    width: .72rem;
    height: .72rem;
    border-radius: 50%;
    border: 1px solid rgba(255, 255, 255, .75);
    box-shadow: 0 0 0 1px rgba(0, 0, 0, .12);
}
.legenda .leg-barra {
    display: inline-block;
    width: clamp(90px, 22vw, 190px);
    height: .55rem;
    border-radius: 4px;
    border: 1px solid rgba(128, 128, 128, .35);
}
.legenda .leg-min, .legenda .leg-max { opacity: .75; }

/* ---- filtros: um botao que resume, a lista so quando pedida ----
   Os filtros sao o contorno da leitura, nao o conteudo: ficam fechados num
   popover (ver `filtros.py`), e por fora aparece so `Território · 3 de 12`.
   O botao e neutro de proposito — quem carrega cor na tela e o dado. */
[data-testid="stPopover"] > button {
    border: 1px solid rgba(128, 128, 128, .35);
    border-radius: 10px;
    background: rgba(128, 128, 128, .06);
    font-weight: 500;
    justify-content: space-between;   /* o resumo encosta na setinha */
    text-align: left;
    padding: .34rem .7rem;
}
[data-testid="stPopover"] > button:hover { border-color: rgba(66, 105, 208, .6); }
/* dentro do popover: caixas compactas, para 12 opcoes caberem sem rolagem */
[data-testid="stPopoverBody"] [data-testid="stCheckbox"] { margin-bottom: -.35rem; }
[data-testid="stPopoverBody"] [data-testid="stCheckbox"] label { font-size: .82rem; }
[data-testid="stPopoverBody"] [data-testid="stCaptionContainer"] { margin-bottom: .2rem; }
[data-testid="stPopoverBody"] [data-testid="stForm"] { padding: 0; max-width: none; border: none; }

/* rotulo de widget: presente, sem competir com os titulos da tela */
[data-testid="stWidgetLabel"] p {
    font-size: clamp(.72rem, 1.9vw, .82rem);
    opacity: .78;
    margin-bottom: .12rem;
}
/* etiqueta do multiselect (busca de listas longas): discreta, e o campo nunca
   cresce sem limite — a partir de ~3 linhas ele rola por dentro */
[data-testid="stMultiSelect"] [data-baseweb="tag"] {
    background: rgba(66, 105, 208, .15) !important;
    color: inherit !important;
    border: 1px solid rgba(66, 105, 208, .3);
    border-radius: 8px;
    height: auto;
    min-height: 0;
    padding: .05rem .12rem .05rem .4rem;
    font-size: clamp(.68rem, 1.8vw, .78rem);
    max-width: 13rem;
}
[data-testid="stMultiSelect"] [data-baseweb="tag"] svg { opacity: .55; }
[data-testid="stMultiSelect"] [data-baseweb="tag"]:hover svg { opacity: 1; }
[data-testid="stMultiSelect"] [data-baseweb="select"] > div:first-child {
    max-height: 4.9rem;
    overflow-y: auto;
}

/* ---- tabela completa: mostra TODAS as linhas e o texto inteiro ----
   O `st.dataframe` corta o texto que nao cabe na celula e rola por dentro num
   quadro de altura fixa. Quando a tabela E o conteudo (a lista de acoes, por
   exemplo), isso esconde justamente o que se quer ler: aqui a celula quebra a
   linha e quem rola e a pagina. O cabecalho gruda no topo para nao se perder a
   referencia da coluna numa lista longa. */
.tabela-completa {
    border: 1px solid rgba(128, 128, 128, .22);
    border-radius: 12px;
    background: rgba(128, 128, 128, .025);
    margin-bottom: .6rem;
}
.tabela-completa table { width: 100%; border-collapse: collapse; }
.tabela-completa th, .tabela-completa td {
    font-size: clamp(.72rem, 1.9vw, .86rem);
    text-align: left;
    padding: .45rem .6rem;
    line-height: 1.35;
}
.tabela-completa th {
    position: sticky;
    top: 0;
    z-index: 1;
    font-weight: 600;
    white-space: nowrap;
    /* opaco de proposito: o cabecalho fica por cima das linhas que passam
       por baixo dele ao rolar a pagina */
    background: rgba(148, 148, 148, .28);
    backdrop-filter: blur(6px);
}
.tabela-completa td {
    vertical-align: top;
    border-top: 1px solid rgba(128, 128, 128, .16);
    word-break: break-word;
}
.tabela-completa tbody tr:nth-child(even) { background: rgba(128, 128, 128, .06); }
.tabela-completa td.data, .tabela-completa td.num { white-space: nowrap; }
.tabela-completa td.num { text-align: right; font-variant-numeric: tabular-nums; }
.tabela-completa td.nome { font-weight: 500; }
/* barra proporcional dentro da celula (comparacao sem ler numero por numero).
   O trilho ocupa a sobra da celula e a barra e uma fracao DELE — sem o trilho,
   a largura em % nao teria referencia estavel e cada linha mediria diferente. */
.tabela-completa .barra { display: flex; align-items: center; gap: .45rem; }
.tabela-completa .barra .trilho {
    flex: 1;
    display: block;
    height: .5rem;
    min-width: 2.5rem;
    border-radius: 3px;
    background: rgba(128, 128, 128, .2);
}
.tabela-completa .barra i {
    display: block;
    height: 100%;
    min-width: 2px;
    border-radius: 3px;
    background: #4269d0;
}
.tabela-completa .barra > span {
    flex: 0 0 auto;
    min-width: 1.8rem;
    text-align: right;
    font-variant-numeric: tabular-nums;
    opacity: .85;
}

/* ---- tabela/mapa ocupam a largura e rolam se preciso ---- */
[data-testid="stDataFrame"] { width: 100%; }
[data-testid="stElementToolbar"] { display: none; }

/* ---- moldura fina em cada visual (grafico, mapa, tabela) ----
   Uma linha de 1px em cinza translucido: funciona no tema claro e no escuro
   sem precisar de duas paletas. O titulo fica FORA da moldura, acima dela,
   como no painel de origem. */
[data-testid="stVegaLiteChart"],
[data-testid="stDeckGlJsonChart"],
[data-testid="stDataFrame"],
.stVegaLiteChart,
.stDeckGlJsonChart,
.stDataFrame {
    border: 1px solid rgba(128, 128, 128, .22);
    border-radius: 12px;
    padding: .55rem;
    background: rgba(128, 128, 128, .025);
    /* o mapa e desenhado em canvas: sem isto ele vaza os cantos arredondados */
    overflow: hidden;
}
/* a tabela ja desenha a propria borda interna — nao precisa de respiro extra */
[data-testid="stDataFrame"], .stDataFrame { padding: 0; }
</style>
"""


def aplicar() -> None:
    st.markdown(_CSS, unsafe_allow_html=True)

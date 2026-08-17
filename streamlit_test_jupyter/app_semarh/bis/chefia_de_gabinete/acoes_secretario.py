"""BI Ações do Secretário — aba da Chefia de Gabinete.

Le as views curadas do space `refinamento` (via Dremio Arrow Flight) e monta a
tela da agenda do Secretário: quantas ações, quantas cidades foram visitadas (e
quantas faltam), onde elas estão no mapa e a lista das ações. Não transforma
dado — isso é feito no notebook `semarh_painel/refinamento_acoes_secretario`.

Layout espelhado no painel de origem da SEMARH: os mesmos três cartões (ações,
cidades visitadas com o percentual, cidades não visitadas), o mesmo mapa das
ações colorido por território e a mesma tabela-resumo (data, município,
território, ação), da mais recente para a mais antiga. O que o painel
acrescenta: filtro por ano e mês (lá são botões), o recorte por pacto, o
seletor do que colore o mapa e o CSV do que está na tela.

Mapa e tabela ficam **lado a lado**, como no painel de origem. A tabela é
desenhada em HTML (`app_semarh/tabela.py`), não com `st.dataframe`: ele CORTA o
texto que não cabe na célula, que é justamente a descrição da ação. Em HTML a
célula quebra a linha e **todas as linhas do recorte são renderizadas** — o
quadro tem a altura do mapa e rola por dentro, com o cabeçalho grudado no topo.
O interruptor **Largura inteira** manda a tabela para baixo do mapa, ocupando a
página e sem limite de altura. O preço do HTML é não ordenar clicando no
cabeçalho, e por isso a ordem virou um seletor explícito ao lado da busca.

São três visões do mesmo recorte: as **ações** (o que foi feito e quando), o
resumo **por município** (onde já se foi, quantas vezes e há quanto tempo) e os
municípios **sem ação** (o complemento do cartão "cidades não visitadas").

**Clicar num município do mapa** mostra na tabela ao lado só as ações dele —
é o atalho de quem olha o mapa e pergunta "o que foi feito ALI?". O resto da
tela (cartões, gráfico, o próprio mapa) não se move: é isso que permite
comparar aquele município com o recorte inteiro. O botão **Ver todos** desfaz.

O gráfico **Ações por mês** é o elo entre as partes: clicar numa barra recorta
os cartões, o mapa e a tabela naquele mês (Ctrl+clique escolhe vários). O
gráfico em si continua mostrando a série inteira — ele é o contexto, quem se
move é o resto da tela. Por isso os cartões são desenhados num container
reservado ANTES do gráfico, mas preenchidos DEPOIS de ler o clique.

**Agenda política entra ou não?** A origem publica as duas listas — com e sem as
ações de agenda política — e o refinamento as junta numa tabela só, marcando a
coluna `agenda_politica`. Aqui isso vira um interruptor: desligado, some tanto
das ações quanto da conta de cidades visitadas (é por isso que a cidade visitada
é recalculada do fato, e não lida pronta da dimensão).

O painel de origem tem ainda um filtro por **órgão**, que não existe aqui: a
planilha de ações não traz essa coluna. Quando a origem passar a trazê-la, o
filtro entra junto do de território.
"""

import altair as alt
import pandas as pd
import streamlit as st

from app_semarh import graficos, mapa, tabela as tab
from app_semarh.dados import consultar, estado_atualizacao
from app_semarh.filtros import multiselect_opcional_url, multiselect_url, selectbox_url

# Prefixo de toda chave de widget e de URL desta aba (a mesma convencao do Selo
# Ambiental: sem isso as abas dividiriam estado na sessao).
SLUG = "acoessec"

PASTA = "refinamento.semarh_painel.chefia_gabinete.acoes_secretario"
FONTE_ACOES = f"{PASTA}.acoes"
FONTE_MUNICIPIOS = f"{PASTA}.municipios"
NOTEBOOK = "semarh_painel/refinamento_acoes_secretario"

MESES = ["Jan", "Fev", "Mar", "Abr", "Mai", "Jun",
         "Jul", "Ago", "Set", "Out", "Nov", "Dez"]

# As tres visoes da tabela-resumo — o mesmo recorte, tres perguntas diferentes.
VISOES_TABELA = {
    "acoes": "Ações",
    "municipios": "Por município",
    "sem": "Sem ação",
}

# Ordenacao de cada visao -> (coluna, crescente). A tabela e desenhada em HTML
# para caber inteira na tela (ver `app_semarh/tabela.py`), e HTML nao ordena ao clicar
# no cabecalho como o `st.dataframe` — daí a ordem virar um seletor explicito.
ORDENS_ACOES = {
    "Mais recentes": ("data", False),
    "Mais antigas": ("data", True),
    "Município (A–Z)": ("municipio", True),
    "Território": ("territorio", True),
}
ORDENS_MUNICIPIOS = {
    "Mais ações": ("acoes", False),
    "Última visita": ("ultima", False),
    "Município (A–Z)": ("municipio", True),
}
ORDENS_SEM_ACAO = {
    "Território": ("territorio", True),
    "Município (A–Z)": ("municipio", True),
    "Maior população": ("populacao", False),
}

# Recorte por adesao ao Pacto pelo Piaui (o filtro "Pactos pelo Piauí" do painel
# de origem). Valor -> filtro aplicado a coluna `aderente_pacto`.
PACTOS = {"todos": "Todos os municípios",
          "sim": "Só os aderentes ao pacto",
          "nao": "Só os não aderentes"}

# Parametro que colore o mapa -> (coluna, tipo de escala).
MODOS_MAPA = {
    "Território": ("territorio", "categoria"),
    "Nº de ações": ("acoes", "numero"),
    "Visita do secretário": ("visitado", "booleano"),
}

TOOLTIP = (
    "<b>{municipio}</b><br/>{territorio}<br/>"
    "{acoes} ação(ões)<br/>última: {ultima_br}"
)


def _frescor() -> str:
    """Quando o serviço de atualização automática (Celery) rodou pela última vez."""
    estado = estado_atualizacao()
    carimbo = estado.get("atualizado_em")
    if not carimbo:
        return "Atualização automática ainda não executou (serviço `celery-worker`)."
    quando = carimbo.replace("T", " ")[:16]
    intervalo = estado.get("intervalo_min")
    a_cada = f" · atualiza a cada {int(intervalo)} min" if intervalo else ""
    return f"Última atualização automática: {quando}{a_cada}."


def _erro(fonte: str, erro: Exception) -> None:
    st.error(f"Falha ao consultar o Dremio: {erro}")
    st.caption(
        "Confira: a stack está no ar, as credenciais em `vars.env` estão corretas, e a view "
        f"`{fonte}` existe. Uma carga completa resolve os dois últimos casos — ela publica as "
        f"tabelas (notebook `{NOTEBOOK}`) **e** recria as views; use o botão **Atualizar dados "
        "agora** na barra lateral."
    )


def _selecionados(evento, parametro: str, campo: str) -> list[str]:
    """Valores clicados no gráfico Altair interativo.

    O payload do Streamlit varia com a versao: pode vir como lista de registros
    (`[{"_mes": "2026-08"}]`) ou como dicionario de listas
    (`{"_mes": ["2026-08"]}`). Aceita os dois e sempre devolve strings.
    """
    selecao = getattr(evento, "selection", None) or {}
    bruto = selecao.get(parametro) or []
    if isinstance(bruto, dict):
        return [str(v) for v in bruto.get(campo, [])]
    return [str(item[campo]) for item in bruto if isinstance(item, dict) and campo in item]


def _limpar_selecao() -> None:
    """Zera o clique no gráfico.

    O estado de evento de um grafico e read-only no Streamlit — nao da para
    apagar direto. O jeito que funciona e trocar a CHAVE do widget: com chave
    nova, o grafico nasce sem selecao. Este contador entra na chave.
    """
    chave = f"_reset_grafico_{SLUG}"
    st.session_state[chave] = st.session_state.get(chave, 0) + 1


def _chave_grafico(*filtros) -> str:
    """Chave do gráfico: muda quando muda um filtro ou o botão de limpar.

    Sem isso o mes clicado sobrevive a troca de filtro — o mes escolhido pode
    nem existir no novo recorte, e cartoes, mapa e tabela passariam a mostrar
    algo que o grafico acima nao mostra.
    """
    assinatura = abs(hash(tuple(tuple(sorted(map(str, x))) for x in filtros)))
    return f"{assinatura}_{st.session_state.get(f'_reset_grafico_{SLUG}', 0)}"


def _por_municipio(acoes: pd.DataFrame, municipios: pd.DataFrame) -> pd.DataFrame:
    """Uma linha por município do recorte, com a contagem de ações do recorte.

    Parte da lista de municípios (nao das acoes) porque o mapa e a conta de
    "não visitadas" precisam mostrar tambem quem ficou com zero.
    """
    resumo = acoes.groupby("cod_ibge").agg(
        acoes=("acao", "size"), ultima=("data", "max")
    )
    base = municipios.merge(resumo, on="cod_ibge", how="left")
    base["acoes"] = base["acoes"].fillna(0).astype(int)
    base["visitado"] = base["acoes"] > 0
    return base


def _desenhar_mapa(geo: pd.DataFrame, modo: str, pertencimento: dict[int, str], chave: str):
    """Mapa das ações: a cor conta o parâmetro escolhido, o tamanho, quantas ações.

    Devolve o evento do mapa — e por ele que chega o municipio clicado.
    """
    coluna, tipo = MODOS_MAPA[modo]
    geo = geo.copy()
    geo["_raio"] = mapa.raio_por_valor(geo["acoes"])
    geo["ultima_br"] = pd.to_datetime(geo["ultima"]).dt.strftime("%d/%m/%Y").fillna("—")

    if tipo == "numero":
        cores, vmin, vmax = mapa.sequencial(geo[coluna])
        geo["_rgb"] = cores
        evento = mapa.pontos(geo, "_rgb", TOOLTIP, raio_m="_raio",
                             base=mapa.contexto(pertencimento), chave=chave)
        mapa.legenda_gradiente(vmin, vmax, modo, casas=0)
        return evento

    if tipo == "booleano":
        rotulos = geo[coluna].map({True: "Visitado", False: "Não visitado"})
        cores = {"Visitado": "#3ca951", "Não visitado": "#9e9e9e"}
    else:
        rotulos = geo[coluna].fillna("Sem informação")
        cores = mapa.paleta(sorted(rotulos.unique()))

    geo["_rgb"] = [mapa.hex_rgb(cores.get(v, "#9e9e9e")) for v in rotulos]
    # Só quando o mapa JÁ colore por território as áreas recebem a cor da
    # legenda; nos outros modos ficam neutras para não disputar significado.
    cores_area = cores if coluna == "territorio" else None
    evento = mapa.pontos(geo, "_rgb", TOOLTIP, raio_m="_raio",
                         base=mapa.contexto(pertencimento, cores_area), chave=chave)
    mapa.legenda_categorias(cores, modo)
    return evento


def _bloco_mapa(por_municipio: pd.DataFrame, municipios: pd.DataFrame) -> dict | None:
    """O mapa das ações com os seus dois controles.

    Devolve o municipio clicado (a linha inteira) ou None. O clique e o atalho
    natural de quem olha o mapa: "o que foi feito ALI?" — e a resposta e a
    tabela ao lado, que passa a mostrar so aquele municipio.
    """
    st.markdown("**Mapa das ações**")
    geo = por_municipio.dropna(subset=["latitude", "longitude"])
    # Padrão do painel de origem: o mapa mostra onde houve ação. Desligue
    # para ver também os municípios sem nenhuma no recorte.
    c_modo, c_so = st.columns([2, 1])
    modo = c_modo.selectbox("Colorir por", list(MODOS_MAPA), key=f"mapa_cor_{SLUG}")
    so_visitados = c_so.toggle("Só com ações", value=True, key=f"mapa_visita_{SLUG}")
    if so_visitados:
        geo = geo[geo["visitado"]]
    if geo.empty:
        st.caption("Nenhum município com coordenadas nos filtros atuais.")
        return None
    # O sombreado dos territórios é contexto geográfico: vem de TODOS os
    # municípios, não só dos filtrados, senão o estado apareceria pela metade
    # sempre que um filtro estivesse ativo.
    pertencimento = {int(c): t for c, t in zip(municipios["cod_ibge"],
                                               municipios["territorio"])}
    # A chave carrega o contador de "limpar": trocá-la faz o mapa renascer sem
    # seleção — o estado do clique é read-only, não dá para apagá-lo direto.
    chave = f"mapa_{SLUG}_{st.session_state.get(f'_reset_mapa_{SLUG}', 0)}"
    return mapa.municipio_clicado(_desenhar_mapa(geo, modo, pertencimento, chave))


def _limpar_mapa() -> None:
    """Zera o clique no mapa (a chave nova faz o mapa nascer sem seleção)."""
    chave = f"_reset_mapa_{SLUG}"
    st.session_state[chave] = st.session_state.get(chave, 0) + 1


def _tabela_resumo(acoes: pd.DataFrame, por_municipio: pd.DataFrame,
                   clicado: dict | None = None) -> None:
    """A tabela do painel de origem, em três visões do mesmo recorte.

    A lista de ações responde "o que foi feito e quando"; o resumo por município
    responde "onde já se foi e há quanto tempo" — a mesma pergunta que os
    cartões fazem, agora município a município; e a terceira diz QUAIS cidades
    ainda não receberam ação, que é a pergunta seguinte de quem monta a agenda.
    A busca vale para a visão aberta e o CSV baixa exatamente o que está na tela.

    `clicado` e o municipio escolhido no mapa: a tabela passa a mostrar so as
    acoes dele — e o resto da tela (cartoes, grafico, mapa) fica como esta, que
    e o que da para comparar "este municipio" com "o recorte todo".

    Fica ao lado do mapa, como no painel de origem, então o quadro tem a altura
    dele e rola por dentro: todas as linhas estão renderizadas e nenhum texto é
    cortado — a coluna larga quebra a linha. O botão **Altura total** solta essa
    altura para quem prefere a lista inteira aberta, com a página rolando.
    """
    st.markdown("**Tabela resumo das ações e visitas**")
    if clicado and clicado.get("cod_ibge") is not None:
        codigo = int(clicado["cod_ibge"])
        acoes = acoes[acoes["cod_ibge"] == codigo]
        por_municipio = por_municipio[por_municipio["cod_ibge"] == codigo]
        c_txt, c_btn = st.columns([3, 1])
        c_txt.caption(f"📍 **{clicado.get('municipio', 'Município')}** — "
                      f"{len(acoes)} ação(ões) no recorte atual.")
        c_btn.button("Ver todos", on_click=_limpar_mapa, key=f"limpar_mapa_{SLUG}",
                     width='stretch')
    visao = st.segmented_control(
        "Visão", list(VISOES_TABELA), format_func=VISOES_TABELA.get,
        default="acoes", key=f"tabela_visao_{SLUG}", label_visibility="collapsed",
    ) or "acoes"
    c_ordem, c_busca = st.columns([2, 3])
    busca = c_busca.text_input(
        "Buscar", key=f"tabela_busca_{SLUG}", label_visibility="collapsed",
        placeholder="Buscar por município, território ou ação…",
    )
    altura = None if tab.interruptor_largura(SLUG) else tab.ALTURA_AO_LADO_DO_MAPA

    if visao == "acoes":
        tabela = tab.buscar(acoes[["data", "municipio", "territorio", "acao"]],
                            ["municipio", "territorio", "acao"], busca)
        tabela = tab.ordenar(tabela, ORDENS_ACOES, f"acoes_{SLUG}", c_ordem)
        st.caption(f"Todas as {len(tabela)} ação(ões) do recorte, em "
                   f"{tabela['municipio'].nunique()} município(s).")
        tab.completa(tabela, [
            ("data", "Data", "data"),
            ("municipio", "Município", "nome"),
            ("territorio", "Território", "texto"),
            ("acao", "Ação", "texto"),
        ], altura)
        tab.baixar(tabela, "acoes_secretario_acoes", f"acoes_{SLUG}")
        return

    if visao == "municipios":
        resumo = (
            acoes.groupby(["municipio", "territorio"])
            .agg(acoes=("acao", "size"), primeira=("data", "min"), ultima=("data", "max"))
            .reset_index()
        )
        resumo = tab.ordenar(tab.buscar(resumo, ["municipio", "territorio"], busca),
                             ORDENS_MUNICIPIOS, f"municipios_{SLUG}", c_ordem)
        st.caption(f"{len(resumo)} município(s) visitado(s) no recorte.")
        tab.completa(resumo, [
            ("municipio", "Município", "nome"),
            ("territorio", "Território", "texto"),
            ("acoes", "Ações", "barra"),
            ("primeira", "1ª visita", "data"),
            ("ultima", "Última visita", "data"),
        ], altura)
        tab.baixar(resumo, "acoes_secretario_por_municipio", f"municipios_{SLUG}")
        return

    # Sem ação no recorte — o complemento do cartão "cidades não visitadas".
    sem_acao = tab.ordenar(
        tab.buscar(por_municipio[~por_municipio["visitado"]]
                   [["municipio", "territorio", "populacao", "aderente_pacto"]]
                   .sort_values("municipio"),
                   ["municipio", "territorio"], busca),
        ORDENS_SEM_ACAO, f"sem_acao_{SLUG}", c_ordem,
    )
    if sem_acao.empty:
        st.caption("Nenhum município ficou sem ação neste recorte.")
        return
    st.caption(f"{len(sem_acao)} município(s) sem nenhuma ação no recorte.")
    tab.completa(sem_acao, [
        ("municipio", "Município", "nome"),
        ("territorio", "Território", "texto"),
        ("populacao", "População", "num"),
        ("aderente_pacto", "Aderente ao pacto", "sim_nao"),
    ], altura)
    tab.baixar(sem_acao, "acoes_secretario_sem_acao", f"sem_acao_{SLUG}")


def render(user: dict | None = None) -> None:
    """Desenha a aba inteira das Ações do Secretário."""
    try:
        acoes = consultar(f"SELECT * FROM {FONTE_ACOES}")
        municipios = consultar(f"SELECT * FROM {FONTE_MUNICIPIOS}")
    except Exception as erro:
        _erro(FONTE_ACOES, erro)
        return

    if acoes.empty or municipios.empty:
        st.warning(f"As views de `{PASTA}` estão vazias.")
        return

    acoes["data"] = pd.to_datetime(acoes["data"])
    acoes["agenda_politica"] = acoes["agenda_politica"].astype(bool)
    municipios["aderente_pacto"] = municipios["aderente_pacto"].astype(bool)

    st.subheader("Ações do Secretário — Piauí")

    # --- filtros (persistem no refresh via URL) --------------------------
    c_terr, c_mun, c_pacto = st.columns(3)
    territorios = sorted(municipios["territorio"].dropna().unique())
    sel_terr = multiselect_url("Território", territorios, f"{SLUG}_terr", c_terr)
    sel_mun = multiselect_opcional_url(
        "Município", sorted(municipios["municipio"].dropna().unique()), f"{SLUG}_mun", c_mun,
        ajuda="Sem nada marcado, entram todos. Escolha um ou vários para comparar.",
    )
    pacto = selectbox_url("Pactos pelo Piauí", list(PACTOS), f"{SLUG}_pacto", c_pacto,
                          padrao="todos", formato=PACTOS.get,
                          ajuda="Recorta pelos municípios que aderiram aos Pactos pelo Piauí.")

    c_ano, c_mes, c_ag = st.columns([1, 2, 1])
    # Ano e mês entram como texto porque é assim que o filtro vai para a URL
    # (o estado é serializado com "|"); a conversão de volta é logo abaixo.
    anos = [str(a) for a in sorted(acoes["data"].dt.year.unique())]
    sel_ano = multiselect_url("Ano", anos, f"{SLUG}_ano", c_ano)
    sel_mes = multiselect_url("Mês", MESES, f"{SLUG}_mes", c_mes)
    with c_ag:
        com_agenda = st.toggle(
            "Incluir agenda política", value=True, key=f"{SLUG}_agenda",
            help="A origem publica as ações em duas listas, com e sem agenda política. "
                 "Desligue para ver só o restante da agenda — as cidades visitadas são "
                 "recontadas junto.",
        )

    # --- recorte ---------------------------------------------------------
    universo = municipios[municipios["territorio"].isin(sel_terr)]
    if sel_mun:
        universo = universo[universo["municipio"].isin(sel_mun)]
    if pacto != "todos":
        universo = universo[universo["aderente_pacto"] == (pacto == "sim")]

    f = acoes[acoes["cod_ibge"].isin(universo["cod_ibge"])]
    if not com_agenda:
        f = f[~f["agenda_politica"]]
    meses = [MESES.index(m) + 1 for m in sel_mes]
    f = f[f["data"].dt.year.astype(str).isin(sel_ano) & f["data"].dt.month.isin(meses)]

    if universo.empty:
        st.warning("Nenhum município para os filtros selecionados.")
        return

    if f.empty:
        st.warning("Nenhuma ação nos filtros selecionados.")
        return

    # Os cartões ficam no topo, como no painel de origem, mas os números só
    # saem depois do gráfico: é o clique nele que decide o mês a mostrar. O
    # container guarda o lugar deles aqui em cima.
    area_kpis = st.container()
    st.divider()

    # --- ações no tempo (clicável: a barra escolhida recorta a tela) --------
    # No painel de origem o período são botões de ano e de mês; aqui eles viram
    # filtro, e a série mostra de uma vez como a agenda se distribuiu.
    st.markdown("**Ações por mês**")
    f = f.assign(_mes=f["data"].dt.strftime("%Y-%m"))
    serie = f.groupby("_mes").size().reset_index(name="acoes")
    # A chave muda quando muda um filtro (ou quando o botão de limpar roda o
    # contador): sem isso o mês clicado sobrevive a uma troca de filtro e pode
    # nem existir no novo recorte, deixando a tela incoerente com o gráfico.
    clique = graficos.selecao("mes", "_mes")
    evento = st.altair_chart(
        alt.Chart(serie)
        .mark_bar(cornerRadiusEnd=3, color="#4269d0")
        .encode(
            # Eixo ordinal com "AAAA-MM" (ordena sozinho) e rótulo "08/26" —
            # o mês é a própria chave do clique. Ver `graficos.py` para o
            # porquê de não usar `yearmonth(...)`.
            x=alt.X("_mes:O", title=None, axis=alt.Axis(
                labelAngle=-45, labelOverlap="greedy",
                labelExpr="slice(datum.value, 5) + '/' + slice(datum.value, 2, 4)")),
            y=alt.Y("acoes:Q", title="ações", stack=None,
                    scale=graficos.escala(serie["acoes"].max())),
            # A barra não escolhida esmaece — fica claro o que está filtrando.
            opacity=alt.condition(clique, alt.value(1), alt.value(0.35)),
            tooltip=[alt.Tooltip("_mes:O", title="mês"),
                     alt.Tooltip("acoes:Q", title="ações")],
        )
        .add_params(clique)
        .properties(height=180),
        width='stretch',
        key=f"grafico_mes_{_chave_grafico(sel_terr, sel_mun, sel_ano, sel_mes, [pacto], [com_agenda])}",
        on_select="rerun",
    )

    # --- clique -> recorte de cartões, mapa e tabela -----------------------
    # O gráfico continua mostrando a série inteira: ele é o contexto: quem se
    # move é o resto da tela.
    sel_clique = _selecionados(evento, "mes", "_mes")
    foco = f[f["_mes"].isin(sel_clique)] if sel_clique else f

    por_municipio = _por_municipio(foco, universo)
    visitadas = int(por_municipio["visitado"].sum())
    total_municipios = len(por_municipio)
    percentual = 100 * visitadas / total_municipios if total_municipios else 0

    # --- indicadores -----------------------------------------------------
    # Os mesmos três cartões do painel de origem, na mesma ordem. O percentual
    # de visitadas é sobre os municípios DO RECORTE (224 sem filtro nenhum).
    # A cor de cada cartão diz o que ele é (ver `.kpi-*` em `estilo.py`):
    # azul = contagem, verde = já visitado, âmbar = ainda falta visitar.
    kpis = [
        ("Total de ações", f"{len(foco)}", "azul"),
        ("Total de cidades visitadas",
         f"{visitadas} <span style='font-size:.7em;opacity:.75'>"
         f"({percentual:.1f}% de {total_municipios})</span>", "verde"),
        ("Total de cidades não visitadas", f"{total_municipios - visitadas}", "ambar"),
    ]
    cartoes = "".join(
        f'<div class="kpi kpi-{cor}"><div class="kpi-v">{valor}</div>'
        f'<div class="kpi-l">{rotulo}</div></div>'
        for rotulo, valor, cor in kpis
    )
    with area_kpis:
        st.markdown(f'<div class="kpi-grid">{cartoes}</div>', unsafe_allow_html=True)
        st.progress(percentual / 100)

    if sel_clique:
        meses_escolhidos = ", ".join(
            f"{MESES[int(m[5:]) - 1]}/{m[:4]}" for m in sorted(sel_clique)
        )
        c_txt, c_btn = st.columns([4, 1])
        c_txt.caption(f"🔎 **Cartões, mapa e tabela filtrados por:** {meses_escolhidos} — "
                      f"{len(foco)} de {len(f)} ações.")
        c_btn.button("Limpar seleção", on_click=_limpar_selecao,
                     key=f"limpar_{SLUG}", width='stretch')
    else:
        st.caption("Clique numa barra para recortar os cartões, o mapa e a tabela "
                   "por mês (Ctrl+clique escolhe vários).")

    st.divider()

    # --- mapa e tabela, lado a lado como no painel de origem ---------------
    # O layout é escolhido ANTES de desenhar: com a tabela em largura inteira
    # ela vai para baixo do mapa, e é por isso que o interruptor é lido da
    # sessão aqui (ele é desenhado lá dentro, e mudá-lo já dispara o rerun).
    if tab.largura_inteira(SLUG):
        clicado = _bloco_mapa(por_municipio, municipios)
        st.divider()
        _tabela_resumo(foco, por_municipio, clicado)
    else:
        esq, dir = st.columns([3, 2])
        with esq:
            clicado = _bloco_mapa(por_municipio, municipios)
        with dir:
            _tabela_resumo(foco, por_municipio, clicado)

    st.caption(f"Fonte: `{FONTE_ACOES}` e `{FONTE_MUNICIPIOS}` — via Dremio Arrow Flight. "
               f"{_frescor()}")

"""BI Selo Ambiental 2026 (SEMARH-PI) — pertence ao setor Chefia de Gabinete.

Le `nessie.refinamento.semarh_painel_fases` (via Dremio Arrow Flight) e monta,
por fase: indicadores, distribuicao por tipo de selo e por criterios, mapa dos
municipios com selo e a tabela de pontuacao/resultado. Tem ainda a visao
**Balanco anual**, com as 3 fases lado a lado. Nao transforma dado — isso e
feito no notebook `semarh_painel/refinamento_selo_ambiental`.

Layout espelhado no painel de origem da SEMARH (Looker Studio), que publica a
**1a fase**: mesmos cartoes, mesmos graficos, mesmos funis do balanco e mesma
ordenacao da tabela. O que o painel acrescenta: seletor de fase (a 3a e o
resultado final), filtro por municipio, mapa colorido por parametro, clique nos
graficos para recortar mapa/tabela e a leitura de consistencia dos dados.
"""

import altair as alt
import pandas as pd
import streamlit as st

from app_semarh import mapa
from app_semarh.dados import consultar, estado_atualizacao
from app_semarh.filtros import multiselect_opcional_url, multiselect_url, selectbox_url

# Grao: 1 linha por municipio x fase. A tabela `semarh_painel` (so a 3a fase)
# continua existindo para quem consome o resultado final direto.
TABELA = "nessie.refinamento.semarh_painel_fases"

# Visoes do BI, na mesma nomenclatura do painel da SEMARH: 1a/2a/3a fase e o
# balanco anual (as tres lado a lado). O padrao e a 3a — o resultado final.
BALANCO = "balanco"
VISOES = {
    "3": "Selo ambiental — 3ª fase",
    "2": "Selo ambiental — 2ª fase",
    "1": "Selo ambiental — 1ª fase",
    BALANCO: "Balanço anual — as 3 fases",
}
# Sufixo do titulo por visao (o rotulo do seletor e mais longo).
TITULO_VISAO = {"3": "3ª fase", "2": "2ª fase", "1": "1ª fase", BALANCO: "Balanço anual"}

# Selo A/B/C e ordinal (A melhor -> C). Tres tons de verde ficavam parecidos
# demais num ponto de mapa: a rampa vai de verde a laranja (RdYlGn), que separa
# por MATIZ e por LUMINOSIDADE — legivel tambem para daltonismo verde-vermelho.
# Situacoes negativas em cinza, fora da rampa.
COR_SELO = {"A": "#1a9850", "B": "#91cf60", "C": "#f4901e"}
ORDEM_RESULTADO = ["Selo A", "Selo B", "Selo C", "Não elegível", "Não habilitado"]
COR_RESULTADO = ["#1a9850", "#91cf60", "#f4901e", "#9e9e9e", "#4d4d4d"]

# Parametro que colore o mapa -> (coluna, tipo de escala).
MODOS_MAPA = {
    "Resultado (selo)": ("resultado", "categoria"),
    "Território de desenvolvimento": ("territorio_desenvolvimento", "categoria"),
    "Critérios atendidos": ("criterios_atendidos", "numero"),
    "Pontuação": ("pontos", "numero"),
    "Pacto ambiental": ("pacto_ambiental", "booleano"),
}

SEM_AVALIACAO = "s/ apuração"


def _regra(df: pd.DataFrame) -> pd.Series:
    """Regra critérios -> resultado, **derivada do dado**, não fixa no código.

    O selo sai do numero de criterios atendidos, nao da pontuacao. Em vez de
    cravar as faixas aqui (que envelhecem a cada recarga da fonte), toma-se o
    resultado predominante de cada quantidade de criterios. Assim, se a regra
    da edicao mudar, o painel acompanha — e o que destoar vira excecao visivel
    em vez de virar texto errado.
    """
    base = df.dropna(subset=["criterios_atendidos"])
    return base.groupby("criterios_atendidos")["resultado"].agg(lambda s: s.mode().iat[0])


def _cor_faixa(faixa: str, regra: pd.Series) -> str:
    """Cor da barra de criterios = cor do selo que aquela faixa gera."""
    if faixa == SEM_AVALIACAO:
        return "#4d4d4d"
    resultado = regra.get(float(faixa))
    if resultado in ("Selo A", "Selo B", "Selo C"):
        return COR_SELO[resultado[-1]]
    return "#9e9e9e"


def _selecionados(evento, parametro: str, campo: str) -> list[str]:
    """Valores clicados num gráfico Altair interativo.

    O payload do Streamlit varia com a versao: pode vir como lista de registros
    (`[{"resultado": "Selo A"}]`) ou como dicionario de listas
    (`{"resultado": ["Selo A"]}`). Aceita os dois e sempre devolve strings.
    """
    selecao = getattr(evento, "selection", None) or {}
    bruto = selecao.get(parametro) or []
    if isinstance(bruto, dict):
        return [str(v) for v in bruto.get(campo, [])]
    return [str(item[campo]) for item in bruto if isinstance(item, dict) and campo in item]


def _recorte(f: pd.DataFrame, sel_selo: list[str], sel_crit: list[str]) -> pd.DataFrame:
    """Linhas correspondentes as barras clicadas (os dois graficos em E lógico).

    Sem clique nenhum, devolve tudo — o padrao e o painel inteiro.
    """
    recorte = f
    if sel_selo:
        recorte = recorte[recorte["resultado"].isin(sel_selo)]
    if sel_crit:
        recorte = recorte[recorte["_faixa"].isin(sel_crit)]
    return recorte


def _limpar_selecao() -> None:
    """Zera o clique nos dois graficos.

    O estado de evento de um grafico e read-only no Streamlit — nao da para
    apagar direto. O jeito que funciona e trocar a CHAVE do widget: com chave
    nova, o grafico nasce sem selecao. Este contador entra na chave.
    """
    st.session_state["_reset_graficos"] = st.session_state.get("_reset_graficos", 0) + 1


def _chave_graficos(fase: str, *filtros) -> str:
    """Chave dos graficos: muda quando muda a fase, um filtro ou o botao.

    Sem isso o clique de antes sobrevive a troca de fase/filtro — a barra
    escolhida pode nem existir no novo recorte, e mapa e tabela passariam a
    mostrar algo que os graficos acima nao mostram. Era essa a inconsistencia.
    """
    assinatura = abs(hash(tuple(tuple(sorted(x)) for x in filtros)))
    return f"{fase}_{assinatura}_{st.session_state.get('_reset_graficos', 0)}"


TOOLTIP = (
    "<b>{municipio}</b><br/>{resultado}<br/>"
    "Pontos: {pontos} &nbsp;|&nbsp; Critérios: {criterios_atendidos}<br/>"
    "{territorio_desenvolvimento}"
)


def _desenhar_mapa(geo: pd.DataFrame, modo: str) -> None:
    """Colore os municipios pelo parametro escolhido e desenha mapa + legenda.

    O tamanho do circulo acompanha a pontuacao (area proporcional), como no
    painel de origem: a cor conta o parametro escolhido, o tamanho conta quanto
    o municipio pontuou.
    """
    coluna, tipo = MODOS_MAPA[modo]
    geo["_raio"] = mapa.raio_por_valor(geo["pontos"])

    if tipo == "numero":
        cores, vmin, vmax = mapa.sequencial(geo[coluna])
        geo["_rgb"] = cores
        mapa.pontos(geo, "_rgb", TOOLTIP, raio_m="_raio")
        mapa.legenda_gradiente(vmin, vmax, modo, casas=0 if coluna == "criterios_atendidos" else 1)
        return

    if tipo == "booleano":
        rotulos = geo[coluna].map({True: "Sim", False: "Não"})
        cores = {"Sim": "#12a5b3", "Não": "#9e9e9e"}
    elif coluna == "resultado":
        # Ordem e cores fixas: as mesmas do grafico de barras acima.
        rotulos = geo[coluna]
        presentes = [r for r in ORDEM_RESULTADO if r in set(rotulos)]
        cores = mapa.paleta(presentes, dict(zip(ORDEM_RESULTADO, COR_RESULTADO)))
    else:
        rotulos = geo[coluna].fillna("Sem informação")
        cores = mapa.paleta(sorted(rotulos.unique()))

    geo["_rgb"] = [mapa.hex_rgb(cores.get(v, "#9e9e9e")) for v in rotulos]
    mapa.pontos(geo, "_rgb", TOOLTIP, raio_m="_raio")
    mapa.legenda_categorias(cores, modo)


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


def _funil(dados: pd.DataFrame, titulo: str) -> None:
    """Funil de uma fase: barras centradas, da categoria mais cheia à mais vazia.

    O rotulo ja traz a contagem — `SELO A (113)` — como no painel de origem, que
    nao tem eixo numerico.
    """
    d = dados.copy()
    d["rotulo"] = d["resultado"].str.upper() + " (" + d["municipios"].astype(str) + ")"
    # Barra centrada = funil: metade para cada lado do eixo.
    d["ini"] = -d["municipios"] / 2
    d["fim"] = d["municipios"] / 2
    ordem = list(d["rotulo"])
    st.markdown(f"**{titulo}**")
    st.altair_chart(
        alt.Chart(d)
        .mark_bar()
        .encode(
            y=alt.Y("rotulo:N", sort=ordem, title=None),
            x=alt.X("ini:Q", axis=None, title=None),
            x2="fim:Q",
            color=alt.Color(
                "resultado:N",
                scale=alt.Scale(domain=ORDEM_RESULTADO, range=COR_RESULTADO),
                legend=None,
            ),
            tooltip=[alt.Tooltip("resultado:N", title="resultado"),
                     alt.Tooltip("municipios:Q", title="municípios")],
        )
        .properties(height=260),
        width='stretch',
    )


def _balanco(f: pd.DataFrame) -> None:
    """Balanço anual: as 3 fases lado a lado + a tabela larga por município.

    Recebe o dado ja filtrado (territorio/municipio) no formato longo, com uma
    linha por municipio x fase.
    """
    colunas = st.columns(3)
    for coluna, fase in zip(colunas, (1, 2, 3)):
        dados = (
            f[f["fase"] == fase].groupby("resultado").size()
            .reset_index(name="municipios").sort_values("municipios", ascending=False)
        )
        with coluna:
            if dados.empty:
                st.caption(f"Sem dados na {fase}ª fase.")
            else:
                _funil(dados, f"Resultado {fase}ª fase")

    # Quanto cada municipio subiu (ou nao) da 1a para a 3a fase.
    posicao = {r: i for i, r in enumerate(reversed(ORDEM_RESULTADO))}
    inicio = f[f["fase"] == 1].set_index("municipio")["resultado"].map(posicao)
    fim = f[f["fase"] == 3].set_index("municipio")["resultado"].map(posicao)
    evolucao = (fim - inicio).dropna()
    if not evolucao.empty:
        st.caption(
            f"**Da 1ª para a 3ª fase:** {int((evolucao > 0).sum())} municípios melhoraram · "
            f"{int((evolucao == 0).sum())} mantiveram · {int((evolucao < 0).sum())} pioraram."
        )

    st.divider()

    # --- tabela larga: uma linha por municipio, as 3 fases lado a lado ----
    st.markdown("**Resultado e pontuação por fase**")
    largo = (
        f.pivot_table(index="municipio", columns="fase",
                      values=["resultado", "pontos"], aggfunc="first")
    )
    largo.columns = [f"{campo}_{fase}" for campo, fase in largo.columns]
    largo = largo.reset_index()
    ordem_colunas = ["municipio"] + [
        f"{campo}_{fase}" for fase in (1, 2, 3) for campo in ("resultado", "pontos")
    ]
    largo = largo[[c for c in ordem_colunas if c in largo.columns]].sort_values("municipio")
    st.dataframe(
        largo,
        width='stretch',
        hide_index=True,
        column_config={
            "municipio": "Município",
            **{f"resultado_{n}": f"Resultado {n}ª fase" for n in (1, 2, 3)},
            **{f"pontos_{n}": st.column_config.NumberColumn(f"Pontos {n}ª fase", format="%.1f")
               for n in (1, 2, 3)},
        },
    )
    st.download_button(
        "Baixar CSV",
        largo.to_csv(index=False).encode("utf-8"),
        file_name="selo_ambiental_2026_balanco_anual.csv",
        mime="text/csv",
    )
    st.caption(f"Fonte: `{TABELA}` — via Dremio Arrow Flight. {_frescor()}")


def render(user: dict | None) -> None:
    try:
        todas = consultar(f"SELECT * FROM {TABELA}")
    except Exception as erro:
        st.error(f"Falha ao consultar o Dremio: {erro}")
        st.caption(
            "Confira: a stack está no ar, as credenciais em `vars.env` estão corretas, e a tabela "
            f"`{TABELA}` existe — rode o notebook `semarh_painel/refinamento_selo_ambiental`."
        )
        return

    if todas.empty:
        st.warning(f"A tabela `{TABELA}` está vazia.")
        return

    # Qual fase esta na tela e a duvida numero 1 ao comparar com listas
    # publicadas: cada fase tem numeros bem diferentes.
    todas["fase"] = pd.to_numeric(todas["fase"], errors="coerce").astype(int)
    todas["tem_selo"] = todas["tem_selo"].astype(bool)
    todas["criterios_atendidos"] = pd.to_numeric(todas["criterios_atendidos"], errors="coerce")

    visao = selectbox_url(
        "Visão", list(VISOES), "fase", padrao="3", formato=VISOES.get,
        ajuda="As 3 fases da edição 2026 ou o balanço anual, que mostra as três juntas. "
              "O resultado válido é o da 3ª fase; as anteriores são parciais.",
    )
    # A fase entra no titulo porque muda TODOS os numeros da tela — no seletor
    # sozinho passava despercebido. O contexto de cada fase fica na ajuda do
    # seletor, nao ocupando a tela.
    st.subheader(f"Selo Ambiental 2026 — Piauí · {TITULO_VISAO[visao]}")

    df = (todas if visao == BALANCO else todas[todas["fase"] == int(visao)]).copy()

    # Regra critérios -> selo lida do dado inteiro (independe dos filtros).
    regra = _regra(df[df["fase"] == (3 if visao == BALANCO else int(visao))])

    # --- filtros (persistem no refresh via URL) --------------------------
    territorios = sorted(df["territorio_desenvolvimento"].dropna().unique())
    municipios = sorted(df["municipio"].dropna().unique())
    # Os filtros na mesma linha; o CSS responsivo empilha quando a tela e
    # estreita. No balanco nao ha filtro de situacao: ela muda de fase para
    # fase, entao filtrar por ela esvaziaria linhas de um funil so.
    if visao == BALANCO:
        c_terr, c_mun = st.columns(2)
        sel_sit = list(df["situacao"].dropna().unique())
    else:
        c_terr, c_sit, c_mun = st.columns(3)
        situacoes = sorted(df["situacao"].dropna().unique())
        sel_sit = multiselect_url("Situação", situacoes, "sit", c_sit)
    sel_terr = multiselect_url("Território de desenvolvimento", territorios, "terr", c_terr)
    # Municipio: vazio = todos. Serve tanto para comparar um punhado de
    # municipios quanto para isolar um so — vale para KPIs, graficos, mapa e
    # tabela, entao o painel inteiro passa a falar so da selecao.
    sel_mun = multiselect_opcional_url(
        "Município", municipios, "mun", c_mun,
        ajuda="Deixe vazio para ver todos. Escolha um ou vários para comparar.",
        placeholder="Todos os municípios",
    )

    f = df[df["territorio_desenvolvimento"].isin(sel_terr) & df["situacao"].isin(sel_sit)].copy()
    if sel_mun:
        f = f[f["municipio"].isin(sel_mun)]
    if f.empty:
        st.warning(
            "Nenhum município para os filtros selecionados."
            + (" O município escolhido pode estar fora do território ou da situação filtrada."
               if sel_mun else "")
        )
        return
    if sel_mun:
        n_mun = f["municipio"].nunique()
        st.caption(f"Filtrando {n_mun} de {df['municipio'].nunique()} municípios.")

    if visao == BALANCO:
        _balanco(f)
        return
    f = f.drop(columns=["fase"])

    # --- indicadores -----------------------------------------------------
    # Mesmos quatro cartoes do painel de origem (Looker Studio), na mesma
    # ordem: com selo / nao postulados / nao elegiveis / nao habilitados.
    # A quebra por Selo A/B/C fica no grafico ao lado, como la.
    kpis = [
        ("Municípios com selo", int(f["tem_selo"].sum())),
        ("Municípios não postulados", int((f["situacao"] == "Não postulado").sum())),
        ("Municípios não elegíveis", int((f["situacao"] == "Não elegível").sum())),
        ("Municípios não habilitados", int((f["situacao"] == "Não habilitado").sum())),
    ]
    cartoes = "".join(
        f'<div class="kpi"><div class="kpi-v">{valor}</div><div class="kpi-l">{rotulo}</div></div>'
        for rotulo, valor in kpis
    )
    st.markdown(f'<div class="kpi-grid">{cartoes}</div>', unsafe_allow_html=True)

    st.divider()

    # --- distribuicoes (clicaveis: a barra escolhida filtra mapa e tabela) --
    # Faixa de criterios como texto: e por ela que a barra e selecionada, entao
    # precisa existir tambem em `f` para o clique poder filtrar as linhas.
    f["_faixa"] = ["0" if pd.isna(v) else str(int(v)) for v in f["criterios_atendidos"]]
    chave = _chave_graficos(visao, sel_terr, sel_sit, sel_mun)

    esq, dir = st.columns(2)
    with esq:
        st.markdown("**Número de municípios por tipo de selo**")
        # So os tres selos, barra horizontal ordenada pela contagem — igual ao
        # painel de origem. Nao elegivel/nao habilitado ficam nos cartoes.
        por_selo = (
            f[f["tem_selo"]].groupby("resultado").size()
            .reset_index(name="municipios").sort_values("municipios")
        )
        ordem_selo = list(por_selo["resultado"])
        clique_selo = alt.selection_point(name="selo", fields=["resultado"])
        evento_selo = st.altair_chart(
            alt.Chart(por_selo)
            .mark_bar(cornerRadiusEnd=4)
            .encode(
                x=alt.X("municipios:Q", title="municípios"),
                y=alt.Y("resultado:N", sort=ordem_selo, title=None),
                color=alt.Color(
                    "resultado:N",
                    scale=alt.Scale(domain=ORDEM_RESULTADO, range=COR_RESULTADO),
                    legend=None,
                ),
                # A barra nao escolhida esmaece — fica claro o que esta filtrando.
                opacity=alt.condition(clique_selo, alt.value(1), alt.value(0.35)),
                tooltip=[alt.Tooltip("resultado:N", title="resultado"),
                         alt.Tooltip("municipios:Q", title="municípios")],
            )
            .add_params(clique_selo)
            .properties(height=260),
            width='stretch',
            key=f"grafico_selo_{chave}",
            on_select="rerun",
        )
    with dir:
        st.markdown("**Número de municípios por critérios atendidos**")
        # Criterio do painel de origem: municipio nao habilitado (sem apuracao
        # na fonte) entra no balde "0". Mantido para o grafico bater com o
        # Looker; a composicao do balde vai na legenda abaixo, porque "nao foi
        # avaliado" e "atendeu zero criterios" nao sao a mesma coisa.
        por_crit = f.groupby("_faixa").size().reset_index(name="municipios")
        ordem_crit = sorted(por_crit["_faixa"], key=int)
        clique_crit = alt.selection_point(name="criterios", fields=["_faixa"])
        evento_crit = st.altair_chart(
            alt.Chart(por_crit)
            .mark_bar(cornerRadiusEnd=4)
            .encode(
                x=alt.X("_faixa:O", sort=ordem_crit, title="critérios atendidos"),
                y=alt.Y("municipios:Q", title="municípios"),
                # Cada barra sai na cor do selo que aquela quantidade de
                # criterios produz — a cor passa a contar a regra.
                color=alt.Color(
                    "_faixa:O",
                    scale=alt.Scale(domain=ordem_crit,
                                    range=[_cor_faixa(v, regra) for v in ordem_crit]),
                    legend=None,
                ),
                opacity=alt.condition(clique_crit, alt.value(1), alt.value(0.35)),
                tooltip=[alt.Tooltip("_faixa:O", title="critérios"),
                         alt.Tooltip("municipios:Q", title="municípios")],
            )
            .add_params(clique_crit)
            .properties(height=260),
            width='stretch',
            key=f"grafico_criterios_{chave}",
            on_select="rerun",
        )
        sem_apuracao = int(f["criterios_atendidos"].isna().sum())
        if sem_apuracao:
            st.caption(
                f"A barra **0** inclui {sem_apuracao} município(s) não habilitado(s), sem "
                "apuração na fonte — mesmo critério do painel de origem."
            )

    st.divider()

    # --- clique nos graficos -> recorte do mapa e da tabela ---------------
    # Os cartoes e os proprios graficos continuam mostrando o total: o clique e
    # um "zoom" para o detalhe embaixo, nao um filtro global (senao a barra
    # clicada viraria o unico dado da tela e o contexto sumiria).
    sel_selo = _selecionados(evento_selo, "selo", "resultado")
    sel_crit = _selecionados(evento_crit, "criterios", "_faixa")
    foco = _recorte(f, sel_selo, sel_crit)

    if sel_selo or sel_crit:
        partes = []
        if sel_selo:
            partes.append(", ".join(sel_selo))
        if sel_crit:
            partes.append(", ".join(f"{c} critério(s)" for c in sel_crit))
        c_txt, c_btn = st.columns([4, 1])
        c_txt.caption(
            f"🔎 **Mapa e tabela filtrados por:** {' + '.join(partes)} — "
            f"{len(foco)} de {len(f)} municípios."
        )
        c_btn.button("Limpar seleção", on_click=_limpar_selecao, width='stretch')
        if foco.empty:
            st.warning("Nenhum município nessa combinação de barras.")
            return
    else:
        st.caption("Clique numa barra acima para filtrar o mapa e a tabela.")

    # --- mapa ------------------------------------------------------------
    # O enquadramento e sempre o Piaui inteiro (mapa.PIAUI), no maior zoom que
    # cabe: filtrar um territorio muda a nuvem de pontos, nao o recorte.
    st.markdown("**Mapa de municípios com selo ambiental**")
    geo = foco.dropna(subset=["latitude", "longitude"]).copy()
    if geo.empty:
        st.caption("Nenhum município com coordenadas nos filtros atuais.")
    else:
        c_modo, c_esc = st.columns([2, 1])
        modo = c_modo.selectbox("Colorir por", list(MODOS_MAPA), key="mapa_cor")
        # Padrao igual ao painel de origem: so quem tem selo. Desligue para ver
        # tambem os nao elegiveis/nao habilitados.
        so_com_selo = c_esc.toggle("Só municípios com selo", value=True, key="mapa_selo")
        if so_com_selo:
            geo = geo[geo["tem_selo"]]
        if geo.empty:
            st.caption("Nenhum município com selo nos filtros atuais.")
        else:
            _desenhar_mapa(geo, modo)

    st.divider()

    # --- tabela ----------------------------------------------------------
    st.markdown("**Pontuação e resultado dos municípios**")
    # Ordem do painel de origem: pontuacao decrescente. Municipio/Resultado/
    # Pontos sao as colunas de la; criterios, territorio e pacto vem depois.
    tabela = (
        foco[["municipio", "resultado", "pontos", "criterios_atendidos",
           "territorio_desenvolvimento", "pacto_ambiental"]]
        .sort_values("pontos", ascending=False, na_position="last")
        .reset_index(drop=True)
    )
    st.dataframe(
        tabela,
        width='stretch',
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
    st.caption(f"Fonte: `{TABELA}` — via Dremio Arrow Flight. {_frescor()}")

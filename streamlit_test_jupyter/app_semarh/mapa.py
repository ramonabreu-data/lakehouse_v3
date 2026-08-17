"""Mapa de pontos do painel (pydeck) — enquadramento, paletas, contexto e legenda.

Compartilhado pelas abas que plotam municipios. Quatro decisoes vivem aqui:

0. **Contexto geografico por baixo dos pontos.** So a nuvem de pontos nao diz
   onde o Piaui comeca e termina, nem em que territorio cada municipio esta.
   `contexto()` desenha duas camadas antes dos pontos: uma sombra sobre tudo o
   que esta FORA do estado (efeito de holofote, feito com um poligono que tem o
   Piaui como furo) e os 12 territorios de desenvolvimento, unidos a partir dos
   municipios. As malhas sao do IBGE e ficam versionadas em `geo/`.

1. **Enquadramento fixo no Piaui.** O `st.map` enquadra pelos dados: ao filtrar
   um territorio, o mapa "pula" e some a referencia geografica. Aqui a camera e
   calculada a partir das extremidades do estado (`PIAUI`), entao o recorte e
   sempre o mesmo — muda so a nuvem de pontos.
2. **Zoom maximo que ainda cabe.** `visao()` faz o fit-bounds em Web Mercator:
   pega o maior zoom em que as quatro extremidades do estado ainda aparecem.
   Como o Piaui e alto e estreito (8,2 graus de latitude x 5,6 de longitude), a
   altura e quem limita em qualquer largura util — por isso o resultado nao
   depende do tamanho da tela.
3. **Cor por parametro.** Paleta categorica (ate 12 series bem separaveis) e
   rampa sequencial (viridis, perceptualmente uniforme e segura para
   daltonismo) + a legenda correspondente.
"""

from __future__ import annotations

import json
import math
from collections import defaultdict
from pathlib import Path

import pandas as pd
import pydeck as pdk
import streamlit as st

# Extremidades do Piaui (N, S, O, L). Delta do Parnaiba no norte, divisa com a
# Bahia no sul, rio Parnaiba a oeste, divisa com o Ceara a leste.
PIAUI = (-2.74, -10.93, -45.99, -40.37)

# Malhas do IBGE versionadas junto do app (ver geo/baixar_malhas.py).
GEO = Path(__file__).resolve().parent / "geo"

# Caixa que cobre folgadamente o entorno do estado. E o anel EXTERNO da mascara:
# com o Piaui como furo, o preenchimento cai so no que esta fora do estado.
CAIXA_EXTERNA = [[-60.0, -25.0], [-30.0, -25.0], [-30.0, 8.0], [-60.0, 8.0]]

# Sombreado de fora do estado: escuro e translucido, para o mapa-base ainda
# aparecer por baixo (rios, divisas dos vizinhos) mas em segundo plano.
FORA_DO_ESTADO = [8, 12, 22, 130]
# Territorio sem cor propria — o padrao. Cinza-azulado escuro, de proposito
# neutro: quem carrega cor na tela sao os pontos, que sao o dado.
TERRITORIO_NEUTRO = [41, 51, 69, 92]
# Tom medio das divisas: mais escuro que o mapa-base claro e mais claro que o
# escuro, entao a linha aparece nos dois temas sem precisar detectar qual e.
LINHA_TERRITORIO = [120, 132, 150, 205]
CONTORNO_PIAUI = [236, 240, 245, 235]

# Paleta categorica: 12 matizes distintos (cobre os 12 territorios de
# desenvolvimento). Ordem escolhida para que vizinhos na lista nao se confundam.
CATEGORICAS = [
    "#4269d0", "#f4901e", "#3ca951", "#e45756", "#a463f2", "#12a5b3",
    "#ff8ab7", "#9c6b4e", "#8bbf3d", "#b04fa8", "#7f8fa6", "#d6b60d",
]

# Rampa sequencial (viridis): escuro = valor baixo, claro = alto.
VIRIDIS = ["#440154", "#414487", "#2a788e", "#22a884", "#7ad151", "#fde725"]


def hex_rgb(cor: str) -> list[int]:
    cor = cor.lstrip("#")
    return [int(cor[i:i + 2], 16) for i in (0, 2, 4)]


def paleta(valores: list, cores: dict | list | None = None) -> dict:
    """Mapa valor -> cor hex. `cores` fixa as cores de series conhecidas."""
    if isinstance(cores, dict):
        return {v: cores.get(v, "#9e9e9e") for v in valores}
    base = cores or CATEGORICAS
    return {v: base[i % len(base)] for i, v in enumerate(valores)}


def _interpolar(t: float, escala: list[str]) -> list[int]:
    """Cor da rampa na posicao t (0..1), interpolando entre as paradas."""
    t = min(max(t, 0.0), 1.0)
    pos = t * (len(escala) - 1)
    i = min(int(pos), len(escala) - 2)
    a, b, peso = hex_rgb(escala[i]), hex_rgb(escala[i + 1]), pos - i
    return [round(a[c] + (b[c] - a[c]) * peso) for c in range(3)]


def sequencial(serie: pd.Series, escala: list[str] | None = None) -> tuple[list, float, float]:
    """Cores RGB de uma serie numerica + os limites usados na legenda.

    Valores nulos saem em cinza (nao ha posicao na rampa para "sem dado").
    """
    escala = escala or VIRIDIS
    valores = pd.to_numeric(serie, errors="coerce")
    vmin, vmax = float(valores.min()), float(valores.max())
    faixa = vmax - vmin or 1.0
    cores = [
        [158, 158, 158] if pd.isna(v) else _interpolar((v - vmin) / faixa, escala)
        for v in valores
    ]
    return cores, vmin, vmax


def visao(altura: int, bounds: tuple = PIAUI, largura: int = 1250,
          margem: float = 0.94) -> pdk.ViewState:
    """Camera que enquadra `bounds` inteiro, no maior zoom possivel."""
    norte, sul, oeste, leste = bounds
    dy = abs(_mercator_y(sul) - _mercator_y(norte))
    dx = (leste - oeste) / 360
    zoom = min(
        math.log2(largura * margem / 256 / dx),
        math.log2(altura * margem / 256 / dy),
    )
    y_centro = (_mercator_y(norte) + _mercator_y(sul)) / 2
    return pdk.ViewState(
        latitude=_mercator_lat(y_centro),
        longitude=(oeste + leste) / 2,
        zoom=round(zoom, 2),
    )


def _mercator_y(lat: float) -> float:
    seno = math.sin(math.radians(lat))
    return 0.5 - math.log((1 + seno) / (1 - seno)) / (4 * math.pi)


def _mercator_lat(y: float) -> float:
    return math.degrees(2 * math.atan(math.exp((0.5 - y) * 2 * math.pi)) - math.pi / 2)


def raio_por_valor(serie: pd.Series, minimo: int = 6000, maximo: int = 16000) -> list[float]:
    """Raio em metros proporcional ao valor — **area** proporcional, via raiz.

    Escalar o raio direto pelo valor exagera: a area cresce com o quadrado, e o
    olho le area. Sem valor (nulo), usa o raio minimo.
    """
    v = pd.to_numeric(serie, errors="coerce")
    lo, hi = float(v.min()), float(v.max())
    faixa = hi - lo or 1.0
    return [
        minimo if pd.isna(x) else minimo + (maximo - minimo) * (((x - lo) / faixa) ** 0.5)
        for x in v
    ]


@st.cache_data(show_spinner=False)
def _malha(arquivo: str) -> dict:
    """GeoJSON do IBGE lido do disco (cache: o arquivo nao muda em execucao)."""
    return json.loads((GEO / arquivo).read_text())


@st.cache_data(show_spinner=False)
def _territorios(pertencimento: tuple[tuple[int, str], ...]) -> list[dict]:
    """Une os municípios de cada território num polígono só.

    Sem dissolver, as divisas MUNICIPAIS apareceriam por dentro de cada
    territorio e o mapa viraria uma malha de 224 celulas — o oposto de
    "evidenciar as areas". Unindo, sobra so a divisa entre territorios.

    Roda em ~25 ms para os 224 municipios e fica em cache; a chave e o proprio
    pertencimento, entao se o refinamento mudar a lotacao de um municipio o
    desenho acompanha, sem arquivo intermediario para envelhecer.
    """
    from shapely.geometry import mapping, shape
    from shapely.ops import unary_union

    por_territorio = defaultdict(list)
    de_codigo = dict(pertencimento)
    for feicao in _malha("municipios.json")["features"]:
        # `codarea` e o codigo IBGE completo; a tabela guarda sem o prefixo do
        # estado (2200000 + cod_ibge), a mesma chave do refinamento.
        codigo = int(feicao["properties"]["codarea"])
        nome = de_codigo.get(codigo - 2200000)
        if nome:
            por_territorio[nome].append(shape(feicao["geometry"]))

    saida = []
    for nome in sorted(por_territorio):
        unido = unary_union(por_territorio[nome])
        geometria = mapping(unido)
        # PolygonLayer do deck.gl quer sempre lista de aneis: normaliza o
        # Polygon simples para o mesmo formato do MultiPolygon.
        partes = (geometria["coordinates"] if geometria["type"] == "MultiPolygon"
                  else [geometria["coordinates"]])
        for parte in partes:
            saida.append({"territorio": nome,
                          "poligono": [[list(p) for p in anel] for anel in parte]})
    return saida


def contexto(pertencimento: dict[int, str],
             cores: dict[str, str] | None = None) -> list[pdk.Layer]:
    """Camadas de fundo: sombra fora do Piauí + os territórios por dentro.

    `pertencimento` e {cod_ibge: territorio} — vem do dado, nao de um arquivo.
    `cores` pinta cada territorio com a sua cor da legenda; sem ele, todos saem
    no mesmo tom neutro. A regra: so colorir quando o MAPA ja esta colorindo por
    territorio, senao dois significados diferentes disputariam a mesma cor (um
    territorio verde por baixo de um ponto verde de Selo A confunde os dois).
    """
    piaui = _malha("piaui.json")["features"][0]["geometry"]["coordinates"]

    # Um poligono com furo: anel externo = a caixa, aneis seguintes = o estado.
    # E o que produz o efeito de holofote sem precisar recortar o mapa-base.
    mascara = pdk.Layer(
        "PolygonLayer",
        # Todas as camadas levam `id`: e o que o Streamlit exige para o mapa
        # manter a selecao entre reruns (ver `pontos`).
        id="fora-do-estado",
        data=[{"poligono": [CAIXA_EXTERNA, *[[list(p) for p in anel] for anel in piaui]]}],
        get_polygon="poligono",
        get_fill_color=FORA_DO_ESTADO,
        stroked=False,
        pickable=False,
    )

    areas = _territorios(tuple(sorted(pertencimento.items())))
    for area in areas:
        area["_cor"] = (hex_rgb(cores[area["territorio"]]) + [150]
                        if cores and area["territorio"] in cores else TERRITORIO_NEUTRO)
    camada_territorios = pdk.Layer(
        "PolygonLayer",
        id="territorios",
        data=areas,
        get_polygon="poligono",
        get_fill_color="_cor",
        get_line_color=LINHA_TERRITORIO,
        line_width_min_pixels=1,
        stroked=True,
        filled=True,
        pickable=False,
    )

    contorno = pdk.Layer(
        "PolygonLayer",
        id="contorno-do-piaui",
        data=[{"poligono": [[list(p) for p in anel] for anel in piaui]}],
        get_polygon="poligono",
        get_line_color=CONTORNO_PIAUI,
        line_width_min_pixels=2,
        stroked=True,
        filled=False,
        pickable=False,
    )
    # Ordem = ordem de desenho: sombra, areas, contorno — e os pontos por cima.
    return [mascara, camada_territorios, contorno]


CAMADA_PONTOS = "pontos"


def pontos(df: pd.DataFrame, cor: str, tooltip: str, altura: int = 620,
           raio_m: int | str = 9000, base: list[pdk.Layer] | None = None,
           chave: str | None = None):
    """Desenha os municipios como circulos coloridos sobre o mapa do estado.

    `cor` e a coluna com [r, g, b]. `raio_m` e um valor fixo em metros ou o nome
    de uma coluna (veja `raio_por_valor`). O raio acompanha o zoom, mas com piso
    e teto em pixels: o ponto nunca some no zoom do estado inteiro nem vira um
    borrao ao aproximar.

    Com `chave`, o mapa vira **clicavel**: clicar num municipio devolve a linha
    correspondente (use `municipio_clicado`), e clicar no vazio limpa. Sem
    `chave`, o mapa e so leitura — que e o padrao das abas que nao usam o
    clique. A selecao exige `id` em TODAS as camadas, inclusive as de contexto.
    """
    camada = pdk.Layer(
        "ScatterplotLayer",
        id=CAMADA_PONTOS,
        data=df,
        get_position="[longitude, latitude]",
        get_fill_color=cor,
        get_radius=raio_m,
        radius_min_pixels=7,
        radius_max_pixels=22,
        opacity=0.85,
        stroked=True,
        get_line_color=[255, 255, 255],
        line_width_min_pixels=1,
        pickable=True,
        auto_highlight=True,
    )
    return st.pydeck_chart(
        pdk.Deck(
            layers=[*(base or []), camada],
            initial_view_state=visao(altura),
            # None: o Streamlit escolhe o mapa-base claro ou escuro pelo tema.
            map_style=None,
            tooltip={"html": tooltip, "style": {"fontSize": "12px"}},
        ),
        height=altura,   # largura: 'stretch' (padrao) — acompanha o container
        key=chave,
        on_select="rerun" if chave else "ignore",
        selection_mode="single-object",
    )


def municipio_clicado(evento) -> dict | None:
    """A linha do municipio clicado no mapa, ou None se ninguem foi clicado."""
    objetos = (getattr(evento, "selection", None) or {}).get("objects") or {}
    escolhidos = objetos.get(CAMADA_PONTOS) or []
    return escolhidos[0] if escolhidos else None


def legenda_categorias(cores: dict, titulo: str = "Legenda") -> None:
    itens = "".join(
        f'<span class="leg-item"><i style="background:{cor}"></i>{rotulo}</span>'
        for rotulo, cor in cores.items()
    )
    st.markdown(
        f'<div class="legenda"><b>{titulo}:</b> {itens}</div>', unsafe_allow_html=True
    )


def legenda_gradiente(vmin: float, vmax: float, titulo: str = "Legenda",
                      escala: list[str] | None = None, casas: int = 0) -> None:
    escala = escala or VIRIDIS
    st.markdown(
        f'<div class="legenda"><b>{titulo}:</b>'
        f'<span class="leg-min">{vmin:.{casas}f}</span>'
        f'<i class="leg-barra" style="background:linear-gradient(90deg,{",".join(escala)})"></i>'
        f'<span class="leg-max">{vmax:.{casas}f}</span></div>',
        unsafe_allow_html=True,
    )

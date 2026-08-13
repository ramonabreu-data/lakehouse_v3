"""Mapa de pontos do painel (pydeck) — enquadramento, paletas e legenda.

Compartilhado pelas abas que plotam municipios. Tres decisoes vivem aqui:

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

import math

import pandas as pd
import pydeck as pdk
import streamlit as st

# Extremidades do Piaui (N, S, O, L). Delta do Parnaiba no norte, divisa com a
# Bahia no sul, rio Parnaiba a oeste, divisa com o Ceara a leste.
PIAUI = (-2.74, -10.93, -45.99, -40.37)

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


def pontos(df: pd.DataFrame, cor: str, tooltip: str, altura: int = 620,
           raio_m: int | str = 9000) -> None:
    """Desenha os municipios como circulos coloridos sobre o mapa do estado.

    `cor` e a coluna com [r, g, b]. `raio_m` e um valor fixo em metros ou o nome
    de uma coluna (veja `raio_por_valor`). O raio acompanha o zoom, mas com piso
    e teto em pixels: o ponto nunca some no zoom do estado inteiro nem vira um
    borrao ao aproximar.
    """
    camada = pdk.Layer(
        "ScatterplotLayer",
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
    st.pydeck_chart(
        pdk.Deck(
            layers=[camada],
            initial_view_state=visao(altura),
            # None: o Streamlit escolhe o mapa-base claro ou escuro pelo tema.
            map_style=None,
            tooltip={"html": tooltip, "style": {"fontSize": "12px"}},
        ),
        height=altura,   # largura: 'stretch' (padrao) — acompanha o container
    )


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

"""Gera `docs/arquitetura.svg` — o caminho do dado, com os logos das ferramentas.

Por que um SVG gerado por script, e não um diagrama desenhado à mão:

* **Self-contained.** Os logos entram embutidos no arquivo (path inline para os
  do simple-icons, `<image>` base64 para o resto). Um arquivo só, sem CDN — o
  README abre igual no GitHub, no VS Code e offline.
* **Editável de verdade.** Mudar uma etapa é mudar um item de `ETAPAS` aqui;
  o layout (posições, setas, larguras) se recalcula sozinho.

Rodar:  python3 docs/gerar_arquitetura.py
"""

import base64
import re
from pathlib import Path

RAIZ = Path(__file__).resolve().parent
LOGOS = RAIZ / "logos"
DESTINO = RAIZ / "arquitetura.svg"

# ---------------------------------------------------------------- paleta ----
# Fundo claro fixo: o SVG é uma imagem, então não acompanha o tema do leitor.
# Um cartão claro e explícito fica legível tanto no tema claro quanto no escuro
# (no escuro lê-se como um cartão de papel, que é o efeito desejado).
FUNDO = "#f6f8fa"
CARTAO = "#ffffff"
BORDA = "#d5dbe2"
TITULO = "#1f2933"
TEXTO = "#52616f"
SETA = "#9aa5b1"
FAIXA = "#eef2f6"
DESTAQUE = "#1a7f5a"

LARGURA_ETAPA, ALTURA_ETAPA = 176, 132
ESPACO = 40
MARGEM = 32


def _simple_icon(nome: str) -> tuple[str, str]:
    """(path `d`, cor) de um SVG do simple-icons — 1 path só, viewBox 0 0 24 24."""
    texto = (LOGOS / f"{nome}.svg").read_text()
    cor = re.search(r'fill="(#[0-9A-Fa-f]{3,8})"', texto).group(1)
    caminho = re.search(r'<path\s+d="([^"]+)"', texto).group(1)
    return caminho, cor


def icone(nome: str, x: float, y: float, lado: float) -> str:
    """Logo do simple-icons desenhado inline, escalado para `lado` pixels."""
    caminho, cor = _simple_icon(nome)
    escala = lado / 24
    return (f'<g transform="translate({x:.1f},{y:.1f}) scale({escala:.4f})">'
            f'<path d="{caminho}" fill="{cor}"/></g>')


def icone_png(arquivo: str, x: float, y: float, lado: float) -> str:
    """Logo que só existe em bitmap (Iceberg), embutido em base64."""
    dados = base64.b64encode((LOGOS / arquivo).read_bytes()).decode()
    return (f'<image x="{x:.1f}" y="{y:.1f}" width="{lado}" height="{lado}" '
            f'preserveAspectRatio="xMidYMid meet" '
            f'xlink:href="data:image/png;base64,{dados}"/>')


# Cada etapa: (título, subtítulo, [logos]). O logo é ("si", nome) para os do
# simple-icons (1 path, vira inline) ou ("png", arquivo) para os que só existem
# em bitmap — Iceberg, Nessie e Dremio não estão no simple-icons.
ETAPAS = [
    ("Origens", "banco · CSV · API",
     [("si", "postgresql"), ("si", "mongodb")]),
    ("MinIO · entrada", "arquivo cru, como chegou",
     [("si", "minio")]),
    ("Spark + Jupyter", "notebook refina e valida",
     [("si", "apachespark"), ("si", "jupyter")]),
    ("Nessie + Iceberg", "tabela versionada · MinIO armazém",
     [("png", "nessie.png"), ("png", "iceberg.png")]),
    ("Dremio", "views curadas por edição",
     [("png", "dremio.png")]),
    ("Streamlit", "painel SEMARH",
     [("si", "streamlit")]),
]


def desenhar_logos(logos, centro_x: float, topo_y: float, lado: float) -> str:
    """Fileira de logos centrada — 1 ou 2 por etapa."""
    passo = lado + 12
    inicio = centro_x - (len(logos) * passo - 12) / 2
    saida = []
    for i, logo in enumerate(logos):
        x = inicio + i * passo
        if logo[0] == "si":
            saida.append(icone(logo[1], x, topo_y, lado))
        else:
            saida.append(icone_png(logo[1], x, topo_y, lado))
    return "".join(saida)


def texto(conteudo: str, x: float, y: float, tamanho: int, cor: str,
          peso: str = "400", ancora: str = "middle") -> str:
    return (f'<text x="{x:.1f}" y="{y:.1f}" text-anchor="{ancora}" '
            f'font-family="DejaVu Sans, Verdana, sans-serif" font-size="{tamanho}" '
            f'font-weight="{peso}" fill="{cor}">{conteudo}</text>')


def gerar() -> str:
    n = len(ETAPAS)
    largura = MARGEM * 2 + n * LARGURA_ETAPA + (n - 1) * ESPACO
    y_faixa_topo = MARGEM + 8
    altura_faixa = 58
    y_etapas = y_faixa_topo + altura_faixa + 34
    # Folga maior embaixo: e onde entram as setas da automacao e os rotulos
    # delas. Com o vao curto de antes, a seta virava um risco solto na tela.
    y_faixa_base = y_etapas + ALTURA_ETAPA + 62
    altura = y_faixa_base + altura_faixa + MARGEM

    partes = [
        f'<svg xmlns="http://www.w3.org/2000/svg" xmlns:xlink="http://www.w3.org/1999/xlink" '
        f'width="{largura}" height="{altura}" viewBox="0 0 {largura} {altura}">',
        f'<rect width="{largura}" height="{altura}" rx="14" fill="{FUNDO}"/>',
        '<defs><marker id="seta" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{SETA}"/></marker>'
        '<marker id="seta-verde" viewBox="0 0 10 10" refX="9" refY="5" '
        f'markerWidth="7" markerHeight="7" orient="auto-start-reverse">'
        f'<path d="M 0 0 L 10 5 L 0 10 z" fill="{DESTAQUE}"/></marker></defs>',
    ]

    # ---- faixa de cima: quem dá acesso ao que está embaixo ----------------
    partes.append(f'<rect x="{MARGEM}" y="{y_faixa_topo}" width="{largura - 2 * MARGEM}" '
                  f'height="{altura_faixa}" rx="10" fill="{FAIXA}"/>')
    partes.append(texto("ACESSO", MARGEM + 18, y_faixa_topo + 24, 11, TEXTO, "700", "start"))
    partes.append(texto("Caddy — HTTPS e subdomínios  ·  Supabase — login e sessão",
                        MARGEM + 18, y_faixa_topo + 43, 13, TITULO, "400", "start"))
    partes.append(icone("caddy", largura - MARGEM - 78, y_faixa_topo + 15, 28))
    partes.append(icone("supabase", largura - MARGEM - 40, y_faixa_topo + 15, 28))

    # ---- fileira principal: o caminho do dado -----------------------------
    for i, (titulo, sub, logos) in enumerate(ETAPAS):
        x = MARGEM + i * (LARGURA_ETAPA + ESPACO)
        centro = x + LARGURA_ETAPA / 2
        partes.append(f'<rect x="{x}" y="{y_etapas}" width="{LARGURA_ETAPA}" '
                      f'height="{ALTURA_ETAPA}" rx="12" fill="{CARTAO}" '
                      f'stroke="{BORDA}" stroke-width="1"/>')
        partes.append(desenhar_logos(logos, centro, y_etapas + 20, 38))
        partes.append(texto(titulo, centro, y_etapas + 88, 14, TITULO, "700"))
        # Subtitulo quebrado em duas linhas quando nao cabe.
        palavras, linhas, atual = sub.split(), [], ""
        for palavra in palavras:
            if len(atual) + len(palavra) + 1 > 26:
                linhas.append(atual)
                atual = palavra
            else:
                atual = f"{atual} {palavra}".strip()
        linhas.append(atual)
        for j, linha in enumerate(linhas[:2]):
            partes.append(texto(linha, centro, y_etapas + 106 + j * 14, 11, TEXTO))

        if i < n - 1:
            x1 = x + LARGURA_ETAPA + 8
            x2 = x + LARGURA_ETAPA + ESPACO - 8
            ym = y_etapas + ALTURA_ETAPA / 2
            partes.append(f'<line x1="{x1}" y1="{ym}" x2="{x2}" y2="{ym}" '
                          f'stroke="{SETA}" stroke-width="2" marker-end="url(#seta)"/>')

    # ---- faixa de baixo: quem reexecuta tudo sozinho ----------------------
    partes.append(f'<rect x="{MARGEM}" y="{y_faixa_base}" width="{largura - 2 * MARGEM}" '
                  f'height="{altura_faixa}" rx="10" fill="{FAIXA}"/>')
    partes.append(texto("AUTOMAÇÃO — todo dia às 07h", MARGEM + 18, y_faixa_base + 24,
                        11, TEXTO, "700", "start"))
    partes.append(texto("Celery (beat + worker) e Redis refazem o caminho inteiro "
                        "e recriam as views",
                        MARGEM + 18, y_faixa_base + 43, 13, TITULO, "400", "start"))
    partes.append(icone("celery", largura - MARGEM - 78, y_faixa_base + 15, 28))
    partes.append(icone("redis", largura - MARGEM - 40, y_faixa_base + 15, 28))

    # Setas da automacao subindo para as DUAS etapas que ela refaz — sem elas,
    # "refaz o caminho inteiro" nao diz onde a carga toca.
    for indice, rotulo in ((2, "reexecuta o notebook"), (4, "recria as views")):
        x_alvo = MARGEM + indice * (LARGURA_ETAPA + ESPACO) + LARGURA_ETAPA / 2
        partes.append(f'<line x1="{x_alvo}" y1="{y_faixa_base - 6}" x2="{x_alvo}" '
                      f'y2="{y_etapas + ALTURA_ETAPA + 10}" stroke="{DESTAQUE}" '
                      f'stroke-width="1.6" stroke-dasharray="5 4" marker-end="url(#seta-verde)"/>')
        # Tarja da cor do fundo atras do rotulo: a linha tracejada passa por
        # tras dele, e sem a mascara o texto fica riscado ao meio.
        largura_rotulo = len(rotulo) * 5.6 + 12
        partes.append(f'<rect x="{x_alvo - largura_rotulo / 2:.1f}" y="{y_faixa_base - 29}" '
                      f'width="{largura_rotulo:.1f}" height="15" fill="{FUNDO}"/>')
        partes.append(texto(rotulo, x_alvo, y_faixa_base - 18, 10, DESTAQUE, "600"))

    partes.append('</svg>')
    return "".join(partes)


DESTINO.write_text(gerar())
print(f"escrito: {DESTINO} ({DESTINO.stat().st_size / 1024:.1f} KB)")

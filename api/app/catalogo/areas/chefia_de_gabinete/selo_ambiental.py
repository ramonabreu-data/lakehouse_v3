"""Selo Ambiental — motor comum das edicoes.

Espelha o painel: em `app_semarh/bis/chefia_de_gabinete/selo_ambiental.py` um
modulo so serve as duas edicoes, porque o refinamento entrega o MESMO contrato
de colunas para 2025 e 2026. Aqui vale igual — a unica diferenca e o `auditor`,
que so a fonte de 2025 traz.

Cada edicao publica quatro conjuntos, um por view do refinamento:

    selo_ambiental           consolidado, um registro por municipio
    selo_ambiental_fases     um registro por municipio E fase (base do BI)
    por_tipo_de_selo         quantos municipios por resultado
    por_criterios_atendidos  quantos municipios por numero de criterios
"""

from __future__ import annotations

from app.catalogo.areas.chefia_de_gabinete import AREA
from app.motores.dremio import fonte
from app.nucleo import Campo, Conjunto

RAIZ = "refinamento.semarh_painel.chefia_gabinete.selos_ambientais"

# Colunas do resultado por municipio, identicas nas duas edicoes.
_MUNICIPIO = (
    Campo("municipio", "texto", "Nome do municipio", agrupavel=True),
    Campo("processo", "texto", "Numero do processo administrativo"),
    Campo("cod_ibge", "inteiro", "Codigo do municipio na fonte"),
    Campo("territorio_desenvolvimento", "texto", "Territorio de desenvolvimento", agrupavel=True),
    Campo("situacao", "texto", "Situacao do processo (ex.: Com selo)", agrupavel=True),
    Campo("resultado", "texto", "Resultado da apuracao (ex.: Selo B, Nao elegivel)", agrupavel=True),
    Campo("selo", "texto", "Categoria do selo conquistado (A, B, C); vazio se nao houve", agrupavel=True),
    Campo("tem_selo", "booleano", "Municipio conquistou selo", agrupavel=True),
    Campo("pontos", "decimal", "Pontuacao apurada"),
    Campo("criterios_atendidos", "inteiro", "Quantidade de criterios atendidos", agrupavel=True),
    Campo("habilitado", "booleano", "Municipio habilitado na edicao", agrupavel=True),
    Campo("pacto_ambiental", "booleano", "Municipio aderiu ao pacto ambiental", agrupavel=True),
    Campo("latitude", "decimal", "Latitude da sede municipal", filtravel=False),
    Campo("longitude", "decimal", "Longitude da sede municipal", filtravel=False),
)

_AUDITOR = Campo("auditor", "texto", "Auditor responsavel pela analise", agrupavel=True)
_FASE = Campo("fase", "inteiro", "Fase do processo de avaliacao", agrupavel=True)


def _com_auditor(campos: tuple[Campo, ...], incluir: bool) -> tuple[Campo, ...]:
    return campos + (_AUDITOR,) if incluir else campos


def edicao(ano: int, *, tem_auditor: bool) -> tuple[Conjunto, ...]:
    """Os quatro conjuntos de uma edicao do Selo Ambiental."""
    espaco = f"{RAIZ}.selos_ambientais_{ano}"
    return (
        Conjunto(
            slug=f"selo-ambiental-{ano}",
            area=AREA,
            fonte=fonte(f"{espaco}.selo_ambiental"),
            titulo=f"Selo Ambiental {ano} — resultado por municipio",
            descricao=(
                f"Resultado consolidado da edicao {ano}: um registro por municipio, com pontuacao, "
                "criterios atendidos, selo conquistado e coordenadas da sede. E a visao para mapa e "
                "para ranking."
            ),
            campos=_com_auditor(_MUNICIPIO, tem_auditor),
            ordem_padrao=("-pontos", "municipio"),
        ),
        Conjunto(
            slug=f"selo-ambiental-{ano}-fases",
            area=AREA,
            fonte=fonte(f"{espaco}.selo_ambiental_fases"),
            titulo=f"Selo Ambiental {ano} — por fase",
            descricao=(
                f"Detalhe da edicao {ano} fase a fase: um registro por municipio E fase do processo. "
                "E a fonte que o painel usa para montar a tela do BI, e a mais granular da edicao."
            ),
            campos=_com_auditor((_FASE,) + _MUNICIPIO, tem_auditor),
            ordem_padrao=("municipio", "fase"),
        ),
        Conjunto(
            slug=f"selo-ambiental-{ano}-por-selo",
            area=AREA,
            fonte=fonte(f"{espaco}.por_tipo_de_selo"),
            titulo=f"Selo Ambiental {ano} — municipios por resultado",
            descricao=(
                f"Contagem de municipios por resultado da edicao {ano} (Selo A, B, C, nao elegivel...). "
                "Ja vem agregado pelo refinamento: sao poucas linhas, prontas para grafico de barras."
            ),
            campos=(
                Campo("resultado", "texto", "Resultado da apuracao", agrupavel=True),
                Campo("n_municipios", "inteiro", "Quantidade de municipios com esse resultado"),
            ),
            ordem_padrao=("-n_municipios",),
        ),
        Conjunto(
            slug=f"selo-ambiental-{ano}-por-criterios",
            area=AREA,
            fonte=fonte(f"{espaco}.por_criterios_atendidos"),
            titulo=f"Selo Ambiental {ano} — municipios por criterios atendidos",
            descricao=(
                f"Distribuicao dos municipios da edicao {ano} pelo numero de criterios atendidos. "
                "`criterios_atendidos` vazio agrupa quem nao teve apuracao."
            ),
            campos=(
                Campo("criterios_atendidos", "inteiro", "Quantidade de criterios atendidos", agrupavel=True),
                Campo("n_municipios", "inteiro", "Quantidade de municipios nessa faixa"),
            ),
            ordem_padrao=("criterios_atendidos",),
        ),
    )

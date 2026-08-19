"""Acoes do secretario nos municipios.

Duas views do mesmo refinamento, com granularidades diferentes: uma linha por
acao (`acoes`) e uma linha por municipio, ja com as contagens (`municipios`).
O painel usa as duas juntas para o mapa de cobertura.
"""

from __future__ import annotations

from app.catalogo.areas.chefia_de_gabinete import AREA
from app.motores.dremio import fonte
from app.nucleo import Campo, Conjunto

RAIZ = "refinamento.semarh_painel.chefia_gabinete.acoes_secretario"

CONJUNTOS = (
    Conjunto(
        slug="acoes-secretario",
        area=AREA,
        fonte=fonte(f"{RAIZ}.acoes"),
        titulo="Acoes do secretario",
        descricao=(
            "Uma linha por acao realizada em municipio, com data, territorio e natureza. "
            "`agenda_politica` marca a acao de agenda politica — o refinamento junta as duas "
            "origens numa tabela so e usa essa coluna para separa-las."
        ),
        campos=(
            Campo("data", "data", "Data da acao", agrupavel=True),
            Campo("ano", "inteiro", "Ano da acao", agrupavel=True),
            Campo("mes", "inteiro", "Mes da acao (1 a 12)", agrupavel=True),
            Campo("municipio", "texto", "Municipio onde a acao ocorreu", agrupavel=True),
            Campo("cod_ibge", "inteiro", "Codigo do municipio na fonte"),
            Campo("territorio", "texto", "Territorio de desenvolvimento", agrupavel=True),
            Campo("acao", "texto", "Descricao da acao"),
            Campo("agenda_politica", "booleano", "Acao de agenda politica", agrupavel=True),
            Campo("aderente_pacto", "booleano", "Municipio aderente ao pacto", agrupavel=True),
            Campo("populacao", "inteiro", "Populacao do municipio"),
            Campo("latitude", "decimal", "Latitude da sede municipal", filtravel=False),
            Campo("longitude", "decimal", "Longitude da sede municipal", filtravel=False),
        ),
        ordem_padrao=("-data", "municipio"),
    ),
    Conjunto(
        slug="municipios-acoes",
        area=AREA,
        fonte=fonte(f"{RAIZ}.municipios"),
        titulo="Cobertura de acoes por municipio",
        descricao=(
            "Um registro por municipio, com quantas acoes recebeu e as datas de primeira e ultima "
            "visita. As colunas `*_sem_agenda_politica` repetem as contagens desconsiderando as "
            "acoes de agenda politica. E a visao de cobertura do mapa."
        ),
        campos=(
            Campo("cod_ibge", "inteiro", "Codigo do municipio na fonte"),
            Campo("municipio", "texto", "Nome do municipio", agrupavel=True),
            Campo("territorio", "texto", "Territorio de desenvolvimento", agrupavel=True),
            Campo("populacao", "inteiro", "Populacao estimada"),
            Campo("aderente_pacto", "booleano", "Municipio aderiu ao pacto", agrupavel=True),
            Campo("visitado", "booleano", "Recebeu ao menos uma acao", agrupavel=True),
            Campo("visitado_sem_agenda_politica", "booleano", "Visitado fora de agenda politica", agrupavel=True),
            Campo("qtd_acoes", "inteiro", "Total de acoes no municipio"),
            Campo("qtd_acoes_sem_agenda_politica", "inteiro", "Acoes fora de agenda politica"),
            Campo("primeira_visita", "data", "Data da primeira acao"),
            Campo("ultima_visita", "data", "Data da acao mais recente"),
            Campo("primeira_visita_sem_agenda_politica", "data", "Primeira acao fora de agenda politica"),
            Campo("ultima_visita_sem_agenda_politica", "data", "Ultima acao fora de agenda politica"),
            Campo("latitude", "decimal", "Latitude da sede municipal", filtravel=False),
            Campo("longitude", "decimal", "Longitude da sede municipal", filtravel=False),
        ),
        ordem_padrao=("-qtd_acoes", "municipio"),
    ),
)

"""Chefia de Gabinete — mesma divisao do painel (`app_semarh/bis/chefia_de_gabinete`).

So a Area mora aqui. Os modulos de conjuntos nao sao importados neste arquivo de
proposito: eles importam a AREA daqui, e o import de volta faria ciclo. Quem
reune tudo e `app/catalogo/areas/__init__.py`.
"""

from __future__ import annotations

from app.nucleo import Area

AREA = Area(
    slug="chefia-de-gabinete",
    titulo="Chefia de Gabinete",
    descricao=(
        "Conjuntos da Chefia de Gabinete da SEMARH: o Selo Ambiental (edicoes 2025 e 2026) "
        "e as acoes do secretario nos municipios."
    ),
)

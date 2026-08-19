"""Reuniao dos conjuntos publicados.

**Para publicar dado novo, mexe-se so aqui e num modulo de conjunto.** Nenhuma
rota precisa ser escrita: as rotas sao geradas a partir deste registro.

Passo a passo:

1. Escreva (ou edite) um modulo em `app/catalogo/areas/<area>/`, expondo `CONJUNTOS`.
2. Se for area nova, crie o pacote com a `AREA` no `__init__.py`.
3. Acrescente o modulo em MODULOS e a area em AREAS, abaixo.

Os imports sao explicitos, e nao por varredura de diretorio: um modulo com erro
de digitacao falha no boot, em vez de sumir do catalogo em silencio.
"""

from __future__ import annotations

from app.catalogo.areas.chefia_de_gabinete import AREA as CHEFIA_DE_GABINETE
from app.catalogo.areas.chefia_de_gabinete import (
    acoes_secretario,
    seloambi_2025,
    seloambi_2026,
)
from app.nucleo import Area, Conjunto

# A ordem daqui e a ordem em que as areas aparecem na documentacao.
AREAS: tuple[Area, ...] = (CHEFIA_DE_GABINETE,)

# A ordem daqui e a ordem dos conjuntos dentro de cada area.
MODULOS = (seloambi_2026, seloambi_2025, acoes_secretario)

CONJUNTOS: tuple[Conjunto, ...] = tuple(
    conjunto for modulo in MODULOS for conjunto in modulo.CONJUNTOS
)

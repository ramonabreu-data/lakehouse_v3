"""Selo Ambiental **2026**. Nesta edicao a fonte nao traz o nome do auditor."""

from __future__ import annotations

from app.catalogo.areas.chefia_de_gabinete import selo_ambiental

CONJUNTOS = selo_ambiental.edicao(2026, tem_auditor=False)

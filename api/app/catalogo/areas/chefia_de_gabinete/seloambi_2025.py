"""Selo Ambiental **2025**. A fonte desta edicao traz quem analisou cada fase,
entao os conjuntos ganham a coluna `auditor` (filtravel e agrupavel)."""

from __future__ import annotations

from app.catalogo.areas.chefia_de_gabinete import selo_ambiental

CONJUNTOS = selo_ambiental.edicao(2025, tem_auditor=True)

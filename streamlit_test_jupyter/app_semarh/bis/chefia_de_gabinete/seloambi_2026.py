"""BI Selo Ambiental **2026** — aba da Chefia de Gabinete.

Toda a tela vive em `selo_ambiental.py`; aqui fica só o que é desta edição.
Nesta edição os 224 municípios postularam, então o cartão "não postulados" fica
em 0, e a fonte não traz o nome do auditor — a coluna não aparece na tabela.
"""

from app_semarh.bis.chefia_de_gabinete import selo_ambiental

EDICAO = selo_ambiental.Edicao(
    ano=2026,
    fonte="refinamento.semarh_painel.chefia_gabinete.selos_ambientais"
          ".selos_ambientais_2026.selo_ambiental_fases",
    notebook="semarh_painel/refinamento_selo_ambiental",
)


def render(user: dict | None = None) -> None:
    selo_ambiental.render(EDICAO)

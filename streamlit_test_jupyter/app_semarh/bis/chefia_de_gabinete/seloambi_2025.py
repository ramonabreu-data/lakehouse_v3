"""BI Selo Ambiental **2025** — aba da Chefia de Gabinete.

Toda a tela vive em `selo_ambiental.py`; aqui fica só o que é desta edição.
Duas coisas que 2026 não tem e aparecem sozinhas na tela, porque o refinamento
já as entregou no mesmo contrato de colunas:

- **12 municípios não postulados** — o cartão "Municípios não postulados" deixa
  de ser 0 e a situação entra no filtro e no mapa.
- **Auditor por fase** — a fonte de 2025 traz quem analisou cada fase, então a
  coluna `Auditor` aparece na tabela de pontuação.
"""

from app_semarh.bis.chefia_de_gabinete import selo_ambiental

EDICAO = selo_ambiental.Edicao(
    ano=2025,
    fonte="refinamento.semarh_painel.chefia_gabinete.selos_ambientais"
          ".selos_ambientais_2025.selo_ambiental_fases",
    notebook="semarh_painel/refinamento_selo_ambiental_2025",
)


def render(user: dict | None = None) -> None:
    selo_ambiental.render(EDICAO)

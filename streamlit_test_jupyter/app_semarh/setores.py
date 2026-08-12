"""Modelo de navegacao: setores (botoes na sidebar) e os BIs (abas) de cada um.

Para implementar um BI: escreva o modulo em `app_semarh/bis/` com uma funcao
`render(user)` e troque o placeholder pela funcao real na lista `bis` do setor.
"""

from app_semarh.bis import selo_ambiental
from app_semarh.bis.em_construcao import render_para

SETORES = [
    {"slug": "gestao", "titulo": "Superintendência de Gestão", "bis": []},
    {"slug": "meio_ambiente", "titulo": "Superintendência de Meio Ambiente", "bis": []},
    {
        "slug": "chefia",
        "titulo": "Chefia de Gabinete",
        "bis": [
            {"slug": "selo_2026", "titulo": "Selo Ambiental 2026", "render": selo_ambiental.render},
            {"slug": "selo_2025", "titulo": "Selo Ambiental 2025", "render": render_para("Selo Ambiental 2025")},
            {"slug": "acoes_secretario", "titulo": "Ações Secretário", "render": render_para("Ações Secretário")},
            {"slug": "compromissos_governo", "titulo": "Compromissos de Governo", "render": render_para("Compromissos de Governo")},
            {"slug": "relatorio_agenda", "titulo": "Relatório Agenda Adm Gov", "render": render_para("Relatório Agenda Adm Gov")},
            {"slug": "pacto_animais", "titulo": "Pacto pelos Animais", "render": render_para("Pacto pelos Animais")},
            {"slug": "pacto_queimadas", "titulo": "Pacto Piauí Sem Queimadas", "render": render_para("Pacto Piauí Sem Queimadas")},
        ],
    },
    {"slug": "psi_pilares", "titulo": "PSI&Pilares II", "bis": []},
]

"""Modelo de navegacao: setores (botoes na sidebar) e os BIs de cada um.

Para adicionar um BI novo: escreva o modulo em `app_semarh/bis/` com uma funcao
`render(user)` e registre-o na lista `bis` do setor correspondente. Um setor sem
BIs aparece como botao, mas abre vazio ("nenhum BI ainda").
"""

from app_semarh.bis import selo_ambiental

SETORES = [
    {"slug": "gestao", "titulo": "Superintendência de Gestão", "bis": []},
    {"slug": "meio_ambiente", "titulo": "Superintendência de Meio Ambiente", "bis": []},
    {
        "slug": "chefia",
        "titulo": "Chefia de Gabinete",
        "bis": [
            {
                "slug": "selo_ambiental_2026",
                "titulo": "Selo Ambiental 2026",
                "render": selo_ambiental.render,
            },
        ],
    },
    {"slug": "psi_pilares", "titulo": "PSI&Pilares II", "bis": []},
]

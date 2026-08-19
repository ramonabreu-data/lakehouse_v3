"""Carimbo da ultima atualizacao do refinamento.

O mesmo arquivo que o painel Streamlit le (`/estado/atualizacao.json`, gravado
pelo celery-worker no fim da carga). Aqui ele serve de VERSAO do dado: entra na
chave do cache, entao publicar dado novo invalida as respostas guardadas na
hora, sem esperar o TTL vencer.
"""

from __future__ import annotations

import json
import os
from pathlib import Path


def arquivo() -> Path:
    return Path(os.getenv("ARQUIVO_ESTADO", "/estado/atualizacao.json"))


def versao_do_dado() -> str:
    """Carimbo ISO da ultima carga, ou string vazia se ainda nao houve uma."""
    try:
        return str(json.loads(arquivo().read_text()).get("atualizado_em") or "")
    except (OSError, ValueError):
        # Sem arquivo (primeira subida) ou conteudo pela metade: o cache passa a
        # valer so pelo TTL. Degradar assim e melhor que falhar a requisicao.
        return ""

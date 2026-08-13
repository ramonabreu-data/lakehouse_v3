"""Bloco de atualização dos dados na sidebar.

Mostra **sempre** quando os dados foram atualizados pela última vez — não
importa se a carga foi automática (Celery, todo dia às 7h) ou manual — e traz o
botão para disparar uma carga na hora, com barra de progresso.

O botão não processa nada aqui: ele publica a tarefa `painel.atualizar` na fila
do Celery e acompanha o andamento. Quem executa é o `celery-worker`, o mesmo que
roda a carga diária — um caminho só para os dois casos.
"""

from __future__ import annotations

import os
import time
from datetime import datetime
from zoneinfo import ZoneInfo

import streamlit as st

from app_semarh.dados import estado_atualizacao

FUSO = ZoneInfo(os.getenv("TZ", "America/Fortaleza"))
BROKER = os.getenv("CELERY_BROKER_URL", "redis://redis:6379/0")
TAREFA = "painel.atualizar"
# Teto de espera do botao: a carga leva ~1,5 min; 10 min cobre um Dremio frio.
ESPERA_MAX_S = 600
DIAS = ("segunda", "terça", "quarta", "quinta", "sexta", "sábado", "domingo")


@st.cache_resource
def _celery():
    """Cliente da fila. Só publica tarefas — nenhum processamento no painel."""
    from celery import Celery

    return Celery("painel-cliente", broker=BROKER, backend=BROKER)


def carimbo() -> str:
    """"Atualizado em ..." legível, do jeito que o usuário lê a data."""
    estado = estado_atualizacao()
    bruto = estado.get("atualizado_em")
    if not bruto:
        return "Ainda sem atualização registrada."
    try:
        quando = datetime.fromisoformat(bruto).astimezone(FUSO)
    except ValueError:
        return bruto
    origem = estado.get("origem", "")
    sufixo = f" ({origem})" if origem else ""
    return f"{DIAS[quando.weekday()]}, {quando:%d/%m/%Y às %H:%M}{sufixo}"


def _acompanhar(resultado, barra) -> tuple[bool, str]:
    """Segue a tarefa até terminar, movendo a barra. Devolve (ok, mensagem)."""
    limite = time.monotonic() + ESPERA_MAX_S
    while time.monotonic() < limite:
        estado = resultado.state
        if estado == "SUCCESS":
            barra.progress(100, text="Concluído")
            return True, "Dados atualizados."
        if estado == "FAILURE":
            return False, str(resultado.info)[:400]
        info = resultado.info if isinstance(resultado.info, dict) else {}
        percentual = int(info.get("percentual", 5))
        etapa = info.get("etapa", "Na fila, aguardando o worker")
        barra.progress(min(percentual, 99), text=f"{etapa}… {min(percentual, 99)}%")
        time.sleep(1.5)
    return False, "A atualização passou do tempo limite. Veja `docker compose logs celery-worker`."


def bloco_sidebar() -> None:
    """Rodapé da sidebar: última atualização + botão de atualizar agora."""
    barra_area = st.sidebar.empty()
    st.sidebar.caption(f"🕒 **Atualizado em:** {carimbo()}")

    if st.sidebar.button("Atualizar dados agora", key="btn_atualizar", width='stretch'):
        try:
            resultado = _celery().send_task(TAREFA, kwargs={"forcar": True})
        except Exception as erro:
            st.sidebar.error(f"Não foi possível falar com a fila: {erro}")
            return
        with barra_area.container():
            barra = st.progress(0, text="Enviando para a fila…")
            ok, mensagem = _acompanhar(resultado, barra)
        if ok:
            # O carimbo novo tambem invalida o cache das consultas (ver dados.py),
            # entao o rerun ja traz o dado novo na tela.
            st.sidebar.success(mensagem)
            time.sleep(1)
            st.rerun()
        else:
            st.sidebar.error(mensagem)

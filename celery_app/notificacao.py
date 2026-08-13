"""Notificação no Telegram a cada atualização do painel.

Credenciais vêm **só do ambiente** (`.env` da stack, que está no `.gitignore`):

    TELEGRAM_BOT_TOKEN   token do BotFather
    TELEGRAM_CHAT_ID     id do grupo (negativo) ou da conversa privada
    TELEGRAM_NOTIFICAR   `sucesso` (padrão), `falha` ou `tudo`/`nada`

Sem token ou sem chat, o envio vira no-op silencioso — a atualização não falha
por causa da notificação.

Descobrir o `TELEGRAM_CHAT_ID` (depois de adicionar o bot ao grupo e mandar
qualquer mensagem lá):

    docker compose exec celery-worker python3 -m celery_app.notificacao --descobrir
    docker compose exec celery-worker python3 -m celery_app.notificacao --teste
"""

from __future__ import annotations

import logging
import os

import requests

log = logging.getLogger(__name__)

API = "https://api.telegram.org/bot{token}/{metodo}"
TIMEOUT = 15


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def _chat() -> str:
    return os.getenv("TELEGRAM_CHAT_ID", "").strip()


def _quando_notificar() -> str:
    return os.getenv("TELEGRAM_NOTIFICAR", "tudo").strip().lower()


def ativo(evento: str = "sucesso") -> bool:
    """Ha credencial e este tipo de evento deve ser notificado?"""
    if not (_token() and _chat()):
        return False
    escolha = _quando_notificar()
    if escolha in ("nada", "off", "false"):
        return False
    return escolha in ("tudo", evento)


def _chamar(metodo: str, **dados) -> dict:
    resposta = requests.post(API.format(token=_token(), metodo=metodo), json=dados, timeout=TIMEOUT)
    corpo = resposta.json()
    if not corpo.get("ok"):
        # Nunca registra o token: a URL fica de fora da mensagem de erro.
        raise RuntimeError(f"Telegram recusou {metodo}: {corpo.get('description', corpo)}")
    return corpo["result"]


def enviar(texto: str, evento: str = "sucesso") -> bool:
    """Manda a mensagem. Devolve False (sem levantar) se nao der para enviar."""
    if not ativo(evento):
        return False
    try:
        _chamar("sendMessage", chat_id=_chat(), text=texto,
                parse_mode="HTML", disable_web_page_preview=True)
        return True
    except Exception as erro:
        log.warning("não foi possível notificar no Telegram: %s", erro)
        return False


def identidade() -> dict:
    """Dados do bot — serve para validar o token sem expor nada."""
    return _chamar("getMe")


def descobrir_chats() -> list[dict]:
    """Chats que já falaram com o bot (grupo precisa ter uma mensagem enviada)."""
    vistos, saida = set(), []
    for item in _chamar("getUpdates"):
        for chave in ("message", "channel_post", "my_chat_member"):
            chat = (item.get(chave) or {}).get("chat")
            if chat and chat["id"] not in vistos:
                vistos.add(chat["id"])
                saida.append({"id": chat["id"], "tipo": chat.get("type"),
                              "nome": chat.get("title") or chat.get("username") or chat.get("first_name")})
    return saida


if __name__ == "__main__":  # pequena CLI de diagnostico
    import sys

    argumento = sys.argv[1] if len(sys.argv) > 1 else "--info"
    if not _token():
        print("TELEGRAM_BOT_TOKEN não está no ambiente do container.")
        raise SystemExit(1)

    if argumento == "--descobrir":
        chats = descobrir_chats()
        if not chats:
            print("Nenhum chat encontrado. Adicione o bot ao grupo, mande uma mensagem lá "
                  "(ex.: /start) e rode de novo.")
        for chat in chats:
            print(f"  TELEGRAM_CHAT_ID={chat['id']:<16} {chat['tipo']:<10} {chat['nome']}")
    elif argumento == "--teste":
        ok = enviar("✅ <b>Painel SEMARH</b>\nNotificação de teste — o bot está configurado.")
        print("mensagem enviada." if ok else "não enviou: confira TELEGRAM_CHAT_ID/TELEGRAM_NOTIFICAR.")
    else:
        bot = identidade()
        print(f"bot @{bot['username']} ({bot['first_name']}) — token válido")
        print(f"chat configurado: {_chat() or '(vazio — rode --descobrir)'}")

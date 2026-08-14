"""Notificação no Telegram a cada atualização do painel.

Credenciais vêm **só do ambiente** (`.env` da stack, que está no `.gitignore`):

    TELEGRAM_BOT_TOKEN   token do BotFather
    TELEGRAM_CHAT_ID     id do grupo (negativo) ou da conversa privada. Aceita
                         vários separados por vírgula e, em grupo com tópicos,
                         `chat:topico`
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
# O Telegram recusa mensagem acima de 4096 caracteres. A margem cobre o rodapé
# de continuação que `_fatiar` acrescenta.
LIMITE = 3900


def _token() -> str:
    return os.getenv("TELEGRAM_BOT_TOKEN", "").strip()


def _chats() -> list[tuple[str, int | None]]:
    """Destinos configurados: `(chat_id, tópico)`.

    `TELEGRAM_CHAT_ID` aceita mais de um destino separado por vírgula — dá para
    avisar no grupo e no privado ao mesmo tempo. Em grupo com tópicos (fórum),
    use `chat:topico`, por exemplo `-1002...:12`.
    """
    destinos = []
    for bruto in os.getenv("TELEGRAM_CHAT_ID", "").split(","):
        bruto = bruto.strip()
        if not bruto:
            continue
        # o id do chat pode comecar com "-": so o ULTIMO ":" separa o topico
        if ":" in bruto:
            chat, _, topico = bruto.rpartition(":")
            destinos.append((chat.strip(), int(topico)))
        else:
            destinos.append((bruto, None))
    return destinos


def _quando_notificar() -> str:
    return os.getenv("TELEGRAM_NOTIFICAR", "tudo").strip().lower()


def ativo(evento: str = "sucesso") -> bool:
    """Ha credencial e este tipo de evento deve ser notificado?"""
    if not (_token() and _chats()):
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


def _fatiar(texto: str) -> list[str]:
    """Divide em mensagens dentro do limite do Telegram, quebrando em LINHAS.

    Cortar no meio de uma linha partiria uma tag HTML (`<code>` sem `</code>`) e
    o Telegram recusaria a mensagem inteira. Uma linha sozinha maior que o
    limite e improvavel aqui — se acontecer, vai inteira e o proprio Telegram
    reclama, que e melhor do que enviar HTML quebrado em silencio.
    """
    if len(texto) <= LIMITE:
        return [texto]
    partes, atual = [], []
    for linha in texto.split("\n"):
        if atual and sum(len(x) + 1 for x in atual) + len(linha) > LIMITE:
            partes.append("\n".join(atual))
            atual = []
        atual.append(linha)
    if atual:
        partes.append("\n".join(atual))
    total = len(partes)
    return [f"{p}\n\n<i>({i}/{total})</i>" for i, p in enumerate(partes, 1)]


def enviar(texto: str, evento: str = "sucesso") -> bool:
    """Manda a mensagem a todos os destinos configurados.

    Devolve True se ao menos um recebeu. Um destino com problema (bot removido
    do grupo, id errado) nao impede os outros nem derruba a atualizacao.
    """
    if not ativo(evento):
        return False
    entregues = 0
    for chat, topico in _chats():
        for pedaco in _fatiar(texto):
            dados = {"chat_id": chat, "text": pedaco,
                     "parse_mode": "HTML", "disable_web_page_preview": True}
            if topico is not None:
                dados["message_thread_id"] = topico
            try:
                _chamar("sendMessage", **dados)
                entregues += 1
            except Exception as erro:
                log.warning("não foi possível notificar %s no Telegram: %s", chat, erro)
                break
    return entregues > 0


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
        destinos = _chats()
        if not destinos:
            print("nenhum destino configurado — rode --descobrir")
        for chat, topico in destinos:
            print(f"  destino: {chat}" + (f" (tópico {topico})" if topico else ""))

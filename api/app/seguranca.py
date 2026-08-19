"""Quem pode chamar a API.

Dois modos, os dois ja emitiveis pela stack:

- **Chave de API** (`X-API-Key`), para aplicacao servidor-a-servidor. As chaves
  ficam no .env, no formato `nome:chave`, e o nome so serve para o log saber
  quem chamou.
- **JWT do Supabase GoTrue** (`Authorization: Bearer`), para aplicacao web com
  usuario logado — o mesmo token que o painel Streamlit ja recebe no login.
  Validado localmente com o JWT_SECRET, sem ida ao GoTrue a cada requisicao.

Nao ha terceiro caminho: sem uma das duas coisas a resposta e 401.
"""

from __future__ import annotations

import logging
import os
import secrets
import time
from dataclasses import dataclass

import jwt

registrador = logging.getLogger(__name__)

# Publico (`aud`) exigido no JWT. Vazio = nao confere, que e o caso desta
# stack: o GoTrue sobe sem GOTRUE_JWT_AUD e emite `aud` vazio. A conferencia so
# acrescenta algo quando o MESMO segredo assina tokens de publicos diferentes;
# aqui o JWT_SECRET pertence a esta instalacao e mais nada.
def publico_esperado() -> str:
    return os.getenv("API_JWT_PUBLICO", "").strip()


@dataclass(frozen=True)
class Identidade:
    tipo: str    # "aplicacao" | "usuario" | "anonimo"
    nome: str

    @property
    def rotulo(self) -> str:
        return f"{self.tipo}:{self.nome}"


def auth_ativa() -> bool:
    return os.getenv("API_AUTH_ATIVA", "true").strip().lower() not in ("false", "0", "nao")


def chaves_configuradas() -> dict[str, str]:
    """`API_CHAVES=painel:abc,app-mobile:def` -> {chave: nome}."""
    cru = os.getenv("API_CHAVES", "")
    chaves: dict[str, str] = {}
    for item in cru.split(","):
        item = item.strip()
        if not item:
            continue
        nome, separador, chave = item.partition(":")
        if not separador or not chave.strip():
            registrador.warning("Entrada de API_CHAVES ignorada: falta o formato nome:chave.")
            continue
        chaves[chave.strip()] = nome.strip()
    return chaves


def verificar_chave(chave: str | None) -> Identidade | None:
    if not chave:
        return None
    for candidata, nome in chaves_configuradas().items():
        # compare_digest: comparacao de tempo constante, sem atalho no 1o byte.
        if secrets.compare_digest(chave, candidata):
            return Identidade("aplicacao", nome)
    return None


def verificar_jwt(token: str | None) -> Identidade | None:
    segredo = os.getenv("JWT_SECRET", "")
    if not token or not segredo:
        return None
    publico = publico_esperado()
    try:
        claims = jwt.decode(
            token,
            segredo,
            algorithms=["HS256"],          # fixo: fecha a porta do alg=none
            audience=publico or None,
            options={"require": ["exp"], "verify_aud": bool(publico)},
        )
    except jwt.PyJWTError:
        # Expirado, forjado, malformado — para o cliente e tudo a mesma coisa.
        return None
    if claims.get("exp", 0) < time.time():
        return None
    return Identidade("usuario", str(claims.get("email") or claims.get("sub") or "sem-identificacao"))


def identificar(chave_de_api: str | None, autorizacao: str | None) -> Identidade | None:
    """Resolve a identidade a partir dos cabecalhos, na ordem mais barata."""
    identidade = verificar_chave(chave_de_api)
    if identidade is not None:
        return identidade
    if not autorizacao:
        return None
    esquema, _, credencial = autorizacao.partition(" ")
    if esquema.lower() != "bearer" or not credencial:
        return None
    # Bearer pode trazer JWT ou, por conveniencia, a propria chave de API:
    # muito cliente HTTP so sabe mandar Authorization.
    return verificar_jwt(credencial) or verificar_chave(credencial)

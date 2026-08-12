"""Normalizacao, validade e renovacao de sessoes do Supabase."""

from __future__ import annotations

import time
from typing import Any

from . import supabase_client

REFRESH_MARGIN_SECONDS = 60
VALIDATION_TTL_SECONDS = 30


def normalize(payload: dict[str, Any]) -> dict[str, Any]:
    access = payload.get("access_token")
    refresh = payload.get("refresh_token")
    if not access or not refresh:
        raise supabase_client.AuthError("Resposta de autenticacao incompleta.")
    expires_at = payload.get("expires_at")
    if not expires_at:
        expires_at = int(time.time()) + int(payload.get("expires_in", 3600))
    return {
        "access_token": access,
        "refresh_token": refresh,
        "expires_at": int(expires_at),
        "user": payload.get("user"),
        "validated_at": int(time.time()),
    }


def restore(raw: dict[str, Any]) -> dict[str, Any]:
    now = int(time.time())
    if int(raw.get("expires_at", 0)) <= now + REFRESH_MARGIN_SECONDS:
        return normalize(supabase_client.refresh(str(raw.get("refresh_token", ""))))

    session = normalize(raw)
    last_validation = int(raw.get("validated_at", 0))
    if not raw.get("user") or now - last_validation >= VALIDATION_TTL_SECONDS:
        session["user"] = supabase_client.get_user(session["access_token"])
        session["validated_at"] = now
    else:
        session["validated_at"] = last_validation
    return session

"""Cliente minimo, exclusivamente server-side, para o Supabase Auth (GoTrue)."""

from __future__ import annotations

import os
import time
from typing import Any

import httpx
import jwt


class AuthError(RuntimeError):
    """Erro esperado de autenticacao, sem incluir tokens ou credenciais."""


class AdminError(RuntimeError):
    """Erro de operacao administrativa (criar/remover usuario)."""


def _url() -> str:
    value = os.environ.get("SUPABASE_URL", "").rstrip("/")
    if not value:
        raise AuthError("SUPABASE_URL nao foi configurada.")
    return value


def _endpoint(path: str) -> str:
    """Monta a rota para GoTrue direto ou para Supabase atras de gateway.

    Nesta stack o GoTrue e acessado diretamente e o prefixo fica vazio. Uma
    instalacao com Kong pode configurar SUPABASE_AUTH_PATH_PREFIX=/auth/v1.
    """
    prefix = os.environ.get("SUPABASE_AUTH_PATH_PREFIX", "").strip("/")
    base = _url()
    return f"{base}/{prefix}{path}" if prefix else f"{base}{path}"


def _headers(access_token: str | None = None) -> dict[str, str]:
    headers = {"Content-Type": "application/json"}
    anon_key = os.environ.get("SUPABASE_ANON_KEY", "")
    if anon_key:
        headers["apikey"] = anon_key
    if access_token:
        headers["Authorization"] = f"Bearer {access_token}"
    return headers


def _request(method: str, path: str, *, token: str | None = None,
             payload: dict[str, Any] | None = None) -> dict[str, Any]:
    try:
        response = httpx.request(
            method, _endpoint(path), headers=_headers(token),
            json=payload, timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise AuthError("O servico de autenticacao esta indisponivel.") from exc
    if response.status_code >= 400:
        # Nao propaga o corpo: provedores podem devolver detalhes sensiveis.
        raise AuthError("Credenciais ou sessao invalidas.")
    if not response.content:
        return {}
    return response.json()


def sign_in(email: str, password: str) -> dict[str, Any]:
    return _request(
        "POST", "/token?grant_type=password",
        payload={"email": email, "password": password},
    )


def sign_up(email: str, password: str) -> dict[str, Any]:
    """Cria a conta no GoTrue.

    Com GOTRUE_MAILER_AUTOCONFIRM=true a resposta ja traz a sessao (tokens); sem
    autoconfirmacao, retorna so o usuario e o login exige confirmar o e-mail.
    """
    return _request("POST", "/signup", payload={"email": email, "password": password})


def refresh(refresh_token: str) -> dict[str, Any]:
    return _request(
        "POST", "/token?grant_type=refresh_token",
        payload={"refresh_token": refresh_token},
    )


def get_user(access_token: str) -> dict[str, Any]:
    return _request("GET", "/user", token=access_token)


def sign_out(access_token: str) -> None:
    _request("POST", "/logout", token=access_token)


# ---------------------------------------------------------------------------
# Admin API (somente o usuario master usa). Autentica com um JWT service_role
# assinado localmente com o JWT_SECRET do GoTrue.
# ---------------------------------------------------------------------------

def _service_token() -> str:
    secret = os.environ.get("JWT_SECRET", "")
    if not secret:
        raise AdminError("JWT_SECRET nao configurado (deve bater com o .env da stack).")
    now = int(time.time())
    claims = {
        "role": "service_role",
        "aud": "authenticated",
        "iss": "streamlit-dashboard",
        "iat": now,
        "exp": now + 300,
    }
    return jwt.encode(claims, secret, algorithm="HS256")


def _admin_request(method: str, path: str, *, payload: dict[str, Any] | None = None) -> httpx.Response:
    try:
        return httpx.request(
            method, _endpoint(path), headers=_headers(_service_token()),
            json=payload, timeout=10.0,
        )
    except httpx.HTTPError as exc:
        raise AdminError("O servico de autenticacao esta indisponivel.") from exc


def _admin_error(response: httpx.Response, fallback: str) -> str:
    try:
        body = response.json()
    except ValueError:
        return fallback
    for key in ("msg", "message", "error_description", "error"):
        value = body.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()
    return fallback


def admin_list_users() -> list[dict[str, Any]]:
    response = _admin_request("GET", "/admin/users?per_page=1000")
    if response.status_code >= 400:
        raise AdminError(_admin_error(response, "Falha ao listar usuarios."))
    data = response.json()
    return data.get("users", []) if isinstance(data, dict) else []


def admin_create_user(email: str, password: str) -> dict[str, Any]:
    response = _admin_request(
        "POST", "/admin/users",
        payload={"email": email, "password": password, "email_confirm": True},
    )
    if response.status_code >= 400:
        raise AdminError(_admin_error(response, "Nao foi possivel criar o usuario."))
    return response.json()


def admin_update_user(user_id: str, **fields: Any) -> None:
    response = _admin_request("PUT", f"/admin/users/{user_id}", payload=fields)
    if response.status_code >= 400:
        raise AdminError(_admin_error(response, "Nao foi possivel atualizar o usuario."))


def admin_delete_user(user_id: str) -> None:
    response = _admin_request("DELETE", f"/admin/users/{user_id}")
    if response.status_code >= 400:
        raise AdminError(_admin_error(response, "Nao foi possivel remover o usuario."))


def ensure_master() -> None:
    """Garante o usuario master a partir do vars.env.

    Cria se nao existir; se ja existir, mantem a senha em sincronia com o
    `vars.env` (o arquivo e a fonte unica da verdade da credencial do master).
    """
    email = os.environ.get("AUTH_MASTER_EMAIL", "").strip().lower()
    password = os.environ.get("AUTH_MASTER_PASSWORD", "")
    if not email or not password:
        return
    match = next(
        (u for u in admin_list_users() if u.get("email", "").lower() == email), None
    )
    if match is None:
        admin_create_user(email, password)
    else:
        admin_update_user(match["id"], password=password)


def is_master(user: dict[str, Any] | None) -> bool:
    master = os.environ.get("AUTH_MASTER_EMAIL", "").strip().lower()
    email = (user or {}).get("email", "").strip().lower()
    return bool(master) and email == master

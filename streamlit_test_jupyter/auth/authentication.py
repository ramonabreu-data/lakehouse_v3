"""Gate central de autenticacao (Supabase) com papel de usuario master.

- Signup publico e DESLIGADO no GoTrue. Ninguem se cadastra sozinho.
- Um usuario master (AUTH_MASTER_EMAIL) e criado no primeiro boot e e o unico
  que cria/remove usuarios, por um painel de administracao na barra lateral.
- Os demais usuarios apenas visualizam a aplicacao.

Uso no app:

    from auth.authentication import require_auth
    user = require_auth()   # para o run e mostra o login se preciso
"""

from __future__ import annotations

import os
import re
from typing import Any

import streamlit as st

from . import cookies as cookie_store
from . import session as session_service
from . import supabase_client

AUTH_KEYS = ("authenticated", "auth_session", "user")

_EMAIL_RE = re.compile(r"[^@\s]+@[^@\s]+\.[^@\s]+")


def _clear_state() -> None:
    for key in AUTH_KEYS:
        st.session_state.pop(key, None)


def _bootstrap_master() -> None:
    """Garante o usuario master uma vez por sessao do Streamlit."""
    if st.session_state.get("_master_ready"):
        return
    try:
        supabase_client.ensure_master()
        st.session_state["_master_ready"] = True
    except supabase_client.AdminError:
        # GoTrue pode ainda estar subindo; tenta de novo no proximo run.
        pass


def _apply_session(cookies, session: dict[str, Any]) -> None:
    # NAO grava o cookie aqui: o st.rerun() abaixo descartaria o render do
    # componente e o cookie nunca chegaria ao navegador (=> logout a cada
    # refresh). Marca a persistencia; ela e efetivada no proximo run, que
    # COMPLETA (renderiza o dashboard) e ai o cookie e realmente gravado.
    st.session_state.update(
        authenticated=True, auth_session=session, user=session.get("user")
    )
    st.session_state.pop("_logged_out", None)
    st.session_state["_persistir_cookie"] = True
    st.rerun()


def _login_screen(cookies) -> None:
    st.title("Acessar o painel")
    st.caption("Entre com seu e-mail e senha. As contas sao criadas pelo administrador.")
    with st.form("login_form", clear_on_submit=False):
        email = st.text_input("E-mail", autocomplete="email")
        password = st.text_input("Senha", type="password", autocomplete="current-password")
        submitted = st.form_submit_button("Entrar", type="primary", use_container_width=True)
    if submitted:
        try:
            session = session_service.normalize(supabase_client.sign_in(email.strip(), password))
        except supabase_client.AuthError:
            st.error("E-mail ou senha invalidos.")
            return
        _apply_session(cookies, session)


def _admin_panel(current_user: dict[str, Any]) -> None:
    """Barra lateral do master: criar e remover usuarios visualizadores."""
    with st.sidebar.expander("Administrar usuarios", expanded=False):
        st.caption("Crie contas para quem vai visualizar o painel.")
        with st.form("admin_create_user", clear_on_submit=True):
            new_email = st.text_input("E-mail do novo usuario")
            new_pwd = st.text_input("Senha", type="password", help="Minimo de 6 caracteres.")
            create = st.form_submit_button("Criar usuario", use_container_width=True)
        if create:
            new_email = new_email.strip()
            if not _EMAIL_RE.fullmatch(new_email):
                st.error("E-mail invalido.")
            elif len(new_pwd) < 6:
                st.error("Senha muito curta: use ao menos 6 caracteres.")
            else:
                try:
                    supabase_client.admin_create_user(new_email, new_pwd)
                    st.success(f"Usuario {new_email} criado.")
                except supabase_client.AdminError as exc:
                    st.error(str(exc))

        st.divider()
        try:
            users = supabase_client.admin_list_users()
        except supabase_client.AdminError as exc:
            st.error(str(exc))
            users = []
        master_email = os.environ.get("AUTH_MASTER_EMAIL", "").strip().lower()
        outros = [u for u in users if u.get("email", "").lower() != master_email]
        st.caption(f"{len(outros)} usuario(s) visualizador(es).")
        for u in outros:
            linha, acao = st.columns([3, 1])
            linha.write(u.get("email", "—"))
            if acao.button("Remover", key=f"del_{u.get('id')}"):
                try:
                    supabase_client.admin_delete_user(u["id"])
                    st.rerun()
                except supabase_client.AdminError as exc:
                    st.error(str(exc))


def _logout(cookies, session: dict[str, Any]) -> None:
    try:
        supabase_client.sign_out(session["access_token"])
    except (supabase_client.AuthError, KeyError):
        pass
    cookie_store.clear(cookies)
    _clear_state()
    # No proximo run o cookie pode ainda nao ter sido sincronizado pelo navegador:
    # forcamos a tela de login ate ele sumir de fato.
    st.session_state["_logged_out"] = True
    st.query_params.clear()
    st.rerun()


def require_auth() -> dict[str, Any] | None:
    """Restaura/valida a sessao ou para o run depois de mostrar o login."""
    if os.environ.get("AUTH_ENABLED", "true").lower() not in {"1", "true", "yes"}:
        return {"id": "development", "email": "auth-disabled"}

    try:
        cookies = cookie_store.manager()
    except RuntimeError as exc:
        st.error(f"Autenticacao nao configurada: {exc}")
        st.stop()
    if not cookies.ready():
        st.stop()

    _bootstrap_master()

    # Logout em andamento: ignora o cookie (que pode estar defasado), garante que
    # ele seja apagado e mostra o login. So volta ao normal quando o cookie some.
    if st.session_state.get("_logged_out"):
        cookie_store.clear(cookies)
        if cookie_store.load(cookies) is None:
            st.session_state.pop("_logged_out", None)
        _login_screen(cookies)
        st.stop()

    raw = st.session_state.get("auth_session") or cookie_store.load(cookies)
    if raw:
        try:
            restored = session_service.restore(raw)
            # Persiste o cookie quando a sessao foi renovada OU logo apos o login
            # (flag posta em _apply_session) — este run completa e grava de fato.
            if st.session_state.pop("_persistir_cookie", False) or restored != raw:
                cookie_store.save(cookies, restored)
            st.session_state.update(
                authenticated=True, auth_session=restored, user=restored.get("user")
            )
            user = restored.get("user") or {}
            with st.sidebar:
                st.caption(user.get("email", "Usuario autenticado"))
                if supabase_client.is_master(user):
                    st.caption("Perfil: **administrador**")
                if st.button("Sair", key="auth_logout", use_container_width=True):
                    _logout(cookies, restored)
            if supabase_client.is_master(user):
                _admin_panel(user)
            return user
        except (supabase_client.AuthError, TypeError, ValueError, KeyError):
            cookie_store.clear(cookies)
            _clear_state()

    _login_screen(cookies)
    st.stop()
    return None

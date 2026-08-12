"""Cookie de sessao criptografado no navegador.

Streamlit nao permite que um componente defina HttpOnly. O componente enxerga
somente o ciphertext autenticado; a chave de cifra permanece no servidor.

Inspirado no modulo de auth do projeto `jupyter`. Traz os mesmos dois
monkeypatches de compatibilidade com Streamlit >= 1.36, porque a lib
`streamlit-cookies-manager` 0.2.0 nao tem manutencao.
"""

from __future__ import annotations

import json
import os
from datetime import datetime, timedelta
from typing import Any

from streamlit_cookies_manager import EncryptedCookieManager
from streamlit_cookies_manager import cookie_manager as _cookie_manager

# --- Compatibilidade Streamlit >= 1.36 -------------------------------------
# A lib renderiza o componente de save sempre com a mesma key fixa
# "CookieManager.sync_cookies.save". Desde a 1.36 o Streamlit proibe a mesma key
# duas vezes no mesmo run, entao qualquer execucao que chame save() mais de uma
# vez (ex.: persistir a sessao e, no mesmo rerun, o logout limpar o cookie)
# quebra com StreamlitDuplicateElementKey e derruba o app. Key unica por run.
if not getattr(_cookie_manager.CookieManager.save, "_uniq_key", False):
    def _save_with_unique_key(self) -> None:
        if self._queue:
            import streamlit as st

            seq = st.session_state.get("_cookie_save_seq", 0) + 1
            st.session_state["_cookie_save_seq"] = seq
            self._run_component(
                save_only=True, key=f"CookieManager.sync_cookies.save.{seq}"
            )

    _save_with_unique_key._uniq_key = True
    _cookie_manager.CookieManager.save = _save_with_unique_key

# key_from_parameters vem decorada com o `st.cache` legado (deprecado desde a
# 1.36), que gera aviso a cada boot. Reimplementamos com st.cache_resource.
from streamlit_cookies_manager import encrypted_cookie_manager as _enc  # noqa: E402

if not getattr(_enc.key_from_parameters, "_no_stcache", False):
    import base64 as _b64

    import streamlit as _st
    from cryptography.hazmat.primitives import hashes as _hashes
    from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC as _PBKDF2HMAC

    @_st.cache_resource(show_spinner=False)
    def _key_from_parameters(salt: bytes, iterations: int, password: str) -> bytes:
        kdf = _PBKDF2HMAC(
            algorithm=_hashes.SHA256(), length=32, salt=salt, iterations=iterations
        )
        return _b64.urlsafe_b64encode(kdf.derive(password.encode("utf-8")))

    _key_from_parameters._no_stcache = True
    _enc.key_from_parameters = _key_from_parameters
# ---------------------------------------------------------------------------


def manager() -> EncryptedCookieManager:
    secret = os.environ.get("COOKIE_SECRET", "")
    if len(secret) < 32:
        raise RuntimeError("COOKIE_SECRET deve ter pelo menos 32 caracteres.")
    cookies = EncryptedCookieManager(
        prefix=os.environ.get("COOKIE_PREFIX", "dash_auth_"), password=secret,
    )
    lifetime = int(os.environ.get("COOKIE_MAX_AGE_DAYS", "7"))
    cookies._default_expiry = datetime.now() + timedelta(days=lifetime)
    return cookies


def name() -> str:
    return os.environ.get("COOKIE_NAME", "dash_session")


def load(cookies: EncryptedCookieManager) -> dict[str, Any] | None:
    value = cookies.get(name())
    if not value:
        return None
    try:
        parsed = json.loads(value)
        return parsed if isinstance(parsed, dict) else None
    except (TypeError, ValueError):
        return None


def save(cookies: EncryptedCookieManager, session: dict[str, Any]) -> None:
    cookies[name()] = json.dumps(session, separators=(",", ":"))
    cookies.save()


def clear(cookies: EncryptedCookieManager) -> None:
    if name() in cookies:
        del cookies[name()]
        cookies.save()

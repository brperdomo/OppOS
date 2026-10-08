"""Identity for the dashboard.

Uses Streamlit's native OIDC login (Google Workspace) when `[auth]` is present
in secrets.toml; otherwise falls back to a single local dev user so the app
still runs without configuration. Admins are listed in OPPOS_ADMINS (emails).
"""

from __future__ import annotations

import os
from typing import Any

import streamlit as st

_DEV_FALLBACK = {"email": "local@oppos.dev", "name": "Local User"}


def auth_configured() -> bool:
    try:
        auth = st.secrets.get("auth")  # type: ignore[attr-defined]
    except Exception:
        return False
    return bool(auth and auth.get("client_id") and auth.get("client_secret") and auth.get("cookie_secret"))


def _admin_emails() -> set[str]:
    raw = os.environ.get("OPPOS_ADMINS", "")
    return {e.strip().lower() for e in raw.split(",") if e.strip()}


def _dev_user() -> dict[str, Any]:
    raw = os.environ.get("OPPOS_DEV_USER", "").strip()  # "Name <email>" or "email"
    if raw:
        if "<" in raw and raw.endswith(">"):
            name, email = raw.split("<", 1)
            return {"email": email[:-1].strip().lower(), "name": name.strip() or email[:-1].strip()}
        return {"email": raw.lower(), "name": raw.split("@")[0]}
    return dict(_DEV_FALLBACK)


def current_user() -> dict[str, Any]:
    """{"email", "name", "is_admin", "authenticated"} for the active session."""
    if auth_configured() and getattr(st.user, "is_logged_in", False):
        email = str(getattr(st.user, "email", "") or "").lower()
        name = str(getattr(st.user, "name", "") or email.split("@")[0])
        user = {"email": email, "name": name, "authenticated": True}
    else:
        user = {**_dev_user(), "authenticated": False}
    admins = _admin_emails()
    # OPPOS_ADMINS, when set, is authoritative (with or without sign-in configured).
    # When it is empty, everyone is an admin — fine for single-user dev, set it before SDR rollout.
    user["is_admin"] = (user["email"] in admins) if admins else True
    return user


def require_login() -> dict[str, Any]:
    """Render a sign-in screen and stop the script if auth is configured and the user is signed out."""
    if auth_configured() and not getattr(st.user, "is_logged_in", False):
        st.markdown(
            '<div style="max-width:420px;margin:80px auto;text-align:center;">'
            '<h2 style="margin-bottom:8px;">OppOS</h2>'
            '<p style="color:var(--text-tertiary);margin-bottom:24px;">Sign in with your Nutrient Google account to continue.</p>'
            "</div>",
            unsafe_allow_html=True,
        )
        _, mid, _ = st.columns([2, 1, 2])
        with mid:
            if st.button("Sign in with Google", type="primary", use_container_width=True):
                st.login()
        st.stop()
    return current_user()


def logout_button(label: str = "Sign out") -> None:
    if auth_configured() and getattr(st.user, "is_logged_in", False):
        if st.button(label, use_container_width=True):
            st.logout()

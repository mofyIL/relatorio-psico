from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Literal

import streamlit as st

BackendProvider = Literal["sheets", "supabase"]


@dataclass(frozen=True)
class BackendSettings:
    provider: BackendProvider
    supabase_url: str = ""
    supabase_service_role_key: str = ""
    supabase_anon_key: str = ""
    supabase_storage_bucket: str = "reports"


def _secret(path: str, default: str = "") -> str:
    current: Any = st.secrets
    for part in path.split("."):
        try:
            current = current[part]
        except Exception:
            return default
    return str(current or "").strip()


def get_backend_settings() -> BackendSettings:
    provider = _secret("app.backend_provider", "sheets").lower()
    if provider not in {"sheets", "supabase"}:
        provider = "sheets"
    return BackendSettings(
        provider=provider,  # type: ignore[arg-type]
        supabase_url=_secret("supabase.url"),
        supabase_service_role_key=_secret("supabase.service_role_key"),
        supabase_anon_key=_secret("supabase.anon_key"),
        supabase_storage_bucket=_secret("supabase.storage_bucket", "reports"),
    )


def require_supabase_config(settings: BackendSettings | None = None) -> None:
    settings = settings or get_backend_settings()
    missing = []
    if not settings.supabase_url:
        missing.append("supabase.url")
    if not settings.supabase_service_role_key:
        missing.append("supabase.service_role_key")
    if missing:
        raise RuntimeError(
            "Backend Supabase selecionado, mas faltam segredos: " + ", ".join(missing)
        )


def is_supabase_selected() -> bool:
    return get_backend_settings().provider == "supabase"

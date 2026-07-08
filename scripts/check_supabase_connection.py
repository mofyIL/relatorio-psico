from __future__ import annotations

import os
import sys
import tomllib
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from database import BackendSettings  # noqa: E402
from supabase_repository import SupabaseRepository  # noqa: E402


def load_streamlit_secrets() -> dict[str, Any]:
    path = ROOT / ".streamlit" / "secrets.toml"
    if not path.exists():
        return {}
    with path.open("rb") as handle:
        return tomllib.load(handle)


def secret_value(secrets: dict[str, Any], section: str, key: str, env_name: str) -> str:
    env_value = os.getenv(env_name, "").strip()
    if env_value:
        return env_value
    section_data = secrets.get(section, {})
    if isinstance(section_data, dict):
        return str(section_data.get(key, "") or "").strip()
    return ""


def main() -> int:
    try:
        secrets = load_streamlit_secrets()
    except tomllib.TOMLDecodeError as exc:
        print(f"Não foi possível ler .streamlit/secrets.toml: TOML inválido ({exc}).")
        print("Confira chaves duplicadas ou seções repetidas. Nenhum segredo foi exibido.")
        return 2
    settings = BackendSettings(
        provider="supabase",
        supabase_url=secret_value(secrets, "supabase", "url", "SUPABASE_URL"),
        supabase_service_role_key=secret_value(
            secrets,
            "supabase",
            "service_role_key",
            "SUPABASE_SERVICE_ROLE_KEY",
        ),
        supabase_anon_key=secret_value(secrets, "supabase", "anon_key", "SUPABASE_ANON_KEY"),
        supabase_storage_bucket=secret_value(
            secrets,
            "supabase",
            "storage_bucket",
            "SUPABASE_STORAGE_BUCKET",
        )
        or "reports",
    )

    missing = []
    if not settings.supabase_url:
        missing.append("SUPABASE_URL ou supabase.url")
    if not settings.supabase_service_role_key:
        missing.append("SUPABASE_SERVICE_ROLE_KEY ou supabase.service_role_key")
    if missing:
        print("Configuração incompleta: " + ", ".join(missing))
        return 2

    try:
        repo = SupabaseRepository(settings)
        questionnaire = repo.get_active_questionnaire()
    except Exception as exc:
        print(f"Falha ao consultar Supabase: {type(exc).__name__}.")
        print("Verifique URL, service role, rede e se as migrations/seed foram executadas.")
        return 1
    if not questionnaire:
        print("Nenhum questionário ativo encontrado.")
        return 1

    questions = questionnaire.get("questions") or []
    closed_count = sum(1 for item in questions if item.get("question_type") == "likert_frequency")
    open_count = sum(1 for item in questions if item.get("question_type") == "open_text")
    domains = questionnaire.get("domains") or []

    print("Conexão Supabase OK.")
    print(f"Questionário ativo: {questionnaire.get('code')} / {questionnaire.get('version')}")
    print(f"Domínios: {len(domains)}")
    print(f"Perguntas fechadas: {closed_count}")
    print(f"Perguntas abertas: {open_count}")

    if closed_count != 56 or open_count != 4:
        print("Atenção: o instrumento V2 esperado tem 56 itens fechados e 4 perguntas abertas.")
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

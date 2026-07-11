from __future__ import annotations

import hashlib
import hmac
import json
import random
import ssl
import time
import unicodedata
import secrets as secure_secrets
import zipfile
from datetime import date, datetime, timedelta
from io import BytesIO
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from zoneinfo import ZoneInfo

import pandas as pd
import qrcode
import streamlit as st
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials as UserCredentials
from googleapiclient.discovery import build
from googleapiclient.errors import HttpError
from googleapiclient.http import MediaIoBaseDownload, MediaIoBaseUpload

from database import get_backend_settings, is_supabase_selected
from reporting import (
    QUESTIONARIO as REPORT_QUESTIONARIO,
    ReportConfig,
    build_critical_alerts,
    calculate_question_results,
    generate_company_reports,
    normalize_dataframe_columns,
    normalize_text,
    validate_questionnaire_columns,
)
from supabase_repository import SupabaseRepository


# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

TZ = ZoneInfo("America/Sao_Paulo")
PARTICIPANT_NOTICE_VERSION = "2026-07-11-v2"
PARTICIPANT_NOTICE_TEMPLATES = {
    PARTICIPANT_NOTICE_VERSION: """
Você está sendo convidado(a) a responder uma pesquisa coletiva sobre condições psicossociais relacionadas ao trabalho.

### Objetivo

A pesquisa busca identificar percepções coletivas sobre organização do trabalho, liderança, demandas, apoio, autonomia e sentido do trabalho. Os resultados serão usados para apoiar ações de prevenção e melhoria das condições de trabalho.

### Confidencialidade

- A organização receberá apenas resultados coletivos.
- Não serão entregues relatórios individuais ao empregador.
- Grupos com menos de **{min_group} participantes** não terão relatório separado; outras supressões podem ser aplicadas para reduzir o risco de identificação.
- Evite escrever informações que identifiquem você ou colegas nas respostas abertas.

### Dados tratados

As respostas incluem a área de trabalho predefinida pela organização e, se você decidir informar, seu cargo ou função atual. O formulário não solicita nome, CPF ou e-mail. O cargo ou função é opcional e não define o grupo usado no relatório.

### Limites

A pesquisa não realiza diagnóstico clínico individual. Ela é uma ferramenta de escuta e apoio à gestão coletiva de riscos psicossociais e deve ser interpretada junto com outras evidências técnicas.
""".strip(),
}
STATUS_VALIDOS = {
    "COLETA",
    "AGUARDANDO_APROVACAO",
    "LIBERADO",
    "GERANDO",
    "GERADO",
    "CANCELADO",
}

EMPRESAS_HEADERS = [
    "EMPRESA_ID",
    "NOME",
    "CNPJ",
    "RESPONSAVEL",
    "EMAIL",
    "ATIVO",
    "CRIADO_EM",
]

CICLOS_HEADERS = [
    "CICLO_ID",
    "EMPRESA_ID",
    "ANO",
    "TOKEN",
    "PARTICIPANT_TOKEN",
    "PIN_HASH",
    "FUNCIONARIOS_CONTRATADOS",
    "PRECO_POR_FUNCIONARIO",
    "VALOR_MINIMO",
    "VALIDO_ATE",
    "STATUS",
    "INICIO_EM",
    "ENCERRADO_EM",
    "GERADO_EM",
    "DRIVE_FILE_ID",
    "DRIVE_FILE_NAME",
    "ZIP_SHA256",
    "VERSAO",
    "PAGAMENTO_OK",
    "ULTIMA_ACAO_EM",
    "OBSERVACOES",
]

RELATORIOS_HEADERS = [
    "CICLO_ID",
    "EMPRESA_ID",
    "TIPO",
    "ESCOPO",
    "FILE_ID",
    "FILE_NAME",
    "GERADO_EM",
    "VISIVEL_CLIENTE",
    "N_RESPONDENTES",
    "ZIP_SHA256",
    "VERSAO",
]

SHEET_EMPRESAS = "Empresas"
SHEET_CICLOS = "Ciclos"
SHEET_RELATORIOS = "Relatorios"
SHEET_AUDITORIA = "Auditoria"
SHEET_RESPOSTAS = "Respostas"

AUDITORIA_HEADERS = [
    "EVENTO_ID",
    "OCORRIDO_EM",
    "TIPO_ATOR",
    "ATOR",
    "EMPRESA_ID",
    "CICLO_ID",
    "ACAO",
    "DETALHES_JSON",
]

SUPABASE_STATUS_TO_LEGACY = {
    "draft": "COLETA",
    "collecting": "COLETA",
    "closed": "AGUARDANDO_APROVACAO",
    "approved": "LIBERADO",
    "generating": "GERANDO",
    "generated": "GERADO",
    "cancelled": "CANCELADO",
}

LEGACY_STATUS_TO_SUPABASE = {
    "COLETA": "collecting",
    "AGUARDANDO_APROVACAO": "closed",
    "LIBERADO": "approved",
    "GERANDO": "generating",
    "GERADO": "generated",
    "CANCELADO": "cancelled",
}

LIKERT_OPTIONS = [
    "Nunca / quase nunca",
    "Raramente",
    "Às vezes",
    "Frequentemente",
    "Sempre",
]

st.set_page_config(
    page_title="Painel de Indicadores Psicossociais",
    page_icon="📊",
    layout="wide",
)


# =============================================================================
# UTILITÁRIOS
# =============================================================================

def now_sp() -> datetime:
    return datetime.now(TZ)


def iso_now() -> str:
    return now_sp().replace(microsecond=0).isoformat()


def parse_datetime(value: Any) -> datetime | None:
    if value is None or str(value).strip() == "":
        return None
    text = str(value).strip()
    try:
        # ISO é o formato usado internamente; dayfirst fica reservado aos carimbos do Forms.
        if "T" in text or (len(text) >= 10 and text[4:5] == "-" and text[7:8] == "-"):
            parsed = pd.to_datetime(text, errors="raise")
        else:
            parsed = pd.to_datetime(text, dayfirst=True, errors="raise")
        if isinstance(parsed, pd.Timestamp):
            result = parsed.to_pydatetime()
        else:
            result = parsed
        if result.tzinfo is None:
            result = result.replace(tzinfo=TZ)
        return result.astimezone(TZ)
    except Exception:
        return None


def parse_date(value: Any) -> date | None:
    dt = parse_datetime(value)
    if dt:
        return dt.date()
    try:
        return date.fromisoformat(str(value).strip())
    except Exception:
        return None


def as_int(value: Any, default: int = 0) -> int:
    try:
        return int(float(str(value).replace(",", ".")))
    except Exception:
        return default


def as_float(value: Any, default: float = 0.0) -> float:
    """Converte números em formatos comuns no Brasil e em formato internacional."""
    try:
        text = str(value).strip().replace(" ", "")
        if not text:
            return default
        if "," in text and "." in text:
            # O último separador observado é tratado como separador decimal.
            if text.rfind(",") > text.rfind("."):
                text = text.replace(".", "").replace(",", ".")
            else:
                text = text.replace(",", "")
        elif "," in text:
            text = text.replace(".", "").replace(",", ".")
        return float(text)
    except Exception:
        return default

def is_yes(value: Any) -> bool:
    return normalize_text(value) in {"SIM", "S", "TRUE", "1", "YES"}


def brl(value: float) -> str:
    formatted = f"{value:,.2f}"
    return "R$ " + formatted.replace(",", "X").replace(".", ",").replace("X", ".")


def safe_status(value: Any) -> str:
    status = normalize_text(value).replace(" ", "_")
    return status if status in STATUS_VALIDOS else "COLETA"


def credential_pepper() -> str:
    """Segredo adicional para hashes. Configure app.credential_pepper em produção."""
    return str(get_app_setting("credential_pepper", "")).strip()


def secret_fingerprint(value: str) -> str:
    """Identificador curto para comparar secrets sem expor o valor real."""
    value = str(value or "")
    if not value:
        return "ausente"
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:12]


def make_stored_secret(raw_value: str, context: str) -> str:
    salt = secure_secrets.token_hex(16)
    pepper = credential_pepper()
    payload = f"{context}:{salt}:{raw_value}".encode("utf-8")
    digest = hmac.new(pepper.encode("utf-8"), payload, hashlib.sha256).hexdigest()
    return f"v2${salt}${digest}"


def verify_stored_secret(raw_value: str, stored_value: str, context: str) -> bool:
    stored_value = str(stored_value or "").strip()
    raw_value = str(raw_value or "")
    if not raw_value or not stored_value:
        return False
    if stored_value.startswith("v2$"):
        try:
            _, salt, expected = stored_value.split("$", 2)
        except ValueError:
            return False
        pepper = credential_pepper()
        payload = f"{context}:{salt}:{raw_value}".encode("utf-8")
        actual = hmac.new(pepper.encode("utf-8"), payload, hashlib.sha256).hexdigest()
        return secure_secrets.compare_digest(actual, expected)
    # Compatibilidade com ciclos criados antes desta versão.
    if context.startswith("PIN:"):
        token = context.split(":", 1)[1]
        legacy = hashlib.sha256(f"{token}:{raw_value}".encode("utf-8")).hexdigest()
        return secure_secrets.compare_digest(legacy, stored_value)
    return secure_secrets.compare_digest(raw_value, stored_value)


def pin_hash(token: str, pin: str) -> str:
    return make_stored_secret(pin, f"PIN:{token}")


def verify_pin(token: str, pin: str, expected_hash: str) -> bool:
    return verify_stored_secret(pin, expected_hash, f"PIN:{token}")


def attempt_state(key: str) -> dict[str, Any]:
    return st.session_state.setdefault(key, {"count": 0, "locked_until": 0.0})


def is_locked(key: str) -> tuple[bool, int]:
    state = attempt_state(key)
    remaining = int(max(0, float(state.get("locked_until", 0)) - time.time()))
    return remaining > 0, remaining


def register_failed_attempt(key: str, *, max_attempts: int = 5, lock_seconds: int = 900) -> None:
    state = attempt_state(key)
    state["count"] = int(state.get("count", 0)) + 1
    if state["count"] >= max_attempts:
        state["locked_until"] = time.time() + lock_seconds
        state["count"] = 0


def clear_attempts(key: str) -> None:
    st.session_state.pop(key, None)

def get_query_value(name: str) -> str:
    value = st.query_params.get(name, "")
    if isinstance(value, list):
        return str(value[0]) if value else ""
    return str(value)


def make_company_id(name: str) -> str:
    base = normalize_text(name)
    base = "".join(ch if ch.isalnum() else "_" for ch in base)
    base = "_".join(part for part in base.split("_") if part)
    return f"EMP_{base[:18]}_{secure_secrets.token_hex(2).upper()}"


def make_cycle_id(company_id: str, year: int) -> str:
    return f"{company_id}_{year}_{secure_secrets.token_hex(2).upper()}"


def make_access_credentials() -> tuple[str, str]:
    return secure_secrets.token_urlsafe(32), f"{secure_secrets.randbelow(1_000_000):06d}"


def last_column_letter(column_count: int) -> str:
    result = ""
    number = column_count
    while number:
        number, remainder = divmod(number - 1, 26)
        result = chr(65 + remainder) + result
    return result


def get_app_setting(name: str, default: Any) -> Any:
    try:
        return st.secrets["app"].get(name, default)
    except Exception:
        return default


def campaign_min_group(campaign: dict[str, Any] | pd.Series) -> int:
    configured = as_int(
        campaign.get("min_group_size", campaign.get("MIN_GRUPO", "")),
        0,
    )
    if configured <= 0:
        configured = as_int(get_app_setting("min_group_size", 7), 7)
    return max(2, configured)


def campaign_notice_version(campaign: dict[str, Any] | pd.Series) -> str:
    return str(
        campaign.get("notice_version", campaign.get("AVISO_VERSAO", ""))
        or PARTICIPANT_NOTICE_VERSION
    ).strip()


def parse_area_group_lines(value: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Interpreta uma linha `Área | Grupo`; sem separador, usa o mesmo nome."""
    mappings: list[tuple[str, str]] = []
    errors: list[str] = []
    seen: dict[str, str] = {}
    for line_number, raw_line in enumerate(str(value or "").splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) == 1:
            area = group = parts[0]
        elif len(parts) == 2:
            area, group = parts
        else:
            errors.append(
                f"Linha {line_number}: use somente o formato Área | Grupo de análise."
            )
            continue
        if not area or not group:
            errors.append(f"Linha {line_number}: informe a área e o grupo de análise.")
            continue
        area_key = normalize_text(area)
        group_key = normalize_text(group)
        previous = seen.get(area_key)
        if previous and previous != group_key:
            errors.append(
                f"Linha {line_number}: a área '{area}' aparece associada a mais de um grupo."
            )
            continue
        if previous:
            continue
        seen[area_key] = group_key
        mappings.append((area, group))
    if not mappings and not errors:
        errors.append("Informe pelo menos uma área e seu grupo de análise.")
    return mappings, errors


def load_campaign_sectors(repo: SupabaseRepository, campaign_id: str) -> list[dict[str, Any]]:
    """Carrega as áreas congeladas da campanha com fallback para o repositório V2 inicial."""
    list_method = getattr(repo, "list_campaign_areas", None)
    if not callable(list_method):
        list_method = getattr(repo, "list_campaign_sectors", None)
    if callable(list_method):
        rows = list_method(campaign_id)
    else:
        response = (
            repo.client.table("campaign_sectors")
            .select("*")
            .eq("campaign_id", campaign_id)
            .execute()
        )
        data = getattr(response, "data", None)
        rows = data if isinstance(data, list) else []

    valid_rows: list[dict[str, Any]] = []
    for raw_row in rows:
        if not isinstance(raw_row, dict):
            continue
        row = dict(raw_row)
        area_name = str(row.get("area_name") or row.get("sector_name") or "").strip()
        group_name = str(
            row.get("analysis_group_name") or row.get("group_name") or ""
        ).strip()
        # Compatibilidade imediata com o schema inicial: enquanto a migration
        # não for aplicada, o par pode estar armazenado em sector_name.
        if not group_name and "|" in area_name:
            area_name, group_name = [part.strip() for part in area_name.split("|", 1)]
        if not area_name:
            continue
        group_name = group_name or area_name
        row["sector_name"] = area_name
        row["analysis_group_name"] = group_name
        row["analysis_group_key"] = str(
            row.get("analysis_group_key")
            or row.get("group_id")
            or normalize_header(group_name).lower()
        )
        valid_rows.append(row)
    return sorted(
        valid_rows,
        key=lambda row: (
            as_int(row.get("sort_order"), 999999),
            normalize_text(row.get("sector_name", "")),
        ),
    )


def set_campaign_area_mappings(
    repo: SupabaseRepository,
    campaign_id: str,
    mappings: list[tuple[str, str]],
) -> list[dict[str, Any]]:
    """Congela área→grupo no ciclo, inclusive durante o rollout da migration."""
    set_method = getattr(repo, "set_campaign_areas", None)
    if callable(set_method):
        return list(set_method(campaign_id, mappings) or [])

    # Compatibilidade com o primeiro schema Supabase. A migration 003 separa
    # estes campos; antes dela, o par fica legível em sector_name.
    table = repo.client.table("campaign_sectors")
    table.delete().eq("campaign_id", campaign_id).execute()
    payload = [
        {
            "campaign_id": campaign_id,
            "sector_name": area if normalize_text(area) == normalize_text(group) else f"{area} | {group}",
            "reportable": True,
        }
        for area, group in mappings
    ]
    response = table.insert(payload).execute()
    data = getattr(response, "data", None)
    return data if isinstance(data, list) else []


def backend_is_supabase() -> bool:
    return is_supabase_selected()


@st.cache_resource(show_spinner=False)
def supabase_repository() -> SupabaseRepository:
    return SupabaseRepository(get_backend_settings())


def latest_campaign_report(campaign: dict[str, Any]) -> dict[str, Any]:
    reports = campaign.get("reports") or []
    if not isinstance(reports, list) or not reports:
        return {}
    return sorted(
        reports,
        key=lambda row: str(row.get("generated_at") or ""),
        reverse=True,
    )[0]


def supabase_company_to_legacy(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "EMPRESA_ID": row.get("id", ""),
        "CODIGO_PUBLICO": row.get("public_code", ""),
        "NOME": row.get("trade_name") or row.get("legal_name") or "",
        "CNPJ": row.get("cnpj", ""),
        "RESPONSAVEL": row.get("responsible_name", ""),
        "EMAIL": row.get("responsible_email", ""),
        "ATIVO": "SIM" if row.get("status", "active") == "active" else "NAO",
        "CRIADO_EM": row.get("created_at", ""),
        "__ROW__": row.get("id", ""),
    }


def supabase_campaign_to_legacy(row: dict[str, Any]) -> dict[str, Any]:
    report = latest_campaign_report(row)
    metadata = report.get("metadata") if isinstance(report.get("metadata"), dict) else {}
    questionnaire = row.get("questionnaires") or {}
    return {
        "CICLO_ID": row.get("id", ""),
        "EMPRESA_ID": row.get("company_id", ""),
        "ANO": row.get("cycle_year", ""),
        "TOKEN": row.get("code", ""),
        "PARTICIPANT_TOKEN": row.get("response_code") or row.get("code", ""),
        "PIN_HASH": row.get("access_token_hash", ""),
        "FUNCIONARIOS_CONTRATADOS": row.get("employees_contracted", 0),
        "PRECO_POR_FUNCIONARIO": row.get("price_per_employee", 0),
        "VALOR_MINIMO": row.get("minimum_price", 0),
        "MIN_GRUPO": row.get("min_group_size", 7),
        "VALIDO_ATE": row.get("closes_at", ""),
        "STATUS": SUPABASE_STATUS_TO_LEGACY.get(str(row.get("status", "")), "COLETA"),
        "INICIO_EM": row.get("starts_at", ""),
        "ENCERRADO_EM": row.get("closed_at", ""),
        "GERADO_EM": row.get("generated_at", ""),
        "DRIVE_FILE_ID": report.get("storage_path", ""),
        "DRIVE_FILE_NAME": metadata.get("zip_file_name") or report.get("file_name", ""),
        "ZIP_SHA256": report.get("sha256", ""),
        "VERSAO": report.get("report_version") or questionnaire.get("version", ""),
        "PAGAMENTO_OK": "SIM" if row.get("payment_status") in {"confirmed", "waived"} else "NAO",
        "ULTIMA_ACAO_EM": row.get("updated_at", ""),
        "OBSERVACOES": row.get("notes", ""),
        "__ROW__": row.get("id", ""),
    }


def supabase_report_to_legacy(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "CICLO_ID": row.get("campaign_id", ""),
        "EMPRESA_ID": "",
        "TIPO": row.get("scope_type", ""),
        "ESCOPO": row.get("scope_name", ""),
        "FILE_ID": row.get("storage_path", ""),
        "FILE_NAME": row.get("file_name", ""),
        "GERADO_EM": row.get("generated_at", ""),
        "VISIVEL_CLIENTE": "SIM" if row.get("visible_to_client", True) else "NAO",
        "N_RESPONDENTES": row.get("respondents_count", ""),
        "ZIP_SHA256": row.get("sha256", ""),
        "VERSAO": row.get("report_version", ""),
        "__ROW__": row.get("id", ""),
    }


def supabase_audit_to_legacy(row: dict[str, Any]) -> dict[str, Any]:
    return {
        "EVENTO_ID": row.get("id", ""),
        "OCORRIDO_EM": row.get("created_at", ""),
        "TIPO_ATOR": row.get("actor_type", ""),
        "ATOR": row.get("actor_id", ""),
        "EMPRESA_ID": row.get("company_id", ""),
        "CICLO_ID": row.get("campaign_id", ""),
        "ACAO": row.get("action", ""),
        "DETALHES_JSON": json.dumps(row.get("details") or {}, ensure_ascii=False, sort_keys=True),
        "__ROW__": row.get("id", ""),
    }


def read_supabase_sheet(sheet_name: str) -> pd.DataFrame:
    repo = supabase_repository()
    if sheet_name == SHEET_EMPRESAS:
        return pd.DataFrame([supabase_company_to_legacy(row) for row in repo.list_companies()])
    if sheet_name == SHEET_CICLOS:
        return pd.DataFrame([supabase_campaign_to_legacy(row) for row in repo.list_campaigns()])
    if sheet_name == SHEET_RESPOSTAS:
        return pd.DataFrame(repo.list_responses_for_campaign())
    if sheet_name == SHEET_RELATORIOS:
        return pd.DataFrame([supabase_report_to_legacy(row) for row in repo.list_reports()])
    if sheet_name == SHEET_AUDITORIA:
        return pd.DataFrame([supabase_audit_to_legacy(row) for row in repo.list_audit_logs()])
    return pd.DataFrame()


def supabase_campaign_update_payload(changes: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in changes.items():
        if key == "STATUS":
            status = LEGACY_STATUS_TO_SUPABASE.get(safe_status(value), "collecting")
            payload["status"] = status
            if status == "approved":
                payload["approved_at"] = iso_now()
            if status == "generated":
                payload.setdefault("generated_at", iso_now())
        elif key == "PAGAMENTO_OK":
            payload["payment_status"] = "confirmed" if is_yes(value) else "pending"
        elif key == "FUNCIONARIOS_CONTRATADOS":
            payload["employees_contracted"] = as_int(value)
        elif key == "PRECO_POR_FUNCIONARIO":
            payload["price_per_employee"] = as_float(value)
        elif key == "VALOR_MINIMO":
            payload["minimum_price"] = as_float(value)
        elif key == "VALIDO_ATE":
            payload["closes_at"] = value or None
        elif key == "INICIO_EM":
            payload["starts_at"] = value or None
        elif key == "ENCERRADO_EM":
            payload["closed_at"] = value or None
        elif key == "GERADO_EM":
            payload["generated_at"] = value or None
        elif key == "OBSERVACOES":
            payload["notes"] = value
        elif key == "PIN_HASH":
            payload["access_token_hash"] = value
    if payload:
        payload["updated_at"] = iso_now()
    return payload


def supabase_company_update_payload(changes: dict[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in changes.items():
        if key == "NOME":
            payload["legal_name"] = value
        elif key == "CNPJ":
            payload["cnpj"] = value
        elif key == "RESPONSAVEL":
            payload["responsible_name"] = value
        elif key == "EMAIL":
            payload["responsible_email"] = value
        elif key == "ATIVO":
            payload["status"] = "active" if is_yes(value) else "inactive"
    if payload:
        payload["updated_at"] = iso_now()
    return payload


# =============================================================================
# GOOGLE SHEETS / DRIVE
# =============================================================================

RETRYABLE_HTTP_STATUS = {408, 429, 500, 502, 503, 504}


def execute_google_request(
    request_factory,
    operation: str,
    max_attempts: int = 4,
):
    """Executa chamadas Google com retry exponencial em falhas temporárias."""
    last_error: Exception | None = None

    for attempt in range(max_attempts):
        try:
            request = request_factory()
            return request.execute(num_retries=2)
        except HttpError as exc:
            status = int(getattr(exc.resp, "status", 0) or 0)
            if status not in RETRYABLE_HTTP_STATUS:
                raise
            last_error = exc
        except (ssl.SSLError, TimeoutError, ConnectionError, OSError) as exc:
            last_error = exc

        if attempt >= max_attempts - 1:
            break

        delay = min(8.0, (2**attempt) + random.uniform(0.0, 1.0))
        time.sleep(delay)

    raise RuntimeError(
        f"Falha temporária ao {operation} após {max_attempts} tentativas. "
        "Tente novamente em alguns instantes."
    ) from last_error


def execute_google_read(request_factory, operation: str, max_attempts: int = 4):
    return execute_google_request(request_factory, operation, max_attempts)


def execute_google_write(request_factory, operation: str, max_attempts: int = 4):
    return execute_google_request(request_factory, operation, max_attempts)

def sheets_service():
    if "gcp_service_account" not in st.secrets:
        raise RuntimeError(
            "As credenciais gcp_service_account não estão configuradas nos Secrets."
        )

    credentials_info = dict(st.secrets["gcp_service_account"])
    credentials_info["private_key"] = credentials_info["private_key"].replace(
        "\\n",
        "\n",
    )

    credentials = service_account.Credentials.from_service_account_info(
        credentials_info,
        scopes=["https://www.googleapis.com/auth/spreadsheets"],
    )

    return build(
        "sheets",
        "v4",
        credentials=credentials,
        cache_discovery=False,
    )


def drive_service():
    if "google_drive_oauth" not in st.secrets:
        raise RuntimeError(
            "Configure google_drive_oauth nos Secrets para armazenar relatórios "
            "no seu Google Drive pessoal."
        )

    cfg = st.secrets["google_drive_oauth"]
    required = ("client_id", "client_secret", "refresh_token")
    missing = [
        name
        for name in required
        if not str(cfg.get(name, "")).strip()
    ]

    if missing:
        raise RuntimeError(
            "Campos OAuth do Drive ausentes: " + ", ".join(missing)
        )

    credentials = UserCredentials(
        token=None,
        refresh_token=str(cfg["refresh_token"]).strip(),
        token_uri=str(
            cfg.get("token_uri", "https://oauth2.googleapis.com/token")
        ).strip(),
        client_id=str(cfg["client_id"]).strip(),
        client_secret=str(cfg["client_secret"]).strip(),
        scopes=["https://www.googleapis.com/auth/drive.file"],
    )

    return build(
        "drive",
        "v3",
        credentials=credentials,
        cache_discovery=False,
    )


def spreadsheet_id() -> str:
    try:
        return str(st.secrets["google_forms"]["spreadsheet_id"])
    except Exception as exc:
        raise RuntimeError("Configure google_forms.spreadsheet_id nos Secrets.") from exc


def read_sheet(sheet_name: str) -> pd.DataFrame:
    if backend_is_supabase():
        return read_supabase_sheet(sheet_name)

    result = execute_google_read(
        lambda: sheets_service()
        .spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id(),
            range=f"'{sheet_name}'",
        ),
        operation=f"ler a aba {sheet_name}",
    )

    values = result.get("values", [])

    if not values:
        return pd.DataFrame()

    headers = [str(value).strip() for value in values[0]]
    width = len(headers)
    rows = []

    for row_number, row in enumerate(values[1:], start=2):
        padded = list(row) + [""] * (width - len(row))
        record = dict(zip(headers, padded[:width]))
        record["__ROW__"] = row_number
        rows.append(record)

    return pd.DataFrame(rows)


def get_sheet_headers(sheet_name: str) -> list[str]:
    result = execute_google_read(
        lambda: sheets_service()
        .spreadsheets()
        .values()
        .get(
            spreadsheetId=spreadsheet_id(),
            range=f"'{sheet_name}'!1:1",
        ),
        operation=f"ler o cabeçalho da aba {sheet_name}",
    )

    values = result.get("values", [])
    return [str(value).strip() for value in values[0]] if values else []


def ensure_sheet(sheet_name: str, headers: list[str]) -> None:
    """Cria a aba ou acrescenta colunas ausentes sem apagar a estrutura existente."""
    sheets = sheets_service()
    metadata = execute_google_read(
        lambda: sheets.spreadsheets().get(spreadsheetId=spreadsheet_id()),
        operation="ler metadados da planilha",
    )
    existing = {item["properties"]["title"] for item in metadata.get("sheets", [])}
    if sheet_name not in existing:
        execute_google_write(
            lambda: sheets.spreadsheets().batchUpdate(
                spreadsheetId=spreadsheet_id(),
                body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
            ),
            operation=f"criar a aba {sheet_name}",
        )
    current = get_sheet_headers(sheet_name)
    if not current:
        merged = list(headers)
    else:
        merged = current + [header for header in headers if header not in current]
    if merged != current:
        execute_google_write(
            lambda: sheets.spreadsheets().values().update(
                spreadsheetId=spreadsheet_id(),
                range=f"'{sheet_name}'!A1:{last_column_letter(len(merged))}1",
                valueInputOption="RAW",
                body={"values": [merged]},
            ),
            operation=f"atualizar o cabeçalho da aba {sheet_name}",
        )
def migrate_existing_companies() -> None:
    """Aproveita linhas da antiga aba Empresas sem alterar fórmulas e colunas legadas."""
    companies = read_sheet(SHEET_EMPRESAS)
    if companies.empty or "NOME" not in companies.columns:
        return
    for _, company in companies.iterrows():
        name = str(company.get("NOME", "")).strip()
        if not name:
            continue
        changes: dict[str, Any] = {}
        if not str(company.get("EMPRESA_ID", "")).strip():
            changes["EMPRESA_ID"] = make_company_id(name)
        if not str(company.get("ATIVO", "")).strip():
            changes["ATIVO"] = "SIM"
        if not str(company.get("CRIADO_EM", "")).strip():
            changes["CRIADO_EM"] = iso_now()
        if changes:
            update_row(SHEET_EMPRESAS, EMPRESAS_HEADERS, company, changes)


def ensure_structure() -> None:
    if backend_is_supabase():
        questionnaire = supabase_repository().get_active_questionnaire()
        if not questionnaire:
            raise RuntimeError("Questionário ativo não encontrado no Supabase. Rode o seed V2.")
        return

    ensure_sheet(SHEET_EMPRESAS, EMPRESAS_HEADERS)
    ensure_sheet(SHEET_CICLOS, CICLOS_HEADERS)
    ensure_sheet(SHEET_RELATORIOS, RELATORIOS_HEADERS)
    ensure_sheet(SHEET_AUDITORIA, AUDITORIA_HEADERS)
    migrate_existing_companies()


def append_row(sheet_name: str, headers: list[str], data: dict[str, Any]) -> dict[str, Any] | None:
    if backend_is_supabase():
        repo = supabase_repository()
        if sheet_name == SHEET_EMPRESAS:
            created = repo.create_company(data)
            return supabase_company_to_legacy(created)
        if sheet_name == SHEET_CICLOS:
            payload = dict(data)
            payload["status"] = LEGACY_STATUS_TO_SUPABASE.get(safe_status(data.get("STATUS")), "collecting")
            payload["payment_status"] = "confirmed" if is_yes(data.get("PAGAMENTO_OK")) else "pending"
            created = repo.create_campaign(payload)
            return supabase_campaign_to_legacy(created)
        if sheet_name == SHEET_RELATORIOS:
            created = repo.create_report(data)
            return supabase_report_to_legacy(created)
        if sheet_name == SHEET_AUDITORIA:
            repo.write_audit_log(
                str(data.get("ACAO", "AUDITORIA")),
                metadata={"legacy": data.get("DETALHES_JSON", "")},
                actor_type=str(data.get("TIPO_ATOR", "system")).lower() or "system",
                company_id=str(data.get("EMPRESA_ID") or "") or None,
                campaign_id=str(data.get("CICLO_ID") or "") or None,
            )
            return data
        raise ValueError(f"Aba sem mapeamento Supabase: {sheet_name}")

    ensure_sheet(sheet_name, headers)
    actual_headers = get_sheet_headers(sheet_name)
    sheets = sheets_service()
    values = [[data.get(header, "") for header in actual_headers]]
    execute_google_write(
        lambda: sheets.spreadsheets().values().append(
            spreadsheetId=spreadsheet_id(),
            range=f"'{sheet_name}'!A:{last_column_letter(len(actual_headers))}",
            valueInputOption="RAW",
            insertDataOption="INSERT_ROWS",
            body={"values": values},
        ),
        operation=f"inserir linha em {sheet_name}",
    )
    return None


def update_row(sheet_name: str, headers: list[str], current: dict[str, Any] | pd.Series, changes: dict[str, Any]) -> None:
    if backend_is_supabase():
        repo = supabase_repository()
        if sheet_name == SHEET_CICLOS:
            campaign_id = str(current.get("CICLO_ID") or current.get("id") or "").strip()
            if not campaign_id:
                raise ValueError("Campanha Supabase não identificada.")
            repo.update_campaign(campaign_id, supabase_campaign_update_payload(changes))
            return
        if sheet_name == SHEET_EMPRESAS:
            company_id = str(current.get("EMPRESA_ID") or current.get("id") or "").strip()
            payload = supabase_company_update_payload(changes)
            if company_id and payload:
                repo.client.table("companies").update(payload).eq("id", company_id).execute()
            return
        raise ValueError(f"Atualização sem mapeamento Supabase: {sheet_name}")

    """Atualiza somente as células alteradas, preservando fórmulas e colunas antigas."""
    row_number = as_int(current.get("__ROW__"))
    if row_number < 2:
        raise ValueError("Linha da planilha não identificada.")
    ensure_sheet(sheet_name, headers)
    actual_headers = get_sheet_headers(sheet_name)
    data = []
    for header, value in changes.items():
        if header not in actual_headers:
            raise ValueError(f"Coluna não encontrada em {sheet_name}: {header}")
        column_number = actual_headers.index(header) + 1
        cell = f"{last_column_letter(column_number)}{row_number}"
        data.append({"range": f"'{sheet_name}'!{cell}", "values": [[value]]})
    if not data:
        return
    sheets = sheets_service()
    execute_google_write(
        lambda: sheets.spreadsheets().values().batchUpdate(
            spreadsheetId=spreadsheet_id(),
            body={"valueInputOption": "RAW", "data": data},
        ),
        operation=f"atualizar linha em {sheet_name}",
    )

def upload_zip_to_drive(content: bytes, filename: str) -> str:
    if backend_is_supabase():
        storage_path = f"reports/{now_sp().strftime('%Y/%m/%d')}/{filename}"
        return supabase_repository().upload_report_bytes(content, storage_path)

    drive = drive_service()
    folder_id = str(st.secrets.get("drive", {}).get("folder_id", "")).strip()
    metadata: dict[str, Any] = {
        "name": filename,
        "mimeType": "application/zip",
    }
    if folder_id:
        metadata["parents"] = [folder_id]
    media = MediaIoBaseUpload(BytesIO(content), mimetype="application/zip", resumable=False)
    created = execute_google_write(
        lambda: drive.files().create(body=metadata, media_body=media, fields="id,name"),
        operation="enviar ZIP para o Drive",
    )
    return str(created["id"])


def trash_drive_file(file_id: str) -> None:
    if not str(file_id).strip():
        return
    if backend_is_supabase():
        supabase_repository().delete_report_file(str(file_id).strip())
        return
    drive = drive_service()
    execute_google_write(
        lambda: drive.files().update(fileId=str(file_id).strip(), body={"trashed": True}, fields="id,trashed"),
        operation="mover arquivo antigo para a lixeira do Drive",
    )


def download_drive_file(file_id: str) -> bytes:
    if backend_is_supabase():
        return supabase_repository().download_report_file(str(file_id).strip())

    drive = drive_service()
    request = drive.files().get_media(fileId=file_id)
    buffer = BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    last_error: Exception | None = None
    for _ in range(6):
        try:
            while not done:
                _, done = downloader.next_chunk(num_retries=2)
            return buffer.getvalue()
        except (HttpError, ssl.SSLError, TimeoutError, ConnectionError, OSError) as exc:
            last_error = exc
            time.sleep(1.0)
    raise RuntimeError("Falha temporária ao baixar arquivo do Drive.") from last_error


# =============================================================================
# DADOS E REGRAS DE NEGÓCIO
# =============================================================================

def find_company(companies: pd.DataFrame, company_id: str) -> pd.Series | None:
    if companies.empty or "EMPRESA_ID" not in companies.columns:
        return None
    matches = companies[companies["EMPRESA_ID"].astype(str) == str(company_id)]
    return matches.iloc[0] if not matches.empty else None


def find_cycle_by_token(cycles: pd.DataFrame, token: str) -> pd.Series | None:
    if cycles.empty or "TOKEN" not in cycles.columns:
        return None
    matches = cycles[cycles["TOKEN"].astype(str) == str(token)]
    return matches.iloc[0] if not matches.empty else None


def find_cycle(cycles: pd.DataFrame, cycle_id: str) -> pd.Series | None:
    if cycles.empty or "CICLO_ID" not in cycles.columns:
        return None
    matches = cycles[cycles["CICLO_ID"].astype(str) == str(cycle_id)]
    return matches.iloc[0] if not matches.empty else None


def load_responses() -> pd.DataFrame:
    df = read_sheet(SHEET_RESPOSTAS)
    if df.empty:
        return df
    df = df.drop(columns=["__ROW__"], errors="ignore")
    return normalize_dataframe_columns(df)


def response_timestamp_column(df: pd.DataFrame) -> str | None:
    for candidate in ("CARIMBO_DE_DATA_HORA", "CARIMBO_DE_DATAHORA", "TIMESTAMP"):
        if candidate in df.columns:
            return candidate
    return None


def parse_response_timestamps(values: pd.Series) -> pd.Series:
    """Converte timestamps ISO/Supabase e carimbos legados do Forms para horário local sem fuso."""
    return values.map(
        lambda value: (
            pd.NaT
            if parse_datetime(value) is None
            else parse_datetime(value).replace(tzinfo=None)  # type: ignore[union-attr]
        )
    )


def deduplicate_responses(df: pd.DataFrame) -> pd.DataFrame:
    """Remove duplicidades comuns sem depender de dados identificáveis."""
    if df.empty:
        return df.copy()
    result = df.drop_duplicates().copy()
    timestamp_col = response_timestamp_column(result)
    if timestamp_col:
        result["__TS_SORT__"] = parse_response_timestamps(result[timestamp_col])
        result = result.sort_values("__TS_SORT__", na_position="first")
    for key in ("CODIGO_RESPONDENTE", "EMAIL", "E_MAIL"):
        if key in result.columns and result[key].astype(str).str.strip().ne("").any():
            result = result.drop_duplicates(subset=[key], keep="last")
            break
    return result.drop(columns=["__TS_SORT__"], errors="ignore")


def filter_cycle_responses(df: pd.DataFrame, company: pd.Series, cycle: pd.Series) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    result = normalize_dataframe_columns(df)
    cycle_id = str(cycle.get("CICLO_ID", "")).strip()
    company_id = str(company.get("EMPRESA_ID", "")).strip()
    company_name = normalize_text(company.get("NOME", ""))

    masks: list[pd.Series] = []
    if "CICLO_ID" in result.columns and cycle_id:
        masks.append(result["CICLO_ID"].astype(str).str.strip() == cycle_id)

    company_mask = pd.Series(False, index=result.index)
    if "EMPRESA_ID" in result.columns and company_id:
        company_mask = company_mask | (result["EMPRESA_ID"].astype(str).str.strip() == company_id)
    if "NOME_DA_EMPRESA" in result.columns and company_name:
        company_mask = company_mask | (result["NOME_DA_EMPRESA"].map(normalize_text) == company_name)

    # Compatibilidade com respostas antigas: se CICLO_ID estiver vazio, usa empresa + janela de datas.
    if "CICLO_ID" in result.columns:
        blank_cycle = result["CICLO_ID"].astype(str).str.strip().eq("")
        masks.append(blank_cycle & company_mask)
    elif company_mask.any():
        masks.append(company_mask)

    if not masks:
        return result.iloc[0:0].copy()

    combined = masks[0]
    for mask in masks[1:]:
        combined = combined | mask
    result = result[combined].copy()

    timestamp_col = response_timestamp_column(result)
    if timestamp_col:
        timestamps = parse_response_timestamps(result[timestamp_col])
        start = parse_datetime(cycle.get("INICIO_EM"))
        end = parse_datetime(cycle.get("ENCERRADO_EM"))
        if start:
            start_naive = start.replace(tzinfo=None)
            result = result[timestamps >= start_naive]
            timestamps = timestamps.loc[result.index]
        if end:
            end_naive = end.replace(tzinfo=None)
            result = result[timestamps <= end_naive]
    return deduplicate_responses(result)

def contracted_value(cycle: pd.Series, response_count: int | None = None) -> tuple[int, float, float, bool]:
    contracted = max(0, as_int(cycle.get("FUNCIONARIOS_CONTRATADOS")))
    unit_price = max(0.0, as_float(cycle.get("PRECO_POR_FUNCIONARIO")))
    minimum = max(0.0, as_float(cycle.get("VALOR_MINIMO")))
    base_quantity = contracted
    value = max(minimum, base_quantity * unit_price)
    over_limit = response_count is not None and contracted > 0 and response_count > contracted
    return contracted, unit_price, value, over_limit


def cycle_expired(cycle: pd.Series) -> bool:
    valid_until = parse_date(cycle.get("VALIDO_ATE"))
    return bool(valid_until and now_sp().date() > valid_until)


def response_validation_message(responses: pd.DataFrame) -> tuple[bool, str]:
    validation = validate_questionnaire_columns(responses)
    missing = validation.get("missing_questions", [])
    if missing:
        return False, (
            f"Instrumento incompleto: {validation['found_questions']}/{validation['expected_questions']} itens encontrados. "
            f"Itens ausentes: {', '.join(map(str, missing))}."
        )
    total = len(REPORT_QUESTIONARIO)
    return True, f"Instrumento completo: {total}/{total} itens encontrados."


def log_audit(
    action: str,
    *,
    actor_type: str,
    actor: str = "",
    company_id: str = "",
    cycle_id: str = "",
    details: dict[str, Any] | None = None,
) -> None:
    if backend_is_supabase():
        try:
            metadata = dict(details or {})
            if actor:
                metadata["actor"] = actor
            supabase_repository().write_audit_log(
                action,
                metadata=metadata,
                actor_type=actor_type.lower() or "system",
                company_id=company_id or None,
                campaign_id=cycle_id or None,
            )
        except Exception:
            pass
        return

    try:
        append_row(
            SHEET_AUDITORIA,
            AUDITORIA_HEADERS,
            {
                "EVENTO_ID": secure_secrets.token_hex(12),
                "OCORRIDO_EM": iso_now(),
                "TIPO_ATOR": actor_type,
                "ATOR": actor,
                "EMPRESA_ID": company_id,
                "CICLO_ID": cycle_id,
                "ACAO": action,
                "DETALHES_JSON": json.dumps(details or {}, ensure_ascii=False, sort_keys=True),
            },
        )
    except Exception:
        # Auditoria não deve derrubar a operação principal; problemas aparecem no painel/configuração.
        pass


def emv_field(field_id: str, value: str) -> str:
    encoded = str(value)
    if len(encoded) > 99:
        raise ValueError(f"Campo EMV {field_id} excede 99 caracteres.")
    return f"{field_id}{len(encoded):02d}{encoded}"


def pix_text(value: Any, max_length: int) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_text = normalized.encode("ASCII", "ignore").decode("ASCII")
    allowed = "".join(
        char
        for char in ascii_text.upper()
        if char.isalnum() or char in {" ", "-", ".", "/"}
    )
    return " ".join(allowed.split())[:max_length]


def pix_txid(value: Any) -> str:
    clean = "".join(char for char in pix_text(value, 80) if char.isalnum())
    return clean[:25] or "***"


def pix_crc16(payload: str) -> str:
    crc = 0xFFFF

    for byte in payload.encode("utf-8"):
        crc ^= byte << 8

        for _ in range(8):
            if crc & 0x8000:
                crc = ((crc << 1) ^ 0x1021) & 0xFFFF
            else:
                crc = (crc << 1) & 0xFFFF

    return f"{crc:04X}"


def build_pix_payload(
    key: str,
    receiver_name: str,
    receiver_city: str,
    amount: float,
    txid: str,
    description: str = "",
) -> str:
    if not key.strip():
        raise ValueError("A chave Pix não foi configurada.")

    merchant_account = (
        emv_field("00", "BR.GOV.BCB.PIX")
        + emv_field("01", key.strip())
    )

    clean_description = pix_text(description, 40)
    if clean_description:
        merchant_account += emv_field("02", clean_description)

    additional_data = emv_field("05", pix_txid(txid))

    payload = (
        emv_field("00", "01")
        + emv_field("26", merchant_account)
        + emv_field("52", "0000")
        + emv_field("53", "986")
        + emv_field("54", f"{amount:.2f}")
        + emv_field("58", "BR")
        + emv_field("59", pix_text(receiver_name, 25))
        + emv_field("60", pix_text(receiver_city, 15))
        + emv_field("62", additional_data)
        + "6304"
    )

    return payload + pix_crc16(payload)


def pix_qr_png(payload: str) -> bytes:
    image = qrcode.make(payload)
    output = BytesIO()
    image.save(output, format="PNG")
    return output.getvalue()


def render_pix_payment(
    company: pd.Series,
    cycle: pd.Series,
    amount: float,
) -> None:
    if amount <= 0 or is_yes(cycle.get("PAGAMENTO_OK", "")):
        return

    pix_cfg = st.secrets.get("pix", {})
    key = str(pix_cfg.get("key", "")).strip()
    receiver_name = str(pix_cfg.get("receiver_name", "")).strip()
    receiver_city = str(pix_cfg.get("receiver_city", "")).strip()
    description = str(
        pix_cfg.get("description", "MAPEAMENTO PSICOSSOCIAL")
    ).strip()
    contact = str(pix_cfg.get("payment_contact", "")).strip()

    if not key or not receiver_name or not receiver_city:
        return

    payload = build_pix_payload(
        key=key,
        receiver_name=receiver_name,
        receiver_city=receiver_city,
        amount=amount,
        txid=str(cycle.get("CICLO_ID", "")),
        description=description,
    )

    with st.expander("💠 Pagamento via Pix", expanded=False):
        st.write(f"**Valor:** {brl(amount)}")
        st.image(
            pix_qr_png(payload),
            width=260,
            caption="Escaneie no aplicativo do seu banco.",
        )
        st.markdown("**Pix Copia e Cola**")
        st.code(payload, language=None)

        if contact:
            st.caption(
                f"Após o pagamento, envie o comprovante para {contact}. "
                "A liberação será confirmada pelo administrador."
            )
        else:
            st.caption(
                "Após o pagamento, envie o comprovante ao responsável comercial. "
                "A liberação será confirmada pelo administrador."
            )


def build_form_link(company: pd.Series, cycle: pd.Series) -> str:
    forms_cfg = st.secrets.get("google_forms", {})
    base_url = str(forms_cfg.get("base_url", "")).strip()

    if not base_url:
        return ""

    parts = urlsplit(base_url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    params["usp"] = "pp_url"

    entry_company = str(forms_cfg.get("entry_company", "327839909")).strip()
    entry_company_id = str(forms_cfg.get("entry_company_id", "")).strip()
    entry_cycle_id = str(forms_cfg.get("entry_cycle_id", "")).strip()

    if entry_company:
        params[f"entry.{entry_company}"] = str(company.get("NOME", ""))

    if entry_company_id:
        params[f"entry.{entry_company_id}"] = str(company.get("EMPRESA_ID", ""))

    if entry_cycle_id:
        params[f"entry.{entry_cycle_id}"] = str(cycle.get("CICLO_ID", ""))

    return urlunsplit(
        (
            parts.scheme,
            parts.netloc,
            parts.path,
            urlencode(params),
            parts.fragment,
        )
    )


def build_client_link(token: str) -> str:
    base_url = str(get_app_setting("base_url", "")).strip()
    if not base_url:
        return f"?token={token}"
    return f"{base_url.rstrip('/')}?token={token}"


def build_response_link(token: str) -> str:
    base_url = str(get_app_setting("base_url", "")).strip()
    query = urlencode({"respond": token})
    if not base_url:
        return f"?{query}"
    return f"{base_url.rstrip('/')}?{query}"


def inject_response_form_styles() -> None:
    st.markdown(
        """
        <style>
        div[data-testid="stForm"] {
            padding-bottom: 1.25rem;
        }
        div[data-testid="stRadio"] {
            margin: 0.75rem 0 1.15rem 0;
            padding: 0.85rem 0.95rem;
            border: 1px solid rgba(49, 51, 63, 0.14);
            border-radius: 8px;
            background: rgba(250, 250, 252, 0.72);
        }
        div[data-testid="stRadio"] > label {
            margin-bottom: 0.65rem;
            line-height: 1.38;
            font-weight: 650;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] {
            gap: 0.38rem;
        }
        div[data-testid="stRadio"] div[role="radiogroup"] label {
            padding: 0.42rem 0.25rem;
            min-height: 2.15rem;
            align-items: flex-start;
        }
        div[data-testid="stRadio"] p {
            line-height: 1.32;
        }
        @media (max-width: 640px) {
            section.main div.block-container {
                padding-left: 1rem;
                padding-right: 1rem;
            }
            div[data-testid="stRadio"] {
                padding: 0.9rem 0.8rem;
            }
            div[data-testid="column"] {
                width: 100% !important;
                flex: 1 1 100% !important;
            }
        }
        </style>
        """,
        unsafe_allow_html=True,
    )


def create_zip(reports, manifest: dict[str, Any]) -> bytes:
    output = BytesIO()
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        for report in reports:
            archive.writestr(report.filename, report.docx)
        archive.writestr(
            "LEIA-ME.json",
            json.dumps(manifest, ensure_ascii=False, indent=2).encode("utf-8"),
        )
    return output.getvalue()


def generate_and_store_reports(company: pd.Series, cycle: pd.Series, responses: pd.DataFrame) -> tuple[bytes, str, str, str, list[str]]:
    ok, validation_msg = response_validation_message(responses)
    if not ok:
        raise ValueError(validation_msg)
    min_group = campaign_min_group(cycle)
    report_version = str(get_app_setting("report_version", "4.0-v2-supabase-ready"))
    config = ReportConfig(min_group_size=min_group, report_version=report_version, methodology_status=str(get_app_setting("methodology_status", "Triagem e monitoramento psicossocial; instrumento proprietário em validação técnica")))
    company_name = str(company.get("NOME", "Empresa"))
    cycle_label = f"Ciclo {cycle.get('ANO', now_sp().year)}"
    generated_at = now_sp()
    reports, suppressed = generate_company_reports(
        responses,
        company=company_name,
        cycle_label=cycle_label,
        config=config,
        generated_at=generated_at,
    )
    manifest = {
        "empresa": company_name,
        "empresa_id": company.get("EMPRESA_ID", ""),
        "ciclo_id": cycle.get("CICLO_ID", ""),
        "gerado_em": generated_at.isoformat(),
        "respostas_analisadas": len(responses),
        "validacao_instrumento": validation_msg,
        "minimo_confidencialidade": min_group,
        "setores_suprimidos_por_confidencialidade": suppressed,
        "versao": report_version,
        "arquivos": [report.filename for report in reports],
        "observacao": "Pacote definitivo do ciclo. Re-download permitido; recálculo exige reabertura administrativa formal.",
    }
    zip_content = create_zip(reports, manifest)
    zip_sha256 = hashlib.sha256(zip_content).hexdigest()
    safe_company = "_".join(normalize_text(company_name).split())[:60]
    filename = f"Relatorios_{safe_company}_{cycle.get('ANO', now_sp().year)}_{generated_at.strftime('%Y%m%d')}.zip"
    if backend_is_supabase():
        repo = supabase_repository()
        file_id = repo.make_report_storage_path(
            company_id=str(company.get("EMPRESA_ID", "")),
            campaign_id=str(cycle.get("CICLO_ID", "")),
            filename=filename,
        )
        repo.upload_report_bytes(zip_content, file_id)
    else:
        file_id = upload_zip_to_drive(zip_content, filename)

    for report in reports:
        append_row(
            SHEET_RELATORIOS,
            RELATORIOS_HEADERS,
            {
                "CICLO_ID": cycle.get("CICLO_ID", ""),
                "EMPRESA_ID": company.get("EMPRESA_ID", ""),
                "TIPO": "COLETIVO",
                "ESCOPO": report.scope,
                "FILE_ID": file_id,
                "FILE_NAME": report.filename,
                "GERADO_EM": generated_at.isoformat(),
                "VISIVEL_CLIENTE": "SIM",
                "N_RESPONDENTES": report.respondents,
                "ZIP_SHA256": zip_sha256,
                "VERSAO": report_version,
                "ZIP_FILE_NAME": filename,
            },
        )
    if backend_is_supabase():
        question_results = calculate_question_results(responses)
        for alert in build_critical_alerts(question_results):
            supabase_repository().create_alert(
                {
                    "campaign_id": cycle.get("CICLO_ID", ""),
                    "scope_type": "company",
                    "severity": alert.get("severidade", "attention"),
                    "code": f"CRITICAL_Q{int(alert.get('numero', 0)):02d}",
                    "title": "Sinal crítico para revisão técnica",
                    "description": str(alert.get("mensagem", "")),
                    "evidence": {
                        "item": alert.get("numero"),
                        "escore": alert.get("escore"),
                        "pct_alta_exposicao": alert.get("pct_alta_exposicao"),
                    },
                }
            )
    return zip_content, file_id, filename, zip_sha256, suppressed


# =============================================================================
# INTERFACE: PARTICIPANTE
# =============================================================================

def render_participant_notice(company: dict[str, Any], campaign: dict[str, Any]) -> None:
    version = campaign_notice_version(campaign)
    template = PARTICIPANT_NOTICE_TEMPLATES.get(
        version,
        PARTICIPANT_NOTICE_TEMPLATES[PARTICIPANT_NOTICE_VERSION],
    )
    controller = str(
        campaign.get("notice_controller")
        or company.get("lgpd_controller_name")
        or company.get("trade_name")
        or company.get("legal_name")
        or "Organização responsável pela pesquisa"
    ).strip()
    operator = str(
        campaign.get("notice_operator")
        or get_app_setting("operator_name", "Responsável pela operação da pesquisa")
    ).strip()
    contact = str(
        campaign.get("notice_contact")
        or company.get("lgpd_contact_email")
        or company.get("responsible_email")
        or get_app_setting("privacy_contact", "Canal informado pela organização")
    ).strip()
    retention = str(
        campaign.get("notice_retention")
        or get_app_setting(
            "retention_policy",
            "Conforme o contrato e a política de privacidade aplicáveis a esta pesquisa",
        )
    ).strip()

    st.subheader("Aviso aos participantes")
    st.markdown(template.format(min_group=campaign_min_group(campaign)))
    st.markdown(
        f"""
### Responsáveis e retenção

- **Controlador dos dados:** {controller}
- **Operador/prestador do serviço:** {operator}
- **Contato para dúvidas e direitos dos titulares:** {contact}
- **Prazo e critério de retenção:** {retention}
"""
    )
    st.caption(f"Versão do aviso: {version}")


def render_response_form() -> None:
    st.title("Escuta psicossocial")
    inject_response_form_styles()
    if not backend_is_supabase():
        st.error("A coleta própria pelo app requer `backend_provider = \"supabase\"`.")
        st.stop()

    token = (get_query_value("respond") or get_query_value("responder")).strip()
    if not token:
        st.error("Link de resposta ausente ou inválido.")
        st.stop()

    repo = supabase_repository()
    response_lookup = getattr(repo, "get_campaign_by_response_code", None)
    campaign = response_lookup(token) if callable(response_lookup) else None
    if not campaign:
        legacy_campaign = repo.get_campaign_by_code(token)
        if not callable(response_lookup) or not str(legacy_campaign.get("response_code") if legacy_campaign else "").strip():
            campaign = legacy_campaign
    if not campaign:
        st.error("Campanha não encontrada ou link revogado.")
        st.stop()

    cycle = pd.Series(supabase_campaign_to_legacy(campaign))
    company = campaign.get("companies") or {}
    if safe_status(cycle.get("STATUS")) != "COLETA":
        st.error("Esta campanha não está aberta para novas respostas.")
        st.stop()
    if cycle_expired(cycle):
        st.error("O prazo de resposta desta campanha expirou.")
        st.stop()

    campaign_id = str(campaign.get("id") or "")
    notice_version = campaign_notice_version(campaign)
    submitted_key = f"response_submitted_{campaign_id}"
    accepted_key = f"notice_accepted_{campaign_id}_{notice_version}"
    declined_key = f"notice_declined_{campaign_id}_{notice_version}"
    decision_key = f"notice_decision_{campaign_id}_{notice_version}"
    if st.session_state.get(submitted_key):
        st.success("Resposta registrada. Obrigado por participar.")
        st.caption("As respostas serão analisadas de forma coletiva, sem relatório individual para a empresa.")
        st.stop()

    st.subheader(str(company.get("trade_name") or company.get("legal_name") or "Empresa"))
    if st.session_state.get(declined_key):
        st.info("Você decidiu não participar. Nenhuma resposta foi coletada e esta página já pode ser fechada.")
        st.stop()

    if not st.session_state.get(accepted_key):
        render_participant_notice(company, campaign)
        decision = st.radio(
            "Depois de ler o aviso, escolha uma opção:",
            (
                "Li as informações e desejo participar",
                "Não desejo participar",
            ),
            index=None,
            key=decision_key,
        )
        continue_clicked = st.button(
            "Continuar",
            type="primary",
            disabled=decision is None,
            use_container_width=True,
        )

        if continue_clicked:
            if decision == "Li as informações e desejo participar":
                st.session_state[accepted_key] = iso_now()
            else:
                st.session_state[declined_key] = True
                st.rerun()
        else:
            st.stop()

    with st.expander("Rever o aviso aos participantes"):
        render_participant_notice(company, campaign)

    questions = repo.list_questions(str(campaign["questionnaire_id"]))
    closed_questions = [q for q in questions if q.get("question_type") == "likert_frequency"]
    open_questions = [q for q in questions if q.get("question_type") == "open_text"]
    if len(closed_questions) != len(REPORT_QUESTIONARIO):
        st.error(
            f"Questionário V2 incompleto no banco: {len(closed_questions)}/{len(REPORT_QUESTIONARIO)} itens fechados."
        )
        st.stop()
    domain_names: dict[str, str] = {}
    for question in closed_questions:
        domain = question.get("domains") or {}
        code = str(domain.get("code") or "GERAL")
        domain_names[code] = str(domain.get("name") or code)

    campaign_sectors = load_campaign_sectors(repo, campaign_id)
    sector_options = {
        str(row.get("id") or f"sector-{index}"): row
        for index, row in enumerate(campaign_sectors)
    }

    with st.form(f"response_form_{campaign_id}"):
        selected_sector_id: str | None = None
        legacy_area = ""
        if sector_options:
            selected_sector_id = st.selectbox(
                "Em qual área você trabalha?",
                list(sector_options.keys()),
                index=None,
                placeholder="Selecione uma área",
                format_func=lambda value: str(
                    sector_options.get(value, {}).get("sector_name") or value
                ),
                help="As opções foram definidas previamente pela organização.",
                key=f"response_area_{campaign_id}",
            )
        else:
            st.warning(
                "Esta campanha ainda usa a estrutura anterior. Informe sua área conforme a nomenclatura adotada pela organização."
            )
            legacy_area = st.text_input(
                "Área de trabalho",
                max_chars=80,
                key=f"response_legacy_area_{campaign_id}",
            )

        current_role = st.text_input(
            "Cargo ou função atual (opcional)",
            max_chars=80,
            help="Este campo não define o grupo do relatório. Deixe em branco se puder identificar você.",
            key=f"response_role_{campaign_id}",
        )

        answers: dict[str, str | None] = {}
        for domain_code, domain_name in domain_names.items():
            st.markdown(f"#### {domain_name}")
            for question in [q for q in closed_questions if (q.get("domains") or {}).get("code") == domain_code]:
                answers[str(question["code"])] = st.radio(
                    str(question["text"]),
                    LIKERT_OPTIONS,
                    index=None,
                    horizontal=False,
                    key=f"q_{campaign.get('id')}_{question['code']}",
                )

        open_payload: dict[str, str] = {}
        if open_questions:
            st.markdown("#### Perguntas abertas")
            for question in open_questions:
                open_payload[str(question["code"])] = st.text_area(
                    str(question["text"]),
                    max_chars=1200,
                    key=f"open_{campaign.get('id')}_{question['code']}",
                )

        submitted = st.form_submit_button("Enviar resposta", type="primary", use_container_width=True)

    if submitted:
        missing = [code for code, value in answers.items() if not value]
        if not st.session_state.get(accepted_key):
            st.error("Leia e confirme o aviso antes de responder.")
            st.stop()
        if sector_options and (not selected_sector_id or selected_sector_id not in sector_options):
            st.error("Selecione sua área de trabalho.")
            st.stop()
        if not sector_options and not legacy_area.strip():
            st.error("Informe sua área de trabalho.")
            st.stop()
        if missing:
            st.error(f"Responda todos os {len(REPORT_QUESTIONARIO)} itens fechados antes de enviar.")
            st.stop()

        selected_sector = sector_options.get(str(selected_sector_id), {})
        group_name = str(
            selected_sector.get("analysis_group_name")
            or selected_sector.get("sector_name")
            or legacy_area
        ).strip()
        repo.create_response(
            campaign_id,
            {
                # O grupo é resolvido da estrutura congelada, nunca digitado livremente
                # quando a campanha possui áreas predefinidas.
                "sector": group_name,
                "campaign_area_id": selected_sector_id,
                "analysis_group_key": selected_sector.get("analysis_group_key"),
                "analysis_group_name": group_name,
                "role_family": current_role.strip(),
                "source": "streamlit_response_form",
                "consent_accepted": True,
                "notice_version": notice_version,
                "notice_accepted_at": st.session_state[accepted_key],
            },
            answers,
            open_payload,
        )
        log_audit(
            "REGISTRAR_RESPOSTA",
            actor_type="PARTICIPANTE",
            company_id=str(campaign.get("company_id", "")),
            cycle_id=str(campaign.get("id", "")),
            details={
                "origem": "streamlit_response_form",
                "area_predefinida_selecionada": bool(sector_options),
                "cargo_informado": bool(current_role.strip()),
                "aviso_versao": notice_version,
            },
        )
        st.session_state[submitted_key] = True
        st.success("Resposta registrada. Obrigado por participar.")
        st.stop()


def render_client() -> None:
    st.title("📊 Painel da pesquisa psicossocial")
    token = get_query_value("token").strip()
    if not token:
        st.error("Link de acesso ausente ou inválido.")
        st.stop()

    companies = read_sheet(SHEET_EMPRESAS)
    cycles = read_sheet(SHEET_CICLOS)
    cycle = find_cycle_by_token(cycles, token)
    if cycle is None:
        st.error("Link inválido ou revogado.")
        st.stop()
    company = find_company(companies, str(cycle.get("EMPRESA_ID", "")))
    if company is None or not is_yes(company.get("ATIVO", "SIM")):
        st.error("Empresa indisponível. Entre em contato com o responsável pelo serviço.")
        st.stop()
    if safe_status(cycle.get("STATUS")) == "CANCELADO":
        st.error("Este ciclo foi cancelado.")
        st.stop()
    if cycle_expired(cycle):
        st.error("O acesso deste ciclo expirou. Os relatórios permanecem armazenados e podem ser reativados pelo administrador.")
        st.stop()

    authenticated_key = f"client_authenticated_{cycle.get('CICLO_ID', '')}"
    attempt_key = f"client_pin_attempts_{cycle.get('CICLO_ID', '')}"
    if not st.session_state.get(authenticated_key):
        st.subheader(str(company.get("NOME", "Empresa")))
        locked, remaining = is_locked(attempt_key)
        if locked:
            st.error(f"Muitas tentativas inválidas. Tente novamente em {remaining // 60 + 1} minuto(s).")
            st.stop()
        pin = st.text_input("PIN de acesso", type="password", max_chars=12)
        if st.button("Entrar", type="primary", use_container_width=True):
            if verify_pin(token, pin, str(cycle.get("PIN_HASH", ""))):
                clear_attempts(attempt_key)
                st.session_state[authenticated_key] = True
                log_audit(
                    "LOGIN_CLIENTE",
                    actor_type="CLIENTE",
                    company_id=str(company.get("EMPRESA_ID", "")),
                    cycle_id=str(cycle.get("CICLO_ID", "")),
                )
                st.rerun()
            register_failed_attempt(attempt_key)
            log_audit(
                "PIN_CLIENTE_INVALIDO",
                actor_type="CLIENTE",
                company_id=str(company.get("EMPRESA_ID", "")),
                cycle_id=str(cycle.get("CICLO_ID", "")),
            )
            st.error("PIN inválido.")
        st.caption("O PIN deve ser enviado separadamente do link. Após tentativas repetidas, o acesso é bloqueado temporariamente nesta sessão.")
        st.stop()

    responses_all = load_responses()
    responses = filter_cycle_responses(responses_all, company, cycle)
    response_count = len(responses)
    status = safe_status(cycle.get("STATUS"))
    contracted, unit_price, contract_value, over_limit = contracted_value(cycle, response_count)
    valid_until = parse_date(cycle.get("VALIDO_ATE"))
    min_group = campaign_min_group(cycle)
    instrument_ok, instrument_msg = response_validation_message(responses)

    st.subheader(str(company.get("NOME", "Empresa")))
    cols = st.columns(4)
    cols[0].metric("Respostas recebidas", response_count)
    cols[1].metric("Funcionários contratados", contracted or "—")
    cols[2].metric("Status", status.replace("_", " ").title())
    cols[3].metric("Acesso válido até", valid_until.strftime("%d/%m/%Y") if valid_until else "Sem data")

    if unit_price > 0:
        st.caption(f"Valor contratado: {brl(contract_value)} ({contracted} funcionário(s) × {brl(unit_price)}; mínimo considerado quando configurado).")
    if response_count:
        (st.success if instrument_ok else st.warning)(instrument_msg)

    refresh_col, updated_col = st.columns([1, 3])

    with refresh_col:
        if st.button(
            "🔄 Atualizar respostas",
            use_container_width=True,
            key=f"refresh_{cycle.get('CICLO_ID', '')}",
        ):
            st.toast("Contagem atualizada com sucesso.")

    with updated_col:
        st.caption(
            f"Dados consultados em {now_sp().strftime('%d/%m/%Y às %H:%M:%S')}."
        )

    render_pix_payment(company, cycle, contract_value)

    if over_limit:
        st.error(
            f"Há {response_count - contracted} resposta(s) acima do contratado. A geração permanece bloqueada até o ajuste comercial pelo administrador."
        )

    if status == "COLETA":
        st.info("A coleta está aberta. Compartilhe somente o link do formulário com os funcionários.")
        if backend_is_supabase():
            response_link = build_response_link(
                str(cycle.get("PARTICIPANT_TOKEN") or token)
            )
            st.code(response_link, language=None)
            st.link_button("Abrir formulário de resposta", response_link, use_container_width=True)
        else:
            form_link = build_form_link(company, cycle)
            if form_link:
                st.code(form_link, language=None)
                st.link_button("Abrir formulário", form_link, use_container_width=True)
            else:
                st.warning("O link-base do Google Forms ainda não está configurado nos Secrets.")

        st.markdown("### Encerrar a coleta")
        st.warning(
            "Ao solicitar o encerramento, o horário será congelado. Respostas enviadas depois desse momento não entrarão nesta edição."
        )
        confirmation = st.checkbox("Confirmo que a empresa concluiu a coleta deste ciclo.")
        if st.button("Solicitar encerramento e conferência", disabled=not confirmation, type="primary"):
            update_row(
                SHEET_CICLOS,
                CICLOS_HEADERS,
                cycle,
                {"STATUS": "AGUARDANDO_APROVACAO", "ENCERRADO_EM": iso_now(), "ULTIMA_ACAO_EM": iso_now()},
            )
            log_audit(
                "SOLICITAR_ENCERRAMENTO_COLETA",
                actor_type="CLIENTE",
                company_id=str(company.get("EMPRESA_ID", "")),
                cycle_id=str(cycle.get("CICLO_ID", "")),
                details={"respostas": response_count},
            )
            st.success("Coleta encerrada. O administrador fará a conferência comercial e liberará a geração.")
            st.rerun()

    elif status == "AGUARDANDO_APROVACAO":
        st.info("A coleta foi encerrada e aguarda conferência do número contratado e do pagamento.")

    elif status == "LIBERADO":
        if response_count < min_group:
            st.warning(
                f"São necessárias pelo menos {min_group} respostas para gerar resultados coletivos com proteção mínima contra identificação indireta."
            )
            st.stop()
        if over_limit:
            st.stop()
        if not is_yes(cycle.get("PAGAMENTO_OK", "")):
            st.warning("A geração ainda aguarda confirmação de pagamento pelo administrador.")
            st.stop()
        if not instrument_ok:
            st.error(instrument_msg)
            st.stop()

        st.success("Relatórios liberados para geração definitiva.")
        st.write(
            "A compra inclui a visão geral da empresa e os relatórios dos setores que atingirem o mínimo de confidencialidade. "
            "Depois da geração, novas respostas não alteram esta edição."
        )
        confirmation = st.checkbox("Confirmo a geração da edição definitiva deste ciclo.")
        if st.button("Gerar pacote definitivo", type="primary", disabled=not confirmation, use_container_width=True):
            update_row(SHEET_CICLOS, CICLOS_HEADERS, cycle, {"STATUS": "GERANDO"})
            try:
                with st.spinner("Gerando, armazenando e registrando os relatórios..."):
                    content, file_id, filename, zip_sha256, suppressed = generate_and_store_reports(company, cycle, responses)
                    update_row(
                        SHEET_CICLOS,
                        CICLOS_HEADERS,
                        cycle,
                        {
                            "STATUS": "GERADO",
                            "GERADO_EM": iso_now(),
                            "DRIVE_FILE_ID": file_id,
                            "DRIVE_FILE_NAME": filename,
                            "ZIP_SHA256": zip_sha256,
                            "VERSAO": str(get_app_setting("report_version", "4.0-v2-supabase-ready")),
                            "ULTIMA_ACAO_EM": iso_now(),
                        },
                    )
                    log_audit(
                        "GERAR_PACOTE_DEFINITIVO",
                        actor_type="CLIENTE",
                        company_id=str(company.get("EMPRESA_ID", "")),
                        cycle_id=str(cycle.get("CICLO_ID", "")),
                        details={"arquivo": filename, "sha256": zip_sha256, "respostas": response_count, "setores_suprimidos": suppressed},
                    )
                    st.session_state[f"generated_zip_{cycle.get('CICLO_ID')}"] = content
                    if suppressed:
                        st.warning(
                            "Alguns setores foram incluídos somente na visão geral por terem menos respostas que o mínimo de confidencialidade: "
                            + ", ".join(suppressed)
                        )
                    st.success("Pacote definitivo gerado. Ele poderá ser baixado novamente durante a validade do acesso.")
                    st.rerun()
            except Exception as exc:
                update_row(SHEET_CICLOS, CICLOS_HEADERS, cycle, {"STATUS": "LIBERADO", "ULTIMA_ACAO_EM": iso_now()})
                log_audit("FALHA_GERACAO", actor_type="SISTEMA", company_id=str(company.get("EMPRESA_ID", "")), cycle_id=str(cycle.get("CICLO_ID", "")), details={"erro": str(exc)})
                st.error(f"Falha ao gerar os relatórios: {exc}")

    elif status == "GERANDO":
        st.warning("A geração anterior não foi concluída. Solicite ao administrador que libere uma nova tentativa.")

    elif status == "GERADO":
        st.success("A edição definitiva já foi gerada. O download pode ser repetido enquanto o acesso estiver válido.")
        file_id = str(cycle.get("DRIVE_FILE_ID", "")).strip()
        filename = str(cycle.get("DRIVE_FILE_NAME", "relatorios.zip")).strip() or "relatorios.zip"
        if not file_id:
            st.error("Registro do arquivo não encontrado. Entre em contato com o administrador.")
            st.stop()
        key = f"download_zip_{file_id}"
        if key not in st.session_state:
            with st.spinner("Preparando o arquivo armazenado..."):
                st.session_state[key] = download_drive_file(file_id)
        st.download_button(
            "⬇️ Baixar pacote de relatórios",
            data=st.session_state[key],
            file_name=filename,
            mime="application/zip",
            type="primary",
            use_container_width=True,
        )
        generated_at = parse_datetime(cycle.get("GERADO_EM"))
        if generated_at:
            st.caption(f"Edição gerada em {generated_at.strftime('%d/%m/%Y às %H:%M')}.")
        if str(cycle.get("ZIP_SHA256", "")).strip():
            st.caption(f"Integridade do pacote (SHA-256): {cycle.get('ZIP_SHA256')}.")

    st.divider()
    st.caption(
        "Os resultados são coletivos e descritivos. Relatórios individuais não são disponibilizados à empresa nesta versão."
    )


# =============================================================================
# INTERFACE: ADMINISTRADOR
# =============================================================================

def verify_admin_password(password: str) -> bool:
    expected_hash = str(get_app_setting("admin_password_hash", "")).strip()
    if expected_hash:
        return verify_stored_secret(password, expected_hash, "ADMIN")
    expected_plain = str(get_app_setting("admin_password", "")).strip()
    return bool(expected_plain) and secure_secrets.compare_digest(password, expected_plain)


def render_admin_secret_diagnostics() -> None:
    expected_hash = str(get_app_setting("admin_password_hash", "")).strip()
    pepper = credential_pepper()
    expected_plain = str(get_app_setting("admin_password", "")).strip()
    with st.expander("Diagnóstico de autenticação", expanded=False):
        st.write(
            {
                "admin_password_hash_presente": bool(expected_hash),
                "admin_password_hash_v2": expected_hash.startswith("v2$") and len(expected_hash.split("$")) == 3,
                "admin_password_hash_id": secret_fingerprint(expected_hash),
                "credential_pepper_presente": bool(pepper),
                "credential_pepper_tamanho": len(pepper),
                "credential_pepper_id": secret_fingerprint(pepper),
                "admin_password_legado_configurado": bool(expected_plain),
            }
        )
        st.caption(
            "Esses IDs servem apenas para comparar o que o app online está lendo; eles não revelam os segredos."
        )


def admin_login() -> bool:
    if not str(get_app_setting("admin_password_hash", get_app_setting("admin_password", ""))).strip():
        st.error("Configure app.admin_password_hash nos Secrets. app.admin_password ainda funciona apenas como compatibilidade temporária.")
        render_admin_secret_diagnostics()
        return False
    if st.session_state.get("admin_authenticated"):
        return True
    attempt_key = "admin_login_attempts"
    locked, remaining = is_locked(attempt_key)
    if locked:
        st.error(f"Muitas tentativas inválidas. Tente novamente em {remaining // 60 + 1} minuto(s).")
        render_admin_secret_diagnostics()
        return False
    password = st.text_input("Senha administrativa", type="password")
    if st.button("Entrar no administrativo", type="primary"):
        if verify_admin_password(password):
            clear_attempts(attempt_key)
            st.session_state["admin_authenticated"] = True
            log_audit("LOGIN_ADMIN", actor_type="ADMIN", actor="admin")
            st.rerun()
        register_failed_attempt(attempt_key, max_attempts=5, lock_seconds=900)
        log_audit("LOGIN_ADMIN_INVALIDO", actor_type="ADMIN", actor="admin")
        st.error("Senha inválida.")
    render_admin_secret_diagnostics()
    return False

def render_admin() -> None:
    st.title("🛠️ Painel administrativo")
    if not admin_login():
        st.stop()

    ensure_structure()
    companies = read_sheet(SHEET_EMPRESAS)
    cycles = read_sheet(SHEET_CICLOS)
    responses_all = load_responses()

    tabs = st.tabs(["Visão geral", "Nova empresa", "Novo ciclo", "Gerenciar ciclo", "Auditoria", "Checklist"])

    with tabs[0]:
        st.subheader("Ciclos")
        if cycles.empty:
            st.info("Nenhum ciclo cadastrado.")
        else:
            rows = []
            for _, cycle in cycles.iterrows():
                company = find_company(companies, str(cycle.get("EMPRESA_ID", "")))
                company_name = str(company.get("NOME", "Empresa não encontrada")) if company is not None else "Empresa não encontrada"
                responses = filter_cycle_responses(responses_all, company, cycle) if company is not None else pd.DataFrame()
                contracted, unit_price, value, over = contracted_value(cycle, len(responses))
                rows.append(
                    {
                        "Empresa": company_name,
                        "Ciclo": cycle.get("CICLO_ID", ""),
                        "Ano": cycle.get("ANO", ""),
                        "Status": safe_status(cycle.get("STATUS")),
                        "Respostas": len(responses),
                        "Contratados": contracted,
                        "Excedente": max(0, len(responses) - contracted) if contracted else 0,
                        "Valor contratado": brl(value),
                        "Pagamento": "OK" if is_yes(cycle.get("PAGAMENTO_OK")) else "Pendente",
                        "Instrumento": response_validation_message(responses)[1] if len(responses) else "Sem respostas",
                        "SHA-256": cycle.get("ZIP_SHA256", ""),
                        "Válido até": cycle.get("VALIDO_ATE", ""),
                    }
                )
            st.dataframe(pd.DataFrame(rows), use_container_width=True, hide_index=True)

    with tabs[1]:
        st.subheader("Cadastrar empresa")
        with st.form("new_company"):
            name = st.text_input("Nome da empresa")
            cnpj = st.text_input("CNPJ")
            responsible = st.text_input("Responsável")
            email = st.text_input("E-mail do responsável")
            company_structure_text = (
                st.text_area(
                    "Áreas e grupos de análise",
                    placeholder=(
                        "Vendas | Administrativo\n"
                        "Recursos Humanos | Administrativo\n"
                        "Produção | Operacional"
                    ),
                    help=(
                        "Uma linha por área, no formato Área | Grupo. "
                        "O participante escolhe a área; o relatório usa o grupo."
                    ),
                )
                if backend_is_supabase()
                else ""
            )
            submitted = st.form_submit_button("Cadastrar", type="primary")
        if submitted:
            company_mappings: list[tuple[str, str]] = []
            structure_errors: list[str] = []
            if backend_is_supabase():
                company_mappings, structure_errors = parse_area_group_lines(
                    company_structure_text
                )
            if not name.strip() or structure_errors:
                if not name.strip():
                    st.error("Informe o nome da empresa.")
                for error in structure_errors:
                    st.error(error)
            else:
                company_id = make_company_id(name)
                created = append_row(
                    SHEET_EMPRESAS,
                    EMPRESAS_HEADERS,
                    {
                        "EMPRESA_ID": company_id,
                        "NOME": name.strip(),
                        "CNPJ": cnpj.strip(),
                        "RESPONSAVEL": responsible.strip(),
                        "EMAIL": email.strip(),
                        "ATIVO": "SIM",
                        "CRIADO_EM": iso_now(),
                    },
                )
                if created and created.get("EMPRESA_ID"):
                    company_id = str(created["EMPRESA_ID"])
                if backend_is_supabase():
                    supabase_repository().set_company_areas(
                        company_id,
                        company_mappings,
                    )
                log_audit("CADASTRAR_EMPRESA", actor_type="ADMIN", actor="admin", company_id=company_id, details={"nome": name.strip(), "areas": len(company_mappings)})
                st.success(f"Empresa cadastrada: {company_id}")
                st.rerun()

    with tabs[2]:
        st.subheader("Criar ciclo comercial")
        if companies.empty:
            st.warning("Cadastre uma empresa primeiro.")
        else:
            company_options = {
                f"{row.get('NOME', '')} — {row.get('EMPRESA_ID', '')}": row.get("EMPRESA_ID", "")
                for _, row in companies.iterrows()
                if is_yes(row.get("ATIVO", "SIM"))
            }
            with st.form("new_cycle"):
                selected_label = st.selectbox("Empresa", list(company_options.keys()))
                year = st.number_input("Ano/ciclo", min_value=2025, max_value=2100, value=now_sp().year, step=1)
                contracted = st.number_input("Funcionários contratados", min_value=1, value=10, step=1)
                unit_price = st.number_input("Preço por funcionário (R$)", min_value=0.0, value=0.0, step=1.0)
                minimum = st.number_input("Valor mínimo da compra (R$)", min_value=0.0, value=0.0, step=10.0)
                min_group_size = st.number_input(
                    "Mínimo de respostas por grupo",
                    min_value=2,
                    value=max(2, as_int(get_app_setting("min_group_size", 7), 7)),
                    step=1,
                    help="Grupos abaixo deste total não recebem relatório separado.",
                )
                cycle_structure_text = st.text_area(
                    "Áreas e grupos deste ciclo",
                    placeholder=(
                        "Vendas | Administrativo\n"
                        "Recursos Humanos | Administrativo\n"
                        "Produção | Operacional"
                    ),
                    help=(
                        "Informe para substituir/confirmar o cadastro da empresa. "
                        "Se deixar vazio, o sistema usa as áreas ativas já cadastradas."
                    ),
                )
                validity = st.number_input("Validade do acesso (dias)", min_value=1, value=90, step=1)
                create = st.form_submit_button("Criar ciclo e credenciais", type="primary")
            if create:
                company_id = str(company_options[selected_label])
                repo = supabase_repository() if backend_is_supabase() else None
                area_mappings: list[tuple[str, str]] = []
                structure_errors: list[str] = []
                if repo is not None and cycle_structure_text.strip():
                    area_mappings, structure_errors = parse_area_group_lines(
                        cycle_structure_text
                    )
                elif repo is not None:
                    saved_areas = repo.list_company_areas(company_id, active_only=True)
                    area_mappings = [
                        (
                            str(row.get("area_name") or row.get("sector_name") or "").strip(),
                            str(row.get("analysis_group_name") or row.get("area_name") or "").strip(),
                        )
                        for row in saved_areas
                        if str(row.get("area_name") or row.get("sector_name") or "").strip()
                    ]
                    if not area_mappings:
                        structure_errors.append(
                            "Informe as áreas e grupos deste ciclo antes de criá-lo."
                        )
                if structure_errors:
                    for error in structure_errors:
                        st.error(error)
                    st.stop()
                cycle_id = make_cycle_id(company_id, int(year))
                token, pin = make_access_credentials()
                start = now_sp()
                valid_until = (start + timedelta(days=int(validity))).date().isoformat()
                company_row = find_company(companies, company_id)
                controller_name = str(
                    company_row.get("NOME", "") if company_row is not None else ""
                ).strip()
                created = append_row(
                    SHEET_CICLOS,
                    CICLOS_HEADERS,
                    {
                        "CICLO_ID": cycle_id,
                        "EMPRESA_ID": company_id,
                        "ANO": int(year),
                        "TOKEN": token,
                        "PIN_HASH": pin_hash(token, pin),
                        "FUNCIONARIOS_CONTRATADOS": int(contracted),
                        "PRECO_POR_FUNCIONARIO": float(unit_price),
                        "VALOR_MINIMO": float(minimum),
                        "min_group_size": int(min_group_size),
                        "notice_version": PARTICIPANT_NOTICE_VERSION,
                        "notice_controller": controller_name,
                        "notice_operator": str(get_app_setting("operator_name", "Responsável pela operação da pesquisa")),
                        "notice_contact": str(get_app_setting("privacy_contact", "Canal informado pela organização")),
                        "notice_retention": str(get_app_setting("retention_policy", "Conforme contrato e política de privacidade")),
                        "notice_frozen_at": start.replace(microsecond=0).isoformat(),
                        "VALIDO_ATE": valid_until,
                        "STATUS": "COLETA",
                        "INICIO_EM": start.replace(microsecond=0).isoformat(),
                        "VERSAO": str(get_app_setting("report_version", "4.0-v2-supabase-ready")),
                        "PAGAMENTO_OK": "NAO",
                        "ULTIMA_ACAO_EM": iso_now(),
                    },
                )
                if created and created.get("CICLO_ID"):
                    cycle_id = str(created["CICLO_ID"])
                participant_token = str(
                    (created or {}).get("PARTICIPANT_TOKEN") or token
                )
                if repo is not None:
                    try:
                        if cycle_structure_text.strip():
                            repo.set_company_areas(company_id, area_mappings)
                        set_campaign_area_mappings(repo, cycle_id, area_mappings)
                    except Exception:
                        repo.update_campaign(cycle_id, {"status": "cancelled"})
                        raise
                log_audit(
                    "CRIAR_CICLO",
                    actor_type="ADMIN",
                    actor="admin",
                    company_id=company_id,
                    cycle_id=cycle_id,
                    details={"ano": int(year), "contratados": int(contracted), "validade_dias": int(validity), "areas": len(area_mappings), "min_grupo": int(min_group_size)},
                )
                st.success("Ciclo criado. Guarde o PIN; apenas o hash foi salvo.")
                st.caption("Link do painel do cliente")
                st.code(build_client_link(token), language=None)
                if backend_is_supabase():
                    st.caption("Link de resposta dos participantes")
                    st.code(build_response_link(participant_token), language=None)
                st.code(pin, language=None)
                st.warning("Envie o link e o PIN por canais separados.")

    with tabs[3]:
        st.subheader("Gerenciar ciclo")
        if cycles.empty:
            st.info("Nenhum ciclo cadastrado.")
        else:
            options: dict[str, str] = {}
            for _, row in cycles.iterrows():
                company = find_company(companies, str(row.get("EMPRESA_ID", "")))
                name = str(company.get("NOME", "?")) if company is not None else "?"
                label = f"{name} | {row.get('ANO', '')} | {safe_status(row.get('STATUS'))} | {row.get('CICLO_ID', '')}"
                options[label] = str(row.get("CICLO_ID", ""))
            selected = st.selectbox("Selecione", list(options.keys()))
            cycle = find_cycle(cycles, options[selected])
            if cycle is not None:
                company = find_company(companies, str(cycle.get("EMPRESA_ID", "")))
                responses = filter_cycle_responses(responses_all, company, cycle) if company is not None else pd.DataFrame()
                contracted, unit_price, value, over = contracted_value(cycle, len(responses))
                st.write(
                    {
                        "empresa": company.get("NOME", "") if company is not None else "",
                        "respostas": len(responses),
                        "contratados": contracted,
                        "excedente": max(0, len(responses) - contracted) if contracted else 0,
                        "valor_contratado": brl(value),
                        "status": safe_status(cycle.get("STATUS")),
                        "pagamento_ok": is_yes(cycle.get("PAGAMENTO_OK")),
                        "valido_ate": cycle.get("VALIDO_ATE", ""),
                        "sha256": cycle.get("ZIP_SHA256", ""),
                    }
                )
                if len(responses):
                    ok_msg = response_validation_message(responses)
                    (st.success if ok_msg[0] else st.warning)(ok_msg[1])

                if backend_is_supabase():
                    repo = supabase_repository()
                    configured_areas = load_campaign_sectors(
                        repo,
                        str(cycle.get("CICLO_ID", "")),
                    )
                    st.markdown("#### Áreas e grupos de análise")
                    if configured_areas:
                        st.dataframe(
                            pd.DataFrame(
                                [
                                    {
                                        "Área mostrada no formulário": row.get("sector_name", ""),
                                        "Grupo usado no relatório": row.get("analysis_group_name", ""),
                                    }
                                    for row in configured_areas
                                ]
                            ),
                            use_container_width=True,
                            hide_index=True,
                        )
                    else:
                        st.warning("Este ciclo ainda não possui áreas predefinidas.")

                    if len(responses) == 0:
                        with st.form(f"cycle_areas_{cycle.get('CICLO_ID', '')}"):
                            updated_structure_text = st.text_area(
                                "Definir áreas antes da primeira resposta",
                                placeholder=(
                                    "Vendas | Administrativo\n"
                                    "Recursos Humanos | Administrativo\n"
                                    "Produção | Operacional"
                                ),
                                help="Ao chegar a primeira resposta, esta estrutura fica congelada.",
                            )
                            save_structure = st.form_submit_button(
                                "Salvar áreas e grupos",
                                type="primary",
                            )
                        if save_structure:
                            mappings, errors = parse_area_group_lines(
                                updated_structure_text
                            )
                            if errors:
                                for error in errors:
                                    st.error(error)
                            else:
                                set_campaign_area_mappings(
                                    repo,
                                    str(cycle.get("CICLO_ID", "")),
                                    mappings,
                                )
                                if company is not None:
                                    repo.set_company_areas(
                                        str(company.get("EMPRESA_ID", "")),
                                        mappings,
                                    )
                                st.success("Estrutura salva para este ciclo.")
                                st.rerun()
                    else:
                        st.caption(
                            "A estrutura não pode ser alterada depois da primeira resposta. "
                            "Isso preserva o agrupamento do ciclo."
                        )

                c1, c2, c3, c4 = st.columns(4)
                if c1.button("Confirmar pagamento", use_container_width=True):
                    update_row(SHEET_CICLOS, CICLOS_HEADERS, cycle, {"PAGAMENTO_OK": "SIM", "ULTIMA_ACAO_EM": iso_now()})
                    log_audit("CONFIRMAR_PAGAMENTO", actor_type="ADMIN", actor="admin", company_id=str(cycle.get("EMPRESA_ID", "")), cycle_id=str(cycle.get("CICLO_ID", "")), details={"valor": value})
                    st.rerun()
                if c2.button("Liberar geração", use_container_width=True):
                    if len(responses) < campaign_min_group(cycle):
                        st.error("Quantidade abaixo do mínimo de confidencialidade.")
                    elif over:
                        st.error("Ajuste o número contratado antes de liberar.")
                    elif not is_yes(cycle.get("PAGAMENTO_OK")):
                        st.error("Confirme o pagamento antes de liberar.")
                    elif not response_validation_message(responses)[0]:
                        st.error(response_validation_message(responses)[1])
                    else:
                        changes = {"STATUS": "LIBERADO", "ULTIMA_ACAO_EM": iso_now()}
                        if not str(cycle.get("ENCERRADO_EM", "")).strip():
                            changes["ENCERRADO_EM"] = iso_now()
                        update_row(SHEET_CICLOS, CICLOS_HEADERS, cycle, changes)
                        log_audit("LIBERAR_GERACAO", actor_type="ADMIN", actor="admin", company_id=str(cycle.get("EMPRESA_ID", "")), cycle_id=str(cycle.get("CICLO_ID", "")), details={"respostas": len(responses)})
                        st.rerun()
                if c3.button("Reabrir coleta", use_container_width=True):
                    if safe_status(cycle.get("STATUS")) == "GERADO":
                        st.error("Uma edição já gerada é imutável. Crie outro ciclo ou use a liberação extraordinária abaixo.")
                    else:
                        update_row(
                            SHEET_CICLOS,
                            CICLOS_HEADERS,
                            cycle,
                            {"STATUS": "COLETA", "ENCERRADO_EM": "", "ULTIMA_ACAO_EM": iso_now()},
                        )
                        log_audit("REABRIR_COLETA", actor_type="ADMIN", actor="admin", company_id=str(cycle.get("EMPRESA_ID", "")), cycle_id=str(cycle.get("CICLO_ID", "")))
                        st.rerun()
                if c4.button("Estender +90 dias", use_container_width=True):
                    current = parse_date(cycle.get("VALIDO_ATE")) or now_sp().date()
                    base = max(current, now_sp().date())
                    update_row(
                        SHEET_CICLOS,
                        CICLOS_HEADERS,
                        cycle,
                        {"VALIDO_ATE": (base + timedelta(days=90)).isoformat(), "ULTIMA_ACAO_EM": iso_now()},
                    )
                    log_audit("ESTENDER_ACESSO", actor_type="ADMIN", actor="admin", company_id=str(cycle.get("EMPRESA_ID", "")), cycle_id=str(cycle.get("CICLO_ID", "")), details={"dias": 90})
                    st.rerun()

                st.markdown("#### Ajuste comercial")
                with st.form(f"adjust_{cycle.get('CICLO_ID')}"):
                    new_contracted = st.number_input(
                        "Funcionários contratados",
                        min_value=1,
                        value=max(1, contracted),
                        step=1,
                    )
                    new_unit = st.number_input(
                        "Preço por funcionário (R$)",
                        min_value=0.0,
                        value=float(unit_price),
                        step=1.0,
                    )
                    new_minimum = st.number_input(
                        "Valor mínimo (R$)",
                        min_value=0.0,
                        value=float(as_float(cycle.get("VALOR_MINIMO"))),
                        step=10.0,
                    )
                    save_adjustment = st.form_submit_button("Salvar ajuste")
                if save_adjustment:
                    update_row(
                        SHEET_CICLOS,
                        CICLOS_HEADERS,
                        cycle,
                        {
                            "FUNCIONARIOS_CONTRATADOS": int(new_contracted),
                            "PRECO_POR_FUNCIONARIO": float(new_unit),
                            "VALOR_MINIMO": float(new_minimum),
                            "ULTIMA_ACAO_EM": iso_now(),
                        },
                    )
                    log_audit("AJUSTAR_COMERCIAL", actor_type="ADMIN", actor="admin", company_id=str(cycle.get("EMPRESA_ID", "")), cycle_id=str(cycle.get("CICLO_ID", "")), details={"contratados": int(new_contracted), "preco_unitario": float(new_unit), "valor_minimo": float(new_minimum)})
                    st.rerun()

                if safe_status(cycle.get("STATUS")) == "GERANDO":
                    if st.button("Recuperar geração travada (voltar para LIBERADO)"):
                        update_row(SHEET_CICLOS, CICLOS_HEADERS, cycle, {"STATUS": "LIBERADO", "ULTIMA_ACAO_EM": iso_now()})
                        log_audit("RECUPERAR_GERACAO_TRAVADA", actor_type="ADMIN", actor="admin", company_id=str(cycle.get("EMPRESA_ID", "")), cycle_id=str(cycle.get("CICLO_ID", "")))
                        st.rerun()

                if safe_status(cycle.get("STATUS")) == "GERADO" and str(cycle.get("DRIVE_FILE_ID", "")).strip():
                    file_id = str(cycle.get("DRIVE_FILE_ID"))
                    key = f"admin_download_{file_id}"
                    if key not in st.session_state:
                        if st.button("Preparar arquivo armazenado"):
                            st.session_state[key] = download_drive_file(file_id)
                            st.rerun()
                    if key in st.session_state:
                        st.download_button(
                            "Baixar pacote como administrador",
                            data=st.session_state[key],
                            file_name=str(cycle.get("DRIVE_FILE_NAME", "relatorios.zip")),
                            mime="application/zip",
                        )

                st.markdown("#### Acesso")
                st.caption("Painel do cliente")
                st.code(build_client_link(str(cycle.get("TOKEN", ""))), language=None)
                if backend_is_supabase():
                    st.caption("Formulário anônimo dos participantes")
                    st.code(build_response_link(str(cycle.get("TOKEN", ""))), language=None)
                st.caption("O PIN original não pode ser recuperado. Para trocar o PIN, gere um novo abaixo.")
                if st.button("Gerar novo PIN"):
                    new_pin = f"{secure_secrets.randbelow(1_000_000):06d}"
                    update_row(
                        SHEET_CICLOS,
                        CICLOS_HEADERS,
                        cycle,
                        {"PIN_HASH": pin_hash(str(cycle.get("TOKEN", "")), new_pin), "ULTIMA_ACAO_EM": iso_now()},
                    )
                    log_audit("GERAR_NOVO_PIN", actor_type="ADMIN", actor="admin", company_id=str(cycle.get("EMPRESA_ID", "")), cycle_id=str(cycle.get("CICLO_ID", "")))
                    st.success("Novo PIN gerado. Copie agora:")
                    st.code(new_pin, language=None)

                with st.expander("Ações excepcionais"):
                    st.warning("Use somente após novo pagamento ou correção administrativa formal.")
                    if st.button("Liberar nova geração e substituir a edição anterior"):
                        old_file_id = str(cycle.get("DRIVE_FILE_ID", "")).strip()
                        if old_file_id:
                            trash_drive_file(old_file_id)
                        update_row(
                            SHEET_CICLOS,
                            CICLOS_HEADERS,
                            cycle,
                            {
                                "STATUS": "LIBERADO",
                                "GERADO_EM": "",
                                "DRIVE_FILE_ID": "",
                                "DRIVE_FILE_NAME": "",
                                "ZIP_SHA256": "",
                                "ULTIMA_ACAO_EM": iso_now(),
                            },
                        )
                        log_audit("LIBERAR_REGERACAO_EXCEPCIONAL", actor_type="ADMIN", actor="admin", company_id=str(cycle.get("EMPRESA_ID", "")), cycle_id=str(cycle.get("CICLO_ID", "")), details={"arquivo_antigo_lixeira": old_file_id})
                        st.rerun()
                    if st.button("Cancelar ciclo"):
                        update_row(SHEET_CICLOS, CICLOS_HEADERS, cycle, {"STATUS": "CANCELADO", "ULTIMA_ACAO_EM": iso_now()})
                        log_audit("CANCELAR_CICLO", actor_type="ADMIN", actor="admin", company_id=str(cycle.get("EMPRESA_ID", "")), cycle_id=str(cycle.get("CICLO_ID", "")))
                        st.rerun()


    with tabs[4]:
        st.subheader("Auditoria")
        audit = read_sheet(SHEET_AUDITORIA)
        if audit.empty:
            st.info("Nenhum evento registrado ainda.")
        else:
            visible_cols = [c for c in ["OCORRIDO_EM", "TIPO_ATOR", "ATOR", "EMPRESA_ID", "CICLO_ID", "ACAO", "DETALHES_JSON"] if c in audit.columns]
            st.dataframe(audit[visible_cols].tail(200).iloc[::-1], use_container_width=True, hide_index=True)

    with tabs[5]:
        st.subheader("Checklist operacional antes de vender")
        checks = [
            "Secrets configurados fora do repositório, com app.credential_pepper e app.admin_password_hash.",
            "Google Form revisado para evitar coleta desnecessária de nome, CPF ou e-mail.",
            "Aviso aos participantes enviado/aceito antes da resposta.",
            "Contrato com a empresa definindo controlador, operador, retenção e escopo pós-entrega.",
            "Mínimo de confidencialidade configurado e respeitado nos recortes setoriais.",
            "Devolutiva técnica agendada com o psicólogo parceiro antes da implantação de medidas.",
            "Relatório tratado como apoio à gestão, não como laudo clínico/pericial nem garantia automática de conformidade.",
        ]
        for item in checks:
            st.checkbox(item, value=False)


# =============================================================================
# EXECUÇÃO
# =============================================================================

def main() -> None:
    try:
        if (get_query_value("respond") or get_query_value("responder")).strip():
            render_response_form()
            return
        admin_mode = get_query_value("admin") == "1"
        if admin_mode:
            render_admin()
        else:
            render_client()
    except Exception as exc:
        st.error(f"Erro de configuração ou conexão: {exc}")
        st.caption("Consulte o SETUP.md e os Secrets do Streamlit antes de publicar.")


if __name__ == "__main__":
    main()

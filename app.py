from __future__ import annotations

import hashlib
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

from reporting import (
    ESCALA_ORDEM,
    FATORES,
    QUESTIONARIO,
    ReportConfig,
    generate_company_reports,
    normalize_dataframe_columns,
    normalize_header,
    normalize_text,
)


# =============================================================================
# CONFIGURAÇÃO
# =============================================================================

TZ = ZoneInfo("America/Sao_Paulo")
PARTICIPANT_NOTICE_VERSION = "2026-07-11"
PARTICIPANT_NOTICE_TEMPLATES = {
    "2026-07-11": """
Esta pesquisa tem a finalidade de identificar, de forma coletiva, aspectos da organização e das condições de trabalho que possam orientar ações de prevenção e melhoria.

O formulário não solicita nome, CPF ou e-mail. O campo de cargo ou função é opcional; deixe-o em branco se a informação puder identificar você. Evite informar dados que permitam identificar você ou outras pessoas. As respostas não serão utilizadas para diagnóstico clínico, avaliação de desempenho, punição ou decisão individual sobre trabalhadores.

A organização receberá somente resultados agrupados. Grupos com menos de **{min_group} respostas** não terão relatório separado; outras supressões podem ser aplicadas para impedir inferência por diferença. Essas respostas poderão compor apenas a visão geral. Relatórios individuais não serão entregues à organização.

O acesso às respostas brutas é restrito às pessoas autorizadas pela prestadora do serviço e usado somente para processamento, controle de qualidade e geração dos resultados contratados.
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
    "VERSAO",
    "PAGAMENTO_OK",
    "OBSERVACOES",
    "MIN_GRUPO",
    "AVISO_VERSAO",
    "AVISO_CONTROLADOR",
    "AVISO_OPERADOR",
    "AVISO_CONTATO",
    "AVISO_RETENCAO",
]

ESTRUTURA_HEADERS = [
    "ESTRUTURA_ID",
    "EMPRESA_ID",
    "AREA_TRABALHO",
    "GRUPO_ID",
    "GRUPO_ANALISE",
    "ATIVO",
    "ORDEM",
    "CRIADO_EM",
]

ESTRUTURA_CICLO_HEADERS = [
    "CICLO_ID",
    "EMPRESA_ID",
    "ESTRUTURA_ID",
    "AREA_TRABALHO",
    "GRUPO_ID",
    "GRUPO_ANALISE",
    "ORDEM",
    "CRIADO_EM",
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
    "VERSAO",
]

RESPOSTAS_HEADERS = [
    "CARIMBO_DE_DATA_HORA",
    "EMPRESA_ID",
    "CICLO_ID",
    "NOME_DA_EMPRESA",
    "GRUPO_ID",
    "GRUPO_ANALISE",
    "SETOR",
    "CARGO_ATUAL",
    "CIENCIA_AVISO",
    "AVISO_VERSAO",
    "CIENCIA_AVISO_EM",
    *QUESTIONARIO.values(),
]

SHEET_EMPRESAS = "Empresas"
SHEET_CICLOS = "Ciclos"
SHEET_RELATORIOS = "Relatorios"
SHEET_RESPOSTAS = "Respostas"
SHEET_ESTRUTURA = "Estrutura"
SHEET_ESTRUTURA_CICLOS = "EstruturaCiclos"

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
    try:
        return float(str(value).replace(".", "").replace(",", ".")) if "," in str(value) else float(value)
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


def pin_hash(token: str, pin: str) -> str:
    return hashlib.sha256(f"{token}:{pin}".encode("utf-8")).hexdigest()


def verify_pin(token: str, pin: str, expected_hash: str) -> bool:
    if not token or not pin or not expected_hash:
        return False
    return secure_secrets.compare_digest(pin_hash(token, pin), str(expected_hash).strip())


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


def make_structure_id(company_id: str) -> str:
    return f"EST_{hashlib.sha256(company_id.encode('utf-8')).hexdigest()[:8].upper()}_{secure_secrets.token_hex(3).upper()}"


def make_group_id(company_id: str, group_name: str) -> str:
    canonical = f"{company_id}:{normalize_text(group_name)}"
    return f"GRP_{hashlib.sha256(canonical.encode('utf-8')).hexdigest()[:12].upper()}"


def make_access_credentials() -> tuple[str, str]:
    return secure_secrets.token_urlsafe(32), f"{secure_secrets.randbelow(1_000_000):06d}"


def make_participant_token() -> str:
    return secure_secrets.token_urlsafe(32)


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


def cycle_min_group(cycle: pd.Series | dict[str, Any]) -> int:
    configured = as_int(cycle.get("MIN_GRUPO", ""), 0)
    if configured <= 0:
        configured = as_int(get_app_setting("min_group_size", 5), 5)
    return max(2, configured)


def parse_structure_lines(value: str) -> tuple[list[tuple[str, str]], list[str]]:
    """Interpreta `Área | Grupo`; sem separador, usa o mesmo nome nos dois níveis."""
    parsed: list[tuple[str, str]] = []
    errors: list[str] = []
    seen: dict[str, str] = {}

    for line_number, raw_line in enumerate(str(value).splitlines(), start=1):
        line = raw_line.strip()
        if not line:
            continue
        parts = [part.strip() for part in line.split("|")]
        if len(parts) == 1:
            area = group = parts[0]
        elif len(parts) == 2:
            area, group = parts
        else:
            errors.append(f"Linha {line_number}: use somente o formato Área | Grupo de análise.")
            continue
        if not area or not group:
            errors.append(f"Linha {line_number}: informe a área e o grupo de análise.")
            continue
        area_key = normalize_text(area)
        group_key = normalize_text(group)
        previous = seen.get(area_key)
        if previous and previous != group_key:
            errors.append(f"Linha {line_number}: a área '{area}' aparece associada a mais de um grupo.")
            continue
        if previous:
            continue
        seen[area_key] = group_key
        parsed.append((area, group))

    if not parsed and not errors:
        errors.append("Informe pelo menos uma área ou grupo de análise.")
    return parsed, errors


def active_company_structures(structures: pd.DataFrame, company_id: str) -> pd.DataFrame:
    if structures.empty or "EMPRESA_ID" not in structures.columns:
        return structures.iloc[0:0].copy()
    result = structures[structures["EMPRESA_ID"].astype(str).str.strip() == str(company_id).strip()].copy()
    if "ATIVO" in result.columns:
        result = result[result["ATIVO"].map(is_yes)]
    if "ORDEM" in result.columns:
        result["__ORDEM_NUM__"] = result["ORDEM"].map(lambda value: as_int(value, 999999))
        result = result.sort_values(["__ORDEM_NUM__", "AREA_TRABALHO"], kind="stable")
        result = result.drop(columns=["__ORDEM_NUM__"])
    return result


def cycle_structure_rows(structures: pd.DataFrame, cycle_id: str) -> pd.DataFrame:
    if structures.empty or "CICLO_ID" not in structures.columns:
        return structures.iloc[0:0].copy()
    result = structures[structures["CICLO_ID"].astype(str).str.strip() == str(cycle_id).strip()].copy()
    if "ORDEM" in result.columns:
        result["__ORDEM_NUM__"] = result["ORDEM"].map(lambda value: as_int(value, 999999))
        result = result.sort_values(["__ORDEM_NUM__", "AREA_TRABALHO"], kind="stable")
        result = result.drop(columns=["__ORDEM_NUM__"])
    return result


def notice_is_complete(cycle: pd.Series | dict[str, Any]) -> bool:
    required = (
        "AVISO_VERSAO",
        "AVISO_CONTROLADOR",
        "AVISO_OPERADOR",
        "AVISO_CONTATO",
        "AVISO_RETENCAO",
    )
    version = str(cycle.get("AVISO_VERSAO", "")).strip()
    return (
        version in PARTICIPANT_NOTICE_TEMPLATES
        and all(str(cycle.get(field, "")).strip() for field in required)
    )


def participant_form_ready(
    cycle: pd.Series | dict[str, Any],
    structures: pd.DataFrame,
) -> bool:
    return (
        notice_is_complete(cycle)
        and bool(str(cycle.get("PARTICIPANT_TOKEN", "")).strip())
        and not structures.empty
    )


def make_structure_records(
    company_id: str,
    mappings: list[tuple[str, str]],
    *,
    start_order: int = 1,
) -> list[dict[str, Any]]:
    created_at = iso_now()
    return [
        {
            "ESTRUTURA_ID": make_structure_id(company_id),
            "EMPRESA_ID": company_id,
            "AREA_TRABALHO": area,
            "GRUPO_ID": make_group_id(company_id, group),
            "GRUPO_ANALISE": group,
            "ATIVO": "SIM",
            "ORDEM": start_order + offset,
            "CRIADO_EM": created_at,
        }
        for offset, (area, group) in enumerate(mappings)
    ]


def make_cycle_structure_records(
    cycle_id: str,
    company_id: str,
    structures: pd.DataFrame,
) -> list[dict[str, Any]]:
    created_at = iso_now()
    return [
        {
            "CICLO_ID": cycle_id,
            "EMPRESA_ID": company_id,
            "ESTRUTURA_ID": row.get("ESTRUTURA_ID", ""),
            "AREA_TRABALHO": row.get("AREA_TRABALHO", ""),
            "GRUPO_ID": row.get("GRUPO_ID", ""),
            "GRUPO_ANALISE": row.get("GRUPO_ANALISE", ""),
            "ORDEM": row.get("ORDEM", index + 1),
            "CRIADO_EM": created_at,
        }
        for index, (_, row) in enumerate(structures.iterrows())
    ]


# =============================================================================
# GOOGLE SHEETS / DRIVE
# =============================================================================

RETRYABLE_HTTP_STATUS = {408, 429, 500, 502, 503, 504}


def execute_google_read(
    request_factory,
    operation: str,
    max_attempts: int = 4,
):
    # Executa leitura idempotente do Google com espera exponencial.
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
        scopes=["https://www.googleapis.com/auth/drive"],
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
    metadata = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id()).execute()
    existing = {item["properties"]["title"] for item in metadata.get("sheets", [])}
    if sheet_name not in existing:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id(),
            body={"requests": [{"addSheet": {"properties": {"title": sheet_name}}}]},
        ).execute()
    current = get_sheet_headers(sheet_name)
    if not current:
        merged = list(headers)
    else:
        merged = current + [header for header in headers if header not in current]
    if merged != current:
        sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id(),
            range=f"'{sheet_name}'!A1:{last_column_letter(len(merged))}1",
            valueInputOption="RAW",
            body={"values": [merged]},
        ).execute()


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
    ensure_sheet(SHEET_EMPRESAS, EMPRESAS_HEADERS)
    ensure_sheet(SHEET_CICLOS, CICLOS_HEADERS)
    ensure_sheet(SHEET_RELATORIOS, RELATORIOS_HEADERS)
    ensure_sheet(SHEET_ESTRUTURA, ESTRUTURA_HEADERS)
    ensure_sheet(SHEET_ESTRUTURA_CICLOS, ESTRUTURA_CICLO_HEADERS)
    ensure_response_sheet()
    migrate_existing_companies()


def append_rows(sheet_name: str, headers: list[str], rows: list[dict[str, Any]]) -> None:
    if not rows:
        return
    ensure_sheet(sheet_name, headers)
    actual_headers = get_sheet_headers(sheet_name)
    sheets = sheets_service()
    values = [[row.get(header, "") for header in actual_headers] for row in rows]
    sheets.spreadsheets().values().append(
        spreadsheetId=spreadsheet_id(),
        range=f"'{sheet_name}'!A:{last_column_letter(len(actual_headers))}",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": values},
    ).execute()


def append_row(sheet_name: str, headers: list[str], data: dict[str, Any]) -> None:
    append_rows(sheet_name, headers, [data])


def ensure_response_sheet() -> list[str]:
    """Preserva cabeçalhos do Forms e evita duplicá-los apenas por acento/formatação."""
    sheets = sheets_service()
    metadata = sheets.spreadsheets().get(spreadsheetId=spreadsheet_id()).execute()
    existing = {item["properties"]["title"] for item in metadata.get("sheets", [])}
    if SHEET_RESPOSTAS not in existing:
        sheets.spreadsheets().batchUpdate(
            spreadsheetId=spreadsheet_id(),
            body={"requests": [{"addSheet": {"properties": {"title": SHEET_RESPOSTAS}}}]},
        ).execute()

    current = get_sheet_headers(SHEET_RESPOSTAS)
    current_normalized = {normalize_header(header) for header in current}
    merged = list(current)
    for header in RESPOSTAS_HEADERS:
        if normalize_header(header) not in current_normalized:
            merged.append(header)
            current_normalized.add(normalize_header(header))
    if not merged:
        merged = list(RESPOSTAS_HEADERS)
    if merged != current:
        sheets.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id(),
            range=f"'{SHEET_RESPOSTAS}'!A1:{last_column_letter(len(merged))}1",
            valueInputOption="RAW",
            body={"values": [merged]},
        ).execute()
    return merged


def append_response(data: dict[str, Any]) -> None:
    actual_headers = ensure_response_sheet()
    normalized_data = {normalize_header(header): value for header, value in data.items()}
    values = [[normalized_data.get(normalize_header(header), "") for header in actual_headers]]
    sheets_service().spreadsheets().values().append(
        spreadsheetId=spreadsheet_id(),
        range=f"'{SHEET_RESPOSTAS}'!A:{last_column_letter(len(actual_headers))}",
        valueInputOption="RAW",
        insertDataOption="INSERT_ROWS",
        body={"values": values},
    ).execute()


def update_row(sheet_name: str, headers: list[str], current: dict[str, Any] | pd.Series, changes: dict[str, Any]) -> None:
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
    sheets.spreadsheets().values().batchUpdate(
        spreadsheetId=spreadsheet_id(),
        body={"valueInputOption": "RAW", "data": data},
    ).execute()

def upload_zip_to_drive(content: bytes, filename: str) -> str:
    drive = drive_service()
    folder_id = str(st.secrets.get("drive", {}).get("folder_id", "")).strip()
    metadata: dict[str, Any] = {
        "name": filename,
        "mimeType": "application/zip",
    }
    if folder_id:
        metadata["parents"] = [folder_id]
    media = MediaIoBaseUpload(BytesIO(content), mimetype="application/zip", resumable=False)
    created = drive.files().create(body=metadata, media_body=media, fields="id,name").execute()
    return str(created["id"])


def download_drive_file(file_id: str) -> bytes:
    drive = drive_service()
    request = drive.files().get_media(fileId=file_id)
    buffer = BytesIO()
    downloader = MediaIoBaseDownload(buffer, request)
    done = False
    while not done:
        _, done = downloader.next_chunk()
    return buffer.getvalue()


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


def find_cycle_by_participant_token(cycles: pd.DataFrame, token: str) -> pd.Series | None:
    if cycles.empty or "PARTICIPANT_TOKEN" not in cycles.columns:
        return None
    matches = cycles[cycles["PARTICIPANT_TOKEN"].astype(str) == str(token)]
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


def filter_notice_responses(df: pd.DataFrame, cycle: pd.Series | dict[str, Any]) -> pd.DataFrame:
    required_version = str(cycle.get("AVISO_VERSAO", "")).strip()
    if not required_version:
        return df.copy()
    if "CIENCIA_AVISO" not in df.columns or "AVISO_VERSAO" not in df.columns:
        return df.iloc[0:0].copy()
    accepted = df["CIENCIA_AVISO"].map(is_yes)
    matching_version = df["AVISO_VERSAO"].astype(str).str.strip() == required_version
    return df[accepted & matching_version].copy()


def filter_cycle_responses(
    df: pd.DataFrame,
    company: pd.Series,
    cycle: pd.Series,
    *,
    require_notice: bool = True,
) -> pd.DataFrame:
    if df.empty:
        return df.copy()
    result = df.copy()
    cycle_id = str(cycle.get("CICLO_ID", "")).strip()
    company_id = str(company.get("EMPRESA_ID", "")).strip()
    company_name = normalize_text(company.get("NOME", ""))

    cycle_values = (
        result["CICLO_ID"].astype(str).str.strip()
        if "CICLO_ID" in result.columns
        else pd.Series("", index=result.index, dtype="object")
    )
    exact_cycle = cycle_values == cycle_id
    if exact_cycle.any():
        result = result[exact_cycle].copy()
        if "EMPRESA_ID" in result.columns:
            ids = result["EMPRESA_ID"].astype(str).str.strip()
            result = result[(ids == "") | (ids == company_id)]
    else:
        # Linhas antigas podem não ter IDs. Em uma planilha mista, somente linhas
        # sem CICLO_ID participam dos fallbacks para não contaminar ciclos legados.
        legacy = result[cycle_values == ""].copy()
        if "EMPRESA_ID" in legacy.columns:
            company_values = legacy["EMPRESA_ID"].astype(str).str.strip()
            exact_company = company_values == company_id
            if exact_company.any():
                result = legacy[exact_company].copy()
            else:
                legacy = legacy[company_values == ""].copy()
                if "NOME_DA_EMPRESA" not in legacy.columns:
                    return legacy.iloc[0:0].copy()
                result = legacy[legacy["NOME_DA_EMPRESA"].map(normalize_text) == company_name].copy()
        elif "NOME_DA_EMPRESA" in legacy.columns:
            result = legacy[legacy["NOME_DA_EMPRESA"].map(normalize_text) == company_name].copy()
        else:
            return legacy.iloc[0:0].copy()

    timestamp_col = response_timestamp_column(result)
    if timestamp_col:
        timestamps = result[timestamp_col].map(parse_datetime).map(
            lambda value: value.replace(tzinfo=None) if value else pd.NaT
        )
        start = parse_datetime(cycle.get("INICIO_EM"))
        end = parse_datetime(cycle.get("ENCERRADO_EM"))
        if start:
            start_naive = start.replace(tzinfo=None)
            result = result[timestamps >= start_naive]
            timestamps = timestamps.loc[result.index]
        if end:
            end_naive = end.replace(tzinfo=None)
            result = result[timestamps <= end_naive]
    if require_notice:
        result = filter_notice_responses(result, cycle)
    return result.copy()


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


def build_app_link(parameter: str, value: str) -> str:
    base_url = str(get_app_setting("base_url", "")).strip()
    if not base_url:
        return f"?{urlencode({parameter: value})}"
    parts = urlsplit(base_url)
    params = dict(parse_qsl(parts.query, keep_blank_values=True))
    for mode_parameter in ("admin", "token", "participar"):
        params.pop(mode_parameter, None)
    params[parameter] = value
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
    return build_app_link("token", token)


def build_participant_link(token: str) -> str:
    return build_app_link("participar", token)


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


def generate_and_store_reports(company: pd.Series, cycle: pd.Series, responses: pd.DataFrame) -> tuple[bytes, str, str, list[str]]:
    min_group = cycle_min_group(cycle)
    report_version = str(get_app_setting("report_version", "2.0"))
    config = ReportConfig(min_group_size=min_group, report_version=report_version)
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
        "respostas": len(responses),
        "grupos_suprimidos_por_confidencialidade": len(suppressed),
        "versao": report_version,
        "arquivos": [report.filename for report in reports],
        "observacao": "Pacote definitivo do ciclo. Re-download permitido; recálculo exige reabertura administrativa.",
    }
    zip_content = create_zip(reports, manifest)
    safe_company = "_".join(normalize_text(company_name).split())[:60]
    filename = f"Relatorios_{safe_company}_{cycle.get('ANO', now_sp().year)}_{generated_at.strftime('%Y%m%d')}.zip"
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
                "VERSAO": report_version,
            },
        )
    return zip_content, file_id, filename, suppressed


# =============================================================================
# INTERFACE: PARTICIPANTE
# =============================================================================

def render_participant_notice(company: pd.Series, cycle: pd.Series) -> None:
    min_group = cycle_min_group(cycle)
    version = str(cycle.get("AVISO_VERSAO", "")).strip()
    template = PARTICIPANT_NOTICE_TEMPLATES.get(version)
    if template is None:
        raise ValueError(f"Versão do aviso não suportada: {version or 'ausente'}")
    st.subheader("Aviso aos participantes")
    st.markdown(template.format(min_group=min_group))
    st.markdown(
        f"""
- **Controlador dos dados:** {cycle.get('AVISO_CONTROLADOR', company.get('NOME', ''))}
- **Operador/prestador do serviço:** {cycle.get('AVISO_OPERADOR', '')}
- **Contato para dúvidas e direitos dos titulares:** {cycle.get('AVISO_CONTATO', '')}
- **Prazo e critério de retenção:** {cycle.get('AVISO_RETENCAO', '')}
"""
    )
    st.caption(f"Versão do aviso: {version}")


def render_participant() -> None:
    st.title("📋 Pesquisa sobre condições psicossociais do trabalho")
    token = get_query_value("participar").strip()
    if not token:
        st.error("Link de participação ausente ou inválido.")
        st.stop()

    companies = read_sheet(SHEET_EMPRESAS)
    cycles = read_sheet(SHEET_CICLOS)
    cycle = find_cycle_by_participant_token(cycles, token)
    if cycle is None:
        st.error("Link de participação inválido ou revogado.")
        st.stop()
    company = find_company(companies, str(cycle.get("EMPRESA_ID", "")))
    if company is None or not is_yes(company.get("ATIVO", "SIM")):
        st.error("Esta pesquisa não está disponível.")
        st.stop()
    if safe_status(cycle.get("STATUS")) != "COLETA":
        st.info("A coleta desta pesquisa não está aberta.")
        st.stop()
    if cycle_expired(cycle):
        st.info("O prazo para participar desta pesquisa terminou.")
        st.stop()
    if not notice_is_complete(cycle):
        st.error("O aviso desta pesquisa ainda não foi finalizado. Avise o responsável pela organização.")
        st.stop()

    structures_all = read_sheet(SHEET_ESTRUTURA_CICLOS)
    structures = cycle_structure_rows(structures_all, str(cycle.get("CICLO_ID", "")))
    if structures.empty:
        st.error("As áreas desta pesquisa ainda não foram configuradas. Avise o responsável pela organização.")
        st.stop()

    cycle_id = str(cycle.get("CICLO_ID", ""))
    accepted_key = f"participant_notice_{cycle_id}"
    declined_key = f"participant_declined_{cycle_id}"
    submitted_key = f"participant_submitted_{cycle_id}"

    st.caption(str(company.get("NOME", "Organização")))
    if st.session_state.get(submitted_key):
        st.success("Resposta enviada. Obrigado por participar.")
        st.info("Você já pode fechar esta página.")
        st.stop()
    if st.session_state.get(declined_key):
        st.info("Nenhuma resposta foi coletada. Você já pode fechar esta página.")
        st.stop()

    if not st.session_state.get(accepted_key):
        render_participant_notice(company, cycle)
        decision = st.radio(
            "Depois de ler o aviso, escolha uma opção:",
            (
                "Li as informações e desejo participar",
                "Não desejo participar",
            ),
            index=None,
            key=f"participant_decision_{cycle_id}",
        )
        if st.button("Continuar", type="primary", disabled=decision is None, use_container_width=True):
            if decision == "Li as informações e desejo participar":
                st.session_state[accepted_key] = iso_now()
            else:
                st.session_state[declined_key] = True
            st.rerun()
        st.stop()

    with st.expander("Rever o aviso aos participantes"):
        render_participant_notice(company, cycle)

    structure_options = {
        str(row.get("ESTRUTURA_ID", "")): str(row.get("AREA_TRABALHO", ""))
        for _, row in structures.iterrows()
        if str(row.get("ESTRUTURA_ID", "")).strip() and str(row.get("AREA_TRABALHO", "")).strip()
    }
    with st.form(f"anonymous_survey_{cycle_id}"):
        st.markdown("### Sobre o seu trabalho")
        selected_structure_id = st.selectbox(
            "Em qual área você trabalha?",
            list(structure_options.keys()),
            index=None,
            placeholder="Selecione uma área",
            format_func=lambda value: structure_options.get(value, value),
            help="As opções foram definidas previamente pela organização.",
            key=f"participant_area_{cycle_id}",
        )
        current_job = st.text_input(
            "Cargo ou função atual (opcional)",
            help="Exemplos: Vendedor, Analista de RH. Este campo não define o grupo do relatório.",
            key=f"participant_job_{cycle_id}",
        )

        st.markdown("### Questionário")
        st.caption("Considere sua experiência de trabalho e marque uma opção em cada item.")
        answers: dict[int, str | None] = {}
        factor_starts = {int(factor["itens"][0]): str(factor["nome"]) for factor in FATORES}
        for number, question in QUESTIONARIO.items():
            if number in factor_starts:
                st.markdown(f"#### {factor_starts[number]}")
            answers[number] = st.radio(
                f"{number}. {question.capitalize()}",
                ESCALA_ORDEM,
                index=None,
                horizontal=True,
                key=f"survey_{cycle_id}_{number}",
            )

        submitted = st.form_submit_button("Enviar resposta", type="primary", use_container_width=True)

    if submitted:
        if not st.session_state.get(accepted_key):
            st.error("Leia e confirme o aviso antes de responder.")
            st.stop()
        if not selected_structure_id or selected_structure_id not in structure_options:
            st.error("Selecione a sua área de trabalho.")
            st.stop()
        unanswered = [number for number, answer in answers.items() if answer is None]
        if unanswered:
            st.error("Responda todos os itens antes de enviar. Itens pendentes: " + ", ".join(map(str, unanswered)))
            st.stop()

        selected = structures[
            structures["ESTRUTURA_ID"].astype(str).str.strip() == str(selected_structure_id).strip()
        ].iloc[0]
        response: dict[str, Any] = {
            "CARIMBO_DE_DATA_HORA": iso_now(),
            "EMPRESA_ID": company.get("EMPRESA_ID", ""),
            "CICLO_ID": cycle_id,
            "NOME_DA_EMPRESA": company.get("NOME", ""),
            "GRUPO_ID": selected.get("GRUPO_ID", ""),
            "GRUPO_ANALISE": selected.get("GRUPO_ANALISE", ""),
            # Compatibilidade com relatórios antigos que agrupavam pela coluna SETOR.
            "SETOR": selected.get("GRUPO_ANALISE", ""),
            "CARGO_ATUAL": current_job.strip(),
            "CIENCIA_AVISO": "SIM",
            "AVISO_VERSAO": cycle.get("AVISO_VERSAO", ""),
            "CIENCIA_AVISO_EM": st.session_state[accepted_key],
        }
        response.update({QUESTIONARIO[number]: answer for number, answer in answers.items()})
        append_response(response)
        st.session_state[submitted_key] = True
        st.rerun()


# =============================================================================
# INTERFACE: CLIENTE
# =============================================================================

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
    if not st.session_state.get(authenticated_key):
        st.subheader(str(company.get("NOME", "Empresa")))
        pin = st.text_input("PIN de acesso", type="password", max_chars=6)
        if st.button("Entrar", type="primary", use_container_width=True):
            if verify_pin(token, pin, str(cycle.get("PIN_HASH", ""))):
                st.session_state[authenticated_key] = True
                st.rerun()
            st.error("PIN inválido.")
        st.caption("O PIN deve ser enviado separadamente do link.")
        st.stop()

    responses_all = load_responses()
    responses = filter_cycle_responses(responses_all, company, cycle)
    response_count = len(responses)
    status = safe_status(cycle.get("STATUS"))
    contracted, unit_price, contract_value, over_limit = contracted_value(cycle, response_count)
    valid_until = parse_date(cycle.get("VALIDO_ATE"))
    min_group = cycle_min_group(cycle)

    st.subheader(str(company.get("NOME", "Empresa")))
    cols = st.columns(4)
    cols[0].metric("Respostas recebidas", response_count)
    cols[1].metric("Funcionários contratados", contracted or "—")
    cols[2].metric("Status", status.replace("_", " ").title())
    cols[3].metric("Acesso válido até", valid_until.strftime("%d/%m/%Y") if valid_until else "Sem data")

    if unit_price > 0:
        st.caption(f"Valor contratado: {brl(contract_value)} ({contracted} funcionário(s) × {brl(unit_price)}; mínimo considerado quando configurado).")

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
        st.info("A coleta está aberta. Compartilhe somente o link de participação abaixo com os trabalhadores.")
        structures = cycle_structure_rows(
            read_sheet(SHEET_ESTRUTURA_CICLOS),
            str(cycle.get("CICLO_ID", "")),
        )
        if participant_form_ready(cycle, structures):
            participant_link = build_participant_link(str(cycle.get("PARTICIPANT_TOKEN", "")))
            st.code(participant_link, language=None)
            st.link_button("Testar formulário anônimo", participant_link, use_container_width=True)
            st.caption("O aviso aos participantes aparece antes das perguntas e precisa ser confirmado para prosseguir.")
        else:
            st.error("O formulário anônimo ainda não foi preparado pelo administrador para este ciclo.")

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
                {"STATUS": "AGUARDANDO_APROVACAO", "ENCERRADO_EM": iso_now()},
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

        st.success("Relatórios liberados para geração definitiva.")
        st.write(
            "A compra inclui a visão geral da empresa e os relatórios dos grupos de análise que atingirem o mínimo de confidencialidade. "
            "Depois da geração, novas respostas não alteram esta edição."
        )
        confirmation = st.checkbox("Confirmo a geração da edição definitiva deste ciclo.")
        if st.button("Gerar pacote definitivo", type="primary", disabled=not confirmation, use_container_width=True):
            update_row(SHEET_CICLOS, CICLOS_HEADERS, cycle, {"STATUS": "GERANDO"})
            try:
                with st.spinner("Gerando, armazenando e registrando os relatórios..."):
                    content, file_id, filename, suppressed = generate_and_store_reports(company, cycle, responses)
                    update_row(
                        SHEET_CICLOS,
                        CICLOS_HEADERS,
                        cycle,
                        {
                            "STATUS": "GERADO",
                            "GERADO_EM": iso_now(),
                            "DRIVE_FILE_ID": file_id,
                            "DRIVE_FILE_NAME": filename,
                            "VERSAO": str(get_app_setting("report_version", "2.0")),
                        },
                    )
                    st.session_state[f"generated_zip_{cycle.get('CICLO_ID')}"] = content
                    if suppressed:
                        st.warning(
                            f"{len(suppressed)} grupo(s) de análise foram incluídos somente na visão geral por proteção de confidencialidade."
                        )
                    st.success("Pacote definitivo gerado. Ele poderá ser baixado novamente durante a validade do acesso.")
                    st.rerun()
            except Exception as exc:
                update_row(SHEET_CICLOS, CICLOS_HEADERS, cycle, {"STATUS": "LIBERADO"})
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

    st.divider()
    st.caption(
        "Os resultados são coletivos e descritivos. Relatórios individuais não são disponibilizados à empresa nesta versão."
    )


# =============================================================================
# INTERFACE: ADMINISTRADOR
# =============================================================================

def admin_login() -> bool:
    expected = str(get_app_setting("admin_password", ""))
    if not expected:
        st.error("Configure app.admin_password nos Secrets.")
        return False
    if st.session_state.get("admin_authenticated"):
        return True
    password = st.text_input("Senha administrativa", type="password")
    if st.button("Entrar no administrativo", type="primary"):
        if secure_secrets.compare_digest(password, expected):
            st.session_state["admin_authenticated"] = True
            st.rerun()
        st.error("Senha inválida.")
    return False


def render_admin() -> None:
    st.title("🛠️ Painel administrativo")
    if not admin_login():
        st.stop()

    ensure_structure()
    companies = read_sheet(SHEET_EMPRESAS)
    cycles = read_sheet(SHEET_CICLOS)
    structures_all = read_sheet(SHEET_ESTRUTURA)
    cycle_structures_all = read_sheet(SHEET_ESTRUTURA_CICLOS)
    responses_all = load_responses()

    tabs = st.tabs(["Visão geral", "Nova empresa", "Estrutura", "Novo ciclo", "Gerenciar ciclo"])

    with tabs[0]:
        st.subheader("Ciclos")
        if cycles.empty:
            st.info("Nenhum ciclo cadastrado.")
        else:
            rows = []
            for _, cycle in cycles.iterrows():
                company = find_company(companies, str(cycle.get("EMPRESA_ID", "")))
                company_name = str(company.get("NOME", "Empresa não encontrada")) if company is not None else "Empresa não encontrada"
                raw_responses = (
                    filter_cycle_responses(responses_all, company, cycle, require_notice=False)
                    if company is not None
                    else pd.DataFrame()
                )
                responses = filter_notice_responses(raw_responses, cycle)
                contracted, unit_price, value, over = contracted_value(cycle, len(responses))
                rows.append(
                    {
                        "Empresa": company_name,
                        "Ciclo": cycle.get("CICLO_ID", ""),
                        "Ano": cycle.get("ANO", ""),
                        "Status": safe_status(cycle.get("STATUS")),
                        "Respostas": len(responses),
                        "Ignoradas sem ciência": max(0, len(raw_responses) - len(responses)),
                        "Contratados": contracted,
                        "Excedente": max(0, len(responses) - contracted) if contracted else 0,
                        "Valor contratado": brl(value),
                        "Pagamento": "OK" if is_yes(cycle.get("PAGAMENTO_OK")) else "Pendente",
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
            structure_text = st.text_area(
                "Áreas e grupos de análise",
                placeholder="Vendas | Administrativo\nRecursos Humanos | Administrativo\nProdução | Operacional",
                help=(
                    "Use uma linha por área no formato Área | Grupo. "
                    "Se houver apenas um nível, informe somente o nome, por exemplo: Administrativo."
                ),
            )
            submitted = st.form_submit_button("Cadastrar", type="primary")
        if submitted:
            mappings, structure_errors = parse_structure_lines(structure_text)
            if not name.strip() or structure_errors:
                if not name.strip():
                    st.error("Informe o nome da empresa.")
                for error in structure_errors:
                    st.error(error)
            else:
                company_id = make_company_id(name)
                append_row(
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
                append_rows(
                    SHEET_ESTRUTURA,
                    ESTRUTURA_HEADERS,
                    make_structure_records(company_id, mappings),
                )
                st.success(f"Empresa cadastrada: {company_id}")
                st.rerun()

    with tabs[2]:
        st.subheader("Áreas e grupos de análise")
        st.write(
            "A pessoa escolhe a área em que trabalha; o relatório usa o grupo de análise definido aqui. "
            "Assim, Vendas e Recursos Humanos podem pertencer ao mesmo grupo Administrativo."
        )
        if companies.empty:
            st.warning("Cadastre uma empresa primeiro.")
        else:
            structure_company_options = {
                f"{row.get('NOME', '')} — {row.get('EMPRESA_ID', '')}": str(row.get("EMPRESA_ID", ""))
                for _, row in companies.iterrows()
            }
            structure_company_label = st.selectbox(
                "Empresa",
                list(structure_company_options.keys()),
                key="structure_company",
            )
            structure_company_id = structure_company_options[structure_company_label]
            if structures_all.empty or "EMPRESA_ID" not in structures_all.columns:
                company_structures = structures_all.iloc[0:0].copy()
            else:
                company_structures = structures_all[
                    structures_all["EMPRESA_ID"].astype(str).str.strip() == structure_company_id
                ].copy()

            if company_structures.empty:
                st.info("Nenhuma área cadastrada para esta empresa.")
            else:
                structure_view = pd.DataFrame(
                    {
                        "Área de trabalho": company_structures["AREA_TRABALHO"],
                        "Grupo de análise": company_structures["GRUPO_ANALISE"],
                        "Status": company_structures["ATIVO"].map(lambda value: "Ativo" if is_yes(value) else "Inativo"),
                    }
                )
                st.dataframe(structure_view, use_container_width=True, hide_index=True)

            with st.form("add_company_structures"):
                new_structure_text = st.text_area(
                    "Adicionar áreas",
                    placeholder="Vendas | Administrativo\nRecursos Humanos | Administrativo",
                    help="Uma linha por área. Sem o caractere |, a área e o grupo recebem o mesmo nome.",
                )
                add_structures = st.form_submit_button("Adicionar")
            if add_structures:
                mappings, structure_errors = parse_structure_lines(new_structure_text)
                active_existing = active_company_structures(structures_all, structure_company_id)
                active_area_groups = {
                    normalize_text(row.get("AREA_TRABALHO", "")): normalize_text(row.get("GRUPO_ANALISE", ""))
                    for _, row in active_existing.iterrows()
                }
                existing_group_names = {
                    str(row.get("GRUPO_ID", "")).strip(): str(row.get("GRUPO_ANALISE", "")).strip()
                    for _, row in company_structures.iterrows()
                    if str(row.get("GRUPO_ID", "")).strip()
                }
                new_mappings: list[tuple[str, str]] = []
                for area, group in mappings:
                    area_key = normalize_text(area)
                    group_key = normalize_text(group)
                    if area_key in active_area_groups:
                        if active_area_groups[area_key] != group_key:
                            structure_errors.append(
                                f"A área '{area}' já está ativa em outro grupo. Desative-a antes de criar um novo mapeamento."
                            )
                        continue
                    group_id = make_group_id(structure_company_id, group)
                    canonical_group = existing_group_names.get(group_id, group)
                    new_mappings.append((area, canonical_group))
                if structure_errors:
                    for error in structure_errors:
                        st.error(error)
                elif not new_mappings:
                    st.info("Nenhuma área nova para adicionar.")
                else:
                    start_order = 1
                    if not company_structures.empty and "ORDEM" in company_structures.columns:
                        start_order = max(company_structures["ORDEM"].map(as_int).max(), 0) + 1
                    append_rows(
                        SHEET_ESTRUTURA,
                        ESTRUTURA_HEADERS,
                        make_structure_records(
                            structure_company_id,
                            new_mappings,
                            start_order=int(start_order),
                        ),
                    )
                    st.success("Áreas adicionadas.")
                    st.rerun()

            if not company_structures.empty:
                structure_actions = {
                    f"{row.get('AREA_TRABALHO', '')} → {row.get('GRUPO_ANALISE', '')} | {row.get('ESTRUTURA_ID', '')}": index
                    for index, (_, row) in enumerate(company_structures.iterrows())
                }
                action_label = st.selectbox("Alterar status", list(structure_actions.keys()))
                action_row = company_structures.iloc[structure_actions[action_label]]
                currently_active = is_yes(action_row.get("ATIVO", ""))
                action_text = "Desativar para ciclos futuros" if currently_active else "Reativar para ciclos futuros"
                if st.button(action_text):
                    if not currently_active:
                        active_existing = active_company_structures(structures_all, structure_company_id)
                        conflict = active_existing[
                            active_existing["AREA_TRABALHO"].map(normalize_text)
                            == normalize_text(action_row.get("AREA_TRABALHO", ""))
                        ]
                        if not conflict.empty:
                            st.error("Já existe um mapeamento ativo para esta área.")
                            st.stop()
                    update_row(
                        SHEET_ESTRUTURA,
                        ESTRUTURA_HEADERS,
                        action_row,
                        {"ATIVO": "NAO" if currently_active else "SIM"},
                    )
                    st.rerun()
            st.caption("Alterações no cadastro valem apenas para ciclos criados depois delas; ciclos existentes usam uma cópia congelada.")

    with tabs[3]:
        st.subheader("Criar ciclo comercial")
        if companies.empty:
            st.warning("Cadastre uma empresa primeiro.")
        else:
            company_options = {
                f"{row.get('NOME', '')} — {row.get('EMPRESA_ID', '')}": row.get("EMPRESA_ID", "")
                for _, row in companies.iterrows()
                if is_yes(row.get("ATIVO", "SIM"))
            }
            if not company_options:
                st.warning("Não há empresa ativa para criar um ciclo.")
                company_options = {"Nenhuma empresa ativa": ""}
            selected_label = st.selectbox(
                "Empresa",
                list(company_options.keys()),
                key="new_cycle_company",
            )
            company_id = str(company_options[selected_label])
            selected_company = find_company(companies, company_id)
            selected_structures = active_company_structures(structures_all, company_id)
            with st.form("new_cycle"):
                if selected_structures.empty:
                    st.warning("Esta empresa ainda não possui áreas ativas. Cadastre-as na aba Estrutura.")
                else:
                    st.dataframe(
                        selected_structures[["AREA_TRABALHO", "GRUPO_ANALISE"]].rename(
                            columns={"AREA_TRABALHO": "Área", "GRUPO_ANALISE": "Grupo de análise"}
                        ),
                        use_container_width=True,
                        hide_index=True,
                    )
                year = st.number_input("Ano/ciclo", min_value=2025, max_value=2100, value=now_sp().year, step=1)
                contracted = st.number_input("Funcionários contratados", min_value=1, value=10, step=1)
                unit_price = st.number_input("Preço por funcionário (R$)", min_value=0.0, value=0.0, step=1.0)
                minimum = st.number_input("Valor mínimo da compra (R$)", min_value=0.0, value=0.0, step=10.0)
                validity = st.number_input("Validade do acesso (dias)", min_value=1, value=90, step=1)
                min_group = st.number_input(
                    "Mínimo de respostas por grupo",
                    min_value=2,
                    value=max(2, as_int(get_app_setting("min_group_size", 5), 5)),
                    step=1,
                )
                st.markdown("#### Aviso aos participantes")
                st.caption(
                    "Estes dados ficam congelados no ciclo e são exibidos antes do questionário. "
                    f"Versão do texto: {PARTICIPANT_NOTICE_VERSION}."
                )
                notice_controller = st.text_input(
                    "Controlador dos dados",
                    value=str(selected_company.get("NOME", "")) if selected_company is not None else "",
                    key=f"notice_controller_{company_id}",
                )
                notice_operator = st.text_input(
                    "Operador/prestador do serviço",
                    value=str(get_app_setting("operator_name", "")),
                    key=f"notice_operator_{company_id}",
                )
                notice_contact = st.text_input(
                    "Contato para dúvidas e direitos dos titulares",
                    value=str(get_app_setting("privacy_contact", "")),
                    key=f"notice_contact_{company_id}",
                )
                notice_retention = st.text_area(
                    "Prazo e critério de retenção",
                    value=str(get_app_setting("retention_policy", "")),
                    key=f"notice_retention_{company_id}",
                )
                create = st.form_submit_button("Criar ciclo e credenciais", type="primary")
            if create:
                selected_structures = active_company_structures(structures_all, company_id)
                missing_notice = [
                    label
                    for label, value in (
                        ("controlador", notice_controller),
                        ("operador/prestador", notice_operator),
                        ("contato de privacidade", notice_contact),
                        ("retenção", notice_retention),
                    )
                    if not str(value).strip()
                ]
                if selected_structures.empty:
                    st.error("Cadastre pelo menos uma área ativa antes de criar o ciclo.")
                elif missing_notice:
                    st.error("Complete o aviso aos participantes: " + ", ".join(missing_notice) + ".")
                else:
                    cycle_id = make_cycle_id(company_id, int(year))
                    token, pin = make_access_credentials()
                    participant_token = make_participant_token()
                    start = now_sp()
                    valid_until = (start + timedelta(days=int(validity))).date().isoformat()
                    # A cópia por ciclo impede que alterações futuras mudem as opções desta coleta.
                    append_rows(
                        SHEET_ESTRUTURA_CICLOS,
                        ESTRUTURA_CICLO_HEADERS,
                        make_cycle_structure_records(cycle_id, company_id, selected_structures),
                    )
                    append_row(
                        SHEET_CICLOS,
                        CICLOS_HEADERS,
                        {
                            "CICLO_ID": cycle_id,
                            "EMPRESA_ID": company_id,
                            "ANO": int(year),
                            "TOKEN": token,
                            "PARTICIPANT_TOKEN": participant_token,
                            "PIN_HASH": pin_hash(token, pin),
                            "FUNCIONARIOS_CONTRATADOS": int(contracted),
                            "PRECO_POR_FUNCIONARIO": float(unit_price),
                            "VALOR_MINIMO": float(minimum),
                            "VALIDO_ATE": valid_until,
                            "STATUS": "COLETA",
                            "INICIO_EM": start.replace(microsecond=0).isoformat(),
                            "VERSAO": str(get_app_setting("report_version", "2.0")),
                            "PAGAMENTO_OK": "NAO",
                            "MIN_GRUPO": int(min_group),
                            "AVISO_VERSAO": PARTICIPANT_NOTICE_VERSION,
                            "AVISO_CONTROLADOR": notice_controller.strip(),
                            "AVISO_OPERADOR": notice_operator.strip(),
                            "AVISO_CONTATO": notice_contact.strip(),
                            "AVISO_RETENCAO": notice_retention.strip(),
                        },
                    )
                    st.success("Ciclo criado. Guarde o PIN; apenas o hash foi salvo.")
                    st.markdown("**Link do painel da empresa**")
                    st.code(build_client_link(token), language=None)
                    st.markdown("**PIN do painel**")
                    st.code(pin, language=None)
                    st.markdown("**Link anônimo para os participantes**")
                    st.code(build_participant_link(participant_token), language=None)
                    st.warning("Envie o link do painel e o PIN por canais separados. Aos trabalhadores, envie somente o link anônimo.")

    with tabs[4]:
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
                raw_responses = (
                    filter_cycle_responses(responses_all, company, cycle, require_notice=False)
                    if company is not None
                    else pd.DataFrame()
                )
                responses = filter_notice_responses(raw_responses, cycle)
                ignored_responses = max(0, len(raw_responses) - len(responses))
                cycle_structures = cycle_structure_rows(
                    cycle_structures_all,
                    str(cycle.get("CICLO_ID", "")),
                )
                contracted, unit_price, value, over = contracted_value(cycle, len(responses))
                st.write(
                    {
                        "empresa": company.get("NOME", "") if company is not None else "",
                        "respostas_válidas": len(responses),
                        "ignoradas_sem_ciência": ignored_responses,
                        "contratados": contracted,
                        "excedente": max(0, len(responses) - contracted) if contracted else 0,
                        "valor_contratado": brl(value),
                        "status": safe_status(cycle.get("STATUS")),
                        "pagamento_ok": is_yes(cycle.get("PAGAMENTO_OK")),
                        "valido_ate": cycle.get("VALIDO_ATE", ""),
                    }
                )

                c1, c2, c3, c4 = st.columns(4)
                if c1.button("Confirmar pagamento", use_container_width=True):
                    update_row(SHEET_CICLOS, CICLOS_HEADERS, cycle, {"PAGAMENTO_OK": "SIM"})
                    st.rerun()
                if c2.button("Liberar geração", use_container_width=True):
                    if len(responses) < cycle_min_group(cycle):
                        st.error("Quantidade abaixo do mínimo de confidencialidade.")
                    elif over:
                        st.error("Ajuste o número contratado antes de liberar.")
                    elif not is_yes(cycle.get("PAGAMENTO_OK")):
                        st.error("Confirme o pagamento antes de liberar.")
                    else:
                        changes = {"STATUS": "LIBERADO"}
                        if not str(cycle.get("ENCERRADO_EM", "")).strip():
                            changes["ENCERRADO_EM"] = iso_now()
                        update_row(SHEET_CICLOS, CICLOS_HEADERS, cycle, changes)
                        st.rerun()
                if c3.button("Reabrir coleta", use_container_width=True):
                    if safe_status(cycle.get("STATUS")) == "GERADO":
                        st.error("Uma edição já gerada é imutável. Crie outro ciclo ou use a liberação extraordinária abaixo.")
                    else:
                        update_row(
                            SHEET_CICLOS,
                            CICLOS_HEADERS,
                            cycle,
                            {"STATUS": "COLETA", "ENCERRADO_EM": ""},
                        )
                        st.rerun()
                if c4.button("Estender +90 dias", use_container_width=True):
                    current = parse_date(cycle.get("VALIDO_ATE")) or now_sp().date()
                    base = max(current, now_sp().date())
                    update_row(
                        SHEET_CICLOS,
                        CICLOS_HEADERS,
                        cycle,
                        {"VALIDO_ATE": (base + timedelta(days=90)).isoformat()},
                    )
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
                        },
                    )
                    st.rerun()

                if safe_status(cycle.get("STATUS")) == "GERANDO":
                    if st.button("Recuperar geração travada (voltar para LIBERADO)"):
                        update_row(SHEET_CICLOS, CICLOS_HEADERS, cycle, {"STATUS": "LIBERADO"})
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
                st.markdown("**Painel da empresa**")
                st.code(build_client_link(str(cycle.get("TOKEN", ""))), language=None)
                form_ready = participant_form_ready(cycle, cycle_structures)
                if form_ready:
                    st.markdown("**Formulário anônimo para os participantes**")
                    st.code(build_participant_link(str(cycle.get("PARTICIPANT_TOKEN", ""))), language=None)
                    st.caption(
                        f"Aviso {cycle.get('AVISO_VERSAO', '')}; {len(cycle_structures)} área(s) congelada(s); "
                        f"mínimo de {cycle_min_group(cycle)} respostas por grupo."
                    )
                    if st.button("Revogar e gerar novo link anônimo"):
                        update_row(
                            SHEET_CICLOS,
                            CICLOS_HEADERS,
                            cycle,
                            {"PARTICIPANT_TOKEN": make_participant_token()},
                        )
                        st.success("O link anônimo anterior foi revogado.")
                        st.rerun()
                elif safe_status(cycle.get("STATUS")) == "COLETA" and company is not None:
                    st.warning("Este ciclo é anterior ao formulário anônimo e ainda precisa ser preparado.")
                    active_for_migration = active_company_structures(
                        structures_all,
                        str(company.get("EMPRESA_ID", "")),
                    )
                    migration_structures = (
                        cycle_structures if not cycle_structures.empty else active_for_migration
                    )
                    with st.expander("Preparar formulário anônimo"):
                        if not raw_responses.empty:
                            st.error(
                                "Este ciclo já tem respostas. Para não misturar respostas sem ciência registrada com o novo fluxo, "
                                "crie um novo ciclo."
                            )
                        if migration_structures.empty:
                            st.error("Cadastre áreas ativas na aba Estrutura antes de preparar o formulário.")
                        with st.form(f"prepare_anonymous_{cycle.get('CICLO_ID', '')}"):
                            migration_operator = st.text_input(
                                "Operador/prestador do serviço",
                                value=str(get_app_setting("operator_name", "")),
                            )
                            migration_contact = st.text_input(
                                "Contato para dúvidas e direitos dos titulares",
                                value=str(get_app_setting("privacy_contact", "")),
                            )
                            migration_retention = st.text_area(
                                "Prazo e critério de retenção",
                                value=str(get_app_setting("retention_policy", "")),
                            )
                            migration_min_group = st.number_input(
                                "Mínimo de respostas por grupo",
                                min_value=2,
                                value=cycle_min_group(cycle),
                                step=1,
                            )
                            prepare_form = st.form_submit_button(
                                "Congelar estrutura e ativar",
                                disabled=not raw_responses.empty or migration_structures.empty,
                            )
                        if prepare_form:
                            if not all(
                                str(value).strip()
                                for value in (migration_operator, migration_contact, migration_retention)
                            ):
                                st.error("Preencha operador, contato e retenção.")
                            else:
                                if cycle_structures.empty:
                                    append_rows(
                                        SHEET_ESTRUTURA_CICLOS,
                                        ESTRUTURA_CICLO_HEADERS,
                                        make_cycle_structure_records(
                                            str(cycle.get("CICLO_ID", "")),
                                            str(company.get("EMPRESA_ID", "")),
                                            migration_structures,
                                        ),
                                    )
                                update_row(
                                    SHEET_CICLOS,
                                    CICLOS_HEADERS,
                                    cycle,
                                    {
                                        "MIN_GRUPO": int(migration_min_group),
                                        "PARTICIPANT_TOKEN": make_participant_token(),
                                        "AVISO_VERSAO": PARTICIPANT_NOTICE_VERSION,
                                        "AVISO_CONTROLADOR": str(company.get("NOME", "")).strip(),
                                        "AVISO_OPERADOR": migration_operator.strip(),
                                        "AVISO_CONTATO": migration_contact.strip(),
                                        "AVISO_RETENCAO": migration_retention.strip(),
                                    },
                                )
                                st.success("Formulário anônimo preparado.")
                                st.rerun()
                st.caption("O PIN original não pode ser recuperado. Para trocar o PIN, gere um novo abaixo.")
                if st.button("Gerar novo PIN"):
                    new_pin = f"{secure_secrets.randbelow(1_000_000):06d}"
                    update_row(
                        SHEET_CICLOS,
                        CICLOS_HEADERS,
                        cycle,
                        {"PIN_HASH": pin_hash(str(cycle.get("TOKEN", "")), new_pin)},
                    )
                    st.success("Novo PIN gerado. Copie agora:")
                    st.code(new_pin, language=None)

                with st.expander("Ações excepcionais"):
                    st.warning("Use somente após novo pagamento ou correção administrativa formal.")
                    if st.button("Liberar nova geração e substituir a edição anterior"):
                        update_row(
                            SHEET_CICLOS,
                            CICLOS_HEADERS,
                            cycle,
                            {
                                "STATUS": "LIBERADO",
                                "GERADO_EM": "",
                                "DRIVE_FILE_ID": "",
                                "DRIVE_FILE_NAME": "",
                            },
                        )
                        st.rerun()
                    if st.button("Cancelar ciclo"):
                        update_row(SHEET_CICLOS, CICLOS_HEADERS, cycle, {"STATUS": "CANCELADO"})
                        st.rerun()


# =============================================================================
# EXECUÇÃO
# =============================================================================

def main() -> None:
    try:
        participant_mode = bool(get_query_value("participar").strip())
        admin_mode = get_query_value("admin") == "1"
        if participant_mode:
            render_participant()
        elif admin_mode:
            render_admin()
        else:
            render_client()
    except Exception as exc:
        st.error(f"Erro de configuração ou conexão: {exc}")
        st.caption("Consulte o SETUP.md e os Secrets do Streamlit antes de publicar.")


if __name__ == "__main__":
    main()

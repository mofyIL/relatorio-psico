from __future__ import annotations

"""
Camada de acesso ao Supabase/Postgres.

O app Streamlit roda do lado do servidor e usa a service role configurada em
`.streamlit/secrets.toml`. Essa chave nunca deve ser enviada ao navegador nem
armazenada no repositório.
"""

import hashlib
import math
import re
import secrets
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable, Sequence

from database import BackendSettings, require_supabase_config


DEFAULT_PARTICIPANT_NOTICE_VERSION = "2026-07-11-v2"


def _response_data(response: Any) -> Any:
    return getattr(response, "data", None)


def _rows(response: Any) -> list[dict[str, Any]]:
    data = _response_data(response)
    return data if isinstance(data, list) else []


def _first(response: Any) -> dict[str, Any] | None:
    rows = _rows(response)
    return rows[0] if rows else None


def _slug(value: str, *, max_length: int = 32) -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").upper()
    slug = re.sub(r"[^A-Z0-9]+", "_", ascii_text).strip("_")
    return (slug or "ITEM")[:max_length]


def _clean_dict(data: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in data.items() if value is not None}


def _boolish(value: Any, default: bool = False) -> bool:
    if value is None or str(value).strip() == "":
        return default
    return str(value).strip().upper() in {"SIM", "S", "TRUE", "1", "YES", "OK"}


def _question_code(value: Any) -> str:
    text = str(value or "").strip().upper()
    if isinstance(value, int) or text.isdigit():
        return f"Q{int(text):02d}"
    match = re.match(r"^Q(\d{1,2})$", text)
    if match:
        return f"Q{int(match.group(1)):02d}"
    return text


def _question_number(code: str) -> int | None:
    match = re.match(r"^Q(\d{1,2})$", str(code or "").strip().upper())
    return int(match.group(1)) if match else None


def _storage_path_part(value: Any) -> str:
    text = str(value or "").strip()
    text = re.sub(r"[^A-Za-z0-9._=-]+", "_", text)
    return text.strip("._") or secrets.token_hex(4)


def _canonical_key(value: Any, *, fallback: str = "item") -> str:
    normalized = unicodedata.normalize("NFKD", str(value or ""))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii").lower()
    key = re.sub(r"[^a-z0-9]+", "_", ascii_text).strip("_")
    return key or fallback


def _schema_feature_missing(exc: Exception) -> bool:
    """Reconhece erro de schema-cache/coluna ausente durante rollout da migration."""
    message = f"{exc!s} {exc!r}".lower()
    return any(
        marker in message
        for marker in (
            "42p01",
            "42703",
            "pgrst204",
            "could not find the table",
            "could not find the column",
            "does not exist",
            "schema cache",
        )
    )


def _split_legacy_area_group(value: Any) -> tuple[str, str]:
    text = str(value or "").strip()
    if "|" not in text:
        return text, text
    area_name, group_name = (part.strip() for part in text.split("|", 1))
    return area_name, group_name or area_name


def _normalize_area_mappings(
    mappings: Iterable[dict[str, Any] | Sequence[Any]],
) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: dict[str, str] = {}
    for index, mapping in enumerate(mappings):
        if isinstance(mapping, dict):
            area_name = str(
                mapping.get("area_name")
                or mapping.get("sector_name")
                or mapping.get("area")
                or ""
            ).strip()
            group_name = str(
                mapping.get("analysis_group_name")
                or mapping.get("group_name")
                or mapping.get("group")
                or area_name
            ).strip()
            active = _boolish(mapping.get("active"), True)
            sort_order = int(mapping.get("sort_order") or index + 1)
        else:
            values = list(mapping)
            area_name = str(values[0] if values else "").strip()
            group_name = str(values[1] if len(values) > 1 else area_name).strip()
            active = True
            sort_order = index + 1
        if not area_name or not group_name:
            raise ValueError("Cada mapeamento precisa informar área e grupo de análise.")
        area_key = _canonical_key(area_name, fallback="area")
        group_key = _canonical_key(group_name, fallback="grupo")
        previous = seen.get(area_key)
        if previous and previous != group_key:
            raise ValueError(
                f"A área '{area_name}' aparece associada a mais de um grupo de análise."
            )
        if previous:
            continue
        seen[area_key] = group_key
        normalized.append(
            {
                "area_name": area_name,
                "area_key": area_key,
                "analysis_group_key": group_key,
                "analysis_group_name": group_name,
                "active": active,
                "sort_order": sort_order,
            }
        )
    return normalized


def _valid_iso_datetime(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("O momento do aceite do aviso é obrigatório.")
    try:
        datetime.fromisoformat(text.replace("Z", "+00:00"))
    except ValueError as exc:
        raise ValueError("O momento do aceite do aviso é inválido.") from exc
    return text


@dataclass
class SupabaseRepository:
    settings: BackendSettings

    def __post_init__(self) -> None:
        require_supabase_config(self.settings)
        try:
            from supabase import create_client  # type: ignore
        except Exception as exc:  # pragma: no cover - depende de instalação opcional
            raise RuntimeError(
                "Instale a dependência supabase com `pip install supabase` para ativar este backend."
            ) from exc
        self.client = create_client(
            self.settings.supabase_url,
            self.settings.supabase_service_role_key,
        )

    # ------------------------------------------------------------------
    # Empresas
    # ------------------------------------------------------------------
    def list_companies(self) -> list[dict[str, Any]]:
        return _rows(
            self.client.table("companies")
            .select("*")
            .order("created_at", desc=True)
            .execute()
        )

    def get_company(self, company_id: str) -> dict[str, Any] | None:
        return _first(
            self.client.table("companies")
            .select("*")
            .eq("id", company_id)
            .limit(1)
            .execute()
        )

    def create_company(self, data: dict[str, Any]) -> dict[str, Any]:
        name = str(
            data.get("legal_name")
            or data.get("NOME")
            or data.get("name")
            or data.get("trade_name")
            or ""
        ).strip()
        if not name:
            raise ValueError("Informe o nome da empresa.")
        public_code = str(data.get("public_code") or data.get("EMPRESA_ID") or "").strip()
        if not public_code:
            public_code = f"EMP_{_slug(name, max_length=20)}_{secrets.token_hex(2).upper()}"
        payload = _clean_dict(
            {
                "public_code": public_code,
                "legal_name": name,
                "trade_name": data.get("trade_name"),
                "cnpj": data.get("cnpj") or data.get("CNPJ"),
                "responsible_name": data.get("responsible_name") or data.get("RESPONSAVEL"),
                "responsible_email": data.get("responsible_email") or data.get("EMAIL"),
                "status": data.get("status") or "active",
                "lgpd_controller_name": data.get("lgpd_controller_name"),
                "lgpd_contact_email": data.get("lgpd_contact_email"),
                "notes": data.get("notes") or data.get("OBSERVACOES"),
            }
        )
        return _first(self.client.table("companies").insert(payload).execute()) or {}

    def list_company_areas(
        self,
        company_id: str,
        *,
        active_only: bool = False,
    ) -> list[dict[str, Any]]:
        try:
            query = (
                self.client.table("company_areas")
                .select("*")
                .eq("company_id", company_id)
                .order("sort_order")
                .order("area_name")
            )
            if active_only:
                query = query.eq("active", True)
            return _rows(query.execute())
        except Exception as exc:
            if _schema_feature_missing(exc):
                return []
            raise

    def set_company_areas(
        self,
        company_id: str,
        mappings: Iterable[dict[str, Any] | Sequence[Any]],
    ) -> list[dict[str, Any]]:
        """Substitui o catálogo ativo sem apagar linhas usadas por snapshots."""
        rows = _normalize_area_mappings(mappings)
        if not rows:
            raise ValueError("Informe pelo menos uma área e seu grupo de análise.")
        payload = [{"company_id": company_id, **row} for row in rows]
        try:
            existing = self.list_company_areas(company_id)
            saved = _rows(
                self.client.table("company_areas")
                .upsert(payload, on_conflict="company_id,area_key")
                .execute()
            )
            active_keys = {row["area_key"] for row in rows}
            stale_ids = [
                str(row.get("id"))
                for row in existing
                if row.get("id")
                and row.get("active", True)
                and str(row.get("area_key") or "") not in active_keys
            ]
            if stale_ids:
                (
                    self.client.table("company_areas")
                    .update({"active": False})
                    .in_("id", stale_ids)
                    .execute()
                )
            return saved or self.list_company_areas(company_id, active_only=True)
        except Exception as exc:
            if _schema_feature_missing(exc):
                # A UI ainda pode congelar os mesmos mappings diretamente em
                # campaign_sectors enquanto a migration não foi aplicada.
                return [{**row, "id": "", "persisted": False} for row in rows]
            raise

    def set_company_area_active(self, area_id: str, active: bool) -> dict[str, Any]:
        try:
            return _first(
                self.client.table("company_areas")
                .update({"active": bool(active)})
                .eq("id", area_id)
                .execute()
            ) or {}
        except Exception as exc:
            if _schema_feature_missing(exc):
                return {}
            raise

    # ------------------------------------------------------------------
    # Campanhas/ciclos
    # ------------------------------------------------------------------
    def list_campaigns(self, company_id: str | None = None) -> list[dict[str, Any]]:
        query = (
            self.client.table("campaigns")
            .select("*, companies(*), questionnaires(*), reports(*)")
            .order("created_at", desc=True)
        )
        if company_id:
            query = query.eq("company_id", company_id)
        return _rows(query.execute())

    def get_campaign(self, campaign_id: str) -> dict[str, Any] | None:
        return _first(
            self.client.table("campaigns")
            .select("*, companies(*), questionnaires(*), reports(*)")
            .eq("id", campaign_id)
            .limit(1)
            .execute()
        )

    def get_campaign_by_code(self, code: str) -> dict[str, Any] | None:
        return _first(
            self.client.table("campaigns")
            .select("*, companies(*), questionnaires(*), reports(*)")
            .eq("code", str(code).strip())
            .limit(1)
            .execute()
        )

    def get_campaign_by_response_code(self, code: str) -> dict[str, Any] | None:
        """Resolve somente o token de participação; usa code no schema legado."""
        normalized = str(code or "").strip()
        if not normalized:
            return None
        try:
            return _first(
                self.client.table("campaigns")
                .select("*, companies(*), questionnaires(*), reports(*)")
                .eq("response_code", normalized)
                .limit(1)
                .execute()
            )
        except Exception as exc:
            if _schema_feature_missing(exc):
                return self.get_campaign_by_code(normalized)
            raise

    def create_campaign(self, data: dict[str, Any]) -> dict[str, Any]:
        questionnaire_id = str(data.get("questionnaire_id") or "").strip()
        if not questionnaire_id:
            questionnaire = self.get_active_questionnaire()
            questionnaire_id = str(questionnaire.get("id", "")).strip()
        if not questionnaire_id:
            raise RuntimeError("Questionário ativo não encontrado no Supabase.")

        token = str(data.get("code") or data.get("TOKEN") or "").strip()
        if not token:
            token = secrets.token_urlsafe(32)
        response_code = str(
            data.get("response_code")
            or data.get("RESPONSE_TOKEN")
            or data.get("PARTICIPANT_TOKEN")
            or ""
        ).strip()
        if not response_code:
            response_code = secrets.token_urlsafe(32)
        notice_body = str(
            data.get("notice_body") or data.get("AVISO_TEXTO") or ""
        ).strip()
        notice_hash = str(
            data.get("notice_content_sha256") or data.get("AVISO_SHA256") or ""
        ).strip()
        if notice_body and not notice_hash:
            notice_hash = hashlib.sha256(notice_body.encode("utf-8")).hexdigest()
        title = str(data.get("title") or data.get("TITULO") or "").strip()
        cycle_year = data.get("cycle_year") or data.get("ANO")
        if not title:
            title = f"Ciclo {cycle_year or ''}".strip()
        payload = _clean_dict(
            {
                "company_id": data.get("company_id") or data.get("EMPRESA_ID"),
                "questionnaire_id": questionnaire_id,
                "code": token,
                "response_code": response_code,
                "title": title,
                "cycle_year": cycle_year,
                "status": data.get("status") or "collecting",
                "payment_status": data.get("payment_status") or "pending",
                "employees_contracted": data.get("employees_contracted")
                or data.get("FUNCIONARIOS_CONTRATADOS")
                or 0,
                "expected_respondents": data.get("expected_respondents"),
                "price_per_employee": data.get("price_per_employee")
                or data.get("PRECO_POR_FUNCIONARIO")
                or 0,
                "minimum_price": data.get("minimum_price") or data.get("VALOR_MINIMO") or 0,
                "min_group_size": data.get("min_group_size") or 7,
                "recommended_group_size": data.get("recommended_group_size") or 10,
                "access_token_hash": data.get("access_token_hash") or data.get("PIN_HASH"),
                "notice_version": data.get("notice_version") or data.get("AVISO_VERSAO"),
                "notice_controller": data.get("notice_controller") or data.get("AVISO_CONTROLADOR"),
                "notice_operator": data.get("notice_operator") or data.get("AVISO_OPERADOR"),
                "notice_contact": data.get("notice_contact") or data.get("AVISO_CONTATO"),
                "notice_retention": data.get("notice_retention") or data.get("AVISO_RETENCAO"),
                "notice_body": notice_body or None,
                "notice_content_sha256": notice_hash or None,
                "notice_frozen_at": data.get("notice_frozen_at"),
                "structure_frozen_at": data.get("structure_frozen_at"),
                "starts_at": data.get("starts_at") or data.get("INICIO_EM"),
                "closes_at": data.get("closes_at") or data.get("VALIDO_ATE"),
                "closed_at": data.get("closed_at") or data.get("ENCERRADO_EM"),
                "approved_at": data.get("approved_at"),
                "generated_at": data.get("generated_at") or data.get("GERADO_EM"),
                "notes": data.get("notes") or data.get("OBSERVACOES"),
            }
        )
        if not payload.get("company_id"):
            raise ValueError("Informe a empresa da campanha.")
        try:
            return _first(self.client.table("campaigns").insert(payload).execute()) or {}
        except Exception as exc:
            if not _schema_feature_missing(exc):
                raise
            legacy_payload = {
                key: value
                for key, value in payload.items()
                if key
                not in {
                    "response_code",
                    "notice_version",
                    "notice_controller",
                    "notice_operator",
                    "notice_contact",
                    "notice_retention",
                    "notice_body",
                    "notice_content_sha256",
                    "notice_frozen_at",
                    "structure_frozen_at",
                }
            }
            return _first(
                self.client.table("campaigns").insert(legacy_payload).execute()
            ) or {}

    def list_campaign_areas(self, campaign_id: str) -> list[dict[str, Any]]:
        """Lista opções congeladas e normaliza linhas do schema V2 inicial."""
        try:
            rows = _rows(
                self.client.table("campaign_sectors")
                .select("*")
                .eq("campaign_id", campaign_id)
                .order("sort_order")
                .order("sector_name")
                .execute()
            )
        except Exception as exc:
            if not _schema_feature_missing(exc):
                raise
            rows = _rows(
                self.client.table("campaign_sectors")
                .select("id,campaign_id,sector_name,expected_headcount,reportable,created_at")
                .eq("campaign_id", campaign_id)
                .order("sector_name")
                .execute()
            )

        normalized: list[dict[str, Any]] = []
        for index, source in enumerate(rows):
            row = dict(source)
            legacy_area, legacy_group = _split_legacy_area_group(row.get("sector_name"))
            area_name = str(row.get("area_name") or legacy_area).strip()
            group_name = str(
                row.get("analysis_group_name") or legacy_group or area_name
            ).strip()
            if not area_name or not group_name:
                continue
            row["area_name"] = area_name
            # Compatibilidade com a UI, que historicamente leu sector_name.
            row["sector_name"] = area_name
            row["area_key"] = str(
                row.get("area_key") or _canonical_key(area_name, fallback="area")
            )
            row["analysis_group_key"] = str(
                row.get("analysis_group_key")
                or _canonical_key(group_name, fallback="grupo")
            )
            row["analysis_group_name"] = group_name
            row["sort_order"] = int(row.get("sort_order") or index + 1)
            normalized.append(row)
        return normalized

    # Alias conservado para integrações que ainda usam o nome antigo.
    def list_campaign_sectors(self, campaign_id: str) -> list[dict[str, Any]]:
        return self.list_campaign_areas(campaign_id)

    def set_campaign_areas(
        self,
        campaign_id: str,
        mappings: Iterable[dict[str, Any] | Sequence[Any]],
    ) -> list[dict[str, Any]]:
        """Grava o snapshot Área→Grupo, com fallback no sector_name legado."""
        normalized = _normalize_area_mappings(mappings)
        if not normalized:
            raise ValueError("Informe pelo menos uma área para congelar a campanha.")
        full_rows = [
            {
                "campaign_id": campaign_id,
                "sector_name": row["area_name"],
                "area_name": row["area_name"],
                "area_key": row["area_key"],
                "analysis_group_key": row["analysis_group_key"],
                "analysis_group_name": row["analysis_group_name"],
                "sort_order": row["sort_order"],
                "reportable": True,
            }
            for row in normalized
        ]
        try:
            self.client.table("campaign_sectors").upsert(
                full_rows,
                on_conflict="campaign_id,sector_name",
            ).execute()
        except Exception as exc:
            if not _schema_feature_missing(exc):
                raise
            legacy_rows = [
                {
                    "campaign_id": campaign_id,
                    "sector_name": (
                        f"{row['area_name']} | {row['analysis_group_name']}"
                        if row["area_name"] != row["analysis_group_name"]
                        else row["area_name"]
                    ),
                    "reportable": True,
                }
                for row in normalized
            ]
            self.client.table("campaign_sectors").upsert(
                legacy_rows,
                on_conflict="campaign_id,sector_name",
            ).execute()
        return self.list_campaign_areas(campaign_id)

    def freeze_campaign_areas(
        self,
        campaign_id: str,
        mappings: Iterable[dict[str, Any] | Sequence[Any]] | None = None,
    ) -> list[dict[str, Any]]:
        campaign = self.get_campaign(campaign_id)
        if not campaign:
            raise ValueError("Campanha não encontrada.")
        selected_mappings = mappings
        if selected_mappings is None:
            selected_mappings = self.list_company_areas(
                str(campaign.get("company_id") or ""),
                active_only=True,
            )
        rows = self.set_campaign_areas(campaign_id, selected_mappings)
        try:
            (
                self.client.table("campaigns")
                .update({"structure_frozen_at": datetime.now().astimezone().isoformat()})
                .eq("id", campaign_id)
                .execute()
            )
        except Exception as exc:
            if not _schema_feature_missing(exc):
                raise
        return rows

    def snapshot_company_areas(self, campaign_id: str, company_id: str) -> list[dict[str, Any]]:
        areas = self.list_company_areas(company_id, active_only=True)
        return self.set_campaign_areas(campaign_id, areas)

    def update_campaign(self, campaign_id: str, data: dict[str, Any]) -> dict[str, Any]:
        if not data:
            return self.get_campaign(campaign_id) or {}
        return _first(
            self.client.table("campaigns")
            .update(data)
            .eq("id", campaign_id)
            .execute()
        ) or {}

    # ------------------------------------------------------------------
    # Questionario
    # ------------------------------------------------------------------
    def get_active_questionnaire(self) -> dict[str, Any]:
        questionnaire = _first(
            self.client.table("questionnaires")
            .select("*")
            .eq("status", "active")
            .order("updated_at", desc=True)
            .limit(1)
            .execute()
        )
        if not questionnaire:
            return {}
        questionnaire["domains"] = self.list_domains(str(questionnaire["id"]))
        questionnaire["questions"] = self.list_questions(str(questionnaire["id"]))
        return questionnaire

    def list_domains(self, questionnaire_id: str) -> list[dict[str, Any]]:
        return _rows(
            self.client.table("domains")
            .select("*")
            .eq("questionnaire_id", questionnaire_id)
            .order("sort_order")
            .execute()
        )

    def list_questions(
        self,
        questionnaire_id: str,
        *,
        include_open: bool = True,
    ) -> list[dict[str, Any]]:
        query = (
            self.client.table("questions")
            .select("*, domains(code, name)")
            .eq("questionnaire_id", questionnaire_id)
            .order("sort_order")
        )
        if not include_open:
            query = query.neq("question_type", "open_text")
        return _rows(query.execute())

    # ------------------------------------------------------------------
    # Respostas
    # ------------------------------------------------------------------
    def count_responses(self, campaign_id: str) -> int:
        campaign = self.get_campaign(campaign_id) or {}
        query = (
            self.client.table("responses")
            .select("id", count="exact")
            .eq("campaign_id", campaign_id)
            .eq("consent_accepted", True)
        )
        required_notice_version = str(campaign.get("notice_version") or "").strip()
        if required_notice_version:
            query = query.eq("notice_version", required_notice_version)
        result = query.execute()
        return int(getattr(result, "count", None) or 0)

    def create_response(
        self,
        campaign_id: str,
        respondent_metadata: dict[str, Any] | None,
        items: dict[Any, Any],
        open_answers: dict[Any, Any] | list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        metadata = dict(respondent_metadata or {})
        # Esta validação vem antes de qualquer acesso ao banco: ausência,
        # checkbox falso ou texto desconhecido nunca significam consentimento.
        if not _boolish(metadata.get("consent_accepted"), False):
            raise ValueError(
                "O aceite afirmativo do aviso é obrigatório para participar."
            )
        accepted_notice_version = str(
            metadata.get("notice_version") or metadata.get("AVISO_VERSAO") or ""
        ).strip()
        if not accepted_notice_version:
            raise ValueError("A versão aceita do aviso é obrigatória.")
        accepted_at = _valid_iso_datetime(
            metadata.get("notice_accepted_at")
            or metadata.get("CIENCIA_AVISO_EM")
        )

        campaign = self.get_campaign(campaign_id)
        if not campaign:
            raise ValueError("Campanha não encontrada.")
        required_notice_version = str(
            campaign.get("notice_version")
            or campaign.get("AVISO_VERSAO")
            or DEFAULT_PARTICIPANT_NOTICE_VERSION
        ).strip()
        if accepted_notice_version != required_notice_version:
            raise ValueError(
                "A versão aceita do aviso não corresponde à versão da campanha."
            )
        required_notice_hash = str(
            campaign.get("notice_content_sha256")
            or campaign.get("AVISO_SHA256")
            or ""
        ).strip()
        accepted_notice_hash = str(
            metadata.get("notice_content_sha256")
            or metadata.get("AVISO_SHA256")
            or required_notice_hash
        ).strip()
        if required_notice_hash and accepted_notice_hash != required_notice_hash:
            raise ValueError("O conteúdo aceito do aviso não corresponde à campanha.")

        campaign_areas = self.list_campaign_areas(campaign_id)
        selected_area_id = str(
            metadata.get("campaign_area_id")
            or metadata.get("campaign_sector_id")
            or metadata.get("ESTRUTURA_ID")
            or ""
        ).strip()
        selected_area = next(
            (
                row
                for row in campaign_areas
                if str(row.get("id") or "").strip() == selected_area_id
            ),
            None,
        )
        if campaign_areas and not selected_area:
            raise ValueError(
                "Selecione uma área válida da estrutura congelada da campanha."
            )

        if selected_area:
            group_name = str(selected_area.get("analysis_group_name") or "").strip()
            group_key = str(selected_area.get("analysis_group_key") or "").strip()
        else:
            # Compatibilidade limitada para campanhas realmente sem snapshot.
            group_name = str(
                metadata.get("analysis_group_name")
                or metadata.get("sector")
                or metadata.get("SETOR")
                or ""
            ).strip()
            group_key = str(
                metadata.get("analysis_group_key")
                or _canonical_key(group_name, fallback="grupo")
            ).strip()
        if not group_name or not group_key:
            raise ValueError("A área/grupo de análise da resposta não foi identificado.")

        questions = self.list_questions(str(campaign["questionnaire_id"]))
        by_code = {_question_code(q.get("code")): q for q in questions}
        by_id = {str(q.get("id")): q for q in questions}
        by_text = {str(q.get("text", "")).strip().lower(): q for q in questions}

        demographics = dict(metadata.get("demographics") or {})
        base_keys = {
            "sector",
            "campaign_area_id",
            "campaign_sector_id",
            "analysis_group_key",
            "analysis_group_name",
            "role_family",
            "current_job_title",
            "work_unit",
            "demographics",
            "consent_accepted",
            "notice_version",
            "notice_content_sha256",
            "notice_accepted_at",
            "dedupe_hash",
            "source",
        }
        for key, value in metadata.items():
            if key not in base_keys and value not in (None, ""):
                demographics[key] = value

        # Duplicados em demographics mantêm leitura durante o intervalo entre
        # deploy do código e aplicação da migration, sem confiar neles no input.
        demographics.update(
            {
                "analysis_group_key": group_key,
                "analysis_group_name": group_name,
                "notice_version": accepted_notice_version,
                "notice_accepted_at": accepted_at,
            }
        )
        if accepted_notice_hash:
            demographics["notice_content_sha256"] = accepted_notice_hash

        current_job_title = str(
            metadata.get("current_job_title")
            or metadata.get("role_family")
            or metadata.get("CARGO_ATUAL")
            or metadata.get("CARGO")
            or ""
        ).strip()

        response_payload = _clean_dict(
            {
                "campaign_id": campaign_id,
                # Compatibilidade: sector recebe o grupo canônico, não a área.
                "sector": group_name,
                "analysis_group_key": group_key,
                "analysis_group_name": group_name,
                "role_family": current_job_title,
                "current_job_title": current_job_title,
                "work_unit": metadata.get("work_unit") or metadata.get("UNIDADE"),
                "demographics": demographics,
                "consent_accepted": True,
                "notice_version": accepted_notice_version,
                "notice_content_sha256": accepted_notice_hash or None,
                "notice_accepted_at": accepted_at,
                "dedupe_hash": metadata.get("dedupe_hash"),
                "source": metadata.get("source") or "streamlit",
            }
        )
        try:
            response = _first(
                self.client.table("responses").insert(response_payload).execute()
            )
        except Exception as exc:
            if not _schema_feature_missing(exc):
                raise
            legacy_payload = {
                key: value
                for key, value in response_payload.items()
                if key
                not in {
                    "analysis_group_key",
                    "analysis_group_name",
                    "current_job_title",
                    "notice_version",
                    "notice_content_sha256",
                    "notice_accepted_at",
                }
            }
            response = _first(
                self.client.table("responses").insert(legacy_payload).execute()
            )
        if not response:
            raise RuntimeError("Falha ao registrar resposta.")
        response_id = str(response["id"])

        item_rows: list[dict[str, Any]] = []
        for key, value in (items or {}).items():
            if value is None or str(value).strip() == "":
                continue
            question = by_code.get(_question_code(key)) or by_id.get(str(key)) or by_text.get(str(key).strip().lower())
            if not question or question.get("question_type") == "open_text":
                continue
            code = _question_code(question.get("code"))
            number = _question_number(code)
            numeric_score = None
            exposure_score = None
            if number is not None:
                from reporting import answer_to_exposure_score, answer_to_frequency_score

                numeric = answer_to_frequency_score(value)
                exposure = answer_to_exposure_score(value, number)
                numeric_score = None if math.isnan(numeric) else round(float(numeric), 2)
                exposure_score = None if math.isnan(exposure) else round(float(exposure), 2)
            item_rows.append(
                {
                    "response_id": response_id,
                    "question_id": question["id"],
                    "raw_value": str(value),
                    "numeric_score": numeric_score,
                    "exposure_score": exposure_score,
                }
            )
        if item_rows:
            self.client.table("response_items").insert(item_rows).execute()

        open_rows = self._build_open_answer_rows(response_id, questions, open_answers)
        if open_rows:
            self.client.table("open_answers").insert(open_rows).execute()

        return response

    def _build_open_answer_rows(
        self,
        response_id: str,
        questions: list[dict[str, Any]],
        open_answers: dict[Any, Any] | list[dict[str, Any]] | None,
    ) -> list[dict[str, Any]]:
        if not open_answers:
            return []
        by_code = {_question_code(q.get("code")): q for q in questions}
        by_text = {str(q.get("text", "")).strip().lower(): q for q in questions}
        rows: list[dict[str, Any]] = []
        if isinstance(open_answers, dict):
            iterable: Iterable[tuple[Any, Any]] = open_answers.items()
            normalized = [
                {"prompt_code": key, "raw_text": value}
                for key, value in iterable
            ]
        else:
            normalized = list(open_answers)
        for answer in normalized:
            raw_text = str(answer.get("raw_text") or answer.get("text") or "").strip()
            if not raw_text:
                continue
            prompt_code = _question_code(
                answer.get("prompt_code")
                or answer.get("code")
                or answer.get("question_code")
                or ""
            )
            question = by_code.get(prompt_code) or by_text.get(str(answer.get("prompt_code", "")).strip().lower())
            rows.append(
                {
                    "response_id": response_id,
                    "question_id": question.get("id") if question else None,
                    "prompt_code": prompt_code or str(answer.get("prompt_code") or "A"),
                    "raw_text": raw_text,
                    "released_to_report": False,
                }
            )
        return rows

    def list_responses_for_campaign(self, campaign_id: str | None = None) -> list[dict[str, Any]]:
        response_query = (
            self.client.table("responses")
            .select("*")
            .order("submitted_at")
        )
        if campaign_id:
            response_query = response_query.eq("campaign_id", campaign_id)
        responses = _rows(response_query.execute())
        if not responses:
            return []

        response_ids = [str(row["id"]) for row in responses]
        campaign_ids = sorted({str(row["campaign_id"]) for row in responses if row.get("campaign_id")})
        campaigns_by_id = self._campaign_index(campaign_ids)
        items_by_response = self._items_index(response_ids)
        open_by_response = self._open_answers_index(response_ids)

        flattened: list[dict[str, Any]] = []
        for response in responses:
            response_id = str(response["id"])
            campaign = campaigns_by_id.get(str(response.get("campaign_id")), {})
            company = campaign.get("companies") or {}
            demographics = response.get("demographics") or {}
            if not isinstance(demographics, dict):
                demographics = {}
            group_name = str(
                response.get("analysis_group_name")
                or demographics.get("analysis_group_name")
                or response.get("sector")
                or ""
            ).strip()
            group_key = str(
                response.get("analysis_group_key")
                or demographics.get("analysis_group_key")
                or (_canonical_key(group_name, fallback="grupo") if group_name else "")
            ).strip()
            current_job = str(
                response.get("current_job_title")
                or response.get("role_family")
                or ""
            ).strip()
            accepted_notice_version = str(
                response.get("notice_version")
                or demographics.get("notice_version")
                or ""
            ).strip()
            accepted_at = (
                response.get("notice_accepted_at")
                or demographics.get("notice_accepted_at")
                or ""
            )
            required_notice_version = str(campaign.get("notice_version") or "").strip()
            if not _boolish(response.get("consent_accepted"), True):
                continue
            if required_notice_version and accepted_notice_version != required_notice_version:
                continue
            row: dict[str, Any] = {
                "CARIMBO_DE_DATA_HORA": response.get("submitted_at") or response.get("created_at"),
                "EMPRESA_ID": campaign.get("company_id", ""),
                "NOME_DA_EMPRESA": company.get("trade_name") or company.get("legal_name") or "",
                "CICLO_ID": response.get("campaign_id", ""),
                "SETOR": group_name,
                "GRUPO_ID": group_key,
                "GRUPO_ANALISE": group_name,
                "CARGO": current_job,
                "CARGO_ATUAL": current_job,
                "UNIDADE": response.get("work_unit") or "",
                "CIENCIA_AVISO": "SIM" if response.get("consent_accepted") else "NAO",
                "AVISO_VERSAO": accepted_notice_version,
                "CIENCIA_AVISO_EM": accepted_at,
            }
            reserved_demographic_keys = {
                "analysis_group_key",
                "analysis_group_name",
                "notice_version",
                "notice_content_sha256",
                "notice_accepted_at",
            }
            for key, value in demographics.items():
                if key not in reserved_demographic_keys and value not in (None, ""):
                    row[str(key).upper()] = value
            for item in items_by_response.get(response_id, []):
                question = item.get("questions") or {}
                question_text = str(question.get("text") or question.get("code") or item.get("question_id"))
                row[question_text] = item.get("raw_value")
            for answer in open_by_response.get(response_id, []):
                prompt_code = str(answer.get("prompt_code") or "").strip()
                if prompt_code:
                    row[prompt_code] = answer.get("raw_text") or ""
            flattened.append(row)
        return flattened

    def _campaign_index(self, campaign_ids: list[str]) -> dict[str, dict[str, Any]]:
        if not campaign_ids:
            return {}
        rows = _rows(
            self.client.table("campaigns")
            .select("*,companies(id,legal_name,trade_name)")
            .in_("id", campaign_ids)
            .execute()
        )
        return {str(row["id"]): row for row in rows}

    def _items_index(self, response_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not response_ids:
            return {}
        rows = _rows(
            self.client.table("response_items")
            .select("response_id,question_id,raw_value,numeric_score,exposure_score,questions(code,text,sort_order)")
            .in_("response_id", response_ids)
            .execute()
        )
        result: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            result.setdefault(str(row["response_id"]), []).append(row)
        return result

    def _open_answers_index(self, response_ids: list[str]) -> dict[str, list[dict[str, Any]]]:
        if not response_ids:
            return {}
        rows = _rows(
            self.client.table("open_answers")
            .select("response_id,prompt_code,raw_text,released_to_report")
            .in_("response_id", response_ids)
            .execute()
        )
        result: dict[str, list[dict[str, Any]]] = {}
        for row in rows:
            result.setdefault(str(row["response_id"]), []).append(row)
        return result

    # ------------------------------------------------------------------
    # Relatorios e Storage
    # ------------------------------------------------------------------
    def create_report(self, data: dict[str, Any]) -> dict[str, Any]:
        metadata = dict(data.get("metadata") or {})
        for key in ("zip_file_name", "ZIP_FILE_NAME"):
            if data.get(key):
                metadata["zip_file_name"] = data[key]
        payload = _clean_dict(
            {
                "campaign_id": data.get("campaign_id") or data.get("CICLO_ID"),
                "scope_type": data.get("scope_type") or self._infer_scope_type(data.get("ESCOPO")),
                "scope_name": data.get("scope_name") or data.get("ESCOPO") or "Geral",
                "storage_bucket": data.get("storage_bucket") or self.settings.supabase_storage_bucket,
                "storage_path": data.get("storage_path") or data.get("FILE_ID"),
                "file_name": data.get("file_name") or data.get("FILE_NAME"),
                "sha256": data.get("sha256") or data.get("ZIP_SHA256"),
                "report_version": data.get("report_version") or data.get("VERSAO") or "4.0-v2-supabase",
                "visible_to_client": _boolish(data.get("visible_to_client") or data.get("VISIVEL_CLIENTE"), True),
                "respondents_count": data.get("respondents_count") or data.get("N_RESPONDENTES"),
                "generated_at": data.get("generated_at") or data.get("GERADO_EM"),
                "metadata": metadata,
            }
        )
        return _first(self.client.table("reports").insert(payload).execute()) or {}

    def list_reports(self, campaign_id: str | None = None) -> list[dict[str, Any]]:
        query = self.client.table("reports").select("*").order("generated_at", desc=True)
        if campaign_id:
            query = query.eq("campaign_id", campaign_id)
        return _rows(query.execute())

    def upload_report_file(self, local_path: str | Path, storage_path: str) -> str:
        path = Path(local_path)
        return self.upload_report_bytes(path.read_bytes(), storage_path)

    def upload_report_bytes(self, content: bytes, storage_path: str) -> str:
        storage_path = storage_path.strip("/")
        self.client.storage.from_(self.settings.supabase_storage_bucket).upload(
            storage_path,
            content,
            file_options={
                "content-type": "application/zip",
                "x-upsert": "true",
            },
        )
        return storage_path

    def download_report_file(self, storage_path: str) -> bytes:
        return self.client.storage.from_(self.settings.supabase_storage_bucket).download(storage_path)

    def delete_report_file(self, storage_path: str) -> None:
        if str(storage_path or "").strip():
            self.client.storage.from_(self.settings.supabase_storage_bucket).remove([storage_path])

    def make_report_storage_path(self, *, company_id: str, campaign_id: str, filename: str) -> str:
        return "/".join(
            [
                "company",
                _storage_path_part(company_id),
                "campaign",
                _storage_path_part(campaign_id),
                _storage_path_part(filename),
            ]
        )

    def sha256_bytes(self, content: bytes) -> str:
        return hashlib.sha256(content).hexdigest()

    @staticmethod
    def _infer_scope_type(scope: Any) -> str:
        normalized = _slug(str(scope or ""))
        if normalized in {"GERAL", "VISAO_GERAL", "VIS_O_GERAL", "EMPRESA"}:
            return "company"
        return "sector"

    # ------------------------------------------------------------------
    # Alertas, metricas e auditoria
    # ------------------------------------------------------------------
    def create_alert(self, data: dict[str, Any]) -> dict[str, Any]:
        severity = str(data.get("severity") or data.get("severidade") or "attention").strip().lower()
        severity = {
            "critico": "critical",
            "crítico": "critical",
            "critical": "critical",
            "alto": "high",
            "high": "high",
            "atencao": "attention",
            "atenção": "attention",
            "attention": "attention",
            "info": "info",
        }.get(severity, "attention")
        payload = _clean_dict(
            {
                "campaign_id": data.get("campaign_id") or data.get("CICLO_ID"),
                "scope_type": data.get("scope_type") or "company",
                "scope_name": data.get("scope_name"),
                "severity": severity,
                "code": data.get("code") or data.get("codigo") or "ALERTA_TECNICO",
                "title": data.get("title") or data.get("titulo") or "Alerta para revisão técnica",
                "description": data.get("description")
                or data.get("descricao")
                or "Sinal para análise humana qualificada, sem conclusão diagnóstica automática.",
                "evidence": data.get("evidence") or data.get("evidencia") or {},
                "status": data.get("status") or "open",
            }
        )
        return _first(self.client.table("alerts").insert(payload).execute()) or {}

    def list_alerts(self, campaign_id: str | None = None) -> list[dict[str, Any]]:
        query = self.client.table("alerts").select("*").order("created_at", desc=True)
        if campaign_id:
            query = query.eq("campaign_id", campaign_id)
        return _rows(query.execute())

    def list_organizational_metrics(self, campaign_id: str) -> list[dict[str, Any]]:
        return _rows(
            self.client.table("organizational_metrics")
            .select("*")
            .eq("campaign_id", campaign_id)
            .order("created_at", desc=True)
            .execute()
        )

    def create_organizational_metric(self, data: dict[str, Any]) -> dict[str, Any]:
        return _first(self.client.table("organizational_metrics").insert(data).execute()) or {}

    def write_audit_log(
        self,
        action: str,
        entity_type: str = "",
        entity_id: str = "",
        metadata: dict[str, Any] | None = None,
        *,
        actor_type: str = "system",
        company_id: str | None = None,
        campaign_id: str | None = None,
    ) -> None:
        details = dict(metadata or {})
        if entity_type:
            details.setdefault("entity_type", entity_type)
        if entity_id:
            details.setdefault("entity_id", entity_id)
        payload = {
            "actor_type": actor_type or "system",
            "company_id": company_id or (entity_id if entity_type == "company" else None),
            "campaign_id": campaign_id or (entity_id if entity_type in {"campaign", "cycle"} else None),
            "action": action,
            "details": details,
        }
        self.client.table("audit_logs").insert(payload).execute()

    def log_audit(
        self,
        *,
        action: str,
        details: dict[str, Any] | None = None,
        company_id: str | None = None,
        campaign_id: str | None = None,
    ) -> None:
        self.write_audit_log(
            action,
            metadata=details,
            company_id=company_id,
            campaign_id=campaign_id,
        )

    def list_audit_logs(self, limit: int = 200) -> list[dict[str, Any]]:
        return _rows(
            self.client.table("audit_logs")
            .select("*")
            .order("created_at", desc=True)
            .limit(limit)
            .execute()
        )

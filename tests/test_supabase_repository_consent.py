from __future__ import annotations

from typing import Any

import pytest

from supabase_repository import SupabaseRepository


class UnexpectedDatabaseAccess:
    """Falha se uma resposta inválida chegar à camada de persistência."""

    def table(self, table_name: str) -> Any:
        raise AssertionError(
            f"O repositório tentou acessar {table_name!r} antes de validar o consentimento."
        )


class FakeResponse:
    def __init__(self, data: list[dict[str, Any]]) -> None:
        self.data = data


class ResponseQuery:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def select(self, *args: Any, **kwargs: Any) -> ResponseQuery:
        return self

    def order(self, *args: Any, **kwargs: Any) -> ResponseQuery:
        return self

    def eq(self, *args: Any, **kwargs: Any) -> ResponseQuery:
        return self

    def execute(self) -> FakeResponse:
        return FakeResponse(self.rows)


class ResponseReadClient:
    def __init__(self, rows: list[dict[str, Any]]) -> None:
        self.rows = rows

    def table(self, table_name: str) -> ResponseQuery:
        assert table_name == "responses"
        return ResponseQuery(self.rows)


def make_repository_without_supabase(monkeypatch: pytest.MonkeyPatch) -> SupabaseRepository:
    repo = object.__new__(SupabaseRepository)
    repo.client = UnexpectedDatabaseAccess()
    monkeypatch.setattr(
        repo,
        "get_campaign",
        lambda campaign_id: {"id": campaign_id, "questionnaire_id": "questionnaire-1"},
    )
    monkeypatch.setattr(repo, "list_questions", lambda questionnaire_id: [])
    return repo


@pytest.mark.parametrize(
    "metadata",
    [
        {},
        {"consent_accepted": None},
        {"consent_accepted": False},
        {"consent_accepted": ""},
        {"consent_accepted": "NAO"},
        {"consent_accepted": "talvez"},
    ],
)
def test_create_response_rejects_missing_or_non_affirmative_consent(
    monkeypatch: pytest.MonkeyPatch,
    metadata: dict[str, Any],
) -> None:
    repo = make_repository_without_supabase(monkeypatch)

    with pytest.raises(ValueError, match=r"(?i)consent|aceite|particip"):
        repo.create_response(
            "campaign-1",
            metadata,
            items={},
            open_answers=None,
        )


def test_flattened_responses_expose_the_canonical_group_expected_by_reporting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    response_rows = [
        {
            "id": "response-vendas",
            "campaign_id": "campaign-1",
            "submitted_at": "2026-07-11T10:00:00-03:00",
            "sector": "Administrativo",
            "role_family": "Vendedor",
            "campaign_area_id": "area-vendas",
            "analysis_group_key": "administrativo",
            "analysis_group_name": "Administrativo",
            "demographics": {},
        },
        {
            "id": "response-rh",
            "campaign_id": "campaign-1",
            "submitted_at": "2026-07-11T10:01:00-03:00",
            "sector": "Administrativo",
            "role_family": "",
            "campaign_area_id": "area-rh",
            "analysis_group_key": "administrativo",
            "analysis_group_name": "Administrativo",
            "demographics": {},
        },
    ]
    repo = object.__new__(SupabaseRepository)
    repo.client = ResponseReadClient(response_rows)
    monkeypatch.setattr(
        repo,
        "_campaign_index",
        lambda campaign_ids: {
            "campaign-1": {
                "id": "campaign-1",
                "company_id": "company-1",
                "companies": {"legal_name": "Empresa Teste"},
            }
        },
    )
    monkeypatch.setattr(repo, "_items_index", lambda response_ids: {})
    monkeypatch.setattr(repo, "_open_answers_index", lambda response_ids: {})

    flattened = repo.list_responses_for_campaign("campaign-1")

    assert [row["GRUPO_ID"] for row in flattened] == ["administrativo"] * 2
    assert [row["GRUPO_ANALISE"] for row in flattened] == ["Administrativo"] * 2
    assert [row["SETOR"] for row in flattened] == ["Administrativo"] * 2
    assert [row["CARGO_ATUAL"] for row in flattened] == ["Vendedor", ""]

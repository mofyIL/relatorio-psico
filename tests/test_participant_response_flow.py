from __future__ import annotations

import unicodedata

import pytest
from streamlit.testing.v1 import AppTest


PARTICIPANT_APP = r'''
import streamlit as st

import app


CAMPAIGN_ID = "campaign-1"
NOTICE_VERSION = getattr(app, "PARTICIPANT_NOTICE_VERSION", "2026-07-11")


class FakeRepository:
    def get_campaign_by_code(self, code):
        assert code == "participant-token"
        return {
            "id": CAMPAIGN_ID,
            "company_id": "company-1",
            "questionnaire_id": "questionnaire-1",
            "code": code,
            "status": "collecting",
            "closes_at": "2099-12-31T23:59:59-03:00",
            "min_group_size": 7,
            "notice_version": NOTICE_VERSION,
            "participant_notice_version": NOTICE_VERSION,
            "notice_controller_name": "Empresa Teste",
            "notice_operator_name": "Prestador Teste",
            "notice_contact": "privacidade@example.com",
            "notice_retention": "12 meses após o encerramento",
            "companies": {
                "id": "company-1",
                "legal_name": "Empresa Teste",
                "trade_name": "Empresa Teste",
                "lgpd_controller_name": "Empresa Teste",
                "lgpd_contact_email": "privacidade@example.com",
            },
        }

    def list_questions(self, questionnaire_id):
        assert questionnaire_id == "questionnaire-1"
        return [
            {
                "id": f"question-{number}",
                "code": f"Q{number:02d}",
                "text": f"Pergunta fechada Q{number:02d}",
                "question_type": "likert_frequency",
                "domains": {"code": "GERAL", "name": "Condições de trabalho"},
            }
            for number in range(1, 57)
        ]

    def list_campaign_sectors(self, campaign_id):
        assert campaign_id == CAMPAIGN_ID
        return [
            {
                "id": "area-vendas",
                "campaign_id": CAMPAIGN_ID,
                "sector_name": "Vendas",
                "analysis_group_key": "administrativo",
                "analysis_group_name": "Administrativo",
                "sort_order": 1,
                "reportable": True,
            },
            {
                "id": "area-rh",
                "campaign_id": CAMPAIGN_ID,
                "sector_name": "Recursos Humanos",
                "analysis_group_key": "administrativo",
                "analysis_group_name": "Administrativo",
                "sort_order": 2,
                "reportable": True,
            },
        ]

    def list_campaign_areas(self, campaign_id):
        return self.list_campaign_sectors(campaign_id)

    def create_response(self, campaign_id, metadata, items, open_answers=None):
        st.session_state["created_response"] = {
            "campaign_id": campaign_id,
            "metadata": dict(metadata),
            "items": dict(items),
            "open_answers": open_answers,
        }
        return {"id": "response-1"}


repo = FakeRepository()
app.backend_is_supabase = lambda: True
app.get_query_value = (
    lambda name: "participant-token" if name in {"respond", "responder"} else ""
)
app.supabase_repository = lambda: repo
app.log_audit = lambda *args, **kwargs: None
app.render_response_form()
'''


ACCEPT_OPTION = "Li as informações e desejo participar"
DECLINE_OPTION = "Não desejo participar"


def normalize(value: object) -> str:
    text = unicodedata.normalize("NFKD", str(value or ""))
    return text.encode("ascii", "ignore").decode("ascii").casefold()


def run_participant_app() -> AppTest:
    return AppTest.from_string(PARTICIPANT_APP, default_timeout=30).run()


def questionnaire_radios(rendered: AppTest):
    return [radio for radio in rendered.radio if radio.label.startswith("Pergunta fechada Q")]


def notice_decision_radio(rendered: AppTest):
    return next(
        radio
        for radio in rendered.radio
        if ACCEPT_OPTION in radio.options and DECLINE_OPTION in radio.options
    )


def continue_button(rendered: AppTest):
    return next(button for button in rendered.button if "continuar" in normalize(button.label))


def accept_notice(rendered: AppTest) -> AppTest:
    notice_decision_radio(rendered).set_value(ACCEPT_OPTION)
    return continue_button(rendered).click().run()


def test_questionnaire_is_not_rendered_before_affirmative_notice_acceptance() -> None:
    rendered = run_participant_app()

    assert questionnaire_radios(rendered) == []
    assert notice_decision_radio(rendered).value is None
    assert "created_response" not in rendered.session_state


def test_affirmative_acceptance_reveals_the_questionnaire() -> None:
    rendered = accept_notice(run_participant_app())

    assert len(questionnaire_radios(rendered)) == 56
    assert "created_response" not in rendered.session_state
    assert not rendered.exception


def test_declining_participation_ends_flow_without_persisting_a_response() -> None:
    rendered = run_participant_app()
    notice_decision_radio(rendered).set_value(DECLINE_OPTION)
    rendered = continue_button(rendered).click().run()

    assert questionnaire_radios(rendered) == []
    assert "created_response" not in rendered.session_state
    visible_text = " ".join(
        str(element.value)
        for collection in (rendered.info, rendered.success, rendered.warning)
        for element in collection
    )
    assert "particip" in normalize(visible_text)
    assert not rendered.exception


@pytest.mark.parametrize(
    ("area", "current_role"),
    [
        ("Vendas", "Vendedor"),
        ("Recursos Humanos", ""),
    ],
)
def test_predefined_areas_resolve_to_administrative_group_and_role_is_optional(
    area: str,
    current_role: str,
) -> None:
    rendered = accept_notice(run_participant_app())
    area_select = next(
        selectbox
        for selectbox in rendered.selectbox
        if "area" in normalize(selectbox.label)
    )
    assert {"Vendas", "Recursos Humanos"}.issubset(set(area_select.options))
    area_select.set_value(area)

    role_input = next(
        text_input
        for text_input in rendered.text_input
        if "cargo ou funcao atual" in normalize(text_input.label)
    )
    assert "opcional" in normalize(role_input.label)
    role_input.set_value(current_role)

    for radio in questionnaire_radios(rendered):
        radio.set_value("Às vezes")
    submit = next(
        button
        for button in rendered.button
        if "enviar resposta" in normalize(button.label)
    )
    rendered = submit.click().run()

    created = rendered.session_state["created_response"]
    metadata = created["metadata"]
    assert created["campaign_id"] == "campaign-1"
    assert metadata["sector"] == "Administrativo"
    assert metadata["analysis_group_key"] == "administrativo"
    assert metadata["analysis_group_name"] == "Administrativo"
    expected_area_id = "area-vendas" if area == "Vendas" else "area-rh"
    assert metadata["campaign_area_id"] == expected_area_id
    assert metadata["role_family"] == current_role
    assert metadata["consent_accepted"] is True
    assert metadata["notice_version"]
    assert metadata["notice_accepted_at"]
    assert len(created["items"]) == 56

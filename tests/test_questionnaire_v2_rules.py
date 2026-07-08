from __future__ import annotations

import pandas as pd

from questionnaire_v2 import CRITICAL_ITEMS, FATORES, OPEN_QUESTIONS, QUESTIONARIO
from reporting import (
    ReportConfig,
    build_critical_alerts,
    calculate_question_results,
    generate_company_reports,
)


def test_questionnaire_v2_shape_is_preserved() -> None:
    assert len(QUESTIONARIO) == 56
    assert len(OPEN_QUESTIONS) == 4
    assert len(FATORES) == 13
    assert len(CRITICAL_ITEMS) == 8


def test_default_confidentiality_minimum_is_seven() -> None:
    assert ReportConfig().min_group_size == 7


def test_small_groups_are_suppressed_by_default() -> None:
    data = {"SETOR": ["Pequeno"] * 6}
    for question in QUESTIONARIO.values():
        data[question] = ["Às vezes"] * 6
    reports, suppressed = generate_company_reports(
        pd.DataFrame(data),
        company="Empresa Teste",
        cycle_label="Ciclo 2026",
        config=ReportConfig(),
    )
    assert suppressed == ["Pequeno"]
    assert len(reports) == 1


def test_critical_alerts_are_sentinel_signals_not_diagnoses() -> None:
    data = {}
    for number, question in QUESTIONARIO.items():
        data[question] = ["Sempre"] * 10 if number in CRITICAL_ITEMS else ["Nunca / Quase Nunca"] * 10
    question_results = calculate_question_results(pd.DataFrame(data))
    alerts = build_critical_alerts(question_results)
    assert alerts
    assert {alert["severidade"] for alert in alerts} == {"crítico"}
    assert all("revisão técnica" in str(alert["mensagem"]) for alert in alerts)

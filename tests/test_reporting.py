from __future__ import annotations

from datetime import datetime

import pandas as pd

from reporting import (
    ESCALA_CURTA,
    QUESTIONARIO,
    ReportConfig,
    answer_to_exposure_score,
    build_action_plan,
    calculate_factor_results,
    calculate_question_results,
    generate_company_reports,
    validate_questionnaire_columns,
)


def make_full_df(rows: int = 6, answer="Às vezes") -> pd.DataFrame:
    data = {"SETOR": ["Operação"] * rows}
    for question in QUESTIONARIO.values():
        data[question] = [answer] * rows
    return pd.DataFrame(data)


def test_exposure_score_inverts_protective_items_and_keeps_exposure_items() -> None:
    # Q5 é protetivo: frequência maior reduz exposição.
    assert answer_to_exposure_score("Sempre", 5) == 0.0
    assert answer_to_exposure_score("Nunca / Quase Nunca", 5) == 100.0
    # Q1 é risco: frequência maior aumenta exposição.
    assert answer_to_exposure_score("Sempre", 1) == 100.0
    assert answer_to_exposure_score("Nunca / Quase Nunca", 1) == 0.0


def test_questionnaire_validation_detects_missing_columns() -> None:
    df = make_full_df()
    validation = validate_questionnaire_columns(df)
    assert validation["found_questions"] == len(QUESTIONARIO)
    assert validation["missing_questions"] == []

    incomplete = df.drop(columns=[QUESTIONARIO[3], QUESTIONARIO[12]])
    validation = validate_questionnaire_columns(incomplete)
    assert validation["found_questions"] == len(QUESTIONARIO) - 2
    assert validation["missing_questions"] == [3, 12]


def test_numeric_answers_are_counted_in_distribution() -> None:
    df = make_full_df(rows=5, answer=3)
    results = calculate_question_results(df)
    q1 = results[results["Numero"] == 1].iloc[0]
    assert q1["Respostas_validas"] == 5
    assert q1[ESCALA_CURTA[2]].startswith("5 (")


def test_factor_results_and_action_plan_are_generated() -> None:
    df = make_full_df(rows=6, answer="Frequentemente")
    factors = calculate_factor_results(df)
    assert {"DEM", "CTL", "LID", "CRI"}.issubset(set(factors["Codigo"]))
    assert "Desvio_padrao" in factors.columns
    assert "Pct_alta_exposicao" in factors.columns
    plan = build_action_plan(factors)
    assert len(plan) == len(factors)
    assert "Ações sugeridas" in plan.columns


def test_generate_company_reports_suppresses_small_sectors() -> None:
    df = make_full_df(rows=6, answer="Às vezes")
    df.loc[0:1, "SETOR"] = "Pequeno"
    df.loc[2:, "SETOR"] = "Grande"
    reports, suppressed = generate_company_reports(
        df,
        company="Empresa Teste",
        cycle_label="Ciclo 2026",
        config=ReportConfig(min_group_size=3, report_version="teste"),
        generated_at=datetime(2026, 7, 8, 12, 0),
    )
    assert "Pequeno" in suppressed
    assert len(reports) == 2  # visão geral + setor Grande
    assert all(report.docx.startswith(b"PK") for report in reports)

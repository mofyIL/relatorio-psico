from __future__ import annotations

import pandas as pd

import reporting


def fake_report(
    df_scope: pd.DataFrame,
    *,
    scope: str,
    **_: object,
) -> reporting.GeneratedReport:
    return reporting.GeneratedReport(
        scope=scope,
        respondents=len(df_scope),
        docx=b"",
        filename=f"{scope}.docx",
    )


def test_vendas_and_rh_share_the_administrative_analysis_group(monkeypatch) -> None:
    monkeypatch.setattr(reporting, "create_collective_report", fake_report)
    responses = pd.DataFrame(
        {
            "AREA_TRABALHO": ["Vendas", "Recursos Humanos"],
            "GRUPO_ID": ["administrativo", "administrativo"],
            "GRUPO_ANALISE": ["Administrativo", "Administrativo"],
            "CARGO_ATUAL": ["Vendedor", "Analista de RH"],
        }
    )

    reports, suppressed = reporting.generate_company_reports(
        responses,
        company="Empresa Teste",
        cycle_label="Ciclo 2026",
        config=reporting.ReportConfig(min_group_size=2),
    )

    assert suppressed == []
    assert [report.scope for report in reports] == [
        "Visão geral da empresa",
        "Grupo de análise: Administrativo",
    ]
    assert reports[1].respondents == 2


def test_optional_current_role_does_not_create_or_split_analysis_groups(monkeypatch) -> None:
    monkeypatch.setattr(reporting, "create_collective_report", fake_report)
    responses = pd.DataFrame(
        {
            "AREA_TRABALHO": ["Vendas", "Vendas", "Recursos Humanos"],
            "GRUPO_ID": ["administrativo"] * 3,
            "GRUPO_ANALISE": ["Administrativo"] * 3,
            "CARGO_ATUAL": ["Vendedor", "", None],
        }
    )

    reports, suppressed = reporting.generate_company_reports(
        responses,
        company="Empresa Teste",
        cycle_label="Ciclo 2026",
        config=reporting.ReportConfig(min_group_size=2),
    )

    assert suppressed == []
    assert len(reports) == 2
    assert reports[1].scope == "Grupo de análise: Administrativo"
    assert reports[1].respondents == 3


from __future__ import annotations

import unittest
from unittest.mock import patch

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


class ReportingGroupTests(unittest.TestCase):
    @patch("reporting.create_collective_report", side_effect=fake_report)
    def test_distinct_areas_share_one_canonical_analysis_group(self, _: object) -> None:
        responses = pd.DataFrame(
            {
                "AREA_TRABALHO": ["Vendas", "Vendas", "Recursos Humanos"],
                "GRUPO_ID": ["GRP_ADMIN", "GRP_ADMIN", "GRP_ADMIN"],
                "GRUPO_ANALISE": ["Administrativo"] * 3,
            }
        )

        reports, suppressed = reporting.generate_company_reports(
            responses,
            company="Empresa",
            cycle_label="Ciclo 2026",
            config=reporting.ReportConfig(min_group_size=3),
        )

        self.assertEqual(suppressed, [])
        self.assertEqual([report.scope for report in reports], [
            "Visão geral da empresa",
            "Grupo de análise: Administrativo",
        ])
        self.assertEqual(reports[1].respondents, 3)

    @patch("reporting.create_collective_report", side_effect=fake_report)
    def test_legacy_sector_values_are_normalized_before_grouping(self, _: object) -> None:
        responses = pd.DataFrame(
            {"SETOR": [" Administrativo ", "administrativo", "ADMINISTRATÍVO"]}
        )

        reports, suppressed = reporting.generate_company_reports(
            responses,
            company="Empresa",
            cycle_label="Ciclo 2026",
            config=reporting.ReportConfig(min_group_size=3),
        )

        self.assertEqual(suppressed, [])
        self.assertEqual(len(reports), 2)
        self.assertEqual(reports[1].respondents, 3)

    @patch("reporting.create_collective_report", side_effect=fake_report)
    def test_single_small_group_triggers_complementary_suppression(self, _: object) -> None:
        responses = pd.DataFrame(
            {
                "GRUPO_ID": ["GRP_ADMIN"] * 5 + ["GRP_OP"] * 2,
                "GRUPO_ANALISE": ["Administrativo"] * 5 + ["Operacional"] * 2,
            }
        )

        reports, suppressed = reporting.generate_company_reports(
            responses,
            company="Empresa",
            cycle_label="Ciclo 2026",
            config=reporting.ReportConfig(min_group_size=5),
        )

        self.assertEqual(suppressed, ["Administrativo", "Operacional"])
        self.assertEqual([report.respondents for report in reports], [7])

    @patch("reporting.create_collective_report", side_effect=fake_report)
    def test_two_small_groups_do_not_hide_an_extra_eligible_group(self, _: object) -> None:
        responses = pd.DataFrame(
            {
                "GRUPO_ID": ["GRP_ADMIN"] * 5 + ["GRP_OP"] * 2 + ["GRP_COM"] * 2,
                "GRUPO_ANALISE": ["Administrativo"] * 5 + ["Operacional"] * 2 + ["Comercial"] * 2,
            }
        )

        reports, suppressed = reporting.generate_company_reports(
            responses,
            company="Empresa",
            cycle_label="Ciclo 2026",
            config=reporting.ReportConfig(min_group_size=5),
        )

        self.assertEqual(suppressed, ["Comercial", "Operacional"])
        self.assertEqual([report.respondents for report in reports], [9, 5])


if __name__ == "__main__":
    unittest.main()

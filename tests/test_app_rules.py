from __future__ import annotations

import unittest

import pandas as pd

import app


class StructureRulesTests(unittest.TestCase):
    def test_parse_structure_lines_supports_mapping_and_simple_group(self) -> None:
        mappings, errors = app.parse_structure_lines(
            "Vendas | Administrativo\nRecursos Humanos | Administrativo\nOperacional"
        )

        self.assertEqual(errors, [])
        self.assertEqual(
            mappings,
            [
                ("Vendas", "Administrativo"),
                ("Recursos Humanos", "Administrativo"),
                ("Operacional", "Operacional"),
            ],
        )

    def test_parse_structure_lines_rejects_conflicting_area(self) -> None:
        _, errors = app.parse_structure_lines(
            "Vendas | Administrativo\n vendas | Comercial"
        )

        self.assertEqual(len(errors), 1)
        self.assertIn("mais de um grupo", errors[0])

    def test_group_id_is_canonical_with_case_and_accents(self) -> None:
        first = app.make_group_id("EMP_1", " Administrativo ")
        second = app.make_group_id("EMP_1", "administrativo")

        self.assertEqual(first, second)
        self.assertNotEqual(first, app.make_group_id("EMP_2", "Administrativo"))

    def test_public_participant_token_does_not_authenticate_client_lookup(self) -> None:
        cycles = pd.DataFrame(
            [{"TOKEN": "panel-secret", "PARTICIPANT_TOKEN": "public-link"}]
        )

        self.assertIsNone(app.find_cycle_by_token(cycles, "public-link"))
        self.assertIsNotNone(app.find_cycle_by_participant_token(cycles, "public-link"))


class NoticeRulesTests(unittest.TestCase):
    def test_notice_version_must_have_an_immutable_template(self) -> None:
        fields = {
            "AVISO_CONTROLADOR": "Empresa",
            "AVISO_OPERADOR": "Operador",
            "AVISO_CONTATO": "contato@example.com",
            "AVISO_RETENCAO": "12 meses",
        }

        self.assertTrue(
            app.notice_is_complete(
                {**fields, "AVISO_VERSAO": app.PARTICIPANT_NOTICE_VERSION}
            )
        )
        self.assertFalse(app.notice_is_complete({**fields, "AVISO_VERSAO": "desconhecida"}))

    def test_filter_notice_keeps_only_matching_affirmative_version(self) -> None:
        responses = pd.DataFrame(
            {
                "CIENCIA_AVISO": ["SIM", "NAO", "SIM", ""],
                "AVISO_VERSAO": ["v1", "v1", "v2", "v1"],
                "VALOR": [1, 2, 3, 4],
            }
        )

        filtered = app.filter_notice_responses(
            responses,
            {"AVISO_VERSAO": "v1"},
        )

        self.assertEqual(filtered["VALOR"].tolist(), [1])

    def test_filter_notice_is_strict_when_columns_are_missing(self) -> None:
        responses = pd.DataFrame({"VALOR": [1, 2]})

        filtered = app.filter_notice_responses(
            responses,
            {"AVISO_VERSAO": "v1"},
        )

        self.assertTrue(filtered.empty)

    def test_legacy_cycle_without_notice_keeps_existing_responses(self) -> None:
        responses = pd.DataFrame({"VALOR": [1, 2]})

        filtered = app.filter_notice_responses(responses, {"AVISO_VERSAO": ""})

        self.assertEqual(filtered["VALOR"].tolist(), [1, 2])

    def test_cycle_filter_accepts_native_iso_timestamp_and_notice(self) -> None:
        company = pd.Series({"EMPRESA_ID": "EMP1", "NOME": "Empresa"})
        cycle = pd.Series(
            {
                "CICLO_ID": "C1",
                "EMPRESA_ID": "EMP1",
                "INICIO_EM": "2026-07-01T00:00:00-03:00",
                "ENCERRADO_EM": "2026-07-31T23:59:59-03:00",
                "AVISO_VERSAO": "v1",
            }
        )
        responses = pd.DataFrame(
            {
                "CICLO_ID": ["C1", "C1"],
                "CARIMBO_DE_DATA_HORA": [
                    "2026-07-11T10:00:00-03:00",
                    "2026-08-01T10:00:00-03:00",
                ],
                "CIENCIA_AVISO": ["SIM", "SIM"],
                "AVISO_VERSAO": ["v1", "v1"],
            }
        )

        filtered = app.filter_cycle_responses(responses, company, cycle)

        self.assertEqual(len(filtered), 1)
        self.assertEqual(filtered.iloc[0]["CARIMBO_DE_DATA_HORA"], "2026-07-11T10:00:00-03:00")

    def test_mixed_sheet_preserves_legacy_and_native_cycle_filters(self) -> None:
        company = pd.Series({"EMPRESA_ID": "EMP1", "NOME": "Empresa"})
        responses = pd.DataFrame(
            {
                "CICLO_ID": ["", "C_NEW"],
                "EMPRESA_ID": ["", "EMP1"],
                "NOME_DA_EMPRESA": ["Empresa", "Empresa"],
                "CARIMBO_DE_DATA_HORA": [
                    "10/07/2025 10:00:00",
                    "2026-07-10T10:00:00-03:00",
                ],
                "CIENCIA_AVISO": ["", "SIM"],
                "AVISO_VERSAO": ["", "v1"],
            }
        )
        legacy_cycle = pd.Series(
            {
                "CICLO_ID": "C_OLD",
                "INICIO_EM": "2025-07-01T00:00:00-03:00",
                "ENCERRADO_EM": "2025-07-31T23:59:59-03:00",
                "AVISO_VERSAO": "",
            }
        )
        native_cycle = pd.Series(
            {
                "CICLO_ID": "C_NEW",
                "INICIO_EM": "2026-07-01T00:00:00-03:00",
                "ENCERRADO_EM": "2026-07-31T23:59:59-03:00",
                "AVISO_VERSAO": "v1",
            }
        )

        legacy = app.filter_cycle_responses(responses, company, legacy_cycle)
        native = app.filter_cycle_responses(responses, company, native_cycle)

        self.assertEqual(legacy["CICLO_ID"].tolist(), [""])
        self.assertEqual(native["CICLO_ID"].tolist(), ["C_NEW"])


if __name__ == "__main__":
    unittest.main()

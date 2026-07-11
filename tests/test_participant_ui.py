from __future__ import annotations

import unittest

from streamlit.testing.v1 import AppTest


PARTICIPANT_APP = r'''
import pandas as pd
import app

company = pd.DataFrame([
    {"EMPRESA_ID": "EMP1", "NOME": "Empresa Teste", "ATIVO": "SIM"}
])
cycle = pd.DataFrame([{
    "CICLO_ID": "C1",
    "EMPRESA_ID": "EMP1",
    "TOKEN": "token",
    "PARTICIPANT_TOKEN": "participant-token",
    "STATUS": "COLETA",
    "VALIDO_ATE": "2099-01-01",
    "INICIO_EM": "2026-01-01T00:00:00-03:00",
    "MIN_GRUPO": "5",
    "AVISO_VERSAO": app.PARTICIPANT_NOTICE_VERSION,
    "AVISO_CONTROLADOR": "Empresa Teste",
    "AVISO_OPERADOR": "Operador Teste",
    "AVISO_CONTATO": "privacidade@example.com",
    "AVISO_RETENCAO": "12 meses",
}])
structure = pd.DataFrame([{
    "CICLO_ID": "C1",
    "EMPRESA_ID": "EMP1",
    "ESTRUTURA_ID": "EST1",
    "AREA_TRABALHO": "Vendas",
    "GRUPO_ID": "GRP_ADMIN",
    "GRUPO_ANALISE": "Administrativo",
    "ORDEM": "1",
}])

def read_sheet(name):
    if name == app.SHEET_EMPRESAS:
        return company
    if name == app.SHEET_CICLOS:
        return cycle
    if name == app.SHEET_ESTRUTURA_CICLOS:
        return structure
    return pd.DataFrame()

app.get_query_value = lambda name: "participant-token" if name == "participar" else ""
app.read_sheet = read_sheet
app.render_participant()
'''


class ParticipantUiTests(unittest.TestCase):
    def test_questions_are_hidden_until_notice_is_affirmatively_accepted(self) -> None:
        rendered = AppTest.from_string(PARTICIPANT_APP, default_timeout=20).run()

        question_radios = [item for item in rendered.radio if item.label[:1].isdigit()]
        self.assertEqual(question_radios, [])
        self.assertIn("Aviso aos participantes", [item.value for item in rendered.subheader])

        rendered.radio[0].set_value("Li as informações e desejo participar")
        rendered.button[0].click().run()

        question_radios = [item for item in rendered.radio if item.label[:1].isdigit()]
        self.assertEqual(len(question_radios), 28)
        self.assertEqual(len(rendered.exception), 0)


if __name__ == "__main__":
    unittest.main()

# Instalação, publicação e operação

## 1. Limpeza do repositório

Este pacote revisado não inclui `.git`, `.venv`, `.venv-oauth`, `__pycache__`, backups ou secrets reais. Mantenha assim no GitHub.

Nunca faça commit de:

- `.streamlit/secrets.toml`;
- `credentials.json`;
- `token.json`;
- chaves `.pem`, `.key` ou arquivos de ambiente;
- ZIPs/DOCXs gerados para clientes.

## 2. Dependências

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python -m py_compile app.py reporting.py questionnaire_v2.py database.py supabase_repository.py scripts/check_supabase_connection.py
pytest -q
```

## 3. Supabase

No Supabase SQL Editor, rode nesta ordem:

1. `supabase/migrations/001_initial_schema.sql`
2. `supabase/migrations/002_rls_policies.sql`
3. `supabase/seed_questionnaire_v2.sql`

Crie um bucket privado chamado `reports` no Supabase Storage.

Depois configure `.streamlit/secrets.toml`:

```toml
[app]
backend_provider = "supabase"

[supabase]
url = "https://SEU-PROJETO.supabase.co"
anon_key = "..."
service_role_key = "..."
storage_bucket = "reports"
```

Valide sem imprimir chaves:

```bash
python scripts/check_supabase_connection.py
```

## 4. Google Cloud e APIs legadas

Use esta seção apenas se `backend_provider = "sheets"`.

Habilite no Google Cloud:

- Google Sheets API;
- Google Drive API.

### Sheets legado

Crie uma conta de serviço e compartilhe a planilha com o e-mail da conta de serviço como Editor.

### Drive legado

Esta versão usa OAuth de usuário para salvar e baixar ZIPs no Drive com escopo `drive.file`, menor que acesso total ao Drive. Configure `google_drive_oauth` nos Secrets e informe `drive.folder_id`.

## 5. Secrets do Streamlit

Copie `.streamlit/secrets.toml.example` para o painel de Secrets do Streamlit Community Cloud.

Gere um `credential_pepper` longo e aleatório. Depois gere o hash da senha administrativa:

```bash
python scripts/hash_secret.py --context ADMIN --secret 'SENHA_ADMIN_FORTE' --pepper 'MESMO_PEPPER_DOS_SECRETS'
```

Configure:

```toml
[app]
backend_provider = "supabase"
credential_pepper = "MESMO_PEPPER_DOS_SECRETS"
admin_password_hash = "v2$..."
```

`app.admin_password` ainda é aceito como compatibilidade, mas não é recomendado para produção.

## 6. Estrutura administrativa

Com Supabase, ao abrir `?admin=1`, o app usa as tabelas `companies`, `campaigns`, `responses`, `reports`, `alerts` e `audit_logs`.

Com Sheets legado, ao abrir `?admin=1`, o app cria ou completa as abas:

- `Empresas`
- `Ciclos`
- `Relatorios`
- `Auditoria`

A aba `Respostas` é alimentada pelo Google Forms.

## 7. Coleta

Com Supabase, o admin cria o ciclo e o app mostra:

- link do painel do cliente, protegido por PIN;
- link `?respond=...` para os participantes responderem sem identificação pessoal.

As respostas são gravadas em `responses`, `response_items` e `open_answers`. Comentários abertos não são liberados automaticamente ao cliente.

Com Google Forms legado, o Forms deve ter os 56 itens fechados com textos compatíveis com `questionnaire_v2.py`. Para reduzir erro operacional, crie perguntas de resposta curta para:

- `EMPRESA_ID`
- `CICLO_ID`

Use “Obter link pré-preenchido” e copie os IDs `entry.XXXX` para:

```toml
[google_forms]
entry_company_id = "..."
entry_cycle_id = "..."
```

O Forms não torna esses campos realmente ocultos ou imutáveis. O app filtra por ciclo, empresa e janela de datas; a coleta própria Supabase é o caminho recomendado.

## 8. Fluxo comercial

1. Cadastre a empresa.
2. Crie um ciclo com quantidade contratada, preço, mínimo e validade.
3. Envie link do painel e PIN por canais separados ao cliente.
4. Envie o link de resposta aos participantes.
5. Cliente solicita encerramento.
6. Admin confere respostas, excesso, pagamento e instrumento.
7. Admin libera geração.
8. Cliente gera o pacote definitivo.
9. Vocês fazem devolutiva pós-entrega e transformam achados em plano de ação.

## 9. Retenção e privacidade

Defina contratualmente:

- quem é controlador e operador;
- prazo de retenção de respostas brutas;
- prazo de retenção dos ZIPs finais;
- quem pode acessar planilha, Drive e painel;
- como o titular pode exercer direitos LGPD;
- como serão tratados grupos pequenos e risco de identificação indireta.

Use os modelos em `docs/`, mas revise com advogado antes da venda recorrente.

## 10. Limitações assumidas

- Google Sheets não é banco transacional. Serve para piloto e operação pequena.
- Login admin ainda é senha compartilhada; para escala, use autenticação individual com e-mail autorizado e MFA.
- O questionário é instrumento de triagem coletiva e apoio técnico, não diagnóstico ou laudo autônomo.
- Relatórios individuais não são entregues ao empregador.
- A service role do Supabase deve existir somente no servidor Streamlit.

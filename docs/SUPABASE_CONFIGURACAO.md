# Configuração do Supabase — Guia Prático

## 1. Criar projeto

Crie um projeto Supabase e copie:

- Project URL;
- anon key;
- service_role key.

A `service_role key` deve ficar somente em ambiente de servidor. Não use essa chave no navegador e não envie para clientes.

## 2. Rodar scripts SQL

No SQL Editor do Supabase, rode nesta ordem:

1. `supabase/migrations/001_initial_schema.sql`
2. `supabase/migrations/002_rls_policies.sql`
3. `supabase/migrations/003_participant_notice_and_analysis_groups.sql`
4. `supabase/seed_questionnaire_v2.sql`

## 3. Criar bucket de relatórios

Crie um bucket privado chamado:

```text
reports
```

Os relatórios finais são salvos nesse bucket em caminhos como:

```text
company/{company_id}/campaign/{campaign_id}/relatorio-final.zip
```

## 4. Configurar Streamlit secrets

Copie `.streamlit/secrets.toml.example` para `.streamlit/secrets.toml` e preencha:

```toml
[app]
backend_provider = "supabase"

[supabase]
url = "https://SEU-PROJETO.supabase.co"
anon_key = "..."
service_role_key = "..."
storage_bucket = "reports"
```

## 5. Política operacional

- O Streamlit usa `service_role_key` no servidor.
- Usuários finais não devem receber acesso direto às tabelas.
- A coleta pública pode ser feita pela tela própria do app em `?respond=TOKEN`, com validação de campanha/token no servidor.
- Comentários abertos não devem ser liberados automaticamente.
- O PIN do painel do cliente é salvo como hash em `campaigns.access_token_hash`; o token público fica em `campaigns.code`.
- O bucket `reports` deve permanecer privado.

## 6. Verificação

Rode:

```bash
python scripts/check_supabase_connection.py
```

O script consulta `questionnaires`, `domains` e `questions`, imprime somente status/contagens e valida a presença de 56 itens fechados e 4 perguntas abertas.

## 7. Mapeamento implementado

- `companies`: cadastro/listagem de empresas.
- `campaigns`: criação/listagem/alteração de ciclos, status, pagamento, validade e PIN hash.
- `company_areas` e `campaign_sectors`: cadastro área → grupo e snapshot imutável da estrutura de cada ciclo.
- `questionnaires`, `domains`, `questions`: leitura do questionário ativo V2.
- `responses`, `response_items`, `open_answers`: coleta própria Streamlit.
- `responses`: registra também grupo canônico, versão do aviso e momento do aceite; consentimento ausente nunca é tratado como verdadeiro.
- `reports`: registro do ZIP final, SHA-256, escopo e metadados.
- `alerts`: alertas sentinela agregados na geração do relatório.
- `audit_logs`: eventos administrativos e de acesso.
- `organizational_metrics`: métodos de repositório disponíveis para leitura/gravação.

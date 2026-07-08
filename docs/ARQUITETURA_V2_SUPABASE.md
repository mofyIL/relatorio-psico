# Arquitetura V2 — Supabase Conectado

## Objetivo

Usar Supabase/Postgres como backend principal da V2, mantendo Google Sheets/Drive como fallback legado durante a transição.

## Estado atual do pacote

- O app Streamlit continua funcional com Sheets/Drive quando `backend_provider = "sheets"`.
- O instrumento e o relatório foram ampliados para a V2.
- O projeto contém migrations Supabase, seed do questionário, camada de configuração e repositório Supabase.
- Com `backend_provider = "supabase"`, o app lista/cria empresas e campanhas, lê o questionário V2, coleta respostas, registra relatórios, salva ZIP no Storage, grava alertas e auditoria.

## Arquitetura alvo

```text
Streamlit App
  ├── Autenticação / sessão
  ├── Painel admin
  ├── Painel cliente
  ├── Coleta própria Streamlit ou formulário legado
  ├── Motor analítico/reporting.py
  └── SupabaseRepository
        ├── Supabase Auth
        ├── Postgres + RLS
        ├── Storage para relatórios
        └── audit_logs
```

## Tabelas principais

- `profiles`: usuários internos e clientes.
- `companies`: empresas clientes.
- `company_members`: vínculo usuário-empresa.
- `questionnaires`, `domains`, `questions`: versionamento do instrumento.
- `campaigns`: ciclos/pesquisas.
- `campaign_sectors`: setores esperados e headcount por setor.
- `responses`, `response_items`, `open_answers`: respostas fechadas e abertas.
- `organizational_metrics`: absenteísmo, turnover, acidentes, afastamentos etc.
- `reports`: arquivos gerados e integridade SHA-256.
- `alerts`: sinais críticos e alertas técnicos.
- `action_plans`, `action_items`: plano de ação pós-devolutiva.
- `audit_logs`: trilha de auditoria.

## Segurança alvo

- Supabase Auth para usuários.
- RLS ativado em todas as tabelas expostas.
- `service_role_key` apenas no servidor Streamlit.
- Nenhuma chave real no repositório.
- Relatórios em bucket privado.
- Comentários abertos revisados antes de qualquer uso em relatório.
- Logs para pagamento, geração, reabertura, alteração de status e download.

## Estratégia de migração

1. Criar projeto Supabase.
2. Rodar `supabase/migrations/001_initial_schema.sql`.
3. Rodar `supabase/migrations/002_rls_policies.sql`.
4. Rodar `supabase/seed_questionnaire_v2.sql`.
5. Criar bucket privado `reports`.
6. Configurar `.streamlit/secrets.toml`.
7. Migrar cadastros de empresas e ciclos.
8. Usar `SupabaseRepository` como backend principal do `app.py`.
9. Usar coleta própria dentro do app em `?respond=TOKEN`.
10. Desativar Sheets como banco quando a operação real estiver validada.

## Decisão importante

Enquanto o Supabase não estiver configurado, o backend padrão permanece `sheets`. Para ativar a V2 de banco, use:

```toml
[app]
backend_provider = "supabase"
```

A ativação sem chaves exibirá erro de configuração, o que é esperado. A service role deve permanecer restrita ao servidor Streamlit.

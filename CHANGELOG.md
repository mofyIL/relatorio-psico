
## 4.1-v2-supabase-connected — 2026-07-08

- Supabase passou a ser backend funcional quando `backend_provider = "supabase"`.
- Completo `supabase_repository.py` para empresas, campanhas, questionário, respostas, relatórios, Storage, alertas, métricas organizacionais e auditoria.
- `app.py` agora usa Supabase para listar/criar empresas e campanhas, coletar respostas em tela própria, gerar relatórios a partir do banco e salvar ZIP no bucket privado `reports`.
- Adicionado formulário de resposta anônima via `?respond=TOKEN`, sem exigir identificação pessoal.
- Adicionado `scripts/check_supabase_connection.py` para validar conexão e seed V2 sem imprimir chaves.
- Adicionado `.streamlit/secrets.toml.example` sem credenciais reais.
- Atualizados README, SETUP e docs Supabase/arquitetura.
- Adicionados testes para formato do questionário V2, confidencialidade mínima e alertas críticos sentinela.

## 4.0-v2-supabase-ready — 2026-07-08

- Preparação da V2 com Supabase/Postgres.
- Adicionados `supabase/migrations/001_initial_schema.sql` e `002_rls_policies.sql`.
- Adicionado `supabase/seed_questionnaire_v2.sql`.
- Adicionado `questionnaire_v2.py` com instrumento proprietário de 56 itens e 4 perguntas abertas.
- Atualizado `reporting.py` para usar a V2, calcular mediana, desvio padrão e percentual de alta exposição.
- Adicionados alertas críticos sentinela para revisão técnica.
- Mínimo de confidencialidade padrão alterado para 7 respondentes por grupo.
- Adicionados documentos de metodologia, arquitetura, configuração Supabase e processo com o psicólogo parceiro.
- Adicionada camada inicial `database.py` e `supabase_repository.py`.

# Changelog

## 3.1 - Revisão comercial MVP

- Limpeza do pacote final.
- `.gitignore` ampliado.
- Secrets reais removidos e `secrets.toml.example` criado.
- Hash HMAC + salt para PIN e senha administrativa.
- Script `scripts/hash_secret.py`.
- Bloqueio temporário de tentativas inválidas na sessão.
- Aba `Auditoria` e eventos básicos.
- Campo `ZIP_SHA256` em ciclo/relatórios.
- Validação dos 28 itens antes da geração.
- Deduplicação simples de respostas.
- Escopo Drive reduzido para `drive.file`.
- Relatório DOCX com plano de ação inicial e roteiro de devolutiva.
- Testes mínimos de pontuação, distribuição e geração.
- Modelos de contrato, privacidade, checklist comercial e pós-entrega.

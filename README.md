# Plataforma de Triagem e Monitoramento Psicossocial — V2 Supabase

Esta versão usa Supabase/Postgres como backend principal quando `backend_provider = "supabase"` está configurado. O fluxo antigo com Google Sheets/Drive permanece como fallback operacional para migração gradual.

## Principais mudanças da V2

- Instrumento proprietário ampliado para 56 itens fechados e 4 perguntas abertas.
- Domínios inspirados em referências reconhecidas, sem copiar instrumentos validados.
- Indicadores com média, mediana, desvio padrão e percentual de alta exposição.
- Alertas críticos para assédio, violência psicológica, medo de retaliação e sofrimento intenso, sempre como sinais para revisão técnica.
- Confidencialidade padrão elevada para mínimo de 7 respondentes por grupo.
- Supabase conectado para empresas, campanhas, questionário, respostas, relatórios, alertas e auditoria.
- Coleta própria em Streamlit por link `?respond=...`, salvando em `responses`, `response_items` e `open_answers`.
- Aviso aos participantes em etapa separada: nenhuma pergunta aparece antes do aceite e a recusa não registra resposta.
- Áreas predefinidas por campanha, mapeadas para grupos canônicos (por exemplo, Vendas e RH → Administrativo).
- Campo simples `Cargo ou função atual (opcional)`, sem influência no agrupamento dos relatórios.
- ZIP final salvo no bucket privado `reports`, com hash SHA-256 e metadados registrados.
- Processo de devolutiva técnica com o psicólogo parceiro documentado.

## Como usar agora

1. Para usar Supabase, configure `.streamlit/secrets.toml` com `[app] backend_provider = "supabase"`.
2. Rode `python scripts/check_supabase_connection.py` para validar o questionário V2 no banco.
3. Abra `streamlit run app.py` e acesse `?admin=1` para cadastrar empresas e campanhas.
4. Para manter o piloto antigo, use `backend_provider = "sheets"` e os secrets do Google.
5. Para revisar metodologia com Pierre, leia `docs/METODOLOGIA_V2.md` e `docs/QUESTIONARIO_V2.md`.

---

# Painel comercial de indicadores psicossociais

Aplicativo Streamlit para operar ciclos de pesquisa psicossocial em empresas, com coleta própria ou Google Forms legado, controle comercial por ciclo, geração de relatórios coletivos em DOCX, pacote ZIP armazenado no Supabase Storage ou Google Drive legado, supressão de recortes pequenos e trilha de auditoria.

## O que esta versão entrega

- Link único por ciclo e PIN separado.
- PIN e senha administrativa com hash HMAC + salt, usando `app.credential_pepper`.
- Bloqueio temporário de tentativas repetidas de PIN/senha na sessão.
- Abas administrativas para empresas, ciclos, relatórios e auditoria.
- Conferência de pagamento, limite contratado, excesso de respostas e validade de acesso.
- Validação automática da presença dos 56 itens fechados do instrumento V2 antes da geração.
- Deduplicação simples de respostas por código/e-mail quando esses campos existirem.
- Filtro de respostas por `CICLO_ID`, com compatibilidade para respostas antigas por empresa + janela de datas.
- Relatórios coletivos com visão geral, recortes setoriais elegíveis e supressão de grupos menores que o mínimo configurado.
- Plano de ação inicial e roteiro de devolutiva pós-entrega no DOCX.
- Manifesto JSON dentro do ZIP e hash SHA-256 registrado no backend.
- Modelos de documentos para LGPD, contrato, checklist comercial e pós-entrega.

## Posicionamento correto do produto

Venda como ferramenta de **escuta estruturada, triagem coletiva e apoio ao gerenciamento de riscos psicossociais**. Não venda como diagnóstico clínico, laudo pericial, prova isolada de conformidade normativa ou substituto de avaliação técnica.

O serviço pós-entrega com psicólogo parceiro é parte essencial do produto: interpretar resultados, cruzar evidências, conduzir devolutiva, priorizar riscos e transformar o relatório em plano de ação.

## Estrutura

```text
app.py                         # Aplicativo Streamlit
reporting.py                   # Pontuação e geração DOCX
database.py                    # Configuração do backend
supabase_repository.py         # Repositório Supabase/Postgres/Storage
requirements.txt               # Dependências
.streamlit/secrets.toml.example# Modelo de secrets; não contém credenciais reais
scripts/hash_secret.py         # Gera hash de senha administrativa
scripts/check_supabase_connection.py # Valida conexão e seed do questionário
tests/                         # Testes mínimos da pontuação e geração
supabase/                      # Migrations e seed V2
docs/                          # Modelos operacionais, LGPD e comercial
```

## Começo rápido local

```bash
python -m venv .venv
source .venv/bin/activate  # Windows: .venv\\Scripts\\activate
pip install -r requirements.txt
cp .streamlit/secrets.toml.example .streamlit/secrets.toml
python scripts/hash_secret.py --context ADMIN --secret 'SENHA_FORTE' --pepper 'PEPPER_LONGO'
python scripts/check_supabase_connection.py
streamlit run app.py
```

Preencha os Secrets antes de abrir o app. O arquivo `.streamlit/secrets.toml` nunca deve ir para o Git.

## Testes

```bash
pytest -q
python -m py_compile app.py reporting.py questionnaire_v2.py database.py supabase_repository.py scripts/check_supabase_connection.py
```

## Documentos importantes

Leia antes de vender ou publicar:

- `SETUP.md`
- `SECURITY.md`
- `DECISOES_E_LIMITES.md`
- `AVISO_AOS_PARTICIPANTES.md`
- `docs/CHECKLIST_COMERCIAL.md`
- `docs/PROCESSO_POS_ENTREGA.md`
- `docs/MODELO_CONTRATO_SERVICO.md`
- `docs/MODELO_POLITICA_PRIVACIDADE.md`

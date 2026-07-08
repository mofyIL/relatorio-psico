# Plano de migração para escala

## Quando migrar

Considere sair de Google Sheets/Forms quando houver qualquer um dos sinais:

- mais de 10 clientes ativos simultâneos;
- necessidade de login individual por usuário;
- exigência contratual de auditoria forte;
- volume alto de respostas;
- necessidade de excluir/anonimizar dados de forma rastreável;
- necessidade de convites individuais sem expor campos manipuláveis.

## Arquitetura recomendada

- Frontend/app: Streamlit, Next.js ou app interno.
- Banco: PostgreSQL/Supabase/Cloud SQL.
- Autenticação: Google/Microsoft OAuth com MFA e RBAC.
- Storage: bucket privado com URLs temporárias.
- Logs: tabela imutável ou serviço dedicado.
- Coleta: formulário próprio com token por respondente ou link por empresa com validação server-side.

## Prioridades técnicas

1. Login individual para admin e cliente.
2. Banco transacional.
3. Registro de auditoria por usuário.
4. Política automática de retenção.
5. Exportação PDF assinada/hash.
6. Painel de plano de ação com status.

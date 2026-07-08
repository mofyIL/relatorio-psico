# Segurança operacional

## O que foi reforçado nesta versão

- `.gitignore` ampliado para evitar secrets, ambientes virtuais e arquivos gerados.
- Remoção de `.git`, `.venv`, `.venv-oauth`, backups e caches do pacote final.
- PIN dos ciclos com hash HMAC-SHA256, salt e `credential_pepper`.
- Senha administrativa com `admin_password_hash` e script gerador.
- Bloqueio temporário por tentativas repetidas de PIN/senha na sessão.
- Auditoria de eventos comerciais, acesso, coleta e geração.
- Hash SHA-256 do ZIP final registrado no backend.
- Supabase Storage privado para pacotes finais quando o backend Supabase está ativo.
- Escopo OAuth do Drive reduzido para `drive.file`.

## Controles obrigatórios antes de vender

- Use senha administrativa única, forte e não reutilizada.
- Envie link e PIN por canais diferentes.
- Restrinja acesso à planilha e pasta Drive a vocês dois.
- Ative 2FA nas contas Google envolvidas.
- Não colete nome, CPF ou e-mail dos participantes salvo necessidade justificada.
- Não compartilhe resposta bruta com a empresa cliente.
- Mantenha `supabase.service_role_key` somente no servidor Streamlit; nunca use essa chave no navegador, em link público ou em código enviado ao cliente.
- Mantenha o bucket `reports` privado.
- Não publique `.streamlit/secrets.toml`.
- Faça backup controlado da planilha e da pasta de relatórios.

## Próxima etapa para escala

Para mais clientes, substitua a senha compartilhada por autenticação individual, de preferência Google/Microsoft OAuth com lista de e-mails autorizados, MFA na conta e logs por usuário.

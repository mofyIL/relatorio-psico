# Instalação e migração

## 1. Substitua os arquivos do projeto

Copie para o repositório:

- `app.py`
- `reporting.py`
- `requirements.txt`
- `.gitignore`
- `.streamlit/secrets.toml.example` apenas como referência

Não envie `.streamlit/secrets.toml` nem `credentials.json` ao GitHub.

## 2. APIs e permissões

No Google Cloud do projeto da conta de serviço, habilite:

- Google Sheets API
- Google Drive API

Compartilhe com o e-mail da conta de serviço, como Editor:

- a planilha de respostas;
- a pasta do Drive onde os ZIPs serão armazenados.

O aplicativo precisa de escrita na planilha para registrar status, geração e arquivos.

## 3. Configure os Secrets no Streamlit

No Streamlit Community Cloud, abra **App settings → Secrets** e use como base `.streamlit/secrets.toml.example`.

Parâmetros importantes:

- `google_forms.spreadsheet_id`: ID da planilha;
- `google_forms.base_url`: URL normal do Forms, sem valores pré-preenchidos;
- `google_forms.entry_company`: atualmente `327839909`;
- `drive.folder_id`: pasta do Drive;
- `app.base_url`: URL publicada do app;
- `app.admin_password`: senha forte para o painel administrativo;
- `app.min_group_size`: recomendado `5`.

## 4. Inicialize as abas administrativas

Depois do deploy, abra:

```text
https://SEU-APP.streamlit.app/?admin=1
```

Ao entrar, o aplicativo cria ou confere estas abas. Se a sua aba `Empresas` já existir, as colunas antigas são preservadas e as novas são acrescentadas; linhas com `NOME` recebem um `EMPRESA_ID` automaticamente:

- `Empresas`
- `Ciclos`
- `Relatorios`

A aba `Respostas` continua sendo alimentada pelo Google Forms.

## 5. Melhore o Forms para vários ciclos

O filtro atual aceita, nesta ordem:

1. `CICLO_ID`;
2. `EMPRESA_ID`;
3. `NOME DA EMPRESA` + intervalo de datas.

Para reduzir erros, crie no Forms duas perguntas de resposta curta:

- `EMPRESA_ID`
- `CICLO_ID`

Use **Obter link pré-preenchido** para descobrir os números `entry.XXXX`. Depois coloque os IDs nos Secrets:

```toml
entry_company_id = "ID_DO_CAMPO_EMPRESA_ID"
entry_cycle_id = "ID_DO_CAMPO_CICLO_ID"
```

O Google Forms não torna esses campos realmente ocultos ou imutáveis. A validação final continua sendo feita no app por empresa, ciclo e período.

## 6. Fluxo operacional recomendado

### Venda

Cadastre o número de funcionários contratado e o preço unitário. A compra inclui todos os relatórios coletivos daquele ciclo.

### Coleta

O cliente recebe:

- link do painel;
- PIN por canal separado;
- link do Forms disponível dentro do painel.

### Encerramento

O cliente clica em **Solicitar encerramento e conferência**. Esse momento congela as respostas incluídas.

### Liberação

No administrativo:

1. confira respostas e limite contratado;
2. ajuste eventual excedente;
3. confirme pagamento;
4. libere a geração.

### Geração

O cliente gera uma edição definitiva. O ZIP contém:

- visão geral da empresa;
- um relatório para cada setor com pelo menos o mínimo configurado;
- manifesto da geração.

O ZIP é salvo no Google Drive. Durante os 90 dias, o cliente pode baixar novamente sem recalcular.

## 7. Git

Dentro do repositório:

```bash
git checkout feature/filtro-por-token
cp /CAMINHO/DO/PACOTE/app.py ./app.py
cp /CAMINHO/DO/PACOTE/reporting.py ./reporting.py
cp /CAMINHO/DO/PACOTE/requirements.txt ./requirements.txt
cp /CAMINHO/DO/PACOTE/.gitignore ./.gitignore

git status
git add app.py reporting.py requirements.txt .gitignore
git commit -m "Add client cycles, one-time reports and privacy controls"
git push -u origin feature/filtro-por-token
```

No Streamlit Community Cloud, altere a branch do app para testar a feature antes de fazer merge na `main`.

## 8. Limitações que permanecem

- O painel administrativo usa senha compartilhada. Para crescer, substitua por login Google/Microsoft e lista de e-mails autorizados.
- O aplicativo não exclui automaticamente arquivos antigos; a política de retenção deve ser definida contratualmente.
- O relatório é um indicador coletivo e descritivo. Questionário isolado não encerra o processo técnico de gerenciamento de riscos.
- Relatórios individuais foram removidos do fluxo empresarial. Uma futura entrega individual deve ser feita diretamente ao trabalhador, com autenticação própria e política de privacidade específica.

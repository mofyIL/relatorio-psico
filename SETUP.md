# Instalação, configuração e operação

## 1. Arquivos e deploy

Publique o repositório com, no mínimo:

- `app.py`;
- `reporting.py`;
- `requirements.txt`;
- `.gitignore`.

Não envie `.streamlit/secrets.toml`, credenciais OAuth, chave privada da conta de serviço ou qualquer outro segredo ao GitHub.

## 2. APIs e permissões do Google

No projeto do Google Cloud:

1. habilite a Google Sheets API e a Google Drive API;
2. crie uma conta de serviço para acesso à planilha;
3. compartilhe a planilha com o e-mail da conta de serviço, como Editor;
4. configure credenciais OAuth com acesso ao Google Drive para armazenar e baixar os ZIPs dos relatórios.

A implementação atual usa a conta de serviço para o Google Sheets e OAuth de usuário para o Google Drive.

## 3. Secrets do Streamlit

No Streamlit Community Cloud, abra **App settings → Secrets**. A estrutura mínima segue este modelo, com valores ilustrativos:

```toml
[gcp_service_account]
type = "service_account"
project_id = "..."
private_key_id = "..."
private_key = "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n"
client_email = "..."
client_id = "..."
auth_uri = "https://accounts.google.com/o/oauth2/auth"
token_uri = "https://oauth2.googleapis.com/token"
auth_provider_x509_cert_url = "https://www.googleapis.com/oauth2/v1/certs"
client_x509_cert_url = "..."

[google_forms]
spreadsheet_id = "ID_DA_PLANILHA"

[google_drive_oauth]
client_id = "..."
client_secret = "..."
refresh_token = "..."
token_uri = "https://oauth2.googleapis.com/token"

[drive]
folder_id = "ID_DA_PASTA"

[app]
base_url = "https://SEU-APP.streamlit.app/"
admin_password = "SENHA_FORTE"
min_group_size = 5
report_version = "2.0"
operator_name = "NOME OU RAZAO SOCIAL DO PRESTADOR"
privacy_contact = "privacidade@exemplo.com"
retention_policy = "PRAZO E CRITERIO DEFINIDOS EM CONTRATO"
```

Observações importantes:

- `google_forms.spreadsheet_id` é o ID da planilha usada pelo aplicativo. O nome `google_forms` foi mantido somente por compatibilidade com o secret existente;
- `google_forms.base_url`, `google_forms.entry_company`, `entry_company_id`, `entry_cycle_id` e demais IDs `entry.XXXX` não são usados e devem ser removidos;
- `app.base_url` continua sendo usado para montar os links do painel e do formulário nativo do Streamlit; ele não é uma URL do Google Forms;
- `app.min_group_size`, `operator_name`, `privacy_contact` e `retention_policy` fornecem valores iniciais na criação do ciclo. O administrador pode revisá-los antes de salvar;
- `drive.folder_id` direciona os ZIPs para uma pasta específica. Sem ele, o upload ocorre na raiz acessível pelas credenciais OAuth;
- a configuração `[pix]` é opcional e pode ser mantida se o fluxo comercial usar pagamento via Pix.

## 4. Inicialização da planilha

Depois do deploy, abra:

```text
https://SEU-APP.streamlit.app/?admin=1
```

Ao autenticar, o aplicativo cria ou confere as abas administrativas:

- `Empresas`: cadastro das organizações;
- `Ciclos`: configuração, aviso, mínimo e estado de cada coleta;
- `Relatorios`: arquivos gerados;
- `Estrutura`: cadastro atual de áreas e grupos de análise por empresa;
- `EstruturaCiclos`: cópia congelada da estrutura usada em cada ciclo.

A aba `Respostas` é criada ou ampliada automaticamente na inicialização administrativa. O aplicativo preserva colunas antigas e acrescenta as colunas atuais sem duplicar cabeçalhos equivalentes.

## 5. Cadastre a empresa e sua estrutura

Na aba **Nova empresa**, informe os dados da organização e uma linha por área no formato:

```text
Área de trabalho | Grupo de análise
```

Exemplo:

```text
Vendas | Administrativo
Recursos Humanos | Administrativo
Financeiro | Administrativo
Produção | Operacional
Manutenção | Operacional
```

A área é a opção que o participante verá. O grupo de análise é a unidade usada para contagem, supressão por confidencialidade e relatório coletivo. Sem o caractere `|`, o mesmo texto é usado nos dois níveis.

Use a aba **Estrutura** para acrescentar áreas ou ativar e desativar mapeamentos. Uma mesma área ativa não pode apontar para dois grupos ao mesmo tempo.

O campo **Cargo ou função atual** aparece no formulário como texto livre opcional. Ele serve apenas como informação complementar da resposta e não define grupos nem gera relatórios por cargo. Exemplos como “Vendedor” e “Analista de RH” continuam agrupados conforme a área selecionada e o mapeamento definido previamente.

## 6. Crie o ciclo e congele as regras

Na aba **Novo ciclo**:

1. selecione a empresa;
2. confira as áreas ativas e os grupos correspondentes;
3. defina dados comerciais, validade e mínimo de respostas por grupo;
4. complete o aviso com controlador, operador/prestador, contato de privacidade e prazo/critério de retenção;
5. crie o ciclo e guarde o PIN exibido.

Ao criar o ciclo, o aplicativo:

- copia as áreas e os grupos ativos de `Estrutura` para `EstruturaCiclos`;
- grava o mínimo em `Ciclos.MIN_GRUPO`;
- grava a versão e os quatro campos do aviso em `Ciclos`;
- associa a versão a um template imutável do texto do aviso;
- gera um token privado para o painel da empresa e outro token, independente, para o link anônimo dos participantes.

Esses dados ficam congelados para a coleta. Alterações posteriores em **Estrutura** valem apenas para ciclos futuros e não mudam as opções ou os agrupamentos de um ciclo já criado.

## 7. Distribua os acessos corretos

Envie ao responsável da empresa:

- o link do painel;
- o PIN por um canal separado.

Envie aos trabalhadores somente o **link anônimo para os participantes**. Não há link de Google Forms e não é necessário criar perguntas `EMPRESA_ID`, `CICLO_ID` ou links pré-preenchidos.

O link anônimo só aceita respostas enquanto o ciclo estiver em `COLETA`, dentro da validade e com aviso e estrutura completos.
Ele não revela o token do painel da empresa e pode ser revogado e recriado em **Gerenciar ciclo**.

## 8. Fluxo do participante em duas etapas

Na primeira etapa, o aplicativo apresenta o aviso do ciclo, incluindo o mínimo de confidencialidade, controlador, operador, contato, retenção e versão. A pessoa deve escolher explicitamente uma das opções:

- **Li as informações e desejo participar**; ou
- **Não desejo participar**.

Somente a decisão afirmativa libera a segunda etapa. Se a pessoa não desejar participar, nenhuma resposta ao questionário é coletada.

Na segunda etapa, a pessoa:

1. seleciona uma das áreas congeladas para o ciclo;
2. pode informar cargo ou função atual, opcionalmente;
3. responde todos os itens;
4. envia a resposta.

A área selecionada é convertida no grupo canônico e não é persistida na linha individual. A linha gravada em `Respostas` contém o grupo, `CIENCIA_AVISO = SIM`, `AVISO_VERSAO` e `CIENCIA_AVISO_EM`. Na apuração, apenas respostas com ciência afirmativa e versão igual à versão do aviso daquele ciclo são consideradas. Respostas antigas, incompletas ou incompatíveis ficam fora da contagem e dos relatórios.

## 9. Encerramento, liberação e geração

1. O cliente solicita **encerramento e conferência** no painel. Esse momento congela o horário final das respostas incluídas.
2. No administrativo, confira respostas válidas, limite contratado e eventual excedente.
3. Confirme o pagamento e libere a geração.
4. O cliente gera uma edição definitiva.

O ZIP contém:

- visão geral da empresa;
- relatórios dos grupos elegíveis depois do limite mínimo e da supressão complementar;
- manifesto da geração.

Grupos abaixo do mínimo participam apenas da visão geral e não são identificados pelo nome. Se apenas um grupo ficar abaixo do mínimo, o menor grupo elegível também é ocultado: isso impede reconstruir o resultado pequeno subtraindo os relatórios publicados da visão geral. O ZIP informa somente a quantidade suprimida, é salvo no Google Drive e pode ser baixado novamente durante a validade sem recálculo.

## 10. Ciclos antigos

Na aba **Gerenciar ciclo**, um ciclo de coleta anterior ao formulário nativo pode ser preparado somente se ainda não tiver respostas. O processo congela a estrutura ativa, o mínimo e o aviso completo.

Se o ciclo antigo já tiver respostas sem ciência versionada, crie um novo ciclo. Isso evita misturar respostas antigas com o fluxo que exige aceite prévio do aviso.

## 11. Limitações que permanecem

- O painel administrativo usa senha compartilhada. Para crescer, substitua por login Google/Microsoft e lista de e-mails autorizados.
- O aplicativo não exclui automaticamente arquivos ou respostas antigos; a política informada no aviso deve ser executada por processo operacional compatível com o contrato.
- O relatório é coletivo e descritivo. O questionário isolado não encerra o processo técnico de gerenciamento de riscos.
- Não são entregues relatórios individuais à empresa. Uma futura entrega individual exigiria canal autenticado próprio e política de privacidade específica.

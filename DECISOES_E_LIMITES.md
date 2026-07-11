# Decisões da versão comercial 2.0

## Modelo de venda

- A unidade comercial é a quantidade de funcionários contratada para o ciclo.
- A compra inclui o relatório geral da empresa e os relatórios de todos os grupos de análise elegíveis.
- Respostas válidas acima do número contratado bloqueiam a liberação até ajuste comercial.
- A geração é definitiva por ciclo; o mesmo pacote pode ser baixado novamente.
- Uma nova edição ou recálculo exige liberação administrativa e pode representar nova cobrança.

## Fluxo

1. O administrador cadastra a empresa e a relação `Área | Grupo de análise`.
2. O administrador cria o ciclo, completa o aviso aos participantes e define o mínimo de respostas por grupo.
3. O sistema congela estrutura, aviso e mínimo, e cria tokens distintos para o painel e para o link anônimo de participação.
4. O participante lê o aviso e precisa declarar afirmativamente que deseja participar antes de acessar o questionário.
5. O participante seleciona uma área predefinida, informa opcionalmente seu cargo ou função atual e responde aos itens.
6. O cliente solicita encerramento; o horário final é congelado.
7. O administrador confere a quantidade de respostas válidas e o pagamento.
8. O cliente gera uma edição definitiva.
9. O ZIP é salvo no Google Drive e permanece disponível para o administrador.
10. O cliente perde o acesso ao fim da validade configurada, sem exclusão automática do arquivo.

O formulário é nativo do Streamlit. Google Forms, links pré-preenchidos e campos `entry.XXXX` não fazem parte deste fluxo.

## Estrutura organizacional e agrupamento

Há dois níveis deliberadamente distintos:

- **Área de trabalho:** opção concreta escolhida pelo participante, como `Vendas` ou `Recursos Humanos`;
- **Grupo de análise:** unidade coletiva usada na contagem e nos relatórios, como `Administrativo`.

O cadastro `Vendas | Administrativo` e `Recursos Humanos | Administrativo` permite que as duas áreas sejam analisadas juntas. Isso evita depender de nomes livres como “Vendas”, “Comercial”, “RH” ou “Recursos Humanos” para formar os grupos.

A aba `Estrutura` contém o cadastro vigente da empresa. Ao criar um ciclo, o sistema copia as linhas ativas para `EstruturaCiclos`. Esse snapshot impede que mudanças futuras de nomenclatura, ativação ou agrupamento alterem retroativamente uma coleta em andamento ou já encerrada.

O campo **Cargo ou função atual** corresponde ao cargo/função informado pela pessoa, é opcional e não participa do agrupamento, do critério de elegibilidade nem da criação de relatórios. Nesta versão, “família de cargo” não é uma dimensão solicitada ao participante.

As colunas `GRUPO_ID` e `GRUPO_ANALISE` são as referências canônicas de agrupamento. A coluna `SETOR` pode ser preenchida com o grupo somente para compatibilidade com relatórios antigos.

## Ciência e versionamento do aviso

- O aviso é uma etapa separada e anterior ao questionário.
- O botão de continuar só fica disponível depois que a pessoa escolhe explicitamente participar ou não participar.
- A escolha afirmativa libera o questionário; a recusa encerra o fluxo sem coletar respostas.
- Cada resposta enviada registra `CIENCIA_AVISO = SIM`, a versão do aviso e o momento da ciência.
- A apuração aceita somente respostas cuja ciência seja afirmativa e cuja versão coincida com `AVISO_VERSAO` do ciclo.
- Respostas sem esses dados ou com versão diferente são ignoradas na contagem comercial e nos relatórios.

Cada ciclo deve guardar, antes da abertura da coleta:

- versão do aviso;
- controlador dos dados;
- operador/prestador do serviço;
- contato para dúvidas e direitos dos titulares;
- prazo e critério de retenção;
- mínimo de respostas por grupo.

Esses valores ficam congelados no ciclo para manter coerência entre a informação apresentada, a ciência registrada e o relatório produzido.

## Privacidade e confidencialidade

- O mínimo padrão é de 5 respostas por grupo, mas o valor efetivo é definido e congelado em cada ciclo, nunca abaixo de 2.
- Grupos abaixo do mínimo entram somente na visão geral e não recebem relatório separado.
- Quando apenas um grupo fica abaixo do mínimo, o menor grupo elegível também é suprimido para impedir inferência por subtração da visão geral.
- Nenhum relatório individual é entregue à empresa.
- Não são solicitados nome, CPF ou e-mail no questionário.
- O cargo ou função atual é opcional e não é usado para criar recortes menores.
- A área escolhida serve apenas para resolver o grupo e não é persistida na resposta individual; horário exato, cargo e suas combinações não aparecem nos relatórios.
- O token público dos participantes é separado do token privado do painel e pode ser revogado sem trocar o acesso do cliente.
- A retenção não é executada automaticamente: controlador e operador precisam cumprir o prazo e o critério informados no aviso e definidos contratualmente.

## Metodologia

- A escala foi reorientada para 0–100, onde valores maiores indicam maior exposição percebida.
- Itens positivos são invertidos; itens redigidos como exposição permanecem diretos.
- Os fatores foram renomeados conforme o conteúdo efetivo das perguntas.
- As faixas são descritivas e internas, não uma classificação legal autônoma.
- O relatório não é chamado de “conclusão de risco” e não promete conformidade com a NR-1 por si só.
- Antes da venda como instrumento técnico validado, a composição de 28 itens e seus pontos de corte devem ser revisados por profissional qualificado e confrontados com a fonte metodológica original.

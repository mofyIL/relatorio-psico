# Painel comercial de indicadores psicossociais

Aplicativo multiempresa em Streamlit para coleta anônima e geração de relatórios coletivos sobre condições psicossociais do trabalho.

## Principais recursos

- formulário anônimo nativo do Streamlit, sem dependência do Google Forms;
- participação em duas etapas: leitura do aviso e decisão afirmativa antes do questionário;
- registro da ciência com versão e data/hora junto da resposta enviada;
- áreas de trabalho definidas previamente e vinculadas a grupos de análise;
- estrutura e mínimo de confidencialidade congelados por ciclo;
- cargo ou função atual opcional, sem uso no agrupamento dos relatórios;
- token privado por ciclo para o painel da empresa, PIN separado e token público independente e revogável para participantes;
- validade de acesso de 90 dias por padrão;
- cobrança e limite por quantidade de funcionários;
- encerramento da coleta pelo cliente e liberação pelo administrador;
- geração definitiva única com possibilidade de baixar novamente;
- armazenamento persistente do ZIP no Google Drive;
- visão geral e relatórios por grupo de análise elegível após as regras de confidencialidade e supressão complementar;
- pontuação orientada para exposição em escala de 0 a 100;
- relatórios coletivos com layout retrato e anexo paisagem;
- nenhuma entrega individual ao empregador.

## Áreas e grupos de análise

A estrutura é cadastrada no formato `Área | Grupo de análise`. A pessoa seleciona sua área de trabalho, mas o relatório é agrupado pelo grupo definido pela organização. Por exemplo:

```text
Vendas | Administrativo
Recursos Humanos | Administrativo
Produção | Operacional
```

Assim, Vendas e Recursos Humanos compõem o mesmo grupo `Administrativo`, sem depender de texto livre digitado por cada participante. Se a organização tiver apenas um nível, uma linha como `Administrativo` usa o mesmo nome como área e grupo.

Leia [SETUP.md](SETUP.md), [DECISOES_E_LIMITES.md](DECISOES_E_LIMITES.md) e [AVISO_AOS_PARTICIPANTES.md](AVISO_AOS_PARTICIPANTES.md) antes do deploy e de cada nova coleta.

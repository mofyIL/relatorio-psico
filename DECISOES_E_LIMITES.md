# Decisões, limites e posicionamento

## Decisões de produto

- O produto entrega relatórios coletivos por empresa e por grupo de análise elegível.
- A empresa define previamente suas áreas e o grupo de análise de cada uma. A pessoa escolhe uma área da lista; não digita o setor livremente.
- Área e grupo de análise são conceitos diferentes. Por exemplo, `Vendas` e `Recursos Humanos` podem pertencer ao mesmo grupo `Administrativo` e ser consolidados no mesmo relatório.
- A estrutura é congelada por ciclo, para que mudanças futuras no cadastro da empresa não alterem respostas ou relatórios anteriores.
- Grupos abaixo do mínimo configurado são suprimidos.
- O aviso aos participantes é uma etapa anterior ao questionário. Somente o aceite afirmativo libera as perguntas; a recusa não grava resposta.
- Cada resposta aceita registra a versão do aviso e o momento da ciência.
- `Cargo ou função atual` é um campo opcional e descritivo. Ele não cria nem divide grupos de análise.
- A edição gerada é definitiva; nova geração exige ação administrativa excepcional.
- O ZIP final fica armazenado no Supabase Storage (ou no Drive legado) e recebe hash SHA-256.
- Não há relatório individual para empregador.
- O relatório inclui plano de ação inicial, mas a decisão final deve ocorrer na devolutiva técnica.

## Limites técnicos

- Google Forms e Google Sheets permanecem apenas como compatibilidade legada; a coleta própria com Supabase é o fluxo recomendado.
- Campanhas antigas sem estrutura predefinida podem usar o fallback legado até a configuração/migração dos grupos.
- A service role do Supabase deve permanecer somente no servidor.
- O bloqueio de tentativas é por sessão, não por IP/usuário persistente.

## Limites metodológicos e jurídicos

- O instrumento está em validação técnica.
- As faixas são descritivas e operacionais.
- O resultado não é diagnóstico clínico, laudo pericial, nexo causal ou conclusão automática de conformidade.
- Questionário isolado não substitui GRO/PGR, AEP quando aplicável, observação do trabalho, entrevistas, dados de SST/RH e julgamento técnico.
- A parceria com psicólogo deve ser apresentada como etapa de interpretação, devolutiva e plano de ação.

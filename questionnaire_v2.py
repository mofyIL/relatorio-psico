from __future__ import annotations

"""
Instrumento proprietário V2 para triagem e monitoramento psicossocial.

IMPORTANTE: estes itens foram redigidos de forma original para o produto. Eles se
inspiram em domínios reconhecidos na literatura e em referências de gestão de
riscos psicossociais, mas não reproduzem instrumentos validados como COPSOQ,
HSE Stress Indicator Tool ou JCQ. Antes de uso em escala, recomenda-se revisão
psicométrica, jurídica e técnica pelo psicólogo responsável.
"""

QUESTIONARIO: dict[int, str] = {
    # DEM - demandas, ritmo e carga
    1: "Tenho que trabalhar em ritmo muito intenso para dar conta das minhas tarefas.",
    2: "A quantidade de trabalho é maior do que consigo realizar com qualidade no tempo disponível.",
    3: "As metas, prazos ou cobranças do trabalho geram pressão excessiva.",
    4: "Meu trabalho exige atenção constante ou esforço mental intenso por longos períodos.",

    # CTL - controle e autonomia (protetivo)
    5: "Tenho autonomia suficiente para decidir como organizar minhas tarefas.",
    6: "Consigo influenciar decisões que afetam diretamente o meu trabalho.",
    7: "Tenho liberdade adequada para propor melhorias no modo como o trabalho é feito.",
    8: "Posso ajustar meu ritmo de trabalho quando percebo sinais de cansaço ou sobrecarga.",

    # ROL - clareza de papel e informação (protetivo)
    9: "Sei claramente o que se espera de mim no trabalho.",
    10: "Recebo as informações necessárias para realizar bem minhas atividades.",
    11: "As responsabilidades entre pessoas e áreas são bem definidas.",
    12: "Quando há mudança de prioridade, recebo orientação clara sobre o que deve ser feito.",

    # LID - liderança e apoio da chefia (protetivo)
    13: "Minha liderança imediata está disponível para orientar quando preciso.",
    14: "Minha liderança trata as pessoas com respeito e justiça.",
    15: "Minha liderança ajuda a remover obstáculos que dificultam o trabalho.",
    16: "Minha liderança reconhece esforços e contribuições da equipe.",

    # APS - apoio social e cooperação (protetivo)
    17: "Posso contar com colegas quando preciso de ajuda no trabalho.",
    18: "Na minha equipe, as pessoas cooperam para resolver problemas.",
    19: "Existe confiança suficiente para pedir ajuda sem medo de julgamento.",
    20: "Sinto que faço parte de um grupo de trabalho respeitoso.",

    # REC - reconhecimento, justiça e reciprocidade (protetivo)
    21: "O esforço realizado no meu trabalho é reconhecido de forma adequada.",
    22: "As regras, cobranças e decisões são aplicadas de forma justa.",
    23: "Tenho oportunidades compatíveis de desenvolvimento e aprendizado.",
    24: "A distribuição de tarefas é percebida como equilibrada na minha área.",

    # CON - conflitos, respeito e relações abusivas (risco)
    25: "Conflitos no trabalho costumam ficar sem tratamento adequado.",
    26: "Presencio ou vivencio comunicação agressiva, humilhações ou ironias no trabalho.",
    27: "Há competição, isolamento ou desrespeito que prejudica a convivência.",
    28: "Problemas de relacionamento no trabalho afetam meu bem-estar ou desempenho.",

    # SEG - segurança psicológica e retaliação (misto, aqui redigido como risco)
    29: "Evito falar sobre problemas do trabalho por medo de consequências negativas.",
    30: "Tenho receio de ser punido(a), prejudicado(a) ou malvisto(a) ao apontar riscos ou erros.",
    31: "Na minha área, erros são usados para culpabilizar pessoas em vez de melhorar processos.",
    32: "Sinto que opiniões divergentes não são bem recebidas no ambiente de trabalho.",

    # MUD - comunicação, mudança e participação (protetivo)
    33: "Mudanças que afetam meu trabalho são comunicadas com antecedência suficiente.",
    34: "As pessoas impactadas por mudanças têm oportunidade de participar ou opinar.",
    35: "A comunicação da empresa é coerente entre o que é dito e o que é praticado.",
    36: "Recebo retorno sobre dúvidas, solicitações ou problemas que levo à liderança.",

    # CTF - conflito trabalho-família e recuperação (risco)
    37: "O trabalho interfere negativamente na minha vida pessoal ou familiar.",
    38: "Tenho dificuldade de me desligar mentalmente do trabalho fora do expediente.",
    39: "Preciso abrir mão de descanso, alimentação ou pausas por causa das demandas do trabalho.",
    40: "Sinto que o tempo de recuperação entre jornadas é insuficiente.",

    # EXA - exaustão e sinais de desgaste (risco)
    41: "Ao final do trabalho, sinto exaustão física ou emocional intensa.",
    42: "Tenho percebido queda de energia, motivação ou concentração por causa do trabalho.",
    43: "Sinto que estou no limite para continuar mantendo o mesmo ritmo de trabalho.",
    44: "O trabalho tem contribuído para irritabilidade, ansiedade ou tensão frequente.",

    # PRE - prevenção, canais e cultura de cuidado (protetivo)
    45: "Conheço canais seguros para relatar situações de risco, conflito ou sofrimento no trabalho.",
    46: "A empresa demonstra agir quando problemas psicossociais são relatados.",
    47: "As medidas de prevenção e cuidado são comunicadas de forma clara aos trabalhadores.",
    48: "Percebo compromisso real da organização com saúde, segurança e respeito no trabalho.",

    # CRI - sinais críticos/sentinela (risco; exigem análise técnica e não diagnóstico automático)
    49: "Vivenciei ou presenciei assédio moral, constrangimento repetido ou humilhação no trabalho.",
    50: "Vivenciei ou presenciei ameaça, intimidação ou violência psicológica no trabalho.",
    51: "Vivenciei ou presenciei conduta de conotação sexual indesejada no ambiente de trabalho.",
    52: "Senti medo de retaliação ao pensar em relatar situação grave no trabalho.",
    53: "Percebo que pessoas são isoladas, ridicularizadas ou perseguidas no ambiente de trabalho.",
    54: "Há situações no trabalho que considero graves e que não são tratadas pela organização.",
    55: "O nível de cansaço ou sofrimento relacionado ao trabalho tem me preocupado seriamente.",
    56: "Já pensei em pedir desligamento ou afastamento por causa das condições psicossociais do trabalho.",
}

# Itens redigidos como exposição/risco: quanto maior a frequência, maior o escore.
ITENS_EXPOSSICAO: set[int] = {
    1, 2, 3, 4,
    25, 26, 27, 28,
    29, 30, 31, 32,
    37, 38, 39, 40,
    41, 42, 43, 44,
    49, 50, 51, 52, 53, 54, 55, 56,
}

CRITICAL_ITEMS: set[int] = {49, 50, 51, 52, 53, 54, 55, 56}

FATORES = [
    {
        "codigo": "DEM",
        "nome": "Demandas, ritmo e carga de trabalho",
        "itens": [1, 2, 3, 4],
        "descricao": "Volume, pressão temporal, metas, ritmo e exigência mental percebida.",
    },
    {
        "codigo": "CTL",
        "nome": "Controle, autonomia e participação na tarefa",
        "itens": [5, 6, 7, 8],
        "descricao": "Margem de decisão, influência sobre o próprio trabalho e possibilidade de ajuste do ritmo.",
    },
    {
        "codigo": "ROL",
        "nome": "Clareza de papel e qualidade da informação",
        "itens": [9, 10, 11, 12],
        "descricao": "Clareza de expectativas, responsabilidades, prioridades e informações para executar o trabalho.",
    },
    {
        "codigo": "LID",
        "nome": "Liderança, justiça e suporte da chefia",
        "itens": [13, 14, 15, 16],
        "descricao": "Disponibilidade, respeito, orientação, justiça e reconhecimento pela liderança imediata.",
    },
    {
        "codigo": "APS",
        "nome": "Apoio social, cooperação e pertencimento",
        "itens": [17, 18, 19, 20],
        "descricao": "Ajuda entre colegas, cooperação, confiança e sentimento de pertencimento ao grupo.",
    },
    {
        "codigo": "REC",
        "nome": "Reconhecimento, justiça e desenvolvimento",
        "itens": [21, 22, 23, 24],
        "descricao": "Reciprocidade, justiça organizacional, oportunidades e equilíbrio na distribuição de tarefas.",
    },
    {
        "codigo": "CON",
        "nome": "Conflitos, respeito e relações abusivas",
        "itens": [25, 26, 27, 28],
        "descricao": "Tratamento de conflitos, comunicação agressiva, isolamento, desrespeito e impacto nas relações.",
    },
    {
        "codigo": "SEG",
        "nome": "Segurança psicológica e medo de retaliação",
        "itens": [29, 30, 31, 32],
        "descricao": "Liberdade para falar de problemas, erros e riscos sem medo de punição ou julgamento.",
    },
    {
        "codigo": "MUD",
        "nome": "Comunicação de mudanças e participação",
        "itens": [33, 34, 35, 36],
        "descricao": "Antecedência, coerência, participação e retorno sobre mudanças ou problemas comunicados.",
    },
    {
        "codigo": "CTF",
        "nome": "Conflito trabalho-vida pessoal e recuperação",
        "itens": [37, 38, 39, 40],
        "descricao": "Interferência do trabalho na vida pessoal, desligamento mental, pausas e recuperação entre jornadas.",
    },
    {
        "codigo": "EXA",
        "nome": "Exaustão e sinais de desgaste",
        "itens": [41, 42, 43, 44],
        "descricao": "Exaustão, queda de energia, sensação de limite, irritabilidade, ansiedade ou tensão associada ao trabalho.",
    },
    {
        "codigo": "PRE",
        "nome": "Prevenção, canais e cultura de cuidado",
        "itens": [45, 46, 47, 48],
        "descricao": "Conhecimento de canais, resposta organizacional, comunicação preventiva e compromisso com cuidado.",
    },
    {
        "codigo": "CRI",
        "nome": "Sinais críticos e eventos sentinela",
        "itens": [49, 50, 51, 52, 53, 54, 55, 56],
        "descricao": "Sinais que exigem análise técnica, acolhimento, apuração adequada e medidas preventivas proporcionais.",
    },
]

ACTION_GUIDES = {
    "DEM": {
        "evidence": "sobrecarga, ritmo, pressão por metas/prazos e exigência mental",
        "actions": [
            "revisar dimensionamento, prazos, metas e critérios de prioridade",
            "mapear gargalos e tarefas com maior pressão temporal",
            "avaliar pausas, redistribuição de carga e medidas de organização do trabalho",
        ],
        "indicator": "horas extras; backlog; absenteísmo; evolução do escore no próximo ciclo",
    },
    "CTL": {
        "evidence": "autonomia, influência sobre a tarefa, participação e possibilidade de ajuste do ritmo",
        "actions": [
            "ampliar participação dos trabalhadores em decisões sobre o modo de executar o trabalho",
            "definir margens claras de autonomia por função e processo",
            "criar rotina de escuta para melhorias operacionais",
        ],
        "indicator": "número de melhorias implementadas; percepção de autonomia; retrabalho",
    },
    "ROL": {
        "evidence": "clareza de expectativas, responsabilidades, prioridades e fluxo de informação",
        "actions": [
            "revisar descrição de papéis e acordos de interface entre áreas",
            "padronizar comunicação de prioridades e mudanças de demanda",
            "criar canal de esclarecimento para dúvidas recorrentes",
        ],
        "indicator": "dúvidas recorrentes; erros por falha de informação; escore no próximo ciclo",
    },
    "LID": {
        "evidence": "disponibilidade, justiça, orientação, respeito e reconhecimento pela liderança",
        "actions": [
            "realizar devolutiva com lideranças sobre padrões de suporte e respeito",
            "treinar liderança em gestão de conflitos, comunicação e prevenção psicossocial",
            "instituir rituais simples de acompanhamento, reconhecimento e remoção de obstáculos",
        ],
        "indicator": "adesão de líderes às rotinas; queixas recorrentes; evolução setorial",
    },
    "APS": {
        "evidence": "apoio entre colegas, cooperação, confiança e pertencimento",
        "actions": [
            "qualificar causas de baixa cooperação ou isolamento entre equipes",
            "fortalecer rotinas de trabalho conjunto e troca de conhecimento",
            "combinar regras de convivência e resolução de conflitos",
        ],
        "indicator": "incidentes relacionais; colaboração interáreas; percepção de apoio social",
    },
    "REC": {
        "evidence": "reconhecimento, justiça, oportunidades e equilíbrio de tarefas",
        "actions": [
            "revisar critérios de distribuição de tarefas, oportunidades e reconhecimento",
            "documentar decisões que impactam pessoas e equipes",
            "criar práticas simples de feedback e reconhecimento não financeiro",
        ],
        "indicator": "percepção de justiça; turnover; pedidos de mudança de área",
    },
    "CON": {
        "evidence": "conflitos não tratados, comunicação agressiva, isolamento e desrespeito",
        "actions": [
            "instituir procedimento claro para acolhimento e tratamento de conflitos",
            "realizar escuta qualificada com proteção contra retaliação",
            "definir medidas educativas e corretivas proporcionais quando houver condutas inadequadas",
        ],
        "indicator": "registros de conflito; reincidência; tempo de tratamento de relatos",
    },
    "SEG": {
        "evidence": "medo de falar, receio de punição, culpabilização e baixa segurança psicológica",
        "actions": [
            "proteger canais de relato e comunicar regras de não retaliação",
            "revisar práticas de tratamento de erros para foco em processo, não culpabilização automática",
            "realizar devolutiva com lideranças sobre segurança psicológica",
        ],
        "indicator": "uso de canais; relatos de retaliação; percepção de segurança psicológica",
    },
    "MUD": {
        "evidence": "comunicação de mudanças, participação, coerência e retorno às demandas",
        "actions": [
            "planejar comunicação de mudanças com antecedência e público impactado",
            "criar momentos de escuta antes e depois de mudanças relevantes",
            "registrar dúvidas e respostas sobre decisões organizacionais",
        ],
        "indicator": "aderência a cronogramas; dúvidas abertas; satisfação com comunicação",
    },
    "CTF": {
        "evidence": "interferência na vida pessoal, dificuldade de desligamento, pausas e recuperação",
        "actions": [
            "avaliar jornada real, pausas, disponibilidade fora do expediente e urgências recorrentes",
            "pactuar limites de comunicação e demandas fora do horário",
            "revisar organização do trabalho para favorecer recuperação entre jornadas",
        ],
        "indicator": "horas extras; contatos fora do expediente; afastamentos e fadiga percebida",
    },
    "EXA": {
        "evidence": "exaustão, queda de energia, sensação de limite, tensão e ansiedade associadas ao trabalho",
        "actions": [
            "priorizar análise técnica do trabalho real nos grupos com maior escore",
            "avaliar medidas imediatas de alívio de carga e suporte às equipes",
            "acompanhar sinais de agravamento e articular cuidado quando necessário",
        ],
        "indicator": "absenteísmo; afastamentos; horas extras; evolução de exaustão no próximo ciclo",
    },
    "PRE": {
        "evidence": "canais de relato, resposta organizacional, medidas preventivas e compromisso percebido",
        "actions": [
            "comunicar canais, fluxos de acolhimento e responsáveis de forma simples",
            "acompanhar tempo de resposta aos relatos e problemas comunicados",
            "registrar medidas preventivas no plano de ação e revisar efetividade",
        ],
        "indicator": "tempo de resposta; ações concluídas; confiança nos canais",
    },
    "CRI": {
        "evidence": "assédio, violência psicológica, medo de retaliação, situações graves e sofrimento intenso",
        "actions": [
            "realizar análise técnica e acolhimento seguro, sem expor respondentes",
            "acionar fluxo de apuração quando houver indícios de conduta grave",
            "definir medidas preventivas imediatas e proporcionais ao risco identificado",
        ],
        "indicator": "status de apuração; medidas preventivas implantadas; reincidência de alertas críticos",
    },
}

OPEN_QUESTIONS: list[dict[str, str]] = [
    {
        "codigo": "A1",
        "texto": "Quais situações do trabalho mais contribuem para estresse, desgaste ou sofrimento?",
        "uso": "análise temática agregada; não publicar respostas brutas sem revisão e anonimização",
    },
    {
        "codigo": "A2",
        "texto": "Que mudanças poderiam melhorar a organização do trabalho, a saúde e o bem-estar da equipe?",
        "uso": "subsídio para plano de ação e devolutiva técnica",
    },
    {
        "codigo": "A3",
        "texto": "Existe algum risco, conflito ou situação grave que a empresa deveria analisar com cuidado?",
        "uso": "triagem de alertas; exige revisão humana antes de qualquer comunicação ao cliente",
    },
    {
        "codigo": "A4",
        "texto": "Há alguma prática positiva que deveria ser mantida ou fortalecida?",
        "uso": "identificação de fatores protetivos e boas práticas",
    },
]

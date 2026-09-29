# Extração e Revisão de Regulamentos - Especificação

## Problem Statement

O cadastro e o controle de fundos dependem de informações presentes em regulamentos públicos, hoje sujeitas a extração manual, atraso e erro. A solução deve automatizar a leitura das tabelas e do texto corrido da seção relevante, mantendo evidência, validação independente e revisão humana para os casos incertos.

O resultado precisa ser demonstrável localmente, reproduzível nos quatro documentos fornecidos e resiliente à mudança de capítulo, página, título e redação no regulamento usado durante a apresentação.

## Goals

- [ ] Processar individualmente os quatro regulamentos fornecidos e produzir variáveis atômicas com valor e evidência.
- [ ] Localizar a seção por conteúdo mesmo quando ela aparecer como Capítulo 6 ou em páginas diferentes.
- [ ] Validar toda extração com um agente separado e encaminhar incertezas para revisão humana.
- [ ] Produzir Excel preliminar e final no formato exigido, com trilha de auditoria local.
- [ ] Demonstrar qualidade por testes offline, golden set versionado e smoke tests reais opt-in.

## Out of Scope

| Funcionalidade | Motivo |
| --- | --- |
| Banco de dados | Arquivos locais atendem ao case e reduzem complexidade operacional. |
| Deploy ou infraestrutura cloud | A execução solicitada é local. |
| Autenticação e múltiplos usuários | A demonstração tem um único operador local. |
| Processamento em lote | Um documento por execução corresponde à dinâmica da apresentação. |
| Regex ou regras determinísticas para extrair conteúdo | O case exige LLM para a extração semântica. |
| Fine-tuning de modelos | Não é necessário para quatro documentos e um documento surpresa similar. |
| RAG completo ou banco vetorial | A busca opcional opera sobre poucas variáveis já extraídas. |
| Destaque por coordenadas no PDF | Página e trecho oferecem evidência suficiente para o case. |
| Edição do trecho-fonte | A evidência precisa permanecer imutável. |

---

## Assumptions & Open Questions

| Premissa ou decisão | Padrão escolhido | Justificativa | Confirmado? |
| --- | --- | --- | --- |
| Modelo de variáveis | Híbrido, com nomes preferenciais e criação dinâmica | Equilibra comparação entre fundos e cobertura de redações novas | Sim |
| Granularidade | Uma variável por fato independente | Melhora revisão, busca e uso posterior | Sim |
| Limite de revisão | Score menor que `0,85` ou veredito diferente de suportado | Produz casos revisáveis sem tratar score como probabilidade | Sim |
| Exportação | Preliminar a qualquer momento; final somente sem pendências | Mantém transparência sem bloquear diagnóstico | Sim |
| Localização | Semântica, com capítulo opcional e correção manual de páginas | Atende ao documento surpresa e protege a demonstração | Sim |
| Busca em linguagem natural | Bônus após o núcleo P1 estar estável | Evita sacrificar confiabilidade por escopo adicional | Sim |
| Unidade de execução | Um documento e um Excel por execução | Corresponde ao fluxo da apresentação | Premissa documentada |
| Limites de entrada | PDF de até 50 MB e 200 páginas | Cobre amplamente o corpus e limita custo e memória | Premissa documentada |
| Uso de LLM externa | Permitido para documentos públicos; estado e interface permanecem locais | Viabiliza visão e saída estruturada sem infraestrutura de modelo local | Premissa documentada |
| Concorrência | Um processamento ativo por instância da interface | Evita conflitos de estado em uma aplicação local sem banco | Premissa documentada |
| Retenção | Execuções persistem localmente sem expiração automática | Facilita auditoria e repetição da demonstração | Premissa documentada |
| Segurança | Credenciais somente em variáveis de ambiente e nunca em arquivos de execução | Evita vazamento acidental de segredo | Premissa documentada |
| Confiança | Rubrica do validador, não probabilidade calibrada | Representa honestamente o significado do número | Sim |
| Modelo específico | Configurável; deve aceitar PDF/visão e saída estruturada | Evita acoplamento a uma versão e permite comparação | Premissa documentada |

**Open questions:** none - todas as decisões foram resolvidas ou registradas como premissas acima.

---

## User Stories

### P1: Iniciar uma execução e localizar a seção ⭐ MVP

**User Story:** Como operador, quero selecionar um regulamento e confirmar a seção relevante para impedir que a extração use páginas erradas.

**Why P1:** Toda extração e validação dependem de uma origem correta e auditável.

**Acceptance Criteria:**

1. [ASET-01] WHEN o usuário selecionar um PDF válido da pasta do projeto ou por upload THEN o sistema SHALL criar uma execução com identificador, hash do documento, nome do arquivo, quantidade de páginas e instante de criação.
2. [ASET-02] IF o arquivo não for PDF, exceder 50 MB, exceder 200 páginas, estiver criptografado sem acesso ou não puder ser aberto THEN o sistema SHALL rejeitar a entrada com uma mensagem que identifique a condição encontrada.
3. [ASET-03] WHEN a localização for iniciada THEN o sistema SHALL pedir à LLM a seção semanticamente relacionada a emissão, aplicação, resgate, amortização ou liquidação sem depender de número fixo de capítulo ou página.
4. [ASET-04] WHEN o localizador responder THEN o sistema SHALL apresentar título identificado, primeira página, última página e justificativa baseada no documento.
5. [ASET-05] WHEN a localização for apresentada THEN o sistema SHALL mostrar uma prévia das páginas selecionadas e permitir a alteração manual do intervalo.
6. [ASET-06] WHILE o intervalo não estiver confirmado pelo usuário, o sistema SHALL impedir o início da extração.
7. [ASET-07] IF a LLM não localizar uma seção compatível THEN o sistema SHALL manter a execução recuperável e solicitar que o usuário informe o intervalo manualmente.

**Independent Test:** Usar um conjunto sintético em que a seção equivalente esteja no Capítulo 6 e confirmar que a aplicação a localiza, exibe e permite corrigir as páginas antes da extração.

---

### P1: Extrair tabelas e texto corrido com LLM ⭐ MVP

**User Story:** Como operador, quero receber variáveis estruturadas para usar o conteúdo do regulamento sem transcrição manual.

**Why P1:** É o valor central do case e deve cobrir formatos abertos e fechados de fundo.

**Acceptance Criteria:**

1. [ASET-08] WHEN o usuário confirmar as páginas THEN o sistema SHALL enviar ao agente extrator somente o documento e o intervalo confirmados, junto com instruções que tratem o conteúdo do PDF como dados não confiáveis.
2. [ASET-09] WHEN o agente extrair uma linha de tabela ou regra textual THEN o sistema SHALL registrar nome da variável, valor, trecho-fonte, página, origem `tabela` ou `texto` e referência de cláusula quando disponível.
3. [ASET-10] WHEN uma célula ou cláusula contiver fatos independentes THEN o sistema SHALL representá-los como variáveis separadas.
4. [ASET-11] WHEN uma informação corresponder ao vocabulário preferencial THEN o sistema SHALL usar o nome canônico indicado pelo agente extrator.
5. [ASET-12] WHEN uma regra relevante não corresponder ao vocabulário preferencial THEN o sistema SHALL permitir que o agente crie um nome semântico novo.
6. [ASET-13] The system SHALL executar a identificação e a extração sem regex, busca literal obrigatória ou regras determinísticas que produzam o conteúdo das variáveis.
7. [ASET-14] The system SHALL validar a saída estrutural do extrator antes de persistir qualquer variável.
8. [ASET-15] IF a seção confirmada não contiver tabela THEN o sistema SHALL continuar a extração das regras em texto corrido sem tratar a ausência de tabela como erro.

**Independent Test:** Processar um regulamento com tabela e outro somente com texto, verificando que ambos geram variáveis estruturadas e evidência por página.

---

### P1: Validar por agente independente e atribuir confiança ⭐ MVP

**User Story:** Como revisor, quero que outro agente confronte cada resultado com a fonte para concentrar minha atenção nos riscos reais.

**Why P1:** O requisito exige agente separado e a proposta de valor depende de reduzir erros silenciosos.

**Acceptance Criteria:**

1. [ASET-16] WHEN a extração terminar THEN o sistema SHALL executar um agente validador em chamada separada da chamada do agente extrator.
2. [ASET-17] WHEN uma variável for validada THEN o sistema SHALL fornecer ao validador o valor extraído e a fonte, sem fornecer raciocínio, veredito ou score produzido pelo extrator.
3. [ASET-18] WHEN o validador concluir uma avaliação THEN o sistema SHALL registrar score entre `0,00` e `1,00`, veredito `suportado`, `parcialmente_suportado` ou `nao_suportado`, justificativa curta e lista de problemas.
4. [ASET-19] WHEN o validador concluir o conjunto THEN o sistema SHALL registrar possíveis omissões identificadas ao comparar a seção-fonte com a lista extraída.
5. [ASET-20] IF o score for menor que `0,85` THEN o sistema SHALL colocar a variável na fila de revisão.
6. [ASET-21] IF o veredito for `parcialmente_suportado` ou `nao_suportado` THEN o sistema SHALL colocar a variável na fila de revisão independentemente do score.
7. [ASET-22] IF o validador apontar conflito ou possível omissão THEN o sistema SHALL criar uma pendência revisável sem alterar automaticamente o resultado do extrator.
8. [ASET-23] The system SHALL exibir o score como confiança atribuída pela LLM com rubrica documentada e não como probabilidade calibrada.

**Independent Test:** Injetar valores corretos, ambíguos, contraditórios e uma omissão conhecida; verificar que o validador mantém os corretos e encaminha os demais para revisão.

---

### P1: Revisar e persistir decisões humanas ⭐ MVP

**User Story:** Como revisor, quero resolver cada pendência sem perder a evidência ou o valor original.

**Why P1:** A revisão humana é o controle exigido para extrações de baixa confiança.

**Acceptance Criteria:**

1. [ASET-24] WHEN a validação terminar THEN o sistema SHALL mostrar todas as variáveis em uma visão geral e somente as pendências na fila de revisão.
2. [ASET-25] WHEN uma pendência for aberta THEN o sistema SHALL mostrar nome, valor, trecho-fonte imutável, página, score, veredito e justificativa do validador.
3. [ASET-26] WHEN o usuário confirmar uma variável THEN o sistema SHALL manter nome e valor vigentes e registrar `Foi revisado?` como verdadeiro.
4. [ASET-27] WHEN o usuário editar uma variável THEN o sistema SHALL permitir alterar nome e valor, preservar os originais e registrar `Foi revisado?` como verdadeiro.
5. [ASET-28] WHEN o usuário marcar uma variável como não aplicável THEN o sistema SHALL registrar a decisão na auditoria e remover a pendência da fila sem apagar o registro original.
6. [ASET-29] WHEN o usuário aceitar uma possível omissão THEN o sistema SHALL permitir criar a variável ausente com nome, valor e evidência revisados manualmente.
7. [ASET-30] The system SHALL marcar `Foi revisado?` como verdadeiro somente após ação humana explícita.
8. [ASET-31] WHEN qualquer decisão de revisão ocorrer THEN o sistema SHALL persistir atomicamente valor original, valor vigente, ação, instante e estado atualizado da execução.
9. [ASET-32] WHEN uma execução existente for reaberta THEN o sistema SHALL restaurar páginas confirmadas, extrações, validações e revisões já salvas.

**Independent Test:** Interromper e reabrir uma execução com uma variável confirmada, uma editada e uma não aplicável; verificar o estado e a trilha de cada uma.

---

### P1: Exportar Excel preliminar e final ⭐ MVP

**User Story:** Como operador, quero baixar um resultado compatível com o formato solicitado e distinguir claramente trabalho pendente de trabalho concluído.

**Why P1:** O Excel é o artefato de entrega do processo.

**Acceptance Criteria:**

1. [ASET-33] WHEN houver ao menos uma variável validada THEN o sistema SHALL permitir gerar um Excel preliminar mesmo que existam pendências.
2. [ASET-34] WHILE existir qualquer pendência de revisão, o sistema SHALL impedir a geração do Excel final e mostrar a quantidade pendente.
3. [ASET-35] WHEN não existir pendência de revisão THEN o sistema SHALL permitir gerar o Excel final.
4. [ASET-36] The system SHALL criar na aba principal exatamente as colunas `Variável`, `Valor da variável`, `Trecho da variável`, `Grau de Confiança` e `Foi revisado?`, nessa ordem.
5. [ASET-37] WHEN uma variável tiver sido editada THEN o sistema SHALL exportar o nome e o valor vigentes, mantendo o trecho-fonte original.
6. [ASET-38] The system SHALL exportar `Grau de Confiança` como número entre `0` e `1` e `Foi revisado?` como booleano.
7. [ASET-39] The system SHALL incluir uma aba de auditoria com identificação do documento, hash, páginas, modelos, versões de prompt, tempos, uso reportado pela API e histórico de revisão.
8. [ASET-40] WHEN o Excel for gerado THEN o sistema SHALL salvá-lo no diretório da execução e disponibilizá-lo para download na interface.

**Independent Test:** Comparar workbooks preliminar e final contra o contrato de colunas, tipos, bloqueio por pendência e conteúdo de auditoria.

---

### P1: Recuperar falhas e produzir evidência operacional ⭐ MVP

**User Story:** Como apresentador, quero que falhas externas sejam visíveis e recuperáveis para não perder o trabalho durante a demonstração.

**Why P1:** Uma chamada instável ou resposta inválida não deve destruir uma execução.

**Acceptance Criteria:**

1. [ASET-41] IF uma chamada de LLM falhar por timeout, limite transitório ou erro de rede THEN o sistema SHALL tentar novamente no máximo três vezes e preservar o último estágio concluído.
2. [ASET-42] IF uma resposta da LLM for recusada, incompleta ou inválida para o schema THEN o sistema SHALL registrar a falha do estágio e apresentar uma ação explícita de nova tentativa.
3. [ASET-43] WHEN uma etapa for concluída THEN o sistema SHALL persistir seu resultado antes de iniciar a etapa seguinte.
4. [ASET-44] WHEN a mesma etapa for repetida para a mesma execução THEN o sistema SHALL substituir somente o resultado daquela etapa e invalidar resultados dependentes posteriores.
5. [ASET-45] WHILE uma execução estiver processando uma chamada externa, o sistema SHALL impedir o início concorrente de outra chamada para a mesma execução.
6. [ASET-46] The system SHALL registrar eventos estruturados com `run_id`, etapa, resultado, duração, modelo, uso reportado e erro sanitizado.
7. [ASET-47] The system SHALL impedir que chaves de API sejam persistidas em logs, estado, fixtures, Excel ou mensagens de erro.

**Independent Test:** Simular timeout, rate limit, schema inválido e repetição de etapa; verificar retry limitado, preservação do estado, invalidação correta e logs sem segredo.

---

### P1: Verificar qualidade de forma reproduzível ⭐ MVP

**User Story:** Como avaliador técnico, quero evidência executável de qualidade para distinguir uma demonstração confiável de um caminho feliz manual.

**Why P1:** Testes e evals são parte explícita da proposta profissional do projeto.

**Acceptance Criteria:**

1. [ASET-48] The system SHALL executar testes unitários e de contrato sem chave de API e sem acesso de rede.
2. [ASET-49] The system SHALL manter um golden set versionado que referencia os quatro PDFs por hash e contém variáveis esperadas, valores aceitos, páginas e trechos de evidência.
3. [ASET-50] WHEN uma alteração modificar prompts, schemas ou pipeline THEN o sistema SHALL produzir um relatório de avaliação comparável ao baseline anterior antes de ser considerada concluída.
4. [ASET-51] The system SHALL incluir um cenário de localização com seção equivalente no Capítulo 6 e páginas diferentes.
5. [ASET-52] The system SHALL encaminhar para revisão 100% dos valores contraditórios ou sem suporte inseridos no conjunto adversarial versionado.
6. [ASET-53] The system SHALL resolver 100% dos trechos de evidência do golden set nos PDFs e páginas declarados.
7. [ASET-54] WHERE uma chave de API estiver disponível, o sistema SHALL oferecer um smoke test real opt-in separado da suíte offline.

**Independent Test:** Rodar a suíte offline em ambiente limpo, verificar o relatório do golden set e executar opcionalmente um smoke test real em um documento.

---

### P3: Buscar variáveis em linguagem natural

**User Story:** Como operador, quero perguntar sobre os dados extraídos para encontrar uma variável sem conhecer seu nome técnico.

**Why P3:** É um diferencial útil, mas não pode competir com a confiabilidade do núcleo.

**Acceptance Criteria:**

1. [ASET-55] WHERE a busca em linguagem natural estiver habilitada, WHEN o usuário fizer uma pergunta respondível pelas variáveis da execução THEN o sistema SHALL responder com valor, nome da variável e trecho-fonte utilizado.
2. [ASET-56] WHERE a busca em linguagem natural estiver habilitada, IF as variáveis não sustentarem uma resposta THEN o sistema SHALL declarar ausência de evidência sem inventar um valor.
3. [ASET-57] WHILE qualquer gate P1 estiver falhando, o sistema SHALL manter a busca em linguagem natural desabilitada.

**Independent Test:** Perguntar por um prazo existente e por uma informação ausente; verificar resposta com evidência no primeiro caso e abstenção no segundo.

---

## Edge Cases

- IF a tabela atravessar uma quebra de página THEN o sistema SHALL manter a relação entre rótulo, valor e páginas de origem.
- IF dois campos receberem o mesmo nome semântico THEN o sistema SHALL preservá-los como registros distintos até que a revisão resolva a duplicidade.
- IF o trecho extraído não existir na página declarada THEN o sistema SHALL criar uma pendência de evidência inválida.
- IF o documento tiver camada textual corrompida ou ausente THEN o sistema SHALL usar a representação visual fornecida ao modelo sem impedir o fluxo.
- IF o usuário reduzir o intervalo de páginas após extrair THEN o sistema SHALL invalidar extração, validação, revisões e exports dependentes.
- IF o diretório de persistência não puder ser escrito THEN o sistema SHALL interromper a etapa antes da chamada paga e explicar o problema.
- WHEN uma execução concluída for reprocessada THEN o sistema SHALL criar nova execução em vez de sobrescrever silenciosamente o histórico anterior.

---

## Requirement Traceability

| Requirement ID | Story | Phase | Status |
| --- | --- | --- | --- |
| ASET-01 | P1: Localização | Design | Implemented (T03–T04, T10, T13, T22) |
| ASET-02 | P1: Localização | Design | Implemented (T04, T13) |
| ASET-03 | P1: Localização | Design | Implemented (T07, T13) |
| ASET-04 | P1: Localização | Design | Implemented (T05, T07, T13) |
| ASET-05 | P1: Localização | Design | Implemented (T04, T13) |
| ASET-06 | P1: Localização | Design | Implemented (T02, T07, T10, T13) |
| ASET-07 | P1: Localização | Design | Implemented (T07, T10, T13) |
| ASET-08 | P1: Extração | Design | Implemented (T04, T08, T10) |
| ASET-09 | P1: Extração | Design | Implemented (T02, T05, T08) |
| ASET-10 | P1: Extração | Design | Implemented (T05, T08) |
| ASET-11 | P1: Extração | Design | Implemented (T08) |
| ASET-12 | P1: Extração | Design | Implemented (T08) |
| ASET-13 | P1: Extração | Design | Implemented (T08) |
| ASET-14 | P1: Extração | Design | Partial (T05, T08) |
| ASET-15 | P1: Extração | Design | Implemented (T08) |
| ASET-16 | P1: Validação | Design | Implemented (T05, T06, T09, T10) |
| ASET-17 | P1: Validação | Design | Implemented (T05, T09) |
| ASET-18 | P1: Validação | Design | Implemented (T02, T05, T09) |
| ASET-19 | P1: Validação | Design | Implemented (T02, T05, T09) |
| ASET-20 | P1: Validação | Design | Implemented (T02, T09) |
| ASET-21 | P1: Validação | Design | Implemented (T02, T09) |
| ASET-22 | P1: Validação | Design | Implemented (T02, T09) |
| ASET-23 | P1: Validação | Design | Implemented (T02, T09) |
| ASET-24 | P1: Revisão | Design | Implemented (T02, T09–T11, T14) |
| ASET-25 | P1: Revisão | Design | Implemented (T02, T09, T11, T14) |
| ASET-26 | P1: Revisão | Design | Implemented (T02, T11, T14) |
| ASET-27 | P1: Revisão | Design | Implemented (T02, T11, T14) |
| ASET-28 | P1: Revisão | Design | Implemented (T02, T11, T14) |
| ASET-29 | P1: Revisão | Design | Implemented (T02, T11, T14) |
| ASET-30 | P1: Revisão | Design | Implemented (T02, T11, T14) |
| ASET-31 | P1: Revisão | Design | Implemented (T03, T11) |
| ASET-32 | P1: Revisão | Design | Implemented (T03, T11, T15) |
| ASET-33 | P1: Excel | Design | Implemented (T12, T15) |
| ASET-34 | P1: Excel | Design | Implemented (T02, T12, T15) |
| ASET-35 | P1: Excel | Design | Implemented (T02, T12, T15) |
| ASET-36 | P1: Excel | Design | Implemented (T12, T15) |
| ASET-37 | P1: Excel | Design | Implemented (T11, T12, T15) |
| ASET-38 | P1: Excel | Design | Implemented (T02, T12, T15) |
| ASET-39 | P1: Excel | Design | Implemented (T10, T12, T15) |
| ASET-40 | P1: Excel | Design | Implemented (T12, T15) |
| ASET-41 | P1: Resiliência | Design | Implemented (T06, T10) |
| ASET-42 | P1: Resiliência | Design | Partial (T06, T10) |
| ASET-43 | P1: Resiliência | Design | Implemented (T03, T10) |
| ASET-44 | P1: Resiliência | Design | Implemented (T02, T10) |
| ASET-45 | P1: Resiliência | Design | Implemented (T02, T10) |
| ASET-46 | P1: Resiliência | Design | Implemented (T03, T06, T10, T15) |
| ASET-47 | P1: Resiliência | Design | Partial (T03, T06, T10, T20) |
| ASET-48 | P1: Qualidade | Design | Implemented (T01, T06, T20, T21) |
| ASET-49 | P1: Qualidade | Design | Implemented (T16) |
| ASET-50 | P1: Qualidade | Design | Implemented (T17) |
| ASET-51 | P1: Qualidade | Design | Implemented (T07, T17) |
| ASET-52 | P1: Qualidade | Design | Implemented (T09, T17) |
| ASET-53 | P1: Qualidade | Design | Implemented (T04, T16, T17) |
| ASET-54 | P1: Qualidade | Design | Implemented (T06, T19, T21) |
| ASET-55 | P3: Busca | - | Pending |
| ASET-56 | P3: Busca | - | Pending |
| ASET-57 | P3: Busca | - | Pending |

T18 adiciona evidência ponta a ponta offline para o fluxo integrado de ASET-01–53. T19
completa ASET-54 com um smoke test real opt-in, isolado do gate offline e sanitizado.

**Coverage:** 57 requisitos totais; 54 P1 mapeados ao desenho; 3 P3 postergados; T01–T24 concluídas e correção T25 aberta após a primeira verificação independente.

---

## Implicit Requirement Dimensions

| Dimensão | Resolução |
| --- | --- |
| Validação de entrada | PDF, máximo de 50 MB e 200 páginas; arquivo precisa abrir e não pode exigir senha indisponível. |
| Falha e falha parcial | Cada estágio persiste antes do próximo; falha preserva último estágio concluído. |
| Idempotência e retry | Até três retries transitórios; repetição de estágio substitui o estágio e invalida dependentes. |
| Autenticação e rate limits | Autenticação é N/A porque a aplicação é local e de usuário único; limites externos usam retry limitado e erro visível. |
| Concorrência e ordenação | Uma chamada ativa por execução; máquina de estados impede etapas fora de ordem. |
| Ciclo de vida | Execuções persistem sem TTL; remoção automática é N/A para o case local. |
| Observabilidade | Eventos JSON estruturados, métricas de tempo/uso e erros sanitizados por `run_id`. |
| Dependência externa | Falhas da LLM têm retry limitado, retomada e ação manual explícita. |
| Integridade de estado | Alterações em páginas invalidam resultados posteriores; Excel final exige zero pendências. |

---

## Success Criteria

- [ ] Os quatro documentos fornecidos completam o fluxo e geram Excel preliminar e final.
- [ ] O cenário equivalente no Capítulo 6 é localizado sem alterar código ou prompt.
- [ ] Todos os valores contraditórios ou sem evidência do conjunto adversarial entram na fila de revisão.
- [ ] Nenhum Excel final é produzido com pendência aberta.
- [ ] Todos os trechos do golden set resolvem no documento e na página declarados.
- [ ] A suíte offline passa sem rede, segredo ou chamada paga.
- [x] Uma pessoa consegue demonstrar seleção, localização, extração, validação, revisão e download em uma única sessão local.

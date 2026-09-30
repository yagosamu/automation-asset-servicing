# Polimento da Interface de Apresentação

## Problem Statement

A interface funcional não comunica com clareza a etapa atual, o trabalho dos agentes nem a prioridade dos resultados. Durante a apresentação, o operador precisa compreender o fluxo sem interpretar detalhes técnicos ou percorrer blocos já concluídos.

## Goals

- [ ] Mostrar o progresso do fluxo em quatro etapas.
- [ ] Dar destaque ao resumo, às pendências e aos arquivos da execução ativa.
- [ ] Tornar localização, extração e validação visíveis enquanto processam.
- [ ] Preservar integralmente o comportamento de persistência, revisão e Excel.

## Out of Scope

| Item | Motivo |
| --- | --- |
| Identidade visual do BTG | Não há autorização nem guia de marca no escopo. |
| CSS customizado | Aumentaria fragilidade antes da apresentação. |
| Alteração do pipeline ou do Excel | O trabalho é exclusivamente de apresentação da interface. |

## Assumptions & Open Questions

| Premissa | Decisão | Confirmado? |
| --- | --- | --- |
| Componentes | Usar somente componentes nativos do Streamlit | Sim |
| Etapas | Documento, Localização, Extração, Revisão e Excel | Sim |
| Confiança | Manter o score e acrescentar classificação visual | Sim |
| Estado anterior | Preservar o baseline na tag `ui-baseline-before-polish-2026-09-30` | Sim |

**Open questions:** none.

## User Stories

Como operador, quero enxergar a etapa atual, o processamento e os resultados prioritários para conduzir a demonstração com clareza.

## Acceptance Criteria

1. [UIP-01] WHEN a aplicação abrir THEN o sistema SHALL mostrar título executivo, descrição curta e as quatro etapas `Documento`, `Localização`, `Extração` e `Revisão e Excel`, destacando a etapa atual.
2. [UIP-02] WHILE nenhuma execução estiver ativa THEN o sistema SHALL mostrar uma orientação para selecionar o regulamento e localizar o capítulo.
3. [UIP-03] WHEN a extração e a validação terminarem THEN o sistema SHALL recolher a seção de documento e localização e mostrar imediatamente a execução ativa.
4. [UIP-04] WHILE localização, extração ou validação estiverem em andamento THEN o sistema SHALL mostrar o estágio correspondente; IF o processamento falhar THEN o sistema SHALL manter um estado visível de erro e a orientação de nova tentativa.
5. [UIP-05] WHEN uma variável validada for exibida THEN o sistema SHALL mostrar o score numérico e uma classificação visual `Alta`, `Média` ou `Baixa` usando os mesmos limites do resumo operacional.
6. [UIP-06] WHEN uma execução estiver ativa THEN o sistema SHALL mostrar primeiro um resumo compacto com variáveis, pendências, aprovadas e duração total.
7. [UIP-07] WHEN detalhes operacionais estiverem disponíveis THEN o sistema SHALL mantê-los em uma seção recolhida sem remover tempos, chamadas, retries, uso, modelos ou versões de prompt.

## Independent Test

Executar a jornada offline completa, observar a progressão das quatro etapas, confirmar o resumo e a classificação de confiança e verificar que a troca de regulamento retorna ao estado inicial sem apagar a execução persistida.

## Edge Cases

- WHEN o usuário selecionar outro regulamento THEN o indicador SHALL voltar para `Documento`, a seção de entrada SHALL abrir e os resultados anteriores SHALL desaparecer.
- IF não houver eventos operacionais THEN a duração total SHALL aparecer como `0,00 s` sem impedir a revisão.
- IF uma variável ainda não tiver validação THEN a classificação visual SHALL aparecer como `Não avaliada`.

## Requirement Traceability

| Requirement | Status |
| --- | --- |
| UIP-01 | Implemented |
| UIP-02 | Implemented |
| UIP-03 | Implemented |
| UIP-04 | Implemented |
| UIP-05 | Implemented |
| UIP-06 | Implemented |
| UIP-07 | Implemented |

## Implicit Requirement Dimensions

| Dimensão | Resolução |
| --- | --- |
| Persistência | Nenhuma alteração no repositório ou ciclo de vida das execuções. |
| Acessibilidade | Textos acompanham ícones e cores; significado não depende somente de cor. |
| Falhas | Estados de erro existentes permanecem visíveis e recuperáveis. |
| Compatibilidade | Componentes nativos do Streamlit 1.50 ou superior. |

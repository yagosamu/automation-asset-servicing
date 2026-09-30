# Validation: UAT Corrections T26–T27 - FAIL ❌

**Verdict**: FAIL ❌
**Date**: 2026-09-30
**Spec**: `.specs/features/regulation-extraction/spec.md`
**Diff range**: `fc67406..063f0ed`
**Verifier**: independent sub-agent (author ≠ verifier)

O fluxo de descarte auditável de omissões atende ao resultado especificado. A correção de limite
semântico está presente nos prompts v2, mas seus testes não distinguem instruções corretas de
instruções invertidas. Duas mutações que mandavam extrator e validador incluir capítulos adjacentes
passaram integralmente. A feature não pode ser declarada verificada enquanto esse comportamento
central não tiver uma prova discriminante.

---

## Task Completion

| Task | Status | Notes |
| --- | --- | --- |
| T26 | ⚠️ Implementada, não verificada | Prompts e baseline foram atualizados, mas o sensor encontrou testes sem discriminação semântica. |
| T27 | ✅ Verificada | Serviço, persistência, UI, desbloqueio do Excel e auditoria têm asserções de estado exatas. |

As tarefas estão marcadas como concluídas em `.specs/features/regulation-extraction/tasks.md:732` e
`.specs/features/regulation-extraction/tasks.md:758`. O veredito permanece FAIL porque o fechamento
de uma tarefa não substitui a evidência independente.

---

## Spec-Anchored Acceptance Criteria

| Critério | Resultado definido pela spec | `file:line` + asserção | Resultado |
| --- | --- | --- | --- |
| ASET-08 + edge case de capítulo adjacente | O extrator usa somente a seção-alvo e para no próximo capítulo ou seção de mesmo nível, inclusive na mesma página. | `tests/contract/test_extractor_prompt.py:48`–`:55` afirma apenas substrings como `"próximo capítulo"` e `"ignore"`; não afirma a polaridade da instrução. M1 provou que `Continue ... Extraia fatos ... adjacentes` também passa. | ❌ GAP |
| ASET-19 + edge case de capítulo adjacente | O validador não registra omissões originadas de capítulos ou seções adjacentes. | `tests/contract/test_validator_prompt.py:48`–`:56` afirma apenas substrings. M3 inverteu a regra para registrar conteúdo adjacente e os 19 testes passaram. | ❌ GAP |
| ASET-22 + edge case de falso positivo | Descartar uma omissão mantém o achado, não cria variável e resolve a pendência. | `tests/unit/application/test_review_service.py:224`–`:232` afirma `DISMISSED`, alvo `finding_id`, fila vazia e `can_export_final() is True`; `tests/ui/test_review_ui.py:304`–`:310` afirma remoção visual da fila. | ✅ PASS |
| ASET-31 | A decisão persiste justificativa, ação, instante e estado atualizado. | `tests/unit/application/test_review_service.py:225`–`:234` afirma estado, ação, id, nota e instante; `tests/integration/test_review_persistence.py:158`–`:164` reabre o JSON e afirma os valores exatos. | ✅ PASS |
| ASET-32 | Reabrir restaura a decisão e não recoloca a omissão na fila. | `tests/integration/test_review_persistence.py:158`–`:164` afirma `DISMISSED`, ação, `finding_id`, nota e fila vazia após reidratação. | ✅ PASS |
| ASET-34–35 | Uma omissão pendente bloqueia o Excel final; a descartada o libera. | `tests/unit/application/test_review_service.py:231`–`:232` afirma fila vazia e liberação; `tests/integration/test_excel_export.py:174`–`:180` gera `final.xlsx` e afirma auditoria por id, ação e justificativa. | ✅ PASS |
| Justificativa obrigatória | Descarte com nota vazia é rejeitado e não altera o estado. | `tests/unit/application/test_review_service.py:237`–`:246` espera `ValueError`, mantém `PENDING` e nenhuma decisão. | ✅ PASS |

**Status**: 5/7 obrigações agrupadas correspondem ao resultado especificado; 2 gaps de
discriminação no comportamento central da T26; 0 gaps de precisão na redação da spec.

---

## Edge Cases

| Edge case | Evidência | Resultado |
| --- | --- | --- |
| Página final contém o capítulo seguinte. | A implementação contém a regra em `src/asset_servicing/application/extractor.py:24`–`:27` e `src/asset_servicing/application/validator.py:29`–`:33`, mas os testes em `tests/contract/test_extractor_prompt.py:48`–`:55` e `tests/contract/test_validator_prompt.py:48`–`:56` aceitaram a semântica inversa. | ❌ Não verificado |
| Omissão é falso positivo ou está fora do escopo. | `tests/unit/application/test_review_service.py:209`–`:234`, `tests/integration/test_review_persistence.py:145`–`:164`, `tests/ui/test_review_ui.py:293`–`:310` e `tests/integration/test_excel_export.py:153`–`:180`. | ✅ PASS |

---

## Gate Check

- **Comando canônico**: `uv run ruff format --check . && uv run ruff check . && uv run mypy src && uv run pytest -m "not needs_api" --cov=asset_servicing --cov-branch --cov-report=term-missing --cov-fail-under=85 -q`
- **Formatação**: 61 arquivos já formatados.
- **Ruff**: sem problemas.
- **mypy**: sem problemas em 27 arquivos-fonte.
- **Testes**: 351 passed, 0 failed, 4 deselected.
- **Cobertura**: 92,48%, acima do limite de 85%.
- **Antes das correções**: 344 passed, 4 deselected em `fc67406`, conforme o relatório versionado naquele commit.
- **Delta**: +7 testes offline; nenhum teste foi removido.
- **Deselecionados**: 4 cenários `needs_api`, excluídos pelo próprio comando canônico.

**Resultado do gate**: PASS ✅

---

## Structural Validation

| Comando | Resultado |
| --- | --- |
| `validate_spec.py .specs/features/regulation-extraction/spec.md` | ✅ 0 erros, 0 avisos |
| `validate_tasks.py .specs/features/regulation-extraction/tasks.md` | ⚠️ 0 erros, 1 aviso de granularidade em T26 por citar dois prompts |
| `git diff --check fc67406..HEAD` | ✅ sem saída |

O aviso de granularidade é documental e não bloqueia o gate. Os dois prompts formam a mesma
correção de fronteira semântica.

---

## Discrimination Sensor

O sensor usou um worktree detached temporário em `063f0ed`. Cada mutação foi revertida antes da
seguinte. Os testes carregaram o `src` do scratch por `PYTHONPATH`. O worktree foi removido e
`git status --porcelain=v1` da árvore real permaneceu idêntico ao baseline vazio.

| Mutação | Arquivo:linha | Defeito injetado | Teste alvo e saída | Resultado |
| --- | --- | --- | --- | --- |
| M1 | `src/asset_servicing/application/extractor.py:24`–`:27` | `Pare/Não extraia` virou `Continue/Extraia` para incluir capítulos adjacentes, preservando o vocabulário superficial. | `tests/contract/test_extractor_prompt.py`: 15 passed. | ❌ Survived |
| M2 | `src/asset_servicing/application/review_service.py:187` | Estado do descarte mudou de `DISMISSED` para `ACCEPTED`. | 3 falhas exatas em unit, integration e UI; 32 passed. | ✅ Killed |
| M3 | `src/asset_servicing/application/validator.py:61`–`:64` | Regra de cobertura foi invertida para registrar capítulos adjacentes, preservando `não registre`, `omissão` e demais tokens exigidos. | `tests/contract/test_validator_prompt.py`: 19 passed. | ❌ Survived |

**Profundidade**: lightweight, 3 mutações nos dois riscos UAT.
**Resultado**: 1/3 killed, 2/3 survived - FAIL ❌

---

## Code Quality

| Checagem | Resultado | Evidência / observação |
| --- | --- | --- |
| Mudança mínima e cirúrgica | ✅ | O diff limita-se a prompts/versionamento, ação de revisão, persistência/auditoria, UI e testes. |
| Sem abstrações ou flexibilidade desnecessárias | ✅ | `dismiss_omission` reutiliza o agregado, repositório e invalidação de exports existentes. |
| Padrões e estilo do repositório | ✅ | Ruff, format e mypy passaram. |
| Integridade dos testes | ✅ | +7 testes, nenhuma remoção, 351 offline verdes. |
| Resultado ancorado na spec | ❌ | Os testes T26 verificam palavras, não o sentido obrigatório; M1 e M3 sobreviveram. |
| Cobertura por camada | ✅ T27 / ❌ T26 | T27 cobre unit, persistence, UI e Excel. T26 tem contract/eval de versão, sem prova discriminante da fronteira. |
| Testes sem reivindicação | ✅ | Os novos testes mapeiam para T26, T27, ASET-22/31–35 ou os dois edge cases. |
| Guidelines | ✅ | `.specs/features/regulation-extraction/tasks.md` e `references/coding-principles.md`. |

---

## Fix Plan

### F1: Tornar a fronteira semântica verificável

- **Severidade**: Major.
- **Raiz**: contratos de prompt baseados em presença de tokens não detectam inversão de polaridade.
- **Correção**: substituir as asserções fragmentadas por uma cláusula canônica versionada ou outra
  representação estrutural cujo valor exato expresse `stop_at_next_peer_heading=true` e
  `include_adjacent_sections=false`, usada para compor os dois prompts. Como reforço de avaliação,
  adicionar um caso gravado com início do capítulo seguinte na página final e saída sem variáveis
  nem omissões daquele capítulo.
- **Prova**: os testes devem falhar quando `pare/ignore` for invertido para `continue/inclua`, e o
  relatório de eval deve falhar quando a saída gravada contiver fato ou omissão do capítulo seguinte.
- **Escopo**: novo fix task de T26; T27 não precisa de alteração.

---

## Requirement Traceability

| Requisito / caso | Status anterior | Status desta validação |
| --- | --- | --- |
| ASET-08 + limite de seção | Implemented (T26) | ❌ Needs fix: prova não discriminante |
| ASET-19 + omissões fora da seção | Implemented (T26) | ❌ Needs fix: prova não discriminante |
| ASET-22, ASET-31–35 + descarte | Implemented (T27) | ✅ Verified |

---

## Summary

**Overall**: ❌ Not ready.
**Spec-anchored check**: T27 atende ao resultado; T26 tem 2 gaps de discriminação.
**Gate**: 351 passed, 0 failed, 4 deselected, 92,48%.
**Sensor**: 1/3 killed; 2/3 survived.
**Next step**: criar um fix task para prova semântica de T26 e executar nova verificação
independente. A correção T27 pode ser mantida como está.

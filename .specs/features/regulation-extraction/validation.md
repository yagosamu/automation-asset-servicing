# Validation: Section-Boundary Corrections T26–T28 - PASS ✅

**Verdict**: PASS ✅
**Date**: 2026-09-30
**Spec**: `.specs/features/regulation-extraction/spec.md`
**Implementation diff**: `1af5957..53735cd`
**Context diff**: `fc67406..53735cd`
**Verifier**: independent sub-agent (author ≠ verifier)

T28 fecha os dois gaps anteriores. Os contratos verificam as cláusulas semânticas completas e os
snapshots dos prompts. O gate offline rejeita variável e omissão do Capítulo 4. As três mutações
comportamentais foram mortas.

---

## Task Completion

| Task | Status | Notes |
| --- | --- | --- |
| T01–T25 | ✅ Verificadas anteriormente | Baseline funcional preservado. |
| T26 | ✅ Verificada | Inversões dos prompts agora falham. |
| T27 | ✅ Verificada | Descarte auditável permaneceu verde no Build. |
| T28 | ✅ Verificada | Contratos exatos e gate negativo passaram no Build e sensor. |

---

## Spec-Anchored Acceptance Criteria

| Critério | Resultado definido pela spec | `file:line` + asserção | Resultado |
| --- | --- | --- | --- |
| ASET-08 + limite da seção | O extrator para no próximo capítulo ou seção de mesmo nível e não extrai conteúdo adjacente. | `tests/contract/test_extractor_prompt.py:50`–`:60` afirma a cláusula completa; `:63`–`:66` fixa o snapshot SHA-256. M1 inverteu `Pare/Não extraia` e causou 2 falhas. | ✅ PASS |
| ASET-19 + limite da seção | O validador ignora capítulos adjacentes e não cria omissões com seu conteúdo. | `tests/contract/test_validator_prompt.py:50`–`:67` afirma as cláusulas completas; `:70`–`:73` fixa o snapshot. M2 inverteu ambas e causou 2 falhas. | ✅ PASS |
| Edge case: capítulo seguinte na página final | A fixture identifica Capítulo 3 e Capítulo 4 começando na página 7. | `evals/golden/v1/adjacent_section_fixture.yaml:3`–`:12` fixa capítulos, página, título e dois fragmentos reais proibidos. | ✅ PASS |
| Exclusão de variável adjacente | Uma variável do Capítulo 4 reprova a avaliação pelo gate de fronteira. | `tests/evals/test_runner.py:99`–`:113` afirma `report.passed is False` e o gate exato; scanner em `src/asset_servicing/evals/runner.py:353`–`:369`. | ✅ PASS |
| Exclusão de omissão adjacente | Uma omissão do Capítulo 4 reprova a avaliação pelo gate de fronteira. | `tests/evals/test_runner.py:116`–`:129` afirma `report.passed is False` e o gate exato; `src/asset_servicing/evals/runner.py:355`–`:356` inclui omissões. | ✅ PASS |

**Status**: 5/5 obrigações da T28 correspondem ao resultado especificado; 0 gaps de precisão.

---

## Edge Cases

| Edge case | Evidência | Resultado |
| --- | --- | --- |
| A página final contém o início do capítulo seguinte. | `.specs/features/regulation-extraction/spec.md:228`; fixture e testes citados acima. | ✅ PASS |
| Uma possível omissão é falso positivo ou está fora de escopo. | `.specs/features/regulation-extraction/spec.md:229`; fluxo T27 permaneceu verde no Build. | ✅ PASS |

---

## Gate Check

- **Comando**: `uv run ruff format --check . && uv run ruff check . && uv run mypy src && uv run pytest -m "not needs_api" --cov=asset_servicing --cov-branch --cov-report=term-missing --cov-fail-under=85 -q`
- **Formatação**: 61 arquivos já formatados.
- **Ruff**: sem problemas.
- **mypy**: sem problemas em 27 arquivos-fonte.
- **Testes**: 355 passed, 0 failed, 4 deselected.
- **Cobertura**: 92,50%, acima do limite de 85%.
- **Antes da T28**: 351 passed, 4 deselected.
- **Delta**: +4 testes offline; nenhum teste removido.
- **Deselecionados**: 4 cenários `needs_api`, conforme o gate canônico.

**Resultado**: PASS ✅

---

## Structural Validation

| Comando | Resultado |
| --- | --- |
| `validate_spec.py .specs/features/regulation-extraction/spec.md` | ✅ 0 erros, 0 avisos |
| `validate_tasks.py .specs/features/regulation-extraction/tasks.md` | ⚠️ 0 erros, 1 aviso documental de granularidade em T26 |
| `git diff --check 1af5957..HEAD` | ✅ sem saída |

O aviso de T26 não bloqueia. Os dois prompts representam a mesma política de fronteira.

---

## Discrimination Sensor

O sensor usou um worktree detached temporário em `53735cd`. O ensaio M3 atualizou apenas os
fingerprints do baseline no scratch para neutralizar diferenças de checkout e medir causalmente o
gate mutado. O scratch foi removido e a árvore real permaneceu limpa.

| Mutação | Arquivo:linha | Defeito injetado | Teste alvo e saída | Resultado |
| --- | --- | --- | --- | --- |
| M1 | `src/asset_servicing/application/extractor.py:24`–`:26` | `Pare/Não extraia` virou `Continue/Extraia`. | Contrato do extrator: 2 failed, 14 passed. | ✅ Killed |
| M2 | `src/asset_servicing/application/validator.py:31`–`:35`, `:61`–`:62` | Limite e omissão foram invertidos para incluir conteúdo adjacente. | Contrato do validador: 2 failed, 18 passed. | ✅ Killed |
| M3 | `src/asset_servicing/evals/runner.py:449` | Removido o caráter bloqueante de `adjacent_section_exclusion`. | Os dois testes negativos falharam: variável e omissão retornaram `report.passed is True`. | ✅ Killed |

**Profundidade**: lightweight, 3 mutações nos riscos centrais da T28.
**Resultado**: 3/3 killed - PASS ✅

---

## Code Quality

| Checagem | Resultado | Evidência |
| --- | --- | --- |
| Mudança mínima e cirúrgica | ✅ | Diff T28 limitado a contratos, fixture, runner e documentação. |
| Sem abstrações desnecessárias | ✅ | Gate reutiliza `EvaluationFailure` e relatório existentes. |
| Padrões e estilo | ✅ | Ruff, format e mypy passaram. |
| Integridade dos testes | ✅ | +4 testes, nenhuma remoção ou enfraquecimento. |
| Resultado ancorado na spec | ✅ | Cláusulas, snapshots e outputs negativos afirmam resultados exatos. |
| Cobertura por camada | ✅ | Contract cobre prompts; eval cobre variável, omissão e bloqueio. |
| Testes com reivindicação | ✅ | Todos mapeiam para ASET-08, ASET-19 ou o edge case. |
| Guidelines | ✅ | `tasks.md` e `references/coding-principles.md`. |

---

## Interactive UAT

Não executada aqui. O usuário fará uma nova execução pela interface com o PDF real para confirmar
que o Capítulo 4 não gera possíveis omissões.

---

## Requirement Traceability

| Requisito / caso | Status anterior | Status desta validação |
| --- | --- | --- |
| ASET-08 + limite de seção | Needs fix | ✅ Verified (T28) |
| ASET-19 + omissões fora da seção | Needs fix | ✅ Verified (T28) |
| ASET-22, ASET-31–35 + descarte | ✅ Verified (T27) | ✅ Verified, sem regressão |

---

## Summary

**Overall**: ✅ Ready para UAT manual.
**Spec-anchored check**: 5/5 obrigações; 0 gaps de precisão.
**Gate**: 355 passed, 0 failed, 4 deselected, 92,50%.
**Sensor**: 3/3 mutações mortas.
**Next step**: reiniciar a aplicação e repetir a execução real. O esperado é zero possível omissão
originada do Capítulo 4; achados legítimos da seção-alvo continuam revisáveis.

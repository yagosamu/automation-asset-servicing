# Validation: T30 e T31 - FAIL ❌

**Verdict**: FAIL ❌
**Date**: 2026-09-30
**Spec**: .specs/features/regulation-extraction/spec.md
**Diff range**: 9e33a90..4ff2657
**Verifier**: independent sub-agent (author ≠ verifier)

Primeira rodada de verificação. T30 e T31 têm testes focados discriminantes, mas o snapshot
4ff2657 não pode ser aprovado: o Build canônico falhou e ASET-18 divergia dos enums públicos.

## Task Completion

| Task | Status | Notes |
| --- | --- | --- |
| T30 | ❌ Needs fix | Faixas, coerência e 1,00 literal passavam; os valores de enum divergiam de ASET-18. |
| T31 | ❌ Needs fix | Fluxo ativo e limpeza passavam nos testes UI; o contrato novo do README derrubava o Build. |

## Spec-Anchored Acceptance Criteria

| Critério | Resultado definido pela spec na rodada | file:line + asserção | Resultado |
| --- | --- | --- | --- |
| ASET-18: base, score e veredito coerentes | A base era literal, normalizada, parcial ou não_suportada. | .specs/features/regulation-extraction/spec.md:109; src/asset_servicing/domain/models.py:63-69 serializava literal, normalized, partial, unsupported; tests/contract/test_llm_contracts.py:321-372 afirmava os valores em inglês. | ❌ FAIL |
| ASET-23: 1,00 literal válido | Literal completo aceita 1,00; saturação literal não falha por si só. | tests/contract/test_llm_contracts.py:324 e :344-346; tests/evals/test_runner.py:215-229. | ✅ PASS |
| Edge: combinação incoerente é rejeitada | Base, faixa e veredito incompatíveis não entram no contrato. | src/asset_servicing/ports/llm.py:146-156; tests/contract/test_llm_contracts.py:349-372. | ✅ PASS |
| Edge: normalized com 1,00 é rejeitado | normalized termina antes de 0,95. | src/asset_servicing/ports/llm.py:149-152; tests/evals/test_runner.py:193-201. | ✅ PASS |
| ASET-24: execução recém-validada ativa | Resultados aparecem sem seleção intermediária. | src/asset_servicing/ui/app.py:313-322 e :675-685; tests/ui/test_complete_journey.py:205-220. | ✅ PASS |
| ASET-32: refresh sem seletor de histórico | run_id e progresso persistem; saved_run não aparece. | tests/ui/test_complete_journey.py:298-318; tests/ui/test_delivery_ui.py:171-193. | ✅ PASS |
| Edge: trocar regulamento limpa UI sem apagar histórico | Estado visível desaparece; execução persistida permanece. | src/asset_servicing/ui/app.py:173-179 e :325-329; tests/ui/test_complete_journey.py:321-340. | ✅ PASS |

**Status da rodada**: 6/7 obrigações verificadas; ASET-18 falhou por incompatibilidade literal.

## Gate Check

- **Comando**: uv run ruff format --check . && uv run ruff check . && uv run mypy src && uv run pytest -m "not needs_api" --cov=asset_servicing --cov-branch --cov-report=term-missing --cov-fail-under=85 -q
- **Ruff format**: 61 arquivos já formatados.
- **Ruff check**: sem problemas.
- **mypy**: 27 arquivos-fonte, 0 problemas.
- **Testes offline**: 376 passed, 1 failed, 4 deselected.
- **Falha**: tests/contract/test_readme.py:74, test_recovery_instructions_match_the_persisted_ui_workflow.
- **Cobertura**: 92,66%.
- **Antes de T30/T31**: 359 passed, 4 deselected, conforme o relatório T29 substituído.
- **Diff check**: git diff --check 9e33a90..4ff2657 sem saída.

No snapshot verificado, README.md:205-206 quebrava a frase entre “histórico” e “permanece”,
enquanto tests/contract/test_readme.py:74 exigia a substring contígua.

**Resultado**: FAIL ❌.

### Testes focados

| Comando | Resultado |
| --- | --- |
| pytest dos contratos/evals/unit de T30 | 98 passed |
| pytest dos dois arquivos UI de T31 | 15 passed |
| pytest UI + contrato README | 20 passed, 1 failed |

## Discrimination Sensor

O sensor usou worktree detached em 4ff2657. Os testes usaram o interpretador do projeto com
PYTHONPATH apontado ao src do scratch. Cada mutação foi restaurada. O scratch foi removido e o
git status --porcelain da árvore real voltou ao baseline vazio.

| Mut. | Arquivo:linha | Defeito injetado | Evidência de morte | Resultado |
| --- | --- | --- | --- | --- |
| M1 | src/asset_servicing/ports/llm.py:150 | Permitiu normalized com confidence=1.0. | O caso normalized-1.0-supported não levantou ValidationError (1 failed, 4 passed). | ✅ Killed |
| M2 | src/asset_servicing/ports/llm.py:149 | Rejeitou literal com confidence=1.0. | O caso literal-1.0-supported levantou ValidationError. | ✅ Killed |
| M3 | src/asset_servicing/ui/app.py:660 | Reintroduziu selectbox saved_run. | Teste do seletor e jornada completa falharam (2 failed). | ✅ Killed |
| M4 | src/asset_servicing/ui/app.py:675 | Removeu releitura do run_id após render. | Teste de troca falhou porque o resultado recém-validado não apareceu (1 failed). | ✅ Killed |
| M5 | src/asset_servicing/ui/app.py:178 | Removeu callback de limpeza ao trocar PDF. | Teste falhou porque o run_id antigo permaneceu na sessão (1 failed). | ✅ Killed |

**Resultado**: 5/5 killed - PASS ✅.

## Ranked Findings e Fix Plans

### P1 - ASET-18 divergia do contrato serializado

- **Evidência da rodada**: spec.md:109 usava normalizada, parcial e não_suportada;
  domain/models.py:66-69 usava normalized, partial e unsupported.
- **Fix**: alinhar a spec aos enums públicos ou alterar todo o contrato serializado.

### P1 - Build vermelho por contrato frágil do README

- **Evidência da rodada**: README.md:204-206 descrevia o comportamento correto, mas
  tests/contract/test_readme.py:74 dependia de whitespace contíguo.
- **Fix**: normalizar whitespace no teste ou afirmar fragmentos; rerodar o Build completo.

## Requirement Traceability

| Requisito / caso | Veredito da rodada |
| --- | --- |
| ASET-18 | ❌ Needs fix |
| ASET-23 | ✅ Verified |
| ASET-24 | ✅ Verified |
| ASET-32 | ✅ Verified |
| Saturação literal em 1,00 | ✅ Verified |
| Incoerência base/faixa/veredito | ✅ Verified |
| Troca de regulamento | ✅ Verified |

## Summary

**Overall**: ❌ Not Ready.
**Spec-anchored check**: 6/7 obrigações; 1 incompatibilidade literal em ASET-18.
**Gate**: Ruff e mypy verdes; 376 passed, 1 failed, 4 deselected; cobertura 92,66%.
**Focused tests**: T30 98 passed; UI T31 15 passed.
**Sensor**: 5/5 mutações mortas; isolamento confirmado.
**Next steps**: corrigir os dois findings e executar nova verificação independente sobre o commit de correção.

**Lessons**: havia sinais ac_gap e gate_fail, mas nenhuma lesson foi registrada porque esta
verificação permitia editar somente validation.md.

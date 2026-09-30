# Validation: Extraction Granularity T29 - PASS ✅

**Verdict**: PASS ✅
**Date**: 2026-09-30
**Spec**: `.specs/features/regulation-extraction/spec.md`
**Diff range**: `3f259b1..0479fa0`
**Verifier**: independent sub-agent (author ≠ verifier)

T29 satisfaz ASET-10 e o edge case de atributos coordenados. O extrator instrui agrupamento da
mesma ação e separação de regras operacionalmente independentes. O validador reconhece detalhes
preservados em variável agrupada. Os snapshots v3 são exatos. O eval rejeita quatro fragmentos e
a perda de qualquer atributo exigido no caso da cláusula 3.2, sem aplicar limite global ao documento.

---

## Task Completion

| Task | Status | Notes |
| --- | --- | --- |
| T01–T28 | ✅ Verificadas anteriormente | Baseline funcional preservado. |
| T29 | ✅ Verificada | Build adaptado ao Windows, 359 testes offline e sensor 3/3. |

---

## Spec-Anchored Acceptance Criteria

| Critério | Resultado definido pela spec | `file:line` + asserção | Resultado |
| --- | --- | --- | --- |
| ASET-10: agrupar a mesma ação | Atributos coordenados que compartilham gatilho, sujeito e consequência permanecem em uma variável completa. | `tests/contract/test_extractor_prompt.py:70` afirma a política completa em `:73`–`:75`; `tests/evals/test_runner.py:144`–`:157` exige `report.passed is False` e a falha `operational_granularity` para quatro fragmentos. | ✅ PASS |
| ASET-10: separar regras independentes | Regras com gatilho, responsável, prazo, valor ou consequência próprios saem separadas. | `tests/contract/test_extractor_prompt.py:70`–`:75` afirma simultaneamente o agrupamento e a cláusula exata de separação; `src/asset_servicing/application/extractor.py:37`–`:46` contém a instrução enviada ao agente. | ✅ PASS |
| Validador cobre detalhe agrupado | Um detalhe no nome, valor ou evidência da variável agrupada conta como coberto, sem falsa omissão ou redução de confiança. | `tests/contract/test_validator_prompt.py:77`–`:83` afirma `detalhe coberto`, `valor ou evidência`, ausência de variável separada e confiança preservada; `src/asset_servicing/application/validator.py:41`–`:47`. | ✅ PASS |
| Prompts v3 e snapshots exatos | As versões são `extractor-v3` e `validator-v3`, e o texto executado coincide exatamente com os snapshots. | `tests/contract/test_extractor_prompt.py:47`–`:48`, `:64`–`:67`; `tests/contract/test_validator_prompt.py:47`–`:48`, `:71`–`:74`. | ✅ PASS |
| Edge case: cláusula 3.2 completa | Uma única variável preserva `equânime`, `simultânea`, `proporcional` e `sem taxa de saída`. | `evals/golden/v1/granularity_fixture.yaml:3`–`:16` fixa o caso, `max_variables: 1` e os quatro fragmentos; `tests/evals/test_runner.py:160`–`:168` exige falha quando `sem taxa de saída` some. | ✅ PASS |
| Eval sem limite global | A restrição de uma variável pertence somente ao caso da cláusula 3.2; documentos normais continuam com múltiplas regras independentes. | `src/asset_servicing/evals/runner.py:374`–`:394` aplica `max_variables` a cada caso do fixture de granularidade, não a `recorded["documents"]`; `tests/evals/test_runner.py:223`–`:234` afirma `report.passed is True` para o corpus normal com múltiplas variáveis. | ✅ PASS |

**Status**: 6/6 obrigações da T29 correspondem aos resultados definidos; 0 gaps de precisão.

---

## Edge Cases

| Edge case | Evidência | Resultado |
| --- | --- | --- |
| A cláusula lista atributos coordenados da mesma ação. | `.specs/features/regulation-extraction/spec.md:230`; fixture e testes citados acima. | ✅ PASS |
| A regra possui gatilho, responsável, prazo, valor ou consequência próprios. | `.specs/features/regulation-extraction/spec.md:88`; contrato do extrator em `tests/contract/test_extractor_prompt.py:70`–`:75`. | ✅ PASS |
| O documento possui várias regras independentes. | O limite está confinado ao caso em `src/asset_servicing/evals/runner.py:374`–`:394`; o corpus multi-regra passa em `tests/evals/test_runner.py:223`–`:234`. | ✅ PASS |

---

## Gate Check

- **Comando canônico solicitado**: `uv run ruff format --check . && uv run ruff check . && uv run mypy src && uv run pytest -m "not needs_api" --cov=asset_servicing --cov-branch --cov-report=term-missing --cov-fail-under=85 -q`
- **Ruff format**: 61 arquivos já formatados.
- **Ruff check**: sem problemas.
- **mypy**: o comando literal foi bloqueado pelo Windows Application Control ao carregar o wheel compilado. A mesma versão `mypy 1.20.2` foi reinstalada do wheel oficial pure-Python e executada diretamente pelo interpretador do projeto: 27 arquivos-fonte, 0 problemas.
- **Testes offline**: 359 passed, 0 failed, 4 deselected.
- **Cobertura**: 92,54%, acima do limite de 85%.
- **Antes da T29**: 355 passed, 4 deselected.
- **Delta**: +4 testes offline; nenhum teste removido.
- **Deselecionados**: 4 cenários `needs_api`, conforme o gate canônico.
- **Diff check**: `git diff --check 3f259b1..0479fa0` sem saída.

**Resultado**: PASS ✅. A adaptação mudou somente a distribuição do mypy no ambiente local; código,
configuração e parâmetros da checagem permaneceram os mesmos.

---

## Discrimination Sensor

O sensor usou worktree detached temporário em `0479fa0`. Cada mutação foi revertida antes da
seguinte. O scratch terminou limpo, foi removido e o `git status --porcelain` da árvore real
permaneceu igual ao baseline vazio.

| Mutação | Arquivo:linha | Defeito injetado | Teste alvo e saída | Resultado |
| --- | --- | --- | --- | --- |
| M1 | `src/asset_servicing/application/extractor.py:41`–`:42` | Inverteu agrupamento para separar atributos coordenados. | `tests/contract/test_extractor_prompt.py`: 2 failed, 15 passed; snapshot e cláusula de agrupamento falharam. | ✅ Killed |
| M2 | `src/asset_servicing/evals/runner.py:384` | Fez o runner aceitar quatro variáveis fragmentadas. | `test_fragmented_coordinated_attributes_fail_granularity_gate`: falhou porque não encontrou `operational_granularity`. | ✅ Killed |
| M3 | `evals/golden/v1/granularity_fixture.yaml:11` | Removeu `sem taxa de saída` dos fragmentos exigidos. | `test_grouped_rule_missing_an_attribute_fails_granularity_gate`: falhou porque não encontrou `operational_granularity`. | ✅ Killed |

**Profundidade**: lightweight, 3 mutações nos riscos centrais da T29.
**Resultado**: 3/3 killed - PASS ✅.

---

## Code Quality

| Checagem | Resultado | Evidência |
| --- | --- | --- |
| Mudança mínima e cirúrgica | ✅ | Diff T29 limitado a prompts, contratos, fixture, runner, recording, baseline e documentação da tarefa. |
| Sem abstrações desnecessárias | ✅ | O runner adiciona um gate local ao fixture versionado e reutiliza `EvaluationFailure`. |
| Sem escopo extra | ✅ | Nenhum limite foi aplicado ao conjunto de variáveis do documento. |
| Padrões e estilo | ✅ | Ruff, mypy e `git diff --check` passaram. |
| Integridade dos testes | ✅ | +4 testes; nenhuma remoção, skip ou enfraquecimento. |
| Resultado ancorado na spec | ✅ | Asserções cobrem agrupamento, independência, snapshots, fragmentação e perda de atributo. |
| Cobertura por camada | ✅ | Contract cobre os agentes; eval cobre o resultado negativo offline. |
| Testes com reivindicação | ✅ | Todos os testes novos mapeiam para ASET-10 ou o edge case da cláusula 3.2. |
| Guidelines | ✅ | `.specs/features/regulation-extraction/tasks.md` e `references/coding-principles.md`. |

---

## Interactive UAT

Não aplicável. T29 altera contratos de prompt e avaliação offline, sem interação nova de interface.

---

## Requirement Traceability

| Requisito / caso | Status anterior | Status desta validação |
| --- | --- | --- |
| ASET-10 | Implemented (T05, T08, T29) | ✅ Verified (T29) |
| Edge case de atributos coordenados | Implemented (T29) | ✅ Verified (T29) |

---

## Summary

**Overall**: ✅ Ready.
**Spec-anchored check**: 6/6 obrigações; 0 gaps de precisão.
**Gate**: Ruff verde, mypy 27 arquivos sem problemas, 359 passed, 4 deselected, 92,54%.
**Sensor**: 3/3 mutações mortas; isolamento confirmado.
**Lessons**: nenhuma nova lesson registrada, pois o PASS foi limpo.

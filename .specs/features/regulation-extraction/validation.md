# Validation: Regulation Extraction - PASS ✅

**Verdict**: PASS ✅
**Date**: 2026-09-29
**Spec**: `.specs/features/regulation-extraction/spec.md`
**Diff range**: `2a48935..bb5ed8d`
**Verifier**: independent sub-agent (author ≠ verifier)

Os 54 requisitos P1 têm evidência executável ancorada no resultado definido pela especificação. As quatro lacunas da primeira verificação foram fechadas por T22–T25. O Build gate canônico passou com 344 testes offline, 0 falhas, 4 cenários `needs_api` excluídos por desenho e 92,71% de cobertura. O sensor fresco matou 3/3 mutações diretamente ligadas às correções. ASET-55–57 permanecem explicitamente postergados como P3 e não entram neste veredito.

---

## Task Completion

| Escopo | Status | Evidência |
| --- | --- | --- |
| T01–T21 | ✅ Done | Todos os Done-when permanecem marcados em `tasks.md`. |
| T22 | ✅ Done | Timestamp e payload completo em `tests/integration/test_pipeline.py:206`–`:212`. |
| T23 | ✅ Done | Novo `run_id` e histórico anterior preservado em `tests/integration/test_pipeline.py:229`–`:234`. |
| T24 | ✅ Done | Dois nomes iguais preservam ids/valores/evidências/páginas distintos em `tests/unit/application/test_extractor.py:137`. |
| T25 | ✅ Done | Falha de persistência antecede o provider e mantém o estado durável em `tests/integration/test_pipeline.py:428`–`:433`. |

**Status**: 25/25 tarefas concluídas; nenhuma bloqueada ou parcial.

---

## Structural Validation

| Comando | Saída | Resultado |
| --- | --- | --- |
| `python C:\Users\yagop\.agents\skills\tlc-spec-driven\scripts\validate_spec.py .specs\features\regulation-extraction\spec.md` | `0 error(s), 0 warning(s)` | ✅ PASS |
| `python C:\Users\yagop\.agents\skills\tlc-spec-driven\scripts\validate_tasks.py .specs\features\regulation-extraction\tasks.md` | `0 error(s), 0 warning(s)` | ✅ PASS |
| `git diff --check 2a48935..bb5ed8d` | exit 0, sem saída | ✅ PASS |

O arquivo `plan.md` citado no pedido não existe. O plano técnico vigente é `design.md`, referenciado por `tasks.md`; ele foi lido integralmente junto com `context.md`.

---

## Spec-Anchored Acceptance Criteria

Evidence-or-zero foi aplicado aos 54 critérios P1. Cada PASS abaixo aponta para uma asserção de valor/estado compatível com o resultado EARS, e não apenas para a existência de um teste.

| AC | Resultado definido pela spec | `file:line` + asserção | Resultado |
| --- | --- | --- | --- |
| ASET-01 | Criar execução com id, hash, nome, páginas e instante. | `tests/integration/test_pipeline.py:206`–`:212` — valores exatos, incluindo `created_at == datetime(2026, 9, 28, 12, 0, tzinfo=UTC)`. | ✅ PASS |
| ASET-02 | Rejeitar cada condição inválida com motivo específico. | `tests/integration/test_pdf_processor.py:84`, `:94`, `:104`, `:118`, `:135` — códigos `not_pdf`, `unreadable`, `encrypted`, `too_large`, `too_many_pages`. | ✅ PASS |
| ASET-03 | Localização semântica, sem capítulo/página/título fixos. | `tests/contract/test_locator_prompt.py:53`, `:59`–`:60`, `:66`–`:68`. | ✅ PASS |
| ASET-04 | Exibir título, páginas inicial/final e justificativa. | `tests/unit/application/test_locator.py:64` e `tests/ui/test_document_location_ui.py:130`–`:132`. | ✅ PASS |
| ASET-05 | Mostrar prévia e aceitar correção manual do intervalo. | `tests/ui/test_document_location_ui.py:181`–`:182`, `:202`–`:203`. | ✅ PASS |
| ASET-06 | Bloquear extração antes da confirmação. | `tests/integration/test_pipeline.py:254`–`:257` e `tests/ui/test_document_location_ui.py:190`. | ✅ PASS |
| ASET-07 | Manter not-found recuperável com intervalo manual. | `tests/unit/application/test_locator.py:89`–`:91`; `tests/ui/test_document_location_ui.py:227`–`:230`; `tests/integration/test_pipeline.py:370`–`:374`. | ✅ PASS |
| ASET-08 | Enviar somente páginas confirmadas e tratar PDF como dado não confiável. | `tests/integration/test_pipeline.py:286`–`:291`; `tests/unit/application/test_extractor.py:215`, `:224`; `tests/contract/test_extractor_prompt.py:51`–`:52`. | ✅ PASS |
| ASET-09 | Registrar todos os campos e evidência de cada variável. | `tests/unit/application/test_extractor.py:71` e `tests/contract/test_llm_contracts.py:192`–`:197`. | ✅ PASS |
| ASET-10 | Separar fatos independentes. | `tests/unit/application/test_extractor.py:101`. | ✅ PASS |
| ASET-11 | Usar nome canônico quando houver vocabulário preferencial. | `tests/unit/application/test_extractor.py:71`, `:202`. | ✅ PASS |
| ASET-12 | Permitir nome semântico novo fora do vocabulário. | `tests/unit/application/test_extractor.py:187`–`:188`. | ✅ PASS |
| ASET-13 | Conteúdo vem da LLM, sem regex/regra determinística. | `tests/unit/application/test_extractor.py:101`, `:187`–`:188`; revisão estática de `src/asset_servicing/application/extractor.py:83`–`:107`. | ✅ PASS |
| ASET-14 | Validar estrutura antes de persistir variáveis. | `tests/contract/test_llm_contracts.py:201`, `:218`; `tests/contract/test_openai_adapter.py:409`–`:415`; `tests/integration/test_pipeline.py:329`–`:334`. | ✅ PASS |
| ASET-15 | Extrair texto corrido sem tabela. | `tests/unit/application/test_extractor.py:170`–`:173`; `tests/contract/test_extractor_prompt.py:94`. | ✅ PASS |
| ASET-16 | Validar em chamada separada do extrator. | `tests/smoke/test_live_pipeline.py:173`; `tests/ui/test_complete_journey.py:202`–`:203`. | ✅ PASS |
| ASET-17 | Validador recebe valor/fonte, não julgamento do extrator. | `tests/unit/application/test_validator.py:252`–`:263`; `tests/contract/test_llm_contracts.py:238`–`:248`. | ✅ PASS |
| ASET-18 | Registrar score, enum de veredito, justificativa e problemas. | `tests/unit/application/test_validator.py:124`; `tests/unit/domain/test_models.py:147`, `:158`. | ✅ PASS |
| ASET-19 | Registrar omissões possíveis. | `tests/unit/application/test_validator.py:167`. | ✅ PASS |
| ASET-20 | Score abaixo de 0,85 entra em revisão; 0,85 não. | `tests/unit/application/test_validator.py:211`; `tests/unit/domain/test_models.py:246`. | ✅ PASS |
| ASET-21 | Veredito parcial/não suportado entra em revisão independentemente do score. | `tests/unit/domain/test_models.py:254`; `tests/unit/application/test_validator.py:211`. | ✅ PASS |
| ASET-22 | Conflito/omissão cria pendência sem alterar extração. | `tests/unit/application/test_validator.py:221`–`:225`, `:238`; `tests/unit/domain/test_models.py:271`–`:273`. | ✅ PASS |
| ASET-23 | Tratar confiança como rubrica LLM, não probabilidade calibrada. | `tests/contract/test_validator_prompt.py:65`; `tests/unit/domain/test_models.py:177`–`:178`. | ✅ PASS |
| ASET-24 | Visão geral contém todas; fila contém apenas pendências. | `tests/ui/test_review_ui.py:121`–`:123`, `:166`–`:171`. | ✅ PASS |
| ASET-25 | Pendência mostra nome, valor, evidência imutável, página, score, veredito e justificativa. | `tests/ui/test_review_ui.py:177`–`:182`, `:190`–`:191`. | ✅ PASS |
| ASET-26 | Confirmar mantém nome/valor e marca revisada. | `tests/ui/test_review_ui.py:202`–`:205`. | ✅ PASS |
| ASET-27 | Editar altera vigente, preserva original e marca revisada. | `tests/ui/test_review_ui.py:221`–`:228`. | ✅ PASS |
| ASET-28 | Não aplicável é auditado, sai da fila e preserva registro. | `tests/ui/test_review_ui.py:242`–`:248`. | ✅ PASS |
| ASET-29 | Aceitar omissão cria variável manual com evidência. | `tests/ui/test_review_ui.py:280`–`:287`. | ✅ PASS |
| ASET-30 | `reviewed=True` somente após ação humana. | `tests/ui/test_review_ui.py:156`–`:158`, `:203`. | ✅ PASS |
| ASET-31 | Decisão persiste atomicamente antes/depois/ação/instante/estado. | `tests/unit/application/test_review_service.py:104`–`:108`; `tests/integration/test_review_persistence.py:135`–`:141`. | ✅ PASS |
| ASET-32 | Reabrir restaura páginas, extração, validação e revisões. | `tests/integration/test_review_persistence.py:107`–`:119`. | ✅ PASS |
| ASET-33 | Preliminar disponível com variável validada e pendências. | `tests/ui/test_delivery_ui.py:210`–`:216`; `tests/integration/test_excel_export.py:113`–`:115`. | ✅ PASS |
| ASET-34 | Final bloqueado enquanto há pendências e mostra contagem. | `tests/ui/test_delivery_ui.py:239`–`:242`; `tests/integration/test_excel_export.py:124`–`:127`. | ✅ PASS |
| ASET-35 | Final disponível quando não há pendências. | `tests/ui/test_delivery_ui.py:259`–`:269`; `tests/integration/test_excel_export.py:147`–`:148`. | ✅ PASS |
| ASET-36 | Aba principal tem exatamente cinco colunas na ordem exigida. | `tests/integration/test_excel_export.py:157`–`:164`. | ✅ PASS |
| ASET-37 | Variável editada exporta nome/valor vigentes e evidência original. | `tests/integration/test_excel_export.py:229`–`:230`. | ✅ PASS |
| ASET-38 | Confiança numérica [0,1] e revisão booleana. | `tests/integration/test_excel_export.py:176`–`:179`. | ✅ PASS |
| ASET-39 | Auditoria inclui documento/hash/páginas/modelos/prompts/tempos/uso/revisão. | `tests/integration/test_excel_export.py:256`–`:260`, `:273`–`:276`, `:301`–`:303`. | ✅ PASS |
| ASET-40 | Workbook fica no diretório da execução e é baixável. | `tests/ui/test_delivery_ui.py:213`–`:216`, `:266`–`:269`. | ✅ PASS |
| ASET-41 | Retry transitório limitado a três e último estágio preservado. | `tests/contract/test_openai_adapter.py:309`–`:312`, `:328`–`:332`; `tests/integration/test_pipeline.py:346`–`:354`. | ✅ PASS |
| ASET-42 | Refusal/incomplete/schema inválido marca falha e permite retry explícito. | `tests/contract/test_openai_adapter.py:377`–`:415`; `tests/ui/test_complete_journey.py:318`–`:325`. | ✅ PASS |
| ASET-43 | Persistir etapa antes da seguinte/chamada externa. | `tests/integration/test_pipeline.py:401` e `:289`–`:304`. | ✅ PASS |
| ASET-44 | Rerun substitui somente estágio e invalida dependentes. | `tests/integration/test_pipeline.py:455`–`:459`, `:485`–`:488`, `:521`–`:524`. | ✅ PASS |
| ASET-45 | Recusar chamada concorrente na mesma execução. | `tests/integration/test_pipeline.py:548`–`:558`. | ✅ PASS |
| ASET-46 | Eventos estruturados contêm campos operacionais e erro sanitizado. | `tests/integration/test_json_repository.py:157`–`:162`; `tests/integration/test_pipeline.py:568`–`:580`, `:592`–`:599`. | ✅ PASS |
| ASET-47 | Segredo não persiste em logs/estado/fixtures/Excel/mensagens. | `tests/contract/test_openai_adapter.py:355`–`:357`; `tests/integration/test_json_repository.py:228`, `:244`; `tests/smoke/test_live_pipeline.py:206`–`:208`; `tests/contract/test_ui_runtime.py:133`. | ✅ PASS |
| ASET-48 | Suíte unit/contract/offline sem chave nem rede. | Build canônico: 344 passed, 4 `needs_api` deselected, 0 failed; contrato em `tests/contract/test_project_contract.py:46`–`:53`. | ✅ PASS |
| ASET-49 | Golden set versionado cobre quatro PDFs por hash e evidência. | `tests/evals/test_golden_set.py:64`–`:65`, `:106`–`:107`, `:150`–`:157`. | ✅ PASS |
| ASET-50 | Mudança de contrato exige relatório comparável ao baseline. | `tests/evals/test_runner.py:200`–`:211`, `:226`–`:230`, `:239`–`:240`. | ✅ PASS |
| ASET-51 | Cenário equivalente no Capítulo 6/páginas diferentes. | `tests/evals/test_runner.py:102`–`:105`; `tests/unit/application/test_locator.py:125`–`:127`. | ✅ PASS |
| ASET-52 | 100% dos adversariais contraditórios/sem suporte vão para revisão. | `tests/evals/test_runner.py:126`–`:129`; `tests/unit/application/test_validator.py:187`. | ✅ PASS |
| ASET-53 | 100% das evidências resolvem no PDF/página declarados. | `tests/evals/test_golden_set.py:178`; `tests/evals/test_runner.py:78`–`:81`. | ✅ PASS |
| ASET-54 | Smoke real opt-in separado da suíte offline. | `tests/smoke/test_live_pipeline.py:211`–`:224`; Build excluiu exatamente os 4 cenários `needs_api`. | ✅ PASS |

**Status**: 54/54 ACs P1 correspondem ao resultado definido pela spec; 0 ACs sem evidência; 0 spec-precision gaps.

**Escopo postergado**: ASET-55–57 são P3, permanecem `Pending` e não foram avaliados como P1.

---

## Edge Cases

| Edge case | Evidência | Resultado |
| --- | --- | --- |
| Tabela multipágina preserva rótulo/valor/páginas. | `tests/unit/application/test_extractor.py:71` afirma payload completo com páginas `[12, 13]`. | ✅ PASS |
| Nomes semânticos duplicados permanecem registros distintos. | `tests/unit/application/test_extractor.py:137` afirma dois ids, valores, evidências e páginas distintos sob o mesmo nome. | ✅ PASS |
| Evidência ausente cria pendência. | `tests/unit/application/test_validator.py:187` afirma os adversariais e a omissão na fila. | ✅ PASS |
| Camada textual ausente usa representação visual. | `tests/contract/test_openai_adapter.py:222` exige PDF com `detail == "high"` sem pré-requisito de texto. | ✅ PASS |
| Alterar páginas invalida resultados posteriores. | `tests/unit/domain/test_models.py:343`–`:350` afirma limpeza de variáveis, validações, achados, revisões e exports. | ✅ PASS |
| Persistência indisponível interrompe antes da chamada paga. | `tests/integration/test_pipeline.py:428`–`:433` afirma exceção, zero requests e estado durável `created`. | ✅ PASS |
| Reprocessar execução concluída cria novo histórico. | `tests/integration/test_pipeline.py:229`–`:234` afirma `run-002`, preservação exata de `run-001` e ambos os PDFs. | ✅ PASS |

**Status**: 7/7 edge cases cobertos.

---

## Gate Check

- **Comando canônico**: `uv run ruff format --check . && uv run ruff check . && uv run mypy src && uv run pytest -m "not needs_api" --cov=asset_servicing --cov-branch --cov-report=term-missing --cov-fail-under=85 -q`
- **Formatação**: `61 files already formatted`.
- **Ruff**: `All checks passed!`.
- **mypy**: `Success: no issues found in 27 source files`.
- **Testes**: 344 passed, 0 failed, 4 deselected.
- **Cobertura**: 92,71% (limite 85%).
- **Coleta total**: 348 cenários (`uv run pytest --collect-only -q`).
- **Antes da feature**: 0 arquivos de teste em `2a48935` (`git ls-tree -r --name-only 2a48935 -- tests`).
- **Delta**: +348 cenários coletados.
- **Skips/xfails**: nenhum na suíte offline; a única chamada `pytest.skip` está em `tests/smoke/test_live_pipeline.py:216` e implementa o smoke real opt-in quando falta configuração.

**Resultado**: PASS ✅

---

## Discrimination Sensor

O sensor usou um worktree temporário detached em `bb5ed8d`, separado da árvore real. Cada mutação foi revertida antes da seguinte. Os testes foram executados com `PYTHONPATH` apontando para o `src` do scratch e com o Python do ambiente virtual do projeto.

| Mutação | Arquivo:linha | Defeito injetado | Teste alvo e saída | Resultado |
| --- | --- | --- | --- | --- |
| M1 | `src/asset_servicing/application/pipeline.py:154` | Substituiu o clock injetado pelo epoch de 1970. | `test_create_run_persists_metadata_and_restartable_source`: 1 failed; asserção em `tests/integration/test_pipeline.py:211`. | ✅ Killed |
| M2 | `src/asset_servicing/application/extractor.py:106` | Truncou a resposta para a primeira variável, descartando o segundo nome duplicado. | `test_duplicate_semantic_names_remain_distinct_until_review`: 1 failed; asserção em `tests/unit/application/test_extractor.py:137`. | ✅ Killed |
| M3 | `src/asset_servicing/application/pipeline.py:167` | Moveu `save_run(LOCATING)` para depois da chamada ao localizador. | `test_persistence_failure_stops_before_the_provider_call`: 1 failed; `locate_requests` deixou de ser vazio em `tests/integration/test_pipeline.py:431`. | ✅ Killed |

**Profundidade**: lightweight, 3 mutações de comportamento nos riscos corrigidos por T22, T24 e T25.

**Resultado**: 3/3 killed, 0 survived — PASS ✅

**Isolamento**: o baseline e o status após a remoção do scratch foram idênticos:

```text
?? .specs/LESSONS.md
?? .specs/features/regulation-extraction/validation.md
?? .specs/lessons.json
```

O worktree temporário criado por esta verificação foi removido. Nenhum código-fonte ou teste da árvore real foi alterado.

---

## EARS and Traceability Review

- `validate_spec.py` aceitou a especificação com 0 erros e 0 avisos.
- Os 54 requisitos P1 têm forma testável e resultado preciso; não há spec-precision gap.
- ASET-55–57 estão claramente condicionados/postergados como P3.
- A matriz de `tasks.md` liga ASET-01–54 a T01–T22. T23–T25 ligam-se explicitamente aos três edge cases restantes.
- A tabela de status em `spec.md` ainda chama ASET-14, ASET-42 e ASET-47 de `Partial`, embora as evidências acima os verifiquem integralmente. Isto é drift documental não bloqueante; esta validação registra os três como verificados, sem alterar a spec.
- Os checkboxes de Goals/Success Criteria continuam funcionando como memória de produto, não como status de AC. O gate offline prova os critérios automatizáveis; a execução credenciada externa continua opt-in.

### Requirement Traceability Update

| Requisito | Status anterior na spec | Status desta validação |
| --- | --- | --- |
| ASET-01 | Implemented | ✅ Verified, incluindo timestamp exato |
| ASET-02–13 | Implemented | ✅ Verified |
| ASET-14 | Partial | ✅ Verified |
| ASET-15–41 | Implemented | ✅ Verified |
| ASET-42 | Partial | ✅ Verified |
| ASET-43–46 | Implemented | ✅ Verified |
| ASET-47 | Partial | ✅ Verified |
| ASET-48–54 | Implemented | ✅ Verified |
| ASET-55–57 | Pending P3 | Deferred, fora do veredito P1 |

---

## Code Quality and Risk Review

| Checagem | Resultado | Evidência / risco residual |
| --- | --- | --- |
| Mudança mínima e cirúrgica | ✅ | T22–T25 alteram apenas testes e artefatos SDD; nenhum código de produção foi mudado após o primeiro FAIL. |
| Integridade dos testes | ✅ | Nenhum teste base foi removido; 348 coletados; nenhum skip/xfail offline; 3/3 mutantes mortos. |
| Payload/conjunction rule | ✅ | T22 afirma individualmente id, nome, hash, páginas e timestamp. T24 afirma todos os campos de ambos os registros. T25 afirma exceção + zero requests + estado durável. |
| Cobertura por camada | ✅ | Build em 92,71%; domínio 100%; pipeline 99%; suíte inclui unit, contract, integration, UI e eval. |
| Sem escopo extra | ✅ | Busca natural P3 permanece desabilitada/postergada. |
| Guidelines | ✅ | `tasks.md`, `design.md` e `references/coding-principles.md`; `git diff --check` passou. |

### Riscos residuais não bloqueantes

1. O smoke real credenciado não foi executado neste gate; ASET-54 exige disponibilidade opt-in, não sucesso permanente contra uma API externa mutável.
2. O corpus real tem quatro documentos e usa gravações offline; a própria spec reconhece o limite de generalização.
3. Há drift documental nos status `Partial` de ASET-14/42/47 e ausência de `plan.md`; `design.md` é o plano efetivo.

Nenhum risco residual contradiz um AC P1 ou sobreviveu ao Build/sensor.

---

## Lessons

O PASS atual não contém novo sinal (`ac_gap`, `surviving_mutant`, `spec_precision_gap`, `spec_deviation` ou `gate_fail`). Portanto, `.specs/LESSONS.md` e `.specs/lessons.json` foram preservados sem alteração. A lição candidata existente L-001 continua fundamentada no FAIL da primeira rodada.

---

## Summary

**Overall**: ✅ Ready para o escopo P1 definido.

- **Tasks**: 25/25 concluídas.
- **Spec-anchored check**: 54/54 ACs P1; 0 gaps; 0 spec-precision gaps.
- **Edge cases**: 7/7 cobertos.
- **Structural validators**: 2/2 passaram sem erros ou avisos.
- **Build gate**: 344 passed, 0 failed, 4 `needs_api` deselected; 92,71% coverage.
- **Sensor**: 3/3 mutações mortas; 0 sobreviventes.
- **P3**: 3 requisitos postergados (ASET-55–57), fora do veredito.
- **Lacunas bloqueantes**: nenhuma.

# Extração e Revisão de Regulamentos - Tarefas P1

## Execution Protocol (MANDATORY -- do not skip)

Implementar estas tarefas com a skill `tlc-spec-driven`: ativá-la por nome e seguir o fluxo Execute e suas Critical Rules. Cada tarefa usa red-green com a skill `tdd`, atualiza este arquivo antes do commit e termina em um único commit Conventional Commit.

Se `tlc-spec-driven` não puder ser ativada, interromper a execução e informar o usuário. Nenhum `push` é autorizado por este plano.

---

**Design:** `.specs/features/regulation-extraction/design.md`
**Status:** P1 refinado após UAT — T29 concluída e aprovada por verificação independente

---

## Confirmed Test Seams

A aprovação deste arquivo confirma estes seams públicos para TDD:

| Seam | Interface observada | Evita testar |
| --- | --- | --- |
| Domínio | Métodos públicos de `Run`, `ExtractedVariable` e serviço de revisão | Campos privados e detalhes de serialização |
| Aplicação | Casos de uso do pipeline com portas falsas | Ordem interna de helpers e chamadas privadas |
| LLM | Protocolo `LLMProvider` e adapter por transporte mockado | Internos do SDK do provedor |
| Arquivos | `PdfProcessor`, `JsonRunRepository` e `ExcelExporter` em diretório temporário | Implementação interna das bibliotecas |
| Interface | Widgets, estados visíveis e downloads do Streamlit | Estrutura interna de componentes |
| Avaliação | Comando público de eval e relatório produzido | Funções auxiliares do harness |

## Test Coverage Matrix

> Gerada a partir de `.specs/features/regulation-extraction/spec.md` e `.specs/features/regulation-extraction/design.md`. Não existem testes ou configuração de qualidade no repositório; os defaults fortes foram aplicados e os comandos abaixo serão instalados por T01.

| Code Layer | Required Test Type | Coverage Expectation | Location Pattern | Run Command |
| --- | --- | --- | --- | --- |
| Domínio e regras de estado | unit | Todos os ramos; relação 1:1 com ACs e edge cases aplicáveis | `tests/unit/domain/test_*.py` | `uv run pytest -m unit -q` |
| Casos de uso da aplicação | unit + integration | Caminho feliz, estados inválidos, repetição e falhas parciais | `tests/unit/application/test_*.py`, `tests/integration/test_pipeline.py` | `uv run pytest -m "unit or integration" -q` |
| Schemas e portas LLM | contract | Campos obrigatórios, enums, limites, refusal e payload incompatível | `tests/contract/test_llm_*.py` | `uv run pytest -m contract -q` |
| Adapter OpenAI | contract | Payload, parse, retry, uso, erro sanitizado e ausência de segredo | `tests/contract/test_openai_adapter.py` | `uv run pytest -m contract -q` |
| PDF, persistência e Excel | integration | PDFs reais/fixtures, I/O temporário, retomada, tipos e erros | `tests/integration/test_*.py` | `uv run pytest -m integration -q` |
| Streamlit | ui | Todos os fluxos P1: feliz, pendência, erro, retomada e downloads | `tests/ui/test_*.py` | `uv run pytest -m ui -q` |
| Golden set e evals | eval | Integridade 100%, campos críticos 100%, adversariais 100% e Capítulo 6 1/1 | `tests/evals/test_*.py` | `uv run pytest -m eval -q` |
| Smoke real | needs_api | Uma execução completa opt-in, nunca no gate offline | `tests/smoke/test_live_pipeline.py` | `uv run pytest -m needs_api -q` |
| Configuração e documentação | contract | Comandos existem, marcadores são registrados e instruções são reproduzíveis | `tests/contract/test_project_contract.py` | `uv run pytest -m contract -q` |

## Gate Check Commands

> Comandos canônicos do projeto, instalados por T01 e confirmados nesta aprovação.

| Gate Level | When to Use | Command |
| --- | --- | --- |
| Quick | Após tarefas com testes unitários ou de contrato | `uv run pytest -m "unit or contract" -q` |
| Full | Após tarefas de integração, UI ou eval | `uv run pytest -m "not needs_api" -q` |
| Build | Ao concluir cada fase e em tarefas de configuração | `uv run ruff format --check . && uv run ruff check . && uv run mypy src && uv run pytest -m "not needs_api" --cov=asset_servicing --cov-branch --cov-report=term-missing --cov-fail-under=85 -q` |
| Live | Somente quando o usuário disponibilizar credencial para smoke real | `uv run pytest -m needs_api -q` |

---

## Execution Plan

As fases são sequenciais. Cada fase termina com o gate Build verde antes da próxima começar.

### Phase 1: Foundation and Boundaries

```text
T01 -> T02 -> T03 -> T04 -> T05 -> T06
```

### Phase 2: Agentic Core

```text
T07 -> T08 -> T09 -> T10 -> T11
```

### Phase 3: Human Loop and Delivery

```text
T12 -> T13 -> T14 -> T15
```

### Phase 4: Evidence and Handoff

```text
T16 -> T17 -> T18 -> T19 -> T20 -> T21 -> T22 -> T23 -> T24 -> T25
```

### Phase 5: UAT Corrections

```text
T26 -> T27 -> T28 -> T29
```

---

## Task Breakdown

### Phase 1: Foundation and Boundaries

#### T01: Bootstrap Python and quality gates

**What:** Criar o projeto Python com `uv`, pacote `src`, dependências fixadas, marcadores pytest, Ruff, mypy estrito, coverage e contrato executável dos comandos.
**Where:** project root and `pyproject.toml`
**Depends on:** None
**Reuses:** Gates definidos no desenho e padrão observado em `production_rag`.
**Requirement:** ASET-48

**Tools:**

- MCP: NONE
- Skills: `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] O contrato executável cobre o bootstrap e passa depois da configuração.
- [x] `uv sync --group dev` cria ambiente reproduzível e lockfile.
- [x] Todos os marcadores da matriz estão registrados.
- [x] Quick, Full e Build existem como comandos documentados e executáveis.
- [x] Gate Build passa.
- [x] Test count: 4 testes de contrato do projeto passam.

**Tests:** contract
**Gate:** build
**Commit:** `chore: bootstrap Python project`

#### T02: Define domain records and run state machine

**What:** Implementar os modelos Pydantic do domínio, enums e transições válidas da execução, incluindo invariantes de confiança, revisão e invalidação.
**Where:** `src/asset_servicing/domain/models.py`
**Depends on:** T01
**Reuses:** Modelos e diagrama de estados do desenho.
**Requirement:** ASET-09, ASET-18, ASET-20–23, ASET-30, ASET-34–35, ASET-38, ASET-44–45

**Tools:**

- MCP: NONE
- Skills: `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Testes começam vermelhos para transições permitidas e proibidas.
- [x] Confidence fora de `0..1`, enum inválido e evidência vazia são rejeitados.
- [x] Alterar páginas invalida todos os artefatos posteriores.
- [x] `pending_items()` cobre score, veredito, conflito e omissão.
- [x] Gate Quick passa.
- [x] Test count: 55 testes unitários de domínio passam.

**Tests:** unit
**Gate:** quick
**Commit:** `feat(domain): define extraction models`

#### T03: Persist run state atomically

**What:** Implementar repositório JSON/JSONL por execução com escrita temporária, `os.replace`, cópia do PDF-fonte, reidratação e eventos sanitizados.
**Where:** `src/asset_servicing/adapters/persistence/json_repository.py`
**Depends on:** T02
**Reuses:** Layout `data/runs/<run_id>/` definido no desenho.
**Requirement:** ASET-01, ASET-31–32, ASET-43, ASET-46–47

**Tools:**

- MCP: NONE
- Skills: `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Testes de integração falham antes da implementação.
- [x] Save/load preserva todos os modelos e revisões.
- [x] Falha antes de `os.replace` mantém o último estado válido.
- [x] Eventos JSONL carregam `run_id`, estágio, duração, modelo, uso e erro sanitizado.
- [x] Uma chave sentinela não aparece em estado, eventos ou mensagens.
- [x] Gate Full passa.
- [x] Test count: 12 testes de integração passam.

**Tests:** integration
**Gate:** full
**Commit:** `feat(storage): persist run state`

#### T04: Validate, inspect, render, and select PDF pages

**What:** Implementar o adapter PDF para validar entrada, calcular hash, contar páginas, renderizar prévias e produzir bytes do intervalo confirmado sem interpretar o domínio.
**Where:** `src/asset_servicing/adapters/pdf/processor.py`
**Depends on:** T03
**Reuses:** Os quatro PDFs em `Regulamentos/` e limites definidos na especificação.
**Requirement:** ASET-01–02, ASET-05, ASET-08, ASET-53

**Tools:**

- MCP: NONE
- Skills: `pdf`, `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Testes cobrem PDF válido, não PDF, criptografado, ilegível, 50 MB e 200 páginas.
- [x] Hash e contagem de páginas são reproduzíveis para os quatro documentos.
- [x] A seleção preserva ordem e numeração original das páginas.
- [x] Prévia visual é gerada em diretório temporário e não versionado.
- [x] O adapter não contém regex ou regras de extração de conteúdo.
- [x] Gate Full passa.
- [x] Test count: 17 testes de integração passam.

**Tests:** integration
**Gate:** full
**Commit:** `feat(pdf): process regulation pages`

#### T05: Define LLM ports and structured contracts

**What:** Definir a porta `LLMProvider`, requests e responses estritos para localizador, extrator e validador, mantendo os três contratos separados.
**Where:** `src/asset_servicing/ports/llm.py`
**Depends on:** T04
**Reuses:** Schemas e separação de agentes do desenho.
**Requirement:** ASET-04, ASET-09–10, ASET-14, ASET-17–19

**Tools:**

- MCP: NONE
- Skills: `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Testes de contrato começam vermelhos para campos ausentes e enums inválidos.
- [x] Cada agente possui request e response próprios.
- [x] O request do validador não possui campo de raciocínio ou confiança do extrator.
- [x] Os schemas representam localização, variáveis atômicas, validações e omissões.
- [x] Gate Quick passa.
- [x] Test count: 27 testes de contrato passam.

**Tests:** contract
**Gate:** quick
**Commit:** `feat(llm): define agent contracts`

#### T06: Add resilient OpenAI adapter

**What:** Implementar o adapter Responses API com PDF multimodal, Structured Outputs, configuração independente de modelos, usage, refusal, timeout e retry limitado.
**Where:** `src/asset_servicing/adapters/llm/openai_responses.py`
**Depends on:** T05
**Reuses:** Porta LLM e orientação oficial registrada no desenho.
**Requirement:** ASET-41–42, ASET-46–48, ASET-54

**Tools:**

- MCP: official OpenAI documentation via web
- Skills: `openai-docs`, `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Testes mockados começam vermelhos para sucesso, refusal, schema inválido, timeout, rate limit e erro não transitório.
- [x] Timeout, rate limit e rede tentam no máximo três vezes com backoff injetável.
- [x] Refusal e resposta incompleta não são persistidas como sucesso.
- [x] Modelos e versões de prompt são configuráveis sem chave no código.
- [x] Logs e exceções não expõem chave ou header de autorização.
- [x] Gate Build da Phase 1 passa.
- [x] Test count: 18 testes de contrato passam.

**Tests:** contract
**Gate:** build
**Commit:** `feat(llm): add resilient OpenAI adapter`

### Phase 2: Agentic Core

#### T07: Locate the semantic regulation section

**What:** Implementar o caso de uso e prompt versionado do localizador, com capítulo opcional, retorno estruturado e fallback para seleção manual.
**Where:** `src/asset_servicing/application/locator.py`
**Depends on:** T06
**Reuses:** `LLMProvider`, `PdfProcessor` e cenário de Capítulo 6 da especificação.
**Requirement:** ASET-03–07, ASET-51

**Tools:**

- MCP: NONE
- Skills: `openai-docs`, `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Um fixture com seção equivalente no Capítulo 6 falha antes da implementação e passa depois.
- [x] O prompt busca significado e não fixa capítulo, título literal ou página.
- [x] Capítulo opcional orienta sem restringir a resposta.
- [x] Ausência de seção produz estado recuperável para intervalo manual.
- [x] Gate Quick passa.
- [x] Test count: 20 testes unitários/contrato passam.

**Tests:** unit + contract
**Gate:** quick
**Commit:** `feat(locator): locate regulation sections`

#### T08: Extract atomic variables from confirmed pages

**What:** Implementar o agente extrator com prompt versionado, vocabulário preferencial, nomes dinâmicos, atomicidade e proteção contra instruções presentes no PDF.
**Where:** `src/asset_servicing/application/extractor.py`
**Depends on:** T07
**Reuses:** Porta LLM, páginas confirmadas e modelo híbrido aprovado.
**Requirement:** ASET-08–15

**Tools:**

- MCP: NONE
- Skills: `openai-docs`, `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Fixtures cobrem tabela multipágina, célula com dois fatos, texto sem tabela e regra fora do vocabulário.
- [x] Toda variável contém nome, valor, evidência, páginas, origem e cláusula opcional.
- [x] Fatos independentes saem como registros independentes.
- [x] O prompt trata o documento como dado e ignora instruções nele contidas.
- [x] Nenhuma regex ou regra determinística produz o conteúdo extraído.
- [x] Gate Quick passa.
- [x] Test count: 22 testes unitários/contrato passam.

**Tests:** unit + contract
**Gate:** quick
**Commit:** `feat(extractor): extract atomic variables`

#### T09: Validate variables and route uncertainty

**What:** Implementar o agente validador independente, a rubrica de confiança, a detecção de omissões e o roteamento para revisão.
**Where:** `src/asset_servicing/application/validator.py`
**Depends on:** T08
**Reuses:** Variáveis extraídas, fonte confirmada e threshold `0,85`.
**Requirement:** ASET-16–23, ASET-52

**Tools:**

- MCP: NONE
- Skills: `openai-docs`, `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Testes começam vermelhos para correto, ambíguo, contraditório, sem suporte e omissão.
- [x] O validador executa em chamada separada e não recebe raciocínio ou score do extrator.
- [x] Score abaixo de `0,85`, veredito não suportado, conflito e omissão criam pendência.
- [x] O validador nunca altera automaticamente nome ou valor extraído.
- [x] 100% dos casos adversariais mínimos entram na revisão.
- [x] Gate Quick passa.
- [x] Test count: 31 testes unitários/contrato passam.

**Tests:** unit + contract
**Gate:** quick
**Commit:** `feat(validator): score extracted variables`

#### T10: Orchestrate resumable pipeline stages

**What:** Implementar o pipeline que cria execuções, coordena estágios, persiste antes de avançar, impede concorrência e invalida dependentes em reruns.
**Where:** `src/asset_servicing/application/pipeline.py`
**Depends on:** T09
**Reuses:** Domínio, repositório, PDF e três casos de uso agentic.
**Requirement:** ASET-01, ASET-06–08, ASET-16, ASET-24, ASET-41–46

**Tools:**

- MCP: NONE
- Skills: `observability-and-instrumentation`, `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Testes de integração começam vermelhos para fluxo feliz, falha e retomada de cada estágio.
- [x] Cada estágio válido é persistido antes do próximo.
- [x] Rerun substitui apenas o estágio solicitado e invalida seus dependentes.
- [x] Uma segunda chamada concorrente para a mesma execução é recusada.
- [x] Eventos estruturados medem duração, modelo, prompt, páginas, uso e resultado.
- [x] Gate Full passa.
- [x] Test count: 20 testes de integração passam.

**Tests:** integration
**Gate:** full
**Commit:** `feat(pipeline): orchestrate extraction runs`

#### T11: Record auditable human review decisions

**What:** Implementar o serviço de revisão para confirmar, editar, marcar não aplicável, aceitar omissão e reabrir uma execução sem alterar a evidência original.
**Where:** `src/asset_servicing/application/review_service.py`
**Depends on:** T10
**Reuses:** Modelos de domínio e repositório atômico.
**Requirement:** ASET-24–32

**Tools:**

- MCP: NONE
- Skills: `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Testes começam vermelhos para as quatro ações e entradas inválidas.
- [x] Somente ação humana explícita define `reviewed=True`.
- [x] Nome/valor originais e evidência permanecem imutáveis.
- [x] A auditoria registra antes, depois, ação, nota e instante.
- [x] Reabrir a execução restaura a fila e as decisões.
- [x] Gate Build da Phase 2 passa.
- [x] Test count: 19 testes unitários e de integração passam.

**Tests:** unit + integration
**Gate:** build
**Commit:** `feat(review): record review decisions`

### Phase 3: Human Loop and Delivery

#### T12: Generate preliminary and final Excel workbooks

**What:** Implementar o exportador `openpyxl` com contrato exato da aba principal, aba de auditoria e bloqueio do arquivo final quando houver pendências.
**Where:** `src/asset_servicing/adapters/export/excel.py`
**Depends on:** T11
**Reuses:** Estado vigente da execução e contrato Excel do desenho.
**Requirement:** ASET-33–40

**Tools:**

- MCP: workspace spreadsheet dependencies
- Skills: `spreadsheets`, `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Testes de integração começam vermelhos para preliminar, final bloqueado, final liberado e variável editada.
- [x] A aba principal contém exatamente as cinco colunas na ordem especificada.
- [x] Score é numérico e revisão é booleana.
- [x] Não aplicáveis não aparecem na aba principal e permanecem na auditoria.
- [x] O workbook reaberto por `openpyxl` preserva valores, tipos e abas.
- [x] Gate Full passa.
- [x] Test count: 14 testes de integração passam.

**Tests:** integration
**Gate:** full
**Commit:** `feat(export): generate Excel workbooks`

#### T13: Build document intake and location UI

**What:** Criar a etapa Streamlit para selecionar/uploadar PDF, orientar capítulo, iniciar localização, mostrar prévias, corrigir páginas e confirmar o intervalo.
**Where:** `src/asset_servicing/ui/app.py`
**Depends on:** T12
**Reuses:** Pipeline público; nenhuma chamada direta aos adapters.
**Requirement:** ASET-01–07

**Tools:**

- MCP: NONE
- Skills: `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Testes de UI começam vermelhos para arquivo válido, inválido, localização, correção e confirmação.
- [x] Extração permanece desabilitada antes da confirmação.
- [x] A UI exibe erro recuperável e entrada manual quando a seção não é localizada.
- [x] Upload e seleção da pasta usam o mesmo caso de uso.
- [x] Gate Full passa.
- [x] Test count: 12 testes de UI passam.

**Tests:** ui
**Gate:** full
**Commit:** `feat(ui): add document location flow`

#### T14: Build results and review UI

**What:** Adicionar visão completa de resultados e fila de pendências com confirmação, edição, não aplicável e inclusão de omissão.
**Where:** `src/asset_servicing/ui/app.py`
**Depends on:** T13
**Reuses:** Serviço de revisão e estado reidratado do repositório.
**Requirement:** ASET-24–30

**Tools:**

- MCP: NONE
- Skills: `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Testes de UI começam vermelhos para tabela geral e as quatro ações de revisão.
- [x] Pendências mostram evidência, página, score, veredito e justificativa.
- [x] Evidência não pode ser editada.
- [x] Contadores são atualizados após cada decisão persistida.
- [x] Gate Full passa.
- [x] Test count: 12 testes de UI passam.

**Tests:** ui
**Gate:** full
**Commit:** `feat(ui): add review workflow`

#### T15: Add exports, recovery, and run summary UI

**What:** Completar a UI com retomada de execuções, downloads preliminar/final, bloqueio por pendência e resumo operacional da execução.
**Where:** `src/asset_servicing/ui/app.py`
**Depends on:** T14
**Reuses:** Repositório, exportador e eventos estruturados.
**Requirement:** ASET-32–40, ASET-46

**Tools:**

- MCP: NONE
- Skills: `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Testes de UI começam vermelhos para retomada, download preliminar, bloqueio e download final.
- [x] Refresh/reabertura preserva o progresso persistido.
- [x] O resumo mostra duração, contagens, distribuição de scores, retries e uso reportado.
- [x] Downloads usam os arquivos da execução correspondente.
- [x] Gate Build da Phase 3 passa.
- [x] Test count: 10 testes de UI passam.

**Tests:** ui
**Gate:** build
**Commit:** `feat(ui): add exports and run recovery`

### Phase 4: Evidence and Handoff

#### T16: Version the four-document golden set

**What:** Criar manifesto e anotações manuais versionadas para os quatro regulamentos, com hashes, campos críticos, valores aceitos, páginas e trechos.
**Where:** `evals/golden/v1/`
**Depends on:** T15
**Reuses:** PDFs em `Regulamentos/` e contrato de variáveis híbridas.
**Requirement:** ASET-49, ASET-53

**Tools:**

- MCP: NONE
- Skills: `pdf`, `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Testes de integridade começam vermelhos antes dos manifests.
- [x] Os quatro hashes correspondem aos arquivos versionados.
- [x] IDs são únicos e cada trecho resolve na página declarada.
- [x] Todo campo marcado crítico possui nome e valor aceitos.
- [x] Gate Full passa.
- [x] Test count: 14 testes de eval passam.

**Tests:** eval
**Gate:** full
**Commit:** `test(evals): add regulation golden set`

#### T17: Add offline extraction evaluation gates

**What:** Implementar o runner offline que compara resultados gravados ao golden set, mede cobertura/valor/evidência, testa Capítulo 6 e injeta erros adversariais.
**Where:** `src/asset_servicing/evals/runner.py`
**Depends on:** T16
**Reuses:** Golden set, fixtures gravadas e rubrica do validador.
**Requirement:** ASET-50–53

**Tools:**

- MCP: NONE
- Skills: `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Testes começam vermelhos para regressão de campo, valor, evidência, Capítulo 6 e erro adversarial sobrevivente.
- [x] O runner falha abaixo de 100% nos quatro gates definidos no desenho.
- [x] O relatório registra modelo/prompt, corpus, métricas, falhas e comparação com baseline.
- [x] Alterar prompt, schema ou pipeline sem relatório atualizado reprova o contrato.
- [x] Gate Full passa.
- [x] Test count: 30 testes de eval passam, incluindo 16 do runner.

**Tests:** eval
**Gate:** full
**Commit:** `test(evals): add extraction quality gates`

#### T18: Cover the complete offline UI journey

**What:** Criar teste ponta a ponta sem rede para seleção, localização, correção, extração gravada, validação, revisão e downloads.
**Where:** `tests/ui/test_complete_journey.py`
**Depends on:** T17
**Reuses:** Streamlit, serviços fakes, golden fixtures e exportador real.
**Requirement:** ASET-01–54

**Tools:**

- MCP: NONE
- Skills: `playwright-skill`, `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] O teste falha antes de cobrir o primeiro fluxo completo.
- [x] O cenário inclui uma variável de baixa confiança revisada manualmente.
- [x] O preliminar é baixável antes da revisão e o final somente depois.
- [x] O workbook baixado é reaberto e validado programaticamente.
- [x] Gate Full passa sem rede ou chave.
- [x] Test count: 4 jornadas de UI passam.

**Tests:** ui + integration
**Gate:** full
**Commit:** `test(ui): cover complete offline journey`

#### T19: Add an opt-in live API smoke test

**What:** Criar um smoke test explícito que usa um PDF, executa os três agentes reais e grava relatório sanitizado sem participar do gate offline.
**Where:** `tests/smoke/test_live_pipeline.py`
**Depends on:** T18
**Reuses:** Pipeline público, configuração de modelos e um regulamento versionado.
**Requirement:** ASET-54

**Tools:**

- MCP: official OpenAI documentation via web
- Skills: `openai-docs`, `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Sem chave, o teste é explicitamente skipped e não falha a suíte offline.
- [x] Com chave, o teste executa localização, extração e validação em chamadas separadas.
- [x] O relatório contém duração, uso, modelos e contagens, sem segredo ou corpo integral do PDF.
- [x] Gate Live passa somente quando credencial estiver disponível.
- [x] Test count: pelo menos 3 cenários de configuração/smoke passam.

**Tests:** needs_api
**Gate:** live
**Commit:** `test(smoke): add live API check`

#### T20: Add the executable local application bootstrap

**What:** Conectar configuração, provider OpenAI, pipeline, persistência, revisão e Excel em um entry point Streamlit executável sem duplicar regras de negócio.
**Where:** `src/asset_servicing/ui/runtime.py`, `.gitignore`
**Depends on:** T19
**Reuses:** Adapters locais, serviços de aplicação, `LocalAppServices` e configuração independente dos três agentes.
**Requirement:** ASET-47–48

**Tools:**

- MCP: NONE
- Skills: `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] O bootstrap monta pipeline, revisão e entrega com os adapters reais sem executar chamada de rede durante a composição.
- [x] Os três modelos são configurados independentemente e o uso reportado é ligado ao ledger do pipeline.
- [x] Dados, uploads e outputs permanecem em caminhos locais ignorados pelo Git.
- [x] Configuração ausente falha com mensagem acionável e sem expor segredo.
- [x] O entry point Streamlit chama a UI com os serviços locais configurados.
- [x] Gate Quick passa.
- [x] Test count: pelo menos 3 cenários de contrato do runtime passam.

**Tests:** contract
**Gate:** quick
**Commit:** `feat(ui): add local runtime bootstrap`

#### T21: Document setup and presentation runbook

**What:** Criar README reproduzível com arquitetura, instalação, configuração, testes, limitações, premissas, demo principal, documento surpresa e recuperação de falhas.
**Where:** `README.md`
**Depends on:** T20
**Reuses:** Comandos canônicos, métricas do eval e fluxo final da interface.
**Requirement:** ASET-48, ASET-54

**Tools:**

- MCP: NONE
- Skills: `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Testes de contrato verificam todos os comandos e headings obrigatórios.
- [x] A instalação parte de clone limpo e não exige arquivo secreto versionado.
- [x] O runbook cobre caminho feliz, revisão de baixa confiança, Capítulo 6 e fallback manual.
- [x] Limitações do corpus, score e uso de API externa estão explícitas.
- [x] Gate Build da Phase 4 passa.
- [x] Test count: pelo menos 4 testes de contrato da documentação passam.

**Tests:** contract
**Gate:** build
**Commit:** `docs(project): add setup and demo runbook`

#### T22: Assert the complete run-creation payload

**What:** Fechar a lacuna ASET-01 com asserções exatas para nome, hash, páginas e timestamp produzido pelo clock injetado.
**Where:** `tests/integration/test_pipeline.py`
**Depends on:** T21
**Reuses:** Harness determinístico do pipeline.
**Requirement:** ASET-01

**Done when:**

- [x] O teste afirma todos os campos obrigatórios da execução criada e reidratada.
- [x] Uma mutação do timestamp é detectada pelo teste.
- [x] Gate Full passa.

**Tests:** integration
**Gate:** full
**Commit:** `test(pipeline): assert creation timestamp`

#### T23: Prove completed-run reprocessing preserves history

**What:** Demonstrar que reprocessar o mesmo documento após gerar o resultado final cria novo `run_id` e preserva a execução anterior.
**Where:** `tests/integration/test_pipeline.py`
**Depends on:** T22
**Reuses:** Pipeline, repositório e exportador reais com provider fake.
**Requirement:** Edge case de reprocessamento concluído

**Done when:**

- [x] A segunda execução recebe id distinto.
- [x] Ambas permanecem legíveis e a primeira não é alterada.
- [x] Gate Full passa.

**Tests:** integration
**Gate:** full
**Commit:** `test(pipeline): preserve reprocessing history`

#### T24: Preserve duplicate semantic variable names

**What:** Demonstrar que dois fatos independentes com o mesmo nome semântico permanecem registros distintos até revisão.
**Where:** `tests/unit/application/test_extractor.py`
**Depends on:** T23
**Reuses:** Extrator e provider estruturado fake.
**Requirement:** Edge case de nomes semânticos duplicados

**Done when:**

- [x] IDs, valores, evidências e páginas distintos são preservados.
- [x] Gate Quick passa.

**Tests:** unit
**Gate:** quick
**Commit:** `test(extractor): preserve duplicate names`

#### T25: Block paid calls when persistence fails

**What:** Injetar falha ao persistir o estado em andamento e provar que o provider não é chamado e o último estado durável permanece intacto.
**Where:** `tests/integration/test_pipeline.py`
**Depends on:** T24
**Reuses:** Harness do pipeline e repositório local.
**Requirement:** Edge case de persistência indisponível

**Done when:**

- [x] A falha de persistência é propagada antes da chamada ao localizador.
- [x] A lista de requests do provider permanece vazia.
- [x] O estado durável anterior permanece `created`.
- [x] Gate Build passa.

**Tests:** integration
**Gate:** build
**Commit:** `test(pipeline): block calls on persistence failure`

### Phase 5: UAT Corrections

#### T26: Constrain agents to the confirmed section boundary

**What:** Impedir que o extrator e o validador tratem capítulos adjacentes presentes nas páginas confirmadas como parte da seção-alvo.
**Where:** `src/asset_servicing/application/extractor.py`, `src/asset_servicing/application/validator.py`, testes contratuais dos prompts
**Depends on:** T25
**Reuses:** Prompts versionados e intervalo confirmado já enviados aos agentes.
**Requirement:** ASET-08, ASET-19 e edge case de capítulo adjacente

**Tools:**

- MCP: NONE
- Skills: `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Testes contratuais exigem escopo semântico e parada no próximo capítulo ou seção de mesmo nível.
- [x] O extrator ignora conteúdo anterior ou posterior à seção-alvo mesmo quando estiver na mesma página.
- [x] O validador não cria omissões a partir de capítulos adjacentes.
- [x] As versões dos dois prompts são incrementadas.
- [x] O relatório de avaliação de prompts é atualizado.
- [x] Gate Quick passa.

**Tests:** contract + eval
**Gate:** quick
**Commit:** `fix(agents): constrain section boundaries`

#### T27: Dismiss false omission findings with audit

**What:** Permitir que o revisor descarte uma possível omissão como falso positivo ou fora de escopo, com justificativa obrigatória e trilha de auditoria.
**Where:** serviço de revisão, domínio, persistência, interface e testes correspondentes
**Depends on:** T26
**Reuses:** Estados de revisão, decisões auditáveis e fila de pendências existentes.
**Requirement:** ASET-22, ASET-31–35 e edge case de descarte de omissão

**Tools:**

- MCP: NONE
- Skills: `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] O serviço público exige justificativa não vazia para descartar a possível omissão.
- [x] A decisão persiste como revisada e restaura corretamente ao reabrir a execução.
- [x] A interface oferece a ação de descarte sem criar variável extraída.
- [x] A pendência descartada sai da fila e deixa de bloquear o Excel final.
- [x] A auditoria registra ação, justificativa, instante e estado resultante.
- [x] Gate Build passa.

**Tests:** unit + integration + ui
**Gate:** build
**Commit:** `feat(review): dismiss omission findings`

#### T28: Make section-boundary tests discriminating

**What:** Fechar os gaps do sensor com contratos exatos dos prompts e uma avaliação negativa que rejeite variáveis ou omissões originadas do capítulo adjacente.
**Where:** testes contratuais dos prompts, fixture de fronteira, runner de eval e baseline offline
**Depends on:** T27
**Reuses:** Prompts v2, gravações offline e relatório de avaliação existentes.
**Requirement:** ASET-08, ASET-19 e edge case de capítulo adjacente

**Tools:**

- MCP: NONE
- Skills: `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] Cada prompt possui snapshot exato e cláusula semântica completa para a fronteira da seção.
- [x] Uma fixture identifica conteúdo real do Capítulo 4 que começa na última página confirmada.
- [x] A avaliação falha quando uma variável gravada contém evidência do capítulo adjacente.
- [x] A avaliação falha quando uma possível omissão gravada contém evidência do capítulo adjacente.
- [x] O relatório offline passa com a gravação limpa e métricas preservadas.
- [x] Gate Build passa.

**Tests:** contract + eval
**Gate:** build
**Commit:** `test(agents): enforce section boundary`

#### T29: Reduce extraction fragmentation

**What:** Ajustar a granularidade operacional para agrupar atributos coordenados da mesma regra sem combinar regras que tenham gatilho, responsável, prazo, valor ou consequência próprios.
**Where:** prompts do extrator e validador, testes contratuais, fixture e runner de eval, gravação e baseline offline
**Depends on:** T28
**Reuses:** Prompts versionados, golden set e runner de avaliação existentes.
**Requirement:** ASET-10 e edge case de atributos coordenados

**Tools:**

- MCP: NONE
- Skills: `tdd`, `git-workflow-and-versioning`

**Done when:**

- [x] O extrator agrupa atributos coordenados da mesma ação em uma variável completa.
- [x] O extrator ainda separa regras com gatilho, responsável, prazo, valor ou consequência próprios.
- [x] O validador considera coberto um detalhe preservado no valor ou evidência de uma variável agrupada.
- [x] Os prompts são versionados e protegidos por cláusulas completas e snapshots exatos.
- [x] Uma fixture da cláusula 3.2 exige uma variável com todos os atributos e rejeita sua fragmentação.
- [x] O relatório offline e o Gate Build passam.

**Tests:** contract + eval
**Gate:** build
**Commit:** `fix(agents): reduce extraction fragmentation`

---

## Phase Execution Map

```text
Phase 1 -> Phase 2 -> Phase 3 -> Phase 4 -> Phase 5

Phase 1: T01 -> T02 -> T03 -> T04 -> T05 -> T06
Phase 2: T07 -> T08 -> T09 -> T10 -> T11
Phase 3: T12 -> T13 -> T14 -> T15
Phase 4: T16 -> T17 -> T18 -> T19 -> T20 -> T21 -> T22 -> T23 -> T24 -> T25
Phase 5: T26 -> T27 -> T28 -> T29
```

As fases formam quatro lotes naturais para execução sequencial: Phase 1 (6 tarefas), Phases 2+3 (9 tarefas), Phase 4 (10 tarefas após as correções do Verifier) e Phase 5 (4 correções de UAT e verificação). Nenhum lote inicia antes do anterior terminar com gate verde.

---

## Task Granularity Check

| Task | Atomic deliverable | Status |
| --- | --- | --- |
| T01 | Bootstrap e contrato de comandos | ✅ Concluída |
| T02 | Modelos e máquina de estados em um módulo coeso | ✅ Concluída |
| T03 | Repositório local | ✅ Concluída |
| T04 | Processador PDF | ✅ Concluída |
| T05 | Porta e contratos LLM | ✅ Concluída |
| T06 | Adapter OpenAI | ✅ Concluída |
| T07 | Localizador | ✅ Granular |
| T08 | Extrator | ✅ Granular |
| T09 | Validador | ✅ Granular |
| T10 | Orquestrador | ✅ Granular |
| T11 | Serviço de revisão | ✅ Granular |
| T12 | Exportador Excel | ✅ Granular |
| T13 | UI de entrada/localização | ✅ Granular |
| T14 | UI de resultados/revisão | ✅ Granular |
| T15 | UI de export/retomada | ✅ Granular |
| T16 | Dataset golden | ✅ Granular |
| T17 | Runner de eval | ✅ Granular |
| T18 | Jornada E2E offline | ✅ Concluída |
| T19 | Smoke real opt-in | ✅ Concluída |
| T20 | Bootstrap local executável | ✅ Concluída |
| T21 | README/runbook | ✅ Concluída |
| T22 | Payload de criação completo | ✅ Concluída |
| T23 | Histórico de reprocessamento | ✅ Concluída |
| T24 | Nomes semânticos duplicados | ✅ Concluída |
| T25 | Falha de persistência pré-provider | ✅ Concluída |
| T26 | Limite semântico da seção nos agentes | ✅ Concluída |
| T27 | Descarte auditável de possíveis omissões | ✅ Concluída |
| T28 | Testes discriminantes da fronteira da seção | ✅ Concluída |
| T29 | Granularidade operacional da extração | ✅ Concluída |

## Diagram-Definition Cross-Check

| Task | Depends on | Diagram shows | Status |
| --- | --- | --- | --- |
| T01 | None | Início Phase 1 | ✅ Match |
| T02 | T01 | T01 -> T02 | ✅ Match |
| T03 | T02 | T02 -> T03 | ✅ Match |
| T04 | T03 | T03 -> T04 | ✅ Match |
| T05 | T04 | T04 -> T05 | ✅ Match |
| T06 | T05 | T05 -> T06 | ✅ Match |
| T07 | T06 | Phase 1 -> Phase 2 | ✅ Match |
| T08 | T07 | T07 -> T08 | ✅ Match |
| T09 | T08 | T08 -> T09 | ✅ Match |
| T10 | T09 | T09 -> T10 | ✅ Match |
| T11 | T10 | T10 -> T11 | ✅ Match |
| T12 | T11 | Phase 2 -> Phase 3 | ✅ Match |
| T13 | T12 | T12 -> T13 | ✅ Match |
| T14 | T13 | T13 -> T14 | ✅ Match |
| T15 | T14 | T14 -> T15 | ✅ Match |
| T16 | T15 | Phase 3 -> Phase 4 | ✅ Match |
| T17 | T16 | T16 -> T17 | ✅ Match |
| T18 | T17 | T17 -> T18 | ✅ Match |
| T19 | T18 | T18 -> T19 | ✅ Match |
| T20 | T19 | T19 -> T20 | ✅ Match |
| T21 | T20 | T20 -> T21 | ✅ Match |
| T22 | T21 | T21 -> T22 | ✅ Match |
| T23 | T22 | T22 -> T23 | ✅ Match |
| T24 | T23 | T23 -> T24 | ✅ Match |
| T25 | T24 | T24 -> T25 | ✅ Match |
| T26 | T25 | Phase 4 -> Phase 5 | ✅ Match |
| T27 | T26 | T26 -> T27 | ✅ Match |
| T28 | T27 | T27 -> T28 | ✅ Match |
| T29 | T28 | T28 -> T29 | ✅ Match |

## Test Co-location Validation

| Task | Code Layer | Matrix Requires | Task Says | Status |
| --- | --- | --- | --- | --- |
| T01 | Configuração | contract | contract | ✅ OK |
| T02 | Domínio | unit | unit | ✅ OK |
| T03 | Persistência | integration | integration | ✅ OK |
| T04 | PDF | integration | integration | ✅ OK |
| T05 | Schemas/portas | contract | contract | ✅ OK |
| T06 | Adapter LLM | contract | contract | ✅ OK |
| T07 | Aplicação | unit + contract | unit + contract | ✅ OK |
| T08 | Aplicação | unit + contract | unit + contract | ✅ OK |
| T09 | Aplicação | unit + contract | unit + contract | ✅ OK |
| T10 | Pipeline | integration | integration | ✅ OK |
| T11 | Domínio/aplicação | unit + integration | unit + integration | ✅ OK |
| T12 | Excel | integration | integration | ✅ OK |
| T13 | Interface | ui | ui | ✅ OK |
| T14 | Interface | ui | ui | ✅ OK |
| T15 | Interface | ui | ui | ✅ OK |
| T16 | Dataset | eval | eval | ✅ OK |
| T17 | Evals | eval | eval | ✅ OK |
| T18 | Interface + adapters | ui + integration | ui + integration | ✅ OK |
| T19 | Integração externa | needs_api | needs_api | ✅ OK |
| T20 | Composição da interface | contract | contract | ✅ OK |
| T21 | Documentação | contract | contract | ✅ OK |
| T22 | Pipeline | integration | integration | ✅ OK |
| T23 | Pipeline | integration | integration | ✅ OK |
| T24 | Aplicação | unit | unit | ✅ OK |
| T25 | Pipeline | integration | integration | ✅ OK |
| T26 | Prompts/evals | contract + eval | contract + eval | ✅ OK |
| T27 | Domínio/aplicação/interface | unit + integration + ui | unit + integration + ui | ✅ OK |
| T28 | Prompts/evals | contract + eval | contract + eval | ✅ OK |
| T29 | Prompts/evals | contract + eval | contract + eval | ✅ OK |

---

## Tools and Skills for Execute

Proposta a confirmar junto com as tarefas:

- Todas as tarefas: shell local, `apply_patch`, `tdd` e `git-workflow-and-versioning`.
- T04 e T16: skill `pdf`.
- T06–T09 e T19: skill `openai-docs` e documentação oficial.
- T10: skill `observability-and-instrumentation`.
- T12: skill `spreadsheets` e runtime de planilhas do workspace.
- T18: skill `playwright-skill` se o harness nativo do Streamlit não cobrir download e navegação; caso contrário, manter o harness nativo.
- Nenhum plugin externo é necessário. O GitHub será usado somente pelo `git` local; `push` permanece responsabilidade do usuário.

Ao aprovar este arquivo, o usuário confirma os seams, a matriz, os comandos de gate, a ordem, os commits planejados e a atribuição de ferramentas acima.

# Automation Asset Servicing

Solução local para localizar, extrair, validar e revisar informações de regulamentos de
fundos de investimento. A aplicação usa três chamadas de LLM com responsabilidades separadas,
mantém evidência e auditoria por execução e entrega arquivos Excel preliminar e final.

O escopo implementado cobre o núcleo P1 do case: tabelas e texto corrido da seção de emissão,
aplicação e resgate de cotas, revisão humana orientada por confiança e resultado final no formato
solicitado.

## Arquitetura

```text
PDF completo
    │
    ▼
Localizador semântico ──► páginas candidatas ──► confirmação humana
                                                   │
                                                   ▼
                                           Extrator estruturado
                                                   │
                                                   ▼
                                        Validador independente
                                                   │
                     ┌─────────────────────────────┴─────────────────────────┐
                     ▼                                                       ▼
              resultados completos                                  fila de revisão
                     │                                                       │
                     └──────────────────────┬────────────────────────────────┘
                                            ▼
                              Excel preliminar / Excel final
```

- **Domínio e aplicação:** controlam estados, revisão, invalidação e orquestração sem depender da
  interface ou do SDK da LLM.
- **Três agentes:** localizador, extrator e validador têm prompts, schemas, chamadas e modelos
  configuráveis de forma independente. O validador não recebe score proposto pelo extrator.
- **Adapters locais:** PyMuPDF processa e renderiza PDFs, JSON/JSONL persiste estado e eventos,
  `openpyxl` produz os workbooks e o adapter OpenAI usa Responses API com Structured Outputs.
- **Interface:** Streamlit consome os serviços públicos. Não acessa o SDK da OpenAI diretamente.
- **Auditoria:** cada execução registra duração, modelo, versão de prompt, uso reportado e erros
  sanitizados em `data/runs/<run_id>/`.

## Instalação

Pré-requisitos:

- Git;
- Python 3.13;
- [uv](https://docs.astral.sh/uv/).

Em PowerShell, partindo de um diretório limpo:

```powershell
git clone https://github.com/yagosamu/automation-asset-servicing.git
cd automation-asset-servicing
uv sync --group dev
```

O `uv` cria e gerencia a `.venv` do projeto. Não é necessário ativá-la manualmente.

## Configuração

A aplicação não possui modelos implícitos. Defina uma chave e um modelo compatível com entrada de
PDF e Structured Outputs para cada agente:

```powershell
$env:OPENAI_API_KEY = "<sua-chave>"
$env:LOCATOR_MODEL = "<modelo-do-localizador>"
$env:EXTRACTOR_MODEL = "<modelo-do-extrator>"
$env:VALIDATOR_MODEL = "<modelo-do-validador>"
```

Configurações opcionais:

```powershell
$env:OPENAI_TIMEOUT_SECONDS = "60"
$env:OPENAI_MAX_ATTEMPTS = "3"
```

`OPENAI_MAX_ATTEMPTS` aceita valores de 1 a 3. O runtime lê o ambiente do processo e não carrega
um arquivo `.env` automaticamente. Nunca versione a chave. Arquivos `.env`, uploads, execuções e
outputs locais estão ignorados pelo Git.

Os PDFs fornecidos devem permanecer em `Regulamentos/`. Um upload feito pela interface é copiado
para `data/uploads/`. Estado, eventos, prévias e exports ficam em `data/runs/<run_id>/`.

## Execução

Com as quatro variáveis obrigatórias configuradas:

```powershell
uv run streamlit run src/asset_servicing/ui/runtime.py
```

O navegador abrirá a interface **Extração de Regulamentos**. A composição do runtime conecta os
adapters reais de OpenAI, PDF, persistência e Excel. Construir os serviços não chama a API; as
chamadas externas começam quando o operador solicita localização, extração ou validação.

Fluxo operacional:

1. Escolha **Pasta do projeto** ou **Upload**.
2. Selecione o PDF e, se for útil, informe **Capítulo esperado (opcional)**.
3. Clique em **Localizar capítulo**.
4. Confira título, justificativa, páginas e prévias. Corrija as páginas se necessário.
5. Clique em **Confirmar intervalo** e depois em **Extrair informações**.
6. Analise a tabela completa e resolva cada pendência: confirmar, editar, marcar como não
   aplicável ou adicionar uma variável possivelmente ausente.
7. Gere e baixe o **Excel preliminar** a qualquer momento. O **Excel final** é liberado somente
   quando não houver revisão pendente.

Cada workbook possui a aba `Variáveis`, com as cinco colunas exigidas pelo case, e a aba
`Auditoria`, com metadados técnicos e histórico de revisão.

## Qualidade e testes

### Suíte offline

Executa todo o projeto sem chave, rede ou chamada paga. Os testes `needs_api` são excluídos:

```powershell
uv run pytest -m "not needs_api" -q
```

### Avaliação contra o golden set

Os quatro regulamentos têm hashes e anotações versionadas. O runner compara cobertura de campos
críticos, valores, integridade da evidência, roteamento adversarial para revisão e o cenário do
Capítulo 6. Os quatro gates têm alvo de 100% no baseline offline versionado.

```powershell
uv run python -m asset_servicing.evals.runner --root . --report output/evals/latest.json
```

O comando retorna código diferente de zero quando um gate ou a compatibilidade com o baseline
falha. O relatório fica em `output/evals/latest.json`.

### Gate Build

```powershell
uv run ruff format --check .
uv run ruff check .
uv run mypy src
uv run pytest -m "not needs_api" --cov=asset_servicing --cov-branch --cov-report=term-missing --cov-fail-under=85 -q
```

### Smoke real opt-in

O smoke usa um regulamento versionado, executa os três agentes reais em chamadas separadas e grava
somente metadados sanitizados. Sem as quatro variáveis obrigatórias, o cenário externo fica
explicitamente `skipped`.

```powershell
uv run pytest -m needs_api -q
```

Por padrão, o relatório é gravado em `tmp/live-smoke/live-smoke-report.json`. É possível alterar o
PDF, diretório de trabalho e relatório com `OPENAI_SMOKE_PDF`, `OPENAI_SMOKE_WORK_DIR` e
`OPENAI_SMOKE_REPORT`.

## Decisões arquiteturais

### Por que não RAG

O fluxo processa um documento por execução e busca uma seção semanticamente bem definida. Depois
da confirmação das páginas, extração e validação trabalham diretamente sobre a mesma fonte. Uma
camada de RAG acrescentaria chunking, embeddings, indexação e recuperação sem resolver uma lacuna
real do caso, além de criar novos pontos de falha e complexidade operacional. RAG passa a fazer
sentido se o escopo evoluir para perguntas sobre uma coleção grande e persistente de regulamentos.

### Por que não uma pipeline de OCR

Os agentes recebem o PDF multimodal, preservando texto, tabelas e representação visual no mesmo
contexto. Para os documentos fornecidos, uma etapa dedicada de OCR duplicaria processamento e
introduziria erros de segmentação e reconstrução de tabelas. A escolha não ignora documentos
digitalizados: se o corpus real demonstrar baixa qualidade visual ou ausência recorrente de camada
textual, OCR pode ser incluído como fallback condicionado e medido por evals.

### Por que agentes separados e revisão humana

Localização, extração e validação têm responsabilidades e prompts distintos. O validador não recebe
o raciocínio nem o score do extrator, reduzindo confirmação automática do primeiro resultado. Casos
incertos são encaminhados para revisão humana com valor, evidência, página, veredito e justificativa.
Essa separação atende ao controle exigido sem esconder incerteza atrás de automação adicional.

### Por que execução local e persistência em arquivos

O case não exige cloud nem banco de dados. Execução local e arquivos JSON por `run_id` reduzem a
superfície operacional, mantêm auditoria e permitem retomar falhas sem infraestrutura desnecessária.
As gravações são atômicas e cada etapa concluída é persistida antes da próxima chamada externa.

## Recuperação de falhas

- **Timeout, rate limit ou erro transitório:** o adapter tenta no máximo três vezes. Se ainda
  falhar, a interface informa que **O progresso foi preservado**.
  Clique novamente em **Extrair informações** para repetir a etapa sem recriar o trabalho.
- **Resposta recusada, incompleta ou fora do schema:** o erro do estágio é sanitizado e o último
  estado concluído permanece persistido. Repita a ação depois de revisar modelo e configuração.
- **Localização incorreta ou inconclusiva:** ajuste o intervalo manual, atualize a prévia e confirme
  antes da extração.
- **Conclusão da extração:** os resultados aparecem imediatamente, sem selecionar uma execução
  intermediária. Ao trocar de regulamento, a visualização anterior é limpa, mas o histórico
  permanece em `data/runs/` para auditoria e recuperação técnica.
- **Excel final bloqueado:** resolva todas as pendências. O preliminar continua disponível para
  inspeção enquanto a revisão estiver aberta.
- **PDF rejeitado:** confirme formato, tamanho máximo de 50 MB, limite de 200 páginas, integridade e
  ausência de senha obrigatória.

## Premissas e limitações

- A aplicação é local, de usuário único, processa um documento por execução e não usa banco de
  dados, autenticação, cloud ou deploy.
- A API externa recebe o PDF selecionado nas etapas dos agentes. Use somente documentos públicos
  ou autorizados e uma conta compatível com a política da organização.
- O corpus de avaliação contém os quatro regulamentos entregues. O golden set demonstra regressão
  nesse corpus, não cobertura universal de todos os regulamentos existentes.
- O score do validador segue uma rubrica estruturada. O limite de revisão é `0,85`, mas o score
  não é uma probabilidade calibrada.
- A entrada usa o PDF multimodal diretamente e não implementa OCR dedicado. PDFs digitalizados
  dependem da capacidade visual do modelo e podem exigir mais revisão humana.
- A solução não implementa RAG. Cada estágio recebe somente o documento ou as páginas necessárias;
  busca em linguagem natural ficou postergada como bônus P3.
- Não há processamento em lote, coordenadas visuais da evidência nem calibração estatística do
  score.
- Modelos, custos e latência dependem da configuração e do provedor. O resumo operacional registra
  uso reportado, retries, duração, modelos e versões de prompt para tornar essa variação visível.

## Estrutura principal

```text
Regulamentos/                 PDFs fornecidos
evals/golden/v1/              golden set e manifesto
evals/recorded/v1/            saídas gravadas para avaliação offline
src/asset_servicing/          domínio, aplicação, adapters e UI
tests/                        unitários, contratos, integração, UI, evals e smoke
data/runs/                    estado local e exports ignorados pelo Git
```

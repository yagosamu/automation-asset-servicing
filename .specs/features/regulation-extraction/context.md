# Extração e Revisão de Regulamentos - Contexto

**Reunido em:** 2026-09-27
**Especificação:** `.specs/features/regulation-extraction/spec.md`
**Status:** Pronto para revisão da especificação e do desenho

---

## Limite da Funcionalidade

A solução processa um regulamento de fundo por execução, localiza a seção que trata de emissão, aplicação, resgate, amortização ou liquidação, extrai tabelas e texto corrido com LLM, valida cada informação com um agente independente, encaminha casos incertos para revisão humana e gera arquivos Excel preliminar e final.

O caso deve funcionar com os quatro PDFs fornecidos e preservar o mesmo fluxo quando a seção equivalente aparecer em outro capítulo ou em outras páginas.

---

## Decisões de Implementação

### Modelo de variáveis

- Usar um modelo híbrido: vocabulário preferencial para campos conhecidos e nomes dinâmicos para regras novas.
- Dividir células ou cláusulas com fatos independentes em variáveis atômicas.
- Manter o valor como formulação curta e fiel; manter o trecho original separadamente como evidência.
- Permitir variáveis originadas tanto de tabelas quanto de texto corrido.

### Confiança e validação

- Usar um agente validador separado do agente extrator.
- O validador não recebe o raciocínio nem uma confiança sugerida pelo extrator.
- Registrar score entre 0 e 1, veredito, justificativa curta e problemas encontrados.
- Encaminhar para revisão todo score abaixo de `0,85`, todo resultado parcialmente suportado ou não suportado e toda suspeita de omissão ou conflito.
- Tratar o score como avaliação estruturada do agente, não como probabilidade estatisticamente calibrada.

### Localização da seção

- Localizar a seção por significado, sem assumir um número fixo de capítulo ou de página.
- Aceitar o número esperado do capítulo como orientação opcional.
- Mostrar título, páginas e prévia antes da extração.
- Permitir que o usuário corrija o intervalo de páginas e confirme a seleção.

### Revisão humana

- Mostrar somente pendências na fila de revisão, sem esconder a tabela completa de resultados.
- Permitir confirmar, editar nome e valor, marcar como não aplicável e incluir uma variável indicada como possivelmente ausente.
- Manter a evidência original imutável.
- Marcar `Foi revisado?` como verdadeiro somente após ação humana explícita.
- Preservar valor original, valor vigente, decisão, instante e justificativa na trilha de auditoria local.

### Excel

- Disponibilizar Excel preliminar mesmo com pendências.
- Liberar Excel final somente quando não houver pendências.
- Manter na aba principal exatamente as cinco colunas solicitadas no case.
- Colocar documento, página, modelos, tempos, versões de prompt e histórico em uma aba separada de auditoria.
- Gerar um arquivo por execução/documento; processamento em lote fica fora do escopo.

### Busca em linguagem natural

- Tratar a busca como bônus, somente depois de extração, validação, revisão, persistência, testes e Excel estarem sólidos.
- Se implementada, consultar as variáveis extraídas e responder com variável e trecho-fonte, sem construir uma infraestrutura RAG adicional.

### Discrição do agente

- Organização exata dos componentes e nomes internos dos modelos de dados.
- Modelo de LLM padrão, desde que seja configurável e aceite PDF/imagem e saída estruturada.
- Aparência visual da interface, preservando o fluxo e os estados decididos acima.
- Biblioteca de renderização e manipulação de PDF, validada antes da implementação.

### Áreas não discutidas convertidas em premissas

- A aplicação será de usuário único e execução local, sem autenticação.
- A interface, os arquivos e o estado serão locais; a chamada à LLM poderá usar API externa.
- O estado será persistido em arquivos no repositório, sem banco de dados e sem expiração automática.
- A aplicação processará um trabalho ativo por vez para evitar concorrência de revisão.

---

## Referências Específicas

- O projeto deve demonstrar o mesmo cuidado com testes, golden set, métricas e observabilidade visto em `juri_ai` e `production_rag`.
- A experiência anterior do `fluxa_comex` serve como referência de pipeline documental e validação, sem reutilizar sua lógica de domínio.
- A apresentação deve tornar visível a separação entre extração, validação e revisão humana.

---

## Ideias Postergadas

- Busca em linguagem natural, condicionada à conclusão do núcleo P1.
- Processamento em lote de vários regulamentos.
- Banco de dados, autenticação, cloud e deploy.
- Destacar coordenadas exatas da evidência sobre a página do PDF.

# Kaguya Studio v3 — Plano de evolução do Kaguya Duo

**Status:** especificação de arquitetura, **não** versão executável nem atualização instalada.
**Condição de projeto:** nenhuma API paga, nenhum uso automático de créditos comprados, uso das CLIs oficiais já autenticadas nas assinaturas, respeitando limites e permissões. **Preservar integralmente** a hierarquia de agentes já criada no Claude Code até auditoria e aprovação.

## 1. Experiência do usuário

Criar aplicação local Windows com painel central de projetos, chat contínuo, seletor `@Codex`, `@Claude`, `@Equipe`, `@Agente:nome`, tarefas, logs, evidências de teste, segundo cérebro e voz opcional. Mensagens com expressões como "depois", "anota" e "quando terminar" são classificadas como fila futura sem interromper tarefa ativa. O usuário pode escolher "interromper agora" explicitamente.

Comportamento inicial: chat em tempo real da **interface** (mensagens e progresso mostrados assim que chegam), mas cada chamada da CLI pode ser uma tarefa delimitada; não confundir com sessão de voz Live oficial ou API de conversação em tempo real.

## 2. Componentes

- `app-ui`: UI local em Python/Tkinter (biblioteca padrão) ou outra interface desktop após avaliação; não exige conta/API nova. Mascotes próprios (um para Codex e outro para Claude) com estados ocioso, executando, pesquisando, revisando, sucesso, alerta e falando. GIF/PNG inicialmente; animação mais avançada depois.
- `orchestrator`: fila persistente SQLite com tarefas, dependências, prioridades, donos, status, critérios de aceite, tentativas, auditoria e log imutável de eventos. Diferenciar `enfileirada`, `em execução`, `bloqueada`, `em revisão`, `concluída`. Não executar automaticamente novas tarefas só porque a IA afirmou que terminou: validar testes e condições.
- `codex-adapter` e `claude-adapter`: usar CLIs oficiais por subprocessos, com a autenticação normal das assinaturas. Detectar versão, capacidades, perfis de modelo e disponibilidade; não extrair tokens de sessão, não usar proxies de API. Persistência/resume somente onde suportado/documentado pela versão instalada. Não mandar mesma alteração para duas IAs simultaneamente no mesmo diretório.
- `memory-adapter`: ler notas Markdown existentes do Obsidian, respeitando exclusões/privacidade. Índice local, filtros por projeto/versão/data/origem. Recuperação contextual curta, com links para o arquivo original. Escrever descobertas em inbox de staging, com deduplicação e aprovação/sincronização; nunca reorganizar ou sobrescrever vault sem prévia de diff.
- `skills-registry`: descobrir skills disponíveis em Codex, Claude e repositório. Mapear objetivo → skill por gatilhos, checar pré-requisitos e custo de contexto. Inventariar skills redundantes, versões, mantenedores e permissões. Instalar somente após exibir origem, conteúdo a executar, dependências, licença, comandos e aprovação expressa. Não instalar arbitrariamente da internet.
- `web-research`: pesquisar quando faltar documentação, versão ou solução; usar recursos nativos de busca se disponíveis e autorizados (Codex CLI `--search`, Claude Code WebSearch/WebFetch ou navegador), registrar URL, data da consulta, versão consultada, resumo, incertezas e referência no Obsidian. Aplicar barreiras contra instruções maliciosas nas páginas.
- `quality-gate`: análise de código/formatadores/testes específicos do repositório, falha reproduzida antes de corrigir quando possível, testes focados e build completo; segunda IA revisa riscos relevantes; artefato final exige evidências reais. Para Minecraft, validar Gradle, versões de Forge/NeoForge, arquivos JSON, logs e compatibilidade, sem afirmar que testou no jogo quando não testou.
- `voice-adapter`: fase 1 Windows `Win+H` (ditado, inserção de texto); fase 2 STT local opcional, por exemplo whisper.cpp, e TTS local Windows/SAPI para leituras. Interrupção de fala e filas de comandos são realizáveis no app próprio; conversa full-duplex com naturalidade igual ao GPT-Live oficial não é garantida sem acesso à interface/serviço apropriado. Codex Voice nativo no ChatGPT Windows existe, mas não pressupor API local para controlá-lo pela UI própria.
- `limits-budget`: limites de paralelismo por projeto, fases de custo/contexto e tempo, desativação de agentes dispensáveis, mensagens compactas de handoff, caches e resumes. Não confundir limite de assinatura com cobrança por token na API; não prometer economias exatas.

## 3. Roteamento inteligente

1. Antes de começar: examinar fila ativa e contexto do Obsidian; diagnosticar se tarefa é pequena, média ou complexa.
2. Para buscas simples, preferir ferramenta local (grep/índice) sem chamar agente; para documentação recente, chamar pesquisador econômico; para mudanças de lógica, agente implementador com testes; para riscos complexos, agente revisor independente.
3. Um único dono modifica cada conjunto de arquivos. Pesquisa e revisão podem ser paralelas em modo leitura; implementação simultânea requer worktrees e arquivos independentes.
4. Registrar razão da delegação, modelo escolhido (quando a ferramenta permitir), ferramentas utilizadas, testes, resultados e duração. Não forçar agentes de modelos indisponíveis.
5. Impor tamanho máximo de resumos, não colar logs extensos no prompt; referenciar arquivo/caminho e trechos pertinentes.

## 4. Política de tarefas durante a conversa

- `AGORA:` interrompe/renegocia atividade somente após confirmação de impacto.
- `DEPOIS:` cria tarefa futura e confirma registro sem alterar tarefa atual.
- `IDEIA:` salva no inbox do Obsidian com projeto e referência.
- `@Codex:` destina pedido ao agente Codex.
- `@Claude:` destina pedido ao Claude Code.
- `@Equipe:` o coordenador decide se distribui, delega leitura, ou executa em sequência.
- Se chegar mensagem sem prefixo durante trabalho: classificar com alta cautela; preferência por fila, a menos que seja uma pergunta sobre progresso.

## 5. Estratégia de habilidades e plugins

- Inventário e leitura do que existe primeiro: `.claude/agents`, `.claude/skills`, `.claude/plugins` (onde aplicável), `CLAUDE.md`, hooks; `.codex/agents`, `.agents/skills`, `AGENTS.md`, MCP e plugins instalados; configurações globais e do repositório.
- Nunca substituir o catálogo de subagentes Claude do usuário por outro; detectar conflitos de nomes, modelos, permissões, regras e skills. Criar relatório de compatibilidade, aplicar migrações em branch separada.
- Exemplos de skills customizadas compartilháveis: `buscar-no-obsidian`, `pesquisar-com-fontes`, `reproduzir-bug`, `teste-gradle-minecraft`, `auditar-kubejs`, `registrar-aprendizado`, `avaliar-permissoes`, `revisao-de-seguranca`, `planejar-refatoracao`.
- Plugins/MCPs só quando acrescentarem ferramentas reais não disponíveis. Uma skill instrui; um MCP/plugin pode conceder acesso e executar ações. Instalação potencialmente arriscada exige consentimento e permissões mínimas.

## 6. Fases (ordem de implementação)

**Etapa 0 — Auditoria sem alterações:** coletar árvore de pastas do vault, configurações Claude/Codex, versões de CLI, plugins e skills; omitir tokens e arquivos privados. Criar relatório de conflitos e backup. Base de testes de regressão.

**Etapa 1 — Chat e fila:** app Windows local, histórico por projeto, seletor de destino, status em tempo real, mensagem `DEPOIS:` persistida e não interruptiva. Mascotes estáticos ou pequenas animações de estado.

**Etapa 2 — Memória e pesquisa:** integração sem duplicar vault, buscas contextuais, referências web com fonte e data, staging de notas, sincronização auditável e deduplicação.

**Etapa 3 — Agentes, skills e otimização:** descobrir e preservar hierarquia Claude, mapear especializações e modelos, verificar skills instaladas, escalonar revisão segundo complexidade, instrumentar consumo observável e criar relatórios.

**Etapa 4 — Qualidade:** executores de testes do projeto, auditoria preventiva periódica quando o usuário iniciar uma execução, verificação de mudanças e exigência de evidência antes de concluir. Sem ações ocultas em background após encerrar o app.

**Etapa 5 — Voz:** ditado Windows primeiro; STT/TTS local opcional depois; interação durante jobs por fila de mensagens e consultas de progresso. Voice nativo do Codex no ChatGPT Desktop funciona em separado, se habilitado pela conta e aplicativo.

## 7. Critérios de aceite e testes

- Rodar com CLIs autenticadas nas assinaturas, sem aceitar variáveis de API key ou conectar a serviços cobrados por uso; indicar quando uma opção só funciona com serviço pago e manter desativada.
- Enviar tarefas `@Codex`, `@Claude`, `@Equipe` pelo chat e exibir logs sem perder saída; inicializar e parar subprocessos com segurança.
- Uma mensagem `DEPOIS:` recebida durante job não interrompe o job, persiste após reiniciar o programa e surge em fila.
- Ler uma nota antiga do vault, relacionar ao projeto, apresentar referência e gravar uma nova nota via staging sem apagar ou modificar a antiga.
- Auditar hierarquia Claude existente sem sobrescrever seus arquivos; criar backup + diff para qualquer alteração.
- Bloquear plugins desconhecidos sem aprovação; registrar fonte e risco.
- Registrar source URL e data para pesquisas; marcar hipóteses não verificadas.
- Reportar precisamente quais testes foram executados, falharam, passaram ou não puderam ser executados.
- Rodar testes automáticos em repositório de exemplo e testes reais em um projeto fornecido pelo usuário antes de chamá-lo de pronto.

## 8. Informações que serão necessárias quando o usuário estiver em casa

- Configuração atual da hierarquia Claude (`.claude/agents/`, skills, settings, `CLAUDE.md`) e Codex (`AGENTS.md`, `.codex/`, skills e plugins) com segredos removidos.
- Estrutura de pastas do Obsidian, especialmente índices, templates e notas principais (preferencialmente árvore anonimizada).
- Saídas dos comandos de versão e disponibilidade das CLIs, sem credenciais.
- Projeto piloto (ex.: mod Java/Gradle ou KubeJS), repositório Git com estado limpo ou cópia de teste.

**Regras:** não comprar créditos automaticamente; não instalar plugins por conta própria; não fazer mudanças destrutivas sem aprovação; não afirmar que funções do v3 já existem no v2.

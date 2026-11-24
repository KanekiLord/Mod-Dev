# KAGUYA STUDIO — Briefing completo de continuidade para Claude Code

**Data de referência:** 24/11/2026  
**Situação:** aplicativo Windows local parcialmente implementado, porém com falhas reais de uso relatadas pelo usuário.  
**Versão mais recente disponível:** Kaguya Studio V3.4 — duas mascotes.  
**Objetivo deste documento:** permitir que Claude Code **audite, conserte e evolua o programa existente**, sem reconstruir cegamente nem perder o trabalho anterior.

> **INSTRUÇÃO INICIAL PARA CLAUDE CODE**  
> Abra e examine o código do ZIP V3.4, este briefing, o plano V3 e o catálogo de agentes. **Não se limite a produzir outra especificação ou uma imagem conceitual.** Primeiro reproduza os bugs e entregue um plano de correções, depois implemente e valide as mudanças por etapas. Considere o relato do usuário no Windows como evidência principal: as funcionalidades que parecem prontas nos testes locais **não estão funcionando para ele**. Não declare nenhuma conexão, voz ou visor de limite como concluído sem prova real.

## 1. Visão do produto

O usuário paga **ChatGPT/Codex e Claude Code** e deseja utilizar ambos no mesmo ambiente de desenvolvimento, **sem API keys cobradas à parte, sem contratar outros serviços pagos e sem consumir créditos extras automaticamente**. O Studio será o centro de trabalho para projetos de programação (especialmente mods Minecraft), modelagem e criação. Também deverá utilizar seu **Segundo Cérebro existente no Obsidian** e os subagentes, skills e plugins já configurados.

O produto final deve ter:

1. Interface desktop premium, elegante, fluida e responsiva, com design escuro em violeta, âmbar/dourado e referências japonesas discretas, **não uma janela Tkinter básica**. Produzir e integrar **assets visuais separados** (fundos, elementos decorativos, ícones, divisores, ornamentos, estados, cards) em vez de simplesmente usar uma imagem de mockup como um banner.
2. Chat central em português com destino **Codex**, **Claude** ou **Equipe**; mensagens, saídas e logs em streaming quando suportado; operações persistentes; cancelamento e retomada controlados; histórico por projeto.
3. Integração real das **CLIs oficiais** com autenticação nas assinaturas já pagas, diagnóstico por ferramenta, indicação clara do motivo de falhas, versões detectadas e permissões. Não extrair tokens OAuth, não usar endpoints privados, não instalar gateways/proxies de credenciais.
4. **Duas IAs trabalhando juntas de verdade**, sequencialmente com feedback/correção e, quando seguro, em paralelo com Git worktrees e tarefas independentes; jamais editar o mesmo arquivo ao mesmo tempo sem coordenação.
5. **Segundo Cérebro Obsidian** conectado por seleção de pasta independente do projeto, com busca confiável, leituras contextualizadas, notas de pesquisa e aprendizado, links, deduplicação, revisão prévia e sincronização não destrutiva.
6. **Agentes, skills, plugins e MCPs:** inventariar e aproveitar os já instalados antes de sugerir novos; respeitar a hierarquia do Claude existente; seleção econômica de agentes/modelos conforme a dificuldade e limites; pedir aprovação para instalações externas.
7. **Detecção proativa de erros:** testes do projeto, compilação, análise estática, revisão por outra IA quando justificado, diagnóstico de dependências, logs e critérios de aceite verificáveis. Nunca dizer “testado” com base somente em execução de comando sem validação.
8. **Voz**: push-to-talk e respostas faladas primeiro (STT/TTS locais, sem API paga); o usuário deseja conversar enquanto o código executa. Depois, evoluir para interrupções naturais/voz contínua conforme viabilidade; não apresentar o ditado Win+H como se fosse o modo Live oficial.
9. **Duas mascotes em pixel art**: Kaguya representa Codex; personagem feminina de tons âmbar representa Claude. Versões integradas ao Studio e janelas flutuantes independentes, com sprites transparentes, expressões, animação e estados de execução.
10. **Painel realista de limites/cotas:** para Codex e Claude, mostrar uso restante, janelas de renovação e limites disponíveis **somente quando houver dados confiáveis autorizados por cliente oficial**; quando não houver integração programática, mostrar “não disponível” + abrir recurso `/status` do Codex, `/usage` do Claude e páginas oficiais. Diferenciar quota da assinatura, uso local desta sessão, tokens, custos simulados e limites de contexto.

## 2. Histórico do que foi construído

- **Kaguya Duo V1** (`kaguya_duo_codex_claude.zip`): Python CLI com modo Codex implementa → Claude revisa → Codex recebe feedback; opção de trabalho paralelo em pastas Git separadas, dependente de integração posterior. Sem interface moderna.
- **Kaguya Duo V2** (`KaguyaDuo_Cerebro_Obsidian_v2.zip`): adicionou pesquisa/registro no Obsidian, fila, modelos/skills e scripts. **Não instalar essa versão sobre o vault atual**: ela propõe estrutura que pode duplicar a memória e a fila já existentes.
- **Kaguya Studio V3 MVP** (`Kaguya_Studio_V3_MVP_Windows.zip`): aplicativo Python/Tkinter; `core.py`, `runtime.py`, `studio.py`, `diagnostico.py`; SQLite local; vínculo de projeto/vault; conversa por tarefas; `@Codex`, `@Claude`, `@Equipe`, `DEPOIS:`, `IDEIA:`; consultas Markdown; inventário de agentes; testes locais.
- **V3.1**: mascote do Codex embutida e flutuante com chat rápido, posição/tamanho salvos e opção de ficar no topo.
- **V3.2**: importou os 18 PNGs 128×128 e 10 frames de animação da Kaguya, mas surgiram dificuldades de transparência/alinhamento.
- **V3.3**: redesenho parcial em Tkinter baseado em conceito gerado por IA; tratamento de PNGs; ainda muito inferior visualmente ao conceito.
- **V3.4 (código atual)**: adicionou personagem feminina do Claude Code (9 PNGs 128×128) no Studio e como mascote flutuante; estados separados e chat rápido. Relatório anterior mencionou 37 testes automatizados, feitos principalmente com **CLIs simuladas e display virtual**, e não com o ambiente real do usuário no Windows.

**Importante:** versões anteriores informaram que tudo estava implementado, mas o usuário relata que recursos centrais **não funcionam**. Tratar os testes existentes como cobertura parcial e não como garantia da experiência final.

## 3. Problemas reais comunicados pelo usuário (24/11/2026)

**P0 — bloqueadores de uso:**

- Não consegue conectar/autenticar Codex e Claude Code dentro do aplicativo.
- Não consegue utilizar as duas IAs juntas.
- Não consegue vincular corretamente pastas dos projetos.
- Não consegue vincular a pasta do Segundo Cérebro do Obsidian.

**P1 — recursos muito incompletos:**

- As IAs não possuem experiência de conversa por voz; Win+H e uma leitura isolada por SAPI não atendem ao objetivo.
- Não há visor confiável mostrando limites, saldo/quota restante e renovação de cada assinatura.
- Interface considerada muito feia; assets precisam ser **criados separadamente, com qualidade de produto**, e incorporados aos componentes reais.
- Melhorar exibição/recorte/animações dos mascotes, sem modificar indevidamente o desenho original.

**P2 — orquestração e memória:**

- Agentes se esquecem de consultar o Obsidian; deixam de registrar erros e aprendizados.
- Não pesquisam referências web espontaneamente quando deveriam.
- Não encontram bugs por iniciativa própria; dependem de o usuário reportar tudo.
- Mudam de tarefa quando o usuário menciona uma ideia “para depois”.
- Consumo excessivo de limites, contexto, tokens e subagentes; pretende trabalhar por períodos maiores, sem custo adicional.

## 4. Diagnóstico inicial baseado no código V3.4 (hipóteses a verificar no Windows)

Arquivos reais presentes no ZIP:

- `core.py`: `Store` SQLite (`projects`, `tasks`, `events`), `Vault.search`, `Vault.stage/sync_approved`, inventário de agentes/skills, `safe_env`, `plan_command`.
- `runtime.py`: `run_process`, `check_subscription`, `run_cli`, `check_project_writable`, `run_quality`.
- `studio.py`: interface Tkinter, seletor de projeto, chat, worker/fila, pesquisa do vault, diagnósticos, comandos de voz rudimentares.
- `mascote.py`: carregamento de sprites, estados, janelas flutuantes, escala/posição e menus.
- `diagnostico.py`: diagnóstico de vault (notas, links, duplicados etc.).
- `tests/`: testes Python, muitos simulados. `mascotes/`: imagens, sprites, backups. `catalogo/agentes.json`: inventário histórico de 72 agentes.

**Pontos concretos a investigar:**

1. **Vínculo de pastas:** `studio.py:_add_project()` usa `filedialog.askdirectory()` duas vezes em sequência e `Store.add_project()` exige `directory` e `vault` existentes na mesma operação. Se o usuário cancelar ou não conseguir selecionar o vault, o projeto não é salvo. O esquema `projects` guarda um vault por projeto, sem um vínculo global de Obsidian. Melhorar com assistentes separados de pastas, edição de caminhos, teste de leitura/escrita, status por pasta e diagnóstico de erro específico.
2. **Repositório Git:** `runtime.py:check_project_writable()` só autoriza edição quando a pasta selecionada é **exatamente a raiz Git**. Separar “pasta do projeto” de “raiz do Git”, detectar subpastas e explicar o motivo do bloqueio, sem obrigar o usuário a adivinhar.
3. **Conexão CLIs:** `check_subscription()` depende do formato textual/JSON de `codex login status` e `claude auth status`; pode quebrar com versões e idiomas distintos. `safe_env()` remove variáveis de API, mas não demonstra que a CLI foi autenticada na máquina. Diagnosticar `PATH`, launchers `.cmd` no Windows, versões, login, modo headless, uso por assinatura, `cwd`, `stdin`, exit code, stderr, sandbox e permissões. Não imprimir segredos.
4. **Execução Claude:** `plan_command('claude')` monta `claude -p --output-format text --permission-mode plan` para leitura e `acceptEdits` para escrita, com listas de ferramentas e `--disallowedTools mcp__*`. Algumas combinações podem limitar ações ou não serem compatíveis com a versão instalada. Auditar nas documentações atuais e testá-las. Não habilitar escrita automática sem aprovação.
5. **Modo Equipe:** `_worker_loop()` chama Codex, depois Claude **somente em leitura**, e conclui a tarefa como `executed`. Não existe ainda um verdadeiro mecanismo de feedback/retrabalho entre ambos ou revisão/teste completo. Reestruturar como máquina de estados auditável (implementação → testes → revisão → correção → aprovação), com limites de ciclos.
6. **Sem continuidade conversacional real:** a UI possui tarefas discretas em processos separados. Investigar `resume`/sessões oficiais compatíveis, histórico por projeto e eventos estruturados, sem depender de parsing frágil de terminal.
7. **Memória:** `Vault.search()` faz varredura por palavras e limita a quantidade de Markdown; não indexa referências/versões nem guarda relações robustas. A fila local SQLite **não está sincronizada em duas vias** com `tasks/todo.md`. Manter arquivo oficial preservado e criar adaptador compatível após inspecionar formato real.
8. **MCPs/plugins:** `--disallowedTools mcp__*` impede uso automático dos MCPs nessa execução. Hoje só existe inventário básico; não há integração real de skills/plugins nem gerenciador com aprovação.
9. **Voz:** `_dictate()` apenas sugere `Win+H`; `_speak()` chama PowerShell `System.Speech` com até 1000 caracteres. Não existe STT contínuo, chat falado integrado nem VAD/interrupção.
10. **Limites:** a base não possui medidor de uso de assinatura. Não confundir dados de `token_usage` de uma execução com “saldo restante da conta”.
11. **UX:** Tkinter e imagem gerada usada como cabeçalho não equivalem à aplicação visual de referência. Necessária revisão real da experiência, escalabilidade, DPI no Windows, menus, atalhos, acessibilidade e componentes.

## 5. Design: reconstrução visual e assets independentes

**Objetivo visual:** uma aplicação Windows de nível comercial, com identidade própria, não uma janela com blocos grandes e textos cortados. Paleta base: fundo grafite/roxo profundo, destaques violeta/ametista para Kaguya e âmbar/terracota para Claude, dourado discreto para ações principais; decoração japonesa leve, sem comprometer contraste.

**Exigir deliverables separados** em pasta versionada, por exemplo:

```text
assets/
  branding/      logotipo, wordmark, ícone do app (SVG/PNG/ICO)
  backgrounds/   fundos, texturas e ilustrações leves (WebP/PNG)
  ornaments/     sakura, luas, separadores, glow e padrões (SVG/PNG transparente)
  icons/         ações, status e navegação (SVG de uma família consistente)
  mascots/
    kaguya/      expressões e animações preservadas
    claude/      9 expressões e futuras animações
  states/        estados de loading, offline, erro, sucesso
  previews/      mockups, capturas reais e comparações
```

**Não** use screenshot/mockup inteiro como UI ou backgrounds contendo textos e botões fictícios; **não** faça recorte apressado de uma prancha com sujeira nos cantos. Gere os elementos visuais separadamente com fundo transparente verdadeiro e recortes conferidos em fundos claros/escuros. Crie componentes reais responsivos com tipografia, ícones e estados interativos.

Recomendação para avaliar: migrar **a camada de apresentação** para **PySide6/Qt Quick QML** (reaproveitando módulos Python) ou Tauri + React caso haja justificativa de desempenho/packaging. **Não reescrever o backend inteiro apenas para mudar aparência.** Definir arquitetura com isolamento UI/adapters/core, empacotador para Windows e testes visuais de DPI 100/125/150/200%. Antes da mudança, construir design system (cores, tipografia, espaçamento, componentes, estados, ícones) e 2–3 telas chave. O usuário quer **assets reais criados e integrados**, não somente um protótipo.

**Layout desejado:** navegação lateral compacta (Projetos, Conversa, Fila, Agentes/Skills, Segundo Cérebro, Diagnóstico, Configurações); centro com mensagens claramente diferenciadas, tarefas e ações; painel de estado com ambas as IAs e quotas; mascotes contextuais, sem invadir a área de trabalho; composer com destino, modo de segurança, fila/depois e botão de voz; ações de abrir pastas e logs; chat flutuante opcional.

**Referência visual:** `CONCEITO_VISUAL_GERADO.png` (conceito, não screenshot funcional). `PREVIA_V3_4_REAL.png` e `PREVIA_V3_4_DESKTOP.png` são referências das limitações da implementação anterior.

## 6. IA: integração real e colaboração

**Estado da conexão individual:** `Não instalado / Encontrado / Não autenticado / Autenticado / Sem permissão / Pronto / Em execução / Limite alcançado / Erro`. Exibir versão, caminho do executável, modo de autenticação confirmado, último diagnóstico, botão de testar e instruções de correção.

**Modo Codex:** tarefas e saídas próprias, aprovações, testes. **Modo Claude:** idem, com seus agentes existentes e skills. **Modo Equipe:**

- Sequencial: Codex implementa → testes → Claude revisa → problemas retornam ao Codex → novo teste → veredito, sem loops infinitos.
- Paralelo: decomposição de tarefas independentes, workers em Git worktrees ou pastas isoladas, revisão e integração com diff/merge supervisionado. Não sobrescrever alterações do usuário nem fazer merge cego.
- Mensagens `DEPOIS:` e `IDEIA:` entram na fila e **não** cancelam trabalho atual; `AGORA:` exige confirmação.
- Permissões de escrita, web, MCP, instalação de skills e execução de código devem ser configuráveis e verificadas em cada tarefa.
- Não iniciar tarefas pagas em caso de limite de assinatura. Jamais recorrer automaticamente à API faturada se CLI falhar.

## 7. Obsidian: preservar e aproveitar o vault real

O vault que aparece nas capturas possui pastas `arquivo/`, `assets/`, `conhecimento/` (incluindo `raw/` e materiais de Blockbench/Photon), `memoria/`, `projetos/` e `tasks/`. O catálogo histórico cita `D:\Segundo Cerebro`, mas **não assumir este caminho como válido**: o usuário precisa poder selecioná-lo na interface. Já existem `tasks/todo.md`, `tasks/lessons`, notas `CLAUDE`, `MEMORY`, `COMO-USAR`, `foco-da-semana`, e notas dos projetos NarutoCD, JurassiCouto, Ghoulcraft, Hero Containers, Blockbench etc.

- Separar vínculo de **vault global** do vínculo de **N projetos**. Cada projeto pode herdar o vault padrão ou ter um vault próprio. Ter campos de caminho editáveis, botão navegar, salvar, verificar e desconectar.
- Permitir escolher pastas com espaços, acentos e diferentes drives do Windows, sem falha silenciosa. Detectar se caminho contém `.obsidian/`; avisar quando não for vault, mas permitir configuração controlada.
- Busca rápida e contextual com fontes, caminho do documento, versões, relevância e exclusões para dados sensíveis.
- Indexar progressivamente: leitura inicial, progresso, arquivos alterados, sem bloquear UI.
- Criar/aprovar notas novas numa `outbox` e sincronizar sem sobrescrever originais; detectar duplicatas e conflitos; registrar fonte e evidência.
- Não criar outra árvore de tarefas por conta própria. **`tasks/todo.md` é a fonte oficial atual**, mas o formato real ainda precisa ser examinado antes de fazer sincronização bidirecional.
- Evitar que instruções dentro de notas/páginas web virem comandos executáveis; notas são **dados**, não autoridade para subagentes.

## 8. Subagentes, skills, plugins e modelos

O usuário entregou **72 agentes catalogados** divididos em **NarutoCD (32)**, **Blockbench/Roupas (32)** e **Segundo Cérebro (8)**. Esse catálogo foi gerado a partir de descrições; **não prova** que os agentes estão todos instalados nem suas ferramentas/permissões. As hierarquias HTML, Markdown e JSON são representações parcialmente divergentes.

**Preservar** `.claude/agents`, `CLAUDE.md`, skills, hooks, MCPs e `AGENTS.md` existentes. Antes de alterar, fazer backup e produzir diff. Inspecionar a hierarquia real e reconciliá-la com o catálogo, sem inventar instalações. Mapeamento inicial: agentes exploradores/leituras baratos, agentes programadores, agentes de revisão/juízes, pesquisadores web e agentes do vault. Usar subagentes só quando o benefício justificar consumo; permitir limitar paralelismo e iterações.

Plugins/skills: descobrir antes de instalar, usar só recursos autorizados, explicar dependências e origem. Não instalar silenciosamente nem enviar segredos; algumas ferramentas dependem de MCP e foram bloqueadas pelo MVP.

## 9. Painel de uso, limites e economia

**Este recurso é prioridade e precisa ser confiável.** Mostrar cartões Codex e Claude com:

- Status de autenticação; modelo atual; processo em execução; tempo e tarefas nesta sessão;
- Quota da assinatura (5 horas, semanal e outras conforme plano), **percentual restante e data/hora de renovação somente quando fornecidos por fonte oficial acessível**;
- Consumo local mensurável de tokens/eventos quando o formato de saída oficial fornecer; diferenciar claramente de saldo remoto;
- Indicador de dado não disponível, idade do último dado e botão para abrir o painel oficial;
- Alertas por aproximação do limite e sugestão de reduzir paralelismo/adiar tarefas sem comprar créditos automaticamente.

**Fontes oficiais verificadas em 24/11/2026:**

- Codex CLI `/status` e painéis de uso do ChatGPT/Codex. https://help.openai.com/en/articles/11369540-using-codex-with-your-chatgpt-plan
- Claude Code `/usage` e página `Settings > Usage` no Claude. https://support.claude.com/pt/articles/14553413-cola-de-referencia-do-claude-code e https://support.claude.com/en/articles/9797557-usage-limit-best-practices

**Limite técnico importante:** comandos de barra costumam ser interativos. Não presuma que `codex exec /status` ou `claude -p /usage` forneçam quotas em formato estruturado. Verifique se há recurso/documentação oficial para uso programático; caso não haja, mostrar “Quota não disponível automaticamente” e links/botões de consulta oficial. Não fazer scraping de sessão, interceptar credenciais nem inventar 78%, 56%, etc. Quota de conta pode ser compartilhada entre produtos ou variar por plano. Não confundir tokens desta execução com franquia restante.

## 10. Voz

Fase A: microfone push-to-talk, transcrição STT local opcional (Whisper.cpp/faster-whisper mediante instalação autorizada) e TTS Windows/Piper; permissão explícita do microfone, seleção de dispositivo, idioma pt-BR, interrupção da fala, legenda, volume, indicador de escuta e estados dos mascotes.

Fase B: comandos de voz durante tarefas em andamento **sem interromper o job**; o orquestrador os encaminha para consulta de status, alteração autorizada ou fila futura. Fase C: avaliação de full-duplex com VAD/eco/cancelamento, se viável sem API adicional. **Não afirmar que replicou GPT-Live nativo.** Prefira processamento local e documente CPU/RAM/modelos baixados.

## 11. Critérios verificáveis de aceite

1. Usuário abre o aplicativo no Windows e **vincula/edita** um projeto e vault Obsidian em `D:` ou outro disco, fecha o app, reabre e os dois caminhos continuam salvos; botões **Abrir pasta** funcionam.
2. `Diagnosticar Codex` e `Diagnosticar Claude` mostram versão, executável encontrado, estado de login e erro específico quando não conectam; testes com **contas reais** passam sem API key.
3. Uma tarefa em Codex exibe log/stream e termina com estado fiel; uma em Claude faz o mesmo.
4. O modo Equipe executa implementação, revisão, feedback, correção e validação (quando cabível), com logs separados. Em modo paralelo, utiliza worktrees e respeita arquivos dos agentes.
5. O vault retorna uma nota de conhecimento existente, com link/caminho, e registra uma descoberta nova via prévia e aprovação, sem modificar notas antigas.
6. `DEPOIS:` digitado no chat durante execução não interrompe a tarefa; fica salvo após reiniciar.
7. Dois mascotes usam sprites correspondentes e transparência real no Windows com DPI escalado; expressões refletem **apenas** sua IA.
8. A interface final usa assets separados e componentes reais, passa avaliação visual comparativa em 100/125/150/200% de DPI, e não apresenta botões ou textos cortados.
9. Voz: gravar microfone com consentimento, transcrever pt-BR e ler resposta em TTS, sem API paga. Mostrar claramente se dependência/modelo local estiver faltando.
10. Painel de limites mostra valores reais **ou “indisponível” com consulta oficial**, nunca números fictícios; diferencia saldo remoto e uso local.
11. O aplicativo gera relatório reproduzível de testes, logs higienizados, mudanças e pendências; as automações não afirmam ter testado Minecraft sem execução real.
12. Os 72 agentes catalogados não são substituídos; só são considerados disponíveis após descoberta nos diretórios reais.

## 12. Ordem de execução recomendada (começar já)

**Etapa 0 — Auditoria e reprodução:** instalar V3.4 em cópia isolada, ler código/documentação, executar testes existentes, identificar falhas de vinculação e integração. Coletar logs do Windows **sem segredos**. Escrever testes de regressão que falham antes de corrigir (TDD).

**Etapa 1 — Fazer funcionar:** consertar seleção/configuração dos projetos e do vault, diagnóstico de CLIs e autenticação, tarefas isoladas Codex/Claude, modo Equipe com feedback e filas sem interrupções. Esta etapa vem antes de um redesign caro.

**Etapa 2 — Design system e assets:** definir layout com o usuário, gerar assets separadamente, preparar migração de UI preservando core, implementar interface realmente bonita, verificar visualmente em Windows.

**Etapa 3 — Obsidian + memória:** índice eficiente, recuperação de notas, staging e deduplicação, integração com tarefas após validar estrutura existente.

**Etapa 4 — Agentes/skills e qualidade:** ler 72 agentes reais, ajustar roteamento econômico, pesquisa automática com fontes, checks e aprovação baseada em evidência.

**Etapa 5 — Uso e voz:** painel de limites com fontes oficiais, STT/TTS local e comandos não interruptivos. A estrutura visual do painel deve existir desde Etapa 2 e funcionar mesmo sem dados remotos.

**Etapa 6 — Packaging:** instalador Windows, logs e diagnósticos de fácil acesso, atualização/backup reversível, documentação PT-BR, testes integrados e smoke tests com assinaturas reais após autorização do usuário.

## 13. Regras de segurança e qualidade

- Não sobrescrever Git, CLAUDE.md, AGENTS.md, `.claude/agents/`, `.obsidian`, `tasks/todo.md`, notas, sprites originais ou quaisquer configs existentes sem backup, diff e permissão.
- Nunca enviar credenciais, chaves, OAuth, cookies, notas privadas ou logs sensíveis a terceiros. Não instalar plugins/MCPs sem consentimento.
- Não inventar conexão funcionando com base em mocks. Documentar exatamente o que passou em testes unitários, integração local e validação Windows real.
- Não selecionar modelos indisponíveis ou acionar API faturada sem usuário pedir; respeitar limites e restrições oficiais dos provedores.
- Manter os nomes das pastas com acentos/espaços e caminhos Windows; tratar corretamente `D:\`, UNC e backslashes.
- Em correções de lógica, reproduzir bug e executar teste antes/depois. Não remover testes para obter 'verde'.
- O protótipo gerado por imagem é **referência**, não representação literal do que está funcionando.

## 14. Arquivos entregues no pacote de handoff

- `Kaguya_Studio_V3_4_Dois_Mascotes_Windows.zip`: **código e sprites da última versão**; este é o principal insumo de implementação.
- `PLANO_KAGUYA_STUDIO_V3.md`: especificação inicial de visão e arquitetura.
- `agentes.json` + `hierarquia-agents.md` + `HIERARQUIA.md`: catálogo/hierarquias históricas Claude.
- `CONCEITO_VISUAL_GERADO.png`: referência de design criada por geração de imagem, **não** screenshot funcional.
- `PREVIA_V3_4_REAL.png`: captura da aplicação que precisa ser melhorada.
- `PREVIA_V3_4_DESKTOP.png`: visualização com mascotes flutuantes.
- `claude_code_feminina_mascote_pacote_completo.zip`: sprites originais do Claude.
- `kaguya_pixel_art_sprites.zip`: sprites originais da Kaguya.

## 15. Pedido imediato ao Claude Code

1. Leia a V3.4 e este documento por completo; mantenha visão do produto.
2. Faça **auditoria técnica honesta** das integrações que o usuário relata como quebradas. Liste causa encontrada, evidência, teste reproduzido, dependência de Windows/assinatura e prioridade.
3. **Implemente primeiro** correções de vinculação de pastas (projeto + Obsidian) e diagnóstico/autenticação das duas CLIs, com testes. Não diga ao usuário apenas para instalar Python ou passar um prompt se o próprio app está com defeito.
4. Em seguida teste o modo Equipe real e estabeleça feedback Codex ↔ Claude com controle de falhas. Não execute compras, API por uso ou instalação desconhecida.
5. Apresente a arquitetura concreta de redesign com **assets separados** e um painel de limites sem números inventados; avance para implementação e forneça capturas da interface real.
6. Entregue uma nova versão instalável/ZIP para Windows com changelog, instruções de migração, diagnóstico simplificado e evidência de testes. Diga claramente o que **ainda não funciona**.

**Princípio:** Kaguya Studio deve ser um ambiente de desenvolvimento realmente utilizável com duas IAs e um Segundo Cérebro, não uma demonstração visual de funcionalidades simuladas.

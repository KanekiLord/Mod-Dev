# Kaguya Studio V3.4 — duas mascotes (Codex e Claude Code)

**Esta versão atualiza a V3.3.** Extraia em uma pasta nova; não substitui arquivos do seu vault do Obsidian nem os agentes já configurados no Claude Code. O aplicativo funciona por Python/Tkinter, sem API paga ou pacotes adicionais em tempo de execução.


## Novidade V3.4: Claude Code com mascote feminina

- O Studio exibe **Kaguya (Codex)** e **Claude Code** lado a lado. As ilustrações são os PNGs originais enviados pelo usuário.
- Claude traz **9 expressões PNG de 128x128** (neutra, feliz, pensando, falando, surpresa, piscando, focada, sucesso e café). Não se trata ainda de uma sequência animada ou modelo de voz.
- Cada mascote pode ficar **flutuante no Windows** independentemente, com sua própria posição, escala, visibilidade, sempre visível e menu de expressões. O botão de cada uma fica na lateral direita.
- **Duplo clique em Claude** abre chat rápido com `Claude` como destino padrão; a Kaguya abre o chat com `Codex` selecionado. Ambos permitem alternar para Equipe ou guardar tarefas/ideias para depois.
- Durante a execução, cada personagem reage **ao estado de sua própria CLI**: Codex implementando ≠ Claude revisando. Expressão de sucesso significa que o processo terminou, **não** que o código foi aprovado.
- A estrutura original de `mascotes/kaguya` e os dados do seu Obsidian **não foram alterados**. O arquivo `%LOCALAPPDATA%\KaguyaStudioV3\mascote_claude.json` guarda as novas preferências separadamente.
- Para abrir os dois mascotes sem a janela principal, use `INICIAR_SOMENTE_MASCOTE.bat`. Se ambos forem ocultados nesse modo, o aplicativo encerra.

**Validação**: 36 testes locais passaram, com teste gráfico no Xvfb. O recorte/transparência final no Windows e o login real nas CLIs continuam pendentes de validação na máquina do usuário.

## O que mudou

- Interface reorganizada com navegação lateral, painel de tarefas/projetos, resumo dos agentes, cartão da Kaguya em tamanho maior, tipografia e cores roxo/âmbar. Mantém as cinco áreas e as mesmas ações da versão anterior.
- Cabeçalho decorativo recortado de um **conceito visual gerado por IA**; a imagem de referência completa está em `CONCEITO_VISUAL_GERADO.png`. O conceito não é uma captura do aplicativo real. A captura real está em `PREVIA_REAL_V3_3.png`.
- Foram corrigidos **28 sprites PNG de 128×128**, com remoção de pequenos resíduos opacos dos cantos e da moldura. São 18 expressões e 10 quadros animados; o personagem não foi redesenhado, redimensionado nem teve rosto ou roupa modificados.
- O material original está guardado em `mascotes/kaguya/originais_backup/` para comparação/recuperação.
- A transparência deve ser verificada na **área de trabalho Windows**. Os frames de animação continuam opcionais e DESLIGADOS por padrão porque nem todas as poses têm encaixe perfeito entre si.
- Navegação da barra lateral e gerenciamento de projetos continuam funcionais; estados do Obsidian/CLIs não são simulados com resultados fictícios.

## Abrir

1. Extraia todo o ZIP em uma pasta como `D:\Ferramentas\KaguyaStudioV3_3`.
2. Tenha Python 3.10+ com Tkinter instalado. **Não precisa executar pip** para usar o app.
3. Execute `INICIAR_KAGUYA_STUDIO_V3.bat` para abrir o aplicativo; ou `INICIAR_SOMENTE_MASCOTE.bat` para a Kaguya flutuante.
4. Em `+ Projeto`, vincule seu projeto e a pasta já existente do Obsidian. Em `Verificar CLIs`, confirme Codex e Claude Code.
5. Ao enviar uma tarefa, habilite alteração de código somente quando confiar no repositório. Pesquisas web também dependem das permissões das CLIs.

## Limitações confirmadas

A interface foi verificada em um display virtual Linux/X11 e os testes automatizados foram executados com clientes simulados. Não foi executada no seu Windows com as duas assinaturas. Não inclui voz Live contínua, nem orquestração econômica avançada entre agentes/modelos. A referência gerada tem mais detalhes gráficos do que o widget Tkinter implementado; o aplicativo entregue é a versão funcional, não uma reprodução pixel a pixel do mockup.

Pillow é usado apenas no utilitário opcional `tools/corrigir_sprites.py` (os PNGs já estão corrigidos); os três testes específicos dos sprites são ignorados se Pillow não estiver instalado. Para refazer o tratamento, instale Pillow separadamente ou use as imagens já prontas.

---

# Kaguya Studio V3.2 — sprites originais incorporados

Esta versão **substitui o pacote V3.1** e já traz os PNGs separados do ZIP fornecido pelo usuário. Não é necessário recortar as sprite sheets nem instalar um segundo pacote de mascote. A V3.2 mantém as funcionalidades anteriores e NÃO modifica o Obsidian, `CLAUDE.md` ou os agentes existentes.

## Novidades desta atualização

- 18 expressões da Kaguya importadas em `mascotes/kaguya/expressoes/` (128 × 128 PNG).
- 10 quadros opcionais em `mascotes/kaguya/animacoes/`: 4 idle, 3 blink, 3 talk.
- Kaguya real aparece **dentro do Studio** e na **mascote flutuante**, com redimensionamento sem suavização (pixels nítidos) e cache de imagens.
- **Clique direito** sobre Kaguya → `Prévia das 18 expressões` para escolher qualquer expressão.
- **Clique direito** → `Animações de teste` para ligar/desligar os frames. Elas começam **desligadas**, pois alguns quadros têm artefatos de recorte e pequenas diferenças de posição. A opção é salva.
- O estado de trabalho do Codex usa a expressão `determinada` quando disponível, erros usam `preocupada` e conclusão usa `feliz`.
- A janela flutuante exibe o sprite em 128, 256 ou 384 pixels (1×/2×/3×) com rodapé separado.
- A geração visual e testes não usam nenhuma API paga.

## Abrir no Windows

1. Extraia o ZIP para uma pasta nova, por exemplo `D:\Ferramentas\KaguyaStudioV3_2`.
2. Instale Python 3.10+ com Tkinter, caso ainda não tenha. Não é preciso `pip install`.
3. Para Studio + mascote flutuante, execute `INICIAR_KAGUYA_STUDIO_V3.bat`.
4. Para deixar apenas a mascote flutuante, execute `INICIAR_SOMENTE_MASCOTE.bat`.
5. Faça **clique direito** na mascote para ajustar o tamanho ou experimentar expressões.
6. Para trabalhar com projetos, vincule a pasta do repositório e do vault; autentique Codex e Claude Code nas CLIs oficiais e confirme permissões quando solicitado.

## Limitação importante das imagens fornecidas

Os PNGs têm canal alfa, mas **alguns cantos continuam opacos** e há pixels de borda/fundo provenientes da prancha original. Por isso a mascote flutuante pode mostrar um quadrado escuro em vez de transparência total. Os quadros de animação também podem apresentar pequenos saltos e recortes. **Kaguya preservou os arquivos exatamente como recebidos**, sem remoção automática do fundo para não apagar cabelos, joias e detalhes da arte.

Se desejar transparência perfeita, edite/limpe os PNGs originais (com Aseprite ou LibreSprite) e substitua os arquivos em `mascotes/kaguya/expressoes/`. Todos devem manter 128 × 128 px e alinhamento. Veja `mascotes/kaguya/LEIA_SPRITES.md`.

## Testes e limites

- `TESTAR_V3.bat` executa os 28 testes locais sem cobrar créditos de IA.
- A interface foi aberta em ambiente gráfico virtual e capturada em `PREVIA_V3_2_SPRITES.png`.
- **Ainda não houve teste no Windows do usuário** nem com assinaturas reais Codex/Claude.
- A integração Obsidian, fila, agentes/skills e pesquisa web permanecem com as limitações do MVP descritas abaixo; não há voz Live contínua nem roteador econômico completo.

---

# Kaguya Studio V3.1 — Mascote interna + flutuante no Windows

**Esta versão substitui a V3 MVP anterior.** Ela mantém os recursos de tarefas, Obsidian e CLIs descritos abaixo e acrescenta a Kaguya nos dois modos pedidos.

## Novidades da V3.1

- Kaguya **dentro do Studio**, no lugar do avatar provisório do Codex.
- Kaguya **flutuante**, arrastável pela tela, opcionalmente sempre no topo. No Windows a janela usa transparência por cor-chave; em outros sistemas a janela pode mostrar fundo escuro.
- Ajuste de tamanho (1, 2 ou 3), posição e preferência de visibilidade salvos em `%LOCALAPPDATA%\KaguyaStudioV3\mascote.json`.
- **Botão `Ocultar Kaguya / Mostrar Kaguya`** na janela principal. Botão direito na mascote flutuante: chat rápido, mostrar Studio, tamanho, sempre visível e ocultar.
- **Clique duplo** abre o chat rápido. Ali você escolhe Codex, Claude ou Equipe, envia tarefas ou guarda ideias (`DEPOIS` e `IDEIA`) sem interromper a execução atual.
- O chat rápido **nunca autoriza escrita no repositório**. Para permitir alteração de código, abra a janela principal e confirme.
- **`INICIAR_SOMENTE_MASCOTE.bat`**: inicia o aplicativo com a janela principal escondida, deixando a Kaguya na área de trabalho. Use a opção `Abrir Kaguya Studio` no clique direito para exibir a interface principal. Fechar a mascote nessa modalidade encerra o aplicativo, após confirmar se houver agentes trabalhando.
- Animação de espera discreta; suporte a sequências `idle`, `blink` e `talk` em PNG, quando fornecidas. Alterações do estado da tarefa mudam a expressão: trabalhando, feliz, preocupada e neutra.
- **Nenhum sprite original foi falsamente extraído da prancha**. Até você colocar os PNGs separados, aparece uma versão provisória pixelada desenhada pelo programa. Consulte `mascotes/kaguya/LEIA_SPRITES.md`.

## Instalação rápida

1. Extraia **todo** o ZIP em uma pasta nova, como `D:\Ferramentas\KaguyaStudioV3_1`.
2. Para abrir Studio e Kaguya juntos, execute `INICIAR_KAGUYA_STUDIO_V3.bat`. Para abrir apenas a mascote flutuante com o Studio escondido, execute `INICIAR_SOMENTE_MASCOTE.bat`.
3. Clique em **+ Vincular projeto** na janela principal e vincule o vault Obsidian existente. O app não reorganiza suas notas.
4. Coloque seus futuros arquivos de sprite em `mascotes/kaguya/expressoes/` e animações em `mascotes/kaguya/animacoes/`. **Não é necessário instalar Pillow**, nem criar API key.
5. Para falar por voz, posicione o cursor no campo do chat e use **Windows + H** (ditado básico). Esta versão não inclui um modo Live de áudio contínuo.

**Limites importantes:** a flutuante funciona enquanto o processo Python está aberto; ela não vira serviço em segundo plano nem é iniciada automaticamente com o Windows. Transparência e permanência visível ao minimizar precisam de validação no Windows real. A integração real com Codex e Claude deve ser testada em seu computador, com suas contas autenticadas. Não instale esta versão sobre a V2 nem use a prancha de expressões como arquivo PNG transparente.

---

# Kaguya Studio V3 — primeira versão executável (MVP)

**Data:** 23/11/2026  
**Sistema:** Windows 10/11 • Python 3.10+ • Codex CLI • Claude Code CLI • Git (para edição)

Este é o **início funcional** da V3. É um aplicativo local escrito em Python/Tkinter, com janela própria, chat por tarefas, dois mascotes vetoriais simples, fila SQLite, consultas ao vault Obsidian já existente, inventário de agentes/skills, auditoria e voz básica do Windows. **Não é o sistema completo descrito no plano da V3.**

## 1. Instalação

1. Extraia todo este ZIP para uma pasta, como `D:\Ferramentas\KaguyaStudioV3`.
2. Instale Python 3.10 ou superior (a biblioteca gráfica Tkinter está incluída na instalação padrão do Python para Windows).
3. Certifique-se de que os executáveis oficiais `codex` e `claude` estão instalados e funcionam pelo terminal.
4. Entre nas **assinaturas** pelas próprias ferramentas, não por API key. Valide em um terminal:
   - `codex login status`
   - `claude auth status` (em versões recentes) ou verifique o login no Claude Code.
5. Dê dois cliques em **`INICIAR_KAGUYA_STUDIO_V3.bat`**.
6. Clique **`+ Vincular projeto`** e escolha a pasta do seu código. Em seguida escolha a pasta raiz do Obsidian, por exemplo `D:\Segundo Cerebro`.
7. No painel de Diagnóstico, clique **Conferir autenticação das CLIs** antes de solicitar uma tarefa.

O aplicativo não precisa de `pip install`, API key, servidor externo, banco de dados na nuvem ou plugins adicionais. A instalação **não altera** `CLAUDE.md`, `AGENTS.md`, `.claude/agents/`, configurações de plugins ou suas notas existentes.

## 2. Como conversar

Na aba **Conversar**, selecione o destinatário (Codex, Claude ou Equipe), escreva uma tarefa e pressione `Ctrl+Enter`.

Exemplos:

- `@Codex: encontre onde a sincronização do chakra é feita` — somente Codex.
- `@Claude: pesquise a documentação de GeckoLib para minha versão e indique as URLs` — somente Claude.
- `@Equipe: corrija o bug e faça revisão independente` — Codex executa primeiro, depois Claude revisa **somente em leitura**.
- `DEPOIS: revisar as texturas` — tarefa guardada; **não interrompe** a tarefa atual nem inicia sozinha.
- `IDEIA: criar animação de transformação` — rascunho local e fila de ideias; não usa IA.
- `AGORA: corrigir erro urgente` — pede confirmação de interrupção se houver execução em andamento.

**Padrão é somente leitura.** Para autorizar alterações, marque **Permitir alterações (Git)** e confirme o aviso. Em modo Equipe, somente Codex recebe permissão de edição; Claude revisa sem editar. Se não houver Git na raiz do projeto, o botão de edição será bloqueado. Antes de testar com projeto importante, faça um backup ou commit e use uma cópia de teste.

A caixa **Permitir pesquisa web** habilita a busca web nativa das CLIs e instrui o agente a pesquisar **quando necessário**, com fontes. Isso não garante que cada pedido será pesquisado. A pesquisa pode depender das permissões e da versão do CLI.

## 3. Segundo Cérebro

A V3 NÃO usa o instalador antigo da V2, nem cria outra estrutura dentro do Obsidian automaticamente.

- **Buscar notas** lê Markdown do vault atual; retorna caminhos reais e trechos curtos.
- Ao pedir uma tarefa, envia aos agentes um contexto pequeno de notas relevantes (até quatro resultados), marcado como **dados não confiáveis**.
- **Registrar ideia** e **Criar rascunho** gravam inicialmente somente em `%LOCALAPPDATA%\KaguyaStudioV3\outbox`.
- **Revisar e sincronizar** mostra a lista de arquivos a criar e exige confirmação. A gravação no vault é **create-only** (nunca sobrescreve notas existentes), em `memoria/agentes/kaguya-studio` ou `conhecimento/kaguya-studio`.
- Seu `tasks/todo.md` existente **permanece intacto**. O SQLite é uma fila **operacional local**. Integração bidirecional com o `todo.md` será implementada após examinar o formato real da nota; não se deve considerar as duas listas sincronizadas nesta versão.
- Não há retreinamento de modelo. O conteúdo é recuperado como informação contextual.

**Privacidade:** ao enviar uma tarefa a uma IA, trechos das notas encontradas podem ser enviados ao serviço oficial dessa IA. Evite vincular vaults com informações privadas que você não deseja compartilhar. O diagnóstico exporta metadados; revise caminhos e nomes antes de enviar qualquer relatório.

## 4. Agentes, plugins e skills

`catalogo/agentes.json` é a cópia do catálogo de **72 agentes** enviado pelo usuário (32 NarutoCD, 32 Blockbench, 8 Segundo Cérebro). **Catálogo ≠ agente efetivamente instalado.**

O painel **Agentes e skills** procura pastas `.claude/agents`, `.claude/skills`, `.agents/skills`, `.codex/agents`, `.codex/skills` no projeto e algumas pastas de usuário. Não instala, atualiza ou modifica plugins/MCPs. As CLIs podem usar sua configuração nativa existente. O Claude recebe permissão para a ferramenta `Agent` quando compatível, mas o uso efetivo depende da versão e das permissões da CLI.

MCPs são bloqueados nas chamadas não interativas desta primeira V3 até passar por auditoria de permissões. Portanto, **plugins que dependem de MCP não executarão automaticamente** por esse painel. A seleção automática de modelos fortes/fracos, a instalação assistida de skills e o orçamento inteligente ainda são evoluções futuras.

## 5. Qualidade, testes e auditoria

O modo Equipe faz **Codex → Claude revisor**. Isso pode encontrar erros adicionais, mas não garante correção perfeita. O Studio roda **`git diff --check`** quando possível e registra o resultado. O estado “executada” significa apenas que o comando das CLIs terminou: **não garante compilação nem funcionamento do mod**.

Na aba **Diagnóstico**, você pode executar testes locais após confirmação. Para repositórios com Gradle Wrapper, a V3 tenta `gradlew --offline test`; para projetos Python, `unittest discover`; em outros projetos, orienta a verificar manualmente. Executar testes pode executar scripts do seu projeto e modificar arquivos de build, portanto só o faça em projetos confiáveis.

**Exportar auditoria Obsidian** gera JSON em `%LOCALAPPDATA%\KaguyaStudioV3\diagnosticos` com agentes detectados, quantidade de notas, conteúdo potencialmente duplicado e possíveis links quebrados. Não inclui o texto integral das notas ou credenciais.

## 6. Voz e mascotes

A interface já desenha um pequeno mascote para Codex e outro para Claude. O botão **Microfone (Win+H)** orienta a usar o ditado do Windows no campo de mensagens. **Ouvir última resposta** tenta usar a voz local SAPI do Windows. Isso **não é** o modo Live nativo do ChatGPT, nem oferece conversa full-duplex ou interrupção natural por voz. O ditado do Windows pode depender de serviços e configurações de privacidade da Microsoft.

## 7. Consumo e faturamento

A V3 usa apenas comandos das CLIs oficiais, não cria API keys e não chama SDKs pagos. Ela bloqueia algumas variáveis conhecidas de provedores/API, e tenta verificar login por assinatura antes de executar cada agente. Se não conseguir confirmar uma assinatura, a execução falha em vez de tentar outra forma de autenticação.

Isso **não garante** que uma conta ou configuração externa não tenha cobrança; confira se não existe uma configuração de pagamento por uso em Claude Code ou Codex. As assinaturas têm limites de uso; a execução em Equipe consome solicitações nas duas. Nenhuma quantidade de tokens economizada foi medida ou prometida.

## 8. Dados locais

`%LOCALAPPDATA%\KaguyaStudioV3\` armazena:

- `studio.sqlite3`: projetos vinculados, fila e histórico de execução (sem tokens de autenticação);
- `logs\`: respostas e logs das tarefas (podem conter conteúdo do projeto; mantenha privado);
- `outbox\`: novas notas pendentes de sua aprovação;
- `diagnosticos\`: relatórios locais para inspeção.

**Não há serviço em segundo plano após fechar o aplicativo.** Se houver tarefa ativa e você encerrar, a V3 solicita interrupção. Tarefas interrompidas são identificadas quando o aplicativo abre novamente.

## 9. O que ainda NÃO está pronto

- Trabalho paralelo em Git worktrees via interface da V3; o modo paralelo anterior do Kaguya Duo V2 continua separado.
- Conversa full-duplex em tempo real com voz como o Live oficial.
- Conexão direta com MCPs, instalação de plugins/skills e auditoria de fontes externas automatizada fora das CLIs.
- Roteamento realmente adaptativo para modelos mais baratos/mais fortes e medição precisa de tokens por tarefa.
- Vigília de qualidade contínua, busca profunda de erros e testes dentro do Minecraft executados automaticamente.
- Sincronização bidirecional do `tasks/todo.md` e deduplicação semântica em todo o vault.
- Teste das CLIs **reais no seu computador** — os testes entregues usam simulações e a interface foi testada em um desktop virtual Linux.

## 10. Testes e fontes

- `TESTAR_V3.bat`: executa testes automatizados locais, sem chamar modelos reais.
- [Documentação oficial Codex CLI](https://developers.openai.com/codex/cli/reference/)
- [Documentação oficial Claude Code CLI](https://code.claude.com/docs/en/cli-reference)
- [Codex como plataforma](https://developers.openai.com/blog/codex-as-a-platform)
- [Permissões e configuração Claude Code](https://code.claude.com/docs/en/settings)

**Próximo passo seguro:** rodar a V3 em um projeto piloto e compartilhar o diagnóstico exportado com a hierarquia real `.claude/agents`, sem credenciais. A partir dessa evidência podemos adaptar o roteador de agentes, skills e a memória ao que está instalado no seu computador.

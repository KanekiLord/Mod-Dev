# Changelog

## 5.2.0 — 25/11/2026 (pacote "Vozes naturais", etapas 1, 2 e 4)

### Novo
- **Página Vozes**: motores de voz com o **status real** deste PC (Kokoro-82M ONNX, vozes do Windows; Qwen3-TTS e
  Chatterbox listados como "não instalado — precisa da sua autorização", com licença, tamanho e avisos — Chatterbox
  está arquivado desde 08/2026). Nada é baixado sem você.
- **Perfil de voz por personagem**, independente da personalidade: motor (automático/Kokoro/Windows), voz, estilo
  (Natural, Suave, Animado, Formal), velocidade e **volume próprio**; "Ouvir Kaguya/Miwa" e Parar. Mudar a Miwa não
  mexe na Kaguya. A voz escolhida na 4.x continua.
- **Texto preparado para fala em pt-BR** sem mudar o chat: números por extenso (com "e" certo: "dois milhões e
  quinhentos mil"), datas, horas, porcentagens, reais, ordinais, versões ("um ponto sete ponto dez"), unidades
  (GB, ms…), siglas técnicas (GPU, VRAM, API…), nomes de arquivo ("main ponto pai"), identificadores de código e links.
- **Benchmark real**: TTFA (até o primeiro áudio, sem a latência da placa de som), tempo de síntese, duração e RTF com
  as frases de teste do pacote; p50/p95; resultados guardados no seu PC.
- **Teste cego A/B**: duas vozes em ordem sorteada, você vota sem saber qual é qual; placar local.
- **Boca guiada pelo áudio de verdade**: a mascote fecha a boca nas pausas da fala (energia do som tocando) e só
  anima enquanto há voz; para junto com o áudio. (Não é sincronização por fonemas.)
- Erros do motor de voz aparecem na tela (antes eram ignorados em silêncio); trecho atrasado nunca toca depois de
  uma interrupção.
- Amostras geradas localmente em `docs/amostras_voz/`.

### Medido (servidor de nuvem de 4 núcleos, sem GPU — não é o seu PC)
- Kokoro, 12 frases do pacote: **RTF p50 ≈ 1,25**, **TTFA p50 ≈ 3 s** (p95 ≈ 6 s), 0 erros.

## 5.1.0 — 25/11/2026 (Etapa B: Kaguya Music)

### Novo
- **Bandeja lateral de música**: uma lingueta fina presa na borda da tela (direita ou esquerda) que, ao clicar, **abre
  na horizontal** para dentro da tela com capa, título, artista, fonte, tempo/progresso (com busca), aleatório, anterior,
  tocar/pausar, próxima, repetir (fila/uma), volume e fila. Passar o mouse destaca e mostra o que está tocando; fecha
  sozinha ao sair (ou fica **fixada**); arraste a lingueta para cima/baixo; tudo é lembrado. Funciona com o Studio
  minimizado ou na bandeja do Windows. Mostrar/ocultar pela página ou pelo ícone perto do relógio.
- **Player local de verdade** (Qt Multimedia/FFmpeg, já incluso): MP3, FLAC, WAV, OGG/Opus, M4A/AAC, WMA. Biblioteca em
  SQLite com as pastas que você escolher (nada é copiado nem alterado), título/artista/capa lidos do arquivo, busca,
  favoritas, contagem de reprodução, **playlists** e fila. Página **Kaguya Music** no menu.
- **Comandos por texto e voz, sem gastar IA**: "toca Blue Bird", "toca a playlist Foco", "pausa a música", "próxima",
  "volume 30%", "abaixa a música", "que música é essa", "coloca X na fila". Funcionam na conversa, no Live e no
  "chamar pelo nome" ("Kaguya, pausa a música").
- **Ducking**: enquanto a Kaguya ou a Miwa falam, a música baixa (25% por padrão, ajustável) e **volta sempre** —
  fim normal, interrupção ou erro. Só o volume do player do Studio muda; o volume do Windows não é tocado.
- **YouTube, Spotify, Amazon Music**: "coloca uma abertura de Naruto no YouTube" abre a busca oficial para você escolher;
  na bandeja, a fonte "Windows" usa as teclas de mídia do próprio Windows (tocar/pausar, próxima, anterior) no app que
  estiver tocando. O Studio não toca vídeos escondidos, não lê o que esses apps tocam e não manda comandos de voz ao
  Spotify (regra da plataforma).

### Corrigido
- Mascotes e player agora pertencem à janela principal: nunca são destruídos fora da thread da interface (evitava um
  travamento raro ao fechar).

## 5.0.0 — 25/11/2026 (Etapa A do pacote de evolução)

Auditoria do pacote × código atual em `docs/AUDITORIA_PACOTE_2026-11-25.md` (matriz de lacunas com evidências).

### Novo
- **Página Personalidades** (spec 04): Kaguya e Miwa lado a lado — nome editável (vale na interface e no "chamar
  pelo nome"; o provedor Codex/Claude não muda), estilo (Kaguya/Miwa clássicas, profissional, descontraída,
  estrategista, professora, fofa, tsundere, gamer, personalizada), apelido, tratamento, saudação, terceira pessoa,
  iniciativa própria (só erros / marcos / conversa livre / silenciosa), **7 controles** (formalidade, humor,
  iniciativa, empatia, criatividade, objetividade, detalhe), emojis, texto livre, voz neural e visual.
  Perfil **global ou só do projeto atual**, **exportar/importar JSON** (aceita o formato do pacote), **restaurar padrão**,
  "Ouvir apresentação" (voz local) e **prévia do texto enviado à IA**. Em tarefas técnicas a personagem fica fora de
  comandos, código e relatórios. Perfis da 4.9.0 são convertidos automaticamente.
- **Início**: painel com estado real — IAs (diagnóstico e limite só se oficial), fila (executando, na fila, guardadas,
  para revisar, última concluída), projetos, Segundo Cérebro (notas indexadas, aprendizados em revisão), modos ativos
  e atalhos (Conversar, Live, Chamar pelo nome, Meu computador, Personalidades, ChatGPT/Claude).
- **Pausar tudo** (cabeçalho, bandeja e Ctrl+Shift+Pause): para todas as tarefas, o controle do PC, o Live, a escuta
  por nome e a fala de uma vez.
- **Segredos protegidos**: as IAs não leem nem alteram `.env`, chaves (`.pem`, `.key`, `id_rsa`…), `.ssh`, `.aws`,
  credenciais e arquivos de login das CLIs — bloqueado pelo próprio Claude Code (verificado de verdade) e pela regra
  no texto para o Codex. Conteúdo de sites/vídeos/arquivos é tratado como dado não confiável.
- `URGENTE:` (igual a `AGORA:`), `@kaguya:` e `@miwa:` na conversa.

### Corrigido
- Captura automática no `.exe` sem console: a proteção contra travamento escreve em arquivo (antes abria uma caixa de
  erro do PyInstaller e o CI ficava parado).

## 4.9.0 — 25/11/2026

### Novo
- **Instalador para Windows** (`KaguyaStudio-Instalador-4.9.0.exe`): instala só para o seu usuário, sem pedir
  administrador, com atalho no menu Iniciar, atalho opcional na área de trabalho, opção "iniciar com o Windows na
  bandeja" e desinstalador. **Para atualizar, rode o instalador da versão nova**: ele encontra a instalação, fecha o
  Studio aberto (mesmo na bandeja), troca os arquivos e mantém seus dados. Desinstalar não apaga seus dados.
- **Uma cópia só do Studio**: abrir de novo traz a janela que já está aberta (útil com a bandeja).
- **Boca e gestos ao falar**: a Kaguya (3 sequências: fala, explicando, acolhedora) e a Miwa (fala, explicando,
  pensando, acenando) mexem a boca e gesticulam enquanto a voz toca — no Live, nas mascotes flutuantes e nos cartões.
  Desliga em Configurações › Mascotes ou no menu da mascote.
  - Quadros da Kaguya refeitos a partir das folhas originais do pacote (o recorte do pacote deixava manchas do fundo e
    buracos no cabelo); o pacote original fica guardado intacto.
  - **Miwa V2 (fala e gestos)** virou o visual padrão (o desenho do pacote é outro, então ela usa o conjunto todo para
    não trocar de roupa no meio da fala); a Miwa V1 continua disponível.
- **Personalidade configurável** (Configurações › Personalidade): estilo (Kaguya/Miwa clássicas, fofa, séria,
  engraçada, tsundere, mentora, gamer ou só o seu texto), apelido para você, tratamento, humor, tamanho das respostas,
  emojis e texto livre. Vale na conversa, na voz, no "chamar pelo nome" e nas tarefas — muda só o jeito de falar.

### Corrigido
- Captura automática podia ficar aberta para sempre com a bandeja ativa (Qt 6 cancela o `quit()` quando uma janela
  recusa fechar); o CI ganhou limite de tempo por etapa.

## 4.8.0 — 25/11/2026

### Novo
- **Meu computador** (menu lateral): a Kaguya e a Miwa trabalham fora dos projetos, como assistentes pessoais —
  ler, criar e editar arquivos na sua pasta de usuário (Downloads, Documentos…), abrir arquivos, pastas, sites e apps,
  usar a tela/mouse/teclado (tela inteira), criar **timers, alarmes, lembretes** (a mascote avisa com voz e
  notificação, mesmo com o Studio na bandeja) e **eventos de agenda** (.ics aberto no seu calendário).
  - Pedidos por voz que são "no computador" ("Miwa, abre o WhatsApp e manda…", "Kaguya, vai na pasta Downloads…")
    viram tarefas de "Meu computador" automaticamente.
  - **Confirmação obrigatória (Sim/Não, com o texto exato)** antes de enviar mensagens/e-mails, apagar/mover/
    sobrescrever seus arquivos e executar programas; sem resposta = não. A mascote aparece, fala a pergunta e a janela
    fica por cima de tudo. Nunca digitam senhas nem fazem compras; apagar pastas inteiras pelo terminal é bloqueado.
  - Explicado e confirmado uma vez antes de ativar. Sem Git aqui: alterações fora de projetos não têm "Desfazer".
- Pesquisa sobre IA grátis, IA por voz e n8n em `docs/PESQUISA_VOZ_IA_N8N.md`.

## 4.7.0 — 25/11/2026

### Novo
- **Chamar pelo nome**: diga "Kaguya, olha isso pra mim" (Codex) ou "Miwa, vê isso pra mim" (Claude Code) — a
  mascote aparece na área de trabalho com um **balão de fala**, responde por voz e, se o pedido for trabalho, cria a
  tarefa (executa direto no modo autônomo; senão analisa sem alterar nada) e avisa por voz quando termina.
  - Escuta opcional (bandeja ou Configurações › Voz), explicada antes de ligar. A transcrição é local; **nada vai
    para a IA antes de ouvir o nome**. Usa o modelo "base" para reconhecer os nomes gastando pouco processador e o
    modelo principal para entender o pedido. Depois da resposta, alguns segundos para continuar sem repetir o nome.
  - Também funciona digitando: "Miwa, revise isso" na conversa vai para o Claude Code.
- A mascote do Claude Code agora se chama **Miwa**.
- **Conversa no estilo WhatsApp**: balões com cauda, suas mensagens à direita com ✓✓, as das IAs à esquerda com o
  rostinho da mascote, hora dentro do balão e avisos do Studio centralizados.
- **ChatGPT e Claude (chats normais)** dentro do Studio: os sites oficiais num navegador embutido, com o seu login,
  sem automação nem leitura das conversas; botão "Copiar contexto do projeto" e "Abrir no navegador".
  Aviso honesto: no Claude o chat e o Claude Code usam o **mesmo** limite; no ChatGPT, Codex e "ChatGPT Work" dividem
  o limite do plano e o chat comum tem limites próprios.
- **Segundo plano**: fechar (X) deixa o Studio rodando na **bandeja**, perto do relógio (opção para minimizar também);
  clique no ícone para abrir; menu com Chamar pelo nome, Live, mascotes e Sair. `--segundo-plano` abre direto na bandeja.

## 4.6.0 — 25/11/2026

### Novo
- **Usar o PC** (chave na conversa, lembrada por projeto): a Kaguya (Codex) e a Claude podem ver a tela e usar
  mouse e teclado durante as tarefas — por exemplo, abrir o Minecraft, entrar no mundo de teste e conferir o mod.
  - Feito com um servidor MCP **do próprio Studio**, passado só para essas tarefas (nada é instalado nas
    configurações das suas CLIs; o Claude roda com `--strict-mcp-config`, sem carregar seus outros MCPs).
  - **Somente a janela do Minecraft** por padrão (Configurações › Uso do computador): as capturas mostram só essa
    janela, cliques fora dela são recusados e a janela é trazida para a frente antes de digitar.
  - Aviso sempre visível com **Parar**; **Ctrl+Alt+End** e **mouse no canto superior esquerdo** também param na hora.
    Limite de ações por tarefa; atalhos do sistema (Ctrl+Alt+Del, Win+L) recusados; cada ação fica registrada na tarefa.
  - Ao ligar pela primeira vez o Studio explica que as capturas vão para a IA (OpenAI/Anthropic) pela sua assinatura.
  - Entrada pelo Windows (SendInput, Unicode para acentos), captura por GDI, coordenadas em pixels reais (DPI).
  - Com o modo autônomo, tarefas pedidas por voz no Live também podem usar o PC.

### Corrigido
- Fechar a janela do Live destruía a janela no meio do próprio evento de fechamento (risco de travar/fechar o app).
- Janelas eram destruídas fora de ordem ao sair do Studio (possível erro ao fechar).

## 4.5.0 — 25/11/2026

### Novo
- **Modo autônomo por projeto** (chave "Autônomo" em Permissões): a Kaguya (Codex) e a Claude editam arquivos,
  rodam comandos, builds e testes e terminam a tarefa **sem pedir confirmação**. Explicado e confirmado uma vez
  por projeto; fica lembrado ao reabrir o Studio; o cabeçalho mostra "Git ✓ • autônomo".
  - **Ponto de restauração Git** antes de cada tarefa (sem mexer no seu stage, branch ou stash) e botão
    **Desfazer** na Fila, que mostra os arquivos alterados e volta tudo como estava — inclusive se a IA fez commit.
  - Codex: sandbox `workspace-write` com rede liberada para builds (Gradle baixa dependências).
    Claude: edição e comandos liberados, com **push, remotes, configuração global, `gh`, instalações
    (npm -g, pip, winget, choco, scoop) e comandos destrutivos do sistema bloqueados** pela própria CLI.
  - Tarefas pedidas por voz no **Modo Live** passam a ser executadas direto quando o projeto está no modo autônomo.
  - Exige repositório Git (é o que permite desfazer); sem Git o Studio oferece criar o repositório.

### Corrigido
- Temporizadores de inicialização (limites, GitHub, áudio) podiam disparar depois de a janela fechar.

## 4.4.0 — 25/11/2026

### Novo
- **Modo Live** (botão "Live" ao lado de "Falar", ou Ctrl+Shift+L): conversa por voz contínua com a Kaguya
  (Codex) ou a Claude, numa janela própria com a mascote grande, legendas ao vivo e nível do microfone.
  - O microfone fica ouvindo com detecção de fala (VAD com ruído de fundo adaptativo); a fala é transcrita
    localmente (faster-whisper) e enviada a uma conversa que fica aberta — o Claude via
    `--input-format stream-json` e o Codex via `app-server` —, então só a primeira resposta tem a partida do processo.
  - A resposta começa a ser falada na primeira frase (voz neural Kokoro, se baixada; senão a voz do Windows).
  - **Interromper falando por cima** (barge-in): a fala para e o turno é cancelado na própria CLI.
  - Comandos falados: "falar com a Claude/Kaguya", "silêncio", "encerrar". Botões: Mudo, trocar IA,
    Silenciar voz, Encerrar.
  - Somente leitura: a IA pode consultar os arquivos do projeto, mas pedidos de alteração viram tarefas
    **DEPOIS** na fila (nada é executado durante a conversa).
  - Usa as assinaturas pelas CLIs oficiais (a voz realtime do Codex exige chave de API paga e não é usada).
  - Limites do Claude informados pela própria CLI durante a conversa aparecem em Uso e limites.

## 4.3.0 — 25/11/2026

### Novo
- **Vozes neurais locais (Kokoro)**, gratuitas e offline, baixadas só com sua autorização (≈ 120 MB,
  arquivos verificados por SHA-256). Uma voz para cada IA (Kaguya e Claude) com mistura de estilos, e
  "Ouvir amostra" em Configurações › Voz.
- **Fala fluida**: o texto é dividido em frases e a próxima é sintetizada enquanto a anterior toca; parar
  interrompe na hora. A voz do Windows continua como alternativa.

## 4.2.0 — 25/11/2026

### Novo
- **Microfone e fone**: escolha em Configurações › Voz (pelo nome, sobrevive a reconectar) e troca rápida no botão
  ao lado de "Falar". Detector automático avisa quando um microfone/fone é conectado ou desconectado e volta ao
  padrão do Windows se o escolhido sumir.
- **Testar microfone** com medidor de nível e **Testar som** no dispositivo escolhido.
- **Uma voz para cada IA** (Kaguya/Codex e Claude), escolhida entre as vozes instaladas no Windows.
- Gravação na taxa nativa do microfone com conversão para 16 kHz (evita erro em microfones de 44,1/48 kHz).

## 4.1.2 — 25/11/2026

### Corrigido
- **Voz no executável**: o .exe era gerado sem a transcrição local e mandava rodar INSTALAR.bat/pip, que não
  funcionam na versão executável. O build agora inclui faster-whisper e o acesso ao microfone, e o CI verifica
  que o próprio .exe consegue carregá-los (`--verificar-voz`). O modelo continua sendo baixado só com sua autorização.

## 4.1.1 — 25/11/2026

### Corrigido
- **Login do GitHub não abria** ("'\\"C:\\Program Files\\GitHub CLI\\gh.EXE\\"' não é reconhecido"): o terminal era aberto
  com aspas escapadas que o cmd.exe não entende. Afetaria também "Entrar" do Codex/Claude em pastas com espaços.
  Agora o comando usa a forma de aspas do cmd (`cmd /k ""C:\\...\\gh.exe" auth login"`), validada num Windows real no CI.
- **"Não está respondendo" ao criar o repositório Git**: o primeiro commit de uma pasta grande rodava na linha
  da interface. Agora roda em segundo plano com aviso de progresso.

## 4.1.0 — 25/11/2026

### Novo — integração com o GitHub (CLI oficial `gh`)
- Diagnóstico › **GitHub**: instalação, conta conectada e login oficial pelo navegador (`gh auth login --web`).
  O Studio nunca lê, mostra ou grava o token.
- Barra do projeto › **GitHub**: Publicar (repositório **privado** por padrão), Salvar versão (commit),
  Enviar (push), Atualizar (pull só *fast-forward*, recusa se houver alterações sem commit), Criar pull request
  de outro ramo (útil para os ramos do modo PARALELO) e Abrir no navegador. Mostra ↑ a enviar, ↓ a receber, ✎ sem commit.
- Nada vai para o GitHub sem o seu clique; as IAs continuam proibidas de fazer commit/push sozinhas.

## 4.0.2 — 25/11/2026

### Corrigido
- **Janela extra pequena** com "0": um selo sem lugar na tela virava janela própria. Removido; selos sem
  janela-mãe nunca mais são exibidos sozinhos.
- **Limites do Codex**: "invalid type: map, expected unit" — versões anteriores do Codex exigem a consulta sem
  parâmetros. Agora a consulta é compatível com versões antigas e novas e, se mesmo assim não houver resposta,
  usa o registro oficial que o Codex grava em `~/.codex/sessions`.
- **Limites não atualizavam**: Codex é consultado ao abrir, a cada 10 min e após cada tarefa (sem gastar cota);
  um dado antigo válido não é mais apagado por uma tentativa que falhou; o painel mostra hora e motivo da última tentativa.
- **Claude**: "Atualizar agora" envia uma mensagem mínima (pergunta antes) para obter a utilização oficial;
  durante tarefas continua automático.

### Novo
- Botão **Criar repositório Git** no projeto (git init, `.gitignore` para mods sem sobrescrever, commit inicial opcional).

## 4.0.1 — 25/11/2026

### Corrigido
- **Janela branca ao abrir o .exe**: o capturador de erros abria uma caixa de diálogo *modal*; um erro
  repetido em timer empilhava diálogos aninhados que nunca eram desenhados, congelando o app. Agora os
  erros vão para `%LOCALAPPDATA%\KaguyaStudio\logs\erros.log` com no máximo um aviso não bloqueante.
- Importação da V3: o vault global passa a ser o que existe no disco (antes podia escolher um inexistente);
  falha na importação não impede mais o Studio de abrir.
- Barra lateral compacta não espreme mais o texto "Nenhum projeto ainda".

### Novo
- Diagnóstico de inicialização: `logs/inicializacao.log` (cada etapa), `logs/travamento_*.txt` (pilhas de
  execução quando a interface para de responder por 12 s) e `logs/falha_grave.log`.
- `--sair-apos N` e teste de CI que abre o `.exe` em modo normal com dados da V3 para importar.
- **Kaguya V2** (9 expressões novas, incluindo *entediada* e *dormindo*) como visual padrão do Codex; a V1
  (18 expressões + animações) continua disponível em Configurações ou no clique direito da mascote.

## 4.0.0 — 25/11/2026

Reconstrução da camada de apresentação em PySide6 e correção dos bloqueios da V3.4, preservando o
núcleo de ideias (fila, DEPOIS/IDEIA, outbox create-only, inventário somente leitura).

### Corrigido (P0)
- Codex falhava fora de repositório Git confiável (`--skip-git-repo-check`).
- Execuções com erro eram marcadas como concluídas (Codex sai com código 0 após 401/limite).
- Instrução do Claude engolida por opção variádica; revisão em modo `plan` não executava.
- Variáveis de ambiente de nuvem bloqueavam todos os agentes.
- Vínculo de projeto e vault: vault global independente, edição, desvincular, colar caminho,
  verificação ao vivo, subpasta de Git, mensagens específicas.
- Diagnóstico das CLIs com estados, versão, executável, login, plano e correção sugerida.

### Novo
- Interface PySide6 com design system próprio, assets independentes (ícones SVG, ornamentos, fundos,
  estados, identidade visual, fontes OFL), layout responsivo 100–200% de DPI.
- Modo Equipe com ciclo de correção e veredito; modo PARALELO em Git worktrees com integração supervisionada.
- Sessões contínuas por projeto e histórico da conversa.
- Segundo Cérebro: índice FTS5 incremental (fora do vault), busca com fonte, outbox com detecção de
  duplicatas, leitura de `tasks/todo.md`, aprendizados extraídos automaticamente.
- Inventário real de agentes/skills/plugins/MCPs conciliado com o catálogo de 72.
- Painel de limites a partir de fontes oficiais (Codex app-server; eventos do Claude Code), nunca inventado.
- Voz local: leitura interrompível, push-to-talk com faster-whisper (opcional), comandos falados não interruptivos.
- Mascotes com transparência real por pixel, expressões por estado da própria IA, chat rápido.
- Migração automática dos projetos/fila da V3.x (somente leitura do banco antigo).
- Instalador local (`INSTALAR.bat`), executável Windows via CI (PyInstaller), testes no Windows.

### Mantido
- `legacy_v3_4/`: código da V3.4 para comparação e para os testes de regressão. Não é mais a versão principal.

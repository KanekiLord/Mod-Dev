# O que foi testado — e o que não foi

Princípio: nada é declarado "funcionando" com base em mock. Cada linha diz **onde** foi verificado.

## Automatizado (`python -m unittest discover -s tests -t .`) — 53 testes, 5 condicionais

| Arquivo | Cobertura | Tipo |
|---|---|---|
| `test_regressoes_v34.py` (9) | Cada defeito da V3.4 é reproduzido no código antigo e verificado no novo. | CLIs simuladas que imitam as reais |
| `test_engine.py` (11) | Turno único com streaming e sessão retomada; Equipe com reprovação → correção → aprovação; limite de ciclos; erro com código 0; limite atingido pausa a fila; DEPOIS/IDEIA não executam e persistem; aprendizados → outbox sem tocar no vault; escrita exige Git; PARALELO em worktrees isolados; sessão expirada → nova conversa. | CLIs simuladas + Git real |
| `test_core_v4.py` (20) | Caminhos (aspas, `%VAR%`, espaços, acentos), verificação de pasta/vault, projetos (editar, desvincular, revincular, persistência), migração da V3 somente leitura, estados do diagnóstico, executável manual, parsers stream-json/JSONL, índice FTS5 incremental e exclusões sensíveis, outbox create-only e duplicatas, extração de aprendizados, `todo.md`, inventário × catálogo sem segredos, limites (parse oficial e "indisponível"), veredito nunca aprovado por omissão, intenções. | Unitário |
| `test_ui_v4.py` (8) | Diálogo de vínculo (colar caminho com aspas, vault próprio, salvar); tarefa de Equipe pela UI atualizando conversa, pipeline e mascotes; DEPOIS não inicia trabalho; todas as páginas sem projeto; modos responsivos; recorte de sprite sem alterar o PNG. | Qt offscreen |
| `test_cli_reais.py` (5) | **CLIs oficiais reais**: descoberta, versão, flags, estado de login, execução headless real e consulta de limites do Codex. Só com `KAGUYA_TEST_REAL_CLIS=1`; execução com conta logada só com `KAGUYA_TEST_REAL_RUN=1`. | Binários reais |

## Modo Live e vozes (4.3.0–4.4.0)

- `test_live.py`: VAD (início/fim de fala, ruído adaptativo, barge-in), comandos falados, marcador de tarefa
  nunca falado e convertido em tarefa DEPOIS, interrupção do turno, conversa persistente com o Claude
  simulado em stream-json (vários turnos num só processo).
- `test_ui_v4.py › LiveUi`: janela Live com turno completo pela conversa simulada do Claude (legenda do usuário,
  resposta, fala pela IA certa), troca para o Codex indisponível mostrando o erro, encerrar limpa a sessão;
  sem transcrição local o Live explica o que falta em vez de abrir.
- `test_speech.py`: divisão em frases (primeira curta), fila de fala que sintetiza à frente e para na hora.
- **Real (Linux)**: Claude Code 2.1.331 em `--input-format stream-json` atendeu vários turnos num processo,
  manteve contexto, enviou `rate_limit_event` e aceitou a interrupção `control_request`. Kokoro int8
  sintetizou pt-BR (pf_dora) localmente. `codex app-server` → `thread/realtime/start` respondeu
  "realtime conversation requires API key auth" (por isso a voz realtime do Codex não é usada).
- **CI Windows**: download dos arquivos Kokoro com verificação de hash e síntese dentro do `.exe` (`--verificar-voz`).

## Extension Hub — 5.8.0

- `test_hub.py` (casas falsas de Claude/Codex + CLIs falsas que editam a configuração como as oficiais): todo o checklist
  do pacote (ver tabela em `docs/EXTENSION_HUB.md`), incluindo delegação e lock/backup numa tarefa real do motor.
- `test_ui_v4.py › HubUi`: página sincroniza sozinha, filtros, detalhes sem segredos, teste oficial, recusar plano não
  roda nada, aprovar instala/remove pelo comando oficial, roteamento Kaguya → Miwa com MCP liberado, plugin só da web.
- **Real** (Claude Code 2.1.332 e Codex 0.172 neste servidor): descoberta de 32 itens; `claude mcp get`, handshake no
  Codex, `claude plugin details`; ciclo instalar → testar → remover nos dois clientes; servidor quebrado reportado como
  falha; segredos fora do catálogo; MCPs de teste removidos ao final.

## Etapa D — 5.7.0 (Leitor Universal + conhecimento)

- `test_reader.py` (arquivos reais gerados por python-docx/openpyxl/python-pptx, PDF montado à mão): log de 5.000
  linhas → só o trecho do erro com número de linha (menos de 1/20 do arquivo); JSON/CSV/Windows-1252; `.env`, chaves,
  `.ssh`, `.exe` recusados; pasta vizinha "NarutoCD2" e atalho para fora negados; zip slip, zip bomb, script dentro e
  XML com entidades **detectados sem extrair nada**; `.jar` de mod com `mods.toml` e classes; Word com título/tabela e
  `.docm` com macro avisada; Excel com fórmula como texto; PowerPoint com notas; PDF com e **sem pypdf** (o
  instalador não tem pypdf); imagem; processo separado e tempo máximo.
- `test_knowledge.py`: propriedades da spec 08; mesma fonte → atualização com backup idêntico ao original e sem nota
  duplicada; repetição exata não gera nada; conteúdo já conhecido → atualização; versão diferente → divergência com
  as duas; nota editada depois da proposta → nada muda; fila sem vault aprovada depois; relatório (antigas, link
  quebrado, sem fonte, duplicadas) e revalidação que muda **só** o status; **Kaguya registra e a Miwa recupera em
  outra sessão/banco** com caminho, versão, fonte e status; detecção de versão.
- `test_ui_v4.py`: `AttachUi` (anexo de log pela Conversa: prévia com só o trecho relevante, token oculto, tarefa com
  o anexo, anexo limpo depois; arquivo sensível sem botão Anexar), `KnowledgeUi` (proposta com diff, aprovar, relatório)
  e `ObservationUi` (indicador aparece com aba compartilhada/controlada e "Parar de compartilhar" some com ele).
- CI Windows: o `.exe` também lê um log com `--ler-arquivo`.

## Live com chibis — 5.6.0

- `test_ui_v4.py › LiveUi`: a conversa completa do Live (Claude falso) roda igual com a **janela grande e com o chibi**;
  o chibi acena ao começar, pensa, abre o notebook se demorar, fala só quando há voz (boca fechada na pausa), fica
  sério no erro, mostra o balão, troca de IA e lembra a posição; a configuração escolhe chibi (padrão) ou janela.
- `ChibiAssets`: todo quadro existe, é RGBA, do mesmo tamanho (Kaguya 128, Miwa 256) e com canto transparente;
  originais guardados; retratos da V3 com borda suave. `KaguyaV3`: variante carrega, fala e não sofre o recorte de
  pixel art.
- Visual conferido em captura (Kaguya ouvindo, Miwa falando, Miwa ouvindo você).

## Etapa C — 5.5.0 (Kaguya Browser + YouTube Intelligence)

- `test_browser.py`: endereço vs pesquisa; favoritos/histórico (anônima não grava, sem duplicar); compartilhamento por
  aba e por IA, revogar na hora, linha do tempo; um controlador por aba, usuário assume e a IA **não retoma** até ele
  devolver; "Parar"; detecção de prompt injection; contexto cercado; ações de alto impacto; YouTube (IDs, capítulos,
  legendas json3/xml, janela do trecho, escolha da legenda, relatório honesto, nota); **anexo chega às duas IAs
  cercado como dado, antes da TAREFA, com a imagem** (`--image` no Codex sem engolir o prompt; `--add-dir` só da pasta).
- `test_ui_v4.py › BrowserUi` (navegador real QtWebEngine + servidor local): aba pessoal → recusar compartilhar não
  envia nada; aceitar → tarefa com texto visível, **sem a senha digitada nem texto escondido**, alerta de injection,
  resposta exibida no navegador; revogar; anônima fora do histórico; favorito. YouTube (página com a mesma estrutura
  de dados): metadados e capítulos, **legendas lidas pelo mesmo caminho do player**, quadro capturado, tarefa com
  níveis A/B/C e imagem, "para depois".
- `test_ui_v4.py › BrowserControlUi` (**o servidor MCP real**, como o Claude/Codex o iniciam): só leitura nega clique;
  com controle: lista elementos, **recusa campo de senha**, digita no campo de busca, "Comprar agora" pede confirmação e
  a recusa bloqueia, usuário assume → IA bloqueada, devolve → link clicado, aba de pesquisa isolada fora do histórico,
  Kaguya sem acesso, **Pausar tudo mata a chave**. Tarefa com controle recebe o servidor e a chave morre ao terminar.
- CI Windows: o `.exe` também sobe `--mcp-browser` e recusa sem ponte.
- **Não testado**: YouTube real (bloqueado no servidor de nuvem); Claude/Codex reais usando as ferramentas (precisam
  da sua conta) — teste no seu PC: compartilhe uma aba, ligue "Pode controlar" e peça algo.

## Filtro de ruído — 5.4.0

- `test_denoise.py`: processamento em pedaços de qualquer tamanho dá o mesmo resultado; ventilador cai ≥ 12 dB e um
  som que começa no meio é preservado; rajadas detectadas como vento (ventilador sozinho não); filtro do botão Falar;
  Silero separa a fala real (amostra do Studio) de ventilador + vento; **sessão Live sem filtro é enganada pelo
  ruído (o problema relatado) e com filtro não começa a ouvir nunca**; fala dentro do ruído chega inteira, num trecho;
  alucinações do Whisper removidas; medição do ambiente com números reais e aviso de vento.
- `test_ui_v4.py › NoiseUi`: filtro ligado por padrão, troca salva, medição mostra o resultado e libera "Ouvir".
- **Simulação com Whisper real** (ruído sintético: ventilador com pás a 58 Hz + ruído rosa, rajadas graves com
  saturação da cápsula; fala = amostras do Studio a -20 dBFS): ver CHANGELOG 5.4.0.
- **Não feito**: teste com o seu ventilador e o seu microfone — use "Medir ruído do ambiente" e me diga o resultado.

## Vozes naturais — 5.3.0 (Qwen3-TTS opcional)

- `test_voices.py › HeavyInstall` (uv falso + modo de teste do processo de voz, sem download): instalação completa →
  marca só depois de carregar e responder; PyTorch pedido do índice **CPU**; o motor fala, mantém o processo entre
  frases, relata erro e continua vivo; Remover apaga tudo; passo que falha não deixa marca; **cancelar no meio de um
  passo silencioso (download longo) para em < 10 s**; checksum errado do uv → nada instalado; sem processos ou
  arquivos abertos sobrando (rodado com `-W error::ResourceWarning`).
- `test_ui_v4.py › VoicesUi`: recusar a confirmação não cria nada; a mensagem mostra licença, tamanho, origem, pasta,
  CPU e que dá para cancelar.
- **Real (nuvem 4 vCPU)**: `qwen-tts 0.1.1` + `torch 2.15.0+cpu` num ambiente isolado; o mesmo `WorkerClient` do Studio
  carregou o modelo em 8,8 s e sintetizou 7 frases pt-BR com RTF 3,75–4,13; Whisper reconheceu português (0,99–1,0)
  nas vozes serena, vivian, ono_anna e sohee. Bug encontrado: a biblioteca imprime no stdout → canal protegido.
- **Não feito**: instalação real no Windows (≈ 4 GB — fica para você, pelo botão); avaliação auditiva sua.
- `test_music.py › CorruptionRecovery`: arquivo que não é banco → backup + biblioteca funcionando; página da tabela de
  músicas danificada no disco com o Studio aberto → recupera na hora, mantém pasta e playlist, reescaneia, e o arquivo
  novo abre limpo. (Motivo: erro "malformed" visto uma vez no CI Windows da 5.1.0; não reproduzido.)

## Vozes naturais — 5.2.0

- `test_voices.py`: números e frases do benchmark do pacote falados corretamente; motores pesados nunca aparecem
  como instalados; perfis independentes, migração da 4.x e valores limitados; volume por personagem aplicado; fallback
  sem motor dá erro claro (bug encontrado pelo teste e corrigido); benchmark mede e **relata** erros; fila: silêncio
  inicial → boca fechada, trecho alto → boca aberta; interrupção durante a síntese → o trecho atrasado **não toca**;
  erro do motor chega à interface.
- `test_ui_v4.py › VoicesUi`: lista honesta de motores (Qwen3/Chatterbox desabilitados até instalar), perfil da Miwa
  salvo sem mexer na Kaguya.
- **Real (Kokoro-82M ONNX, 12 frases pt-BR do pacote, CPU de 4 núcleos sem GPU)**: Kaguya RTF p50 1,249, TTFA p50
  3,31 s / p95 6,05 s; Miwa (Animado 1,05×) RTF p50 1,271, TTFA p50 2,82 s / p95 5,43 s; 0 erros.
- **Não feito (na 5.2)**: Qwen3-TTS (feito na 5.3) e Chatterbox (adiado: arquivado); avaliação auditiva sua;
  medição no seu PC/GPU.

## Etapa B — 5.1.0 (Kaguya Music)

- `test_music.py`: varredura de pastas (ignora ocultas e não-áudio, sem duplicar), título/artista pelo nome do arquivo,
  busca, playlists, favoritas, limpeza de arquivos apagados; comandos em português e frases que **não** são música
  ("coloca o botão no menu", "coloca a tarefa X na fila"); **player real**: decodifica WAV pelo FFmpeg do Qt (duração
  500 ms medida), passa sozinho para a próxima ao fim, volume 30% aplicado, ducking 25% de 30% e restauração,
  YouTube abre a busca oficial.
- `test_ui_v4.py › MusicUi`: a lingueta tem 26 px; clique abre na horizontal ancorada na borda; fixar mantém aberta;
  trocar para a borda esquerda e persistir; "toca Blue Bird" e "volume 40%" na conversa não criam tarefa; fala da IA
  baixa e restaura a música, inclusive quando interrompida; página lista a biblioteca.
- Não testável aqui: som saindo na placa (o servidor não tem áudio) e as teclas de mídia em apps reais do Windows.

## Etapa A — 5.0.0

- `test_persona.py`: padrões, controles e textos; conversão do formato 4.9.0; ajuste por projeto; nome personalizado
  no "chamar pelo nome"; exportar/importar (inclusive o formato `personalidades.exemplo.json` do pacote); restaurar;
  personalidade **depois** das regras no texto enviado à CLI.
- `test_ui_v4.py › PersonaUi`: estilo move os controles, salvar não afeta a outra IA, nome aparece na mascote, ajuste por
  projeto e remoção, restaurar devolve o nome. `HomeAndPause`: Início mostra dados reais (fila, projeto, modos, limite
  indisponível); Pausar tudo cancela tarefa longa em execução e aciona a parada do controle do PC.
- **Real (Claude Code 2.1.331)**: com as regras do Studio, `.env` e `sub/.env.local` foram negados ("File is in a directory
  that is denied by your permission settings") e um arquivo comum foi lido normalmente.

## Instalador, fala animada e personalidade (4.9.0)

- **CI Windows** (passo "Instalador"): gera o instalador com Inno Setup, instala em silêncio só para o usuário,
  confere o atalho do menu Iniciar, abre o Studio instalado na bandeja e roda o instalador de novo — ele precisa fechar
  o Studio aberto e atualizar —, depois desinstala e confere que os dados do usuário continuam.
- Real (Linux): segunda cópia só traz a primeira para a frente; `--sair` fecha a aberta; sem cópia aberta sai em silêncio.
- `test_ui_v4.py › TalkingMascots`: quadros trocam enquanto fala e voltam ao normal ao parar, para as duas; pode
  desligar; os quadros refeitos da Kaguya não têm fundo nos cantos e o pacote original está preservado.
- `test_persona.py`: padrões por IA, salvar, texto gerado (apelido, tratamento, humor, tamanho, emojis só no texto),
  desligar; a personalidade vai **depois** das regras no texto realmente enviado à CLI.
  `test_ui_v4.py › PersonaUi`: a tela salva por IA sem afetar a outra.

## Meu computador (4.8.0)

- `test_pc_mode.py`: horários ("16:30", "9h" → amanhã, data completa), timers que vencem, evento .ics correto;
  confirmação ida e volta, sem resposta = não; abrir programa exige confirmação; abrir pasta/site; ferramentas novas só
  existem no modo Meu computador; "regedit" recusado; tarefa sem Git roda na pasta do usuário com tela inteira, com
  `rm -rf`, `Remove-Item -Recurse` e `git push` bloqueados.
- `test_ui_v4.py › PcModeUi`: sem ativar, pedido por voz explica como ativar; ativação explicada; tarefa digitada e por
  voz; pergunta de confirmação aparece e a resposta volta ao processo da IA; alarme faz a mascote aparecer e falar.
- **Real (Claude Code 2.1.331, tela simulada)**: "Miwa, abre o WhatsApp e manda mensagem para mamãe…" → abriu o app
  pelo menu Iniciar, conferiu a tela; como a janela não apareceu (simulador), **não enviou nada** e relatou isso.
  "Vá até Downloads, abra Batata Game 2 e analise" → achou `main.py`, **reproduziu** o erro `vida`/`vidas`
  (NameError) e entregou análise e lista de problemas.

## Chamar pelo nome, conversa, chats e bandeja (4.7.0)

- `test_live.py › NameDetection`: "Kaguya, …", "Ei Miwa, …", "Miwa (Claude Code) …", grafias do Whisper ("kaguia");
  citar o nome no meio da frase não chama; mensagens digitadas com o nome vão para a IA certa.
- `test_live.py › WakeByName`: fala sem nome é ignorada sem chegar à IA; "Miwa, implemente…" acorda a Miwa, responde
  e cria a tarefa; dentro da janela de continuação a próxima fala vai para ela sem o nome; depois volta a ignorar;
  só "Kaguya" faz a Kaguya cumprimentar e esperar o pedido.
- `test_ui_v4.py › CallByNameUi`: a mascote aparece com o balão (pedido + resposta); pedido sem modo autônomo vira
  análise somente leitura; ao terminar a IA fala um resumo sem os títulos do relatório; mensagem digitada "Miwa, …"
  vai para o Claude e aparece à direita; fechar com bandeja esconde e reabre; página de chats não carrega nada sem
  clique e copia o contexto do projeto.
- **Real (Linux)**: o navegador embutido abriu o claude.ai de verdade (aqui, num servidor de nuvem, o Cloudflare
  pediu a verificação anti-robô).
- **CI Windows (4.6.0)**: o `.exe --mcp-desktop` listou janelas, capturou a tela 1024×768, moveu o mouse e apertou
  tecla no Windows real.

## Uso do computador (4.6.0)

- `test_desktop.py` (backend simulado): só a janela permitida é capturada e as coordenadas são convertidas para a
  tela; clique fora da janela, janela não permitida e janela ausente são recusados; captura da tela inteira reduzida;
  botão Parar, failsafe do canto e limite de ações; Ctrl+Alt+Del recusado; teclas seguradas; protocolo JSON-RPC;
  servidor rodando por `run_kaguya.py --mcp-desktop` via stdio como as CLIs fazem; o motor passa ao Claude só o
  servidor do Studio (`--strict-mcp-config`) e o Claude simulado **inicia o servidor a partir dessa configuração** e
  usa screenshot + clique; o Codex recebe `mcp_servers.kaguya_desktop.*` com aprovação automática; tarefas normais
  não recebem nada disso.
- `test_ui_v4.py › DesktopUi`: recusar o aviso mantém desligado; o aviso fala da janela permitida e de que as capturas
  vão para a IA; fica salvo por projeto; tarefa mostra e esconde o aviso flutuante, que conta as ações; Parar grava
  a parada.
- **Real (Linux, backend simulado)**: Claude Code 2.1.331, sem nenhuma confirmação, chamou
  `mcp__kaguya_desktop__screenshot`, viu a imagem 800×600 da janela "Minecraft", clicou no centro (convertido para a
  posição real na tela), apertou F3, conferiu com outro screenshot e relatou com honestidade que não viu efeito.
- **Real (Linux)**: `codex-cli 0.172` aceitou a configuração do servidor (`default_tools_approval_mode` só aceita
  auto/prompt/writes/approve — verificado com um valor inválido).
- **CI Windows**: teste do backend real (captura GDI, mover e ler o cursor, listar janelas, tecla) e o `.exe` com
  `--mcp-desktop` por pipes usando o Windows de verdade (lista janelas, captura a tela, move o mouse, tecla).

## Modo autônomo (4.5.0)

- `test_checkpoint.py` (Git real): o ponto de restauração não altera nada ao ser criado; depois de a "IA" editar,
  apagar, criar arquivos e até fazer commit, Desfazer volta HEAD, arquivos, arquivos não rastreados e o stage
  do usuário exatamente como estavam, sem tocar em arquivos ignorados (ex.: `build/`); também em repositório sem commits.
- `test_engine.py › AutonomyTests`: tarefa autônoma do Codex roda com escrita + comandos + testes, rede liberada no
  sandbox, cria o ponto de restauração e é desfeita; Claude autônomo libera Edit/Bash mas mantém `git push` etc.
  bloqueados e nunca usa `bypassPermissions`; sem Git a tarefa autônoma é recusada; tarefas normais não mudam.
- `test_ui_v4.py › AutonomyUi`: ligar exige aceitar a explicação (recusar mantém desligado), fica salvo por projeto,
  envio sem diálogo de confirmação, Desfazer na Fila, desligar devolve as chaves manuais; sem Git não liga.
- **Real (Linux)**: Claude Code 2.1.331 com o comando autônomo do Studio criou arquivo e rodou `git status` sem
  pedir nada, e recusou `git push` ("Permission to use Bash with command git push --dry-run has been denied").
  `codex-cli 0.172` aceitou `-c sandbox_workspace_write.network_access=true` (sem login, parou no 401 esperado).

## Verificado com binários reais (ambiente Linux de desenvolvimento)

- `codex-cli 0.172.0` sem login: diagnóstico "Não autenticado"; `exec` fora do Git agora chega à API e
  falha com **401** reportado como falha (a V3.4 parava em "Not inside a trusted directory");
  `app-server` → `account/rateLimits/read` responde "autenticação necessária" → painel "indisponível".
- `Claude Code 2.1.331` logado neste ambiente: diagnóstico "Pronto (oauth_token)". Uma execução real do
  comando montado pelo Studio (`-p --output-format stream-json --verbose --permission-mode dontAsk
  --allowedTools … --disallowedTools …`, tarefa via stdin) concluiu com sucesso e sessão identificada
  (uma requisição mínima). Também confirmado que `--resume` com ID inexistente gera
  `result.is_error` + "No conversation found" — o Studio recomeça a conversa automaticamente.

## Verificado visualmente

Capturas reais da aplicação (modo demonstração, CLIs simuladas, rotulado na própria janela) em
`assets/previews/v4/`: todas as páginas a 100%; conversa a 100% (1366×768), 125%, 150% (1920×1080) e
200%; mascotes flutuantes. Transparência das mascotes sobre fundo claro/escuro/papel de parede:
`assets/previews/transparencia_mascotes.png`.

## CI em Windows (`.github/workflows/kaguya-windows.yml`)

Roda em `windows-latest`: suíte completa (incluindo as CLIs oficiais instaladas via npm, **sem conta**),
capturas 100–200% com renderização do Windows, build PyInstaller e teste de fumaça do `.exe`.

**Execução de 25/11/2026 (Windows Server 2025, Python 3.12): todos os passos com sucesso.**

- 53 testes OK, incluindo as CLIs reais no Windows:
  - Claude Code 2.1.331 encontrado em `C:\npm\prefix\claude.CMD` (launcher npm `.cmd`) → "Não autenticado",
    com a correção sugerida; execução headless real → falha reportada com o motivo exato
    `Not logged in · Please run /login` (sessão lida do stream-json).
  - codex-cli 0.172.0 em `C:\npm\prefix\codex.CMD` → "Não autenticado"; `exec` fora do Git chegou à API
    (401 reportado como falha, não como "executada"); limites → "indisponível" sem login.
- Capturas renderizadas pelo Windows a 100/125/150/200% (artefato `capturas-windows`). O runner tem tela
  pequena, então a janela ficou no tamanho mínimo (1180 px lógicos) — também é um teste do layout compacto.
- Executável `KaguyaStudio.exe` gerado (ZIP de 67 MB, artefato `KaguyaStudio-windows`) e aberto no teste
  de fumaça, renderizando a página Diagnóstico sem Python instalado no caminho do app.
- Problema encontrado pelo CI e corrigido: janelas antigas continuavam recebendo eventos de outros
  motores (ponte de eventos global) — agora cada janela só reage ao seu motor e se desliga ao fechar.

## NÃO testado (depende do seu computador/contas)

- Login e tarefas reais com **suas** assinaturas Codex e Claude; leitura de limites com sua conta Codex.
- Seu vault real e o formato real do seu `tasks/todo.md`; seus 72 agentes nos diretórios reais.
- Chamar pelo nome com o seu microfone e ruído de casa; login do ChatGPT/Claude no navegador embutido
  (o Google pode recusar navegadores embutidos — use e-mail ou "Abrir no navegador").
- Controle real do Minecraft no seu PC (captura de janela OpenGL, foco, teclas no jogo) e o Codex usando o
  servidor com a sua conta.
- Microfone/fone reais, eco sem fone no Live, transcrição faster-whisper com sua voz, vozes SAPI do seu Windows
  e a velocidade do Kokoro no seu processador.
- Minecraft/Gradle de projetos reais (o Studio executa os testes do projeto só com sua autorização).

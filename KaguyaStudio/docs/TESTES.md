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
- Controle real do Minecraft no seu PC (captura de janela OpenGL, foco, teclas no jogo) e o Codex usando o
  servidor com a sua conta.
- Microfone/fone reais, eco sem fone no Live, transcrição faster-whisper com sua voz, vozes SAPI do seu Windows
  e a velocidade do Kokoro no seu processador.
- Minecraft/Gradle de projetos reais (o Studio executa os testes do projeto só com sua autorização).

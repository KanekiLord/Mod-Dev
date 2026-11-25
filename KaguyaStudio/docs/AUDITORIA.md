# Auditoria técnica da V3.4 — por que conexões e vínculos falhavam

Data: 24–25/11/2026. Base auditada: `legacy_v3_4/` (código da V3.4 sem alterações de lógica).
Evidências obtidas com as **CLIs oficiais reais** instaladas neste ambiente de desenvolvimento
(`codex-cli 0.172.0` via npm, `Claude Code 2.1.331`) e com testes de regressão que reproduzem cada defeito
(`tests/test_regressoes_v34.py`: cada teste demonstra o defeito na V3.4 e verifica a correção na V4).

> Limite desta auditoria: não houve acesso ao seu Windows nem às suas contas. O que depende delas está
> marcado como **pendente de validação no seu PC** no fim deste documento.

## P0 — bloqueadores

| # | Defeito na V3.4 | Evidência | Correção na V4 | Teste |
|---|---|---|---|---|
| 1 | `codex exec` fora de um repositório Git confiável **sempre falha**: a V3.4 não passava `--skip-git-repo-check`. Pastas de projeto sem Git (ou ainda não "confiadas") nunca funcionavam. | Execução real: `Not inside a trusted directory and --skip-git-repo-check was not specified.` (código 1) | Flag adicionada para trabalho somente leitura; edição continua exigindo Git (para poder desfazer). | `test_codex_outside_git_failed_in_v34_and_works_in_v4`; real: `test_headless_run_outside_git_reaches_auth…` |
| 2 | **Falha marcada como sucesso**: `codex exec --json` termina com código **0** mesmo quando todas as requisições falham (401, limite, rede). A V3.4 só olhava o código de saída e concluía como "executada". | Execução real sem login: 5 tentativas com `401 Unauthorized` e saída 0. | O resultado só é sucesso com evento de conclusão (`turn.completed` / `result`) e sem erro fatal; o motivo exato vai para a tarefa. | `test_codex_exit_zero_with_errors_was_reported_as_success`, `test_failure_with_exit_zero_is_error_and_pauses_queue` |
| 3 | `--disallowedTools` e `--tools` do Claude Code são **variádicos**; a V3.4 colocava a instrução logo depois, que era engolida como nome de ferramenta. | `claude --help`: `--disallowedTools <tools...>` | Nenhum argumento posicional após opções variádicas; a tarefa vai só pelo stdin. | `test_claude_positional_after_variadic_option` |
| 4 | Revisão do Claude em `--permission-mode plan` (headless): o modo plano só planeja e não pode ser aprovado sem interface. Em escrita, `acceptEdits` sem `Bash` liberado impedia rodar testes. | `claude --help` (modos) | Leitura: `dontAsk` + ferramentas de leitura; escrita: `acceptEdits`; comandos/testes: permissão explícita por tarefa. | `test_write_mode_can_run_tests_only_with_permission` |
| 5 | **Qualquer** variável como `AWS_ACCESS_KEY_ID` ou `ANTHROPIC_BASE_URL` no Windows fazia a V3.4 recusar **todos** os agentes com uma mensagem genérica. | Reproduzido neste próprio ambiente: `ValueError: Configuracao de provedor externo detectada: ANTHROPIC_BASE_URL, AWS_ACCESS_KEY_ID` | As variáveis de API/provedor simplesmente não são repassadas às CLIs; o diagnóstico informa quais foram ignoradas. | `test_unrelated_cloud_variable_blocked_every_agent` |
| 6 | Vincular projeto exigia **duas janelas de pasta seguidas** e o vault obrigatório no mesmo passo; cancelar/errar o segundo descartava tudo **sem mensagem**. Com as mascotes "sempre visíveis", a segunda janela podia abrir **atrás** delas. | `studio.py:_add_project()`; `Store.add_project` exigia vault existente | Vault global independente; projeto com vault opcional; caminho editável/colável com verificação ao vivo e mensagem específica; mascotes ocultas durante o seletor; diálogo com janela-mãe. | `test_project_could_not_be_saved_without_vault`, `test_link_project_dialog_and_persistence` |
| 7 | Revincular a mesma pasta com outro vault era **ignorado** (`INSERT OR IGNORE`). Não havia editar/desvincular. | Teste de regressão | Revincular atualiza; editar e desvincular disponíveis (sem apagar arquivos). | `test_relinking_was_silently_ignored`, `test_store_edit_unlink_relink_and_persist` |
| 8 | Projeto em **subpasta** de um repositório Git era recusado ("escolha a raiz do repositório"). | `runtime.check_project_writable` | Raiz Git detectada e usada; o projeto pode ser subpasta. | `test_git_subfolder_was_refused` |
| 9 | "Verificar CLIs" **exigia projeto vinculado** — como vincular falhava, nem o diagnóstico rodava. | `studio.py:_check_clis` | Diagnóstico independente de projeto. | — |
| 10 | Diagnóstico das CLIs genérico ("NÃO VERIFICADO — …"); sem versão, caminho, motivo ou correção. GUIs abertas pelo Explorer muitas vezes não têm `%APPDATA%\npm` ou `%USERPROFILE%\.local\bin` no PATH. | `runtime.check_subscription` | Estados (Não instalado / Encontrado / Não autenticado / Sem permissão / Pronto / Erro…), versão, executável, método de login, plano, correção sugerida; busca nos locais padrão do Windows; escolha manual do executável; botão **Entrar** abre o login oficial. | `test_diagnosis_states`, real: `test_discovery_and_not_logged_in` |

## P1 — recursos incompletos

- **Equipe** era Codex → Claude (somente leitura) → "executada", sem retorno ao Codex nem veredito.
  Agora: implementação → verificação → revisão → correção (retomando a mesma sessão do Codex) → veredito,
  com limite de ciclos, logs separados e veredito estruturado (nunca aprova por omissão).
- **Sem continuidade**: cada mensagem era um processo novo. Agora a sessão por projeto é retomada
  (`--resume` no Claude, `exec resume` no Codex) e o histórico aparece ao reabrir.
- **Limites**: não existia. Fontes oficiais verificadas:
  - Codex: `codex app-server` → `account/rateLimits/read` (mesmo protocolo da extensão oficial). Testado
    com o binário real: sem login responde "codex account authentication required to read rate limits".
  - Claude Code: o modo `stream-json` emite `rate_limit_event` com `utilization` (0–1) e `resetsAt`
    por janela (5 h, 7 dias…), confirmado no próprio binário 2.1.331. Não há consulta sem custo, então o
    painel mostra o último dado recebido ou "indisponível".
- **Voz**: era Win+H e leitura de 1000 caracteres. Agora: leitura interrompível (voz pt-BR do Windows),
  push-to-talk com transcrição local opcional (faster-whisper) e comandos falados que não interrompem.
- **Mascotes**: os 9 PNGs da Claude têm o corpo com alfa ≈252 (levemente transparente) e um halo de
  pixels com alfa 1–9; os da Kaguya originais tinham cantos opacos. A janela Tk usava uma única cor-chave
  (`-transparentcolor`), o que gera quadrado/franja escura. Agora a janela usa alfa por pixel e um recorte
  nítido **somente na exibição** (arquivos originais intactos). Ver `assets/previews/transparencia_mascotes.png`.

## P2 — memória e orquestração

- Agentes "esqueciam" o Obsidian → o **Studio** busca no índice e injeta as notas (marcadas como dados,
  não instruções) em toda tarefa.
- Aprendizados/erros não eram registrados → as respostas terminam com `APRENDIZADOS:`/`ERROS:`/
  `REFERÊNCIAS:` e o Studio cria rascunhos na outbox para sua aprovação.
- `DEPOIS:`/`IDEIA:` nunca chegam ao agente em execução (não há como "mudar de assunto").
- Consumo: limite de subagentes, ciclos, paralelismo e tempo; fila pausa após falha ou limite atingido.

## Pendente de validação no seu PC (não verificável aqui)

1. Login real **das suas contas** e uma tarefa real Codex e Claude (botão *Teste real* em Diagnóstico).
2. Leitura de limites do Codex com sua conta (Uso e limites › Atualizar agora).
3. Seu vault real (`D:\Segundo Cerebro` ou outro): indexação, busca e formato real do `tasks/todo.md`.
4. Seus 72 agentes reais: em quais pastas estão (`.claude/agents` do projeto, do vault ou global).
5. Microfone e transcrição local (depende da instalação opcional e da permissão do Windows).
6. Transparência das mascotes na sua área de trabalho e escalas de exibição reais.

# Auditoria do pacote de evolução (25/11/2026) × Kaguya Studio 4.9.0

Base auditada: branch `ccr-a23654da-7hqyv0`, versão **4.9.0** (≈13,6 mil linhas em `kaguya/`, 119 testes automatizados).
O pacote V3.4 do ZIP foi tratado só como histórico; nada abaixo vem dele.

Estados: **validado_no_windows** (CI Windows real) · **validado_em_teste_local** (Linux + CLIs reais/simuladas) ·
**parcial** · **planejado** · **não_verificado** (depende do PC/conta do usuário) · **bloqueado_por_limitação_externa**.

| ID | Requisito | Estado | Evidência (código / teste) | Próximo passo |
|---|---|---|---|---|
| M01 | Projetos e vault vinculados independentes | validado_no_windows | `paths.py`, `store.py`, `ui/dialogs.py` · `test_core_v4`, `test_ui_v4` | — |
| M02 | Codex/Claude por login de assinatura, sem API | validado_no_windows (sem conta) · não_verificado com sua conta no CI | `cli/discovery.py`, `env.py` remove chaves · `test_cli_reais` | — |
| M03 | Equipe: implementa → testa → revisa → corrige | validado_em_teste_local | `orchestrator/engine.py::_run_team` · `test_engine` | — |
| M04 | Paralelo isolado por worktrees | validado_em_teste_local | `orchestrator/worktree.py` · `test_engine` | — |
| M05 | Ler/pesquisar notas existentes | validado_em_teste_local | `vault/index.py` (FTS5 incremental, exclusões sensíveis) | — |
| M06 | Staging e registro de conhecimentos | parcial | `vault/outbox.py` (rascunho fora do vault, aprovação, nunca sobrescreve) | **Etapa D**: frontmatter da spec 08, status/confiança/fonte/versão |
| M07 | Busca incremental e deduplicação | parcial | hash + títulos parecidos em `outbox.py`/`index.py` | **Etapa D**: "propor atualização" de nota existente em vez de duplicar |
| M08 | Validação e reuso entre agentes | parcial | aprendizados extraídos das tarefas → rascunhos; `memory_for` injeta trechos | **Etapa D**: revalidação (notas antigas/obsoletas), divergências |
| M09 | Ler PDF/Office/ZIP/logs/imagens | parcial | as CLIs leem arquivos; não há leitor próprio do Studio | **Etapa D**: Leitor Universal (Office/ZIP seguros, trechos, limites) |
| M10 | Observar janela autorizada | parcial | "Usar o PC": captura só da janela permitida, Parar, failsafe (`desktop/`) · CI real | indicador "Observação ativa" unificado (Etapa D) |
| M11 | Navegador com abas e favoritos | parcial | só ChatGPT/Claude embutidos (`page_webchats.py`) | **Etapa C**: Kaguya Browser |
| M12 | Aba compartilhada com agente | inexistente | — | **Etapa C** |
| M13 | Ação supervisionada, um controlador por aba | inexistente | ("Usar o PC" já controla tela inteira com confirmação) | Etapa C (após M12) |
| M14 | YouTube: metadados/timestamps | inexistente | — | **Etapa C** |
| M15 | YouTube: texto e visual autorizados | inexistente | — | **Etapa C** |
| M16 | Perfis Kaguya/Miwa editáveis | parcial | `persona.py` + Configurações (4.9.0) · `test_persona` | **Etapa A**: editor completo (nome, controles, regras por tarefa, por projeto, exportar/importar) |
| M17 | Voz/sprite/estilo separados | parcial | voz por IA (`voice/neural.py`), sprites por variante, persona separada | Etapa A: voz e visual dentro do editor |
| M18 | Bandeja lateral (lingueta) | inexistente | — | **Etapa B**: Kaguya Music |
| M19 | Player local real | inexistente | — | **Etapa B** (QtMultimedia, já incluso no PySide6) |
| M20 | Sessões de mídia do Windows | inexistente | — | Etapa B: teclas de mídia do Windows (controle); status depende de WinRT (avaliar) |
| M21 | YouTube/Spotify/Amazon | bloqueado_por_limitação_externa (parcial) | — | Etapa B: só controles do próprio Windows; Spotify sem comando por voz (política) |
| M22 | Comandos de música por agentes/playlists | inexistente | — | Etapa B |
| M23 | STT/TTS local | validado_no_windows (carregamento) · não_verificado com seu microfone | `voice/` faster-whisper, Kokoro, SAPI · `--verificar-voz` no CI | — |
| M24 | Comandos durante execução, ducking | parcial | Live/chamar pelo nome não interrompem a fila; barge-in | Etapa B: ducking da música |
| M25 | Inventário real dos 72 agentes | parcial | `inventory.py` + catálogo, página Agentes e skills (documentado × instalado) | invocar agente real com evidência (Etapa A, tarefa de teste) |
| M26 | Skills/plugins/MCP com permissões | parcial | MCP só com permissão; servidor próprio não instala nada | painel de permissões unificado (Etapa A) |
| M27 | Delegação econômica, fila não interruptiva | validado_em_teste_local | DEPOIS/IDEIA/AGORA, `economy.max_subagents`, modelos por papel | URGENTE como sinônimo de AGORA (Etapa A) |
| M28 | Testes, auditoria, logs por tarefa | validado_no_windows | `quality.py`, logs higienizados por tarefa, CI Windows | — |
| M29 | Design system e assets isolados | validado_no_windows | `ui/theme.py`, ícones SVG, sprites individuais, capturas 100–200% | Etapa A: página Início (dashboard) |
| — | Limites só de fonte oficial | validado_no_windows | `usage.py` (app-server Codex, rate_limit_event Claude, "indisponível") | — |
| — | Pausar tudo (agentes, voz, controle) | inexistente | Parar por projeto e Parar do controle existem | **Etapa A** |
| — | Exclusões sensíveis (.env, chaves…) | parcial | índice do vault exclui; tarefas não | **Etapa A**: bloquear leitura pelas CLIs |
| — | Instalador e atualização | validado_em_teste_local (CI em andamento) | `instalador/KaguyaStudio.iss`, passo no CI | — |

## Ordem de execução (pelos gaps reais)

- **Etapa A (5.0)**: editor de personalidade completo, página Início, Pausar tudo, exclusões sensíveis, URGENTE.
- **Etapa B (5.1)**: Kaguya Music — lingueta lateral, player local, teclas de mídia do Windows, ducking, comandos.
- **Etapa C (5.2)**: Kaguya Browser (abas, favoritos, compartilhar aba) + YouTube Intelligence (níveis A/B/C).
- **Etapa D (5.3)**: Leitor Universal + motor de conhecimento (frontmatter, atualização em vez de duplicata, revalidação).

Limitações já conhecidas (não serão simuladas): Spotify proíbe assistentes de voz controlando a plataforma; YouTube
exige player visível (≥ 200×200) e não permite extrair áudio; quotas só quando a ferramenta oficial informa.

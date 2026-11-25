# Changelog

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

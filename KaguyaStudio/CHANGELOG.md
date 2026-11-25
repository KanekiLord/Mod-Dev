# Changelog

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

# Kaguya Extension Hub — relatório (25/11/2026, versão 5.8.0)

Integração sobre o Kaguya Studio atual (5.7.0), sem substituir nada que existia: o inventário antigo
(`kaguya/inventory.py`, página *Agentes e skills*, catálogo dos 72 agentes) continua igual; o Hub é um módulo novo
(`kaguya/hub/`) e uma página nova (**Extensões**).

## Antes × depois

| | Antes (5.7.0) | Depois (5.8.0) |
|---|---|---|
| O que era visto | só **nomes** de agentes, skills, plugins e MCPs | MCPs, plugins (com componentes), skills, agentes (com a hierarquia de pastas), comandos e hooks, de **Claude Code e Codex**, por escopo (usuário / projeto / local / plugin / builtin) e projeto |
| Estado | nenhum | `descoberto → configurado → habilitado → carregado na sessão → conectado → capacidade verificada` + condições (`requer login/aprovação/reinício`, `falha`, `desabilitado`, `só na web`, `removido`…), com **evidência** e data |
| Mudanças | não detectava | observação com *debounce* + revarredura; instalação, remoção, atualização e mudança de versão aparecem sozinhas (aviso na tela) |
| Uso pelas IAs | nenhum | cada IA recebe a lista curta do que ela e a outra têm; pedido que precisa de uma ferramenta vai para quem a tem; `[[DELEGAR:…]]` vira tarefa para a outra IA |
| Instalar/remover | — | plano com o comando **oficial**, revisão de segurança, aprovação explícita, execução, releitura, auditoria |

Inventário **real** deste ambiente de testes (servidor de nuvem, configurações reais do Claude Code 2.1.332 e Codex
0.172), segredos mascarados — depois de registrar um MCP de teste nos dois clientes:

```
claude mcp     user     kaguya-teste            capacidade verificada  env=[API_TOKEN, …] (valores nunca lidos para o catálogo)
claude plugin  builtin  cc-plugin-*@builtin ×5  habilitado (1 desabilitado) — "claude plugin list --json"
claude skill   user     25 skills               habilitado (carregadas pelo cliente)
codex  mcp     user     kaguya-teste            capacidade verificada (handshake MCP, 10 ferramentas listadas)
→ 32 itens; 2ª, 3ª e 4ª sincronização: 0 eventos (sem duplicatas); token de teste ausente do banco do Hub
```
O MCP de teste foi removido dos dois clientes ao final (pelo próprio Hub e pelos comandos oficiais).

## Evidências de integração real (neste ambiente)
- `claude plugin list --json`, `claude plugin details`, `claude mcp get` (status "√ Connected"), `codex mcp list --json`
  (inclui `auth_status`), `codex plugin list --json` — chamados de verdade.
- Ciclo completo nos **dois clientes** pelo Hub: plano → aprovação → `claude mcp add-json` / `codex mcp add` →
  redescoberta → teste → `claude mcp remove` / `codex mcp remove` → item marcado "removido" com histórico.
- Um servidor que não responde foi reportado como **"× Failed to connect"** / "o servidor encerrou" — nunca sucesso falso.
- **Achado importante:** `claude mcp get` e `codex mcp list --json` imprimem os **valores** das variáveis (tokens) em
  texto puro. O Hub guarda só a linha de status / só os nomes das variáveis.
- Proteção oficial respeitada: dentro de uma sessão do Claude Code, ele recusa receber a configuração pela entrada
  padrão ("Run the command outside the session"). O Hub **não contorna**: no Studio (fora de sessão) funciona; se
  recusar, o plano explica.

## Decisões
1. **Origem ≠ execução.** A configuração fica no cliente dono. O Hub nunca copia `config.toml`, `.mcp.json`, credenciais
   ou servidores entre Claude e Codex: a outra IA **pede o trabalho** (delegação pelo orquestrador).
2. **Identidade** = `provedor:tipo:escopo:projeto:plugin/nome` — o mesmo nome em dois projetos são dois itens.
3. **Descoberta só lê.** Arquivos oficiais + listagens oficiais somente-leitura. Nenhum servidor é iniciado na
   varredura (teste de hash: nada muda; teste com `subprocess` bloqueado: nada é executado).
4. **Arquivo meio gravado/inválido** → problema da fonte; os itens dela são **mantidos** (nunca "removidos" por engano).
5. **Verificação** só por meios oficiais: `claude mcp get` (Claude), handshake MCP `initialize + tools/list` (Codex não
   tem teste próprio) — ferramentas **listadas, nunca executadas** — e o evento `init` das **sessões reais** do
   Claude Code que o Studio já abre (prova mais forte, sem custo extra).
6. **Habilidades contextuais**: o prompt recebe só a lista curta de MCPs; skills continuam com cada cliente.
7. **Hooks** são inventariados com o risco ("executa comandos no seu PC"), nunca executados pelo Hub.
8. **Plugins só da web** (ChatGPT/Claude web): registráveis, sempre "só na web", nunca usáveis pela CLI/Studio.
9. **Custos**: serviços pagos (ElevenLabs, OpenAI API…) marcados antes de qualquer uso; conexão existente ≠ consentimento
   para gastar.
10. **Blender/Blockbench**: um escritor por arquivo/aplicativo (lock) e backup do `.blend`/`.bbmodel` antes da tarefa.

## Quando é preciso reabrir uma sessão
- As tarefas do Studio abrem uma sessão nova por turno: mudanças valem **na próxima tarefa**.
- O **Live** mantém sessão aberta: mudança durante o Live marca `requer reinício` até ela fechar.
- Sessões que você abriu fora do Studio (terminal) também precisam ser reabertas — o Hub não as vê.
- Ativar/desativar plugin do Claude Code: vale nas próximas sessões (o próprio comando avisa).
- MCP de projeto (`.mcp.json`) do Claude Code: precisa da sua aprovação **no Claude Code** (o Hub mostra
  `requer aprovação`, não aprova por você).

## Limitações conhecidas
- O Codex não tem comando de teste de MCP; servidores **remotos** (HTTP) do Codex só são confirmados numa sessão real.
- "Carregado na sessão" para o Codex depende de uso real (o Codex não lista as ferramentas ao abrir).
- Conectores da conta web (ChatGPT/Claude) não são descobríveis localmente: registro manual como "só na web".
- Observação de arquivos é por varredura periódica (6 s) com debounce — sem dependência extra.
- Não testado no seu Windows real: seus MCPs de **Blender/Blockbench** e o plugin **ElevenLabs** (o Hub vai detectá-los
  lendo as configurações; os ensaios 1–9 do pacote ficam para você, guiados pela página Extensões).

## Rollback
- Instalação pelo Hub → **Remover…** (o plano mostra o comando oficial de desfazer antes de aprovar).
- Remoção → reinstalar pelo Hub (valores secretos precisam ser digitados de novo: o Hub nunca os guardou).
- Desligar o Hub inteiro: `hub.enabled = false` nas configurações (as tarefas voltam ao comportamento da 5.7.0).
- Os arquivos do Hub ficam em `<dados>/hub/` (catálogo, planos) — apagar a pasta zera o Hub sem tocar nos clientes.

## Checklist de aceitação (04_TESTES) → onde está provado
| Critério | Teste |
|---|---|
| Descoberta não modifica arquivos (hash antes/depois) | `test_hub.Discovery.test_read_only_scopes_states_and_hierarchy` |
| Global × projeto com nomes iguais sem colisão | idem (`aprovado` em dois projetos) |
| Criação/edição/remoção com debounce e fallback | `Sync.test_watcher_debounces…`, `Sync.test_service_poll_picks_up_a_new_skill` |
| Arquivo parcialmente gravado não vale como configuração | `Sync.test_repeat_change_remove_partial_and_restart` |
| Proveniência, escopo, versão, verificação, estado | `Discovery`, `Checks` |
| `descoberto` separado de `carregado/conectado/testado` | `Discovery` (nada ≥ conectado sem prova), `Checks` |
| Sem segredos em JSON/SQLite/logs/UI | `Discovery.test_no_secret_anywhere`, `Checks`, `HubUi` |
| Manifesto malicioso não vira comando | `Discovery.test_injection_in_manifest_is_only_text` |
| Nada instalado/removido sem aprovação específica | `Lifecycle_`, `HubUi` (recusar → nada roda) |
| Sem duplicatas ao sincronizar repetidamente | `Sync` (+ ensaio real: 32 → 0 → 0 → 0) |
| Capacidade some quando a extensão é removida | `Sync` (`usable()` falso, rota deixa de apontar) |
| `requer reinício` com sessão usando config antiga | `Sync` |
| CLI indisponível sem falso sucesso | `Checks` |
| UI com inventário grande e responsiva | página com paginação (400) e trabalho em segundo plano |
| Router delega para quem tem capacidade validada; senão avisa | `Routing`, `EngineIntegration`, `HubUi` |
| Bloqueio de acesso simultâneo a arquivo Blender/Blockbench | `Routing` (lock + backup), `EngineIntegration` |

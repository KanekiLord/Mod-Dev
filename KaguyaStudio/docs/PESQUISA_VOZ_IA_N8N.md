# Pesquisa: IA grátis, IA por voz e n8n (25/11/2026)

Feita por buscas na web. **Não consegui assistir aos vídeos do YouTube nem usar o resumo do Microsoft Edge** (o
ambiente em que trabalho não tem o Edge nem acesso ao player do YouTube); os vídeos citados vêm de páginas que os
listam ou resumem. Dá para pedir isso à Kaguya no modo "Meu computador" no seu PC (abrir o Edge e usar o resumo).

## 1. Criar IA grátis (agentes locais)
- Padrão em quase todos os tutoriais de 2026: **modelo local no Ollama** (Qwen3, Llama 3.x, Mistral Small) +
  um laço que executa ferramentas + uma camada de permissão para controlar navegador/computador.
- Projetos citados: OpenClaw, AnythingLLM, Hermes Agent, n8n + Ollama, Browser-Use.
- Vídeos/resumos em português: "Crie um Agente de IA Local para Resumo de Documentos com Ollama e Llama 3.1 em
  10 Minutos", "O Curso Intensivo MAIS FÁCIL sobre Ollama para IA Local", "Crie o seu primeiro Agente de IA –
  Tutorial completo n8n".
- **Para o Kaguya Studio**: um modelo local no Ollama poderia responder coisas simples sem gastar o limite das
  assinaturas (ex.: confirmar timers, conversa curta). Exige um PC com GPU/RAM boas; a qualidade para código é bem
  menor que a do Codex/Claude. Sugestão: opção futura "IA local para tarefas pequenas", desligada por padrão.

## 2. IA por voz
O que o Studio usa hoje: microfone → detecção de fala por energia → **faster-whisper** local → Codex/Claude pelas
CLIs → **Kokoro** local (voz neural) — tudo grátis e no seu PC.

O que a pesquisa mostrou de útil:
| Ideia | O que é | Vale para nós? |
|---|---|---|
| **Silero VAD** | detector de fala por rede neural (ONNX, pequeno) | **Sim, próximo passo**: menos disparos com TV/ruído, corte de fala mais preciso; já temos onnxruntime |
| **openWakeWord / ViolaWake / livekit-wakeword** | detector de palavra de ativação treinável ("Kaguya", "Miwa") | Sim, depois: gasta bem menos CPU que transcrever tudo; exige treinar os dois nomes (ferramentas locais existem) |
| Parakeet (NVIDIA) | transcrição muito rápida | Foco em inglês; o Whisper continua melhor para pt-BR |
| Moshi (Kyutai), Step-Audio 2 | voz para voz sem etapas (fala e ouve ao mesmo tempo) | Ainda sem pt-BR bom e sem ligação com as assinaturas Codex/Claude |
| Pipecat / Hugging Face speech-to-speech / LocalAI | frameworks de agente de voz | Fazem o que o Studio já faz; trocar traria peso sem ganho claro |
| MOSS-TTS-Nano, VibeVoice, Qwen3-TTS | vozes novas, algumas com clonagem | Testar no futuro como alternativa ao Kokoro (licença e pt-BR a confirmar) |

Serviços pagos (ElevenLabs, OpenAI Realtime, Vapi, Retell, Telnyx) ficaram de fora: cobram por uso.

## 3. n8n
- **O que é**: automação de fluxos por blocos (gatilho → passos → ações), com 400+ integrações (Gmail, Google
  Agenda, Telegram, planilhas…) e nós de agente de IA.
- **Custo/licença**: a edição Community é grátis para instalar no próprio PC/servidor, sem limite de execuções;
  licença "Sustainable Use" (fair-code, não é open source OSI): uso pessoal/interno liberado, revender como serviço não.
- **Como usar**: Docker ou Node.js, roda um servidor local (porta 5678) aberto no navegador; os fluxos são montados
  arrastando blocos; um fluxo pode ser chamado por **webhook** (endereço HTTP).
- **Viável para o Kaguya Studio?** Como núcleo, **não**: o Studio já orquestra Codex/Claude, voz e tela; o agente de IA
  do n8n precisaria de chave de API paga ou de um modelo local (não usa as assinaturas do Codex/Claude), e seria mais
  um servidor rodando no seu PC.
  Como **complemento opcional, sim**: para integrações oficiais que hoje fazemos olhando a tela — por exemplo
  Google Agenda e Gmail por login OAuth do próprio n8n — a Kaguya chamaria um webhook do seu n8n ("criar evento",
  "enviar e-mail") em vez de clicar. WhatsApp pessoal **não** tem API oficial gratuita (a API é do WhatsApp Business),
  então mensagens continuam pelo app na tela, com a sua confirmação.

## Fontes
- https://shop.zimaspace.com/pt/blogs/tech-ai-hub/top-10-open-source-local-ai-agent-projects-to-watch-in-2026
- https://horadecodar.com.br/criar-agente-ia-gratis-n8n-sem-llm-paga/
- https://www.freecodecamp.org/news/build-a-personal-ai-web-research-agent-with-ollama-and-qwen/
- https://developers.redhat.com/articles/2026/07/20/computer-use-how-ai-agents-can-automate-almost-anything
- https://localaimaster.com/blog/build-local-ai-agent
- https://lilys.ai/notes/pt/pdf-summarizer-20251126/ollama-llama-3-1-local-summarizer
- https://lilys.ai/notes/pt/get-your-first-users-20260207/easiest-ollama-local-ai-course
- https://github.com/huggingface/speech-to-speech
- https://github.com/pipecat-ai/pipecat
- https://theaibench.ai/use-cases/voice/
- https://localaimaster.com/blog/local-speech-to-speech-assistant
- https://dev.to/dedupedai/best-open-source-voice-ai-repos-in-2026-private-dictation-local-text-to-speech-and-a-self-hosted-2gi
- https://www.dio.me/es/articles/criando-um-novo-amigo-assistente-virtual
- https://raw.githubusercontent.com/dscripka/openWakeWord/HEAD/README.md
- https://dev.to/buguatec/how-to-get-a-wake-word-model-in-2026-3amo
- https://pypi.org/project/violawake/
- https://docs.livekit.io/agents/multimodality/audio/wakeword/
- https://findstack.com/resources/what-is-n8n
- https://www.activepieces.com/blog/n8n-community-edition-limits-and-features-compared.md
- https://www.ssdnodes.com/learn/is-n8n-free-community-vs-enterprise
- https://support.claude.com/en/articles/11145838 • https://developers.openai.com/codex/pricing

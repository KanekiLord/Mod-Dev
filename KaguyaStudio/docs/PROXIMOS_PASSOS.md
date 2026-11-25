# Próximos passos (registro de 25/11/2026)

## Estado ao encerrar o dia
- Versão no branch: **4.2.0**. CI do Windows da 4.1.1 passou; 4.1.2 (voz dentro do .exe) e 4.2.0 (microfone/fone)
  estavam rodando — conferir o resultado ao retomar.
- Confirmado no PC do usuário: Studio abre, Codex e Claude "Pronto", tarefa real do Claude concluída, limites
  oficiais aparecendo (Codex e Claude), vault vinculado, repositório Git criado no projeto Kodachi.

## Pedidos em aberto do usuário
1. **Modo Live** (como o do ChatGPT/Codex): conversa por voz contínua.
   - Microfone sempre ouvindo com detecção de fala (VAD) → transcrição local (faster-whisper) → IA → voz.
   - Processo do Claude mantido aberto com `--input-format stream-json` (vários turnos sem reiniciar; menor
     latência) e `--include-partial-messages` para começar a falar na primeira frase; Codex via `app-server`.
   - Interromper falando por cima (barge-in; recomendar fone para evitar eco).
   - Tela Live: mascote grande da IA ativa, legenda ao vivo, nível do microfone, trocar IA por voz, encerrar.
   - Somente leitura por padrão; pedidos de alteração viram tarefas na fila.
   - Expectativa honesta: alguns segundos entre parar de falar e ouvir a resposta (não é um modelo de voz nativo).
2. **Vozes mais fluidas, uma por IA**: vozes neurais locais e gratuitas.
   - **Kokoro** (pt-BR: `pf_dora` feminina, `pm_alex`/`pm_santa` masculinas) — candidato principal; ONNX local.
   - Piper: em pt-BR só foi encontrada a voz masculina `faber`.
   - Vozes dos apps oficiais do ChatGPT/Claude **não** são acessíveis sem API paga/endpoints privados.
3. **IAs usando o computador sem o usuário precisar aprovar**: definir com o usuário o que significa
   (a) rodar comandos/testes/builds e editar arquivos sem confirmações (modo autônomo por projeto, com Git e
   limites), ou (b) controlar mouse/teclado/janelas (por exemplo, abrir o Minecraft e testar o mod).
4. Validar com a conta real: publicar no GitHub (login corrigido na 4.1.1), push/pull.

## Fontes consultadas
- Kokoro pt-BR: https://offlinetts.com/voice/pf-dora/ • https://soniqo.audio/pt/guides/kokoro •
  https://huggingface.co/NeuML/kokoro-base-onnx
- Piper pt-BR: https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0/pt

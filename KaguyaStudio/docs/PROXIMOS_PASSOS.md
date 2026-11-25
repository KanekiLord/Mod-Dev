# Próximos passos (registro de 25/11/2026)

## Estado (25/11/2026, 4.6.0)
- Feitos: vozes neurais Kokoro (4.3.0), **Modo Live** (4.4.0), **modo autônomo** (4.5.0) e **Usar o PC**
  (4.6.0) — ver CHANGELOG.
- Medido no ambiente de desenvolvimento (CPU lenta de 4 núcleos, conversa já aquecida): primeiro texto do
  Claude ~2,2 s depois de você parar de falar; primeiro áudio ~6 s (Kokoro aqui roda em tempo real ≈ 1×).
  Num PC comum o áudio deve sair bem antes; conferir no seu computador.
- Ainda não validado no seu computador: microfone/fone reais, Live com suas contas, publicar no GitHub.

## Próximos itens escolhidos pelo usuário
1. ~~Autonomia sem aprovação~~ — feito na 4.5.0.
2. ~~Controle de mouse/teclado~~ — feito na 4.6.0.

## Para validar no seu PC
0. Bandeja: fechar no X e reabrir pelo ícone; "Chamar pelo nome": "Kaguya, …" / "Miwa, …" com e sem fone;
   ChatGPT e Claude embutidos (entrar com e-mail).
1. Live com fone: latência real, interrupção falando por cima, troca de IA por voz.
2. Modo autônomo num projeto com Git: uma tarefa pequena e depois "Desfazer".
3. Usar o PC com o Minecraft aberto: pedir "abra o mundo de teste e veja se o HUD aparece"; testar Parar,
   Ctrl+Alt+End e o canto da tela. O Codex com MCP só foi verificado até a configuração (sem conta aqui).

## Fontes consultadas
- Kokoro pt-BR: https://offlinetts.com/voice/pf-dora/ • https://soniqo.audio/pt/guides/kokoro •
  https://huggingface.co/NeuML/kokoro-base-onnx
- Piper pt-BR: https://huggingface.co/rhasspy/piper-voices/tree/v1.0.0/pt

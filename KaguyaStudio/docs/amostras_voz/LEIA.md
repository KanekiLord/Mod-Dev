# Amostras de voz geradas localmente (Kokoro-82M, sem internet nem API)

Geradas em 25/11/2026 pelo próprio Studio (`VoiceEngines` + normalização pt-BR), num servidor de nuvem de 4 núcleos sem GPU.
- `kaguya_natural.wav` — perfil padrão da Kaguya (Dora + toque japonês), estilo Natural.
- `miwa_natural.wav` — perfil padrão da Miwa (Dora calorosa), estilo Natural.
- `miwa_animada.wav` — Miwa, estilo Animado, velocidade 1,05×.

Qwen3-TTS 0.6B CustomVoice (opcional, instalado só com sua confirmação), mesma máquina, frase "Olá! Eu sou a Kaguya.
Hoje é 25/11/2026 e já terminei a primeira etapa do seu projeto.":
- `qwen3_serena.wav` — voz "serena" do modelo (RTF 3,99).
- `qwen3_vivian.wav` — voz "vivian" do modelo (RTF 4,13).
As vozes do Qwen são nativas de outros idiomas, então o português tem sotaque; o Kokoro é bem mais rápido.

Ouça e compare; no Studio, a página **Vozes** tem o teste cego A/B e o benchmark para medir no seu PC.

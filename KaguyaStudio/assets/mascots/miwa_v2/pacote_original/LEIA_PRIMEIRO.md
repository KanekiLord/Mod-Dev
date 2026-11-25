# Claude Code — Pacote de fala e gestos V1

Este pacote fornece **16 frames PNG** para a mascote feminina Claude Code em pixel art, organizados em 4 ciclos:

- **fala_normal**: boca fechada, abertura leve, aberta e sorriso.
- **explicando**: mão no peito, mão aberta e gesticulação de explicação.
- **pensando_falando**: mão no queixo e gesto de apontar.
- **animada_acenando**: sorriso, piscada e aceno.

## Pastas

- `sprites/128/` — 16 arquivos 128×128 RGBA.
- `sprites/256/` — 16 arquivos 256×256 RGBA.
- `animacoes/` — quatro GIFs em loop e demonstração contínua.
- `originais/` — sprite sheet gerada e nove sprites fornecidos anteriormente.
- `manifest.json` — sequência, nomes e duração por ciclo.
- `VISUALIZADOR.html` — abra em navegador para escolher ciclos e velocidade; sem servidor.

## Integração

Exiba uma imagem por vez em intervalos conforme `manifest.json` (ou 140–220 ms por quadro).
Na ausência de voz, use `fala_normal_01.png` ou um dos sprites neutros originais. Ao receber evento de TTS iniciado, ative ciclo de fala; no final, desative o ciclo. Se houver acesso a intensidade do áudio, ela pode orientar a seleção dos quadros de boca, mas para sincronia com fonemas serão necessários visemas separados.

**Importante:** não contém áudio nem motor de reconhecimento de voz. Não utiliza APIs pagas. Os GIFs são prévias, preferindo PNGs para renderização em aplicativos.

## Limites visuais

O desenho foi gerado numa folha com 4×4 quadros e os crops foram centralizados. Como as poses mudam de mãos e ombros, as animações não têm a precisão de rigging em camadas. A mascote foi preservada em estilo semelhante ao conjunto original, não em pixels idênticos aos sprites anteriores.

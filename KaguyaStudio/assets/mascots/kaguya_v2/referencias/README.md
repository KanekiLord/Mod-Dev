# Kaguya — Mascote Pixel Art V2

Pacote de sprites para integração no Kaguya Studio, produzido a partir da cartela mais recente da Kaguya.

## Arquivos

- `sprites_128/`: 9 expressões em PNG RGBA transparente com **128 × 128 pixels**.
- `sprites_original_418/`: as mesmas expressões em **418 × 418 pixels** extraídos da arte original.
- `kaguya_sprite_sheet_3x3_128.png`: cartela 3 colunas × 3 linhas, **384 × 384 pixels**, fundo transparente.
- `kaguya_sprite_sheet_original_1254.png`: cartela original, **1254 × 1254 pixels**.
- `manifest.json`: nomes, ordem e coordenadas para o aplicativo.

## Expressões e ordem (esquerda→direita; cima→baixo)

1. `kaguya_neutra.png`
2. `kaguya_feliz.png`
3. `kaguya_pensando.png`
4. `kaguya_falando.png`
5. `kaguya_surpresa.png`
6. `kaguya_entediada.png`
7. `kaguya_apaixonada.png`
8. `kaguya_confiante.png`
9. `kaguya_dormindo.png`

## Integração

Exiba as versões 128 × 128 em múltiplos inteiros (2×, 3×, 4×) e use `image-rendering: pixelated` em CSS para preservar as bordas. O centro e o tamanho do quadro são fixos, mas gestos e acessórios variam entre as imagens. As versões de 128 px são reduzidas com `nearest neighbor`, sem suavização.

## Limites do pacote

Este pacote contém **9 imagens estáticas**, não uma animação quadro a quadro. Piscar, fala sincronizada e idle ainda precisam de novos quadros desenhados e alinhados. O desenho original é uma arte gerada por IA; pequenos pixels soltos e contornos podem exigir limpeza manual para produção final.

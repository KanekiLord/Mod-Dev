# Kaguya — Mascote Pixel Art (referência visual + sprites recortados)

Referência fornecida pelo usuário: Kaguya, personagem adulta com cabelos longos prateados, olhos avermelhados/violetas, vestido branco adornado e joias.

## Pacote inicial
- `sprite_sheet_6.png`: 3 colunas x 2 linhas, cada célula 128 x 128 px.
- `sprite_sheet_18.png`: 6 colunas x 3 linhas, cada célula 128 x 128 px.
- `expressoes/kaguya_*.png`: 18 expressões individuais (128 x 128 px, RGBA).
- `animacoes/idle_*.png`, `blink_*.png`, `talk_*.png`: recortes de *referência* de quadros. Alinhar/refinar antes de usar como animação em produção.
- `prancha_referencia.png`: arte conceitual original (não é layout de sprites pronto).

## Ordem do sprite_sheet_6.png
Linha 1: neutra | feliz | pensando
Linha 2: falando | triste | surpresa

## Avisos de qualidade
Os recortes foram extraídos de uma prancha gerada por IA, não desenhados quadro a quadro. O quadriculado cinza-claro de fundo foi removido onde detectado; conferir bordas, possíveis resíduos de fundo e consistência facial/pixel art antes de usar numa versão final. Animacoes não são garantidamente loops sem trepidação.

Recomendado: validar os arquivos individuais visualmente, corrigir pixels e alinhamento em Aseprite/LibreSprite, e exportar via nearest-neighbor sem anti-aliasing. Direção visual de mascote e não reprodução fiel de fotografia.

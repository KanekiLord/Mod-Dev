# Sprites Kaguya — correção da V3.3

Os 18 PNGs de expressões e 10 PNGs de animação já estão em 128×128 pixels e **foram tratados** para retirar resíduos de moldura nos cantos e bordas, preservando o desenho da personagem. Os originais anteriores ao tratamento foram copiados para `originais_backup/`.

Os recortes foram feitos por tratamento de transparência e identificação de fragmentos de moldura. As animações continuam em caráter experimental por diferença de pose entre frames originais; não foi fabricada interpolação. Para restaurar uma imagem original, copie o PNG correspondente da pasta de backup.

---

# Sprites Kaguya — pacote integrado na V3.2

Origem: ZIP `kaguya_pixel_art_sprites.zip` enviado pelo usuário nesta conversa.

- `expressoes/`: 18 imagens 128×128 (nomes `kaguya_*.png`).
- `animacoes/`: `idle_01..04`, `blink_01..03`, `talk_01..03` (128×128).
- `referencias/`: sprite sheets, a prancha original e as instruções do pacote enviado.

Os sprites aparecem na janela do Studio e na mascote flutuante. Para experimentar as expressões: clique direito em cima da Kaguya → `Prévia das 18 expressões`.

Os quadros de animação ficam desligados por padrão por problemas visuais nos recortes. Para testá-los, clique direito → `Animações de teste`. A animação de idle/piscar se aplica ao estado neutro, e a de fala ao estado falando. Outras expressões permanecem estáticas, para não apagar a emoção desejada.

**Transparência:** parte dos PNGs ainda contém pixels opacos do fundo nos cantos. Para obter uma silhueta realmente transparente na área de trabalho Windows, limpe os fundos manualmente mantendo o canal alfa; não aplique anti-aliasing e não mude o canvas 128×128. Os arquivos fornecidos foram mantidos sem alterações.

Não há sincronização labial avançada; os frames de `talk` só fornecem animação ilustrativa. O sistema de voz Live continua fora do MVP.

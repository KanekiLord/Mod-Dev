import unittest
from pathlib import Path
try:
    from PIL import Image
except ImportError:
    Image=None  # Pillow is optional; installed sprites already cleaned

ROOT=Path(__file__).resolve().parents[1]
SPRITES=ROOT.parent/'assets'/'mascots'/'kaguya'
@unittest.skipIf(Image is None, "Pillow optional necessário apenas para testes de imagem")
class SpriteRepairTests(unittest.TestCase):
    def test_every_expression_has_real_transparent_corners(self):
        paths=list((SPRITES/'expressoes').glob('kaguya_*.png'))
        self.assertEqual(len(paths),18)
        for path in paths:
            with self.subTest(sprite=path.name):
                im=Image.open(path).convert('RGBA')
                self.assertEqual(im.size,(128,128))
                for xy in ((0,0),(127,0),(0,127),(127,127)):
                    self.assertEqual(im.getpixel(xy)[3],0)
    def test_animation_top_border_is_transparent(self):
        paths=list((SPRITES/'animacoes').glob('*.png'))
        self.assertEqual(len(paths),10)
        for path in paths:
            with self.subTest(sprite=path.name):
                im=Image.open(path).convert('RGBA')
                self.assertEqual(im.size,(128,128))
                self.assertEqual(im.getpixel((0,0))[3],0)
                self.assertEqual(im.getpixel((127,0))[3],0)
                self.assertGreater(im.getpixel((64,70))[3],0)
    def test_originals_are_preserved_in_backup(self):
        p=SPRITES/'originais_backup'/'expressoes'/'kaguya_neutra.png'
        self.assertTrue(p.is_file())
        with Image.open(p) as im:
            self.assertEqual(im.size,(128,128))
if __name__=='__main__':unittest.main()

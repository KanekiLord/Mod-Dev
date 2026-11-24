"""Contracts for the user's supplied 18-expression sprite pack (RED before implementation)."""
from pathlib import Path
from tempfile import TemporaryDirectory
import unittest
from mascote import MascotSettings, sprite_path, animation_sprite, ALLOWED, expression_names, label_for_state

class UploadedSpriteTests(unittest.TestCase):
    def test_all_18_uploaded_expressions_supported(self):
        names={'neutra','feliz','sorriso_sutil','falando','surpresa','curiosa',
               'pensando','confiante','provocante','apaixonada','emburrada','triste',
               'envergonhada','preocupada','cansada','chorando','determinada','rindo'}
        self.assertTrue(names.issubset(ALLOWED))
        self.assertEqual(set(expression_names()),names)
    def test_animation_can_be_turned_off_and_happy_stays_happy(self):
        with TemporaryDirectory() as d:
            base=Path(d);(base/'expressoes').mkdir();(base/'animacoes').mkdir()
            happy=base/'expressoes'/'kaguya_feliz.png';happy.write_bytes(b'png')
            neutral=base/'expressoes'/'kaguya_neutra.png';neutral.write_bytes(b'png')
            idle=base/'animacoes'/'idle_01.png';idle.write_bytes(b'png')
            self.assertEqual(animation_sprite(base,'feliz',0),happy)
            self.assertEqual(animation_sprite(base,'neutra',0,animations=False),neutral)
            self.assertEqual(animation_sprite(base,'neutra',0,animations=True),idle)
    def test_preferences_allow_animation_toggle_persistently(self):
        with TemporaryDirectory() as d:
            p=Path(d)/'settings.json'
            a=MascotSettings.load(p)
            self.assertFalse(a.animations)
            a.animations=True;a.save(p)
            self.assertTrue(MascotSettings.load(p).animations)
    def test_all_states_can_have_a_caption(self):
        for state in ALLOWED:
            self.assertTrue(label_for_state(state))

if __name__=='__main__':unittest.main()

"""Condições de contrato da mascote, antes de implementar (RED)."""
import json
import tempfile
import unittest
from pathlib import Path
from mascote import MascotSettings, state_for_status, sprite_path, animation_sprite, safe_location

class MascotTests(unittest.TestCase):
    def test_settings_roundtrip_and_corrupt_file(self):
        with tempfile.TemporaryDirectory() as d:
            p=Path(d)/'mascote.json'
            initial=MascotSettings.load(p)
            self.assertTrue(initial.visible)
            initial.x=77;initial.y=99;initial.topmost=False;initial.scale=3
            initial.save(p)
            current=MascotSettings.load(p)
            self.assertEqual((current.x,current.y,current.topmost,current.scale),(77,99,False,3))
            p.write_text('{broken',encoding='utf-8')
            self.assertTrue(MascotSettings.load(p).visible)
    def test_status_mapping(self):
        self.assertEqual(state_for_status('Executando #4 — codex'),'trabalhando')
        self.assertEqual(state_for_status('Erro na tarefa #4'),'preocupada')
        self.assertEqual(state_for_status('Execução interrompida'),'preocupada')
        self.assertEqual(state_for_status('#4 executado — ainda requer validação'),'feliz')
        self.assertEqual(state_for_status('Pronto • sem tarefas'),'neutra')
    def test_sprite_path_requires_png_and_prioritizes_specific_state(self):
        with tempfile.TemporaryDirectory() as d:
            base=Path(d);(base/'expressoes').mkdir()
            neutral=base/'expressoes'/'kaguya_neutra.png'
            happy=base/'expressoes'/'kaguya_feliz.png'
            neutral.write_bytes(b'x');happy.write_bytes(b'y')
            self.assertEqual(sprite_path(base,'feliz'),happy)
            self.assertEqual(sprite_path(base,'trabalhando'),neutral)
            self.assertIsNone(sprite_path(base,'../x'))
    def test_optional_animation_frames_override_only_when_present(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d);(root/'animacoes').mkdir();(root/'expressoes').mkdir()
            still=root/'expressoes'/'kaguya_neutra.png';still.write_bytes(b'static')
            frame=root/'animacoes'/'idle_01.png';frame.write_bytes(b'frame')
            self.assertEqual(animation_sprite(root,'neutra',0),frame)
            self.assertEqual(animation_sprite(root,'neutra',6),still)
            self.assertEqual(animation_sprite(root,'preocupada',0),still)

    def test_location_stays_on_screen(self):
        self.assertEqual(safe_location(-100,-20,1920,1080,180,220),(0,0))
        self.assertEqual(safe_location(2500,1400,1920,1080,180,220),(1740,860))

if __name__=='__main__':unittest.main()

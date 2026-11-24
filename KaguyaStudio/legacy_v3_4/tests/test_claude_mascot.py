"""Contrato TDD para integrar a mascote de Claude sem substituir Kaguya."""
import tempfile
import unittest
from pathlib import Path
from mascote import sprite_path, label_for_state, expression_names, animation_sprite, MascotSettings, state_for_agent_status

ROOT=Path(__file__).resolve().parents[1]
CLAUDE=ROOT.parent/'assets'/'mascots'/'claude'
KAGUYA=ROOT.parent/'assets'/'mascots'/'kaguya'

class ClaudeMascotTests(unittest.TestCase):
    def test_preserves_kaguya_and_loads_all_nine_claude_expressions(self):
        self.assertEqual(len(expression_names('claude')),9)
        self.assertEqual(len(expression_names()),18)
        for state in ('neutra','feliz','pensando','falando','surpresa','piscando','focada','sucesso','cafe'):
            path=sprite_path(CLAUDE,state,'claude')
            self.assertIsNotNone(path,state)
            self.assertEqual(path.name,f'claude_feminina_{state}.png')
        self.assertEqual(sprite_path(KAGUYA,'neutra').name,'kaguya_neutra.png')

    def test_claude_state_fallback_and_menus(self):
        self.assertEqual(sprite_path(CLAUDE,'trabalhando','claude').name,'claude_feminina_focada.png')
        self.assertEqual(sprite_path(CLAUDE,'preocupada','claude').name,'claude_feminina_surpresa.png')
        self.assertIsNone(sprite_path(CLAUDE,'../../secrets','claude'))
        self.assertEqual(animation_sprite(CLAUDE,'trabalhando',4,True,'claude').name,'claude_feminina_focada.png')
        self.assertIn('Claude',label_for_state('trabalhando','claude'))

    def test_independent_preferences_and_agent_status(self):
        with tempfile.TemporaryDirectory() as d:
            root=Path(d)
            p1=root/'kaguya.json';p2=root/'claude.json'
            a=MascotSettings.load(p1);b=MascotSettings.load(p2)
            a.x=45; b.x=230; b.visible=False
            a.save(p1);b.save(p2)
            self.assertEqual(MascotSettings.load(p1).x,45)
            self.assertEqual(MascotSettings.load(p2).x,230)
            self.assertTrue(MascotSettings.load(p1).visible)
            self.assertFalse(MascotSettings.load(p2).visible)
        self.assertEqual(state_for_agent_status('claude','running'),'focada')
        self.assertEqual(state_for_agent_status('claude','success'),'sucesso')
        self.assertEqual(state_for_agent_status('codex','running'),'determinada')
        self.assertEqual(state_for_agent_status('codex','error'),'preocupada')

if __name__=='__main__':unittest.main()

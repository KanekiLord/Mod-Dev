"""UI integration contracts: both mascots in dock and on desktop."""
import os
import unittest

@unittest.skipIf(os.name!='nt' and not os.environ.get('DISPLAY'), 'Requires Windows/X11')
class DualMascotUITests(unittest.TestCase):
    def test_both_mascots_independent_in_studio_and_on_desktop(self):
        from studio import Studio
        app=Studio()
        try:
            app.update()
            self.assertEqual(app.mascot.mascot_id,'kaguya')
            self.assertEqual(app.claude_mascot.mascot_id,'claude')
            self.assertTrue(app.codex_canvas.winfo_exists())
            self.assertTrue(app.claude_canvas.winfo_exists())
            self.assertNotEqual(app.mascot.pref_path,app.claude_mascot.pref_path)
            app.claude_mascot.show()
            app.update()
            self.assertTrue(app.claude_mascot.window.winfo_exists())
            self.assertTrue(app.mascot.window.winfo_exists())
            app.claude_mascot.open_quick_chat()
            self.assertEqual(app.claude_mascot.quick_target.get(),'Claude')
            app.claude_mascot.set_state('focada')
            self.assertEqual(app.claude_mascot.state,'focada')
            self.assertEqual(app.mascot.state,'neutra')
        finally:
            app.destroy()

if __name__=='__main__': unittest.main()

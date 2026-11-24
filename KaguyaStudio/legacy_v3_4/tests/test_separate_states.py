import os
import unittest

@unittest.skipIf(os.name!='nt' and not os.environ.get('DISPLAY'), 'Desktop necessário')
class AgentStatusTests(unittest.TestCase):
    def test_codex_state_does_not_change_claude_and_vice_versa(self):
        from studio import Studio
        app=Studio()
        try:
            app.mascot.set_state('neutra')
            app.claude_mascot.set_state('neutra')
            app.events.put(('agent_state',('codex','running')))
            app._poll()
            self.assertEqual(app.mascot.state,'determinada')
            self.assertEqual(app.claude_mascot.state,'neutra')
            app.events.put(('agent_state',('claude','running')))
            app._poll()
            self.assertEqual(app.mascot.state,'determinada')
            self.assertEqual(app.claude_mascot.state,'focada')
        finally:
            app.destroy()

if __name__=='__main__':unittest.main()

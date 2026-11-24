import sys
import tempfile
import unittest
from pathlib import Path
from runtime import run_process, run_quality, check_project_writable

class RuntimeTests(unittest.TestCase):
    def setUp(self):
        self.tmp=tempfile.TemporaryDirectory();self.addCleanup(self.tmp.cleanup)
        self.path=Path(self.tmp.name)

    def test_stream_logs_and_returns_status(self):
        lines=[]
        code, output=run_process([sys.executable,'-c','print("mensagem 1");print("mensagem 2")'],self.path,'',lines.append,self.path/'log.txt')
        self.assertEqual(code,0)
        self.assertIn('mensagem 1',output)
        self.assertTrue((self.path/'log.txt').exists())
        self.assertTrue(any('mensagem 2' in s for s in lines))

    def test_quality_reports_unavailable_git(self):
        items=run_quality(self.path, run_tests=False)
        self.assertTrue(items)
        self.assertIn('status',items[0])

    def test_write_needs_git_repo(self):
        with self.assertRaises(ValueError):check_project_writable(self.path)

if __name__=='__main__':unittest.main()

class CommandInjectionRegression(unittest.TestCase):
    def test_claude_receives_user_prompt_only_via_stdin(self):
        from unittest.mock import patch
        from runtime import run_cli
        import tempfile
        malicious='mensagem com & | %% ^ caracteres especiais do cmd.exe'
        with tempfile.TemporaryDirectory() as root:
            with patch('runtime._resolved',side_effect=lambda x:x), patch('runtime.run_process',return_value=(0,'ok')) as run:
                run_cli('claude',Path(root),malicious,False,False,lambda _:None,Path(root)/'log',verify_login=False)
                self.assertNotIn(malicious,' '.join(run.call_args.args[0]))
                self.assertIn(malicious,run.call_args.args[2])

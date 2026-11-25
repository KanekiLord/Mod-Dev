"""Limits: compatibility with old/new Codex app-server params, rollout fallback, Claude payload."""
import json
from pathlib import Path
import sys
import tempfile
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kaguya import usage  # noqa: E402


class FakeClient:
    """Mimics an OLD Codex app-server: methods take *unit* params (a map is rejected)."""
    def __init__(self, old=True):
        self.old, self.calls = old, []

    def request(self, method, params=None):
        self.calls.append((method, params))
        if self.old and params is not None:
            return {"error": {"message": "Invalid request: invalid type: map, expected unit"}}
        if not self.old and method == "account/read" and params is None:
            return {"error": {"message": "Invalid request: missing field `params`"}}
        if method == "account/read":
            return {"result": {"account": {"type": "chatgpt", "planType": "plus"}}}
        return {"result": {"rate_limits": {"primary": {"used_percent": 31, "window_minutes": 300, "resets_in_seconds": 3600}}}}


class Limits(unittest.TestCase):
    def test_old_codex_unit_params_retry(self):
        c = FakeClient(old=True)
        r = usage._request_compat(c, "account/read", {"refreshToken": False})
        self.assertIn("result", r)
        self.assertEqual(c.calls, [("account/read", {"refreshToken": False}), ("account/read", None)])
        r = usage._request_compat(c, "account/rateLimits/read", None)
        snap = usage.codex_snapshot_from_response(r["result"])
        self.assertEqual(snap.windows[0].name, "Janela de 5 horas")
        self.assertEqual(snap.windows[0].remaining_percent, 69)
        self.assertGreater(snap.windows[0].resets_at, time.time())

    def test_new_codex_requires_params_for_account_read(self):
        c = FakeClient(old=False)
        self.assertIn("result", usage._request_compat(c, "account/read", {"refreshToken": False}))
        self.assertEqual(len(c.calls), 1)

    def test_rollout_fallback(self):
        with tempfile.TemporaryDirectory() as tmp:
            d = Path(tmp) / "sessions" / "2026" / "11" / "25"
            d.mkdir(parents=True)
            line = {"timestamp": "2026-11-25T10:00:00.000Z", "type": "event_msg",
                    "payload": {"type": "token_count", "info": {},
                                "rate_limits": {"primary": {"used_percent": 42.0, "window_minutes": 300, "resets_at": 1795600000},
                                                "secondary": {"used_percent": 12.5, "window_minutes": 10080, "resets_at": 1796000000}}}}
            (d / "rollout-2026-11-25T10-00-00-x.jsonl").write_text('{"type":"session_meta"}\n' + json.dumps(line) + "\n",
                                                                   encoding="utf-8")
            snap = usage.read_codex_rollout_limits(Path(tmp))
            self.assertTrue(snap.available)
            self.assertEqual([w.name for w in snap.windows], ["Janela de 5 horas", "Semanal (7 dias)"])
            self.assertEqual(snap.windows[1].used_percent, 12.5)
            empty = usage.read_codex_rollout_limits(Path(tmp) / "nada")
            self.assertFalse(empty.available)

    def test_claude_payload_from_real_event_shape(self):
        info = {"status": "allowed", "resetsAt": 1795580400, "rateLimitType": "five_hour",
                "unifiedWindows": {"five_hour": {"utilization": 0.69, "resetsAt": 1795580400, "status": "allowed"},
                                   "seven_day": {"utilization": 0.1, "resetsAt": 1795867200, "status": "allowed"}}}
        p = usage.claude_payload(info)
        self.assertEqual(p["windows"]["five_hour"]["used_percent"], 69.0)
        self.assertEqual(p["windows"]["seven_day"]["used_percent"], 10.0)
        snap = usage.claude_snapshot({"payload": p, "captured_at": "2026-11-25T00:00:00+00:00", "source": "x"})
        self.assertTrue(snap.available)
        self.assertEqual(round(snap.windows[0].remaining_percent), 31)


if __name__ == "__main__":
    unittest.main()

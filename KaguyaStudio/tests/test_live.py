"""Live mode without hardware: synthetic audio drives the real VAD, the persistent conversation
runs against the fake Claude CLI speaking stream-json, and speech output is captured."""
import os
from pathlib import Path
import shutil
import sys
import tempfile
import threading
import time
import unittest

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kaguya.live.conversation import ClaudeConversation  # noqa: E402
from kaguya.live.session import LiveSession, command_of  # noqa: E402
from kaguya.live.vad import EnergyVAD, RATE  # noqa: E402
from tests.helpers import fake_env, make_fake_clis  # noqa: E402


def speechlike(seconds, amp=0.2):
    t = np.arange(int(RATE * seconds)) / RATE
    return (amp * np.sin(2 * np.pi * 180 * t) * (0.6 + 0.4 * np.sin(2 * np.pi * 3 * t))).astype("float32")


def noise(seconds, amp=0.003, seed=1):
    return (np.random.default_rng(seed).standard_normal(int(RATE * seconds)) * amp).astype("float32")


def frames(audio, ms=30):
    n = int(RATE * ms / 1000)
    return [audio[i:i + n] for i in range(0, len(audio) - n + 1, n)]


class VAD(unittest.TestCase):
    def test_one_utterance_with_preroll(self):
        v = EnergyVAD()
        events = []
        for f in frames(np.concatenate([noise(1.0), speechlike(1.2), noise(1.2, seed=2)])):
            events += v.feed(f)
        kinds = [k for k, _ in events]
        self.assertEqual(kinds, ["start", "end"])
        dur = len(events[1][1]) / RATE
        self.assertTrue(1.3 < dur < 2.4, dur)

    def test_background_noise_is_ignored(self):
        v = EnergyVAD()
        self.assertEqual(sum((v.feed(f) for f in frames(noise(3.0, amp=0.006))), []), [])

    def test_assistant_voice_needs_louder_speech(self):
        v = EnergyVAD()
        for f in frames(noise(1.0)):
            v.feed(f)
        v.assistant_talking = True
        quiet = sum((v.feed(f) for f in frames(speechlike(0.6, amp=0.02))), [])
        self.assertEqual(quiet, [])


class Commands(unittest.TestCase):
    def test_spoken_commands(self):
        self.assertEqual(command_of("Falar com a Claude"), ("switch", "claude"))
        self.assertEqual(command_of("fala com a Kaguya"), ("switch", "codex"))
        self.assertEqual(command_of("Encerrar."), ("end", ""))
        self.assertEqual(command_of("silêncio"), ("silence", ""))
        self.assertEqual(command_of("como está o mod?"), ("", ""))


@unittest.skipUnless(shutil.which("git") or True, "")
class SessionBase(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.bin = Path(self.tmp.name) / "bin"
        self.exe = make_fake_clis(self.bin)
        self.env = fake_env(self.bin)
        self.said, self.events, self.tasks, self.limits = [], [], [], []
        self.stopped = threading.Event()
        self.busy = False
        self.texts = ["implemente o HUD de chakra", "e o que mais?"]

        self.convs = []
        # order matters on Windows: stop the session first, then close its processes, then delete the folder
        self.addCleanup(lambda: [c.close() for c in self.convs])

        def make(agent):
            c = ClaudeConversation(self.exe["claude"], Path(self.tmp.name), env=self.env, on_rate_limit=self.limits.append)
            self.convs.append(c)
            return c
        self.s = LiveSession(agent="claude", make_conversation=make, transcribe=lambda a: self.texts.pop(0),
                             say=lambda text, agent: self.said.append((agent, text)) or True,
                             stop_speech=self.stopped.set, speech_busy=lambda: self.busy,
                             on_event=self.events.append, on_task=lambda t, a: self.tasks.append((a, t)))
        self.s.start(with_microphone=False)
        self.addCleanup(self.s.stop)

    def wait(self, cond, timeout=20):
        end = time.time() + timeout
        while time.time() < end:
            if cond():
                return True
            time.sleep(0.05)
        return False

    def speak_into_mic(self):
        for f in frames(np.concatenate([noise(0.6), speechlike(1.0), noise(1.0, seed=3)])):
            self.s.feed(f)



class Session(SessionBase):
    def test_turns_keep_context_speak_sentences_and_queue_tasks(self):
        self.speak_into_mic()
        self.assertTrue(self.wait(lambda: self.tasks), self.events[-5:])
        self.assertEqual(self.tasks, [("claude", "implemente o HUD de chakra")])
        spoken = " ".join(t for _, t in self.said)
        self.assertNotIn("[[", spoken)
        self.assertIn("Já são 1 mensagens", spoken)
        self.assertGreaterEqual(len(self.said), 2)  # spoken sentence by sentence
        self.speak_into_mic()
        self.assertTrue(self.wait(lambda: "Já são 2 mensagens" in " ".join(t for _, t in self.said)))
        self.assertTrue(self.limits)  # official limits captured during Live
        states = [e["state"] for e in self.events if e["type"] == "state"]
        for st in ("hearing", "transcribing", "thinking", "speaking"):
            self.assertIn(st, states)

    def test_barge_in_stops_voice(self):
        self.busy = True
        self.speak_into_mic()
        self.assertTrue(self.stopped.is_set())
        self.assertTrue(any(e["type"] == "barge_in" for e in self.events))


class WakeByName(SessionBase):
    """Background listener: only a name wakes an assistant; nothing reaches the AI before that."""

    def setUp(self):
        super().setUp()
        self.s.stop()
        self.texts = ["que dia lindo hoje", "Miwa, implemente o HUD de chakra", "e o que mais?",
                      "conversa da sala sem nome", "Kaguya"]
        self.made = []

        def make(agent):
            self.made.append(agent)
            c = ClaudeConversation(self.exe["claude"], Path(self.tmp.name), env=self.env)
            self.addCleanup(c.close)
            return c
        self.events.clear()
        self.s = LiveSession(agent="codex", make_conversation=make, transcribe=lambda a: self.texts.pop(0),
                             say=lambda text, agent: self.said.append((agent, text)) or True,
                             stop_speech=self.stopped.set, speech_busy=lambda: False,
                             on_event=self.events.append, on_task=lambda t, a: self.tasks.append((a, t)),
                             wake=True, follow_up_s=30)
        self.s.start(with_microphone=False)
        self.addCleanup(self.s.stop)

    def test_name_wakes_follow_up_then_sleeps(self):
        self.speak_into_mic()  # "que dia lindo hoje" → ignored
        self.assertTrue(self.wait(lambda: any(e["type"] == "ignored" for e in self.events)))
        self.assertFalse([e for e in self.events if e["type"] == "caption"])
        self.speak_into_mic()  # "Miwa, implemente…" → Claude wakes up, answers, task queued
        self.assertTrue(self.wait(lambda: self.tasks), self.events[-6:])
        called = [e for e in self.events if e["type"] == "called"]
        self.assertEqual(called[0]["agent"], "claude")
        self.assertEqual(self.tasks[0][0], "claude")
        self.assertTrue(all(a == "claude" for a, _ in self.said))
        n = len(self.said)
        self.speak_into_mic()  # follow-up without the name still goes to Miwa
        self.assertTrue(self.wait(lambda: len(self.said) > n and "Já são 2 mensagens" in " ".join(t for _, t in self.said)))
        self.s._awake_until = 0  # follow-up window over
        before = len([e for e in self.events if e["type"] == "caption"])
        self.speak_into_mic()  # no name → ignored again
        self.assertTrue(self.wait(lambda: sum(e["type"] == "ignored" for e in self.events) >= 2))
        self.assertEqual(before, len([e for e in self.events if e["type"] == "caption"]))
        self.speak_into_mic()  # just "Kaguya" → greeting from Kaguya, waiting for the request
        self.assertTrue(self.wait(lambda: self.said[-1][0] == "codex"))
        self.assertIn("Pode falar", self.said[-1][1])


class NameDetection(unittest.TestCase):
    def test_names_and_typed_messages(self):
        from kaguya.live.wake import detect_name
        from kaguya.messages import classify_message
        self.assertEqual(detect_name("Kaguya, poderia olhar isso para mim?"), ("codex", "poderia olhar isso para mim?"))
        self.assertEqual(detect_name("Ei Miwa, vê isso pra mim")[0], "claude")
        self.assertEqual(detect_name("Miwa (Claude Code) poderia ver isso")[1], "poderia ver isso")
        self.assertEqual(detect_name("kaguia olha o log")[0], "codex")  # common Whisper spelling
        self.assertIsNone(detect_name("a Kaguya disse que sim")[0])   # mentioned, not called
        self.assertEqual(classify_message("Miwa, revise o PR", "equipe").target, "claude")
        self.assertEqual(classify_message("Kaguya (Codex) poderia olhar isso", "claude").target, "codex")
        self.assertEqual(classify_message("@equipe: Kaguya implementa", "codex").target, "equipe")


if __name__ == "__main__":
    unittest.main()

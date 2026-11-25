import os
from pathlib import Path
import sys
import threading
import time
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kaguya.voice.speech import SpeechQueue, split_sentences  # noqa: E402
from kaguya.voice import neural  # noqa: E402


class Sentences(unittest.TestCase):
    def test_streaming_deltas_become_sentences(self):
        buf, said = "", []
        for delta in ["Oi! Eu", " sou a Kaguya. Terminei a", " revisão das missões. Encontrei", " dois erros"]:
            buf += delta
            out, buf = split_sentences(buf)
            said += out
        out, buf = split_sentences(buf, final=True)
        said += out
        self.assertEqual(said, ["Oi! Eu sou a Kaguya.", "Terminei a revisão das missões.", "Encontrei dois erros"])
        self.assertEqual(buf, "")

    def test_numbers_and_short_fragments(self):
        out, rest = split_sentences("Versão 1.20.1 do Forge. Ok. Agora vou compilar o projeto inteiro. ")
        self.assertEqual(out, ["Versão 1.20.1 do Forge.", "Ok. Agora vou compilar o projeto inteiro."])


class Chunks(unittest.TestCase):
    def test_long_sentence_is_cut_at_comma(self):
        long = ("Os principais são sobrevivência, com coleta de recursos e perigos, criativo, com recursos infinitos e voo, "
                "aventura, para jogar mapas feitos por outros.")
        out, _ = split_sentences(long + " ", final=True)
        self.assertGreater(len(out), 1)
        self.assertTrue(all(len(x) <= 110 for x in out))
        self.assertEqual(" ".join(out), long)

    def test_first_piece_of_a_reply_is_short(self):
        out, _ = split_sentences("O Gradle é uma ferramenta que automatiza a build de projetos, ou seja, compila. ",
                                 first_max=55)
        self.assertLessEqual(len(out[0]), 62)


class Queue(unittest.TestCase):
    def test_pipeline_order_and_barge_in(self):
        played, states = [], []
        synth = lambda text, voice: (time.sleep(0.05), ([0.0] * 10, 24000))[1]

        def play(audio, sr, stop):
            for _ in range(20):
                if stop.is_set():
                    played.append("interrompida")
                    return
                time.sleep(0.01)
            played.append("ok")
        q = SpeechQueue(synth, play, lambda s, v: states.append(s))
        for t in ("Primeira frase completa.", "Segunda frase completa.", "Terceira frase completa."):
            q.say(t, "kaguya")
        time.sleep(0.12)
        q.stop()
        time.sleep(0.4)
        self.assertIn("interrompida", played)
        self.assertLess(len([p for p in played if p == "ok"]), 3)
        self.assertEqual(states[0], "speaking")
        self.assertEqual(states[-1], "idle")
        q.say("Depois da interrupção ela volta a falar.", "kaguya")
        time.sleep(0.5)
        self.assertEqual(played[-1], "ok")


@unittest.skipUnless(os.environ.get("KAGUYA_TEST_KOKORO_DIR") and neural.package_available(), "modelo Kokoro local")
class RealKokoro(unittest.TestCase):
    def test_presets_synthesise_ptbr(self):
        v = neural.NeuralVoices(Path(os.environ["KAGUYA_TEST_KOKORO_DIR"]))
        self.assertTrue(v.installed())
        for pid in ("kaguya", "claude", "alex"):
            audio, sr = v.synth("Olá, tudo bem?", pid)
            self.assertEqual(sr, neural.SAMPLE_RATE)
            self.assertGreater(len(audio) / sr, 0.5)


if __name__ == "__main__":
    unittest.main()

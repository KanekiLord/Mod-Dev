import sys
from pathlib import Path
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from kaguya.voice import devices as dv  # noqa: E402

RAW = [  # same physical devices repeated per host API, as PortAudio reports on Windows
    {"name": "Microfone (Headset HyperX)", "hostapi": 0, "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 44100},
    {"name": "Fones de ouvido (Headset HyperX)", "hostapi": 0, "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 48000},
    {"name": "Alto-falantes (Realtek)", "hostapi": 0, "max_input_channels": 0, "max_output_channels": 2, "default_samplerate": 48000},
    {"name": "Microfone (Headset HyperX)", "hostapi": 2, "max_input_channels": 1, "max_output_channels": 0, "default_samplerate": 48000},
]


class Devices(unittest.TestCase):
    def test_parse_dedupes_and_marks_defaults(self):
        ins, outs = dv.parse(RAW, 0, 0, 2)
        self.assertEqual([d.name for d in ins], ["Microfone (Headset HyperX)"])
        self.assertEqual([d.name for d in outs], ["Fones de ouvido (Headset HyperX)", "Alto-falantes (Realtek)"])
        self.assertTrue(ins[0].default and outs[1].default)

    def test_choice_by_name_survives_index_change(self):
        ins, outs = dv.parse(RAW, 0, 0, 2)
        self.assertEqual(dv.resolve("Fones de ouvido (Headset HyperX)", outs).index, 1)
        shifted, outs2 = dv.parse([RAW[2], RAW[1]], 0, None, 0)
        self.assertEqual(dv.resolve("Fones de ouvido (Headset HyperX)", outs2).index, 1)
        self.assertIsNone(dv.resolve("Fone que não existe", outs2))
        self.assertIsNone(dv.resolve(None, outs2))

    def test_plug_unplug_detection(self):
        _, before = dv.parse(RAW, 0, 0, 2)
        _, after = dv.parse([RAW[0], RAW[2]], 0, 0, 1)
        ch = dv.diff(before, after, "saída")
        self.assertEqual(ch.removed, ["Fones de ouvido (Headset HyperX)"])
        self.assertIsNone(dv.diff(after, after, "saída"))

    @unittest.skipUnless(dv.available(), "numpy/sounddevice")
    def test_resample_to_16k(self):
        import numpy as np
        out = dv.resample(np.zeros(48000, dtype="float32"), 48000, 16000)
        self.assertEqual(len(out), 16000)


if __name__ == "__main__":
    unittest.main()

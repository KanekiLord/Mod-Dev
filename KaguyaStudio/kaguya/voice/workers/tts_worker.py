"""Isolated TTS worker: runs inside the engine's own Python environment (never inside the Studio).

Protocol (one JSON object per line):
  start   → {"ready": true, "engine", "model", "speakers": [...], "languages": [...], "load_s"}
  request ← {"id", "text", "speaker", "language", "instruct", "out"}       (out = .wav path to write)
  reply   → {"id", "ok": true, "sr", "audio_s", "gen_s"}  or  {"id", "ok": false, "error"}
Standalone on purpose: no Studio imports, so heavy libraries (PyTorch…) stay out of the Studio process.
"""
import json
import os
import sys
import time
import wave

_PROTO = None


def _protect_stdout():
    """The protocol gets a private copy of the real stdout; fd 1 is pointed at stderr so that anything the heavy
    libraries print (progress bars, blank lines, warnings) can never corrupt the channel. Only when run as a script."""
    global _PROTO
    _PROTO = os.fdopen(os.dup(1), "w", encoding="utf-8", buffering=1)
    os.dup2(2, 1)
    sys.stdout = sys.stderr


def emit(obj):
    _PROTO.write(json.dumps(obj, ensure_ascii=False) + "\n")
    _PROTO.flush()


def write_wav(path, audio, sr):
    import numpy as np
    pcm = (np.clip(np.asarray(audio, dtype="float32").reshape(-1), -1, 1) * 32767).astype("<i2").tobytes()
    with wave.open(path, "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(int(sr))
        w.writeframes(pcm)


def load_qwen(model_id):
    import torch
    from qwen_tts import Qwen3TTSModel
    torch.set_num_threads(max(1, torch.get_num_threads()))
    device = "cuda:0" if torch.cuda.is_available() else "cpu"
    dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32
    model = Qwen3TTSModel.from_pretrained(model_id, device_map=device, dtype=dtype)
    speakers = sorted(model._supported_speakers_set() or [])
    languages = sorted(model._supported_languages_set() or [])

    def synth(req):
        lang = req.get("language") or "Portuguese"
        if speakers:
            wavs, sr = model.generate_custom_voice(text=req["text"], speaker=req.get("speaker") or speakers[0],
                                                   language=lang, instruct=req.get("instruct") or None)
        else:
            raise RuntimeError("este modelo precisa de uma referência de voz autorizada (Base/clonagem)")
        return wavs[0], sr
    return synth, speakers, languages, device


def load_fake():
    """Test double (KAGUYA_TTS_WORKER_FAKE=1): no model, a short tone; prints junk to stdout on purpose."""
    import numpy as np
    print("\nbiblioteca barulhenta: aviso qualquer")

    def synth(req):
        if "falhe" in req["text"]:
            raise RuntimeError("falha simulada")
        n = 2400 + 120 * len(req["text"])
        return np.sin(np.linspace(0, 400, n)).astype("float32") * 0.5, 24000
    return synth, ["serena", "vivian"], ["portuguese"], "cpu"


def main():
    _protect_stdout()
    engine, model_id = sys.argv[1], sys.argv[2]
    t0 = time.perf_counter()
    try:
        if os.environ.get("KAGUYA_TTS_WORKER_FAKE") == "1":
            synth, speakers, languages, device = load_fake()
        elif engine == "qwen3":
            synth, speakers, languages, device = load_qwen(model_id)
        else:
            raise RuntimeError(f"motor desconhecido: {engine}")
    except Exception as exc:  # reported to the Studio, never hidden
        emit({"ready": False, "error": f"{type(exc).__name__}: {exc}"})
        return 1
    emit({"ready": True, "engine": engine, "model": model_id, "device": device, "speakers": speakers,
          "languages": languages, "load_s": round(time.perf_counter() - t0, 2)})
    for line in sys.stdin:
        line = line.strip()
        if not line:
            continue
        try:
            req = json.loads(line)
        except ValueError:
            continue
        if req.get("cmd") == "quit":
            return 0
        t1 = time.perf_counter()
        try:
            audio, sr = synth(req)
            write_wav(req["out"], audio, sr)
            emit({"id": req.get("id"), "ok": True, "sr": int(sr), "audio_s": round(len(audio) / float(sr), 3),
                  "gen_s": round(time.perf_counter() - t1, 3), "speaker": req.get("speaker"),
                  "instruct": req.get("instruct")})
        except Exception as exc:
            emit({"id": req.get("id"), "ok": False, "error": f"{type(exc).__name__}: {exc}"})
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

"""Heavy neural TTS engines (Qwen3-TTS) in their own isolated Python environment.

Nothing here runs unless the user confirms the install in the Vozes page (spec "07 segurança": tell model, origin,
size, licence and destination before downloading). Everything lives in ``<data>/vozes/<engine>/``:

    uv/            pinned uv 0.11.32 (sha256 checked)   → creates the environment, downloads Python 3.12
    python/        Python managed by uv
    venv/          PyTorch (CPU build) + qwen-tts 0.1.1
    hf/            model weights (Hugging Face cache)
    instalado.json written only after the worker really loaded the model and answered

The Studio never imports PyTorch: synthesis goes through ``workers/tts_worker.py`` (JSON lines over stdin/stdout).
Removing the folder removes everything.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import io
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import threading
import time
import urllib.request
import zipfile

UV_VERSION = "0.11.32"
UV_ASSETS = {  # official GitHub release assets and their published sha256
    "win32": ("uv-x86_64-pc-windows-msvc.zip", "acfde570451cfdb8689fa159a138ee805ba4e241c466432750302c86254b0984"),
}
TORCH_INDEX_CPU = "https://download.pytorch.org/whl/cpu"


@dataclass
class HeavySpec:
    id: str
    name: str
    packages: list[str]
    model: str
    license: str
    approx: str
    notes: str


SPECS = {
    "qwen3": HeavySpec(
        id="qwen3", name="Qwen3-TTS 0.6B CustomVoice", packages=["qwen-tts==0.1.1"],
        model="Qwen/Qwen3-TTS-12Hz-0.6B-CustomVoice", license="Apache-2.0",
        approx="≈ 4 GB no total: ambiente ≈ 1,6 GB (PyTorch para CPU + bibliotecas), modelo ≈ 2,4 GB "
               "(Hugging Face, Qwen) e ≈ 60 MB de ferramentas (uv e Python 3.12)",
        notes="9 vozes predefinidas, todas nativas de outros idiomas (chinês, inglês, japonês, coreano): o português sai "
              "com sotaque. Sem clonagem. Roda na CPU (a GT 1030 não tem memória suficiente). Medido na nuvem (4 vCPU): "
              "carga 9 s, RTF ≈ 4 — cerca de 3× mais lento que o Kokoro. Bom para testar no A/B, não para o Live."),
}


def engine_dir(home: Path, eid: str) -> Path:
    return Path(home) / "vozes" / eid


def venv_python(home: Path, eid: str) -> Path:
    v = engine_dir(home, eid) / "venv"
    return v / ("Scripts/python.exe" if sys.platform == "win32" else "bin/python")


def status(home: Path, eid: str) -> dict:
    """Read the install marker (written only after a successful real load)."""
    try:
        info = json.loads((engine_dir(home, eid) / "instalado.json").read_text(encoding="utf-8"))
        if venv_python(home, eid).exists():
            return info
    except (OSError, ValueError):
        pass
    return {}


def worker_script() -> Path:
    return Path(__file__).resolve().parent / "workers" / "tts_worker.py"


def _flags() -> int:
    return getattr(subprocess, "CREATE_NO_WINDOW", 0) if os.name == "nt" else 0


class Installer:
    """Runs the install steps in a background thread; every line goes to ``log``. Cancellable."""

    def __init__(self, home: Path, eid: str, log=print):
        self.home, self.spec, self.log = Path(home), SPECS[eid], log
        self.dir = engine_dir(home, eid)
        self.cancel = threading.Event()
        self.proc: subprocess.Popen | None = None

    # ------------------------------------------------------------------ steps
    def _env(self) -> dict:
        env = dict(os.environ)
        env.update({"UV_CACHE_DIR": str(self.dir / "uv-cache"), "UV_PYTHON_INSTALL_DIR": str(self.dir / "python"),
                    "HF_HOME": str(self.dir / "hf"), "PYTHONNOUSERSITE": "1", "UV_NO_PROGRESS": "1"})
        for k in ("OPENAI_API_KEY", "ANTHROPIC_API_KEY", "HF_TOKEN"):
            env.pop(k, None)
        return env

    def _run(self, cmd: list[str], timeout: int = 3600) -> None:
        if self.cancel.is_set():
            raise RuntimeError("instalação cancelada")
        self.log("$ " + " ".join(str(c) for c in cmd))
        proc = self.proc = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True,
                                            encoding="utf-8", errors="replace", env=self._env(), creationflags=_flags())
        reason = {}

        def watch():   # cancel/timeout take effect even while the command prints nothing (e.g. a big download)
            end = time.monotonic() + timeout
            while proc.poll() is None:
                if self.cancel.wait(0.3) or time.monotonic() > end:
                    reason["r"] = "instalação cancelada" if self.cancel.is_set() else "tempo esgotado"
                    proc.kill()
                    return
        watcher = threading.Thread(target=watch, daemon=True)
        watcher.start()
        try:
            for line in proc.stdout:
                if line.strip():
                    self.log("  " + line.rstrip()[:300])
            code = proc.wait()
        finally:
            proc.stdout.close()
            watcher.join(2)
        if reason:
            raise RuntimeError(reason["r"])
        if code != 0:
            raise RuntimeError(f"comando falhou (código {code})")

    def uv(self) -> str:
        found = shutil.which("uv")
        if found:
            self.log(f"uv encontrado: {found}")
            return found
        target = self.dir / "uv" / ("uv.exe" if sys.platform == "win32" else "uv")
        if target.exists():
            return str(target)
        if sys.platform not in UV_ASSETS:
            raise RuntimeError("sem uv para este sistema")
        name, sha = UV_ASSETS[sys.platform]
        url = f"https://github.com/astral-sh/uv/releases/download/{UV_VERSION}/{name}"
        self.log(f"baixando uv {UV_VERSION} (oficial, GitHub astral-sh/uv)…")
        data = urllib.request.urlopen(url, timeout=120).read()
        got = hashlib.sha256(data).hexdigest()
        if got != sha:
            raise RuntimeError(f"checksum do uv não confere ({got[:12]}…); nada foi instalado")
        target.parent.mkdir(parents=True, exist_ok=True)
        with zipfile.ZipFile(io.BytesIO(data)) as z:
            for member in z.namelist():
                if member.endswith(("uv.exe", "uvx.exe")) and ".." not in member:
                    (target.parent / Path(member).name).write_bytes(z.read(member))
        return str(target)

    def install(self) -> dict:
        self.dir.mkdir(parents=True, exist_ok=True)
        uv = self.uv()
        venv = self.dir / "venv"
        if not venv_python(self.home, self.spec.id).exists():
            self._run([uv, "venv", str(venv), "--python", "3.12", "--seed"])
        py = str(venv_python(self.home, self.spec.id))
        self._run([uv, "pip", "install", "--python", py, "torch", "torchaudio", "--index-url", TORCH_INDEX_CPU])
        self._run([uv, "pip", "install", "--python", py, *self.spec.packages])
        self.log("carregando o modelo pela primeira vez (baixa os pesos do Hugging Face)…")
        client = WorkerClient(self.home, self.spec.id, self.spec.model)
        try:
            info = client.start(timeout=3600, cancel=self.cancel)
        finally:
            client.close()
        marker = {"engine": self.spec.id, "model": self.spec.model, "speakers": info.get("speakers", []),
                  "languages": info.get("languages", []), "device": info.get("device"), "load_s": info.get("load_s"),
                  "installed_at": time.strftime("%Y-%m-%d %H:%M")}
        (self.dir / "instalado.json").write_text(json.dumps(marker, ensure_ascii=False, indent=1), encoding="utf-8")
        self.log(f"pronto: {len(marker['speakers'])} voz(es), dispositivo {marker['device']}")
        return marker

    def uninstall(self) -> None:
        shutil.rmtree(self.dir, ignore_errors=True)


class WorkerClient:
    """Persistent worker process (keeps the model loaded); one request at a time."""

    def __init__(self, home: Path, eid: str, model: str, python: str | None = None):
        self.home, self.eid, self.model = Path(home), eid, model
        self.python = python or str(venv_python(home, eid))
        self.proc: subprocess.Popen | None = None
        self.info: dict = {}
        self._lock = threading.Lock()

    def start(self, timeout: float = 600, cancel: threading.Event | None = None) -> dict:
        env = dict(os.environ, HF_HOME=str(engine_dir(self.home, self.eid) / "hf"), PYTHONNOUSERSITE="1",
                   TOKENIZERS_PARALLELISM="false")
        self.err = tempfile.TemporaryFile(mode="w+")
        self.proc = subprocess.Popen([self.python, str(worker_script()), self.eid, self.model], stdin=subprocess.PIPE,
                                     stdout=subprocess.PIPE, stderr=self.err, text=True, encoding="utf-8",
                                     env=env, creationflags=_flags())
        line = self._readline(timeout, cancel)
        self.info = json.loads(line) if line else {"ready": False, "error": "o processo de voz não respondeu"}
        if not self.info.get("ready"):
            self.close()
            raise RuntimeError(self.info.get("error") or "falha ao carregar o modelo")
        return self.info

    def _readline(self, timeout: float, cancel=None) -> str:
        """Next protocol line (a JSON object); stray non-JSON output is skipped."""
        box = {}

        def read():
            for line in self.proc.stdout:
                if line.lstrip().startswith("{"):
                    box["l"] = line
                    return
        t = threading.Thread(target=read, daemon=True)
        t.start()
        end = time.monotonic() + timeout
        while t.is_alive() and time.monotonic() < end:
            if cancel is not None and cancel.is_set():
                self.close()
                raise RuntimeError("cancelado")
            t.join(0.2)
        return box.get("l", "")

    def synth(self, text: str, speaker: str = "", language: str = "Portuguese", instruct: str = "",
              timeout: float = 300):
        import numpy as np
        import wave
        with self._lock:
            if self.proc is None or self.proc.poll() is not None:
                self.start()
            fd, out = tempfile.mkstemp(suffix=".wav", prefix="kaguya-voz-")
            os.close(fd)
            try:
                req = {"id": 1, "text": text, "speaker": speaker, "language": language, "instruct": instruct, "out": out}
                self.proc.stdin.write(json.dumps(req, ensure_ascii=False) + "\n")
                self.proc.stdin.flush()
                line = self._readline(timeout)
                if not line:
                    self.close()
                    raise RuntimeError("o motor de voz não respondeu a tempo")
                rep = json.loads(line)
                if not rep.get("ok"):
                    raise RuntimeError(rep.get("error") or "falha na síntese")
                with wave.open(out, "rb") as w:
                    sr = w.getframerate()
                    pcm = np.frombuffer(w.readframes(w.getnframes()), dtype="<i2").astype("float32") / 32768
                return pcm, sr
            finally:
                try:
                    os.unlink(out)
                except OSError:
                    pass

    def close(self):
        p, self.proc = self.proc, None
        if p is None:
            return
        if p.poll() is None:
            try:
                p.stdin.write('{"cmd":"quit"}\n')
                p.stdin.flush()
                p.wait(10)
            except Exception:
                p.kill()
                p.wait(5)
        for f in (p.stdin, p.stdout, getattr(self, "err", None)):
            try:
                f.close()
            except Exception:
                pass

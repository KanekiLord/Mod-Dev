"""Entry point: ``python -m kaguya`` (or INICIAR_KAGUYA_STUDIO.bat).

Options:
  --mascotes            open only the floating mascots
  --demo                demonstration mode: temporary data folder + simulated CLIs (tests/fake_cli.py)
  --captura ARQ.png     render the window to an image and exit (visual verification)
  --pagina NOME         page for --captura (chat, queue, memory, agents, usage, diag, settings)
  --escala N            simulate Windows display scaling (1, 1.25, 1.5, 2) — sets QT_SCALE_FACTOR
  --tamanho LxA         window size for --captura (default 1480x920)
"""
from __future__ import annotations

import argparse
import os
from pathlib import Path
import sys
import tempfile


def _args(argv):
    ap = argparse.ArgumentParser(prog="kaguya")
    ap.add_argument("--mascotes", action="store_true")
    ap.add_argument("--demo", action="store_true")
    ap.add_argument("--captura")
    ap.add_argument("--pagina", default="chat")
    ap.add_argument("--escala", type=float)
    ap.add_argument("--tamanho", default="1480x920")
    ap.add_argument("--flutuantes", action="store_true", help="em --captura, também captura as mascotes flutuantes")
    ap.add_argument("--verificar-voz", action="store_true", dest="verificar_voz",
                    help="grava em logs/voz.txt se a transcrição local está disponível e sai")
    ap.add_argument("--sair", action="store_true",
                    help="pede para o Kaguya Studio aberto fechar (usado pelo instalador antes de atualizar)")
    ap.add_argument("--segundo-plano", action="store_true", dest="segundo_plano",
                    help="abre direto na bandeja (perto do relógio), sem mostrar a janela")
    ap.add_argument("--sair-apos", type=float, dest="sair_apos",
                    help="abre normalmente e fecha após N segundos (teste automático do modo normal)")
    return ap.parse_args(argv)


def _setup_demo() -> dict:
    """Simulated environment for screenshots/tests: never touches the real data folder."""
    from ..appdirs import APP_ROOT
    base = Path(tempfile.mkdtemp(prefix="kaguya-demo-"))
    os.environ["KAGUYA_HOME"] = str(base / "dados")
    sys.path.insert(0, str(APP_ROOT))
    from tests.helpers import fake_env, git_init, make_fake_clis
    bindir = base / "bin"
    make_fake_clis(bindir)
    project = base / "Projetos" / "NarutoCD"
    git_init(project)
    (project / "src" / "missao").mkdir(parents=True)
    (project / "src" / "missao" / "MissaoManager.java").write_text("class MissaoManager {}\n", encoding="utf-8")
    agents = project / ".claude" / "agents"
    agents.mkdir(parents=True)
    for name, desc, model in (("narutocd-explorador", "Encontra onde uma classe ou mecânica é usada, sem alterar.", "haiku"),
                              ("narutocd-revisor", "Revisa alterações de código antes de dar por concluídas.", "sonnet"),
                              ("narutocd-juiz", "Dá o veredito: aprovada, reprovada ou pendente.", "sonnet"),
                              ("narutocd-registro", "Registra o que foi feito no segundo cérebro.", "haiku"),
                              ("ajudante-local", "Agente de exemplo que não está no catálogo.", "")):
        (agents / f"{name}.md").write_text(f"---\nname: {name}\ndescription: {desc}\nmodel: {model}\n---\nExemplo.\n",
                                           encoding="utf-8")
    vault = base / "Segundo Cérebro"
    for d in (".obsidian", "conhecimento/raw", "memoria", "projetos/NarutoCD", "tasks"):
        (vault / d).mkdir(parents=True, exist_ok=True)
    (vault / "conhecimento" / "forge-eventos.md").write_text("# Eventos no Forge 1.7.10\nRegistre handlers no "
                                                             "FMLInitializationEvent. Ver [[NarutoCD]].\n", encoding="utf-8")
    (vault / "conhecimento" / "raw" / "photon.md").write_text("# Photon shader\nEfeitos de luz do jutsu.\n", encoding="utf-8")
    (vault / "projetos" / "NarutoCD" / "missoes.md").write_text("# Missões rank A e S\nRecompensas progressivas.\n",
                                                                 encoding="utf-8")
    (vault / "tasks" / "todo.md").write_text("# Foco da semana\n- [ ] Missões rank S\n- [x] Missões rank C\n"
                                             "- [ ] Registro no Obsidian\n", encoding="utf-8")
    return {"env": fake_env(bindir, FAKE_CODEX_WRITE="1", FAKE_VERDICTS=str(base / "verdicts.txt")),
            "project": project, "vault": vault, "base": base}


def main(argv=None) -> int:
    args = _args(sys.argv[1:] if argv is None else argv)
    from . import diagnostics as dg
    if args.verificar_voz:
        return _check_voice(dg)
    if not args.captura:
        dg.install()
    dg.step(f"início • args={sys.argv[1:] if argv is None else argv} • congelado={getattr(sys, 'frozen', False)}"
            f" • python={sys.version.split()[0]}")
    if args.escala:
        os.environ["QT_SCALE_FACTOR"] = str(args.escala)
    if args.captura and sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
    demo = _setup_demo() if args.demo else None

    from PySide6.QtCore import Qt
    from PySide6.QtGui import QGuiApplication, QIcon
    from PySide6.QtWidgets import QApplication

    QGuiApplication.setHighDpiScaleFactorRoundingPolicy(Qt.HighDpiScaleFactorRoundingPolicy.PassThrough)
    if os.name == "nt":
        try:  # taskbar icon/grouping
            import ctypes
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("KaguyaStudio.4")
        except Exception:
            pass
    app = QApplication.instance() or QApplication(sys.argv)
    dg.step(f"QApplication criado • plataforma={app.platformName()}")
    if not args.captura:
        dg.start_watchdog(app)
    app.setApplicationName("Kaguya Studio")
    app.setOrganizationName("KaguyaStudio")
    single = not (args.captura or args.demo or args.mascotes)
    if single or args.sair:
        from . import single as one
        if one.send("sair" if args.sair else ("bandeja" if args.segundo_plano else "mostrar")):
            dg.step("outra cópia já está aberta: comando enviado a ela")
            return 0
        if args.sair:
            return 0  # nothing running

    from . import theme
    theme.load_fonts()
    app.setFont(theme.font(9.5))
    app.setStyleSheet(theme.stylesheet())
    app.setWindowIcon(QIcon(str(theme.asset("branding/kaguya.ico"))))

    from ..appdirs import data_dir, legacy_v3_database
    from ..orchestrator.engine import Engine
    from ..store import Store
    home = data_dir()
    store = Store(home / "studio.sqlite3")
    store.recover_interrupted()
    dg.step(f"banco aberto em {home}")
    legacy = legacy_v3_database()
    if legacy and not store.get_setting("migration.v3.done") and not demo:
        try:
            rep = store.import_v3(legacy)
            dg.step(f"importação V3: {rep}")
        except Exception:
            dg.step("importação V3 falhou (o Studio segue sem ela)")
            sys.excepthook(*sys.exc_info())
            store.set_setting("migration.v3.done", True)
    engine = Engine(store, home=home, env=demo["env"] if demo else None)

    if demo:
        _seed_demo(store, engine, demo)

    from .main_window import MainWindow
    dg.step("criando janela principal")
    win = MainWindow(store, engine, demo=bool(demo))
    dg.step("janela criada")
    if args.mascotes:
        for m in win.mascots.values():
            m.show_window()
        win.hide()
        app.setQuitOnLastWindowClosed(True)
        return app.exec()
    if args.captura:
        return _capture(app, win, args)
    if single:
        from .single import InstanceServer

        def command(msg):
            if msg == "mostrar":
                win.show_from_tray()
            elif msg == "sair":
                dg.step("pedido para sair (instalador/atualização)")
                win.quit_app(force=True)
        win._instance_server = InstanceServer(command, win)
    if args.segundo_plano and getattr(win, "tray", None):
        dg.step("iniciado na bandeja")
    else:
        win.show()
    dg.step("janela exibida; entrando no laço de eventos")
    if args.sair_apos:
        from PySide6.QtCore import QTimer

        def finish():
            n = dg.error_count()
            dg.step(f"saída automática • erros={n}")
            app.exit(0 if n == 0 else 3)
        QTimer.singleShot(int(args.sair_apos * 1000), finish)
    code = app.exec()
    dg.step(f"encerrado • código={code}")
    _teardown(app, win)
    return code


def _teardown(app, win) -> None:
    """Destroy windows while QApplication still exists (objects left for interpreter shutdown are destroyed
    in arbitrary order, which can crash on exit)."""
    from PySide6.QtCore import QCoreApplication, QEvent
    from .common import wait_background
    try:
        win.detach()
        wait_background(10)
        for wdg in app.topLevelWidgets():
            wdg.deleteLater()
        QCoreApplication.sendPostedEvents(None, QEvent.DeferredDelete)
    except RuntimeError:
        pass


def _check_voice(dg) -> int:
    """Import the voice stack for real (no microphone needed) and record the result."""
    from ..appdirs import data_dir
    from ..voice import stt
    lines = []
    st = stt.status(data_dir() / "modelos")
    lines.append(f"faltando={st.missing}")
    ok = st.ready
    for mod in ("numpy", "faster_whisper", "ctranslate2", "sounddevice", "kokoro_onnx", "espeakng_loader"):
        try:
            __import__(mod)
            lines.append(f"{mod}: ok")
        except Exception as exc:  # report precisely what fails inside the frozen build
            ok = False
            lines.append(f"{mod}: ERRO {type(exc).__name__}: {exc}")
    lines.append("RESULTADO: " + ("PRONTO" if ok else "INDISPONIVEL"))
    (dg.logs_dir() / "voz.txt").write_text("\n".join(lines), encoding="utf-8")
    print("\n".join(lines))
    return 0 if ok else 4


def _seed_demo(store, engine, demo):
    from ..messages import classify_message
    pid = store.add_project("NarutoCD", demo["project"])
    store.set_global_vault(demo["vault"])
    store.add_project("JurassiCouto", demo["base"] / "Projetos" / "NarutoCD" / "src")
    store.set_setting("ui.last_project", pid)
    (demo["base"] / "verdicts.txt").write_text("reprovado\naprovado\n", encoding="utf-8")
    for a in ("codex", "claude"):
        engine.diagnose(a, str(demo["project"]))
    engine.vault_index(str(demo["vault"])).update()
    engine.submit(pid, classify_message("@equipe: Implemente o sistema de missões rank A e S com recompensas "
                                        "progressivas e testes", "equipe"), write=True, commands=True)
    engine.wait(pid, 60)
    engine.submit(pid, classify_message("DEPOIS: criar HUD de chakra", "equipe"))
    engine.submit(pid, classify_message("IDEIA: modo sharingan com efeito Photon", "equipe"))


def _capture(app, win, args) -> int:
    from PySide6.QtCore import QTimer
    import faulthandler
    # automated runs must never hang: dump the stacks and exit. The windowed .exe has no stderr, so write to a file.
    from . import diagnostics as dg
    try:
        target = sys.stderr if sys.stderr is not None and sys.stderr.fileno() >= 0 else None
    except (OSError, ValueError, AttributeError):
        target = None
    if target is None:
        target = open(dg.logs_dir() / "captura_travada.txt", "w", encoding="utf-8")  # noqa: SIM115 (kept open)
    faulthandler.dump_traceback_later(120, exit=True, file=target)
    w, h = (int(x) for x in args.tamanho.lower().split("x"))
    win.resize(w, h)
    win.show()
    win.go(args.pagina)
    if args.flutuantes:
        for m in win.mascots.values():
            m.show_window()

    def shot():
        for _ in range(5):
            app.processEvents()
        pm = win.grab()
        out = Path(args.captura)
        out.parent.mkdir(parents=True, exist_ok=True)
        pm.save(str(out))
        if args.flutuantes:
            for m in win.mascots.values():
                if m.window:
                    m.window.grab().save(str(out.with_name(out.stem + f"_flutuante_{m.agent}.png")))
        print(f"captura: {out} ({pm.width()}x{pm.height()} px, escala {args.escala or 1})")
        # exit(), not quit(): in Qt 6 quit() first asks every window to close, and the main window
        # declines (it goes to the tray), which would keep the process alive forever
        app.exit(0)
    QTimer.singleShot(1200, shot)
    return app.exec()


if __name__ == "__main__":
    raise SystemExit(main())

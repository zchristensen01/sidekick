# PyInstaller build of Sidekick (M24): Sidekick.exe (the app, no console window) and
# sidekick-helper.exe (its hidden command-line twin, for data refreshes), in one folder that
# shares Python and the libraries (`_internal`). Run it through packaging/build.py, which
# writes build.json and the version resources first.
#
# What goes in: the scout package with its rules, client certificate and page; the shared
# champion knowledge (data/manual); the writer's prompt (docs/REPORT_AGENT.md); the example
# settings. Nothing personal: those files live in each user's own folder (scout/paths.py).

from pathlib import Path

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

ROOT = Path(SPECPATH).parent  # noqa: F821 (PyInstaller defines SPECPATH)
STAGE = ROOT / "build" / "packaging"
ICON = str(ROOT / "scout" / "app" / "sidekick.ico")

datas = collect_data_files("scout")
datas += [
    (str(ROOT / "data" / "manual"), "data/manual"),
    (str(ROOT / "docs" / "REPORT_AGENT.md"), "docs"),
    (str(ROOT / "docs" / "TRAITS.md"), "docs"),
    (str(ROOT / "config.example.yaml"), "."),
    (str(ROOT / ".env.example"), "."),
    (str(STAGE / "build.json"), "."),
]
hidden = ["webview.platforms.winforms", "webview.platforms.edgechromium", "clr"]
hidden += collect_submodules("scout")
# Not used by the installed app: other window toolkits, the old tkinter window, test tools.
excludes = ["tkinter", "PyQt5", "PyQt6", "PySide2", "PySide6", "gi", "cefpython3", "pytest", "ruff"]


def analysis(script):
    return Analysis(  # noqa: F821
        [str(ROOT / "packaging" / script)], pathex=[str(ROOT)], datas=datas,
        hiddenimports=hidden, excludes=excludes,
    )


app = analysis("entry_app.py")
helper = analysis("entry_helper.py")

app_exe = EXE(  # noqa: F821
    PYZ(app.pure), app.scripts, [], exclude_binaries=True, name="Sidekick", icon=ICON,  # noqa: F821
    console=False, upx=False, version=str(STAGE / "version_app.txt"),
)
helper_exe = EXE(  # noqa: F821
    PYZ(helper.pure), helper.scripts, [], exclude_binaries=True, name="sidekick-helper",  # noqa: F821
    icon=ICON, console=True, upx=False, version=str(STAGE / "version_helper.txt"),
)
COLLECT(  # noqa: F821
    app_exe, helper_exe, app.binaries, app.datas, helper.binaries, helper.datas,
    name="Sidekick", upx=False,
)

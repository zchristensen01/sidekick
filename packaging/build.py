"""Build Sidekick's installer (M24): build.json, PyInstaller, Inno Setup, latest.json.

From the repo folder, on Windows, with the developer environment (tools/dev_setup.ps1) plus
`pip install -e ".[build]"` and Inno Setup 6:

    python packaging/build.py --version 2026.10.5.3

Steps (each one stops the build with a plain message if it fails):
1. build/packaging/: build.json (version, commit, date) and the two .exe version resources.
2. PyInstaller (packaging/sidekick.spec) -> dist/Sidekick/ (Sidekick.exe, sidekick-helper.exe).
3. Microsoft's WebView2 bootstrapper, downloaded once (the installer runs it only on a PC that
   lacks the runtime; Microsoft allows passing it on).
4. Inno Setup (packaging/sidekick.iss) -> dist/SidekickSetup.exe.
5. dist/latest.json (what the app's update check reads) and dist/notes.md (the release text):
   the version, what changed since the last release, the installer's SHA-256.
GitHub Actions runs the same on every release (.github/workflows/release.yml).
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
STAGE = ROOT / "build" / "packaging"
DIST = ROOT / "dist"
REPO = "zchristensen01/sidekick"
WEBVIEW2_URL = "https://go.microsoft.com/fwlink/p/?LinkId=2124703"  # the Evergreen bootstrapper
VERSION = re.compile(r"^\d{1,5}\.\d{1,5}\.\d{1,5}\.\d{1,5}$")
VERSION_RESOURCE = """VSVersionInfo(
  ffi=FixedFileInfo(filevers={nums}, prodvers={nums}, mask=0x3f, flags=0x0, OS=0x40004,
                    fileType=0x1, subtype=0x0, date=(0, 0)),
  kids=[
    StringFileInfo([StringTable('040904B0', [
      StringStruct('CompanyName', 'Sidekick'),
      StringStruct('FileDescription', '{description}'),
      StringStruct('FileVersion', '{version}'),
      StringStruct('InternalName', '{name}'),
      StringStruct('OriginalFilename', '{name}.exe'),
      StringStruct('ProductName', 'Sidekick'),
      StringStruct('ProductVersion', '{version}')])]),
    VarFileInfo([VarStruct('Translation', [1033, 1200])])
  ]
)
"""


class BuildError(Exception):
    pass


def run(args: list[str], **kwargs) -> str:
    done = subprocess.run(args, cwd=ROOT, capture_output=True, text=True, encoding="utf-8",
                          errors="replace", **kwargs)  # fmt: skip
    if done.returncode != 0:
        raise BuildError(f"{Path(args[0]).name} failed:\n{(done.stdout + done.stderr)[-4000:]}")
    return done.stdout.strip()


def git(*args: str) -> str:
    try:
        return run(["git", *args])
    except (BuildError, OSError):
        return ""


def check_version(version: str) -> tuple[int, int, int, int]:
    if not VERSION.match(version) or any(int(p) > 65535 for p in version.split(".")):
        raise BuildError(f"Version {version!r} must be four numbers up to 65535, e.g. 2026.10.5.3.")
    a, b, c, d = (int(p) for p in version.split("."))
    return a, b, c, d


def stage(version: str) -> dict:
    """build.json and the version resources for the two .exe files."""
    STAGE.mkdir(parents=True, exist_ok=True)
    info = {"version": version, "commit": git("rev-parse", "--short", "HEAD"),
            "built": date.today().isoformat()}  # fmt: skip
    (STAGE / "build.json").write_text(json.dumps(info, indent=1) + "\n", encoding="utf-8")
    nums = check_version(version)
    for name, file, description in (("Sidekick", "version_app.txt", "Sidekick"),
                                    ("sidekick-helper", "version_helper.txt",
                                     "Sidekick helper (data refresh)")):  # fmt: skip
        text = VERSION_RESOURCE.format(nums=nums, version=version, name=name,
                                       description=description)  # fmt: skip
        (STAGE / file).write_text(text, encoding="utf-8")
    return info


def pyinstaller() -> Path:
    run([sys.executable, "-m", "PyInstaller", str(ROOT / "packaging" / "sidekick.spec"),
         "--noconfirm", "--clean", "--distpath", str(DIST),
         "--workpath", str(ROOT / "build" / "pyinstaller")])  # fmt: skip
    folder = DIST / "Sidekick"
    for exe in ("Sidekick.exe", "sidekick-helper.exe"):
        if not (folder / exe).exists():
            raise BuildError(f"PyInstaller didn't make {exe}.")
    return folder


def webview2() -> Path:
    target = STAGE / "MicrosoftEdgeWebview2Setup.exe"
    if not target.exists():
        import httpx

        response = httpx.get(WEBVIEW2_URL, follow_redirects=True, timeout=120)
        if response.status_code != 200 or not response.content.startswith(b"MZ"):
            raise BuildError("Couldn't download the WebView2 bootstrapper "
                             f"({response.status_code}).")
        target.write_bytes(response.content)
    return target


def iscc_path() -> Path:
    candidates = [os.environ.get("ISCC", "")]
    candidates += [str(Path(base) / "Inno Setup 6" / "ISCC.exe") for base in (
        os.environ.get("PROGRAMFILES(X86)", r"C:\Program Files (x86)"),
        os.environ.get("PROGRAMFILES", r"C:\Program Files"),
        str(Path(os.environ.get("LOCALAPPDATA", "")) / "Programs"),
    )]  # fmt: skip
    found = next((Path(c) for c in candidates if c and Path(c).exists()), None)
    if found is None and shutil.which("iscc"):
        found = Path(shutil.which("iscc"))
    if found is None:
        raise BuildError("Inno Setup 6 isn't installed "
                         "(winget install -e --id JRSoftware.InnoSetup).")
    return found


def installer(version: str, folder: Path, bootstrapper: Path) -> Path:
    run([str(iscc_path()), f"/DAppVersion={version}", f"/DSourceDir={folder}",
         f"/DOutputDir={DIST}", f"/DWebView2={bootstrapper}", "/Q",
         str(ROOT / "packaging" / "sidekick.iss")])  # fmt: skip
    setup = DIST / "SidekickSetup.exe"
    if not setup.exists():
        raise BuildError("Inno Setup didn't make SidekickSetup.exe.")
    return setup


def changes(since: str) -> list[str]:
    """Commit subjects since the last release tag (or the last 15), newest first."""
    span = [f"{since}..HEAD"] if since else ["-n", "15"]
    log = git("log", "--format=%s", "--no-merges", *span)
    return [line for line in log.splitlines() if line.strip()][:30]


def last_tag() -> str:
    return git("describe", "--tags", "--abbrev=0", "--match", "v*")


def publish_files(version: str, setup: Path, info: dict, since: str) -> None:
    digest = hashlib.sha256(setup.read_bytes()).hexdigest()
    tag = f"v{version}"
    notes = changes(since)
    latest = {"version": version, "tag": tag, "commit": info["commit"],
              "published": info["built"],
              "installer": f"https://github.com/{REPO}/releases/download/{tag}/SidekickSetup.exe",
              "sha256": digest, "notes": notes}  # fmt: skip
    (DIST / "latest.json").write_text(json.dumps(latest, indent=1) + "\n", encoding="utf-8")
    lines = [f"Sidekick {version}.", "", "**Download:** `SidekickSetup.exe` below. New here? "
             f"See the [README](https://github.com/{REPO}#readme).", "", "What changed:"]
    lines += [f"- {n}" for n in notes] or ["- Maintenance."]
    lines += ["", f"SHA-256 of SidekickSetup.exe: `{digest}`"]
    (DIST / "notes.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def main() -> int:
    today = date.today()
    parser = argparse.ArgumentParser(description="Build Sidekick's installer.")
    parser.add_argument("--version", default=f"{today.year}.{today.month}.{today.day}.0",
                        help="four numbers, e.g. 2026.10.5.3 (default: today's date, .0)")
    parser.add_argument("--since", default=None, help="the last release's tag (default: newest)")
    parser.add_argument("--no-installer", action="store_true", help="stop after PyInstaller")
    args = parser.parse_args()
    try:
        check_version(args.version)
        info = stage(args.version)
        print(f"Building Sidekick {args.version} ({info['commit'] or 'no commit'})")
        folder = pyinstaller()
        print(f"  app: {folder}")
        if args.no_installer:
            return 0
        setup = installer(args.version, folder, webview2())
        since = last_tag() if args.since is None else args.since
        publish_files(args.version, setup, info, since)
        print(f"  installer: {setup} ({setup.stat().st_size / 1e6:.1f} MB)")
        print(f"  release files: {DIST / 'latest.json'}, {DIST / 'notes.md'}")
    except BuildError as exc:
        print(exc, file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())

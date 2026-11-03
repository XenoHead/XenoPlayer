#!/usr/bin/env python3
"""Build the macOS Core edition of XenoPlayer.

Run this on macOS (or a macOS CI runner). PyInstaller cannot cross-compile a
macOS .app from Windows.

    python3 -m venv .venv-mac
    source .venv-mac/bin/activate
    pip install -r requirements-macos.txt
    python build_macos.py

Outputs:
    dist/XenoPlayer.app
    dist/XenoPlayer-<version>-macOS.dmg

Optional environment variables:
    XENO_MAC_ARCH            arm64 (default), x86_64, or universal2
    XENO_CODESIGN_IDENTITY   Developer ID identity for codesigning
    XENO_SKIP_DMG=1          skip DMG creation
"""

import json
import os
import platform
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path


ROOT = Path(__file__).resolve().parent
DIST = ROOT / "dist"
BUILD = ROOT / "build"
APP_NAME = "XenoPlayer"
BUNDLE_ID = "com.xenohead.xenoplayer"
VERSION_FALLBACK = "0.0.0"


def run(cmd, **kwargs):
    print("+", " ".join(str(part) for part in cmd))
    return subprocess.run(cmd, check=True, **kwargs)


def read_version():
    try:
        with (ROOT / "version.json").open("r", encoding="utf-8") as handle:
            return str(json.load(handle).get("version") or VERSION_FALLBACK)
    except Exception:
        return VERSION_FALLBACK


def git_value(args):
    env = os.environ.copy()
    env["GIT_TERMINAL_PROMPT"] = "0"
    env["GCM_INTERACTIVE"] = "never"
    try:
        return subprocess.check_output(
            ["git", "-C", str(ROOT)] + args,
            text=True, encoding="utf-8", errors="replace", env=env,
        ).strip()
    except Exception:
        return ""


def write_build_info(version):
    remote_main = ""
    try:
        remote_line = subprocess.check_output(
            ["git", "-C", str(ROOT), "ls-remote", "origin", "refs/heads/main"],
            text=True, encoding="utf-8", errors="replace",
            env={**os.environ, "GIT_TERMINAL_PROMPT": "0", "GCM_INTERACTIVE": "never"},
            timeout=30,
        ).strip()
        if remote_line:
            remote_main = remote_line.split()[0]
    except Exception:
        remote_main = git_value(["rev-parse", "origin/main"])

    info = {
        "version": version,
        "commit": git_value(["rev-parse", "HEAD"]),
        "remote_main": remote_main,
        "build_date": datetime.now().isoformat(timespec="seconds"),
        "platform": "macos",
        "arch": platform.machine(),
    }
    with (ROOT / "build_info.json").open("w", encoding="utf-8") as handle:
        json.dump(info, handle, indent=4)
    print(f"Build info: {info['version']} ({info['commit'] or 'unknown'})")
    return info


def make_icns():
    """Convert icon.png to build/XenoPlayer.icns using macOS tools."""
    source = ROOT / "icon.png"
    icns = BUILD / f"{APP_NAME}.icns"
    if icns.exists():
        return icns
    if not source.exists():
        print("No icon.png found; building without a custom icon.")
        return None

    iconset = BUILD / f"{APP_NAME}.iconset"
    if iconset.exists():
        shutil.rmtree(iconset)
    iconset.mkdir(parents=True, exist_ok=True)

    sizes = [
        (16, "icon_16x16.png"),
        (32, "icon_16x16@2x.png"),
        (32, "icon_32x32.png"),
        (64, "icon_32x32@2x.png"),
        (128, "icon_128x128.png"),
        (256, "icon_128x128@2x.png"),
        (256, "icon_256x256.png"),
        (512, "icon_256x256@2x.png"),
        (512, "icon_512x512.png"),
        (1024, "icon_512x512@2x.png"),
    ]
    for size, name in sizes:
        try:
            run([
                "sips", "-s", "format", "png", "-z", str(size), str(size),
                str(source), "--out", str(iconset / name),
            ], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
        except subprocess.CalledProcessError as error:
            print(f"Warning: sips could not resize the icon ({error}); building without one.")
            shutil.rmtree(iconset, ignore_errors=True)
            return None

    result = subprocess.run(
        ["iconutil", "-c", "icns", str(iconset), "-o", str(icns)],
        capture_output=True, text=True,
    )
    shutil.rmtree(iconset, ignore_errors=True)
    if result.returncode != 0 or not icns.exists():
        print("Warning: could not generate XenoPlayer.icns; building without a custom icon.")
        if result.stderr:
            print(result.stderr.strip())
        return None
    return icns


def data_argument(source, destination):
    """PyInstaller --add-data uses ':' on macOS (os.pathsep)."""
    return f"{source}{os.pathsep}{destination}"


def plist_set(plist, key, value):
    for action in ("-replace", "-insert"):
        result = subprocess.run(
            ["plutil", action, key, "-string", str(value), str(plist)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            return True
    return False


def patch_info_plist(app_path, version):
    """Set bundle metadata and allow WKWebView to reach http://localhost."""
    plist = app_path / "Contents" / "Info.plist"
    if not plist.is_file():
        return
    for key, value in (
        ("CFBundleShortVersionString", version),
        ("CFBundleVersion", version),
        ("CFBundleDisplayName", APP_NAME),
        ("LSMinimumSystemVersion", "11.0"),
        ("LSApplicationCategoryType", "public.app-category.video"),
    ):
        plist_set(plist, key, value)

    ats = json.dumps({
        "NSAllowsLocalNetworking": True,
        "NSExceptionDomains": {
            "localhost": {
                "NSExceptionAllowsInsecureHTTPLoads": True,
                "NSIncludesSubdomains": True,
            },
            "127.0.0.1": {
                "NSExceptionAllowsInsecureHTTPLoads": True,
            },
        },
    })
    for action in ("-replace", "-insert"):
        result = subprocess.run(
            ["plutil", action, "NSAppTransportSecurity", "-json", ats, str(plist)],
            capture_output=True, text=True,
        )
        if result.returncode == 0:
            print(f"Patched Info.plist for {APP_NAME} {version} and localhost access.")
            return
    print("Warning: could not add the localhost ATS exception to Info.plist.")


def resign_app(app_path):
    identity = os.environ.get("XENO_CODESIGN_IDENTITY", "").strip() or "-"
    result = subprocess.run(
        ["codesign", "--force", "--deep", "--sign", identity, str(app_path)],
        capture_output=True, text=True,
    )
    if result.returncode == 0:
        signer = identity if identity != "-" else "ad-hoc"
        print(f"Codesigned app ({signer}).")
    else:
        print("Warning: codesign failed; the app may not launch until it is signed.")
        print(result.stderr.strip())


def build_app(version, icns):
    if not (ROOT / "XenoPlayer.py").is_file():
        raise SystemExit("XenoPlayer.py not found; run this from the repository root.")

    hidden_imports = [
        "webview",
        "webview.platforms.cocoa",
        "flask",
        "cv2",
        "numpy",
        "PIL",
        "PIL.Image",
        "cloudscraper",
        "bs4",
        "edge_tts",
        "aiohttp",
        "gallery_dl",
        "send2trash",
        "requests",
        "enhance_video",
    ]
    excludes = [
        "torch", "torchvision", "transformers", "manga_ocr", "argostranslate",
        "tensorboard", "PyQt5", "PyQt6", "pytesseract", "speech_recognition",
        "pyaudio", "unidic_lite", "fugashi", "sentencepiece", "tiktoken",
        "tkinter",
    ]

    cmd = [
        sys.executable, "-m", "PyInstaller",
        str(ROOT / "XenoPlayer.py"),
        "--name", APP_NAME,
        "--windowed",
        "--clean",
        "--noconfirm",
        "--osx-bundle-identifier", BUNDLE_ID,
        "--distpath", str(DIST),
        "--workpath", str(BUILD / "pyinstaller"),
        "--specpath", str(BUILD),
    ]
    if icns:
        cmd += ["--icon", str(icns)]

    arch = os.environ.get("XENO_MAC_ARCH", "").strip()
    if arch:
        cmd += ["--target-arch", arch]
    identity = os.environ.get("XENO_CODESIGN_IDENTITY", "").strip()
    if identity:
        cmd += ["--codesign-identity", identity]

    data_files = [
        (ROOT / "web", "web"),
        (ROOT / "MAINLIST.json", "."),
        (ROOT / "version.json", "."),
        (ROOT / "build_info.json", "."),
        (ROOT / "XenoHead_art.png", "."),
        (ROOT / "XenoHead_logo.png", "."),
        (ROOT / "icon.png", "."),
    ]
    # MAINLIST.json is gitignored because it holds personal sources. CI can
    # fall back to the tracked online_sources.json so a fresh build still has
    # the default collection/audio/story sites.
    if not (ROOT / "MAINLIST.json").exists() and (ROOT / "online_sources.json").exists():
        fallback = BUILD / "MAINLIST.json"
        shutil.copy2(ROOT / "online_sources.json", fallback)
        data_files[1] = (fallback, ".")
    for source, destination in data_files:
        if source.exists():
            cmd += ["--add-data", data_argument(source, destination)]

    cmd += ["--collect-all", "edge_tts"]
    cmd += ["--collect-all", "aiohttp"]
    for module in hidden_imports:
        cmd += ["--hidden-import", module]
    for module in excludes:
        cmd += ["--exclude-module", module]

    run(cmd)
    app_path = DIST / f"{APP_NAME}.app"
    if not app_path.is_dir():
        raise SystemExit(f"Build failed: {app_path} was not produced.")
    return app_path


def make_dmg(app_path, version):
    if os.environ.get("XENO_SKIP_DMG") == "1":
        print("Skipping DMG (XENO_SKIP_DMG=1).")
        return None

    stage = BUILD / "dmg"
    if stage.exists():
        shutil.rmtree(stage)
    stage.mkdir(parents=True)
    shutil.copytree(app_path, stage / app_path.name, symlinks=True)
    try:
        os.symlink("/Applications", stage / "Applications")
    except OSError:
        pass

    dmg = DIST / f"{APP_NAME}-{version}-macOS.dmg"
    if dmg.exists():
        dmg.unlink()
    run([
        "hdiutil", "create",
        "-volname", APP_NAME,
        "-srcfolder", str(stage),
        "-ov", "-format", "UDZO",
        str(dmg),
    ])
    print(f"DMG: {dmg}")
    return dmg


def main():
    if sys.platform != "darwin":
        raise SystemExit(
            "build_macos.py must run on macOS. PyInstaller cannot cross-compile "
            "a macOS .app from Windows or Linux."
        )

    try:
        import PyInstaller  # noqa: F401
    except ImportError:
        print("PyInstaller is not installed; installing it now...")
        run([sys.executable, "-m", "pip", "install", "pyinstaller"])

    DIST.mkdir(exist_ok=True)
    BUILD.mkdir(exist_ok=True)
    for stale in (DIST / f"{APP_NAME}.app",):
        if stale.exists():
            shutil.rmtree(stale, ignore_errors=True)

    version = read_version()
    write_build_info(version)
    icns = make_icns()
    app_path = build_app(version, icns)
    patch_info_plist(app_path, version)
    resign_app(app_path)
    print(f"\nApp bundle: {app_path}")
    dmg = make_dmg(app_path, version)

    print("\nDone.")
    print(f"  App: {app_path}")
    if dmg:
        print(f"  DMG: {dmg}")
    print("\nThe build is unsigned unless XENO_CODESIGN_IDENTITY was set.")
    print("See MACOS.md for signing, notarization, and test steps.")


if __name__ == "__main__":
    main()

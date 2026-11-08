# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller spec for the SigmaHelix desktop bundle.

Build from the repository root:

    pyinstaller packaging/sigmahelix.spec --noconfirm

The result is ``dist/sigmahelix``: a single self-contained executable that
starts the GUI when run without arguments and behaves like the CLI otherwise.
"""

import os
import sys

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

# Paths in a spec are relative to the spec file, not the working directory.
REPO_ROOT = os.path.dirname(SPECPATH)
SRC_ROOT = os.path.join(REPO_ROOT, "src")
sys.path.insert(0, SRC_ROOT)

block_cipher = None

hiddenimports = [
    "sigmahelix.app.ui",
    "sigmahelix.app.console",
    "sigmahelix.cli",
    *collect_submodules("sigmahelix.core"),
    *collect_submodules("customtkinter"),
    *collect_submodules("keyring"),
]

datas = [
    *collect_data_files("customtkinter"),
    # Skills and the web assets are read at runtime, never imported.
    (os.path.join(SRC_ROOT, "sigmahelix", "skills"), "sigmahelix/skills"),
    (
        os.path.join(SRC_ROOT, "sigmahelix", "app", "webui", "static"),
        "sigmahelix/app/webui/static",
    ),
]

a = Analysis(
    [os.path.join(SRC_ROOT, "sigmahelix", "__main__.py")],
    pathex=[SRC_ROOT],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["pytest", "mypy", "ruff", "setuptools", "pip"],
    win_no_prefer_redirects=False,
    win_private_assemblies=False,
    cipher=block_cipher,
    noarchive=False,
)

pyz = PYZ(a.pure, a.zipped_data, cipher=block_cipher)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.zipfiles,
    a.datas,
    [],
    name="sigmahelix",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
)

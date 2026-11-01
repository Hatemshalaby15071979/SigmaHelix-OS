# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: SigmaHelix console agent (GUI runs from source or next version)
a = Analysis(
    ['console_os.py'],
    pathex=['apps/desktop'],
    hiddenimports=['speech_recognition', 'pyttsx3'],
    excludes=['tkinter', 'customtkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='sigmahelix', console=True, upx=True, strip=False,
)

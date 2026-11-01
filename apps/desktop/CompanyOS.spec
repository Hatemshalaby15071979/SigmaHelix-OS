# -*- mode: python ; coding: utf-8 -*-
# PyInstaller spec: single-file CompanyOS console agent (GUI runs from source or next version)
a = Analysis(
    ['console_os.py'],
    pathex=['/run/media/hatem/2A3AE01E311C617F/Career/company-os-app'],
    hiddenimports=['speech_recognition', 'pyttsx3'],
    excludes=['tkinter', 'customtkinter'],
    noarchive=False,
)
pyz = PYZ(a.pure, a.zipped_data, cipher=None)
exe = EXE(
    pyz, a.scripts, a.binaries, a.zipfiles, a.datas, [],
    name='CompanyOS', console=True, upx=True, strip=False,
)

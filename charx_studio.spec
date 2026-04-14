# -*- mode: python ; coding: utf-8 -*-
#
# PyInstaller spec for Persona Packager Studio.
# Build with:  python -m PyInstaller charx_studio.spec

from PyInstaller.utils.hooks import collect_data_files, collect_submodules

block_cipher = None

ctk_datas = collect_data_files('customtkinter')
try:
    dnd_datas = collect_data_files('tkinterdnd2')
except Exception:
    dnd_datas = []

a = Analysis(
    ['charx_studio.py'],
    pathex=[],
    binaries=[],
    datas=ctk_datas + dnd_datas + [
        ('assets', 'assets'),   # logo.ico bundled for runtime icon
    ],
    hiddenimports=(
        collect_submodules('customtkinter') +
        [
            'PIL._imagingtk',
            'PIL.ImageTk',
            'PIL.Image',
            'PIL.ImageDraw',
            'PIL.PngImagePlugin',
            'PIL.JpegImagePlugin',
            'tkinter',
            'tkinter.filedialog',
            'tkinter.messagebox',
            'tkinterdnd2',
        ]
    ),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[
        'numpy', 'scipy', 'matplotlib', 'pandas',
        'PyQt5', 'PyQt6', 'PySide2', 'PySide6',
        'IPython', 'jupyter', 'notebook',
    ],
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
    name='PersonaPackagerStudio',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon='assets/logo.ico',
)

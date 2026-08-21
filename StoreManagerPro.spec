# -*- mode: python ; coding: utf-8 -*-
"""Recette de construction du .exe StoreManager Pro.

    .venv\\Scripts\\python.exe -m PyInstaller StoreManagerPro.spec --noconfirm

Mode « onedir » volontairement : l'application démarre bien plus vite qu'en
« onefile » (pas de réextraction de 300 Mo à chaque lancement) et, en cas de
souci chez le client, on peut inspecter les fichiers livrés.
"""
from pathlib import Path

from PyInstaller.utils.hooks import collect_dynamic_libs, collect_submodules

# ── Bibliothèques natives que l'analyse ne trouve pas ────────────────────
# pyzbar charge libzbar-64.dll par chemin, à l'exécution : PyInstaller ne
# voit donc jamais cette dépendance. Sans elle l'application démarre
# normalement, et le scan de codes-barres échoue seulement une fois chez le
# client — au pire moment possible.
binaries = collect_dynamic_libs("pyzbar")
if not binaries:
    raise SystemExit(
        "Les DLL de pyzbar sont introuvables : le scan de codes-barres serait "
        "cassé dans le .exe. Vérifiez que pyzbar est installé dans le venv."
    )

# ── Ressources chargées à l'exécution ────────────────────────────────────
# Ces fichiers ne sont pas importés par Python : PyInstaller ne peut pas les
# deviner. Sans cette liste, l'application se lance puis échoue au premier
# écran (QUiLoader ne trouve pas le .ui) ou s'affiche sans aucun style.
datas = [
    ("app/ui/*.ui", "app/ui"),          # 32 formulaires chargés par QUiLoader
    ("assets/themes/*.qss", "assets/themes"),
    ("assets/icons", "assets/icons"),
]

# ── Imports que l'analyse statique ne voit pas ───────────────────────────
hiddenimports = [
    "pymysql",
    "pymysql.cursors",
    "bcrypt",
    # reportlab charge ses polices et codecs par nom, dynamiquement.
    *collect_submodules("reportlab.pdfbase"),
]

# ── Poids inutile : tout ce qui n'est jamais utilisé en caisse ───────────
excludes = [
    "tkinter",          # Qt fait l'interface
    "PySide6.QtQml",    # aucune interface QML
    "PySide6.QtQuick",
    "PySide6.Qt3DCore",
    "PySide6.QtWebEngineCore",
    "PySide6.QtWebEngineWidgets",
    "PySide6.QtMultimedia",
    "PySide6.QtCharts",
    "PySide6.QtDataVisualization",
    "PySide6.QtBluetooth",
    "PySide6.QtPositioning",
    "PySide6.QtSensors",
    "PySide6.QtSerialPort",
    "PySide6.QtTest",
    "PySide6.QtDesigner",
    "IPython",
    "jupyter",
    "pytest",
    "setuptools",
]

a = Analysis(
    ["main.py"],
    pathex=["."],
    binaries=binaries,
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    runtime_hooks=[],
    excludes=excludes,
    noarchive=False,
)

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    [],
    exclude_binaries=True,
    name="StoreManagerPro",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,          # UPX déclenche des faux positifs antivirus
    console=False,      # application graphique : pas de fenêtre noire
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=None,
)

coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    strip=False,
    upx=False,
    upx_exclude=[],
    name="StoreManagerPro",
)

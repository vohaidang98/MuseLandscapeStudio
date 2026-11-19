from pathlib import Path
from PyInstaller.utils.hooks import collect_data_files, collect_submodules

root = Path(SPECPATH).parent
data = [(str(file), 'agent') for file in (root / 'agent').glob('*.json')]
data += collect_data_files('muse2api')
data += [(str(root / 'dashboard/dist'), 'dashboard/dist'),
         (str(root / 'windows/assets/app-icon.ico'), '.'),
         (str(root / 'LICENSE'), '.'),
         (str(root / 'THIRD_PARTY_NOTICES.md'), '.'),
         (str(root / 'windows/ffmpeg-notices'), 'licenses/ffmpeg')]
data += [(str(root / 'windows/dependency-licenses'), 'licenses/dependencies')]
hidden = [
    'uvicorn.logging', 'uvicorn.loops.auto', 'uvicorn.protocols.http.auto',
    'uvicorn.protocols.websockets.auto', 'uvicorn.lifespan.on',
    'webview.platforms.edgechromium', 'webview.platforms.winforms',
]
hidden += collect_submodules('muse2api')
a = Analysis([str(root / 'windows/launcher.py')], pathex=[str(root)],
             binaries=[(str(root / 'windows/bin/ffmpeg.exe'), 'bin'),
                       (str(root / 'windows/bin/ffprobe.exe'), 'bin')],
             datas=data, hiddenimports=hidden,
             excludes=['pytest', 'IPython', 'torch', 'tensorflow', 'PyQt5', 'PyQt6', 'PySide6'])
pyz = PYZ(a.pure)
exe = EXE(pyz, a.scripts, [], exclude_binaries=True, name='MuseLandscapeStudio',
          debug=False, strip=False, upx=False, console=False, icon=str(root / 'windows/assets/app-icon.ico'))
coll = COLLECT(exe, a.binaries, a.datas, strip=False, upx=False, name='MuseLandscapeStudio')

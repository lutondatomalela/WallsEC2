# -*- mode: python ; coding: utf-8 -*-
# Build one-folder first: easier diagnosis, faster startup with SciPy.
from pathlib import Path
root=Path(SPECPATH)
a=Analysis([str(root/'WallsEC2.py')],pathex=[str(root)],binaries=[],
           datas=[(str(root/'assets'/'WallsEC2.png'),'assets'),(str(root/'assets'/'WallsEC2.ico'),'assets')],
           hiddenimports=['xlsxwriter','openpyxl','scipy.optimize','reportlab.pdfbase._fontdata'],
           hookspath=[],hooksconfig={},runtime_hooks=[],excludes=[],noarchive=False)
pyz=PYZ(a.pure)
exe=EXE(pyz,a.scripts,[],exclude_binaries=True,name='WallsEC2',debug=False,
        bootloader_ignore_signals=False,strip=False,upx=False,console=False,
        icon=str(root/'assets'/'WallsEC2.ico'))
coll=COLLECT(exe,a.binaries,a.datas,strip=False,upx=False,name='WallsEC2')

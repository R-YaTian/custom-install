@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x86 --vcvars_ver=14.16
set CCFLAGS=/nologo /D _USING_V110_SDK71_ /D _WIN32_WINNT=0x0503
set LDFLAGS=/nologo /subsystem:windows,"5.01"
call nuitka.cmd --standalone --windows-console-mode=disable --onefile --onefile-no-compression --msvc=14.3 --remove-output --enable-plugin=tk-inter --nofollow-import-to=PIL --nofollow-import-to=dbm --nofollow-import-to=distutils --nofollow-import-to=py_compile --nowarn-mnemonic=old-python-windows-console ci-gui.py
mkdir dist
move ci-gui.exe dist
copy TaskbarLib.dll dist
xcopy /Y /S /Q i18n dist\i18n\
del dist\i18n\template.pot
xcopy /Y /S /Q bin\win32\save3ds_fuse.exe dist\bin\win32\
copy title.db.gz dist
copy LICENSE.md dist
cd finalize && make
move custom-install-finalize.3dsx ..\dist\
cd ..\dist
python -m zipfile -c ci-gui.zip bin i18n ci-gui.exe LICENSE.md title.db.gz custom-install-finalize.3dsx TaskbarLib.dll

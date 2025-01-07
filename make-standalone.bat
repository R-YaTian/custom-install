@echo off
call "C:\Program Files\Microsoft Visual Studio\2022\Community\VC\Auxiliary\Build\vcvarsall.bat" x86 --vcvars_ver=14.16
set CCFLAGS=/nologo /D _USING_V110_SDK71_ /D _WIN32_WINNT=0x0503
set LDFLAGS=/nologo /subsystem:windows,"5.01"
call .venv\Scripts\activate.bat
call nuitka.cmd --standalone --windows-console-mode=disable --msvc=14.3 --remove-output --enable-plugin=tk-inter --nowarn-mnemonic=old-python-windows-console --windows-icon-from-ico=icon.ico ci-gui.py
rmdir /S /Q ci-gui.dist\tk\images
move ci-gui.dist dist
copy TaskbarLib.dll dist
xcopy /Y /S /Q i18n dist\i18n\
del dist\i18n\template.pot
xcopy /Y /S /Q bin\win32\save3ds_fuse.exe dist\bin\win32\
copy title.db.gz dist
copy LICENSE.md dist
copy icon.ico dist
cd finalize && make
move custom-install-finalize.3dsx ..\dist\
cd ..\dist
zip -r ../Custom-Install-GUI.zip .
pause

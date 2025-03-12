import sys
from cx_Freeze import setup, Executable

build_options = {
    "packages": [],
    "excludes": [],
    "include_files": [
        ("i18n", "i18n"),
        ("bin/win32/save3ds_fuse.exe", "bin/save3ds_fuse.exe"),
        ("finalize/custom-install-finalize.3dsx", "custom-install-finalize.3dsx"),
        ("icon.ico", "icon.ico"),
        ("LICENSE.md", "LICENSE.md"),
        ("title.db.gz", "title.db.gz")
    ]
}

if sys.platform == 'win32':
    executables = [
        Executable('ci-gui.py', target_name='custom-install-gui-console', icon='icon.ico'),
        Executable('ci-gui.py', target_name='custom-install-gui', base='Win32GUI', icon='icon.ico'),
    ]
else:
    executables = [
        Executable('ci-gui.py', target_name='custom-install-gui'),
    ]

setup(
    name = "custom-install-gui",
    version = "2.1c",
    description = "Installs a title directly to an SD card for the Nintendo 3DS",
    options={"build_exe": build_options},
    executables = executables
)

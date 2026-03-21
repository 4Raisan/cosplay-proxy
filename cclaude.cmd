@echo off
set "PATH=%LocalAppData%\CosplayPython;%LocalAppData%\CosplayPython\Scripts;%LocalAppData%\CosplayNode;%PATH%"
python "%~dp0cclaude.py" %*

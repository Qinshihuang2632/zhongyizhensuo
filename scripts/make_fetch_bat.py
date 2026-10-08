"""生成老电脑一键取数脚本（GBK 编码，兼容 XP/7/10 的命令行）。"""
import os

BAT = r'''@echo off
title 老诊所系统 一键取数工具
color 1F
echo ============================================================
echo    老诊所系统数据 一键取数工具
echo    请保持本U盘插在这台老电脑上，然后按任意键开始
echo    扫描可能需要几分钟，请耐心等待，不要关窗口
echo ============================================================
pause >nul
set "DEST=%~d0\取回数据"
md "%DEST%" >nul 2>&1
md "%DEST%\数据库文件" >nul 2>&1
set "LOG=%DEST%\取到了什么.txt"
echo 取数时间 %DATE% %TIME% > "%LOG%"
echo 开始扫描，请稍候……

rem —— 第一步：全盘搜索老系统的两个程序，把它们所在文件夹整个拷走 ——
for %%D in (C D E) do (
  if exist %%D:\nul (
    for /r %%D:\ %%f in (中医诊所服务器*.exe 中医诊所管理系统*.exe) do (
      echo 发现程序文件夹：%%~dpf
      echo 程序文件夹：%%~dpf >> "%LOG%"
      xcopy "%%~dpf" "%DEST%\程序文件夹\%%~nx?" /S /E /C /H /R /Y /I /D >nul 2>&1
    )
  )
)

rem —— 第二步：全盘搜索可能的数据库文件（Access/SQLite/DBase/备份） ——
for %%D in (C D E) do (
  if exist %%D:\nul (
    for /r %%D:\ %%f in (*.mdb *.sqlite *.db3 *.DBF *.bak) do (
      echo %%f | find /i "Windows" >nul
      if errorlevel 1 (
        echo 拷贝数据库文件：%%f
        echo 数据库文件：%%f >> "%LOG%"
        xcopy "%%f" "%DEST%\数据库文件\" /C /H /R /Y /D >nul 2>&1
      )
    )
  )
)

rem —— 第三步：桌面上如果有相关文件夹也整个拷走 ——
for %%D in ("%USERPROFILE%\桌面" "%ALLUSERSPROFILE%\桌面") do (
  if exist %%D (
    for /d %%f in (%%D\*中医*) do (
      echo 发现桌面相关文件夹：%%f
      echo 桌面文件夹：%%f >> "%LOG%"
      xcopy "%%f" "%DEST%\桌面文件夹\%%~nxf\" /S /E /C /H /R /Y /I /D >nul 2>&1
    )
  )
)

echo.
echo ============================================================
echo    取数完成！拷到U盘的内容清单见文件：
echo    %LOG%
echo    请安全拔出U盘，插到新电脑上，把「取回数据」整个文件夹
echo    发给开发者即可。
echo ============================================================
dir /s /b "%DEST%" >> "%LOG%"
pause
'''

dest = os.path.join("dist", "老电脑取数工具-插U盘双击.bat")
with open(dest, "w", encoding="gbk", newline="\r\n") as f:
    f.write(BAT)
print("生成:", dest, os.path.getsize(dest), "字节")

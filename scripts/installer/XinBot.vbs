' XinBot 启动器（无控制台窗口）
'
' 用 VBScript 而不是 .bat/.exe：
'   - .bat 会闪一个黑窗口，桌宠启动不该这样；
'   - .exe 需要编译，增加构建复杂度与杀软误报概率；
'   - VBScript 是 Windows 自带的，`Run ..., 0` 就是"隐藏窗口运行"。
'
' 它只负责启动，不做判断；真正的错误会写进 data\web.log 与进程日志。

Option Explicit

Dim shell, fso, root, command
Set shell = CreateObject("WScript.Shell")
Set fso = CreateObject("Scripting.FileSystemObject")

' 脚本所在目录 = 安装目录（快捷方式的工作目录也指向这里）
root = fso.GetParentFolderName(WScript.ScriptFullName)

command = "cmd /c cd /d """ & root & """ && uv run --frozen xinbot start pet"

' 0 = 隐藏窗口，False = 不等待退出
shell.Run command, 0, False

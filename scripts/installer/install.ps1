# XinBot 一键安装脚本
#
# 它做四件事：
#   1. 检查 Python 依赖管理工具 uv，缺了就装（官方安装脚本）
#   2. uv sync --frozen 安装本项目依赖（首次需要联网）
#   3. 生成无控制台窗口的启动器并创建桌面 / 开始菜单快捷方式
#   4. 可选立即启动
#
# 用法：
#   .\install.ps1              交互式安装
#   .\install.ps1 -Yes         全部确认（无人值守）
#   .\install.ps1 -NoShortcut  不创建快捷方式
#   .\install.ps1 -Launch      安装完立刻启动桌宠
#
# 不需要管理员权限：uv 装在用户目录，快捷方式建在用户桌面。

[CmdletBinding()]
param(
    [switch]$Yes,
    [switch]$NoShortcut,
    [switch]$Launch
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
Set-Location -LiteralPath $Root

function Write-Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }
function Write-Ok($text)   { Write-Host "    $text" -ForegroundColor Green }
function Write-Warn2($text){ Write-Host "    $text" -ForegroundColor Yellow }

function Confirm-Action($question) {
    if ($Yes) { return $true }
    $answer = Read-Host "$question [Y/n]"
    return ($answer -eq '' -or $answer -match '^[Yy]')
}

Write-Step "XinBot 安装程序"
Write-Host "    安装目录：$Root"

# ── 1. uv ────────────────────────────────────────────────────────
$uv = Get-Command uv -ErrorAction SilentlyContinue
if (-not $uv) {
    Write-Step "未检测到 uv（Python 依赖管理工具）"
    Write-Warn2 "将从 https://astral.sh/uv 下载安装（约 10 MB，装到用户目录，无需管理员权限）"
    if (-not (Confirm-Action "是否现在安装 uv？")) {
        Write-Host "已取消。你也可以手动安装后重新运行本脚本：https://docs.astral.sh/uv/" -ForegroundColor Yellow
        exit 1
    }
    try {
        Invoke-RestMethod -Uri 'https://astral.sh/uv/install.ps1' | Invoke-Expression
    } catch {
        Write-Host "uv 安装失败：$($_.Exception.Message)" -ForegroundColor Red
        Write-Host "请手动安装后重试：https://docs.astral.sh/uv/getting-started/installation/" -ForegroundColor Yellow
        exit 1
    }
    # 安装脚本把 uv 放进用户目录，当前会话的 PATH 还看不到它
    $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
    $uv = Get-Command uv -ErrorAction SilentlyContinue
    if (-not $uv) {
        Write-Host "uv 已安装，但当前终端尚未识别。请关掉本窗口重新打开后再次运行 install.ps1。" -ForegroundColor Yellow
        exit 1
    }
}
Write-Ok "uv: $((& uv --version) 2>&1)"

# ── 2. 依赖 ──────────────────────────────────────────────────────
Write-Step "安装项目依赖（首次需要联网，可能耗时几分钟）"
& uv sync --frozen
if ($LASTEXITCODE -ne 0) {
    Write-Host "依赖安装失败。若网络受限，可设置镜像后重试。" -ForegroundColor Red
    exit 1
}
Write-Ok "依赖已就绪"

# 桌面常驻桌宠需要额外依赖；装不上不影响网页 / 终端形态
Write-Step "安装桌宠窗口依赖（可选）"
& uv sync --frozen --extra desktop
if ($LASTEXITCODE -ne 0) {
    Write-Warn2 "桌宠窗口依赖安装失败，网页端与终端端仍可正常使用"
} else {
    Write-Ok "桌宠窗口依赖已就绪"
}

# ── 3. 启动器与快捷方式 ──────────────────────────────────────────
$launcher = Join-Path $Root 'XinBot.vbs'
if (-not (Test-Path $launcher)) {
    Write-Warn2 "缺少 XinBot.vbs，跳过快捷方式创建"
} elseif (-not $NoShortcut) {
    Write-Step "创建快捷方式"
    $shell = New-Object -ComObject WScript.Shell
    $targets = @(
        [System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'XinBot 桌宠.lnk'),
        [System.IO.Path]::Combine([Environment]::GetFolderPath('Programs'), 'XinBot 桌宠.lnk')
    )
    foreach ($shortcutPath in $targets) {
        try {
            $shortcut = $shell.CreateShortcut($shortcutPath)
            $shortcut.TargetPath = 'wscript.exe'
            $shortcut.Arguments = "`"$launcher`""
            $shortcut.WorkingDirectory = $Root
            $shortcut.Description = 'XinBot 桌面常驻桌宠'
            $shortcut.Save()
            Write-Ok $shortcutPath
        } catch {
            Write-Warn2 "创建快捷方式失败：$shortcutPath"
        }
    }
}

# ── 4. 完成 ──────────────────────────────────────────────────────
Write-Step "安装完成"
Write-Host @"
    双击桌面上的「XinBot 桌宠」即可启动
    或在本目录运行：uv run xinbot start pet

    网页界面：uv run xinbot start web
    终端界面：uv run xinbot start cli
    查看状态：uv run xinbot start --show
    卸载：    .\uninstall.ps1
"@ -ForegroundColor Gray

if ($Launch) {
    Write-Step "启动桌宠"
    Start-Process -FilePath 'wscript.exe' -ArgumentList "`"$launcher`"" -WorkingDirectory $Root
}

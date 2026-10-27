# XinBot 卸载脚本
#
# 默认只删除快捷方式与开机自启项，**保留你的数据**（对话、角色、外观）。
# 加 -Purge 才会连数据一起删——这是不可恢复的，会二次确认。
#
# 用法：
#   .\uninstall.ps1            删除快捷方式与自启项
#   .\uninstall.ps1 -Purge     连同 data/ 、pet/ 、.env 一起删除
#   .\uninstall.ps1 -Purge -Yes 跳过确认

[CmdletBinding()]
param(
    [switch]$Purge,
    [switch]$Yes
)

$ErrorActionPreference = 'Stop'
$Root = $PSScriptRoot
Set-Location -LiteralPath $Root

function Write-Step($text) { Write-Host "==> $text" -ForegroundColor Cyan }

function Confirm-Action($question) {
    if ($Yes) { return $true }
    $answer = Read-Host "$question [y/N]"
    return ($answer -match '^[Yy]')
}

Write-Step "移除快捷方式"
$shell = New-Object -ComObject WScript.Shell
$shortcuts = @(
    [System.IO.Path]::Combine([Environment]::GetFolderPath('Desktop'), 'XinBot 桌宠.lnk'),
    [System.IO.Path]::Combine([Environment]::GetFolderPath('Programs'), 'XinBot 桌宠.lnk')
)
foreach ($path in $shortcuts) {
    if (Test-Path -LiteralPath $path) {
        Remove-Item -LiteralPath $path -Force
        Write-Host "    已删除 $path" -ForegroundColor Green
    }
}

Write-Step "移除开机自启"
try {
    $key = 'HKCU:\Software\Microsoft\Windows\CurrentVersion\Run'
    if (Get-ItemProperty -Path $key -Name 'XinBotDesktopPet' -ErrorAction SilentlyContinue) {
        Remove-ItemProperty -Path $key -Name 'XinBotDesktopPet'
        Write-Host "    已移除开机自启项" -ForegroundColor Green
    } else {
        Write-Host "    开机自启本来就没开"
    }
} catch {
    Write-Host "    移除自启项失败（可手工在任务管理器的「启动」里关闭）" -ForegroundColor Yellow
}

if ($Purge) {
    Write-Host ""
    Write-Host "警告：-Purge 会删除以下内容，且无法恢复：" -ForegroundColor Red
    Write-Host "    data\   （对话记忆、配置、日志）" -ForegroundColor Red
    Write-Host "    pet\    （导入的外观模型）" -ForegroundColor Red
    Write-Host "    .env    （API 密钥）" -ForegroundColor Red
    if (-not (Confirm-Action "确定要继续吗？")) {
        Write-Host "已取消数据删除，其余清理已完成。" -ForegroundColor Yellow
        exit 0
    }
    foreach ($name in @('data', 'pet')) {
        $target = Join-Path $Root $name
        if (Test-Path -LiteralPath $target) {
            Remove-Item -LiteralPath $target -Recurse -Force
            Write-Host "    已删除 $name\" -ForegroundColor Green
        }
    }
    $envFile = Join-Path $Root '.env'
    if (Test-Path -LiteralPath $envFile) {
        Remove-Item -LiteralPath $envFile -Force
        Write-Host "    已删除 .env" -ForegroundColor Green
    }
    Write-Host "    依赖目录 .venv\ 仍在；如需要可手动删除" -ForegroundColor Gray
} else {
    Write-Host ""
    Write-Host "你的数据已保留（data\ 、pet\ 、.env）。" -ForegroundColor Gray
    Write-Host "要一并删除请运行：.\uninstall.ps1 -Purge" -ForegroundColor Gray
}

Write-Step "卸载完成"

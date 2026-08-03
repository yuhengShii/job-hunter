<#
.SYNOPSIS
    一键启动 job-hunter（前端 + 后端）。

.DESCRIPTION
    默认生产模式：frontend/dist 缺失时自动构建，由后端单端口托管
    （http://127.0.0.1:8000，含前端页面与 API）。

    加 -Dev 参数：开发模式，同时启动后端（8000）与 Vite dev server
    （5173，热更新，/api 代理到 8000）。按 Ctrl+C 退出时后端一并停止。

.PARAMETER Dev
    开发模式：Vite dev server + 后端两个进程。

.PARAMETER Rebuild
    生产模式下强制重新构建前端（默认仅在 dist/index.html 缺失时构建）。
#>
param(
    [switch]$Dev,
    [switch]$Rebuild
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$frontend = Join-Path $root "frontend"
$distIndex = Join-Path $frontend "dist\index.html"
$logDir = Join-Path $env:TEMP "job-hunter"

function Test-PortBusy([int]$port) {
    return [bool](Get-NetTCPConnection -LocalPort $port -State Listen -ErrorAction SilentlyContinue)
}

function Write-Step([string]$msg) {
    Write-Host "==> $msg" -ForegroundColor Cyan
}

function Get-Executable([string]$name) {
    $cmd = Get-Command $name -ErrorAction SilentlyContinue
    if (-not $cmd) {
        Write-Host "缺少依赖：$name 未找到。请先安装（uv: https://docs.astral.sh/uv/；Node: https://nodejs.org/）" -ForegroundColor Red
        exit 1
    }
    return $cmd.Source
}

if (Test-PortBusy 8000) {
    Write-Host "端口 8000 已被占用——job-hunter 后端可能已在运行，请先停止现有进程。" -ForegroundColor Yellow
    exit 1
}

$uv = Get-Executable "uv"
$npm = Get-Executable "npm"

if ($Dev) {
    if (Test-PortBusy 5173) {
        Write-Host "端口 5173 已被占用——Vite dev server 可能已在运行，请先停止。" -ForegroundColor Yellow
        exit 1
    }
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $out = Join-Path $logDir "uvicorn.out.log"
    $err = Join-Path $logDir "uvicorn.err.log"
    $env:PYTHONUTF8 = "1"

    Write-Step "启动后端 (http://127.0.0.1:8000)，日志：$out / $err"
    $backend = Start-Process -FilePath $uv -ArgumentList "run", "uvicorn", "backend.app.main:app" -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru

    try {
        $ready = $false
        for ($i = 0; $i -lt 40; $i++) {
            Start-Sleep -Milliseconds 500
            if (Test-PortBusy 8000) { $ready = $true; break }
        }
        if (-not $ready) {
            Write-Host "后端启动失败，错误日志：$err" -ForegroundColor Red
            Get-Content $err -Tail 20 -ErrorAction SilentlyContinue
            exit 1
        }
        Write-Step "后端就绪；启动 Vite dev server (http://localhost:5173)，Ctrl+C 一并停止"
        Push-Location $frontend
        try {
            & $npm run dev
        }
        finally {
            Pop-Location
        }
    }
    finally {
        Write-Step "停止后端 (PID $($backend.Id))"
        Stop-Process -Id $backend.Id -Force -ErrorAction SilentlyContinue
    }
}
else {
    if ($Rebuild -or -not (Test-Path $distIndex)) {
        Write-Step "构建前端（npm run build）"
        Push-Location $frontend
        try {
            & $npm run build
        }
        finally {
            Pop-Location
        }
    }

    $env:PYTHONUTF8 = "1"
    Write-Step "启动 job-hunter（生产模式）：http://127.0.0.1:8000 （账号见 data/config.ini），Ctrl+C 停止"
    Push-Location $root
    try {
        & $uv run uvicorn backend.app.main:app
    }
    finally {
        Pop-Location
    }
}

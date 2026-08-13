<#
.SYNOPSIS
    一键启动 job-hunter（前端 + 后端）。

.DESCRIPTION
    默认生产模式：frontend/dist 缺失时自动构建，由后端单端口托管
    （http://127.0.0.1:8000，含前端页面与 API）。Ctrl+C 停止，退出时
    自动清理后端进程树（不再残留孤儿 uvicorn）。

    加 -Dev 参数：开发模式，同时启动后端（8000）与 Vite dev server
    （5173，热更新，/api 代理到 8000）。按 Ctrl+C 退出时一并停止。

    加 -Stop 参数：清理残留的 job-hunter 进程（兜底，进程被强杀后使用）。

.PARAMETER Dev
    开发模式：Vite dev server + 后端两个进程。

.PARAMETER Rebuild
    生产模式下强制重新构建前端（默认仅在 dist/index.html 缺失时构建）。

.PARAMETER Stop
    清理模式：结束所有 job-hunter 相关进程（uvicorn/start.ps1 包装/vite）。
#>
param(
    [switch]$Dev,
    [switch]$Rebuild,
    [switch]$Stop
)

$ErrorActionPreference = "Stop"
$root = $PSScriptRoot
$frontend = Join-Path $root "frontend"
$distIndex = Join-Path $frontend "dist\index.html"
$logDir = Join-Path $env:TEMP "job-hunter"
$venvUvicorn = Join-Path $root ".venv\Scripts\uvicorn.exe"

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

function Get-Descendants([int]$parentId) {
    $all = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue
    $result = New-Object System.Collections.Generic.List[int]
    $queue = New-Object System.Collections.Generic.Queue[int]
    $queue.Enqueue($parentId)
    while ($queue.Count -gt 0) {
        $cur = $queue.Dequeue()
        foreach ($p in $all) {
            if ($p.ParentProcessId -eq $cur) {
                $result.Add($p.ProcessId)
                $queue.Enqueue($p.ProcessId)
            }
        }
    }
    return $result
}

function Stop-ProcessTree([int]$rootPid) {
    $ids = @(Get-Descendants $rootPid) + @($rootPid)
    foreach ($id in $ids) {
        Stop-Process -Id $id -Force -ErrorAction SilentlyContinue
    }
}

# --- 清理模式 ---
if ($Stop) {
    $pattern = 'backend\.app\.main|start\.ps1|vite'
    $targets = Get-CimInstance Win32_Process -ErrorAction SilentlyContinue | Where-Object {
        $_.ProcessId -ne $PID -and $_.CommandLine -match $pattern
    }
    if (-not $targets) {
        Write-Host "没有发现 job-hunter 相关进程" -ForegroundColor Green
        exit 0
    }
    foreach ($t in $targets) {
        Write-Step "清理 PID $($t.ProcessId) $($t.Name)（及其子进程）"
        Stop-ProcessTree $t.ProcessId
    }
    Write-Host "清理完成" -ForegroundColor Green
    exit 0
}

if (Test-PortBusy 8000) {
    Write-Host "端口 8000 已被占用——job-hunter 后端可能已在运行。可先执行 .\start.ps1 -Stop 清理。" -ForegroundColor Yellow
    exit 1
}

$uv = Get-Executable "uv"
$npm = Get-Executable "npm"

# 优先直接调用 venv 内的 uvicorn.exe（单进程，避免 uv 包装层导致孤儿进程）
if (Test-Path $venvUvicorn) {
    $backendExe = $venvUvicorn
    $backendArgs = @("backend.app.main:app", "--host", "0.0.0.0")
}
else {
    $backendExe = $uv
    $backendArgs = @("run", "uvicorn", "backend.app.main:app", "--host", "0.0.0.0")
}

if ($Dev) {
    if (Test-PortBusy 5173) {
        Write-Host "端口 5173 已被占用——Vite dev server 可能已在运行。可先执行 .\start.ps1 -Stop 清理。" -ForegroundColor Yellow
        exit 1
    }
    New-Item -ItemType Directory -Path $logDir -Force | Out-Null
    $out = Join-Path $logDir "uvicorn.out.log"
    $err = Join-Path $logDir "uvicorn.err.log"
    $env:PYTHONUTF8 = "1"

    Write-Step "启动后端 (http://0.0.0.0:8000，局域网可访问)，日志：$out / $err"
    $backend = Start-Process -FilePath $backendExe -ArgumentList $backendArgs -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput $out -RedirectStandardError $err -PassThru

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
        Write-Step "停止后端 (PID $($backend.Id) 及子进程)"
        Stop-ProcessTree $backend.Id
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
    Write-Step "启动 job-hunter（生产模式）：http://0.0.0.0:8000 （局域网设备用 http://<本机IP>:8000 访问，账号见 data/config.ini），Ctrl+C 停止"
    $backend = Start-Process -FilePath $backendExe -ArgumentList $backendArgs -WorkingDirectory $root -PassThru
    try {
        Wait-Process -Id $backend.Id
    }
    finally {
        Write-Step "停止后端 (PID $($backend.Id) 及子进程)"
        Stop-ProcessTree $backend.Id
    }
}

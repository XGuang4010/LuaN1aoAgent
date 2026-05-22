#requires -Version 5.1
<#
.SYNOPSIS
    LuaN1ao Agent Windows 进程守护脚本

.DESCRIPTION
    在循环中运行 python agent.py，当进程异常退出时自动重启，
    最多尝试 5 次后放弃。重启记录写入日志文件。

.EXAMPLE
    .\supervise-agent.ps1 -Goal "测试 http://example.com" -TaskName "pentest_example"

.EXAMPLE
    .\supervise-agent.ps1 -Goal "测试 http://example.com" -TaskName "pentest_example" -ExtraArgs "--output-mode simple"

.PARAMETER Goal
    渗透测试目标（对应 agent.py --goal）

.PARAMETER TaskName
    任务名称（对应 agent.py --task-name）

.PARAMETER ExtraArgs
    传递给 agent.py 的额外参数，例如 "--output-mode simple --web"

.PARAMETER Python
    Python 解释器路径，默认使用环境中的 python

.PARAMETER MaxRestarts
    最大重启次数，默认 5
#>
param(
    [Parameter(Mandatory = $true)]
    [string]$Goal,

    [Parameter(Mandatory = $true)]
    [string]$TaskName,

    [string]$ExtraArgs = "",

    [string]$Python = "python",

    [int]$MaxRestarts = 5
)

$scriptDir = Split-Path -Parent $MyInvocation.MyCommand.Definition
$projectDir = Split-Path -Parent $scriptDir
$logDir = Join-Path $projectDir "logs"
$superviseLog = Join-Path $logDir "supervise-agent.log"

# 确保日志目录存在
New-Item -ItemType Directory -Force -Path $logDir | Out-Null

function Write-Log {
    param([string]$Message)
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] $Message"
    Write-Host $line
    Add-Content -Path $superviseLog -Value $line -Encoding UTF8
}

Write-Log "========================================"
Write-Log "LuaN1ao Agent Supervisor 启动"
Write-Log "目标: $Goal"
Write-Log "任务: $TaskName"
Write-Log "工作目录: $projectDir"
Write-Log "最大重启次数: $MaxRestarts"
Write-Log "========================================"

$restartCount = 0
$agentArgs = @("agent.py", "--goal", $Goal, "--task-name", $TaskName)
if ($ExtraArgs) {
    $agentArgs += $ExtraArgs -split '\s+'
}

while ($restartCount -le $MaxRestarts) {
    $restartCount++
    Write-Log "第 $restartCount 次启动 Agent..."

    $proc = $null
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $Python
        $psi.Arguments = ($agentArgs | ForEach-Object { '"{0}"' -f $_ }) -join ' '
        $psi.WorkingDirectory = $projectDir
        $psi.UseShellExecute = $false
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.StandardOutputEncoding = [System.Text.Encoding]::UTF8
        $psi.StandardErrorEncoding = [System.Text.Encoding]::UTF8

        $proc = [System.Diagnostics.Process]::Start($psi)

        # 实时输出 stdout/stderr
        $stdoutTask = $proc.StandardOutput.ReadToEndAsync()
        $stderrTask = $proc.StandardError.ReadToEndAsync()

        # 等待进程结束
        $proc.WaitForExit()

        $stdout = $stdoutTask.Result
        $stderr = $stderrTask.Result

        if ($stdout) {
            Write-Log "STDOUT:`n$stdout"
        }
        if ($stderr) {
            Write-Log "STDERR:`n$stderr"
        }

        $exitCode = $proc.ExitCode
        Write-Log "Agent 退出，退出码: $exitCode"

        # 退出码 0 视为正常结束，不再重启
        if ($exitCode -eq 0) {
            Write-Log "Agent 正常结束，守护进程退出。"
            break
        }
    }
    catch {
        Write-Log "启动 Agent 时发生异常: $_"
    }
    finally {
        if ($proc -and -not $proc.HasExited) {
            $proc.Kill()
        }
    }

    if ($restartCount -gt $MaxRestarts) {
        Write-Log "已达到最大重启次数 ($MaxRestarts)，放弃重启。"
        break
    }

    $delay = 5
    Write-Log "$delay 秒后尝试重启..."
    Start-Sleep -Seconds $delay
}

Write-Log "Supervisor 结束，共尝试 $restartCount 次。"

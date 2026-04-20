param(
    [switch]$Restart
)

$ErrorActionPreference = "Stop"

$ProjectRoot = Split-Path -Parent $MyInvocation.MyCommand.Path
$FastApiPort = 8000
$StreamlitPort = 8501
$FastApiUrl = "http://127.0.0.1:$FastApiPort/docs"
$StreamlitUrl = "http://localhost:$StreamlitPort"

function Get-PortOwnerIds {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    $connections = @(Get-NetTCPConnection -LocalPort $Port -State Listen -ErrorAction SilentlyContinue)
    return @($connections | Select-Object -ExpandProperty OwningProcess -Unique)
}

function Test-PortListening {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port
    )

    return @(Get-PortOwnerIds -Port $Port).Count -gt 0
}

function Stop-PortOwners {
    param(
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$Name
    )

    $ownerIds = @(Get-PortOwnerIds -Port $Port)
    if ($ownerIds.Count -eq 0) {
        Write-Host "$Name is not running on port $Port."
        return
    }

    foreach ($ownerId in $ownerIds) {
        $process = Get-Process -Id $ownerId -ErrorAction SilentlyContinue
        if ($null -eq $process) {
            continue
        }

        Write-Host "Stopping $Name on port $Port (PID $($process.Id), $($process.ProcessName))."
        Stop-Process -Id $process.Id -Force -ErrorAction Stop
    }

    Start-Sleep -Seconds 2
}

function Start-ServiceIfNeeded {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [Parameter(Mandatory = $true)]
        [string]$Command
    )

    if (Test-PortListening -Port $Port) {
        Write-Host "$Name is already running on port $Port."
        return $false
    }

    Write-Host "Starting $Name on port $Port..."
    Start-Process powershell -ArgumentList "-NoExit", "-Command", $Command | Out-Null
    return $true
}

function Wait-PortListening {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [int]$Port,
        [int]$TimeoutSeconds = 25
    )

    $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
    while ((Get-Date) -lt $deadline) {
        if (Test-PortListening -Port $Port) {
            Write-Host "$Name is listening on port $Port."
            return $true
        }

        Start-Sleep -Milliseconds 500
    }

    Write-Warning "$Name did not start listening on port $Port within $TimeoutSeconds seconds. Check its PowerShell window for details."
    return $false
}

function Open-AppUrl {
    param(
        [Parameter(Mandatory = $true)]
        [string]$Name,
        [Parameter(Mandatory = $true)]
        [string]$Url
    )

    Write-Host "Opening ${Name}: $Url"
    Start-Process $Url | Out-Null
}

$escapedProjectRoot = $ProjectRoot.Replace("'", "''")
$fastApiCommand = "Set-Location -LiteralPath '$escapedProjectRoot'; conda run -n compute uvicorn api:app --reload --port $FastApiPort"
$streamlitCommand = "Set-Location -LiteralPath '$escapedProjectRoot'; conda run -n compute streamlit run app.py --server.port $StreamlitPort --server.headless true"

Write-Host "Travel Planner project: $ProjectRoot"
Write-Host ""

if ($Restart) {
    Write-Host "Restart requested. Stopping services that own the app ports."
    Stop-PortOwners -Port $FastApiPort -Name "FastAPI"
    Stop-PortOwners -Port $StreamlitPort -Name "Streamlit"
    Write-Host ""
}

$fastApiStarted = Start-ServiceIfNeeded -Name "FastAPI" -Port $FastApiPort -Command $fastApiCommand
$streamlitStarted = Start-ServiceIfNeeded -Name "Streamlit" -Port $StreamlitPort -Command $streamlitCommand

if ($fastApiStarted) {
    Wait-PortListening -Name "FastAPI" -Port $FastApiPort | Out-Null
}

if ($streamlitStarted) {
    Wait-PortListening -Name "Streamlit" -Port $StreamlitPort | Out-Null
}

Write-Host ""
Open-AppUrl -Name "Streamlit UI" -Url $StreamlitUrl
Write-Host ""
Write-Host "FastAPI docs are available at $FastApiUrl"
Write-Host "Use .\run_apps.ps1 -Restart for a full server restart."

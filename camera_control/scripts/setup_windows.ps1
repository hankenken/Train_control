# User-invoked setup for Windows 10 x64. No administrator rights are required.
# Uses an existing x64 Python; never downloads an installer or changes policy.
[CmdletBinding()]
param(
    [string]$VenvPath = "",
    [switch]$CheckOnly
)

$ErrorActionPreference = 'Stop'
$ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot '..\..')).Path
if ([string]::IsNullOrWhiteSpace($VenvPath)) {
    $VenvPath = Join-Path $ProjectRoot '.venv-camera'
}
$VenvPath = [System.IO.Path]::GetFullPath($VenvPath)
$RequirementsPath = Join-Path $ProjectRoot 'camera_control\requirements-windows.txt'

# All platform/Python checks precede venv creation or package installation.
if ($env:OS -ne 'Windows_NT' -or -not [Environment]::Is64BitOperatingSystem) {
    throw 'Windows 10 x64 is required. Nothing was installed.'
}
$OperatingSystem = Get-CimInstance -ClassName Win32_OperatingSystem
$BuildNumber = [int]$OperatingSystem.BuildNumber
if ($OperatingSystem.Caption -notmatch 'Windows 10' -or $BuildNumber -lt 10240 -or $BuildNumber -ge 22000) {
    throw "This setup targets Windows 10 x64; detected: $($OperatingSystem.Caption), build $BuildNumber. Nothing was installed."
}

$ProbeCode = 'import json,struct,sys; print(json.dumps({"executable":sys.executable,"version":list(sys.version_info[:3]),"bits":struct.calcsize("P")*8}))'
$Candidates = @()
$Launcher = Get-Command py -ErrorAction SilentlyContinue
if ($Launcher -and $Launcher.Source -notmatch '\\Microsoft\\WindowsApps\\') {
    $Candidates += @{ Exe = $Launcher.Source; Prefix = @('-3.12') }
}
$PythonCommand = Get-Command python -ErrorAction SilentlyContinue
if ($PythonCommand -and $PythonCommand.Source -notmatch '\\Microsoft\\WindowsApps\\') {
    $Candidates += @{ Exe = $PythonCommand.Source; Prefix = @() }
}
$PythonInfo = $null
foreach ($Candidate in $Candidates) {
    try {
        $Prefix = @($Candidate.Prefix)
        $Result = & $Candidate.Exe @Prefix -c $ProbeCode 2>$null
        if ($LASTEXITCODE -ne 0) { continue }
        $Info = ($Result -join "`n") | ConvertFrom-Json
        if ($Info.bits -eq 64 -and $Info.version[0] -eq 3 -and $Info.version[1] -ge 10 -and $Info.version[1] -le 12 -and (Test-Path -LiteralPath $Info.executable -PathType Leaf)) {
            $PythonInfo = $Info
            break
        }
    } catch {
        # Try the next existing interpreter. Do not launch a Store installer.
        continue
    }
}
if ($null -eq $PythonInfo) {
    throw 'Install Python 3.12 x64 from python.org first (3.10-3.12 x64 accepted). Existing py -3.12 and python were checked. No installer was downloaded and nothing was installed.'
}
if (-not (Test-Path -LiteralPath $RequirementsPath -PathType Leaf)) {
    throw "Requirements file is missing: $RequirementsPath. Nothing was installed."
}
$PythonPath = [string]$PythonInfo.executable
Write-Host "OS: $($OperatingSystem.Caption), build $BuildNumber, x64"
Write-Host "Python: $PythonPath ($($PythonInfo.version -join '.')), x64"
Write-Host 'Board model is not automatically verified; confirm LattePanda 3 Delta 864 manually.'
if ($CheckOnly) {
    Write-Host 'Checks passed. No environment or packages were created.'
    exit 0
}

$VenvPython = Join-Path $VenvPath 'Scripts\python.exe'
if ((Test-Path -LiteralPath $VenvPath) -and -not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    throw "The destination exists but is not a Windows virtual environment: $VenvPath. Use -VenvPath with a new directory; existing files were preserved."
}
if (-not (Test-Path -LiteralPath $VenvPython -PathType Leaf)) {
    & $PythonPath -m venv $VenvPath
    if ($LASTEXITCODE -ne 0) { throw 'Virtual environment creation failed.' }
}
$VenvCheck = & $VenvPython -c $ProbeCode
if ($LASTEXITCODE -ne 0) { throw 'The virtual environment Python could not be started.' }
$VenvInfo = ($VenvCheck -join "`n") | ConvertFrom-Json
if ($VenvInfo.bits -ne 64 -or $VenvInfo.version[0] -ne 3 -or $VenvInfo.version[1] -lt 10 -or $VenvInfo.version[1] -gt 12) {
    throw 'The existing virtual environment must use Python 3.10-3.12 x64. Choose a new -VenvPath.'
}
& $VenvPython -m pip install -r $RequirementsPath
if ($LASTEXITCODE -ne 0) { throw 'Package installation failed; see the pip error above.' }
& $VenvPython -c 'import cv2,numpy,fastapi,uvicorn; print("Dependencies available. No camera, GPIO, serial connection, or Arduino firmware was started.")'
if ($LASTEXITCODE -ne 0) { throw 'Dependency import check failed.' }
Write-Host ''
Write-Host "Setup complete: $VenvPython"
Write-Host 'No service, startup task, firmware update, reboot, or permanent execution-policy change was made.'
Write-Host "Next: & `"$VenvPython`" camera_control\scripts\check_usb_cameras.py"

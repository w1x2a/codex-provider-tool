param(
    [switch]$SkipZip
)

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
$distRoot = Join-Path $root "dist"
$packageName = "CodexProviderTool-windows-x64"
$packageDir = Join-Path $distRoot $packageName
$zipPath = Join-Path $distRoot "$packageName.zip"
$buildRoot = Join-Path $root "build\codex-provider-tool"
$stagingDir = Join-Path $buildRoot "release\$packageName"

$resolvedRoot = [System.IO.Path]::GetFullPath($root).TrimEnd('\') + '\'
$resolvedPackage = [System.IO.Path]::GetFullPath($packageDir).TrimEnd('\') + '\'
$resolvedStaging = [System.IO.Path]::GetFullPath($stagingDir).TrimEnd('\') + '\'
foreach ($candidatePath in @($resolvedPackage, $resolvedStaging)) {
    if (-not $candidatePath.StartsWith($resolvedRoot, [System.StringComparison]::OrdinalIgnoreCase)) {
        throw "Refusing to clean a package path outside the workspace: $candidatePath"
    }
}

$python = $null
$venvPython = Join-Path $root ".venv\Scripts\python.exe"
$pythonCandidates = @($venvPython, "python")
foreach ($candidate in $pythonCandidates) {
    if ($candidate -ne "python" -and -not (Test-Path -LiteralPath $candidate -PathType Leaf)) {
        continue
    }
    $available = $false
    try {
        & $candidate -m PyInstaller --version *> $null
        $available = ($LASTEXITCODE -eq 0)
    } catch {
        $available = $false
    }
    if ($available) {
        $python = $candidate
        break
    }
}
if (-not $python) {
    throw "PyInstaller is not available. Install it with: python -m pip install pyinstaller"
}

New-Item -ItemType Directory -Force -Path $distRoot,$buildRoot | Out-Null
if (Test-Path -LiteralPath $stagingDir) {
    Remove-Item -LiteralPath $stagingDir -Recurse -Force
}
if (Test-Path -LiteralPath $zipPath) {
    Remove-Item -LiteralPath $zipPath -Force
}

& $python -m PyInstaller `
    --noconfirm `
    --clean `
    --onefile `
    --console `
    --name CodexProviderTool `
    --distpath $stagingDir `
    --workpath $buildRoot `
    --specpath $buildRoot `
    (Join-Path $PSScriptRoot "codex_provider_gui.py")
if ($LASTEXITCODE -ne 0) {
    throw "PyInstaller failed with exit code $LASTEXITCODE"
}

Copy-Item -LiteralPath (Join-Path $PSScriptRoot "CodexProviderTool-package.ps1") -Destination (Join-Path $stagingDir "CodexProviderTool.ps1")
Copy-Item -LiteralPath (Join-Path $PSScriptRoot "CODEX-PROVIDER-TOOL-PACKAGE-README.md") -Destination (Join-Path $stagingDir "README.md")

$hash = Get-FileHash -LiteralPath (Join-Path $stagingDir "CodexProviderTool.exe") -Algorithm SHA256
"$($hash.Hash)  CodexProviderTool.exe" | Set-Content -LiteralPath (Join-Path $stagingDir "SHA256SUMS.txt") -Encoding ASCII
Copy-Item -LiteralPath (Join-Path $stagingDir "SHA256SUMS.txt") -Destination (Join-Path $distRoot "SHA256SUMS.txt") -Force

if (-not $SkipZip) {
    Compress-Archive -Path (Join-Path $stagingDir "*") -DestinationPath $zipPath -CompressionLevel Optimal
}

$packageExe = Join-Path $packageDir "CodexProviderTool.exe"
$packageInUse = @(Get-Process CodexProviderTool -ErrorAction SilentlyContinue | Where-Object { $_.Path -eq $packageExe }).Count -gt 0
if ($packageInUse) {
    Write-Warning "The existing package EXE is running, so the unpacked directory was not replaced. The ZIP is current."
} else {
    if (Test-Path -LiteralPath $packageDir) {
        Remove-Item -LiteralPath $packageDir -Recurse -Force
    }
    New-Item -ItemType Directory -Force -Path $packageDir | Out-Null
    Copy-Item -Path (Join-Path $stagingDir "*") -Destination $packageDir -Recurse -Force
}

Write-Output "Staged package:    $stagingDir"
Write-Output "Package directory: $packageDir"
if (-not $SkipZip) {
    Write-Output "ZIP package:       $zipPath"
}

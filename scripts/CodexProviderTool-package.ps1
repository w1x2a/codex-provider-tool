param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$exe = Join-Path $PSScriptRoot "CodexProviderTool.exe"

if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "CodexProviderTool.exe was not found beside this script."
}

& $exe @Arguments
exit $LASTEXITCODE

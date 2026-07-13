param(
    [Parameter(ValueFromRemainingArguments = $true)]
    [string[]]$Arguments
)

$ErrorActionPreference = "Stop"
$exeName = if ($Arguments.Count -gt 0) { "CodexProviderTool-cli.exe" } else { "CodexProviderTool.exe" }
$exe = Join-Path $PSScriptRoot $exeName

if (-not (Test-Path -LiteralPath $exe -PathType Leaf)) {
    throw "$exeName was not found beside this script."
}

& $exe @Arguments
exit $LASTEXITCODE

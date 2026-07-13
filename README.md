# Codex Provider Tool for Windows

This is a portable Windows build. It does not require Python or installation.

Double-click `CodexProviderTool.exe` to open the desktop page without a console window. Command-line usage is provided by `CodexProviderTool-cli.exe`.

The tool checks the local Codex provider configuration, probes OpenAI-compatible `/models` endpoints, and adds or switches relay providers with timestamped backups.

When adding or editing a provider, the model selector automatically requests `GET /models` after the Base URL or API key changes. The returned model IDs are loaded into an editable dropdown.

## Download

Download `dist/CodexProviderTool-windows-x64.zip`, extract it, and double-click `CodexProviderTool.exe`.

## Run

Open PowerShell in this directory:

```powershell
.\CodexProviderTool-cli.exe check
.\CodexProviderTool-cli.exe check --remote
.\CodexProviderTool-cli.exe models
```

The default Codex home is `%CODEX_HOME%` or `%USERPROFILE%\.codex`. To inspect another profile:

```powershell
.\CodexProviderTool-cli.exe --codex-home "D:\\some\\codex-home" check
```

The bundled `CodexProviderTool.ps1` is an optional PowerShell wrapper:

```powershell
.\CodexProviderTool.ps1 check
```

## Add a relay

```powershell
.\CodexProviderTool-cli.exe add relay_a `
  --label "Relay A" `
  --base-url "https://relay.example/v1" `
  --model "gpt-5.5" `
  --wire-api responses `
  --activate
```

Use `models relay_a --api-key "your-key"` to test the model catalog. The key is used only for that request.

To explicitly update `auth.json`, add `--api-key "your-key" --write-auth`. A timestamped backup is created before configuration changes.

The package contains no user configuration, API key, cookie, or login state.

## Build from source

Requires Python 3.11+ and PyInstaller:

```powershell
python -m pip install pyinstaller
.\scripts\Build-CodexProviderTool.ps1
```

The build creates `dist/CodexProviderTool-windows-x64.zip`.

## Test

```powershell
python .\scripts\test_codex_provider_tool.py
```

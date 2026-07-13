# Codex Provider Tool for Windows

This is a portable Windows build. It does not require Python or installation.

Double-click `CodexProviderTool.exe` to open the desktop page. The command line is also supported.

## Run

Open PowerShell in this directory:

```powershell
.\CodexProviderTool.exe check
.\CodexProviderTool.exe check --remote
.\CodexProviderTool.exe models
```

The default Codex home is `%CODEX_HOME%` or `%USERPROFILE%\.codex`. To inspect another profile:

```powershell
.\CodexProviderTool.exe --codex-home "D:\\some\\codex-home" check
```

The bundled `CodexProviderTool.ps1` is an optional PowerShell wrapper:

```powershell
.\CodexProviderTool.ps1 check
```

## Add a relay

```powershell
.\CodexProviderTool.exe add relay_a `
  --label "Relay A" `
  --base-url "https://relay.example/v1" `
  --model "gpt-5.5" `
  --wire-api responses `
  --activate
```

Use `models relay_a --api-key "your-key"` to test the model catalog. The key is used only for that request.

To explicitly update `auth.json`, add `--api-key "your-key" --write-auth`. A timestamped backup is created before configuration changes.

The package contains no user configuration, API key, cookie, or login state.

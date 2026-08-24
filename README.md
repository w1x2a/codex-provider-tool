# Codex Provider Tool for Windows

This is a portable Windows build. It does not require Python or installation.

Double-click `CodexProviderTool.exe` to open the desktop page without a console window. Command-line usage is provided by `CodexProviderTool-cli.exe`.

The tool checks the local Codex provider configuration, probes OpenAI-compatible `/models` endpoints, and adds or switches relay providers with timestamped backups.

When adding or editing a provider, the model selector automatically requests `GET /models` after the Base URL or API key changes. The returned model IDs are loaded into an editable dropdown.

Base URLs are normalized automatically: a missing `/v1` is appended, while repeated endings such as `/v1/v1/` are collapsed to one `/v1`.

Provider dialogs open centered over the main window and remain within the current virtual desktop bounds.

The **Get Codex** dialog opens the official Microsoft download page for product ID `9PLM9XGG6VKS`. If Microsoft Store is unavailable, it can copy the product ID and open the RG Adguard Store link generator with step-by-step Chinese instructions.

This build also fixes an older provider-update bug that could collapse a TOML section header and its first key onto one line. Known damage from that bug is backed up and repaired automatically when the GUI starts.

Provider switching preserves the active Codex `model_provider` identity and swaps the complete provider profiles behind it, including nested `auth` configuration. This keeps existing Codex conversations visible because their session metadata continues to use the same `model_provider` value. If the current identity cannot be rebound without a complete profile, the tool refuses the switch instead of changing the identity.

## Download

Download `dist/CodexProviderTool-windows-x64.zip`, extract it, and double-click `CodexProviderTool.exe`.

Linux x86_64 users can download `dist/CodexProviderTool-linux-x64.tar.gz`, extract it, run `chmod +x CodexProviderTool CodexProviderTool-cli`, and start the GUI with `./CodexProviderTool`.

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

Build Linux x86_64 binaries from a Linux environment with PyInstaller:

```bash
python3 -m pip install pyinstaller
./scripts/Build-CodexProviderTool-Linux.sh
```

## Test

```powershell
python .\scripts\test_codex_provider_tool.py
```

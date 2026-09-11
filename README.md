# Codex Provider Tool for Windows

This is a portable Windows build. It does not require Python or installation.

Double-click `CodexProviderTool.exe` to open the desktop page without a console window. Command-line usage is provided by `CodexProviderTool-cli.exe`.

The tool checks the local Codex provider configuration, lists the official OpenAI ChatGPT/Cookie login together with custom providers, probes OpenAI-compatible `/models` endpoints, and switches profiles with timestamped backups.

When adding or editing a provider, the model selector automatically requests `GET /models` after the Base URL or API key changes. The returned model IDs are loaded into an editable dropdown.

For the active relay, use the **模型** button to refresh its complete `/models` list and set the top-level Codex model without changing the provider/session identity. The selector prefers `gpt-6-astra` when available, and also keeps relay-provided IDs such as `gpt-6` selectable.

Base URLs are normalized automatically: a missing `/v1` is appended, while repeated endings such as `/v1/v1/` are collapsed to one `/v1`.

Provider dialogs open centered over the main window and remain within the current virtual desktop bounds.

The **Get Codex** dialog opens the official Microsoft download page for product ID `9PLM9XGG6VKS`. If Microsoft Store is unavailable, it can copy the product ID and open the RG Adguard Store link generator with step-by-step Chinese instructions.

This build also fixes an older provider-update bug that could collapse a TOML section header and its first key onto one line. Known damage from that bug is backed up and repaired automatically when the GUI starts.

Provider switching preserves the active Codex `model_provider` identity and swaps the complete provider profiles behind it, including nested `auth` configuration. For existing built-in `openai` conversations, it keeps that identity and uses Codex's supported `openai_base_url` override for the relay. This keeps existing conversations visible because their session metadata continues to use the same `model_provider` value. If a custom identity cannot be rebound without a complete profile, the tool refuses the switch instead of changing the identity.

The official card is always shown as **OpenAI 官方（ChatGPT/Cookie 登录）**. Before a relay API-key login, the tool backs up the current Codex-managed official login; selecting the official card restores that snapshot and removes the relay override. Under an established custom session identity, the tool swaps in a managed official profile (`responses` with `requires_openai_auth = true` and no relay Base URL) while keeping that identity unchanged. The previous relay profile is retained in the list and can be switched back losslessly. When no explicit `model_provider` exists, the official built-in `openai` provider is shown as current.

Use the card's **官方登录** button or the CLI `login` command when Codex needs a fresh browser login. This runs the official `codex login` flow with the selected `CODEX_HOME`; Codex alone stores and refreshes the login cache in `auth.json` or the OS credential store.

## Download

Download `dist/CodexProviderTool-windows-x64.zip`, extract it, and double-click `CodexProviderTool.exe`.

The current release includes a rebuilt Windows package only; an older Linux archive must not be treated as this release.

## Run

Open PowerShell in this directory:

```powershell
.\CodexProviderTool-cli.exe check
.\CodexProviderTool-cli.exe check --remote
.\CodexProviderTool-cli.exe models
.\CodexProviderTool-cli.exe use openai
.\CodexProviderTool-cli.exe login
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
  --api-key "your-key" `
  --write-auth `
  --activate
```

Use `models relay_a --api-key "your-key"` to test the model catalog. The key is used only for that request.

With `--activate`, `--api-key "your-key" --write-auth` submits the key to Codex's supported API-key login command. The tool creates timestamped configuration and official-login backups first. Fully exit and reopen Codex after changing a route; a saved configuration is not itself proof of relay traffic.

The package contains no user configuration, API key, Cookie, or login state. Provider switching never edits Codex SQLite, session JSONL, or existing chats.

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

# Codex Provider Tool for Windows

This is a portable Windows build. It does not require Python or installation.

Double-click `CodexProviderTool.exe` to open the desktop page without a console window. Use `CodexProviderTool-cli.exe` for command-line output.

The provider editor automatically loads model IDs from the relay's `/models` endpoint and fills an editable model dropdown.

The provider list always includes **OpenAI 官方（ChatGPT/Cookie 登录）**. Switching to it reuses the existing Codex-managed Cookie/login cache without copying or overwriting token contents. With an established custom session identity, the complete official profile is swapped behind the same ID, and the previous relay remains available for lossless switch-back.

Use **官方登录** or run `CodexProviderTool-cli.exe login` to start Codex's official browser login when the cached session has expired.

The Base URL field automatically adds a missing `/v1` and removes duplicate endings such as `/v1/v1/`.

Use **获取 Codex** to open the official Microsoft download page for product ID `9PLM9XGG6VKS`. When Microsoft Store cannot open, the dialog copies the product ID and opens the RG Adguard Store link generator with Chinese instructions.

The GUI automatically backs up and repairs the known malformed provider header produced by older builds.

Switching providers keeps the active Codex session identity unchanged and exchanges the complete provider profile, including nested `auth` settings, so existing chat history remains visible while the provider URL and settings change. A switch is refused when preserving the current identity would not be lossless.

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
  --activate
```

Use `models relay_a --api-key "your-key"` to test the model catalog. The key is used only for that request.

To explicitly update `auth.json`, add `--api-key "your-key" --write-auth`. A timestamped backup is created before configuration changes.

The package contains no user configuration, API key, Cookie, or login state. Switching providers does not edit Codex SQLite, session JSONL, existing chats, or Cookie/token contents.

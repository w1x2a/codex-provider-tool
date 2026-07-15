# Codex Provider Tool for Windows

This is a portable Windows build. It does not require Python or installation.

Double-click `CodexProviderTool.exe` to open the desktop page without a console window. Use `CodexProviderTool-cli.exe` for command-line output.

The provider editor automatically loads model IDs from the relay's `/models` endpoint and fills an editable model dropdown.

The Base URL field automatically adds a missing `/v1` and removes duplicate endings such as `/v1/v1/`.

The Add Provider dialog includes a one-click `https://anxiii.com/v1` preset. Enter the API key and click the button to validate, select a model, save, and activate it automatically.

Use **获取 Codex** to open the official Microsoft download page for product ID `9PLM9XGG6VKS`. When Microsoft Store cannot open, the dialog copies the product ID and opens the RG Adguard Store link generator with Chinese instructions.

The GUI automatically backs up and repairs the known malformed provider header produced by older builds.

Switching providers keeps the active Codex session identity unchanged, so existing chat history remains visible while the relay URL and provider settings change.

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

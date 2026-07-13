# Codex Provider Tool

`codex_provider_tool.py` is a small local CLI for checking the Codex provider configured in `config.toml` and connecting an OpenAI-compatible relay.

The tool does not print raw API keys. It does not write a key to `config.toml`. Configuration-changing commands create a timestamped backup beside the file first.

## Quick start

From the workspace root on Windows:

```powershell
.\scripts\Invoke-CodexProviderTool.ps1 check
.\scripts\Invoke-CodexProviderTool.ps1 check --remote
.\scripts\Invoke-CodexProviderTool.ps1 models
```

Use `--codex-home` when the target configuration is not `CODEX_HOME` or `%USERPROFILE%\.codex`.

## Connect a relay

Add a provider and make it active:

```powershell
.\scripts\Invoke-CodexProviderTool.ps1 add relay_a `
  --label "Relay A" `
  --base-url "https://relay.example/v1" `
  --model "gpt-5.5" `
  --wire-api responses `
  --activate
```

Then verify the remote model catalog:

```powershell
.\scripts\Invoke-CodexProviderTool.ps1 models relay_a --api-key "your-key"
```

The key above is used only for that request. Codex can use `OPENAI_API_KEY` from the process environment or from `auth.json`, depending on the local setup.

To explicitly update `auth.json`, use the opt-in form below. This also creates an auth backup:

```powershell
.\scripts\Invoke-CodexProviderTool.ps1 add relay_a `
  --base-url "https://relay.example/v1" `
  --model "gpt-5.5" `
  --activate `
  --api-key "your-key" `
  --write-auth
```

Switch between already configured providers without changing their definitions:

```powershell
.\scripts\Invoke-CodexProviderTool.ps1 use OpenAI --model "gpt-5.5"
```

## Commands

- `check`: inspect local files, active provider, provider definitions, and masked key status.
- `check --remote`: also request the active provider's `/models` endpoint.
- `models [provider_id]`: request `/models` and print model IDs.
- `add <provider_id>`: add or update an OpenAI-compatible provider.
- `use <provider_id>`: select an existing provider.

The tool only performs a `GET /models` probe. It does not send a completion request and therefore does not intentionally consume model quota.

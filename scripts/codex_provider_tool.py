#!/usr/bin/env python3
"""Inspect and manage Codex model providers without third-party dependencies."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import sys
import tempfile
import urllib.error
import urllib.request
from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Any


PROVIDER_ID_RE = re.compile(r"^[A-Za-z0-9_-]+$")
SECTION_RE = re.compile(r"^\[[^\r\n]+\][ \t]*$", re.MULTILINE)
TOP_LEVEL_KEY_RE = re.compile(r"^(?P<indent>[ \t]*){key}[ \t]*=.*$", re.MULTILINE)
PROVIDER_KEY_RE = re.compile(r"^(?P<indent>[ \t]*){key}[ \t]*=.*$", re.MULTILINE)
COLLAPSED_PROVIDER_HEADER_RE = re.compile(
    r"^(\[model_providers\.[A-Za-z0-9_-]+\])(?=[A-Za-z_][A-Za-z0-9_-]*[ \t]*=)",
    re.MULTILINE,
)


class ToolError(RuntimeError):
    """An expected, user-facing tool error."""


@dataclass
class Provider:
    provider_id: str
    name: str
    base_url: str
    wire_api: str
    requires_openai_auth: bool
    current: bool = False

    @property
    def category(self) -> str:
        host = self.base_url.lower()
        if not self.base_url:
            return "local/official"
        if "openai.com" in host or "chatgpt.com" in host:
            return "official"
        return "third-party/openai-compatible"


@dataclass
class ProbeResult:
    provider_id: str
    url: str
    ok: bool
    status: int | None
    message: str
    models: list[str]
    elapsed_ms: int | None


def safe_url(value: str) -> str:
    """Do not print query strings or fragments that may contain credentials."""
    value = value.strip()
    if not value:
        return ""
    try:
        from urllib.parse import urlsplit, urlunsplit

        parsed = urlsplit(value)
        return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, "", ""))
    except ValueError:
        return value.split("?", 1)[0].split("#", 1)[0]


def mask_secret(value: str | None) -> str:
    if not value:
        return "missing"
    return f"present (length={len(value)})"


def resolve_codex_home(explicit: str | None) -> Path:
    if explicit:
        return Path(explicit).expanduser()
    env_home = os.environ.get("CODEX_HOME")
    if env_home:
        return Path(env_home).expanduser()
    candidates = [Path.home() / ".codex", Path.cwd() / ".codex"]

    seen: set[str] = set()
    for candidate in candidates:
        resolved = str(candidate.resolve())
        if resolved in seen:
            continue
        seen.add(resolved)
        if (candidate / "config.toml").is_file() or (candidate / "auth.json").is_file():
            return candidate
    return candidates[0] if candidates else Path.home() / ".codex"


def read_json(path: Path) -> dict[str, Any]:
    if not path.is_file():
        return {}
    try:
        value = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ToolError(f"Cannot read JSON file {path}: {exc}") from exc
    if not isinstance(value, dict):
        raise ToolError(f"Expected a JSON object in {path}")
    return value


def read_config(path: Path) -> tuple[str, dict[str, Any]]:
    if not path.is_file():
        return "", {}
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ToolError(f"Cannot read config {path}: {exc}") from exc
    try:
        import tomllib

        data = tomllib.loads(text)
    except (ModuleNotFoundError, ImportError) as exc:
        raise ToolError("Python 3.11 or newer is required because tomllib is unavailable") from exc
    except Exception as exc:  # tomllib raises TOMLDecodeError, which varies by Python version.
        raise ToolError(f"Invalid TOML in {path}: {exc}") from exc
    return text, data


def repair_collapsed_provider_headers(path: Path) -> Path | None:
    if not path.is_file():
        return None
    try:
        text = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ToolError(f"Cannot read config {path}: {exc}") from exc
    repaired, count = COLLAPSED_PROVIDER_HEADER_RE.subn(r"\1\n", text)
    if count == 0:
        return None
    try:
        import tomllib

        tomllib.loads(repaired)
    except Exception:
        return None
    backup = backup_file(path, "provider-tool-auto-repair")
    atomic_write(path, repaired)
    return backup


def get_providers(data: dict[str, Any]) -> list[Provider]:
    current_id = str(data.get("model_provider") or "")
    raw_providers = data.get("model_providers") or {}
    if not isinstance(raw_providers, dict):
        raise ToolError("config.toml has an invalid model_providers table")

    providers: list[Provider] = []
    for provider_id, raw in raw_providers.items():
        if not isinstance(raw, dict):
            continue
        providers.append(
            Provider(
                provider_id=str(provider_id),
                name=str(raw.get("name") or provider_id),
                base_url=str(raw.get("base_url") or ""),
                wire_api=str(raw.get("wire_api") or "responses"),
                requires_openai_auth=bool(raw.get("requires_openai_auth", True)),
                current=str(provider_id) == current_id,
            )
        )
    return providers


def find_provider(data: dict[str, Any], provider_id: str | None) -> Provider:
    providers = get_providers(data)
    wanted = provider_id or str(data.get("model_provider") or "")
    for provider in providers:
        if provider.provider_id == wanted:
            return provider
    if wanted:
        raise ToolError(f"Provider not found: {wanted}")
    raise ToolError("No active model_provider is configured")


def load_auth_key(home: Path, cli_key: str | None = None, env_name: str = "OPENAI_API_KEY") -> tuple[str | None, str]:
    if cli_key:
        return cli_key, "command line"
    env_key = os.environ.get(env_name)
    if env_key:
        return env_key, f"environment:{env_name}"
    auth = read_json(home / "auth.json")
    auth_key = auth.get(env_name)
    if isinstance(auth_key, str) and auth_key:
        return auth_key, f"auth.json:{env_name}"
    if env_name != "OPENAI_API_KEY":
        auth_key = auth.get("OPENAI_API_KEY")
        if isinstance(auth_key, str) and auth_key:
            return auth_key, "auth.json:OPENAI_API_KEY"
    return None, "missing"


def normalize_base_url(base_url: str) -> str:
    from urllib.parse import urlsplit, urlunsplit

    value = base_url.strip()
    try:
        parsed = urlsplit(value)
    except ValueError as exc:
        raise ToolError(f"invalid base URL: {exc}") from exc
    if parsed.scheme.lower() not in ("http", "https") or not parsed.netloc:
        raise ToolError("base URL must be a valid http:// or https:// URL")
    path = parsed.path.rstrip("/")
    path = re.sub(r"(?:/v1)+$", "", path, flags=re.IGNORECASE).rstrip("/")
    normalized_path = f"{path}/v1" if path else "/v1"
    return urlunsplit((parsed.scheme.lower(), parsed.netloc, normalized_path, "", ""))


def endpoint_for_models(base_url: str) -> str:
    return normalize_base_url(base_url) + "/models"


def probe_provider(provider: Provider, api_key: str | None, timeout: float) -> ProbeResult:
    import time

    url = endpoint_for_models(provider.base_url)
    headers = {"Accept": "application/json", "User-Agent": "codex-provider-tool/1.0"}
    if api_key:
        headers["Authorization"] = f"Bearer {api_key}"
    request = urllib.request.Request(url, headers=headers, method="GET")
    started = time.monotonic()
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            payload = response.read()
            status = response.status
        elapsed_ms = round((time.monotonic() - started) * 1000)
    except urllib.error.HTTPError as exc:
        elapsed_ms = round((time.monotonic() - started) * 1000)
        detail = ""
        try:
            detail = exc.read(400).decode("utf-8", errors="replace").replace("\n", " ")
        except OSError:
            pass
        message = f"HTTP {exc.code}"
        if exc.code in (401, 403):
            message += " (authentication rejected)"
        elif exc.code == 404:
            message += " (/models is not available)"
        if detail:
            message += f": {detail[:160]}"
        return ProbeResult(provider.provider_id, safe_url(url), False, exc.code, message, [], elapsed_ms)
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        elapsed_ms = round((time.monotonic() - started) * 1000)
        return ProbeResult(provider.provider_id, safe_url(url), False, None, f"connection failed: {exc}", [], elapsed_ms)

    models: list[str] = []
    try:
        decoded = json.loads(payload.decode("utf-8"))
        raw_models = decoded.get("data", []) if isinstance(decoded, dict) else []
        if isinstance(raw_models, list):
            for item in raw_models:
                if isinstance(item, dict) and isinstance(item.get("id"), str):
                    models.append(item["id"])
    except (UnicodeDecodeError, json.JSONDecodeError):
        return ProbeResult(provider.provider_id, safe_url(url), False, status, "response is not valid JSON", [], elapsed_ms)

    if status < 200 or status >= 300:
        return ProbeResult(provider.provider_id, safe_url(url), False, status, f"HTTP {status}", models, elapsed_ms)
    message = f"reachable; {len(models)} model(s) reported"
    return ProbeResult(provider.provider_id, safe_url(url), True, status, message, models, elapsed_ms)


def toml_string(value: str) -> str:
    return json.dumps(value, ensure_ascii=True)


def set_top_level_value(text: str, key: str, rendered: str) -> str:
    pattern = re.compile(TOP_LEVEL_KEY_RE.pattern.format(key=re.escape(key)), re.MULTILINE)
    first_section = SECTION_RE.search(text)
    top_level_text = text[: first_section.start()] if first_section else text
    match = pattern.search(top_level_text)
    if match:
        return text[: match.start()] + f"{match.group('indent')}{key} = {rendered}" + text[match.end() :]

    insert = f"{key} = {rendered}\n"
    return insert + text


def update_provider_block(text: str, provider_id: str, values: dict[str, str]) -> str:
    header = f"[model_providers.{provider_id}]"
    header_pattern = re.compile(rf"^\[model_providers\.{re.escape(provider_id)}\][ \t]*$", re.MULTILINE)
    match = header_pattern.search(text)
    if match:
        next_section = SECTION_RE.search(text, match.end())
        end = next_section.start() if next_section else len(text)
        block = text[match.end() : end]
        for key, rendered in values.items():
            key_pattern = re.compile(PROVIDER_KEY_RE.pattern.format(key=re.escape(key)), re.MULTILINE)
            key_match = key_pattern.search(block)
            line = f"{key} = {rendered}"
            if key_match:
                block = block[: key_match.start()] + line + block[key_match.end() :]
            else:
                if not block.endswith("\n"):
                    block += "\n"
                block += line + "\n"
        return text[: match.end()] + block + text[end:]

    suffix = "\n" if text and not text.endswith("\n") else ""
    block = f"{suffix}\n{header}\n" + "".join(f"{key} = {rendered}\n" for key, rendered in values.items())
    return text + block


def backup_file(path: Path, label: str) -> Path | None:
    if not path.is_file():
        return None
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    backup = path.with_name(f"{path.name}.bak-{label}-{stamp}")
    shutil.copy2(path, backup)
    return backup


def atomic_write(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name: str | None = None
    try:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8", newline="", dir=path.parent, delete=False) as handle:
            handle.write(text)
            temp_name = handle.name
        os.replace(temp_name, path)
    except OSError as exc:
        if temp_name:
            try:
                Path(temp_name).unlink(missing_ok=True)
            except OSError:
                pass
        raise ToolError(f"Cannot write {path}: {exc}") from exc


def write_auth_key(home: Path, key: str) -> Path | None:
    path = home / "auth.json"
    auth = read_json(path)
    backup = backup_file(path, "provider-tool-auth")
    auth["OPENAI_API_KEY"] = key
    atomic_write(path, json.dumps(auth, indent=2, ensure_ascii=True) + "\n")
    return backup


def upsert_provider(home: Path, args: argparse.Namespace) -> tuple[Path, list[Path]]:
    if not PROVIDER_ID_RE.fullmatch(args.provider_id):
        raise ToolError("provider id may contain only letters, digits, '_' and '-'")
    normalized_base_url = normalize_base_url(args.base_url)
    if args.write_auth and not args.api_key:
        raise ToolError("--write-auth requires --api-key")
    config_path = home / "config.toml"
    text, _ = read_config(config_path)
    values = {
        "name": toml_string(args.label or args.provider_id),
        "base_url": toml_string(normalized_base_url),
        "wire_api": toml_string(args.wire_api),
        "requires_openai_auth": "true" if args.requires_openai_auth else "false",
    }
    if args.activate:
        updated = set_top_level_value(text, "model_provider", toml_string(args.provider_id))
        updated = set_top_level_value(updated, "model", toml_string(args.model))
    else:
        updated = text
    updated = update_provider_block(updated, args.provider_id, values)
    backups: list[Path] = []
    backup = backup_file(config_path, "provider-tool")
    if backup:
        backups.append(backup)
    atomic_write(config_path, updated)
    if args.write_auth:
        auth_backup = write_auth_key(home, args.api_key)
        if auth_backup:
            backups.append(auth_backup)
    return config_path, backups


def print_check(home: Path, data: dict[str, Any], auth_source: str, auth_key: str | None) -> None:
    config_path = home / "config.toml"
    auth_path = home / "auth.json"
    print(f"Codex home: {home}")
    print(f"Config:     {'OK' if config_path.is_file() else 'missing'} ({config_path})")
    print(f"Auth:       {'present' if auth_path.is_file() else 'missing'} ({auth_path})")
    print(f"API key:    {mask_secret(auth_key)} [{auth_source}]")
    print(f"Model:      {data.get('model') or 'not set'}")
    print(f"Active:     {data.get('model_provider') or 'not set'}")
    providers = get_providers(data)
    if not providers:
        print("Providers:  none")
        return
    print("Providers:")
    for provider in providers:
        marker = "*" if provider.current else " "
        auth = "auth-required" if provider.requires_openai_auth else "no-auth"
        print(
            f" {marker} {provider.provider_id}: {provider.name} | {provider.category} | "
            f"{safe_url(provider.base_url) or 'no base_url'} | {provider.wire_api} | {auth}"
        )


def check_json(home: Path, data: dict[str, Any], auth_source: str, auth_key: str | None) -> dict[str, Any]:
    providers = [asdict(provider) | {"base_url": safe_url(provider.base_url), "category": provider.category} for provider in get_providers(data)]
    return {
        "codex_home": str(home),
        "config_path": str(home / "config.toml"),
        "auth_path": str(home / "auth.json"),
        "config_exists": (home / "config.toml").is_file(),
        "auth_exists": (home / "auth.json").is_file(),
        "api_key_present": bool(auth_key),
        "api_key_source": auth_source,
        "model": data.get("model"),
        "model_provider": data.get("model_provider"),
        "providers": providers,
    }


def command_check(args: argparse.Namespace) -> int:
    home = resolve_codex_home(args.codex_home)
    _, data = read_config(home / "config.toml")
    key, source = load_auth_key(home, env_name=args.api_key_env)
    if args.json:
        print(json.dumps(check_json(home, data, source, key), indent=2, ensure_ascii=True))
    else:
        print_check(home, data, source, key)
    if args.remote:
        provider = find_provider(data, None)
        result = probe_provider(provider, key, args.timeout)
        print(f"Remote:     {'OK' if result.ok else 'FAIL'} {result.message} ({result.elapsed_ms} ms)")
        if result.models:
            print("Models:     " + ", ".join(result.models))
        return 0 if result.ok else 1
    return 0


def command_models(args: argparse.Namespace) -> int:
    home = resolve_codex_home(args.codex_home)
    _, data = read_config(home / "config.toml")
    provider = find_provider(data, args.provider_id)
    key, source = load_auth_key(home, args.api_key, args.api_key_env)
    result = probe_provider(provider, key, args.timeout)
    print(f"Provider: {provider.provider_id} ({provider.name})")
    print(f"Endpoint: {result.url}")
    print(f"Auth:     {source if key else 'missing'}")
    print(f"Result:   {'OK' if result.ok else 'FAIL'} - {result.message}")
    if result.models:
        for model in result.models:
            print(f"  {model}")
    return 0 if result.ok else 1


def command_add(args: argparse.Namespace) -> int:
    home = resolve_codex_home(args.codex_home)
    config_path, backups = upsert_provider(home, args)
    print(f"Provider written: {args.provider_id}")
    print(f"Config: {config_path}")
    for backup in backups:
        print(f"Backup: {backup}")
    if args.write_auth:
        print("Auth: OPENAI_API_KEY updated in auth.json")
    print("Active provider: " + (args.provider_id if args.activate else "unchanged"))
    return 0


def command_use(args: argparse.Namespace) -> int:
    home = resolve_codex_home(args.codex_home)
    config_path = home / "config.toml"
    text, data = read_config(config_path)
    find_provider(data, args.provider_id)
    updated = set_top_level_value(text, "model_provider", toml_string(args.provider_id))
    if args.model:
        updated = set_top_level_value(updated, "model", toml_string(args.model))
    backup = backup_file(config_path, "provider-tool")
    atomic_write(config_path, updated)
    print(f"Active provider: {args.provider_id}")
    print(f"Config: {config_path}")
    if backup:
        print(f"Backup: {backup}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Inspect and manage Codex model providers")
    parser.add_argument("--codex-home", help="Codex home directory; defaults to CODEX_HOME or ~/.codex")
    subparsers = parser.add_subparsers(dest="command")

    check = subparsers.add_parser("check", help="show local provider and auth status")
    check.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    check.add_argument("--remote", action="store_true", help="also probe the active provider /models endpoint")
    check.add_argument("--timeout", type=float, default=8.0)
    check.add_argument("--api-key-env", default="OPENAI_API_KEY")
    check.set_defaults(func=command_check)

    models = subparsers.add_parser("models", help="probe a provider and list its models")
    models.add_argument("provider_id", nargs="?", help="provider id; defaults to the active provider")
    models.add_argument("--api-key", help="temporary key for this request; never written")
    models.add_argument("--api-key-env", default="OPENAI_API_KEY")
    models.add_argument("--timeout", type=float, default=8.0)
    models.set_defaults(func=command_models)

    add = subparsers.add_parser("add", help="add or update an OpenAI-compatible provider")
    add.add_argument("provider_id", help="simple id, for example relay_a")
    add.add_argument("--base-url", required=True, help="provider base URL, usually ending in /v1")
    add.add_argument("--model", required=True, help="model id used when activating this provider")
    add.add_argument("--label", help="display name; defaults to provider id")
    add.add_argument("--wire-api", choices=("responses", "chat"), default="responses")
    auth_group = add.add_mutually_exclusive_group()
    auth_group.add_argument("--requires-openai-auth", dest="requires_openai_auth", action="store_true", default=True)
    auth_group.add_argument("--no-requires-openai-auth", dest="requires_openai_auth", action="store_false")
    add.add_argument("--activate", action="store_true", help="also set model_provider and model")
    add.add_argument("--api-key", help="key used only with --write-auth")
    add.add_argument("--write-auth", action="store_true", help="write API key to auth.json; otherwise no key is persisted")
    add.set_defaults(func=command_add)

    use = subparsers.add_parser("use", help="switch the active provider")
    use.add_argument("provider_id")
    use.add_argument("--model", help="override the top-level model")
    use.set_defaults(func=command_use)

    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    raw_args = list(sys.argv[1:] if argv is None else argv)
    args = parser.parse_args(raw_args)
    if not args.command:
        args = parser.parse_args([*raw_args, "check"])
    try:
        return int(args.func(args))
    except ToolError as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

#!/usr/bin/env python3
"""Inspect and manage Codex model providers without third-party dependencies."""

from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
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
OFFICIAL_PROVIDER_ID = "openai"
OFFICIAL_PROVIDER_NAME = "OpenAI 官方（ChatGPT/Cookie 登录）"
OFFICIAL_PROFILE_STORAGE_ID = "codex_official"
OFFICIAL_AUTH_BACKUP_LABEL = "provider-tool-official-auth"


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
    official: bool = False

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


def is_managed_official_profile(raw: Any) -> bool:
    if not isinstance(raw, dict):
        return False
    return (
        str(raw.get("name") or "") == OFFICIAL_PROVIDER_NAME
        and not str(raw.get("base_url") or "").strip()
        and str(raw.get("wire_api") or "responses") == "responses"
        and raw.get("requires_openai_auth") is True
        and not any(raw.get(key) for key in ("auth", "env_key", "experimental_bearer_token"))
    )


def get_providers(data: dict[str, Any]) -> list[Provider]:
    current_id = str(data.get("model_provider") or OFFICIAL_PROVIDER_ID)
    raw_providers = data.get("model_providers") or {}
    if not isinstance(raw_providers, dict):
        raise ToolError("config.toml has an invalid model_providers table")

    current_raw = raw_providers.get(current_id)
    builtin_url = str(data.get("openai_base_url") or "").rstrip("/")
    builtin_relay = next((str(pid) for pid, raw in raw_providers.items()
                          if isinstance(raw, dict) and builtin_url
                          and str(raw.get("base_url") or "").rstrip("/") == builtin_url), None)
    official_current = (
        (current_id == OFFICIAL_PROVIDER_ID and not builtin_url)
        or is_managed_official_profile(current_raw)
    )
    providers: list[Provider] = [
        Provider(
            provider_id=OFFICIAL_PROVIDER_ID,
            name=OFFICIAL_PROVIDER_NAME,
            base_url="",
            wire_api="responses",
            requires_openai_auth=True,
            current=official_current,
            official=True,
        )
    ]
    for provider_id, raw in raw_providers.items():
        if (
            not isinstance(raw, dict)
            or str(provider_id) == OFFICIAL_PROVIDER_ID
            or is_managed_official_profile(raw)
        ):
            continue
        providers.append(
            Provider(
                provider_id=str(provider_id),
                name=str(raw.get("name") or provider_id),
                base_url=str(raw.get("base_url") or ""),
                wire_api=str(raw.get("wire_api") or "responses"),
                requires_openai_auth=bool(raw.get("requires_openai_auth", True)),
                current=(str(provider_id) == builtin_relay if current_id == OFFICIAL_PROVIDER_ID
                         else str(provider_id) == current_id),
            )
        )
    return providers


def find_provider(data: dict[str, Any], provider_id: str | None) -> Provider:
    providers = get_providers(data)
    if provider_id is None:
        active = next((provider for provider in providers if provider.current), None)
        if active is not None:
            return active
    current_id = str(data.get("model_provider") or OFFICIAL_PROVIDER_ID)
    raw_providers = data.get("model_providers") or {}
    current_raw = raw_providers.get(current_id) if isinstance(raw_providers, dict) else None
    if provider_id:
        wanted = provider_id
    elif not current_id or current_id == OFFICIAL_PROVIDER_ID or is_managed_official_profile(current_raw):
        wanted = OFFICIAL_PROVIDER_ID
    else:
        wanted = current_id
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


def remove_top_level_value(text: str, key: str) -> str:
    pattern = re.compile(TOP_LEVEL_KEY_RE.pattern.format(key=re.escape(key)), re.MULTILINE)
    first_section = SECTION_RE.search(text)
    top_level_text = text[: first_section.start()] if first_section else text
    match = pattern.search(top_level_text)
    if not match:
        return text
    end = match.end()
    if text.startswith("\r\n", end):
        end += 2
    elif text.startswith("\n", end):
        end += 1
    return text[: match.start()] + text[end:]


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


def swap_provider_table_ids(text: str, first_id: str, second_id: str) -> str:
    if first_id == second_id:
        return text
    first = re.escape(first_id)
    second = re.escape(second_id)
    pattern = re.compile(
        rf"^(?P<prefix>\[model_providers\.)(?P<provider>{first}|{second})(?P<suffix>(?:\.[^\]\r\n]+)?)\](?P<trailing>[ \t]*)$",
        re.MULTILINE,
    )

    def replace(match: re.Match[str]) -> str:
        provider_id = second_id if match.group("provider") == first_id else first_id
        return f"{match.group('prefix')}{provider_id}{match.group('suffix')}]{match.group('trailing')}"

    return pattern.sub(replace, text)


def find_managed_official_profile_id(raw_providers: dict[str, Any]) -> str | None:
    for provider_id, raw in raw_providers.items():
        if str(provider_id) != OFFICIAL_PROVIDER_ID and is_managed_official_profile(raw):
            return str(provider_id)
    return None


def next_official_profile_storage_id(raw_providers: dict[str, Any]) -> str:
    candidate = OFFICIAL_PROFILE_STORAGE_ID
    suffix = 2
    while candidate in raw_providers or candidate == OFFICIAL_PROVIDER_ID:
        candidate = f"{OFFICIAL_PROFILE_STORAGE_ID}_{suffix}"
        suffix += 1
    return candidate


def add_managed_official_profile(text: str, provider_id: str) -> str:
    return update_provider_block(
        text,
        provider_id,
        {
            "name": toml_string(OFFICIAL_PROVIDER_NAME),
            "wire_api": toml_string("responses"),
            "requires_openai_auth": "true",
        },
    )


def switch_provider_preserving_history(
    text: str,
    data: dict[str, Any],
    provider_id: str,
    model: str | None = None,
) -> tuple[str, str, bool]:
    find_provider(data, provider_id)
    current_id = str(data.get("model_provider") or OFFICIAL_PROVIDER_ID)
    if provider_id == OFFICIAL_PROVIDER_ID:
        if current_id == OFFICIAL_PROVIDER_ID:
            updated = remove_top_level_value(text, "openai_base_url")
            updated = set_top_level_value(updated, "model_provider", toml_string(OFFICIAL_PROVIDER_ID))
            if model:
                updated = set_top_level_value(updated, "model", toml_string(model))
            return updated, OFFICIAL_PROVIDER_ID, current_id == OFFICIAL_PROVIDER_ID

        raw_providers = data.get("model_providers") or {}
        if not isinstance(raw_providers, dict) or current_id not in raw_providers:
            raise ToolError(
                f"Cannot switch to {OFFICIAL_PROVIDER_NAME} without changing the active model_provider "
                f"session identity ({current_id}); add a complete provider table for {current_id} first"
            )
        if is_managed_official_profile(raw_providers[current_id]):
            updated = text
        else:
            official_profile_id = find_managed_official_profile_id(raw_providers)
            if not official_profile_id:
                official_profile_id = next_official_profile_storage_id(raw_providers)
                updated = add_managed_official_profile(text, official_profile_id)
            else:
                updated = text
            updated = swap_provider_table_ids(updated, current_id, official_profile_id)
        if model:
            updated = set_top_level_value(updated, "model", toml_string(model))
        return updated, current_id, True

    if current_id == OFFICIAL_PROVIDER_ID:
        raw = data["model_providers"][provider_id]
        # Codex reserves the built-in openai table. Use its supported URL override
        # and reject options that cannot be honored instead of silently dropping them.
        unsupported = set(raw) - {"name", "base_url", "wire_api", "requires_openai_auth"}
        if unsupported or raw.get("wire_api", "responses") != "responses" or raw.get("requires_openai_auth", True) is not True:
            fields = ", ".join(sorted(unsupported)) or "wire_api / requires_openai_auth"
            raise ToolError(
                f"Cannot preserve built-in openai identity with these provider options: {fields}. "
                "The built-in route supports Responses with API-key authentication; "
                "custom session identities can exchange complete provider/auth tables."
            )
        if not raw.get("base_url"):
            raise ToolError("The selected relay has no base_url")
        updated = set_top_level_value(text, "model_provider", toml_string(OFFICIAL_PROVIDER_ID))
        updated = set_top_level_value(updated, "openai_base_url", toml_string(raw["base_url"]))
        if model:
            updated = set_top_level_value(updated, "model", toml_string(model))
        return updated, OFFICIAL_PROVIDER_ID, True
    if current_id == provider_id:
        updated = set_top_level_value(text, "model_provider", toml_string(current_id))
        if model:
            updated = set_top_level_value(updated, "model", toml_string(model))
        return updated, current_id, True

    raw_providers = data.get("model_providers") or {}
    can_keep_session_identity = (
        isinstance(raw_providers, dict)
        and current_id in raw_providers
        and provider_id in raw_providers
    )
    if not can_keep_session_identity:
        raise ToolError(
            f"Cannot switch to {provider_id} without changing the active model_provider "
            f"session identity ({current_id}); add a complete provider table for {current_id} first"
        )

    updated = swap_provider_table_ids(text, current_id, provider_id)
    active_id = current_id
    history_preserved = True
    if model:
        updated = set_top_level_value(updated, "model", toml_string(model))
    return updated, active_id, history_preserved


def launch_codex_login(home: Path, new_console: bool = True) -> subprocess.Popen[Any]:
    if not shutil.which("codex"):
        raise ToolError("Codex CLI was not found in PATH; install Codex before starting official login")
    env = os.environ.copy()
    env["CODEX_HOME"] = str(home)
    if os.name == "nt":
        pwsh = shutil.which("pwsh")
        if not pwsh:
            raise ToolError("PowerShell 7 (pwsh) was not found; it is required to start Codex login")
        script = (
            "$ErrorActionPreference = 'Stop'\n"
            "$PSNativeCommandUseErrorActionPreference = $true\n"
            "codex login"
        )
        command = [pwsh, "-NoProfile"]
        if new_console:
            command.append("-NoExit")
        command.extend(["-Command", script])
        creationflags = subprocess.CREATE_NEW_CONSOLE if new_console else 0
        try:
            return subprocess.Popen(command, env=env, creationflags=creationflags)
        except OSError as exc:
            raise ToolError(f"Cannot start Codex official login: {exc}") from exc

    codex = shutil.which("codex")
    try:
        return subprocess.Popen([codex, "login"], env=env)
    except OSError as exc:
        raise ToolError(f"Cannot start Codex official login: {exc}") from exc


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


def atomic_write_bytes(path: Path, content: bytes) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary: str | None = None
    try:
        with tempfile.NamedTemporaryFile("wb", dir=path.parent, delete=False) as handle:
            handle.write(content)
            temporary = handle.name
        os.replace(temporary, path)
    except OSError as exc:
        if temporary:
            Path(temporary).unlink(missing_ok=True)
        raise ToolError(f"Cannot write {path}: {exc}") from exc


def latest_backup(path: Path, label: str) -> Path | None:
    matches = sorted(path.parent.glob(f"{path.name}.bak-{label}-*"), key=lambda item: item.stat().st_mtime, reverse=True)
    return matches[0] if matches else None


def native_codex_executable() -> str:
    local_root = Path(os.environ.get("LOCALAPPDATA") or Path.home() / "AppData" / "Local") / "OpenAI" / "Codex" / "bin"
    candidates = sorted(local_root.glob("*/codex.exe"), key=lambda item: item.stat().st_mtime, reverse=True)
    if candidates:
        return str(candidates[0])
    command = shutil.which("codex")
    if command:
        return command
    raise ToolError("Cannot find the Codex CLI needed to activate an API-key provider")


def codex_login_with_api_key(home: Path, api_key: str) -> None:
    environment = os.environ.copy()
    environment["CODEX_HOME"] = str(home)
    creation_flags = subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0
    try:
        result = subprocess.run(
            [native_codex_executable(), "login", "--with-api-key"],
            input=api_key + "\n",
            text=True,
            encoding="utf-8",
            errors="replace",
            env=environment,
            capture_output=True,
            timeout=30,
            creationflags=creation_flags,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        raise ToolError(f"Codex API-key login could not start: {exc}") from exc
    if result.returncode:
        raise ToolError("Codex rejected the provider API Key; the previous Cookie/login state was restored")


def activate_provider(
    home: Path, provider_id: str, model: str | None = None,
    restore_official_identity: bool = False, api_key: str | None = None,
) -> tuple[str, list[Path]]:
    text, data = read_config(home / "config.toml")
    target = find_provider(data, provider_id)
    switch_data = data
    if restore_official_identity:
        # Explicit repair for older releases that changed implicit openai to a new ID.
        switch_data = dict(data, model_provider=OFFICIAL_PROVIDER_ID)
        text = set_top_level_value(text, "model_provider", toml_string(OFFICIAL_PROVIDER_ID))
    updated, active_id, _ = switch_provider_preserving_history(text, switch_data, provider_id, model)
    config_path = home / "config.toml"
    auth_path = home / "auth.json"
    before_config = config_path.read_bytes() if config_path.is_file() else None
    before_auth = auth_path.read_bytes() if auth_path.is_file() else None
    backups: list[Path] = []
    if target.official:
        active = find_provider(data, None)
        if active.official and not data.get("openai_base_url"):
            return active_id, backups
        official_auth = latest_backup(auth_path, OFFICIAL_AUTH_BACKUP_LABEL)
        if not official_auth:
            if read_json(auth_path).get("tokens"):
                config_backup = backup_file(config_path, "provider-tool")
                if config_backup:
                    backups.append(config_backup)
                atomic_write(config_path, updated)
                return active_id, backups
            raise ToolError("找不到官方 Cookie 登录备份；请先点击“官方登录”重新登录。")
        active_backup = backup_file(auth_path, f"provider-tool-relay-{active.provider_id}")
        if active_backup:
            backups.append(active_backup)
        config_backup = backup_file(config_path, "provider-tool")
        if config_backup:
            backups.append(config_backup)
        try:
            atomic_write(config_path, updated)
            atomic_write_bytes(auth_path, official_auth.read_bytes())
        except Exception:
            if before_config is None:
                config_path.unlink(missing_ok=True)
            else:
                atomic_write_bytes(config_path, before_config)
            if before_auth is None:
                auth_path.unlink(missing_ok=True)
            else:
                atomic_write_bytes(auth_path, before_auth)
            raise
        return active_id, backups

    # A pre-existing custom session identity can exchange complete provider tables,
    # including its own auth helper. The built-in openai identity instead requires
    # Codex's supported API-key login for the openai_base_url override.
    if active_id != OFFICIAL_PROVIDER_ID:
        config_backup = backup_file(config_path, "provider-tool")
        if config_backup:
            backups.append(config_backup)
        atomic_write(config_path, updated)
        return active_id, backups

    relay_auth = latest_backup(auth_path, f"provider-tool-relay-{provider_id}")
    stored_key = read_json(relay_auth).get("OPENAI_API_KEY") if relay_auth else None
    key = api_key or stored_key or read_json(auth_path).get("OPENAI_API_KEY")
    if not isinstance(key, str) or not key:
        raise ToolError("该中转站没有可用 API Key；请在编辑供应商中填写 API Key 后保存。")
    current_auth = read_json(auth_path)
    if current_auth.get("tokens"):
        official_backup = backup_file(auth_path, OFFICIAL_AUTH_BACKUP_LABEL)
        if official_backup:
            backups.append(official_backup)
    config_backup = backup_file(config_path, "provider-tool")
    if config_backup:
        backups.append(config_backup)
    try:
        atomic_write(config_path, updated)
        # Let Codex create its own supported API-key credential representation.
        codex_login_with_api_key(home, key)
    except Exception:
        if before_config is None:
            config_path.unlink(missing_ok=True)
        else:
            atomic_write_bytes(config_path, before_config)
        if before_auth is None:
            auth_path.unlink(missing_ok=True)
        else:
            atomic_write_bytes(auth_path, before_auth)
        raise
    return active_id, backups


def upsert_provider(home: Path, args: argparse.Namespace) -> tuple[Path, list[Path]]:
    if not PROVIDER_ID_RE.fullmatch(args.provider_id):
        raise ToolError("provider id may contain only letters, digits, '_' and '-'")
    if args.provider_id == OFFICIAL_PROVIDER_ID:
        raise ToolError("provider id 'openai' is reserved by Codex; use 'use openai' for official login")
    normalized_base_url = normalize_base_url(args.base_url)
    if args.write_auth and not args.api_key:
        raise ToolError("--write-auth requires --api-key")
    if args.write_auth and not args.activate:
        raise ToolError("API Key is applied only during activation so Codex can manage it safely; add --activate.")
    config_path = home / "config.toml"
    text, previous = read_config(config_path)
    values = {
        "name": toml_string(args.label or args.provider_id),
        "base_url": toml_string(normalized_base_url),
        "wire_api": toml_string(args.wire_api),
        "requires_openai_auth": "true" if args.requires_openai_auth else "false",
    }
    updated = update_provider_block(text, args.provider_id, values)
    import tomllib

    updated_data = tomllib.loads(updated)
    if args.activate:
        original = config_path.read_bytes() if config_path.is_file() else None
        backup = backup_file(config_path, "provider-tool")
        try:
            atomic_write(config_path, updated)
            _, activation_backups = activate_provider(home, args.provider_id, args.model, api_key=args.api_key)
        except Exception:
            if original is None:
                config_path.unlink(missing_ok=True)
            else:
                atomic_write_bytes(config_path, original)
            raise
        return config_path, ([backup] if backup else []) + activation_backups
    backup = backup_file(config_path, "provider-tool")
    atomic_write(config_path, updated)
    return config_path, [backup] if backup else []


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
        print("API key was submitted to Codex for API-key login; the official ChatGPT login snapshot was backed up.")
    if args.activate:
        _, active_data = read_config(config_path)
        active_id = str(active_data.get("model_provider") or args.provider_id)
        print(f"Active provider profile: {args.provider_id}")
        if active_id != args.provider_id:
            print(f"Session identity: {active_id} (preserved for chat history)")
    else:
        print("Active provider: unchanged")
    return 0


def command_use(args: argparse.Namespace) -> int:
    home = resolve_codex_home(args.codex_home)
    config_path = home / "config.toml"
    active_id, backups = activate_provider(
        home, args.provider_id, args.model, args.restore_official_identity, args.api_key,
    )
    print(f"Provider configuration saved: {args.provider_id}")
    if active_id != args.provider_id:
        print(f"Session identity: {active_id} (preserved for chat history)")
    print(f"Config: {config_path}")
    for backup in backups:
        print(f"Backup: {backup}")
    print("Restart Codex to reload the route for existing chats; saved configuration is not a traffic check.")
    return 0


def command_login(args: argparse.Namespace) -> int:
    home = resolve_codex_home(args.codex_home)
    process = launch_codex_login(home, new_console=False)
    return int(process.wait())


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
    add.add_argument("--write-auth", action="store_true", help="save this provider's key locally; copy it to auth.json only when activated")
    add.set_defaults(func=command_add)

    use = subparsers.add_parser("use", help="switch the active provider; use 'openai' for official Cookie/ChatGPT login")
    use.add_argument("provider_id")
    use.add_argument("--model", help="override the top-level model")
    use.add_argument("--api-key", help="submit this relay key to Codex's official API-key login")
    use.add_argument("--restore-official-identity", action="store_true", help="repair old official chats by restoring their original openai identity")
    use.set_defaults(func=command_use)

    login = subparsers.add_parser("login", help="start the official Codex ChatGPT/Cookie login flow")
    login.set_defaults(func=command_login)

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

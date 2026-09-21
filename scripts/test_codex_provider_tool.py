import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from unittest import mock


MODULE_PATH = Path(__file__).with_name("codex_provider_tool.py")
SPEC = importlib.util.spec_from_file_location("codex_provider_tool", MODULE_PATH)
MODULE = importlib.util.module_from_spec(SPEC)
assert SPEC and SPEC.loader
sys.modules["codex_provider_tool"] = MODULE
SPEC.loader.exec_module(MODULE)


class ModelHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path == "/v1/models":
            payload = json.dumps({"data": [{"id": "relay-model"}, {"id": "another-model"}]}).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(payload)))
            self.end_headers()
            self.wfile.write(payload)
            return
        self.send_response(404)
        self.end_headers()

    def log_message(self, *_args):
        return


class CodexProviderToolTests(unittest.TestCase):
    def test_explicit_codex_home_is_used_even_when_empty(self):
        with tempfile.TemporaryDirectory() as directory:
            self.assertEqual(MODULE.resolve_codex_home(directory), Path(directory))

    def test_provider_list_always_includes_official_cookie_login(self):
        data = {
            "model_provider": "custom",
            "model_providers": {
                "custom": {
                    "name": "Relay",
                    "base_url": "https://relay.example/v1",
                    "wire_api": "responses",
                    "requires_openai_auth": True,
                }
            },
        }

        providers = MODULE.get_providers(data)
        official = next(provider for provider in providers if provider.provider_id == MODULE.OFFICIAL_PROVIDER_ID)

        self.assertTrue(official.official)
        self.assertFalse(official.current)
        self.assertEqual(official.name, MODULE.OFFICIAL_PROVIDER_NAME)
        self.assertEqual(official.base_url, "")
        self.assertEqual(len(providers), 2)

    def test_missing_model_provider_is_shown_as_official_current(self):
        providers = MODULE.get_providers({})

        self.assertEqual(len(providers), 1)
        self.assertEqual(providers[0].provider_id, MODULE.OFFICIAL_PROVIDER_ID)
        self.assertTrue(providers[0].current)

    def test_setting_model_does_not_change_provider_or_chat_files(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / "config.toml"
            chat = home / "sessions" / "one.jsonl"
            chat.parent.mkdir()
            config.write_text('model_provider = "openai"\nmodel = "old"\n', encoding="utf-8")
            chat.write_bytes(b"keep")
            backup = MODULE.set_active_model(home, "gpt-6")
            self.assertIsNotNone(backup)
            _, data = MODULE.read_config(config)
            self.assertEqual(data["model_provider"], "openai")
            self.assertEqual(data["model"], "gpt-6")
            self.assertEqual(chat.read_bytes(), b"keep")

    def test_upsert_and_switch_preserve_existing_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / "config.toml"
            config.write_text(
                'model_provider = "OpenAI"\nmodel = "old-model"\n\n'
                '[model_providers.OpenAI]\nname = "OpenAI"\nbase_url = "https://old.example/v1"\n'
                'wire_api = "responses"\nrequires_openai_auth = false\n\n'
                '[features]\ngoals = true\n',
                encoding="utf-8",
            )
            args = MODULE.build_parser().parse_args(
                [
                    "--codex-home",
                    directory,
                    "add",
                    "relay_a",
                    "--base-url",
                    "https://relay.example/v1/v1/",
                    "--model",
                    "relay-model",
                    "--label",
                    "Relay A",
                    "--no-requires-openai-auth",
                    "--activate",
                ]
            )
            self.assertEqual(MODULE.command_add(args), 0)
            text = config.read_text(encoding="utf-8")
            self.assertIn('model_provider = "OpenAI"', text)
            self.assertIn('model = "relay-model"', text)
            self.assertIn('[model_providers.relay_a]', text)
            self.assertIn('base_url = "https://relay.example/v1"', text)
            self.assertIn('[features]', text)
            _, switched_data = MODULE.read_config(config)
            self.assertEqual(switched_data["model_providers"]["OpenAI"]["name"], "Relay A")
            self.assertEqual(switched_data["model_providers"]["relay_a"]["name"], "OpenAI")

            use_args = MODULE.build_parser().parse_args(["--codex-home", directory, "use", "relay_a"])
            self.assertEqual(MODULE.command_use(use_args), 0)
            self.assertIn('model_provider = "OpenAI"', config.read_text(encoding="utf-8"))
            _, restored_data = MODULE.read_config(config)
            self.assertEqual(restored_data["model_providers"]["OpenAI"]["name"], "OpenAI")
            self.assertEqual(restored_data["model_providers"]["relay_a"]["name"], "Relay A")
            self.assertGreaterEqual(len(list(home.glob("config.toml.bak-provider-tool-*"))), 2)

            add_only_args = MODULE.build_parser().parse_args(
                [
                    "--codex-home",
                    directory,
                    "add",
                    "relay_b",
                    "--base-url",
                    "https://relay-b.example/v1",
                    "--model",
                    "relay-b-model",
                ]
            )
            self.assertEqual(MODULE.command_add(add_only_args), 0)
            self.assertIn('model_provider = "OpenAI"', config.read_text(encoding="utf-8"))

    def test_updating_existing_provider_preserves_header_newline(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / "config.toml"
            config.write_text(
                'model_provider = "custom"\nmodel = "old-model"\n\n'
                '[model_providers.custom]\n'
                'name = "Old name"\n'
                'base_url = "https://old.example/v1"\n'
                'wire_api = "responses"\n'
                'requires_openai_auth = true\n',
                encoding="utf-8",
            )
            args = MODULE.build_parser().parse_args(
                [
                    "--codex-home",
                    directory,
                    "add",
                    "custom",
                    "--label",
                    "Updated name",
                    "--base-url",
                    "https://relay.example",
                    "--model",
                    "new-model",
                    "--no-requires-openai-auth",
                    "--activate",
                ]
            )
            self.assertEqual(MODULE.command_add(args), 0)
            text = config.read_text(encoding="utf-8")
            self.assertIn('[model_providers.custom]\nname = "Updated name"', text)
            self.assertNotIn('[model_providers.custom]name', text)
            MODULE.read_config(config)

    def test_add_rejects_reserved_builtin_openai_id(self):
        with tempfile.TemporaryDirectory() as directory:
            args = MODULE.build_parser().parse_args(
                [
                    "--codex-home",
                    directory,
                    "add",
                    MODULE.OFFICIAL_PROVIDER_ID,
                    "--base-url",
                    "https://relay.example/v1",
                    "--model",
                    "relay-model",
                ]
            )
            with self.assertRaisesRegex(MODULE.ToolError, "reserved by Codex"):
                MODULE.upsert_provider(Path(directory), args)

    def test_switch_provider_keeps_session_identity_and_nested_tables(self):
        text = (
            'model_provider = "custom"\nmodel = "model-a"\n\n'
            '[model_providers.custom]\nname = "Provider A"\nbase_url = "https://a.example/v1"\n'
            'wire_api = "responses"\nrequires_openai_auth = false\n'
            'http_headers = { "X-Provider" = "a" }\n\n'
            '[model_providers.custom.auth]\ncommand = "token-a"\nargs = ["--profile", "a"]\n'
            'cwd = "C:/provider-a"\nrefresh_interval_ms = 1000\ntimeout_ms = 1200\n\n'
            '[model_providers.relay_b]\nname = "Provider B"\nbase_url = "https://b.example/v1"\n'
            'wire_api = "responses"\nrequires_openai_auth = true\n'
            'http_headers = { "X-Provider" = "b" }\n\n'
            '[model_providers.relay_b.auth]\ncommand = "token-b"\nargs = ["--profile", "b"]\n'
            'cwd = "C:/provider-b"\nrefresh_interval_ms = 2000\ntimeout_ms = 2400\n'
        )
        import tomllib

        updated, active_id, preserved = MODULE.switch_provider_preserving_history(
            text,
            tomllib.loads(text),
            "relay_b",
        )
        data = tomllib.loads(updated)
        self.assertTrue(preserved)
        self.assertEqual(active_id, "custom")
        self.assertEqual(data["model_provider"], "custom")
        self.assertEqual(data["model_providers"]["custom"]["name"], "Provider B")
        self.assertEqual(data["model_providers"]["custom"]["http_headers"]["X-Provider"], "b")
        self.assertEqual(data["model_providers"]["custom"]["auth"]["command"], "token-b")
        self.assertEqual(data["model_providers"]["custom"]["auth"]["args"], ["--profile", "b"])
        self.assertEqual(data["model_providers"]["custom"]["auth"]["timeout_ms"], 2400)
        self.assertEqual(data["model_providers"]["relay_b"]["name"], "Provider A")
        self.assertEqual(data["model_providers"]["relay_b"]["http_headers"]["X-Provider"], "a")
        self.assertEqual(data["model_providers"]["relay_b"]["auth"]["command"], "token-a")
        self.assertEqual(data["model_providers"]["relay_b"]["auth"]["args"], ["--profile", "a"])
        self.assertEqual(data["model_providers"]["relay_b"]["auth"]["timeout_ms"], 1200)

    def test_official_cookie_switch_preserves_identity_and_all_codex_data(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / "config.toml"
            auth = home / "auth.json"
            sqlite_file = home / "state.sqlite"
            transcript = home / "sessions" / "one.jsonl"
            transcript.parent.mkdir()
            config.write_text(
                'model_provider = "custom"\nmodel = "relay-model"\n\n'
                '[model_providers.custom]\n'
                'name = "Relay"\n'
                'base_url = "https://relay.example/v1"\n'
                'wire_api = "responses"\n'
                'requires_openai_auth = false\n\n'
                '[model_providers.custom.auth]\n'
                'command = "relay-token"\n'
                'args = ["--relay"]\n',
                encoding="utf-8",
            )
            auth.write_text(
                '{"auth_mode":"chatgpt","tokens":{"access_token":"cookie-token","refresh_token":"refresh"}}\n',
                encoding="utf-8",
            )
            sqlite_file.write_bytes(b"sqlite-fixture")
            transcript.write_text('{"type":"message","text":"keep"}\n', encoding="utf-8")
            untouched = {
                auth: auth.read_bytes(),
                sqlite_file: sqlite_file.read_bytes(),
                transcript: transcript.read_bytes(),
            }

            official_args = MODULE.build_parser().parse_args(
                ["--codex-home", directory, "use", MODULE.OFFICIAL_PROVIDER_ID]
            )
            self.assertEqual(MODULE.command_use(official_args), 0)

            _, official_data = MODULE.read_config(config)
            self.assertEqual(official_data["model_provider"], "custom")
            self.assertEqual(
                official_data["model_providers"]["custom"]["name"],
                MODULE.OFFICIAL_PROVIDER_NAME,
            )
            self.assertNotIn("base_url", official_data["model_providers"]["custom"])
            self.assertTrue(official_data["model_providers"]["custom"]["requires_openai_auth"])
            storage_ids = [
                provider_id
                for provider_id, value in official_data["model_providers"].items()
                if value.get("name") == "Relay"
            ]
            self.assertEqual(len(storage_ids), 1)
            relay_storage_id = storage_ids[0]
            self.assertEqual(official_data["model_providers"][relay_storage_id]["auth"]["command"], "relay-token")
            official_card = next(provider for provider in MODULE.get_providers(official_data) if provider.official)
            self.assertTrue(official_card.current)

            relay_args = MODULE.build_parser().parse_args(
                ["--codex-home", directory, "use", relay_storage_id]
            )
            self.assertEqual(MODULE.command_use(relay_args), 0)
            _, restored_data = MODULE.read_config(config)
            self.assertEqual(restored_data["model_provider"], "custom")
            self.assertEqual(restored_data["model_providers"]["custom"]["name"], "Relay")
            self.assertEqual(restored_data["model_providers"]["custom"]["auth"]["command"], "relay-token")

            for path, before in untouched.items():
                self.assertEqual(path.read_bytes(), before)

    def test_builtin_official_switch_removes_only_openai_base_url_override(self):
        text = (
            'openai_base_url = "https://relay.example/v1"\n'
            'service_tier = "fast"\n'
            'model = "gpt-5.6"\n'
        )
        import tomllib

        updated, active_id, preserved = MODULE.switch_provider_preserving_history(
            text,
            tomllib.loads(text),
            MODULE.OFFICIAL_PROVIDER_ID,
        )
        data = tomllib.loads(updated)

        self.assertEqual(active_id, MODULE.OFFICIAL_PROVIDER_ID)
        self.assertTrue(preserved)
        self.assertEqual(data["model_provider"], MODULE.OFFICIAL_PROVIDER_ID)
        self.assertNotIn("openai_base_url", data)
        self.assertEqual(data["service_tier"], "fast")
        self.assertEqual(data["model"], "gpt-5.6")

    @unittest.skipUnless(MODULE.os.name == "nt", "Windows PowerShell launcher test")
    def test_official_login_launcher_uses_pwsh_and_selected_codex_home(self):
        home = Path(r"D:\isolated-codex-home")
        process = mock.Mock()
        with (
            mock.patch.object(
                MODULE.shutil,
                "which",
                side_effect=lambda name: r"C:\Program Files\PowerShell\7\pwsh.exe" if name == "pwsh" else r"C:\tools\codex.ps1",
            ),
            mock.patch.object(MODULE.subprocess, "Popen", return_value=process) as popen,
        ):
            self.assertIs(MODULE.launch_codex_login(home), process)

        command = popen.call_args.args[0]
        options = popen.call_args.kwargs
        self.assertEqual(command[0], r"C:\Program Files\PowerShell\7\pwsh.exe")
        self.assertIn("-NoProfile", command)
        self.assertIn("-NoExit", command)
        script = command[-1]
        self.assertTrue(script.startswith("$ErrorActionPreference = 'Stop'\n$PSNativeCommandUseErrorActionPreference = $true\n"))
        self.assertTrue(script.endswith("codex login"))
        self.assertEqual(options["env"]["CODEX_HOME"], str(home))
        self.assertNotIn("token", script.casefold())
        self.assertNotIn("cookie", script.casefold())
        self.assertNotIn("api_key", script.casefold())

    def test_switch_rejects_missing_current_profile_without_changing_identity(self):
        text = (
            'model_provider = "missing"\nmodel = "gpt-5.5"\n\n'
            '[model_providers.relay]\nname = "Relay"\nbase_url = "https://relay.example/v1"\n'
        )
        import tomllib

        with self.assertRaisesRegex(MODULE.ToolError, "without changing the active model_provider"):
            MODULE.switch_provider_preserving_history(text, tomllib.loads(text), "relay")

    def test_provider_switch_does_not_touch_chat_data_files(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / "config.toml"
            sqlite_file = home / "state.sqlite"
            transcript = home / "sessions" / "one.jsonl"
            transcript.parent.mkdir()
            config.write_text(
                'model_provider = "custom"\nmodel = "old-model"\n\n'
                '[model_providers.custom]\nname = "Old"\nbase_url = "https://old.example/v1"\n'
                'requires_openai_auth = false\n\n'
                '[model_providers.relay]\nname = "New"\nbase_url = "https://new.example/v1"\n'
                'requires_openai_auth = false\n',
                encoding="utf-8",
            )
            sqlite_file.write_bytes(b"sqlite-fixture")
            transcript.write_text('{"type":"message","text":"keep"}\n', encoding="utf-8")
            before_sqlite = sqlite_file.read_bytes()
            before_transcript = transcript.read_bytes()

            args = MODULE.build_parser().parse_args(["--codex-home", directory, "use", "relay"])
            self.assertEqual(MODULE.command_use(args), 0)

            self.assertEqual(sqlite_file.read_bytes(), before_sqlite)
            self.assertEqual(transcript.read_bytes(), before_transcript)

    def test_activating_new_provider_keeps_existing_session_identity(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / "config.toml"
            config.write_text(
                'model_provider = "custom"\nmodel = "old-model"\n\n'
                '[model_providers.custom]\n'
                'name = "Old relay"\n'
                'base_url = "https://old.example/v1"\n'
                'wire_api = "responses"\n'
                'requires_openai_auth = false\n',
                encoding="utf-8",
            )
            args = MODULE.build_parser().parse_args(
                [
                    "--codex-home",
                    directory,
                    "add",
                    "provider_b",
                    "--label",
                    "Provider B",
                    "--base-url",
                    "https://provider-b.example/v1",
                    "--model",
                    "relay-model",
                    "--no-requires-openai-auth",
                    "--activate",
                ]
            )
            self.assertEqual(MODULE.command_add(args), 0)
            _, data = MODULE.read_config(config)
            self.assertEqual(data["model_provider"], "custom")
            self.assertEqual(data["model"], "relay-model")
            self.assertEqual(data["model_providers"]["custom"]["name"], "Provider B")
            self.assertEqual(data["model_providers"]["custom"]["base_url"], "https://provider-b.example/v1")
            self.assertEqual(data["model_providers"]["provider_b"]["name"], "Old relay")

    def test_repairs_collapsed_provider_header_from_older_build(self):
        with tempfile.TemporaryDirectory() as directory:
            config = Path(directory) / "config.toml"
            config.write_text(
                'model_provider = "custom"\nmodel = "model-a"\n\n'
                '[model_providers.custom]name = "OpenAI"\n'
                'base_url = "https://relay.example/v1"\n'
                'wire_api = "responses"\n'
                'requires_openai_auth = true\n',
                encoding="utf-8",
            )
            backup = MODULE.repair_collapsed_provider_headers(config)
            self.assertIsNotNone(backup)
            self.assertTrue(backup.is_file())
            text, data = MODULE.read_config(config)
            self.assertIn('[model_providers.custom]\nname = "OpenAI"', text)
            self.assertEqual(data["model_providers"]["custom"]["name"], "OpenAI")

    def test_probe_reads_models_without_external_dependencies(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = MODULE.Provider("relay", "Relay", f"http://127.0.0.1:{server.server_port}", "responses", True)
            result = MODULE.probe_provider(provider, "test-key", 2)
            self.assertTrue(result.ok)
            self.assertEqual(result.models, ["relay-model", "another-model"])
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_safe_url_removes_query_and_fragment(self):
        self.assertEqual(
            MODULE.safe_url("https://relay.example/v1?key=secret#fragment"),
            "https://relay.example/v1",
        )

    def test_normalize_base_url_adds_and_deduplicates_v1(self):
        cases = {
            "https://relay.example": "https://relay.example/v1",
            "https://relay.example/": "https://relay.example/v1",
            "https://relay.example/v1": "https://relay.example/v1",
            "https://relay.example/v1/v1/": "https://relay.example/v1",
            "https://relay.example/api/v1/v1?key=secret#x": "https://relay.example/api/v1",
        }
        for source, expected in cases.items():
            with self.subTest(source=source):
                self.assertEqual(MODULE.normalize_base_url(source), expected)


if __name__ == "__main__":
    unittest.main()

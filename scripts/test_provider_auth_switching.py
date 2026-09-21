"""Regression tests for built-in OpenAI relay routing and login restoration."""
import json
import os
import tempfile
import tomllib
import unittest
from pathlib import Path
from unittest import mock

import codex_provider_tool as tool


class ProviderAuthSwitchingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.home = Path(self.temp.name)
        self.config = self.home / "config.toml"
        self.auth = self.home / "auth.json"
        self.config.write_text('model = "test-model"\ncli_auth_credentials_store = "file"\n', encoding="utf-8")
        self.original_auth = {"auth_mode": "chatgpt", "tokens": {"access_token": "fake-cookie", "refresh_token": "fake-refresh"}}
        self.auth.write_text(json.dumps(self.original_auth), encoding="utf-8")

        def fake_login(home, key):
            (home / "auth.json").write_text(json.dumps({"auth_mode": "apikey", "OPENAI_API_KEY": key}), encoding="utf-8")

        self.login = mock.patch.object(tool, "codex_login_with_api_key", side_effect=fake_login)
        self.mock_login = self.login.start()
        self.addCleanup(self.login.stop)

    def add_and_activate(self, provider_id="relay_a", key="relay-a-key"):
        args = tool.build_parser().parse_args([
            "--codex-home", str(self.home), "add", provider_id,
            "--base-url", f"https://{provider_id}.example/v1", "--model", "test-model",
            "--api-key", key, "--write-auth", "--activate",
        ])
        return tool.upsert_provider(self.home, args)

    def test_openai_identity_relay_official_round_trip_preserves_chat_files(self):
        history = self.home / "session.jsonl"
        database = self.home / "state.sqlite"
        history.write_bytes(b"original chat")
        database.write_bytes(b"original database")
        self.add_and_activate()
        data = tomllib.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(data["model_provider"], "openai")
        self.assertEqual(data["openai_base_url"], "https://relay_a.example/v1")
        self.assertEqual(json.loads(self.auth.read_text(encoding="utf-8"))["OPENAI_API_KEY"], "relay-a-key")

        tool.activate_provider(self.home, "openai")
        data = tomllib.loads(self.config.read_text(encoding="utf-8"))
        self.assertNotIn("openai_base_url", data)
        self.assertEqual(json.loads(self.auth.read_text(encoding="utf-8")), self.original_auth)
        self.assertEqual(history.read_bytes(), b"original chat")
        self.assertEqual(database.read_bytes(), b"original database")

    def test_missing_key_never_forwards_chatgpt_cookie(self):
        args = tool.build_parser().parse_args([
            "--codex-home", str(self.home), "add", "relay_a", "--base-url", "https://relay.example/v1", "--model", "test-model",
        ])
        tool.upsert_provider(self.home, args)
        before = (self.config.read_bytes(), self.auth.read_bytes())
        with self.assertRaisesRegex(tool.ToolError, "API Key"):
            tool.activate_provider(self.home, "relay_a")
        self.assertEqual((self.config.read_bytes(), self.auth.read_bytes()), before)

    def test_direct_relay_switch_never_reuses_current_provider_key(self):
        self.add_and_activate("relay_a", "relay-a-key")
        args = tool.build_parser().parse_args([
            "--codex-home", str(self.home), "add", "relay_b",
            "--base-url", "https://relay_b.example/v1", "--model", "test-model",
        ])
        tool.upsert_provider(self.home, args)
        before = (self.config.read_bytes(), self.auth.read_bytes())

        with self.assertRaisesRegex(tool.ToolError, "自己保存的 API Key"):
            tool.activate_provider(self.home, "relay_b")

        self.assertEqual((self.config.read_bytes(), self.auth.read_bytes()), before)
        self.assertEqual(json.loads(self.auth.read_text(encoding="utf-8"))["OPENAI_API_KEY"], "relay-a-key")

    def test_direct_relay_round_trip_uses_each_saved_key(self):
        self.add_and_activate("relay_a", "relay-a-key")
        self.add_and_activate("relay_b", "relay-b-key")

        tool.activate_provider(self.home, "relay_a")
        self.assertEqual(json.loads(self.auth.read_text(encoding="utf-8"))["OPENAI_API_KEY"], "relay-a-key")
        tool.activate_provider(self.home, "relay_b")
        self.assertEqual(json.loads(self.auth.read_text(encoding="utf-8"))["OPENAI_API_KEY"], "relay-b-key")

    def test_custom_session_identity_switches_plain_provider_api_keys(self):
        self.config.write_text(
            'model = "test-model"\n'
            'model_provider = "custom"\n'
            'cli_auth_credentials_store = "file"\n\n'
            '[model_providers.custom]\n'
            'name = "Relay A"\n'
            'base_url = "https://relay-a.example/v1"\n'
            'wire_api = "responses"\n'
            'requires_openai_auth = true\n\n'
            '[model_providers.relay_b]\n'
            'name = "Relay B"\n'
            'base_url = "https://relay-b.example/v1"\n'
            'wire_api = "responses"\n'
            'requires_openai_auth = true\n',
            encoding="utf-8",
        )
        self.auth.write_text(json.dumps({"auth_mode": "apikey", "OPENAI_API_KEY": "relay-a-key"}), encoding="utf-8")

        identity, _ = tool.activate_provider(self.home, "relay_b", api_key="relay-b-key")
        data = tomllib.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(identity, "custom")
        self.assertEqual(data["model_provider"], "custom")
        self.assertEqual(data["model_providers"]["custom"]["name"], "Relay B")
        self.assertEqual(json.loads(self.auth.read_text(encoding="utf-8"))["OPENAI_API_KEY"], "relay-b-key")

        identity, _ = tool.activate_provider(self.home, "relay_b")
        data = tomllib.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(identity, "custom")
        self.assertEqual(data["model_provider"], "custom")
        self.assertEqual(data["model_providers"]["custom"]["name"], "Relay A")
        self.assertEqual(json.loads(self.auth.read_text(encoding="utf-8"))["OPENAI_API_KEY"], "relay-a-key")

    def test_custom_provider_auth_table_does_not_replace_global_login(self):
        self.config.write_text(
            'model = "test-model"\n'
            'model_provider = "custom"\n\n'
            '[model_providers.custom]\n'
            'name = "Relay A"\n'
            'base_url = "https://relay-a.example/v1"\n'
            'wire_api = "responses"\n'
            'requires_openai_auth = true\n\n'
            '[model_providers.relay_b]\n'
            'name = "Relay B"\n'
            'base_url = "https://relay-b.example/v1"\n'
            'wire_api = "responses"\n'
            'requires_openai_auth = true\n\n'
            '[model_providers.relay_b.auth]\n'
            'command = "credential-helper"\n',
            encoding="utf-8",
        )
        before_auth = self.auth.read_bytes()
        self.mock_login.reset_mock()

        identity, _ = tool.activate_provider(self.home, "relay_b")

        data = tomllib.loads(self.config.read_text(encoding="utf-8"))
        self.assertEqual(identity, "custom")
        self.assertEqual(data["model_provider"], "custom")
        self.assertEqual(data["model_providers"]["custom"]["auth"]["command"], "credential-helper")
        self.assertEqual(self.auth.read_bytes(), before_auth)
        self.mock_login.assert_not_called()

    def test_latest_backup_uses_timestamp_name_not_preserved_mtime(self):
        older = self.home / "auth.json.bak-provider-tool-test-20260921-010101-000001"
        newer = self.home / "auth.json.bak-provider-tool-test-20260921-010102-000001"
        older.write_text("{}", encoding="utf-8")
        newer.write_text("{}", encoding="utf-8")
        os.utime(older, (200, 200))
        os.utime(newer, (100, 100))

        self.assertEqual(tool.latest_backup(self.auth, "provider-tool-test"), newer)

    def test_repair_old_provider_id_restores_openai_identity(self):
        self.add_and_activate()
        text = self.config.read_text(encoding="utf-8").replace('model_provider = "openai"', 'model_provider = "relay_a"')
        self.config.write_text(text, encoding="utf-8")
        self.auth.write_text(json.dumps(self.original_auth | {"OPENAI_API_KEY": "relay-a-key"}), encoding="utf-8")
        identity, _ = tool.activate_provider(self.home, "relay_a", restore_official_identity=True)
        self.assertEqual(identity, "openai")
        self.assertEqual(tomllib.loads(self.config.read_text(encoding="utf-8"))["openai_base_url"], "https://relay_a.example/v1")

    def test_unsupported_custom_auth_is_rejected_for_builtin_openai(self):
        args = tool.build_parser().parse_args([
            "--codex-home", str(self.home), "add", "relay_a", "--base-url", "https://relay.example/v1", "--model", "test-model",
        ])
        tool.upsert_provider(self.home, args)
        with self.config.open("a", encoding="utf-8") as handle:
            handle.write('\n[model_providers.relay_a.auth]\ncommand = "credential-helper"\n')
        with self.assertRaisesRegex(tool.ToolError, "auth"):
            tool.activate_provider(self.home, "relay_a", api_key="relay-a-key")

    def test_api_login_failure_rolls_back_config_and_auth(self):
        args = tool.build_parser().parse_args([
            "--codex-home", str(self.home), "add", "relay_a", "--base-url", "https://relay.example/v1", "--model", "test-model",
        ])
        tool.upsert_provider(self.home, args)
        before = (self.config.read_bytes(), self.auth.read_bytes())
        with mock.patch.object(tool, "codex_login_with_api_key", side_effect=tool.ToolError("login failed")):
            with self.assertRaisesRegex(tool.ToolError, "login failed"):
                tool.activate_provider(self.home, "relay_a", api_key="relay-a-key")
        self.assertEqual((self.config.read_bytes(), self.auth.read_bytes()), before)

    def test_api_login_wrong_key_state_rolls_back_config_and_auth(self):
        args = tool.build_parser().parse_args([
            "--codex-home", str(self.home), "add", "relay_a", "--base-url", "https://relay.example/v1", "--model", "test-model",
        ])
        tool.upsert_provider(self.home, args)
        before = (self.config.read_bytes(), self.auth.read_bytes())

        def write_wrong_key(home, _key):
            (home / "auth.json").write_text(
                json.dumps({"auth_mode": "apikey", "OPENAI_API_KEY": "wrong-key"}), encoding="utf-8"
            )

        with mock.patch.object(tool, "codex_login_with_api_key", side_effect=write_wrong_key):
            with self.assertRaisesRegex(tool.ToolError, "without activating"):
                tool.activate_provider(self.home, "relay_a", api_key="relay-a-key")
        self.assertEqual((self.config.read_bytes(), self.auth.read_bytes()), before)


if __name__ == "__main__":
    unittest.main()

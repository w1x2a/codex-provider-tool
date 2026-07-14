import importlib.util
import json
import sys
import tempfile
import threading
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path


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

    def test_upsert_and_switch_preserve_existing_tables(self):
        with tempfile.TemporaryDirectory() as directory:
            home = Path(directory)
            config = home / "config.toml"
            config.write_text(
                'model_provider = "OpenAI"\nmodel = "old-model"\n\n'
                '[model_providers.OpenAI]\nname = "OpenAI"\nbase_url = "https://old.example/v1"\n'
                'wire_api = "responses"\nrequires_openai_auth = true\n\n'
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
                    "--activate",
                ]
            )
            self.assertEqual(MODULE.command_add(args), 0)
            text = config.read_text(encoding="utf-8")
            self.assertIn('model_provider = "relay_a"', text)
            self.assertIn('model = "relay-model"', text)
            self.assertIn('[model_providers.relay_a]', text)
            self.assertIn('base_url = "https://relay.example/v1"', text)
            self.assertIn('[features]', text)

            use_args = MODULE.build_parser().parse_args(["--codex-home", directory, "use", "OpenAI"])
            self.assertEqual(MODULE.command_use(use_args), 0)
            self.assertIn('model_provider = "OpenAI"', config.read_text(encoding="utf-8"))
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
                    "--activate",
                ]
            )
            self.assertEqual(MODULE.command_add(args), 0)
            text = config.read_text(encoding="utf-8")
            self.assertIn('[model_providers.custom]\nname = "Updated name"', text)
            self.assertNotIn('[model_providers.custom]name', text)
            MODULE.read_config(config)

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

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
                    "https://relay.example/v1",
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

    def test_probe_reads_models_without_external_dependencies(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        try:
            provider = MODULE.Provider("relay", "Relay", f"http://127.0.0.1:{server.server_port}/v1", "responses", True)
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


if __name__ == "__main__":
    unittest.main()

import json
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
from unittest import mock
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tkinter import ttk


SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

import codex_provider_gui as GUI  # noqa: E402


ProviderApp = GUI.ProviderApp


class ModelHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        if self.path != "/v1/models":
            self.send_response(404)
            self.end_headers()
            return
        payload = json.dumps({"data": [{"id": "relay-model-a"}, {"id": "relay-model-b"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        return


def descendants(widget):
    for child in widget.winfo_children():
        yield child
        yield from descendants(child)


class ProviderGuiTests(unittest.TestCase):
    def test_codex_download_dialog_copies_product_id_and_opens_fallback(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = ProviderApp(root)
            with mock.patch.object(GUI.webbrowser, "open_new_tab") as open_tab:
                app.open_codex_download_dialog()
                dialog = next(item for item in root.winfo_children() if isinstance(item, tk.Toplevel))
                widgets = list(descendants(dialog))
                fallback_button = next(
                    item
                    for item in widgets
                    if isinstance(item, tk.Button) and item.cget("text") == "复制 ID 并打开备用页"
                )
                fallback_button.invoke()
                root.update()
                self.assertEqual(root.clipboard_get(), GUI.CODEX_STORE_PRODUCT_ID)
                open_tab.assert_called_once_with(GUI.CODEX_FALLBACK_STORE_URL)
        finally:
            for child in list(root.winfo_children()):
                try:
                    child.destroy()
                except tk.TclError:
                    pass
            root.destroy()

    def test_recommended_model_prefers_current_then_known_models(self):
        models = ["other", "gpt-5.6-luna", "gpt-5.5"]
        self.assertEqual(GUI.choose_recommended_model(models, "gpt-5.5"), "gpt-5.5")
        self.assertEqual(GUI.choose_recommended_model(models, "missing"), "gpt-5.6-luna")

    def test_provider_dialog_automatically_loads_models(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        root = tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                (home / "config.toml").write_text(
                    'model_provider = "relay"\n'
                    'model = "relay-model-a"\n\n'
                    '[model_providers.relay]\n'
                    'name = "Relay"\n'
                    f'base_url = "http://127.0.0.1:{server.server_port}"\n'
                    'wire_api = "responses"\n'
                    'requires_openai_auth = false\n',
                    encoding="utf-8",
                )
                app = ProviderApp(root)
                app.home_var.set(directory)
                app.refresh()
                app.open_provider_dialog(app.providers["relay"])

                deadline = time.monotonic() + 4
                loaded = False
                while time.monotonic() < deadline and not loaded:
                    root.update()
                    combos = [item for item in descendants(root) if isinstance(item, ttk.Combobox)]
                    loaded = any("relay-model-b" in tuple(combo.cget("values")) for combo in combos)
                    time.sleep(0.03)
                self.assertTrue(loaded, "model combobox was not populated from /models")
        finally:
            for child in list(root.winfo_children()):
                try:
                    child.destroy()
                except tk.TclError:
                    pass
            root.destroy()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)

    def test_one_click_anxiii_add_uses_only_api_key(self):
        server = ThreadingHTTPServer(("127.0.0.1", 0), ModelHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        root = tk.Tk()
        root.withdraw()
        original_url = GUI.DEFAULT_RELAY_BASE_URL
        GUI.DEFAULT_RELAY_BASE_URL = f"http://127.0.0.1:{server.server_port}/v1"
        try:
            with tempfile.TemporaryDirectory() as directory:
                app = ProviderApp(root)
                app.home_var.set(directory)
                app.refresh()
                app.open_add_provider_choice()
                dialog = next(item for item in root.winfo_children() if isinstance(item, tk.Toplevel))
                widgets = list(descendants(dialog))
                key_entry = next(item for item in widgets if isinstance(item, tk.Entry) and item.cget("show") == "*")
                add_button = next(item for item in widgets if isinstance(item, tk.Button) and item.cget("text") == "一键添加并启用")
                key_entry.insert(0, "test-key")
                add_button.invoke()

                config_path = Path(directory) / "config.toml"
                auth_path = Path(directory) / "auth.json"
                deadline = time.monotonic() + 4
                while time.monotonic() < deadline and not (config_path.is_file() and auth_path.is_file()):
                    root.update()
                    time.sleep(0.03)
                self.assertTrue(config_path.is_file())
                self.assertTrue(auth_path.is_file())
                config = config_path.read_text(encoding="utf-8")
                auth = json.loads(auth_path.read_text(encoding="utf-8"))
                self.assertIn('model_provider = "anxiii"', config)
                self.assertIn('model = "relay-model-a"', config)
                self.assertIn(f'base_url = "http://127.0.0.1:{server.server_port}/v1"', config)
                self.assertEqual(auth["OPENAI_API_KEY"], "test-key")
        finally:
            GUI.DEFAULT_RELAY_BASE_URL = original_url
            for child in list(root.winfo_children()):
                try:
                    child.destroy()
                except tk.TclError:
                    pass
            root.destroy()
            server.shutdown()
            server.server_close()
            thread.join(timeout=2)


if __name__ == "__main__":
    unittest.main()

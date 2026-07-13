import json
import sys
import tempfile
import threading
import time
import tkinter as tk
import unittest
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from tkinter import ttk


SCRIPTS = Path(__file__).resolve().parent
sys.path.insert(0, str(SCRIPTS))

from codex_provider_gui import ProviderApp  # noqa: E402


class ModelHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
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
                    f'base_url = "http://127.0.0.1:{server.server_port}/v1"\n'
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


if __name__ == "__main__":
    unittest.main()

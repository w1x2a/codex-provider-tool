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
    def test_add_provider_dialog_is_centered_over_main_window(self):
        root = tk.Tk()
        try:
            app = ProviderApp(root)
            root.geometry("1000x700+120+80")
            root.update()
            app.open_add_provider_choice()
            dialog = next(item for item in root.winfo_children() if isinstance(item, tk.Toplevel))
            root.update()
            root_center = (root.winfo_x() + root.winfo_width() / 2, root.winfo_y() + root.winfo_height() / 2)
            dialog_center = (dialog.winfo_x() + dialog.winfo_width() / 2, dialog.winfo_y() + dialog.winfo_height() / 2)
            self.assertLessEqual(abs(root_center[0] - dialog_center[0]), 12)
            self.assertLessEqual(abs(root_center[1] - dialog_center[1]), 12)
        finally:
            for child in list(root.winfo_children()):
                try:
                    child.destroy()
                except tk.TclError:
                    pass
            root.destroy()

    def test_add_provider_opens_complete_form_without_relay_binding(self):
        root = tk.Tk()
        root.withdraw()
        try:
            app = ProviderApp(root)
            app.open_add_provider_choice()
            dialog = next(item for item in root.winfo_children() if isinstance(item, tk.Toplevel))
            self.assertEqual(dialog.title(), "添加供应商")
            labels = [str(item.cget("text")) for item in descendants(dialog) if isinstance(item, tk.Label)]
            self.assertIn("Provider ID", labels)
            self.assertNotIn("推荐", " ".join(labels))
            buttons = [str(item.cget("text")) for item in descendants(root) if isinstance(item, tk.Button)]
            self.assertNotIn("渠道监控", buttons)
            self.assertFalse(any("打开官网" in text for text in buttons))
        finally:
            for child in list(root.winfo_children()):
                try:
                    child.destroy()
                except tk.TclError:
                    pass
            root.destroy()

    def test_official_cookie_login_card_is_listed_and_launches_codex_login(self):
        root = tk.Tk()
        root.withdraw()
        try:
            with tempfile.TemporaryDirectory() as directory:
                home = Path(directory)
                (home / "config.toml").write_text("", encoding="utf-8")
                app = ProviderApp(root)
                app.home_var.set(directory)
                app.refresh()

                labels = [str(item.cget("text")) for item in descendants(app.card_inner) if isinstance(item, tk.Label)]
                self.assertIn(GUI.OFFICIAL_PROVIDER_NAME, labels)
                self.assertIn("Cookie/ChatGPT", labels)
                login_button = next(
                    item
                    for item in descendants(app.card_inner)
                    if isinstance(item, tk.Button) and item.cget("text") == "官方登录"
                )
                with mock.patch.object(GUI, "launch_codex_login") as launch_login:
                    login_button.invoke()
                    launch_login.assert_called_once_with(home)
        finally:
            for child in list(root.winfo_children()):
                try:
                    child.destroy()
                except tk.TclError:
                    pass
            root.destroy()

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

    def test_recommended_model_prefers_gpt6_when_reported(self):
        self.assertEqual(GUI.choose_recommended_model(["gpt-5.6-sol", "gpt-6", "gpt-6-astra"], "missing"), "gpt-6-astra")

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

if __name__ == "__main__":
    unittest.main()

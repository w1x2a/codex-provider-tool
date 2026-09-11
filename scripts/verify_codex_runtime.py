"""Exercise an installed Codex against a loopback relay with synthetic credentials.

No existing Codex files or remote services are used. Optional --provider-cli verifies
the packaged switcher as well as the real Codex executable.
"""
import argparse
import json
import os
import subprocess
import tempfile
import threading
import tomllib
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

import codex_provider_tool as tool


class Relay(BaseHTTPRequestHandler):
    requests = []

    def do_GET(self):
        payload = json.dumps({"data": [{"id": "test-model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def do_POST(self):
        body = json.loads(self.rfile.read(int(self.headers.get("Content-Length", 0))))
        authorized = self.headers.get("Authorization") == "Bearer test-relay-key"
        credential_kind = ("relay_key" if authorized else "chatgpt_cookie" if self.headers.get("Authorization") == "Bearer fake-cookie"
                           else "missing" if not self.headers.get("Authorization") else "other")
        self.requests.append({"path": self.path, "authorized": authorized, "credential_kind": credential_kind, "model": body.get("model")})
        message = {"id": "msg_test", "type": "message", "role": "assistant", "status": "completed",
                   "content": [{"type": "output_text", "text": "OK", "annotations": []}]}
        events = [
            {"type": "response.created", "response": {"id": "resp_test", "object": "response", "status": "in_progress", "output": []}},
            {"type": "response.output_item.added", "output_index": 0, "item": dict(message, status="in_progress", content=[])},
            {"type": "response.output_text.delta", "item_id": "msg_test", "output_index": 0, "content_index": 0, "delta": "OK"},
            {"type": "response.output_item.done", "output_index": 0, "item": message},
            {"type": "response.completed", "response": {"id": "resp_test", "object": "response", "status": "completed", "output": [message],
                                                          "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2}}},
        ]
        payload = "".join(f"event: {event['type']}\ndata: {json.dumps(event)}\n\n" for event in events).encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *_args):
        pass


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--codex-exe", required=True)
    parser.add_argument("--provider-cli")
    args = parser.parse_args()
    server = ThreadingHTTPServer(("127.0.0.1", 0), Relay)
    worker = threading.Thread(target=server.serve_forever, daemon=True)
    worker.start()
    try:
        with tempfile.TemporaryDirectory(prefix="provider-runtime-") as directory:
            home = Path(directory)
            config = home / "config.toml"
            auth = home / "auth.json"
            config.write_text('model = "test-model"\ncli_auth_credentials_store = "file"\n', encoding="utf-8")
            tokens = {"id_token": "fake-id-token", "access_token": "fake-cookie", "refresh_token": "fake-refresh", "account_id": "test"}
            auth.write_text(json.dumps({"auth_mode": "chatgpt", "tokens": tokens}), encoding="utf-8")
            command = ["--codex-home", directory, "add", "relay", "--base-url", f"http://127.0.0.1:{server.server_port}/v1",
                       "--model", "test-model"]
            if args.provider_cli:
                subprocess.run([args.provider_cli, *command], check=True, capture_output=True, timeout=20)
                subprocess.run([args.provider_cli, "--codex-home", directory, "use", "relay", "--api-key", "test-relay-key"],
                               check=True, capture_output=True, timeout=30)
            else:
                tool.upsert_provider(home, tool.build_parser().parse_args(command))
                tool.activate_provider(home, "relay", api_key="test-relay-key")
            data = tomllib.loads(config.read_text(encoding="utf-8"))
            assert data["model_provider"] == "openai"
            api_auth = json.loads(auth.read_text(encoding="utf-8"))
            env = dict(os.environ, CODEX_HOME=directory, NO_PROXY="127.0.0.1,localhost", no_proxy="127.0.0.1,localhost")
            for key in list(env):
                if (key.startswith("CODEX_") and key != "CODEX_HOME") or key in ("OPENAI_API_KEY", "OPENAI_BASE_URL"):
                    env.pop(key, None)
            status = subprocess.run([args.codex_exe, "login", "status"], cwd=directory, env=env, capture_output=True,
                                    text=True, encoding="utf-8", errors="replace", timeout=15)
            status_text = status.stdout + status.stderr
            status_kind = "chatgpt" if "using ChatGPT" in status_text else "apikey" if "API key" in status_text else "unknown"
            process = subprocess.run(
                [args.codex_exe, "exec", "--ephemeral", "--skip-git-repo-check", "-c", "features.plugins=false", "-m", "test-model", "Reply only OK"],
                cwd=directory, env=env, capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=50,
                creationflags=subprocess.CREATE_NO_WINDOW if os.name == "nt" else 0,
            )
            if process.returncode or not Relay.requests:
                raise RuntimeError(f"Codex runtime verification failed ({process.returncode}): {process.stderr[-1800:]}")
            assert all(request["authorized"] for request in Relay.requests), f"Codex sent the wrong credential (login status={status_kind}, exit={status.returncode}): {Relay.requests}"
            assert any(request["path"] == "/v1/responses" for request in Relay.requests)
            assert "OK" in process.stdout
            if args.provider_cli:
                subprocess.run([args.provider_cli, "--codex-home", directory, "use", "openai"], check=True, capture_output=True, timeout=20)
            else:
                tool.activate_provider(home, "openai")
            restored = json.loads(auth.read_text(encoding="utf-8"))
            assert "openai_base_url" not in tomllib.loads(config.read_text(encoding="utf-8"))
            print(json.dumps({"codex_runtime": "passed", "packaged_switcher": bool(args.provider_cli), "identity": "openai",
                              "relay_requests": Relay.requests, "api_login_fields": sorted(api_auth),
                              "cookie_retained_after_api_login": restored.get("tokens") == tokens,
                              "existing_chat_files_modified": False}))
    finally:
        server.shutdown()
        server.server_close()
        worker.join(timeout=2)


if __name__ == "__main__":
    main()

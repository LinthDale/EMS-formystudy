"""Real HTTP cookie round-trip for the simulator CLI (PRD-0022)."""
import importlib.util
import json
from pathlib import Path

import pytest

spec = importlib.util.spec_from_file_location("sim_cli", Path(__file__).parents[2] / "scripts/simulator_control.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


@pytest.mark.integration
def test_secure_session_real_http_login_list_logout(monkeypatch, capsys):
    """Reproduce production login=200, Secure cookie, HTTP loopback transport."""
    from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
    from threading import Thread
    calls = []
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def reply(self, status, value=None, cookie=False):
            self.send_response(status)
            self.send_header("Content-Type", "application/json")
            if cookie:
                self.send_header("Set-Cookie", "ems_bff_session=test-session; Path=/; Secure; HttpOnly; SameSite=Strict")
            self.end_headers()
            if value is not None:
                self.wfile.write(json.dumps(value).encode())

        def do_POST(self):
            calls.append(self.path)
            payload = json.loads(self.rfile.read(int(self.headers.get("Content-Length", "0"))) or "{}")
            if self.path == "/api/auth/login":
                assert payload == {"username": "tester", "password": "test-only-password"}
                self.reply(200, {"username": "tester", "role": "ops"}, cookie=True)
            else:
                authenticated = self.headers.get("Cookie") == "ems_bff_session=test-session"
                self.reply(204 if authenticated else 401)

        def do_GET(self):
            calls.append(self.path)
            authenticated = self.headers.get("Cookie") == "ems_bff_session=test-session"
            self.reply(200 if authenticated else 401, {"items": []} if authenticated else {"detail": "invalid session"})

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = Thread(target=server.serve_forever, daemon=True)
    thread.start()
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "test-only-password")
    try:
        result = cli.main(["--url", f"http://127.0.0.1:{server.server_port}", "--username", "tester", "list"])
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=3)
    assert result == 0
    assert calls == ["/api/auth/login", "/api/simulators", "/api/auth/logout"]
    output = capsys.readouterr()
    assert "test-session" not in output.out + output.err
    assert "test-only-password" not in output.out + output.err

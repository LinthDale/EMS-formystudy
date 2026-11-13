"""CLI success must survive the BFF's empty 204 logout response."""
import importlib.util
import io
import json
from pathlib import Path
import pytest

spec = importlib.util.spec_from_file_location("sim_cli", Path(__file__).parents[2] / "scripts/simulator_control.py")
cli = importlib.util.module_from_spec(spec)
spec.loader.exec_module(cli)


class Response(io.BytesIO):
    def __init__(self, value, status=200):
        super().__init__(b"" if status == 204 else json.dumps(value).encode())
        self.status = status


@pytest.mark.parametrize("action", ["list", "set"])
def test_successful_command_and_logout_204_exit_zero(monkeypatch, capsys, action):
    requests = []
    class Opener:
        def open(self, req, timeout):
            requests.append(req)
            if req.full_url.endswith("/logout"):
                return Response(None, 204)
            if req.full_url.endswith("/delta-sim-001"):
                return Response({"available": True, "instance_id": "stub-instance", "revision": 0})
            return Response({"status": "succeeded"})
    monkeypatch.setattr(cli, "build_opener", lambda *args: Opener())
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "test-only-password")
    args = ["--username", "tester", action]
    if action == "set":
        args += ["delta-sim-001", "scenario=night", "--reason", "test"]
    assert cli.main(args) == 0
    output = capsys.readouterr()
    assert "not confirmed" not in output.err
    assert "test-only-password" not in output.out + output.err
    assert requests[-1].full_url.endswith("/logout")
    if action == "set":
        commands = [req for req in requests if req.full_url.endswith("/commands")]
        assert len(commands) == 1
        assert json.loads(commands[0].data)["changes"] == {"scenario": "night"}


def test_timeout_never_retries_write_and_still_logs_out(monkeypatch, capsys):
    calls = []
    class Opener:
        def open(self, req, timeout):
            calls.append(req.full_url)
            if req.full_url.endswith("/commands"):
                raise TimeoutError()
            if req.full_url.endswith("/logout"):
                return Response(None, 204)
            return Response({"available": True, "instance_id": "stub-instance", "revision": 0})
    monkeypatch.setattr(cli, "build_opener", lambda *args: Opener())
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "test-password")
    assert cli.main(["--username", "tester", "set", "delta-sim-001", "scenario=night",
                     "--reason", "timeout test"]) == 2
    assert sum(url.endswith("/commands") for url in calls) == 1
    assert calls[-1].endswith("/logout")
    assert "request_id=" in capsys.readouterr().err


def _cookie_jar(origin, *, path="/", expired=False):
    """Use the actual CookieJar parser and selection rules, not a mocked opener."""
    import email.message
    headers = email.message.Message()
    expires = "; Expires=Thu, 01 Jan 1970 00:00:00 GMT" if expired else ""
    headers.add_header("Set-Cookie", f"ems_bff_session=test-session; Path={path}; Secure; HttpOnly{expires}")
    class CookieResponse:
        def info(self):
            return headers
    jar = cli.http.cookiejar.CookieJar(policy=cli.LocalSessionCookiePolicy(origin))
    jar.extract_cookies(CookieResponse(), cli.Request(origin + "/api/auth/login"))
    return jar


@pytest.mark.parametrize("origin,target,expected", [
    ("http://127.0.0.1:8003", "http://127.0.0.1:8003/api/simulators", True),
    ("http://[::1]:8003", "http://[::1]:8003/api/simulators", True),
    ("http://127.0.0.1", "http://127.0.0.1:80/api/simulators", True),
    ("http://127.0.0.1:8003", "http://127.0.0.1:8004/api/simulators", False),
    ("http://127.0.0.1:8003", "http://localhost:8003/api/simulators", False),
    ("http://localhost:8003", "http://localhost:8003/api/simulators", False),
    ("http://192.168.1.20:8003", "http://192.168.1.20:8003/api/simulators", False),
    ("http://example.test", "http://example.test/api/simulators", False),
    ("http://127.0.0.1:8003", "http://example.test:8003/api/simulators", False),
    ("http://127.0.0.1:8003", "http://user@127.0.0.1:8003/api/simulators", False),
    ("https://127.0.0.1:8003", "http://127.0.0.1:8003/api/simulators", False),
    ("https://example.test", "https://example.test/api/simulators", True),
])
def test_secure_cookie_exception_is_limited_to_exact_numeric_loopback(origin, target, expected):
    jar = _cookie_jar(origin)
    assert all(cookie.secure for cookie in jar)
    request = cli.Request(target)
    jar.add_cookie_header(request)
    assert request.has_header("Cookie") is expected
    assert all(cookie.secure for cookie in jar)


@pytest.mark.parametrize("path,expired", [("/other", False), ("/", True)])
def test_local_cookie_exception_keeps_path_and_expiry_checks(path, expired):
    origin = "http://127.0.0.1:8003"
    jar = _cookie_jar(origin, path=path, expired=expired)
    request = cli.Request(origin + "/api/simulators")
    jar.add_cookie_header(request)
    assert not request.has_header("Cookie")




@pytest.mark.parametrize("failed_path,args,label", [
    ("/api/auth/login", ["list"], "Login failed (HTTP 401)"),
    ("/api/simulators", ["list"], "Session rejected (HTTP 401)"),
    ("/delta-sim-001", ["set", "delta-sim-001", "scenario=night", "--reason", "test"], "Session rejected (HTTP 401)"),
])
def test_auth_failure_reports_stage_without_claiming_a_write(monkeypatch, capsys, failed_path, args, label):
    from urllib.error import HTTPError
    calls = []
    class Opener:
        def open(self, req, timeout):
            calls.append(req.full_url)
            if req.full_url.endswith(failed_path):
                raise HTTPError(req.full_url, 401, "Unauthorized", {}, None)
            if req.full_url.endswith("/logout"):
                return Response(None, 204)
            return Response({"status": "succeeded"})
    monkeypatch.setattr(cli, "build_opener", lambda *args: Opener())
    monkeypatch.setattr(cli.getpass, "getpass", lambda prompt: "test-only-password")
    assert cli.main(["--username", "tester", *args]) == 2
    error = capsys.readouterr().err
    assert label in error
    assert "No simulator command was sent" in error
    assert "Do not resend a write" not in error
    assert not any(url.endswith("/commands") for url in calls)

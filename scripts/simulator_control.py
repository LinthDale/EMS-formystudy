#!/usr/bin/env python3
"""OPS simulator client: login, query, configure and reconcile through the BFF."""
import argparse
import getpass
import http.cookiejar
import json
import sys
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode, urlsplit, quote
from urllib.request import Request, build_opener, HTTPCookieProcessor, ProxyHandler, HTTPRedirectHandler
from uuid import UUID, uuid4


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        return None


def _local_http_origin(url: str) -> tuple[str, int] | None:
    """Only numeric loopback avoids DNS/hosts-file trust for this exception."""
    try:
        parsed = urlsplit(url)
        if (parsed.scheme != "http" or parsed.hostname not in ("127.0.0.1", "::1")
                or parsed.username is not None or parsed.password is not None):
            return None
        return parsed.hostname, parsed.port if parsed.port is not None else 80
    except ValueError:
        return None


class LocalSessionCookiePolicy(http.cookiejar.DefaultCookiePolicy):
    """Keep Secure cookies intact; permit only this CLI's exact local HTTP origin."""

    def __init__(self, origin: str):
        super().__init__()
        self._local_origin = _local_http_origin(origin)

    def return_ok_secure(self, cookie, request):
        if (self._local_origin is not None
                and _local_http_origin(request.full_url) == self._local_origin):
            return True
        return super().return_ok_secure(cookie, request)


def parse_changes(items):
    changes = {}
    for item in items:
        key, sep, raw = item.partition("=")
        if not sep or not key or key in changes:
            raise ValueError("expected unique key=value pairs")
        try:
            value = json.loads(raw)
        except json.JSONDecodeError:
            value = raw
        changes[key] = value
    return changes


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--url", default="http://127.0.0.1:8003")
    parser.add_argument("--username", required=True)
    sub = parser.add_subparsers(dest="action", required=True)
    sub.add_parser("list")
    state = sub.add_parser("state")
    state.add_argument("simulator_id")
    configure = sub.add_parser("set")
    configure.add_argument("simulator_id")
    configure.add_argument("changes", nargs="+")
    configure.add_argument("--reason", required=True)
    history = sub.add_parser("history")
    history.add_argument("--limit", type=int, default=20)
    history.add_argument("--before", type=int)
    history.add_argument("--simulator-id")
    operation = sub.add_parser("operation")
    operation.add_argument("request_id")
    reconcile = sub.add_parser("reconcile")
    reconcile.add_argument("request_id")
    reconcile.add_argument("--reason", required=True)
    args = parser.parse_args(argv)
    parsed = urlsplit(args.url)
    if (parsed.username or parsed.password or parsed.query or parsed.fragment
            or parsed.path not in ("", "/") or not parsed.hostname
            or (parsed.scheme != "https" and not (parsed.scheme == "http"
                and parsed.hostname in ("localhost", "127.0.0.1", "::1")))):
        parser.error("--url must be HTTPS or loopback HTTP origin")
    origin = args.url.rstrip("/")
    jar = http.cookiejar.CookieJar(policy=LocalSessionCookiePolicy(origin))
    opener = build_opener(ProxyHandler({}), NoRedirect(), HTTPCookieProcessor(jar))
    stage = "login"
    command_sent = False

    def call(path, payload=None):
        nonlocal command_sent
        data = None if payload is None else json.dumps(payload, allow_nan=False).encode()
        req = Request(origin + path, data=data,
                      headers={"Origin": origin, "Content-Type": "application/json"})
        if payload is not None and path.endswith("/commands"):
            command_sent = True
        with opener.open(req, timeout=15) as response:
            return {} if response.status == 204 else json.load(response)

    try:
        call("/api/auth/login", {"username": args.username, "password": getpass.getpass("EMS password: ")})
        stage = "read"
        try:
            prefix = "/api/simulators"
            if args.action == "list":
                result = call(prefix)
            elif args.action == "state":
                result = call(prefix + "/" + quote(args.simulator_id, safe=""))
            elif args.action == "history":
                query = {k: v for k, v in (("limit", args.limit), ("before", args.before),
                         ("simulator_id", args.simulator_id)) if v is not None}
                result = call(prefix + "/operations?" + urlencode(query))
            elif args.action in ("operation", "reconcile"):
                stage = args.action
                result = call(prefix + "/operations/" + str(UUID(args.request_id)) +
                              ("/reconcile" if args.action == "reconcile" else ""),
                              {"reason": args.reason} if args.action == "reconcile" else None)
            else:
                changes = parse_changes(args.changes)
                path = prefix + "/" + quote(args.simulator_id, safe="")
                state = call(path)
                if not state["available"]:
                    raise ValueError("simulator unavailable")
                request_id = str(uuid4())
                print("request_id=" + request_id, file=sys.stderr, flush=True)
                result = call(path + "/commands",
                              dict(request_id=request_id, expected_instance_id=state["instance_id"],
                                   expected_revision=state["revision"], changes=changes, reason=args.reason))
            print(json.dumps(result, ensure_ascii=False, indent=2))
            return 0 if result.get("status", "succeeded") == "succeeded" else 2
        finally:
            try:
                call("/api/auth/logout", {})
            except (HTTPError, URLError, TimeoutError):
                pass
    except (HTTPError, URLError, TimeoutError, ValueError) as error:
        label = f"HTTP {error.code}" if isinstance(error, HTTPError) else type(error).__name__
        if stage == "login":
            message = f"Login failed ({label}). No simulator command was sent."
        elif command_sent:
            message = f"Request not confirmed ({label}). Do not resend a write; query its request_id."
        elif stage == "reconcile":
            message = f"Reconciliation not confirmed ({label}). Query its request_id; no simulator command was resent."
        elif isinstance(error, HTTPError) and error.code == 401:
            message = (f"Session rejected ({label}). No simulator command was sent. "
                       "For local HTTP use --url http://127.0.0.1:8003; otherwise use HTTPS.")
        else:
            message = f"Request failed ({label}). No simulator command was sent."
        print(message, file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())

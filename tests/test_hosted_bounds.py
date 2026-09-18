"""Issue #229: provael's own serving surface bounds what it accepts, where it binds, what it says.

Three concerns, each pinned: an inbound body past MAX_BODY_BYTES is refused rather than buffered
(one byte over is enough); `provael serve` binds loopback unless `--allow-remote` is given; no
response body ever carries a traceback, a path or a module name. The pure parts (the constants,
the loopback test, the ASGI limiter) run on the CPU core; the FastAPI wiring runs only where the
`hosted` extra is installed, behind the same skip the existing hosted tests use.
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import logging
from typing import Any

import pytest
from typer.testing import CliRunner

from provael.cli import app
from provael.config import RunConfig
from provael.hosted import ENABLE_HOSTED_ENV
from provael.hosted.bounds import (
    ALLOW_REMOTE_FLAG,
    MAX_BODY_BYTES,
    PAYLOAD_TOO_LARGE,
    BodyLimit,
    BodyTooLarge,
    error_body,
    is_loopback,
)
from provael.runner import run

_HAS_FASTAPI = importlib.util.find_spec("fastapi") is not None
# TestClient needs an HTTP client too; a half-installed extra (fastapi without httpx) must
# skip, not fail — CI never installs either, so this only ever bites a local env.
_HAS_TESTCLIENT = _HAS_FASTAPI and any(
    importlib.util.find_spec(name) is not None for name in ("httpx", "httpx2")
)
runner = CliRunner()


def _report():  # noqa: ANN202
    return run(RunConfig(policy="stub", suite="stub", attacks=["none"], episodes=1, seed=0))


# --------------------------------------------------------------------------- #
# the named limit and the loopback rule
# --------------------------------------------------------------------------- #


def test_the_limit_is_a_named_constant_a_reader_can_size_a_report_against() -> None:
    assert MAX_BODY_BYTES == 16 * 1024 * 1024
    assert PAYLOAD_TOO_LARGE == 413


@pytest.mark.parametrize("host", ["127.0.0.1", "127.0.0.2", "::1", "[::1]", "localhost",
                                  "LOCALHOST", " 127.0.0.1 "])
def test_loopback_addresses_are_recognised(host: str) -> None:
    assert is_loopback(host)


# S104: the wildcard is the input under test — the point is that it is REJECTED, not bound.
_NOT_LOOPBACK = ["0.0.0.0", "::", "[::]", "192.168.1.20", "10.0.0.5",  # noqa: S104
                 "example.internal", "", "not an address"]
_WILDCARD = "0.0.0.0"  # noqa: S104 - passed to the CLI to prove it refuses


@pytest.mark.parametrize("host", _NOT_LOOPBACK)
def test_everything_else_is_not_loopback_including_garbage(host: str) -> None:
    """Unparseable input is not loopback: the failure mode of this check is an open port."""
    assert not is_loopback(host)


def test_the_error_shape_is_stable_and_carries_only_what_the_caller_named() -> None:
    body = error_body("payload_too_large", "too big", limit_bytes=3)
    assert body == {"error": {"code": "payload_too_large", "message": "too big", "limit_bytes": 3}}


# --------------------------------------------------------------------------- #
# the ASGI limiter, framework-free
# --------------------------------------------------------------------------- #


class _Harness:
    """Drive an ASGI app with one request and collect what it sent."""

    def __init__(self, chunks: list[bytes], content_length: int | None) -> None:
        self.messages = [{"type": "http.request", "body": c, "more_body": True} for c in chunks]
        if self.messages:
            self.messages[-1]["more_body"] = False
        else:
            self.messages = [{"type": "http.request", "body": b"", "more_body": False}]
        headers = []
        if content_length is not None:
            headers.append((b"content-length", str(content_length).encode()))
        self.scope: dict[str, Any] = {"type": "http", "method": "POST", "path": "/", "headers": headers}
        self.sent: list[dict[str, Any]] = []
        self.app_saw = 0

    async def receive(self) -> dict[str, Any]:
        return self.messages.pop(0)

    async def send(self, message: dict[str, Any]) -> None:
        self.sent.append(dict(message))

    async def echo_app(self, scope: Any, receive: Any, send: Any) -> None:
        """Reads the whole body, then answers 200 with its length."""
        total = 0
        while True:
            message = await receive()
            total += len(message.get("body", b""))
            if not message.get("more_body"):
                break
        self.app_saw = total
        await send({"type": "http.response.start", "status": 200, "headers": []})
        await send({"type": "http.response.body", "body": str(total).encode()})

    def status(self) -> int:
        return int(self.sent[0]["status"])

    def json(self) -> dict[str, Any]:
        return json.loads(self.sent[1]["body"])  # type: ignore[no-any-return]


def _drive(harness: _Harness, limit: int) -> None:
    asyncio.run(BodyLimit(harness.echo_app, max_bytes=limit)(
        harness.scope, harness.receive, harness.send
    ))


def test_a_declared_length_one_byte_over_the_limit_is_refused_before_the_app_runs() -> None:
    h = _Harness([b"x" * 65], content_length=65)
    _drive(h, limit=64)
    assert h.status() == PAYLOAD_TOO_LARGE
    assert h.app_saw == 0, "the body must not be read, let alone buffered"
    assert h.json()["error"] == {
        "code": "payload_too_large",
        "message": "request body is larger than this server accepts",
        "limit_bytes": 64,
        "received_bytes": 65,
    }


def test_a_streamed_body_is_stopped_at_the_first_byte_over_the_limit() -> None:
    """No Content-Length (chunked): the app's receive raises at limit + 1, nothing more is read."""
    h = _Harness([b"x" * 32, b"x" * 32, b"x", b"y" * 1000], content_length=None)
    _drive(h, limit=64)
    assert h.status() == PAYLOAD_TOO_LARGE
    assert h.app_saw == 0, "the app never finished reading, so it never handled the request"
    assert h.messages, "the chunks past the refusal were never pulled off the wire"
    assert h.json()["error"]["received_bytes"] == 65


def test_a_body_exactly_at_the_limit_passes_through() -> None:
    h = _Harness([b"x" * 64], content_length=64)
    _drive(h, limit=64)
    assert h.status() == 200
    assert h.app_saw == 64


def test_the_limiter_leaves_non_http_scopes_alone() -> None:
    seen: list[str] = []

    async def inner(scope: Any, receive: Any, send: Any) -> None:
        seen.append(scope["type"])

    asyncio.run(BodyLimit(inner, max_bytes=1)({"type": "lifespan"}, None, None))  # type: ignore[arg-type]
    assert seen == ["lifespan"]


def test_the_exception_carries_the_stable_body() -> None:
    exc = BodyTooLarge(10, 11)
    assert exc.body()["error"]["code"] == "payload_too_large"
    with pytest.raises(ValueError, match="positive"):
        BodyLimit(lambda *_: None, max_bytes=0)  # type: ignore[arg-type, return-value]


# --------------------------------------------------------------------------- #
# the CLI: loopback by default, explicit opt-in for anything wider
# --------------------------------------------------------------------------- #


def test_serve_refuses_a_wildcard_bind_without_the_opt_in(monkeypatch: pytest.MonkeyPatch) -> None:
    """Checked before any import or start-up, so it holds with or without the extra installed."""
    monkeypatch.delenv(ENABLE_HOSTED_ENV, raising=False)
    result = runner.invoke(app, ["serve", "--host", _WILDCARD])
    assert result.exit_code != 0
    assert "Refusing to bind" in result.output and ALLOW_REMOTE_FLAG in result.output


def test_serve_with_the_opt_in_gets_past_the_bind_check(monkeypatch: pytest.MonkeyPatch) -> None:
    """With the flag the refusal is lifted; the run then stops at the next gate (extra / enable
    flag), which proves the host check was the thing that stopped it before."""
    monkeypatch.delenv(ENABLE_HOSTED_ENV, raising=False)
    result = runner.invoke(app, ["serve", "--host", _WILDCARD, ALLOW_REMOTE_FLAG])
    assert result.exit_code != 0
    assert "Refusing to bind" not in result.output


def test_serve_default_host_is_loopback() -> None:
    from provael.cli.serve import serve

    defaults = {p.name: p.default for p in __import__("inspect").signature(serve).parameters.values()}
    assert is_loopback(defaults["host"])
    assert defaults["allow_remote"] is False


# --------------------------------------------------------------------------- #
# the wired app (needs the `hosted` extra)
# --------------------------------------------------------------------------- #


@pytest.mark.skipif(not _HAS_TESTCLIENT, reason="requires the `hosted` extra and an HTTP client")
def test_the_app_refuses_one_byte_over_and_reads_one_byte_under(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setenv(ENABLE_HOSTED_ENV, "1")
    from fastapi.testclient import TestClient

    from provael.hosted.server import create_app

    client = TestClient(create_app(max_body_bytes=64), raise_server_exceptions=False)
    headers = {"content-type": "application/json"}
    over = client.post("/attest", content=b"{" + b" " * 63 + b"}", headers=headers)  # 65 bytes
    assert over.status_code == PAYLOAD_TOO_LARGE
    assert over.json()["error"]["code"] == "payload_too_large"
    # Exactly at the limit is read: it fails validation (not a report), never the size check.
    at = client.post("/attest", content=b"{" + b" " * 62 + b"}", headers=headers)  # 64 bytes
    assert at.status_code == 422
    assert at.json()["error"]["code"] == "invalid_request"


@pytest.mark.skipif(not _HAS_TESTCLIENT, reason="requires the `hosted` extra and an HTTP client")
def test_the_app_refuses_a_chunked_body_past_the_limit(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENABLE_HOSTED_ENV, "1")
    from fastapi.testclient import TestClient

    from provael.hosted.server import create_app

    client = TestClient(create_app(max_body_bytes=64), raise_server_exceptions=False)

    def chunks():  # noqa: ANN202
        yield b"{" + b" " * 60
        yield b" " * 60 + b"}"

    resp = client.post("/attest", content=chunks(), headers={"content-type": "application/json"})
    assert resp.status_code == PAYLOAD_TOO_LARGE
    assert resp.json()["error"]["limit_bytes"] == 64


@pytest.mark.skipif(not _HAS_TESTCLIENT, reason="requires the `hosted` extra and an HTTP client")
def test_validation_errors_do_not_echo_the_input(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv(ENABLE_HOSTED_ENV, "1")
    from fastapi.testclient import TestClient

    from provael.hosted.server import create_app

    client = TestClient(create_app(), raise_server_exceptions=False)
    secret = "s3cr3t-value-that-must-not-come-back"  # noqa: S105 - a marker, not a credential
    resp = client.post("/attest", json={"policy": secret, "unexpected": secret})
    assert resp.status_code == 422
    body = resp.json()
    assert body["error"]["code"] == "invalid_request"
    assert body["error"]["errors"] and {"loc", "msg", "type"} == set(body["error"]["errors"][0])
    assert secret not in resp.text, "FastAPI's default reflects the input; ours must not"


@pytest.mark.skipif(not _HAS_TESTCLIENT, reason="requires the `hosted` extra and an HTTP client")
def test_an_internal_failure_is_logged_with_its_traceback_and_answered_without_it(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    monkeypatch.setenv(ENABLE_HOSTED_ENV, "1")
    from fastapi.testclient import TestClient

    import provael.hosted.server as server

    def explode(*_args: Any, **_kwargs: Any) -> Any:
        raise RuntimeError("boom from /srv/provael/secret_module.py")

    monkeypatch.setattr(server, "to_bundle", explode)
    client = TestClient(server.create_app(), raise_server_exceptions=False)
    with caplog.at_level(logging.ERROR, logger="provael.hosted"):
        resp = client.post("/attest", json=_report().model_dump(mode="json"))
    assert resp.status_code == 500
    body = resp.json()["error"]
    assert body["code"] == "internal_error" and len(body["request_id"]) == 32
    for leak in ("Traceback", "boom", "secret_module", ".py", "RuntimeError"):
        assert leak not in resp.text, f"{leak!r} reached the response body"
    logged = "\n".join(f"{r.getMessage()}\n{r.exc_text or ''}" for r in caplog.records)
    assert body["request_id"] in logged and "secret_module.py" in logged, (
        "the traceback belongs in the operator's log, keyed by the request id"
    )

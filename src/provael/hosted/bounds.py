# SPDX-License-Identifier: Apache-2.0
# Copyright (c) 2026 Sattyam Jain
"""Resource bounds for provael's own serving surface (issue #229).

The findings that motivated this were made against another project's policy server — a websocket
frame cap disabled, a wildcard bind with no authentication in front, a stack trace in an error
body — and they generalise: a serving layer that sits in front of anything kinetic must bound what
it accepts, bind where it was told to and nowhere wider, and never describe its own internals to
a caller. Provael's reference server is HTTP-only and moves no actuator, but it is the one serving
surface this project ships, so the same three bounds apply to it first.

Everything here is framework-free on purpose: the limits are named constants, the loopback test is
a pure function, and :class:`BodyLimit` is plain ASGI, so all three are unit-tested on the CPU core
without the ``[hosted]`` extra. :mod:`provael.hosted.server` only wires them in.
"""

from __future__ import annotations

import ipaddress
import json
from collections.abc import Awaitable, Callable, MutableMapping
from typing import Any

#: The largest request body the server will read, in bytes. A LIBERO shard's ``report.json`` with
#: per-step trajectories is a few hundred kilobytes; a 4,000-episode combined report is ~20 MB and
#: is not something this endpoint is for. Anything larger is refused with 413, not buffered.
MAX_BODY_BYTES = 16 * 1024 * 1024

#: Hostnames that resolve to the local machine and nothing else. Any other bind address is a
#: wider exposure and needs the explicit ``--allow-remote`` opt-in on ``provael serve``.
LOOPBACK_HOSTS = frozenset({"localhost"})

#: The CLI flag that lifts the loopback-only default. Named here so the refusal message and the
#: option definition cannot drift apart.
ALLOW_REMOTE_FLAG = "--allow-remote"

#: HTTP status for a refused body: RFC 9110 "Content Too Large".
PAYLOAD_TOO_LARGE = 413

Scope = MutableMapping[str, Any]
Message = MutableMapping[str, Any]
Receive = Callable[[], Awaitable[Message]]
Send = Callable[[Message], Awaitable[None]]
ASGIApp = Callable[[Scope, Receive, Send], Awaitable[None]]


def is_loopback(host: str) -> bool:
    """True only for an address that reaches the local machine alone.

    Accepts the literal loopback names and any address inside the loopback ranges (``127.0.0.0/8``,
    ``::1``), with or without IPv6 brackets. A wildcard (``0.0.0.0``, ``::``), a LAN address or a
    hostname other than ``localhost`` is not loopback, and an unparseable string is treated as
    not-loopback — the safe direction for a check whose failure mode is an open port.
    """
    candidate = host.strip().lower()
    if candidate.startswith("[") and candidate.endswith("]"):
        candidate = candidate[1:-1]
    if candidate in LOOPBACK_HOSTS:
        return True
    try:
        return ipaddress.ip_address(candidate).is_loopback
    except ValueError:
        return False


def error_body(code: str, message: str, **detail: Any) -> dict[str, Any]:
    """The one error shape every refusal and failure uses: ``{"error": {"code", "message", …}}``.

    Stable and content-free about the server: a code a client can branch on, a sentence a person
    can read, and only the details named by the caller — never an exception string, a path, or a
    module name.
    """
    return {"error": {"code": code, "message": message, **detail}}


class BodyTooLarge(Exception):
    """Raised by :class:`BodyLimit` at the first byte past the limit on a streamed body."""

    def __init__(self, limit_bytes: int, received_bytes: int) -> None:
        super().__init__(f"request body exceeds {limit_bytes} bytes")
        self.limit_bytes = limit_bytes
        self.received_bytes = received_bytes

    def body(self) -> dict[str, Any]:
        return error_body(
            "payload_too_large",
            "request body is larger than this server accepts",
            limit_bytes=self.limit_bytes,
            received_bytes=self.received_bytes,
        )


def _content_length(scope: Scope) -> int | None:
    for name, value in scope.get("headers", ()):
        if bytes(name).lower() == b"content-length":
            try:
                return int(bytes(value).decode("latin-1").strip())
            except ValueError:
                return None
    return None


async def _send_json(send: Send, status: int, payload: dict[str, Any]) -> None:
    body = json.dumps(payload, separators=(",", ":")).encode("utf-8")
    await send({
        "type": "http.response.start",
        "status": status,
        "headers": [
            (b"content-type", b"application/json"),
            (b"content-length", str(len(body)).encode("ascii")),
        ],
    })
    await send({"type": "http.response.body", "body": body})


class BodyLimit:
    """Pure-ASGI middleware that refuses a request body larger than ``max_bytes``.

    Two checks, because bodies arrive two ways. A declared ``Content-Length`` above the limit is
    refused with 413 before a single body byte is read — the request never reaches the app. A
    streamed body with no usable length is counted as it arrives, and the first byte over the
    limit raises :class:`BodyTooLarge` out of the app's ``receive`` — so the app stops reading at
    limit + 1, nothing past it is buffered, and the framework's handler for that exception (or,
    absent one, this middleware) answers 413. Non-HTTP scopes pass through untouched.
    """

    def __init__(self, app: ASGIApp, max_bytes: int = MAX_BODY_BYTES) -> None:
        if max_bytes < 1:
            raise ValueError("max_bytes must be positive")
        self.app = app
        self.max_bytes = max_bytes

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope.get("type") != "http":
            await self.app(scope, receive, send)
            return

        declared = _content_length(scope)
        if declared is not None and declared > self.max_bytes:
            await _send_json(send, PAYLOAD_TOO_LARGE, BodyTooLarge(self.max_bytes, declared).body())
            return

        seen = 0
        started = False
        tripped: BodyTooLarge | None = None

        async def limited_receive() -> Message:
            nonlocal seen, tripped
            message = await receive()
            if message.get("type") == "http.request":
                seen += len(message.get("body", b""))
                if seen > self.max_bytes:
                    tripped = BodyTooLarge(self.max_bytes, seen)
                    raise tripped
            return message

        async def tracking_send(message: Message) -> None:
            # A framework may turn the exception raised out of `receive` into its own error
            # response (FastAPI answers 400 "error parsing the body"). Whatever it decided, the
            # caller gets the 413 with the stable shape: the first response the app starts after
            # the trip is replaced, and the rest of that response is dropped.
            nonlocal started
            if tripped is not None:
                if message.get("type") == "http.response.start" and not started:
                    started = True
                    await _send_json(send, PAYLOAD_TOO_LARGE, tripped.body())
                return
            if message.get("type") == "http.response.start":
                started = True
            await send(message)

        try:
            await self.app(scope, limited_receive, tracking_send)
        except BodyTooLarge as exc:
            if started:
                raise
            await _send_json(send, PAYLOAD_TOO_LARGE, exc.body())


__all__ = [
    "ALLOW_REMOTE_FLAG",
    "LOOPBACK_HOSTS",
    "MAX_BODY_BYTES",
    "PAYLOAD_TOO_LARGE",
    "BodyLimit",
    "BodyTooLarge",
    "error_body",
    "is_loopback",
]

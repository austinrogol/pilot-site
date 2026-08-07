"""The HTTP boundary.

Split out from the client for one reason: the API key must exist in exactly one
place. The transport is the only object that ever sees it. It injects the key
into the outbound query string and it is never returned, never cached, never
placed in a provenance record, and never included in an exception message --
`redact()` scrubs it out of any URL before that URL reaches a log line.

The second reason is testability. `FixtureTransport` replays recorded response
bodies, so the whole client -- governor, cache, parsing, provenance -- can be
exercised end to end without a network route or a key. The phase 1 proof runs
on real FMP bodies captured from this account through FMP's MCP server.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol

import httpx


class TransportError(RuntimeError):
    """A transport-level failure. Never carries the API key."""


@dataclass(frozen=True)
class Response:
    status: int
    body: Any
    url: str  # already redacted


def redact(url: str, api_key: str | None) -> str:
    """Remove the API key from a URL so it is safe to log or raise."""
    if not api_key:
        return url
    return url.replace(api_key, "<FMP_API_KEY>")


class Transport(Protocol):
    async def get(self, url: str, params: dict[str, Any]) -> Response: ...
    async def aclose(self) -> None: ...


class HttpxTransport:
    """The real thing. FMP takes its key as an ``apikey`` query parameter."""

    def __init__(self, api_key: str, timeout_seconds: float = 20.0):
        if not api_key:
            raise ValueError("HttpxTransport requires an API key")
        self._api_key = api_key
        self._client = httpx.AsyncClient(
            timeout=timeout_seconds,
            headers={"User-Agent": "edgeloop2/0.1 (research)"},
        )

    async def get(self, url: str, params: dict[str, Any]) -> Response:
        outbound = {**params, "apikey": self._api_key}
        try:
            raw = await self._client.get(url, params=outbound)
        except httpx.HTTPError as exc:
            raise TransportError(
                f"{type(exc).__name__} calling {redact(url, self._api_key)}: "
                f"{redact(str(exc), self._api_key)}"
            ) from None

        safe_url = redact(str(raw.url), self._api_key)
        try:
            body = raw.json()
        except json.JSONDecodeError:
            # FMP returns an HTML error page for some auth failures.
            snippet = raw.text[:200].replace("\n", " ")
            raise TransportError(
                f"non-JSON response ({raw.status_code}) from {safe_url}: {snippet!r}"
            ) from None
        return Response(status=raw.status_code, body=body, url=safe_url)

    async def aclose(self) -> None:
        await self._client.aclose()


class FixtureTransport:
    """Replays recorded bodies from disk. No network, no key.

    Fixture files are named after the registry key: ``fixtures/quote.json``.
    A request for a fixture that does not exist raises rather than returning
    empty, so a missing recording can never be mistaken for a company that has
    no data.
    """

    def __init__(self, fixture_dir: Path, record_calls: list[str] | None = None):
        self.fixture_dir = Path(fixture_dir)
        self.calls: list[str] = record_calls if record_calls is not None else []

    async def get(self, url: str, params: dict[str, Any]) -> Response:
        key = url.rstrip("/").split("/stable/", 1)[-1].replace("/", "-")
        self.calls.append(key)
        path = self.fixture_dir / f"{key}.json"
        if not path.exists():
            raise TransportError(
                f"no fixture at {path} for {url}. Fixtures are recorded response "
                "bodies; a missing one means this endpoint was never captured, "
                "not that the symbol has no data."
            )
        return Response(status=200, body=json.loads(path.read_text()), url=url)

    async def aclose(self) -> None:
        return None

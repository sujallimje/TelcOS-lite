"""
src/federation/client.py
------------------------
TelcOS Lite – TMF621 Federation Client.

Async HTTP client responsible for dispatching a ``TMF621Payload`` to the
downstream mock-ServiceNow integration endpoint.

Retry policy:
    • 3 attempts total (1 initial + 2 retries)
    • Exponential back-off: 0.5 s, 1.0 s
    • Retries on HTTP 5xx and network-level transport errors
    • Hard per-request timeout: 10 s (well within the 30-second SLA budget)
"""

from __future__ import annotations

import logging
from typing import Final

import httpx

from src.federation.mapper import TMF621Payload

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

_DEFAULT_BASE_URL: Final[str] = "http://localhost:8080"
_TICKET_ENDPOINT: Final[str] = "/api/v1/mock-servicenow/tmf621/ticket"

_MAX_ATTEMPTS: Final[int] = 3
_BACKOFF_FACTOR: Final[float] = 0.5   # seconds; doubles each retry
_REQUEST_TIMEOUT: Final[float] = 10.0  # seconds


# ---------------------------------------------------------------------------
# Exceptions
# ---------------------------------------------------------------------------

class FederationError(Exception):
    """Raised when all retry attempts to post a TMF621 ticket are exhausted."""

    def __init__(self, message: str, last_status: int | None = None) -> None:
        super().__init__(message)
        self.last_status = last_status


# ---------------------------------------------------------------------------
# Client
# ---------------------------------------------------------------------------

class TMF621Client:
    """
    Async HTTP client for the TMF621 trouble-ticket federation endpoint.

    The client owns its own ``httpx.AsyncClient`` lifecycle and should be
    used as an async context manager to ensure deterministic connection-pool
    teardown::

        async with TMF621Client(base_url="http://servicenow-proxy:8080") as client:
            result = await client.post_ticket(payload)

    Alternatively, call :meth:`aclose` explicitly when context-manager usage
    is not possible.
    """

    def __init__(
        self,
        base_url: str = _DEFAULT_BASE_URL,
        timeout: float = _REQUEST_TIMEOUT,
        max_attempts: int = _MAX_ATTEMPTS,
        backoff_factor: float = _BACKOFF_FACTOR,
    ) -> None:
        """
        Initialise the client.

        Args:
            base_url:       Base URL of the ServiceNow proxy service.
            timeout:        Per-request timeout in seconds.
            max_attempts:   Total number of dispatch attempts (retries = max_attempts - 1).
            backoff_factor: Base sleep duration (seconds) between retries;
                            actual sleep = backoff_factor * 2^(attempt_index).
        """
        self._base_url = base_url.rstrip("/")
        self._timeout = timeout
        self._max_attempts = max_attempts
        self._backoff_factor = backoff_factor

        self._http: httpx.AsyncClient = httpx.AsyncClient(
            base_url=self._base_url,
            timeout=httpx.Timeout(self._timeout),
            headers={
                "Content-Type": "application/json",
                "Accept": "application/json",
                "X-Source-System": "TelcOS-Lite",
            },
        )

    # ------------------------------------------------------------------
    # Context-manager support
    # ------------------------------------------------------------------

    async def __aenter__(self) -> "TMF621Client":
        return self

    async def __aexit__(self, *_: object) -> None:
        await self.aclose()

    async def aclose(self) -> None:
        """Release the underlying HTTP connection pool."""
        await self._http.aclose()

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    async def post_ticket(self, payload: TMF621Payload) -> dict:
        """
        POST a TMF621 ticket to the downstream integration endpoint.

        Implements a bounded retry loop with exponential back-off.  The method
        re-raises :class:`FederationError` only after all attempts are
        exhausted so callers can decide whether to dead-letter the event.

        Args:
            payload: Validated ``TMF621Payload`` produced by ``TMF621Mapper``.

        Returns:
            Parsed JSON response body from the downstream service.

        Raises:
            FederationError: All ``max_attempts`` have been exhausted without
                a successful 2xx response.
        """
        import asyncio  # stdlib – deferred to minimise module-level overhead

        body: str = payload.model_dump_json()
        last_exc: Exception | None = None
        last_status: int | None = None

        for attempt in range(1, self._max_attempts + 1):
            try:
                response = await self._http.post(
                    _TICKET_ENDPOINT,
                    content=body,
                )
                last_status = response.status_code

                if response.is_success:
                    logger.info(
                        "TMF621 ticket posted successfully",
                        extra={
                            "ticket_id": payload.id,
                            "http_status": last_status,
                            "attempt": attempt,
                            "endpoint": f"{self._base_url}{_TICKET_ENDPOINT}",
                        },
                    )
                    return response.json()

                # 4xx errors are not retried – they indicate a client-side fault
                if 400 <= last_status < 500:
                    logger.error(
                        "TMF621 client error – will not retry",
                        extra={
                            "ticket_id": payload.id,
                            "http_status": last_status,
                            "attempt": attempt,
                            "response_body": response.text[:512],
                        },
                    )
                    raise FederationError(
                        f"Non-retryable HTTP {last_status} from federation endpoint.",
                        last_status=last_status,
                    )

                # 5xx – log and fall through to retry logic
                logger.warning(
                    "TMF621 server error – scheduling retry",
                    extra={
                        "ticket_id": payload.id,
                        "http_status": last_status,
                        "attempt": attempt,
                        "max_attempts": self._max_attempts,
                        "response_body": response.text[:512],
                    },
                )
                last_exc = FederationError(
                    f"HTTP {last_status} from federation endpoint.",
                    last_status=last_status,
                )

            except httpx.TransportError as exc:
                last_exc = exc
                logger.warning(
                    "TMF621 transport error – scheduling retry",
                    extra={
                        "ticket_id": payload.id,
                        "attempt": attempt,
                        "max_attempts": self._max_attempts,
                        "error": str(exc),
                    },
                )

            except FederationError:
                # Non-retryable 4xx – re-raise immediately
                raise

            # Back-off before next attempt (skip sleep after the final attempt)
            if attempt < self._max_attempts:
                sleep_secs: float = self._backoff_factor * (2 ** (attempt - 1))
                logger.debug(
                    "Retry back-off",
                    extra={
                        "ticket_id": payload.id,
                        "sleep_seconds": sleep_secs,
                        "next_attempt": attempt + 1,
                    },
                )
                await asyncio.sleep(sleep_secs)

        # All attempts exhausted
        logger.error(
            "TMF621 ticket dispatch failed – all attempts exhausted",
            extra={
                "ticket_id": payload.id,
                "max_attempts": self._max_attempts,
                "last_http_status": last_status,
                "last_error": str(last_exc),
            },
        )
        raise FederationError(
            f"Failed to post TMF621 ticket '{payload.id}' after "
            f"{self._max_attempts} attempts. Last status: {last_status}.",
            last_status=last_status,
        ) from last_exc 
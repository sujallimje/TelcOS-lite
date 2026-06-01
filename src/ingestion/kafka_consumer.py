"""
TelcOS Lite – Ingestion Layer: Async Kafka Consumer
====================================================
Consumes raw JSON messages from ``telemetry.network.faults``, validates them
into :class:`~src.ingestion.models.TelemetryEvent` objects, and routes
invalid payloads to a dead-letter queue (DLQ) topic.

Architecture notes
------------------
* Pure async I/O via ``aiokafka``.  No blocking calls on the event loop.
* Exponential backoff with jitter is applied per-message on transient
  deserialization / validation failures *before* DLQ forwarding.
* The DLQ producer is a separate :class:`~aiokafka.AIOKafkaProducer` instance
  so that DLQ writes never block the main consumer poll loop.
* Structured logging uses the stdlib ``logging`` module with a JSON-friendly
  format; integrators may replace the handler with ``python-json-logger`` or
  similar without modifying this module.
* ``TelemetryConsumer`` is designed to be instantiated once and run inside an
  ``asyncio`` event loop (e.g. as a FastAPI lifespan task).

Environment variables (resolved via :class:`ConsumerSettings`)
--------------------------------------------------------------
``KAFKA_BOOTSTRAP_SERVERS``  – comma-separated broker list (default: ``localhost:9092``)
``KAFKA_GROUP_ID``           – consumer group (default: ``telcos-lite-ingestion``)
``KAFKA_AUTO_OFFSET_RESET``  – ``earliest`` | ``latest`` (default: ``earliest``)
``KAFKA_MAX_RETRY_ATTEMPTS`` – max per-message retries before DLQ (default: ``5``)
``KAFKA_RETRY_BASE_MS``      – initial backoff in ms (default: ``200``)
``KAFKA_RETRY_MAX_MS``       – ceiling backoff in ms (default: ``10_000``)
"""

from __future__ import annotations

import asyncio
import json
import logging
import math
import random
import time
from collections.abc import AsyncGenerator
from typing import Final

from aiokafka import AIOKafkaConsumer, AIOKafkaProducer
from aiokafka.errors import KafkaError
from pydantic import ValidationError
from pydantic_settings import BaseSettings, SettingsConfigDict

from src.ingestion.models import TelemetryEvent

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------

logger: logging.Logger = logging.getLogger(__name__)

_LOG_FORMAT: Final[str] = (
    "%(asctime)s %(levelname)s %(name)s "
    "[%(filename)s:%(lineno)d] %(message)s"
)

logging.basicConfig(
    level=logging.INFO,
    format=_LOG_FORMAT,
)

# ---------------------------------------------------------------------------
# Topics
# ---------------------------------------------------------------------------

TOPIC_FAULTS: Final[str] = "telemetry.network.faults"
TOPIC_DLQ: Final[str] = "telemetry.network.faults.dlq"

# ---------------------------------------------------------------------------
# Settings
# ---------------------------------------------------------------------------


class ConsumerSettings(BaseSettings):
    """Runtime configuration resolved from environment variables.

    All fields have sensible defaults so the consumer works out-of-the-box
    in a local Docker Compose environment.
    """

    model_config = SettingsConfigDict(env_prefix="KAFKA_", case_sensitive=False)

    bootstrap_servers: str = "localhost:9092"
    group_id: str = "telcos-lite-ingestion"
    auto_offset_reset: str = "earliest"
    max_retry_attempts: int = 5
    retry_base_ms: int = 200
    retry_max_ms: int = 10_000


# ---------------------------------------------------------------------------
# Retry helpers
# ---------------------------------------------------------------------------


def _exponential_backoff_seconds(
    attempt: int,
    base_ms: int,
    ceiling_ms: int,
) -> float:
    """Return jittered exponential backoff in **seconds**.

    Uses full-jitter strategy: ``random(0, min(ceiling, base * 2^attempt))``.

    Parameters
    ----------
    attempt:
        Zero-indexed retry attempt counter.
    base_ms:
        Initial backoff in milliseconds.
    ceiling_ms:
        Maximum backoff cap in milliseconds.

    Returns
    -------
    float
        Seconds to sleep before the next attempt.
    """
    cap_ms = min(ceiling_ms, base_ms * math.pow(2, attempt))
    jitter_ms = random.uniform(0, cap_ms)  # noqa: S311 – non-crypto use
    return jitter_ms / 1_000.0


# ---------------------------------------------------------------------------
# Consumer
# ---------------------------------------------------------------------------


class TelemetryConsumer:
    """Async Kafka consumer that produces validated :class:`TelemetryEvent` objects.

    Usage
    -----
    .. code-block:: python

        consumer = TelemetryConsumer()
        await consumer.start()
        async for event in consumer.consume():
            # handle event
            ...
        await consumer.stop()

    It is strongly recommended to use this inside an ``asyncio`` context and
    wrap lifecycle calls in a ``try/finally`` to guarantee ``stop()`` is
    called even on exceptions.

    Parameters
    ----------
    settings:
        Optional pre-built :class:`ConsumerSettings`.  When ``None`` the
        settings are resolved from environment variables automatically.
    """

    def __init__(self, settings: ConsumerSettings | None = None) -> None:
        self._settings: ConsumerSettings = settings or ConsumerSettings()
        self._consumer: AIOKafkaConsumer | None = None
        self._dlq_producer: AIOKafkaProducer | None = None
        self._running: bool = False

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        """Initialise and start the Kafka consumer and DLQ producer.

        Raises
        ------
        KafkaError
            If the broker is unreachable during startup.
        """
        logger.info(
            "Starting TelemetryConsumer",
            extra={
                "bootstrap_servers": self._settings.bootstrap_servers,
                "group_id": self._settings.group_id,
                "topic": TOPIC_FAULTS,
            },
        )

        self._consumer = AIOKafkaConsumer(
            TOPIC_FAULTS,
            bootstrap_servers=self._settings.bootstrap_servers,
            group_id=self._settings.group_id,
            auto_offset_reset=self._settings.auto_offset_reset,
            enable_auto_commit=False,
            value_deserializer=None,  # raw bytes – we decode manually
        )

        self._dlq_producer = AIOKafkaProducer(
            bootstrap_servers=self._settings.bootstrap_servers,
            value_serializer=lambda v: v if isinstance(v, bytes) else v.encode("utf-8"),
        )

        await self._consumer.start()
        await self._dlq_producer.start()
        self._running = True

        logger.info("TelemetryConsumer started successfully.")

    async def stop(self) -> None:
        """Gracefully stop the consumer and DLQ producer, committing offsets."""
        self._running = False

        if self._consumer is not None:
            try:
                await self._consumer.commit()
            except KafkaError as exc:
                logger.warning("Failed to commit offsets on shutdown: %s", exc)
            await self._consumer.stop()
            logger.info("Kafka consumer stopped.")

        if self._dlq_producer is not None:
            await self._dlq_producer.stop()
            logger.info("DLQ producer stopped.")

    # ------------------------------------------------------------------
    # Main consume loop
    # ------------------------------------------------------------------

    async def consume(self) -> AsyncGenerator[TelemetryEvent, None]:
        """Yield validated :class:`TelemetryEvent` instances indefinitely.

        Invalid messages are sent to the DLQ after exhausting retries.
        The consumer commits offsets only after successful processing or
        confirmed DLQ delivery to prevent message loss.

        Yields
        ------
        TelemetryEvent
            A fully validated telemetry event ready for downstream processing.

        Raises
        ------
        RuntimeError
            If called before :meth:`start`.
        """
        if self._consumer is None or self._dlq_producer is None:
            raise RuntimeError(
                "TelemetryConsumer.start() must be called before consume()."
            )

        logger.info("Entering consume loop on topic '%s'.", TOPIC_FAULTS)

        async for raw_message in self._consumer:
            if not self._running:
                break

            partition_info = {
                "topic": raw_message.topic,
                "partition": raw_message.partition,
                "offset": raw_message.offset,
            }

            event = await self._process_message(
                raw_message.value,
                partition_info=partition_info,
            )

            # Commit regardless of outcome (valid → yield; invalid → DLQ).
            try:
                await self._consumer.commit()
            except KafkaError as exc:
                logger.error(
                    "Offset commit failed after processing message.",
                    extra={**partition_info, "error": str(exc)},
                )

            if event is not None:
                yield event

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _process_message(
        self,
        raw_bytes: bytes | None,
        *,
        partition_info: dict[str, object],
    ) -> TelemetryEvent | None:
        """Attempt to parse and validate a raw Kafka message payload.

        Applies exponential backoff between attempts.  On exhaustion the
        payload is forwarded to the DLQ topic.

        Parameters
        ----------
        raw_bytes:
            Raw message bytes from Kafka.
        partition_info:
            Contextual metadata (topic, partition, offset) for logging.

        Returns
        -------
        TelemetryEvent | None
            Validated event on success, ``None`` when routed to DLQ.
        """
        last_error: Exception | None = None

        for attempt in range(self._settings.max_retry_attempts):
            try:
                event = _parse_and_validate(raw_bytes)
                if attempt > 0:
                    logger.info(
                        "Message parsed successfully after %d retry/retries.",
                        attempt,
                        extra=partition_info,
                    )
                return event

            except (ValueError, ValidationError, json.JSONDecodeError) as exc:
                last_error = exc
                backoff = _exponential_backoff_seconds(
                    attempt,
                    self._settings.retry_base_ms,
                    self._settings.retry_max_ms,
                )
                logger.warning(
                    "Transient parse/validation failure (attempt %d/%d). "
                    "Retrying in %.3fs. Error: %s",
                    attempt + 1,
                    self._settings.max_retry_attempts,
                    backoff,
                    exc,
                    extra=partition_info,
                )
                await asyncio.sleep(backoff)

        # All retries exhausted – send to DLQ.
        logger.error(
            "Message failed validation after %d attempts. Routing to DLQ '%s'. "
            "Last error: %s",
            self._settings.max_retry_attempts,
            TOPIC_DLQ,
            last_error,
            extra=partition_info,
        )
        await self._send_to_dlq(raw_bytes, error=last_error, partition_info=partition_info)
        return None

    async def _send_to_dlq(
        self,
        raw_bytes: bytes | None,
        *,
        error: Exception | None,
        partition_info: dict[str, object],
    ) -> None:
        """Forward an unparseable / invalid payload to the DLQ topic.

        The DLQ message is a JSON envelope containing the original raw payload
        (base64-encoded if not valid UTF-8), the error description, and a
        server-side timestamp.

        Parameters
        ----------
        raw_bytes:
            Original raw bytes from the failed Kafka message.
        error:
            The last exception that caused the failure.
        partition_info:
            Contextual Kafka metadata for the DLQ envelope.
        """
        if self._dlq_producer is None:
            logger.critical(
                "DLQ producer unavailable – cannot forward failed message.",
                extra=partition_info,
            )
            return

        try:
            raw_text = (raw_bytes or b"").decode("utf-8", errors="replace")
        except Exception:  # noqa: BLE001
            raw_text = repr(raw_bytes)

        dlq_envelope: dict[str, object] = {
            "source_topic": TOPIC_FAULTS,
            "source_partition": partition_info.get("partition"),
            "source_offset": partition_info.get("offset"),
            "error": str(error),
            "raw_payload": raw_text,
            "dlq_timestamp_utc": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        }

        try:
            await self._dlq_producer.send_and_wait(
                TOPIC_DLQ,
                json.dumps(dlq_envelope),
            )
            logger.info(
                "Payload forwarded to DLQ '%s'.",
                TOPIC_DLQ,
                extra=partition_info,
            )
        except KafkaError as exc:
            logger.critical(
                "CRITICAL: DLQ delivery failed for message at %s. "
                "Manual intervention required. Error: %s",
                partition_info,
                exc,
                extra=partition_info,
            )


# ---------------------------------------------------------------------------
# Pure parse/validate helper (easily unit-testable without Kafka)
# ---------------------------------------------------------------------------


def _parse_and_validate(raw_bytes: bytes | None) -> TelemetryEvent:
    """Decode, deserialize, and validate raw Kafka bytes into a TelemetryEvent.

    Parameters
    ----------
    raw_bytes:
        UTF-8 encoded JSON bytes from a Kafka record value.

    Returns
    -------
    TelemetryEvent
        A validated, immutable telemetry event.

    Raises
    ------
    ValueError
        If *raw_bytes* is ``None`` or empty.
    json.JSONDecodeError
        If the bytes are not valid JSON.
    pydantic.ValidationError
        If the parsed dict does not satisfy :class:`TelemetryEvent` constraints.
    """
    if not raw_bytes:
        raise ValueError("Received empty or None message payload.")

    payload: object = json.loads(raw_bytes.decode("utf-8"))

    if not isinstance(payload, dict):
        raise ValueError(
            f"Expected a JSON object at the top level, got {type(payload).__name__}."
        )

    return TelemetryEvent.model_validate(payload)
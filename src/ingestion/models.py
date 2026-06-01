"""
TelcOS Lite – Ingestion Layer: Domain Models
=============================================
Defines validated Pydantic V2 domain models for inbound telemetry events.

Design decisions
----------------
* ``sla_expiration`` is a computed field; callers must NOT supply it – it is
  always derived as ``telemetry_timestamp + 30 s`` (Rule: SLA target 30 s).
* All datetimes are timezone-aware.  Naive datetimes are rejected at parse
  time so that downstream comparators never hit ambiguous offset arithmetic.
* IP validation delegates to Python's ``ipaddress`` stdlib rather than a
  hand-rolled regex, which correctly handles both IPv4 and IPv6.
"""

from __future__ import annotations

import ipaddress
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

SLA_WINDOW_SECONDS: int = 30
"""Hard SLA target (seconds) defined at module level for single-source truth."""


# ---------------------------------------------------------------------------
# Model
# ---------------------------------------------------------------------------


class TelemetryEvent(BaseModel):
    """Immutable, validated representation of a network-fault telemetry event.

    Attributes
    ----------
    alarm:
        Human-readable alarm identifier (e.g. ``"BGP_PEER_DOWN"``).
    asset:
        Logical asset or device name that raised the alarm.
    ip:
        Management-plane IP address of the affected device (IPv4 or IPv6).
        Validated via :mod:`ipaddress`.
    telemetry_timestamp:
        UTC-aware moment the alarm was recorded by the originating system.
    sla_expiration:
        Derived field – always ``telemetry_timestamp + 30 s``.  Not accepted
        from external payloads; computed automatically via a model validator.

    Examples
    --------
    >>> from datetime import datetime, timezone
    >>> event = TelemetryEvent(
    ...     alarm="LINK_DOWN",
    ...     asset="core-router-01",
    ...     ip="10.0.0.1",
    ...     telemetry_timestamp=datetime.now(tz=timezone.utc),
    ... )
    >>> (event.sla_expiration - event.telemetry_timestamp).seconds
    30
    """

    model_config = ConfigDict(
        frozen=True,          # enforce immutability after construction
        populate_by_name=True,
        str_strip_whitespace=True,
    )

    alarm: str = Field(
        ...,
        min_length=1,
        description="Alarm identifier raised by the network element.",
    )
    asset: str = Field(
        ...,
        min_length=1,
        description="Logical name of the affected network asset.",
    )
    ip: str = Field(
        ...,
        description="Management-plane IPv4 or IPv6 address of the device.",
    )
    telemetry_timestamp: datetime = Field(
        ...,
        description="Timezone-aware UTC datetime when the alarm was recorded.",
    )
    sla_expiration: datetime = Field(
        default=None,  # type: ignore[assignment]
        description=(
            "Derived. Absolute deadline by which remediation must complete. "
            "Always telemetry_timestamp + 30 s. Do not supply in payloads."
        ),
    )

    # ------------------------------------------------------------------
    # Field validators
    # ------------------------------------------------------------------

    @field_validator("ip", mode="before")
    @classmethod
    def validate_ip_address(cls, value: Any) -> str:
        """Reject values that are not valid IPv4 or IPv6 addresses.

        Parameters
        ----------
        value:
            Raw value from the incoming payload.

        Returns
        -------
        str
            Normalised string representation of the validated IP.

        Raises
        ------
        ValueError
            If *value* cannot be parsed as a valid IP address.
        """
        try:
            parsed = ipaddress.ip_address(str(value).strip())
        except ValueError as exc:
            raise ValueError(
                f"'{value}' is not a valid IPv4 or IPv6 address."
            ) from exc
        return str(parsed)

    @field_validator("telemetry_timestamp", mode="before")
    @classmethod
    def ensure_timezone_aware(cls, value: Any) -> datetime:
        """Coerce ISO-8601 strings and reject timezone-naive datetimes.

        Parameters
        ----------
        value:
            Raw datetime value (``str`` or :class:`~datetime.datetime`).

        Returns
        -------
        datetime
            Timezone-aware :class:`~datetime.datetime` instance.

        Raises
        ------
        ValueError
            If *value* is a naive datetime (no tzinfo) or not parseable.
        """
        if isinstance(value, str):
            try:
                value = datetime.fromisoformat(value)
            except ValueError as exc:
                raise ValueError(
                    f"Cannot parse '{value}' as an ISO-8601 datetime."
                ) from exc

        if not isinstance(value, datetime):
            raise ValueError(
                f"Expected a datetime or ISO-8601 string, got {type(value).__name__}."
            )

        if value.tzinfo is None:
            raise ValueError(
                "telemetry_timestamp must be timezone-aware (tzinfo must not be None). "
                "Supply a UTC offset or 'Z' suffix, e.g. '2024-01-15T12:00:00Z'."
            )

        # Normalise to UTC for consistent downstream comparison.
        return value.astimezone(timezone.utc)

    # ------------------------------------------------------------------
    # Model validator – derive sla_expiration
    # ------------------------------------------------------------------

    @model_validator(mode="after")
    def derive_sla_expiration(self) -> "TelemetryEvent":
        """Compute ``sla_expiration`` from ``telemetry_timestamp``.

        This validator runs *after* all field validators so
        ``telemetry_timestamp`` is guaranteed to be timezone-aware UTC.

        Returns
        -------
        TelemetryEvent
            The model instance with ``sla_expiration`` populated.
        """
        # Bypass Pydantic's frozen guard via object.__setattr__ during
        # construction (model_validator(mode='after') is called before freeze).
        object.__setattr__(
            self,
            "sla_expiration",
            self.telemetry_timestamp + timedelta(seconds=SLA_WINDOW_SECONDS),
        )
        return self
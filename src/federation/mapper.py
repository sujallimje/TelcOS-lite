"""
src/federation/mapper.py
------------------------
TelcOS Lite – TMF621 Trouble Ticket Mapper.

Converts a LangGraph ``GraphState`` snapshot into a fully-formed
TMF621 TroubleTicket payload ready for dispatch to downstream OSS/BSS
systems (e.g., ServiceNow, Remedy).

Specification reference:
    TM Forum TMF621 Trouble Ticket Management API v4.0
"""

from __future__ import annotations

import logging
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SLA budget (seconds) – must resolve within 30 s per project constraint
# ---------------------------------------------------------------------------
_SLA_SECONDS: int = 30


# ---------------------------------------------------------------------------
# GraphState contract (subset consumed by this mapper)
# ---------------------------------------------------------------------------

class GraphState(BaseModel):
    """
    Minimal projection of the LangGraph workflow state used by the federation
    layer.  Only the fields required for TMF621 mapping are declared here;
    additional keys present in the full pipeline state are ignored via
    ``model_config = ConfigDict(extra="allow")``.
    """

    model_config = {"extra": "allow"}

    # Correlation / routing
    incident_id: str = Field(
        description="Unique incident identifier produced by the detection stage.",
    )
    alarm_type: str = Field(
        description="Canonical alarm classification (e.g. 'BGP_SESSION_DOWN').",
    )
    alarm_severity: str = Field(
        default="MINOR",
        description="Alarm severity: CRITICAL | MAJOR | MINOR | WARNING | INDETERMINATE.",
    )
    alarm_description: str = Field(
        default="",
        description="Human-readable alarm description derived from telemetry.",
    )

    # Asset / topology
    asset_name: str = Field(
        description="Logical name of the affected network element.",
    )
    asset_type: str = Field(
        default="NetworkElement",
        description="Asset class (e.g. 'Router', 'Switch', 'OLT').",
    )
    device_ip: str = Field(
        description="Management-plane IP address of the affected device.",
    )

    # Remediation outcome
    resolution_status: str = Field(
        default="IN_PROGRESS",
        description=(
            "Current remediation status: "
            "ACKNOWLEDGED | IN_PROGRESS | RESOLVED | FAILED."
        ),
    )
    resolution_notes: str = Field(
        default="",
        description="Free-text remediation notes produced by the autonomic engine.",
    )

    # Timing
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=timezone.utc),
        description="UTC timestamp when the fault was first detected.",
    )

    @field_validator("alarm_severity")
    @classmethod
    def _validate_severity(cls, v: str) -> str:
        allowed = {"CRITICAL", "MAJOR", "MINOR", "WARNING", "INDETERMINATE"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(
                f"alarm_severity '{v}' is not one of {allowed}."
            )
        return upper

    @field_validator("resolution_status")
    @classmethod
    def _validate_resolution_status(cls, v: str) -> str:
        allowed = {"ACKNOWLEDGED", "IN_PROGRESS", "RESOLVED", "FAILED"}
        upper = v.upper()
        if upper not in allowed:
            raise ValueError(
                f"resolution_status '{v}' is not one of {allowed}."
            )
        return upper


# ---------------------------------------------------------------------------
# TMF621 payload models
# ---------------------------------------------------------------------------

class TMF621Alarm(BaseModel):
    """Embeds alarm context inside a TMF621 ticket."""

    alarmType: str
    severity: str
    description: str


class TMF621Asset(BaseModel):
    """Represents the affected managed entity."""

    name: str
    type: str


class TMF621Resolution(BaseModel):
    """Captures the autonomic engine's remediation outcome."""

    status: str
    notes: str


class TMF621Payload(BaseModel):
    """
    TMF621 TroubleTicket representation.

    All datetime fields are serialised as ISO-8601 strings with UTC offset
    so downstream systems need no additional parsing.
    """

    id: str = Field(description="Globally unique ticket identifier (UUID4).")
    alarm: TMF621Alarm
    asset: TMF621Asset
    ip: str = Field(description="Management IP of the affected device.")
    status: str = Field(
        description="Ticket lifecycle status aligned to TMF621 statusType enum.",
    )
    resolution: TMF621Resolution
    createdDate: str = Field(
        description="ISO-8601 UTC timestamp of ticket creation.",
    )
    slaExpiration: str = Field(
        description="ISO-8601 UTC deadline by which the fault must be resolved.",
    )

    model_config = {"populate_by_name": True}


# ---------------------------------------------------------------------------
# Status translation table
# ---------------------------------------------------------------------------

_RESOLUTION_TO_TMF621_STATUS: dict[str, str] = {
    "ACKNOWLEDGED": "acknowledged",
    "IN_PROGRESS": "inProgress",
    "RESOLVED": "resolved",
    "FAILED": "pending",  # TMF621 has no 'failed'; park as 'pending' for review
}


# ---------------------------------------------------------------------------
# Mapper
# ---------------------------------------------------------------------------

class TMF621Mapper:
    """
    Stateless mapper that converts a ``GraphState`` instance into a
    ``TMF621Payload``.

    Usage::

        mapper = TMF621Mapper()
        payload = mapper.map(state)
    """

    def __init__(self, sla_seconds: int = _SLA_SECONDS) -> None:
        """
        Initialise the mapper.

        Args:
            sla_seconds: SLA window in seconds from ticket creation.
                         Defaults to the project-wide 30-second target.
        """
        self._sla_seconds = sla_seconds

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------

    def map(self, state: GraphState) -> TMF621Payload:
        """
        Convert *state* into a ``TMF621Payload``.

        Args:
            state: Validated ``GraphState`` from the LangGraph pipeline.

        Returns:
            A fully-populated ``TMF621Payload`` ready for HTTP dispatch.

        Raises:
            ValueError: If a required field on *state* is invalid or missing.
        """
        now_utc: datetime = datetime.now(tz=timezone.utc)
        sla_deadline: datetime = now_utc + timedelta(seconds=self._sla_seconds)

        tmf621_status = _RESOLUTION_TO_TMF621_STATUS.get(
            state.resolution_status, "inProgress"
        )

        payload = TMF621Payload(
            id=str(uuid.uuid4()),
            alarm=TMF621Alarm(
                alarmType=state.alarm_type,
                severity=state.alarm_severity,
                description=state.alarm_description,
            ),
            asset=TMF621Asset(
                name=state.asset_name,
                type=state.asset_type,
            ),
            ip=state.device_ip,
            status=tmf621_status,
            resolution=TMF621Resolution(
                status=state.resolution_status,
                notes=state.resolution_notes,
            ),
            createdDate=now_utc.isoformat(),
            slaExpiration=sla_deadline.isoformat(),
        )

        logger.info(
            "TMF621 payload mapped",
            extra={
                "ticket_id": payload.id,
                "incident_id": state.incident_id,
                "alarm_type": state.alarm_type,
                "severity": state.alarm_severity,
                "device_ip": state.device_ip,
                "tmf621_status": tmf621_status,
                "sla_expiration": payload.slaExpiration,
            },
        )

        return payload

    def map_from_dict(self, raw: dict[str, Any]) -> TMF621Payload:
        """
        Convenience wrapper that validates *raw* as a ``GraphState`` before
        mapping.

        Args:
            raw: Dictionary representation of a ``GraphState``.

        Returns:
            A fully-populated ``TMF621Payload``.

        Raises:
            pydantic.ValidationError: If *raw* does not satisfy the
                ``GraphState`` schema.
        """
        state = GraphState.model_validate(raw)
        return self.map(state)
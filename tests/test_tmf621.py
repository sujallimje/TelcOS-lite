"""
Tests for TMF621 Trouble Ticket Mapping and Client Federation.
=============================================================
Tests mapper schema compliance, validators, SLA calculations,
and the async HTTP client's retry/back-off policies under success,
error, and timeout conditions.
"""

import asyncio
from datetime import datetime, timezone, timedelta
from unittest.mock import AsyncMock, MagicMock, patch
import httpx
import pytest
from pydantic import ValidationError

from src.federation.client import TMF621Client, FederationError
from src.federation.mapper import (
    TMF621Mapper,
    GraphState as MapperGraphState,
    TMF621Payload,
)


def run_async(coro):
    """Helper to run async coroutines in a synchronous test."""
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Mapper Tests
# ---------------------------------------------------------------------------

def test_mapper_valid_state_mapping() -> None:
    """Test mapping a valid GraphState to TMF621Payload."""
    state = MapperGraphState(
        incident_id="inc-123",
        alarm_type="BGP_SESSION_DOWN",
        alarm_severity="CRITICAL",
        alarm_description="BGP session down between peer routers",
        asset_name="router-01",
        asset_type="Router",
        device_ip="192.0.2.1",
        resolution_status="RESOLVED",
        resolution_notes="BGP session restored by clearing IP BGP soft",
    )

    mapper = TMF621Mapper()
    payload = mapper.map(state)

    assert isinstance(payload, TMF621Payload)
    assert payload.alarm.alarmType == "BGP_SESSION_DOWN"
    assert payload.alarm.severity == "CRITICAL"
    assert payload.alarm.description == "BGP session down between peer routers"
    assert payload.asset.name == "router-01"
    assert payload.asset.type == "Router"
    assert payload.ip == "192.0.2.1"
    # Status translation: RESOLVED -> resolved
    assert payload.status == "resolved"
    assert payload.resolution.status == "RESOLVED"
    assert payload.resolution.notes == "BGP session restored by clearing IP BGP soft"


def test_mapper_sla_expiration_calculation() -> None:
    """Test that TMF621 ticket SLA matches creation date + 30 seconds."""
    state = MapperGraphState(
        incident_id="inc-123",
        alarm_type="LINK_DOWN",
        asset_name="switch-01",
        device_ip="10.0.0.1",
    )
    mapper = TMF621Mapper(sla_seconds=30)
    payload = mapper.map(state)

    created_dt = datetime.fromisoformat(payload.createdDate)
    sla_dt = datetime.fromisoformat(payload.slaExpiration)
    
    # SLA duration must be exactly 30 seconds from creation date
    assert (sla_dt - created_dt).total_seconds() == pytest.approx(30.0)


def test_mapper_severity_validation() -> None:
    """Test that invalid severities in GraphState raise validation errors."""
    valid_severities = ["CRITICAL", "MAJOR", "MINOR", "WARNING", "INDETERMINATE"]
    
    # Test valid severities pass validation
    for sev in valid_severities:
        state = MapperGraphState(
            incident_id="inc-123",
            alarm_type="LINK_DOWN",
            alarm_severity=sev,
            asset_name="switch-01",
            device_ip="10.0.0.1",
        )
        assert state.alarm_severity == sev

    # Test invalid severity is rejected
    with pytest.raises(ValidationError) as exc_info:
        MapperGraphState(
            incident_id="inc-123",
            alarm_type="LINK_DOWN",
            alarm_severity="CRIT",  # must be exact CRITICAL
            asset_name="switch-01",
            device_ip="10.0.0.1",
        )
    assert "alarm_severity" in str(exc_info.value)


def test_mapper_resolution_status_validation() -> None:
    """Test that invalid resolution statuses in GraphState raise validation errors."""
    valid_statuses = ["ACKNOWLEDGED", "IN_PROGRESS", "RESOLVED", "FAILED"]

    # Test valid statuses pass validation
    for status in valid_statuses:
        state = MapperGraphState(
            incident_id="inc-123",
            alarm_type="LINK_DOWN",
            asset_name="switch-01",
            device_ip="10.0.0.1",
            resolution_status=status,
        )
        assert state.resolution_status == status

    # Test invalid status is rejected
    with pytest.raises(ValidationError) as exc_info:
        MapperGraphState(
            incident_id="inc-123",
            alarm_type="LINK_DOWN",
            asset_name="switch-01",
            device_ip="10.0.0.1",
            resolution_status="COMPLETED",  # invalid status
        )
    assert "resolution_status" in str(exc_info.value)


# ---------------------------------------------------------------------------
# Client Tests (with mocked httpx calls and asyncio sleep)
# ---------------------------------------------------------------------------

@pytest.fixture
def sample_payload() -> TMF621Payload:
    """Fixture returning a pre-configured valid TMF621Payload."""
    return TMF621Payload(
        id="ticket-uuid-12345",
        alarm={"alarmType": "LINK_DOWN", "severity": "MAJOR", "description": "Link down"},
        asset={"name": "router-01", "type": "Router"},
        ip="192.0.2.1",
        status="inProgress",
        resolution={"status": "IN_PROGRESS", "notes": ""},
        createdDate=datetime.now(timezone.utc).isoformat(),
        slaExpiration=(datetime.now(timezone.utc) + timedelta(seconds=30)).isoformat(),
    )


@patch("src.federation.client.httpx.AsyncClient.post")
def test_client_post_ticket_success(mock_post: MagicMock, sample_payload: TMF621Payload) -> None:
    """Test successful dispatch of TMF621 ticket."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 201
    mock_response.is_success = True
    mock_response.json.return_value = {"id": "ticket-uuid-12345", "status": "created"}
    mock_post.return_value = mock_response

    async def run() -> dict:
        async with TMF621Client(base_url="http://mock-service") as client:
            return await client.post_ticket(sample_payload)

    result = run_async(run())
    assert result == {"id": "ticket-uuid-12345", "status": "created"}
    mock_post.assert_called_once()


@patch("src.federation.client.httpx.AsyncClient.post")
def test_client_post_ticket_4xx_immediate_error(mock_post: MagicMock, sample_payload: TMF621Payload) -> None:
    """Test that a client error (4xx) raises FederationError immediately without retrying."""
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 400
    mock_response.is_success = False
    mock_response.text = "Bad Request"
    mock_post.return_value = mock_response

    async def run() -> None:
        async with TMF621Client(base_url="http://mock-service", max_attempts=3) as client:
            await client.post_ticket(sample_payload)

    with pytest.raises(FederationError) as exc_info:
        run_async(run())

    assert exc_info.value.last_status == 400
    assert "Non-retryable HTTP 400" in str(exc_info.value)
    # 400 Client error should not trigger any retry attempts (called exactly once)
    assert mock_post.call_count == 1


@patch("asyncio.sleep")
@patch("src.federation.client.httpx.AsyncClient.post")
def test_client_post_ticket_5xx_retry_and_exhaustion(
    mock_post: MagicMock, mock_sleep: MagicMock, sample_payload: TMF621Payload
) -> None:
    """Test that server errors (5xx) trigger retries and eventually raise FederationError."""
    # Mock a server error response
    mock_response = MagicMock(spec=httpx.Response)
    mock_response.status_code = 503
    mock_response.is_success = False
    mock_response.text = "Service Unavailable"
    mock_post.return_value = mock_response

    async def run() -> None:
        async with TMF621Client(
            base_url="http://mock-service",
            max_attempts=3,
            backoff_factor=0.1,
        ) as client:
            await client.post_ticket(sample_payload)

    with pytest.raises(FederationError) as exc_info:
        run_async(run())

    assert exc_info.value.last_status == 503
    assert "after 3 attempts" in str(exc_info.value)
    # Assert that post was called 3 times (1 initial + 2 retries)
    assert mock_post.call_count == 3
    # Assert sleep was called twice with exponential backoff: 0.1 * 2^0 = 0.1 and 0.1 * 2^1 = 0.2
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(0.1)
    mock_sleep.assert_any_call(0.2)


@patch("asyncio.sleep")
@patch("src.federation.client.httpx.AsyncClient.post")
def test_client_post_ticket_transport_error_retry(
    mock_post: MagicMock, mock_sleep: MagicMock, sample_payload: TMF621Payload
) -> None:
    """Test that connection/transport errors trigger retries and raise FederationError on exhaustion."""
    # Mock a transport error (e.g. timeout, connection refused)
    mock_post.side_effect = httpx.ConnectTimeout("Connection timed out")

    async def run() -> None:
        async with TMF621Client(
            base_url="http://mock-service",
            max_attempts=3,
            backoff_factor=0.5,
        ) as client:
            await client.post_ticket(sample_payload)

    with pytest.raises(FederationError) as exc_info:
        run_async(run())

    assert "after 3 attempts" in str(exc_info.value)
    assert mock_post.call_count == 3
    assert mock_sleep.call_count == 2
    mock_sleep.assert_any_call(0.5)
    mock_sleep.assert_any_call(1.0)

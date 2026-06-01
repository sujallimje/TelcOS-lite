"""
Tests for the TelcOS Lite Domain Models.
=========================================
Tests validation, timezone coercion, SLA expiration calculation,
and immutability rules for TelemetryEvent.
"""

from datetime import datetime, timezone, timedelta
import pytest
from pydantic import ValidationError

from src.ingestion.models import TelemetryEvent, SLA_WINDOW_SECONDS


def test_telemetry_event_valid_construction() -> None:
    """Test that a valid TelemetryEvent is parsed successfully and SLA is set."""
    now_utc = datetime.now(timezone.utc)
    event = TelemetryEvent(
        alarm="BGP_PEER_DOWN",
        asset="core-router-01",
        ip="10.0.0.1",
        telemetry_timestamp=now_utc,
    )
    
    assert event.alarm == "BGP_PEER_DOWN"
    assert event.asset == "core-router-01"
    assert event.ip == "10.0.0.1"
    assert event.telemetry_timestamp == now_utc
    # Check that sla_expiration is exactly telemetry_timestamp + 30s
    expected_sla = now_utc + timedelta(seconds=SLA_WINDOW_SECONDS)
    assert event.sla_expiration == expected_sla


def test_telemetry_event_utc_coercion_and_timezone_aware() -> None:
    """Test that timezone-aware string/datetime is coerced to UTC."""
    # Test ISO format string with 'Z'
    event_str = TelemetryEvent(
        alarm="LINK_DOWN",
        asset="switch-02",
        ip="172.16.100.5",
        telemetry_timestamp="2026-06-01T12:00:00Z",
    )
    assert event_str.telemetry_timestamp.tzinfo == timezone.utc
    assert event_str.telemetry_timestamp.hour == 12

    # Test timezone offset (e.g. +05:30)
    event_offset = TelemetryEvent(
        alarm="LINK_DOWN",
        asset="switch-02",
        ip="172.16.100.5",
        telemetry_timestamp="2026-06-01T12:00:00+02:00",
    )
    # The datetime should be normalized to UTC (12:00 +02:00 = 10:00 UTC)
    assert event_offset.telemetry_timestamp.tzinfo == timezone.utc
    assert event_offset.telemetry_timestamp.hour == 10
    assert event_offset.telemetry_timestamp.minute == 0


def test_telemetry_event_naive_timestamp_rejected() -> None:
    """Test that naive datetimes (no timezone info) are rejected."""
    naive_dt = datetime.now()  # no tzinfo
    with pytest.raises(ValidationError) as exc_info:
        TelemetryEvent(
            alarm="CPU_HIGH",
            asset="router-03",
            ip="192.168.1.1",
            telemetry_timestamp=naive_dt,
        )
    assert "telemetry_timestamp must be timezone-aware" in str(exc_info.value)

    # Test naive ISO-8601 string
    with pytest.raises(ValidationError) as exc_info:
        TelemetryEvent(
            alarm="CPU_HIGH",
            asset="router-03",
            ip="192.168.1.1",
            telemetry_timestamp="2026-06-01T12:00:00",
        )
    assert "telemetry_timestamp must be timezone-aware" in str(exc_info.value)


def test_telemetry_event_invalid_timestamp_type_rejected() -> None:
    """Test that invalid types for telemetry_timestamp are rejected."""
    with pytest.raises(ValidationError) as exc_info:
        TelemetryEvent(
            alarm="CPU_HIGH",
            asset="router-03",
            ip="192.168.1.1",
            telemetry_timestamp=123.456,  # type: ignore[arg-type]
        )
    assert "Expected a datetime or ISO-8601 string" in str(exc_info.value)


def test_telemetry_event_ip_validation() -> None:
    """Test IPv4 and IPv6 address parsing and malformed IP rejection."""
    # Valid IPv4
    e_ipv4 = TelemetryEvent(
        alarm="LINK_DOWN",
        asset="pe-01",
        ip="192.0.2.1",
        telemetry_timestamp=datetime.now(timezone.utc),
    )
    assert e_ipv4.ip == "192.0.2.1"

    # Valid IPv4 with whitespace
    e_ipv4_ws = TelemetryEvent(
        alarm="LINK_DOWN",
        asset="pe-01",
        ip="  192.0.2.2  ",
        telemetry_timestamp=datetime.now(timezone.utc),
    )
    assert e_ipv4_ws.ip == "192.0.2.2"

    # Valid IPv6
    e_ipv6 = TelemetryEvent(
        alarm="LINK_DOWN",
        asset="pe-01",
        ip="2001:db8::1",
        telemetry_timestamp=datetime.now(timezone.utc),
    )
    assert e_ipv6.ip == "2001:db8::1"

    # Invalid IP formats
    with pytest.raises(ValidationError) as exc_info:
        TelemetryEvent(
            alarm="LINK_DOWN",
            asset="pe-01",
            ip="999.999.999.999",
            telemetry_timestamp=datetime.now(timezone.utc),
        )
    assert "is not a valid IPv4 or IPv6 address" in str(exc_info.value)

    with pytest.raises(ValidationError) as exc_info:
        TelemetryEvent(
            alarm="LINK_DOWN",
            asset="pe-01",
            ip="hostname.local",
            telemetry_timestamp=datetime.now(timezone.utc),
        )
    assert "is not a valid IPv4 or IPv6 address" in str(exc_info.value)


def test_telemetry_event_immutability_frozen() -> None:
    """Test that TelemetryEvent attributes are frozen and cannot be modified."""
    event = TelemetryEvent(
        alarm="INTERFACE_ERRORS",
        asset="leaf-01",
        ip="10.10.10.1",
        telemetry_timestamp=datetime.now(timezone.utc),
    )
    
    with pytest.raises((ValidationError, ValidationError, TypeError)):
        # Pydantic V2 raises ValidationError or raises TypeError when frozen attributes are mutated
        # Let's verify we cannot mutate attributes.
        event.alarm = "NEW_ALARM"  # type: ignore[misc]


def test_telemetry_event_min_length_constraints() -> None:
    """Test that alarm and asset fields require at least 1 character."""
    now = datetime.now(timezone.utc)
    
    # Empty alarm
    with pytest.raises(ValidationError) as exc_info:
        TelemetryEvent(
            alarm="",
            asset="router-1",
            ip="10.0.0.1",
            telemetry_timestamp=now,
        )
    assert "alarm" in str(exc_info.value)
    assert "String should have at least 1 character" in str(exc_info.value)

    # Empty asset
    with pytest.raises(ValidationError) as exc_info:
        TelemetryEvent(
            alarm="TEST_ALARM",
            asset="",
            ip="10.0.0.1",
            telemetry_timestamp=now,
        )
    assert "asset" in str(exc_info.value)
    assert "String should have at least 1 character" in str(exc_info.value)

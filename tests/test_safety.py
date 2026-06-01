"""
Tests for the Safety Node and Veto Logic.
==========================================
Tests the deterministic safety gate logic:
- Blocked command patterns (reload, shutdown, erase, format).
- Power threshold validations.
"""

import asyncio
import pytest
from src.cognitive.nodes import (
    safety_node,
    GraphState,
    CognitiveConfig,
    SafetyResult,
)


def run_async(coro):
    """Helper to run async coroutines in a synchronous test."""
    return asyncio.run(coro)


def test_safety_node_pass_standard_commands() -> None:
    """Test that safe diagnostic commands pass safety evaluation."""
    state = GraphState(
        raw_alarm={"alarm_id": "123", "power_pct": 50.0},
        proposed_commands=["show version", "show ip interface brief", "show running-config"],
    )
    
    updated_state = run_async(safety_node(state))
    
    assert updated_state.safety is not None
    assert updated_state.safety.is_safe is True
    assert "All deterministic safety checks passed." in updated_state.safety.reason


def test_safety_node_blocks_prohibited_commands() -> None:
    """Test that commands matching blocked patterns are rejected."""
    blocked_commands = [
        "reload",
        "shutdown",
        "erase startup-config",
        "format flash:",
        "reload force",
        "shutdown interface Gi0/1",
    ]

    for cmd in blocked_commands:
        state = GraphState(
            raw_alarm={"alarm_id": "123"},
            proposed_commands=["show version", cmd, "show ip route"],
        )
        updated_state = run_async(safety_node(state))
        
        assert updated_state.safety is not None
        assert updated_state.safety.is_safe is False
        assert f"matches blocked pattern" in updated_state.safety.reason


def test_safety_node_case_insensitivity_and_boundaries() -> None:
    """Test that blocked patterns match case-insensitively and handle boundaries."""
    # Test case insensitivity
    state_case = GraphState(
        raw_alarm={"alarm_id": "123"},
        proposed_commands=["ReLoAd"],
    )
    updated_state = run_async(safety_node(state_case))
    assert updated_state.safety is not None
    assert updated_state.safety.is_safe is False

    # Test word boundaries: "shutdown" should be blocked, but "no shutdown" should also be blocked
    # because it contains the word "shutdown".
    state_no_shutdown = GraphState(
        raw_alarm={"alarm_id": "123"},
        proposed_commands=["no shutdown"],
    )
    updated_state = run_async(safety_node(state_no_shutdown))
    assert updated_state.safety is not None
    assert updated_state.safety.is_safe is False

    # A command like "show power-format" contains "format" but not as a word boundary?
    # Wait, the pattern is r"\bformat\b". Let's check:
    # "show power-format": "format" is preceded by "-" which is a non-word character,
    # so \b matches the boundary between "-" and "f". Thus, "format" matches!
    # Let's test a command that contains the substring "format" but NO boundary, like "informational".
    # "informational" contains "format"? No, it doesn't.
    # What about "deformat"? "format" is preceded by "de" which are word characters, so \b doesn't match!
    state_no_boundary = GraphState(
        raw_alarm={"alarm_id": "123"},
        proposed_commands=["deformat device"],
    )
    updated_state = run_async(safety_node(state_no_boundary))
    assert updated_state.safety is not None
    assert updated_state.safety.is_safe is True


def test_safety_node_power_threshold_pass() -> None:
    """Test that power level at or above threshold is allowed."""
    config = CognitiveConfig(power_threshold_pct=20.0)
    
    # Exactly 20%
    state_20 = GraphState(
        raw_alarm={"alarm_id": "123", "power_pct": 20.0},
        proposed_commands=["show version"],
    )
    updated_state = run_async(safety_node(state_20, config))
    assert updated_state.safety is not None
    assert updated_state.safety.is_safe is True

    # Above 20%
    state_50 = GraphState(
        raw_alarm={"alarm_id": "123", "power_percent": "50.5"},
        proposed_commands=["show version"],
    )
    updated_state = run_async(safety_node(state_50, config))
    assert updated_state.safety is not None
    assert updated_state.safety.is_safe is True


def test_safety_node_power_threshold_violations() -> None:
    """Test that power level below threshold is blocked."""
    config = CognitiveConfig(power_threshold_pct=25.0)
    
    # 19.9%
    state_19 = GraphState(
        raw_alarm={"alarm_id": "123", "pwr_pct": 19.9},
        proposed_commands=["show version"],
    )
    updated_state = run_async(safety_node(state_19, config))
    
    assert updated_state.safety is not None
    assert updated_state.safety.is_safe is False
    assert "below the minimum safe threshold" in updated_state.safety.reason


def test_safety_node_missing_power_pct() -> None:
    """Test that missing power parameter defaults to passing."""
    # When power_pct is missing from the payload, it shouldn't block execution.
    state = GraphState(
        raw_alarm={"alarm_id": "123"},
        proposed_commands=["show version"],
    )
    updated_state = run_async(safety_node(state))
    assert updated_state.safety is not None
    assert updated_state.safety.is_safe is True


def test_safety_node_malformed_power_pct() -> None:
    """Test that malformed/non-numeric power parameter is handled gracefully (defaults to passing)."""
    state = GraphState(
        raw_alarm={"alarm_id": "123", "power_pct": "not-a-number"},
        proposed_commands=["show version"],
    )
    updated_state = run_async(safety_node(state))
    assert updated_state.safety is not None
    assert updated_state.safety.is_safe is True
